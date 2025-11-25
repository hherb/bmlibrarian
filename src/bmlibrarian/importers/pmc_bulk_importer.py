"""PMC Open Access bulk importer.

Downloads and imports PMC Open Access baseline and incremental packages
for offline access to biomedical literature.

Features:
- Resumable downloads with progress tracking
- Configurable rate limiting (polite to NCBI servers)
- License-based filtering (commercial, non-commercial, other)
- PMCID range filtering for selective downloads
- Automatic extraction of PDFs and NXML full-text
- Database integration for metadata and full-text storage

Usage:
    from bmlibrarian.importers.pmc_bulk_importer import PMCBulkImporter

    importer = PMCBulkImporter(
        output_dir=Path('~/pmc_archive'),
        license_types=['oa_comm'],  # Commercial use allowed
        delay_between_files=120  # 2 minutes between downloads
    )

    # Download baseline packages
    importer.download_baseline()

    # Import to database
    importer.import_to_database()
"""

import ftplib
import io
import json
import logging
import re
import tarfile
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable, Iterator
from urllib.parse import urlparse

from bmlibrarian.discovery.pmc_package_downloader import NXMLParser

logger = logging.getLogger(__name__)

# PMC FTP server details
PMC_FTP_HOST = "ftp.ncbi.nlm.nih.gov"
PMC_FTP_BASE = "/pub/pmc"
PMC_HTTPS_BASE = "https://ftp.ncbi.nlm.nih.gov/pub/pmc"

# Default configuration
DEFAULT_DELAY_SECONDS = 120  # 2 minutes between files (polite)
DEFAULT_FTP_TIMEOUT = 300  # 5 minutes for large files
DEFAULT_MAX_RETRIES = 3


class LicenseType(Enum):
    """PMC Open Access license categories."""
    COMMERCIAL = "oa_comm"      # CC0, CC BY, CC BY-SA, CC BY-ND
    NON_COMMERCIAL = "oa_noncomm"  # CC BY-NC, CC BY-NC-SA, CC BY-NC-ND
    OTHER = "oa_other"          # Custom/no license


class PackageFormat(Enum):
    """Package content format."""
    XML = "xml"   # NXML + images
    TXT = "txt"   # Plain text


@dataclass
class PackageInfo:
    """Information about a bulk package file."""
    filename: str
    license_type: LicenseType
    format: PackageFormat
    pmcid_range: str  # e.g., "PMC001xxxxxx"
    is_baseline: bool
    date: str  # YYYY-MM-DD
    size_bytes: int = 0
    url: str = ""
    downloaded: bool = False
    extracted: bool = False
    imported: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'filename': self.filename,
            'license_type': self.license_type.value,
            'format': self.format.value,
            'pmcid_range': self.pmcid_range,
            'is_baseline': self.is_baseline,
            'date': self.date,
            'size_bytes': self.size_bytes,
            'url': self.url,
            'downloaded': self.downloaded,
            'extracted': self.extracted,
            'imported': self.imported
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PackageInfo':
        """Create from dictionary."""
        return cls(
            filename=data['filename'],
            license_type=LicenseType(data['license_type']),
            format=PackageFormat(data['format']),
            pmcid_range=data['pmcid_range'],
            is_baseline=data['is_baseline'],
            date=data['date'],
            size_bytes=data.get('size_bytes', 0),
            url=data.get('url', ''),
            downloaded=data.get('downloaded', False),
            extracted=data.get('extracted', False),
            imported=data.get('imported', False)
        )


@dataclass
class DownloadProgress:
    """Tracks overall download progress."""
    total_packages: int = 0
    downloaded_packages: int = 0
    total_bytes: int = 0
    downloaded_bytes: int = 0
    total_articles: int = 0
    imported_articles: int = 0
    errors: List[str] = field(default_factory=list)
    start_time: Optional[datetime] = None
    last_update: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'total_packages': self.total_packages,
            'downloaded_packages': self.downloaded_packages,
            'total_bytes': self.total_bytes,
            'downloaded_bytes': self.downloaded_bytes,
            'total_articles': self.total_articles,
            'imported_articles': self.imported_articles,
            'errors': self.errors,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'last_update': self.last_update.isoformat() if self.last_update else None
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DownloadProgress':
        """Create from dictionary."""
        return cls(
            total_packages=data.get('total_packages', 0),
            downloaded_packages=data.get('downloaded_packages', 0),
            total_bytes=data.get('total_bytes', 0),
            downloaded_bytes=data.get('downloaded_bytes', 0),
            total_articles=data.get('total_articles', 0),
            imported_articles=data.get('imported_articles', 0),
            errors=data.get('errors', []),
            start_time=datetime.fromisoformat(data['start_time']) if data.get('start_time') else None,
            last_update=datetime.fromisoformat(data['last_update']) if data.get('last_update') else None
        )


@dataclass
class ArticleMetadata:
    """Metadata extracted from NXML article."""
    pmcid: str
    pmid: Optional[str] = None
    doi: Optional[str] = None
    title: Optional[str] = None
    abstract: Optional[str] = None
    authors: List[str] = field(default_factory=list)
    journal: Optional[str] = None
    publication_date: Optional[str] = None
    year: Optional[int] = None
    full_text: Optional[str] = None
    pdf_filename: Optional[str] = None
    nxml_filename: Optional[str] = None
    license: Optional[str] = None


class PMCBulkImporter:
    """Bulk importer for PMC Open Access packages.

    Downloads baseline and incremental packages from PMC FTP,
    extracts articles, and imports them into the database.
    """

    def __init__(
        self,
        output_dir: Path,
        license_types: Optional[List[str]] = None,
        pmcid_ranges: Optional[List[str]] = None,
        delay_between_files: int = DEFAULT_DELAY_SECONDS,
        timeout: int = DEFAULT_FTP_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        use_https: bool = True
    ):
        """Initialize bulk importer.

        Args:
            output_dir: Base directory for downloaded files
            license_types: List of license types to download
                ('oa_comm', 'oa_noncomm', 'oa_other')
                Default: ['oa_comm'] (commercial use allowed)
            pmcid_ranges: List of PMCID ranges to download
                (e.g., ['PMC001xxxxxx', 'PMC002xxxxxx'])
                Default: None (download all)
            delay_between_files: Seconds to wait between file downloads
            timeout: FTP/HTTP timeout in seconds
            max_retries: Maximum retry attempts per file
            use_https: Use HTTPS instead of FTP (recommended)
        """
        self.output_dir = Path(output_dir).expanduser()
        self.license_types = [
            LicenseType(lt) for lt in (license_types or ['oa_comm'])
        ]
        self.pmcid_ranges = pmcid_ranges
        self.delay_between_files = delay_between_files
        self.timeout = timeout
        self.max_retries = max_retries
        self.use_https = use_https

        # Create directory structure
        self.packages_dir = self.output_dir / 'packages'
        self.extracted_dir = self.output_dir / 'extracted'
        self.pdf_dir = self.output_dir / 'pdf'
        self.fulltext_dir = self.output_dir / 'fulltext'
        self.state_file = self.output_dir / 'import_state.json'

        for d in [self.packages_dir, self.extracted_dir, self.pdf_dir, self.fulltext_dir]:
            d.mkdir(parents=True, exist_ok=True)

        # NXML parser for full-text extraction
        self.nxml_parser = NXMLParser()

        # Load or initialize state
        self.packages: Dict[str, PackageInfo] = {}
        self.progress = DownloadProgress()
        self._load_state()

    def _load_state(self) -> None:
        """Load download state from file."""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    state = json.load(f)

                self.packages = {
                    k: PackageInfo.from_dict(v)
                    for k, v in state.get('packages', {}).items()
                }
                self.progress = DownloadProgress.from_dict(
                    state.get('progress', {})
                )
                logger.info(
                    f"Loaded state: {self.progress.downloaded_packages}/"
                    f"{self.progress.total_packages} packages downloaded"
                )
            except Exception as e:
                logger.warning(f"Failed to load state: {e}")

    def _save_state(self) -> None:
        """Save download state to file."""
        self.progress.last_update = datetime.now()
        state = {
            'packages': {k: v.to_dict() for k, v in self.packages.items()},
            'progress': self.progress.to_dict()
        }
        with open(self.state_file, 'w') as f:
            json.dump(state, f, indent=2)

    def list_available_packages(
        self,
        refresh: bool = False
    ) -> List[PackageInfo]:
        """List available packages from PMC FTP.

        Args:
            refresh: Force refresh from server

        Returns:
            List of available PackageInfo objects
        """
        if self.packages and not refresh:
            return list(self.packages.values())

        logger.info("Fetching package list from PMC FTP...")

        packages = []

        for license_type in self.license_types:
            # Get baseline packages
            baseline_packages = self._list_packages_for_license(
                license_type, is_baseline=True
            )
            packages.extend(baseline_packages)

            # Get incremental packages
            incr_packages = self._list_packages_for_license(
                license_type, is_baseline=False
            )
            packages.extend(incr_packages)

        # Filter by PMCID range if specified
        if self.pmcid_ranges:
            packages = [
                p for p in packages
                if p.pmcid_range in self.pmcid_ranges
            ]

        # Update state
        self.packages = {p.filename: p for p in packages}
        self.progress.total_packages = len(packages)
        self.progress.total_bytes = sum(p.size_bytes for p in packages)
        self._save_state()

        logger.info(
            f"Found {len(packages)} packages "
            f"({self._format_bytes(self.progress.total_bytes)} total)"
        )

        return packages

    def _list_packages_for_license(
        self,
        license_type: LicenseType,
        is_baseline: bool
    ) -> List[PackageInfo]:
        """List packages for a specific license type.

        Args:
            license_type: License category
            is_baseline: True for baseline, False for incremental

        Returns:
            List of PackageInfo objects
        """
        packages = []
        format_type = PackageFormat.XML  # We want XML for full NXML content

        # Build directory path
        dir_path = f"{PMC_FTP_BASE}/oa_bulk/{license_type.value}/{format_type.value}/"

        try:
            if self.use_https:
                packages = self._list_via_https(
                    dir_path, license_type, format_type, is_baseline
                )
            else:
                packages = self._list_via_ftp(
                    dir_path, license_type, format_type, is_baseline
                )
        except Exception as e:
            logger.error(f"Failed to list packages from {dir_path}: {e}")

        return packages

    def _list_via_https(
        self,
        dir_path: str,
        license_type: LicenseType,
        format_type: PackageFormat,
        is_baseline: bool
    ) -> List[PackageInfo]:
        """List packages via HTTPS directory listing."""
        import requests

        packages = []
        url = f"{PMC_HTTPS_BASE}{dir_path[len(PMC_FTP_BASE):]}"

        try:
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()

            # Parse HTML directory listing
            # Look for patterns like: oa_comm_xml.PMC001xxxxxx.baseline.2024-01-01.tar.gz
            pattern = rf'{license_type.value}_{format_type.value}\.PMC\d{{3}}xxxxxx\.'
            if is_baseline:
                pattern += r'baseline\.\d{4}-\d{2}-\d{2}\.tar\.gz'
            else:
                pattern += r'incr\.\d{4}-\d{2}-\d{2}\.tar\.gz'

            for match in re.finditer(pattern, response.text):
                filename = match.group(0)
                packages.append(self._parse_package_filename(
                    filename, license_type, format_type, url
                ))

        except Exception as e:
            logger.error(f"HTTPS listing failed: {e}")

        return packages

    def _list_via_ftp(
        self,
        dir_path: str,
        license_type: LicenseType,
        format_type: PackageFormat,
        is_baseline: bool
    ) -> List[PackageInfo]:
        """List packages via FTP directory listing."""
        packages = []

        try:
            ftp = ftplib.FTP()
            ftp.connect(PMC_FTP_HOST, timeout=self.timeout)
            ftp.login()

            files = []
            ftp.dir(dir_path, files.append)
            ftp.quit()

            for line in files:
                parts = line.split()
                if len(parts) < 9:
                    continue

                filename = parts[-1]
                size = int(parts[4]) if parts[4].isdigit() else 0

                # Check if it matches our criteria
                if is_baseline and 'baseline' not in filename:
                    continue
                if not is_baseline and 'incr' not in filename:
                    continue
                if not filename.endswith('.tar.gz'):
                    continue

                pkg = self._parse_package_filename(
                    filename, license_type, format_type,
                    f"ftp://{PMC_FTP_HOST}{dir_path}"
                )
                pkg.size_bytes = size
                packages.append(pkg)

        except Exception as e:
            logger.error(f"FTP listing failed: {e}")

        return packages

    def _parse_package_filename(
        self,
        filename: str,
        license_type: LicenseType,
        format_type: PackageFormat,
        base_url: str
    ) -> PackageInfo:
        """Parse package filename to extract metadata."""
        # Pattern: oa_comm_xml.PMC001xxxxxx.baseline.2024-01-01.tar.gz
        parts = filename.replace('.tar.gz', '').split('.')

        pmcid_range = ""
        date = ""
        is_baseline = False

        for part in parts:
            if part.startswith('PMC'):
                pmcid_range = part
            elif re.match(r'\d{4}-\d{2}-\d{2}', part):
                date = part
            elif part == 'baseline':
                is_baseline = True

        return PackageInfo(
            filename=filename,
            license_type=license_type,
            format=format_type,
            pmcid_range=pmcid_range,
            is_baseline=is_baseline,
            date=date,
            url=f"{base_url}{filename}"
        )

    def download_packages(
        self,
        baseline_only: bool = True,
        progress_callback: Optional[Callable[[str, int, int], None]] = None
    ) -> int:
        """Download packages from PMC.

        Args:
            baseline_only: If True, only download baseline packages
            progress_callback: Callback(filename, current, total)

        Returns:
            Number of packages downloaded
        """
        if not self.packages:
            self.list_available_packages()

        packages_to_download = [
            p for p in self.packages.values()
            if not p.downloaded and (not baseline_only or p.is_baseline)
        ]

        if not packages_to_download:
            logger.info("No packages to download")
            return 0

        logger.info(f"Downloading {len(packages_to_download)} packages...")

        if not self.progress.start_time:
            self.progress.start_time = datetime.now()

        downloaded = 0
        for i, pkg in enumerate(packages_to_download):
            if progress_callback:
                progress_callback(pkg.filename, i + 1, len(packages_to_download))

            try:
                success = self._download_package(pkg)
                if success:
                    pkg.downloaded = True
                    self.progress.downloaded_packages += 1
                    self.progress.downloaded_bytes += pkg.size_bytes
                    downloaded += 1
                    self._save_state()
                    logger.info(
                        f"Downloaded {pkg.filename} "
                        f"({self.progress.downloaded_packages}/{self.progress.total_packages})"
                    )
            except Exception as e:
                error_msg = f"Failed to download {pkg.filename}: {e}"
                logger.error(error_msg)
                self.progress.errors.append(error_msg)
                self._save_state()

            # Rate limiting - be polite to NCBI
            if i < len(packages_to_download) - 1:
                logger.info(f"Waiting {self.delay_between_files}s before next download...")
                time.sleep(self.delay_between_files)

        return downloaded

    def _download_package(self, pkg: PackageInfo) -> bool:
        """Download a single package.

        Args:
            pkg: Package to download

        Returns:
            True if successful
        """
        output_path = self.packages_dir / pkg.filename

        # Skip if already exists and has content
        if output_path.exists() and output_path.stat().st_size > 0:
            logger.info(f"Package already exists: {pkg.filename}")
            return True

        if self.use_https:
            return self._download_via_https(pkg.url, output_path)
        else:
            return self._download_via_ftp(pkg.url, output_path)

    def _download_via_https(self, url: str, output_path: Path) -> bool:
        """Download file via HTTPS with progress."""
        import requests

        for attempt in range(self.max_retries):
            try:
                if attempt > 0:
                    logger.info(f"Retry attempt {attempt + 1}/{self.max_retries}")
                    time.sleep(5 * attempt)

                response = requests.get(url, stream=True, timeout=self.timeout)
                response.raise_for_status()

                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0

                with open(output_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)

                            # Log progress every 10MB
                            if downloaded % (10 * 1024 * 1024) == 0:
                                pct = (downloaded / total_size * 100) if total_size else 0
                                logger.debug(
                                    f"  {self._format_bytes(downloaded)} / "
                                    f"{self._format_bytes(total_size)} ({pct:.1f}%)"
                                )

                return True

            except Exception as e:
                logger.warning(f"Download error: {e}")
                if output_path.exists():
                    output_path.unlink()

        return False

    def _download_via_ftp(self, url: str, output_path: Path) -> bool:
        """Download file via FTP."""
        parsed = urlparse(url)
        host = parsed.hostname
        path = parsed.path

        for attempt in range(self.max_retries):
            try:
                if attempt > 0:
                    logger.info(f"Retry attempt {attempt + 1}/{self.max_retries}")
                    time.sleep(5 * attempt)

                ftp = ftplib.FTP()
                ftp.connect(host, timeout=self.timeout)
                ftp.login()

                with open(output_path, 'wb') as f:
                    ftp.retrbinary(f'RETR {path}', f.write)

                ftp.quit()
                return True

            except Exception as e:
                logger.warning(f"FTP download error: {e}")
                if output_path.exists():
                    output_path.unlink()

        return False

    def extract_packages(
        self,
        progress_callback: Optional[Callable[[str, int, int], None]] = None
    ) -> int:
        """Extract downloaded packages.

        Args:
            progress_callback: Callback(filename, current, total)

        Returns:
            Number of packages extracted
        """
        packages_to_extract = [
            p for p in self.packages.values()
            if p.downloaded and not p.extracted
        ]

        if not packages_to_extract:
            logger.info("No packages to extract")
            return 0

        logger.info(f"Extracting {len(packages_to_extract)} packages...")

        extracted = 0
        for i, pkg in enumerate(packages_to_extract):
            if progress_callback:
                progress_callback(pkg.filename, i + 1, len(packages_to_extract))

            try:
                count = self._extract_package(pkg)
                pkg.extracted = True
                extracted += 1
                self._save_state()
                logger.info(
                    f"Extracted {pkg.filename}: {count} articles"
                )
            except Exception as e:
                error_msg = f"Failed to extract {pkg.filename}: {e}"
                logger.error(error_msg)
                self.progress.errors.append(error_msg)
                self._save_state()

        return extracted

    def _extract_package(self, pkg: PackageInfo) -> int:
        """Extract a single package.

        Args:
            pkg: Package to extract

        Returns:
            Number of articles extracted
        """
        package_path = self.packages_dir / pkg.filename
        extract_dir = self.extracted_dir / pkg.filename.replace('.tar.gz', '')

        if extract_dir.exists():
            # Already extracted
            return len(list(extract_dir.glob('**/*.nxml')))

        extract_dir.mkdir(parents=True, exist_ok=True)

        article_count = 0
        with tarfile.open(package_path, 'r:gz') as tar:
            for member in tar.getmembers():
                if member.isfile():
                    # Extract to flat structure with PMCID prefix
                    tar.extract(member, extract_dir)
                    if member.name.endswith('.nxml'):
                        article_count += 1

        return article_count

    def import_to_database(
        self,
        batch_size: int = 100,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> int:
        """Import extracted articles to database.

        Args:
            batch_size: Number of articles per database transaction
            progress_callback: Callback(imported, total)

        Returns:
            Number of articles imported
        """
        from bmlibrarian.database import get_db_manager

        # Find all NXML files in extracted directories
        nxml_files = list(self.extracted_dir.glob('**/*.nxml'))

        if not nxml_files:
            logger.info("No NXML files to import")
            return 0

        logger.info(f"Importing {len(nxml_files)} articles to database...")

        db_manager = get_db_manager()
        imported = 0
        errors = 0

        for i, nxml_path in enumerate(nxml_files):
            try:
                metadata = self._parse_nxml_metadata(nxml_path)
                if metadata:
                    self._upsert_article(db_manager, metadata)
                    imported += 1

                if progress_callback and (i + 1) % batch_size == 0:
                    progress_callback(imported, len(nxml_files))

            except Exception as e:
                errors += 1
                if errors <= 10:  # Only log first 10 errors
                    logger.warning(f"Failed to import {nxml_path.name}: {e}")

        self.progress.imported_articles = imported
        self._save_state()

        logger.info(f"Imported {imported} articles ({errors} errors)")
        return imported

    def _parse_nxml_metadata(self, nxml_path: Path) -> Optional[ArticleMetadata]:
        """Parse article metadata from NXML file.

        Args:
            nxml_path: Path to NXML file

        Returns:
            ArticleMetadata or None if parsing fails
        """
        try:
            content = nxml_path.read_text(encoding='utf-8')
            root = ET.fromstring(content)

            # Get PMCID from filename or article-id
            pmcid = None
            for article_id in root.findall('.//article-id'):
                if article_id.get('pub-id-type') == 'pmc':
                    pmcid = f"PMC{article_id.text}"
                    break

            if not pmcid:
                # Try to get from filename
                match = re.search(r'PMC\d+', nxml_path.name)
                if match:
                    pmcid = match.group(0)

            if not pmcid:
                return None

            # Extract other metadata
            metadata = ArticleMetadata(pmcid=pmcid)

            # PMID
            for article_id in root.findall('.//article-id'):
                if article_id.get('pub-id-type') == 'pmid':
                    metadata.pmid = article_id.text

            # DOI
            for article_id in root.findall('.//article-id'):
                if article_id.get('pub-id-type') == 'doi':
                    metadata.doi = article_id.text

            # Title
            title_elem = root.find('.//article-title')
            if title_elem is not None:
                metadata.title = ''.join(title_elem.itertext()).strip()

            # Abstract
            abstract_elem = root.find('.//abstract')
            if abstract_elem is not None:
                metadata.abstract = ''.join(abstract_elem.itertext()).strip()

            # Authors
            for contrib in root.findall('.//contrib[@contrib-type="author"]'):
                name_elem = contrib.find('.//name')
                if name_elem is not None:
                    surname = name_elem.findtext('surname', '')
                    given = name_elem.findtext('given-names', '')
                    if surname:
                        metadata.authors.append(f"{surname} {given}".strip())

            # Journal
            journal_elem = root.find('.//journal-title')
            if journal_elem is not None:
                metadata.journal = journal_elem.text

            # Publication date
            pub_date = root.find('.//pub-date[@pub-type="epub"]')
            if pub_date is None:
                pub_date = root.find('.//pub-date')
            if pub_date is not None:
                year = pub_date.findtext('year')
                month = pub_date.findtext('month', '01')
                day = pub_date.findtext('day', '01')
                if year:
                    metadata.year = int(year)
                    metadata.publication_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"

            # License
            license_elem = root.find('.//license')
            if license_elem is not None:
                license_link = license_elem.get('{http://www.w3.org/1999/xlink}href')
                if license_link:
                    metadata.license = license_link

            # Full text
            metadata.full_text = self.nxml_parser.parse(content)

            # File paths
            metadata.nxml_filename = str(nxml_path.relative_to(self.output_dir))

            # Check for corresponding PDF
            pdf_name = nxml_path.stem + '.pdf'
            pdf_path = nxml_path.parent / pdf_name
            if pdf_path.exists():
                metadata.pdf_filename = str(pdf_path.relative_to(self.output_dir))

            return metadata

        except Exception as e:
            logger.debug(f"Failed to parse {nxml_path}: {e}")
            return None

    def _upsert_article(
        self,
        db_manager,
        metadata: ArticleMetadata
    ) -> None:
        """Insert or update article in database.

        Args:
            db_manager: Database manager instance
            metadata: Article metadata to insert/update
        """
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                # Check if article exists by PMCID
                cur.execute(
                    "SELECT id FROM document WHERE pmcid = %s",
                    (metadata.pmcid,)
                )
                existing = cur.fetchone()

                if existing:
                    # Update existing record
                    cur.execute("""
                        UPDATE document SET
                            pmid = COALESCE(%s, pmid),
                            doi = COALESCE(%s, doi),
                            title = COALESCE(%s, title),
                            abstract = COALESCE(%s, abstract),
                            authors = COALESCE(%s, authors),
                            journal = COALESCE(%s, journal),
                            publication_date = COALESCE(%s, publication_date),
                            full_text = COALESCE(%s, full_text),
                            pdf_filename = COALESCE(%s, pdf_filename),
                            updated_at = NOW()
                        WHERE pmcid = %s
                    """, (
                        metadata.pmid,
                        metadata.doi,
                        metadata.title,
                        metadata.abstract,
                        metadata.authors if metadata.authors else None,
                        metadata.journal,
                        metadata.publication_date,
                        metadata.full_text,
                        metadata.pdf_filename,
                        metadata.pmcid
                    ))
                else:
                    # Insert new record
                    cur.execute("""
                        INSERT INTO document (
                            pmcid, pmid, doi, title, abstract, authors,
                            journal, publication_date, full_text, pdf_filename,
                            source, created_at, updated_at
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            'pmc_bulk', NOW(), NOW()
                        )
                    """, (
                        metadata.pmcid,
                        metadata.pmid,
                        metadata.doi,
                        metadata.title,
                        metadata.abstract,
                        metadata.authors if metadata.authors else None,
                        metadata.journal,
                        metadata.publication_date,
                        metadata.full_text,
                        metadata.pdf_filename
                    ))

                conn.commit()

    def get_status(self) -> Dict[str, Any]:
        """Get current import status.

        Returns:
            Status dictionary
        """
        return {
            'output_dir': str(self.output_dir),
            'license_types': [lt.value for lt in self.license_types],
            'pmcid_ranges': self.pmcid_ranges,
            'packages': {
                'total': self.progress.total_packages,
                'downloaded': self.progress.downloaded_packages,
                'extracted': sum(1 for p in self.packages.values() if p.extracted),
                'imported': sum(1 for p in self.packages.values() if p.imported)
            },
            'bytes': {
                'total': self.progress.total_bytes,
                'downloaded': self.progress.downloaded_bytes,
                'total_formatted': self._format_bytes(self.progress.total_bytes),
                'downloaded_formatted': self._format_bytes(self.progress.downloaded_bytes)
            },
            'articles': {
                'imported': self.progress.imported_articles
            },
            'errors': len(self.progress.errors),
            'start_time': self.progress.start_time.isoformat() if self.progress.start_time else None,
            'last_update': self.progress.last_update.isoformat() if self.progress.last_update else None
        }

    def _format_bytes(self, size: int) -> str:
        """Format bytes as human-readable string."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"
