"""
MedRxiv MECA Package Importer for BMLibrarian.

Downloads and imports medRxiv MECA packages from AWS S3 for comprehensive
offline access to full-text JATS XML content.

MECA (Manuscript Exchange Common Approach) packages are ZIP archives containing:
- PDF file
- Full-text JATS XML file
- Images and supplementary materials
- manifest.xml with package metadata

S3 Bucket: s3://medrxiv-src-monthly (requester-pays)
Region: us-east-1

Usage:
    from bmlibrarian.importers.medrxiv_meca_importer import MedRxivMECAImporter

    importer = MedRxivMECAImporter(
        output_dir=Path('~/medrxiv_meca'),
        aws_access_key='...',
        aws_secret_key='...'
    )

    # List available packages
    packages = importer.list_packages()

    # Download packages
    importer.download_packages(limit=10)

    # Import to database
    importer.import_to_database()

Note: Requires AWS credentials and incurs requester-pays S3 costs.
Install AWS dependencies with: uv pip install bmlibrarian[aws]
"""

import json
import logging
import time
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable, Iterator

from bmlibrarian.discovery.pmc_package_downloader import NXMLParser

logger = logging.getLogger(__name__)

# S3 bucket details
MEDRXIV_S3_BUCKET = "medrxiv-src-monthly"
MEDRXIV_S3_REGION = "us-east-1"

# Default configuration
DEFAULT_DELAY_SECONDS = 60  # 1 minute between downloads (polite)
DEFAULT_MAX_RETRIES = 3


class PackageStatus(Enum):
    """Status of a MECA package."""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    EXTRACTED = "extracted"
    IMPORTED = "imported"
    ERROR = "error"


@dataclass
class MECAPackageInfo:
    """Information about a MECA package file."""
    key: str  # S3 key
    filename: str
    size_bytes: int = 0
    last_modified: Optional[str] = None
    doi: Optional[str] = None
    status: PackageStatus = PackageStatus.PENDING
    error_message: Optional[str] = None
    local_path: Optional[str] = None
    extracted_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'key': self.key,
            'filename': self.filename,
            'size_bytes': self.size_bytes,
            'last_modified': self.last_modified,
            'doi': self.doi,
            'status': self.status.value,
            'error_message': self.error_message,
            'local_path': self.local_path,
            'extracted_path': self.extracted_path
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MECAPackageInfo':
        """Create from dictionary."""
        return cls(
            key=data['key'],
            filename=data['filename'],
            size_bytes=data.get('size_bytes', 0),
            last_modified=data.get('last_modified'),
            doi=data.get('doi'),
            status=PackageStatus(data.get('status', 'pending')),
            error_message=data.get('error_message'),
            local_path=data.get('local_path'),
            extracted_path=data.get('extracted_path')
        )


@dataclass
class MECAImportProgress:
    """Tracks overall import progress."""
    total_packages: int = 0
    downloaded_packages: int = 0
    extracted_packages: int = 0
    imported_packages: int = 0
    total_bytes: int = 0
    downloaded_bytes: int = 0
    errors: List[str] = field(default_factory=list)
    start_time: Optional[datetime] = None
    last_update: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'total_packages': self.total_packages,
            'downloaded_packages': self.downloaded_packages,
            'extracted_packages': self.extracted_packages,
            'imported_packages': self.imported_packages,
            'total_bytes': self.total_bytes,
            'downloaded_bytes': self.downloaded_bytes,
            'errors': self.errors,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'last_update': self.last_update.isoformat() if self.last_update else None
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MECAImportProgress':
        """Create from dictionary."""
        return cls(
            total_packages=data.get('total_packages', 0),
            downloaded_packages=data.get('downloaded_packages', 0),
            extracted_packages=data.get('extracted_packages', 0),
            imported_packages=data.get('imported_packages', 0),
            total_bytes=data.get('total_bytes', 0),
            downloaded_bytes=data.get('downloaded_bytes', 0),
            errors=data.get('errors', []),
            start_time=datetime.fromisoformat(data['start_time']) if data.get('start_time') else None,
            last_update=datetime.fromisoformat(data['last_update']) if data.get('last_update') else None
        )


@dataclass
class MECAArticle:
    """Article data extracted from a MECA package."""
    doi: str
    pdf_path: Optional[Path] = None
    xml_path: Optional[Path] = None
    full_text: Optional[str] = None
    title: Optional[str] = None
    abstract: Optional[str] = None
    authors: List[str] = field(default_factory=list)
    publication_date: Optional[str] = None


class MedRxivMECAImporter:
    """Bulk importer for medRxiv MECA packages from AWS S3.

    Downloads MECA packages containing PDF and JATS XML full-text,
    extracts articles, and imports them into the database.

    Attributes:
        output_dir: Directory for downloaded and extracted packages
        s3_client: Boto3 S3 client (lazy initialized)
        nxml_parser: Parser for JATS XML content
        packages: List of tracked packages
        progress: Import progress tracker
    """

    def __init__(
        self,
        output_dir: Path,
        aws_access_key: Optional[str] = None,
        aws_secret_key: Optional[str] = None,
        aws_region: str = MEDRXIV_S3_REGION,
        delay_between_downloads: int = DEFAULT_DELAY_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES
    ):
        """Initialize MECA importer.

        Args:
            output_dir: Directory for downloaded packages
            aws_access_key: AWS access key (or use environment/credentials file)
            aws_secret_key: AWS secret key (or use environment/credentials file)
            aws_region: AWS region for S3 bucket
            delay_between_downloads: Seconds to wait between downloads
            max_retries: Maximum retry attempts for failed downloads
        """
        self.output_dir = Path(output_dir).expanduser()
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.aws_access_key = aws_access_key
        self.aws_secret_key = aws_secret_key
        self.aws_region = aws_region
        self.delay_between_downloads = delay_between_downloads
        self.max_retries = max_retries

        # Lazy initialization of S3 client
        self._s3_client = None

        # JATS XML parser
        self.nxml_parser = NXMLParser()

        # State tracking
        self.packages: List[MECAPackageInfo] = []
        self.progress = MECAImportProgress()

        # State file for resumable operations
        self.state_file = self.output_dir / '.meca_import_state.json'

        # Load existing state if available
        self._load_state()

        logger.info(f"MedRxiv MECA importer initialized with output directory: {self.output_dir}")

    @property
    def s3_client(self):
        """Lazy initialization of S3 client."""
        if self._s3_client is None:
            try:
                import boto3
            except ImportError:
                raise ImportError(
                    "boto3 is required for AWS S3 access. "
                    "Install with: uv pip install bmlibrarian[aws]"
                )

            session_kwargs = {}
            if self.aws_access_key and self.aws_secret_key:
                session_kwargs['aws_access_key_id'] = self.aws_access_key
                session_kwargs['aws_secret_access_key'] = self.aws_secret_key

            session = boto3.Session(**session_kwargs)
            self._s3_client = session.client('s3', region_name=self.aws_region)

        return self._s3_client

    def _load_state(self) -> None:
        """Load state from state file if it exists."""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                self.packages = [MECAPackageInfo.from_dict(p) for p in data.get('packages', [])]
                self.progress = MECAImportProgress.from_dict(data.get('progress', {}))
                logger.info(f"Loaded state: {len(self.packages)} packages tracked")
            except Exception as e:
                logger.warning(f"Failed to load state file: {e}")

    def _save_state(self) -> None:
        """Save current state to state file."""
        try:
            data = {
                'packages': [p.to_dict() for p in self.packages],
                'progress': self.progress.to_dict()
            }
            with open(self.state_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save state file: {e}")

    def list_packages(
        self,
        prefix: Optional[str] = None,
        limit: Optional[int] = None,
        refresh: bool = False
    ) -> List[MECAPackageInfo]:
        """List available MECA packages in the S3 bucket.

        Args:
            prefix: S3 key prefix to filter (e.g., 'Current_Content/2024-01/')
            limit: Maximum number of packages to list
            refresh: Force refresh from S3 even if packages already loaded

        Returns:
            List of MECAPackageInfo objects
        """
        if self.packages and not refresh:
            return self.packages[:limit] if limit else self.packages

        logger.info(f"Listing MECA packages from s3://{MEDRXIV_S3_BUCKET}")

        packages = []
        continuation_token = None

        while True:
            list_kwargs = {
                'Bucket': MEDRXIV_S3_BUCKET,
                'RequestPayer': 'requester'
            }
            if prefix:
                list_kwargs['Prefix'] = prefix
            if continuation_token:
                list_kwargs['ContinuationToken'] = continuation_token

            try:
                response = self.s3_client.list_objects_v2(**list_kwargs)
            except Exception as e:
                logger.error(f"Failed to list S3 bucket: {e}")
                raise

            for obj in response.get('Contents', []):
                key = obj['Key']
                # Only include .meca files
                if key.endswith('.meca'):
                    pkg = MECAPackageInfo(
                        key=key,
                        filename=key.split('/')[-1],
                        size_bytes=obj['Size'],
                        last_modified=obj['LastModified'].isoformat() if obj.get('LastModified') else None
                    )
                    packages.append(pkg)

                    if limit and len(packages) >= limit:
                        break

            if limit and len(packages) >= limit:
                break

            if not response.get('IsTruncated'):
                break

            continuation_token = response.get('NextContinuationToken')

        self.packages = packages
        self.progress.total_packages = len(packages)
        self._save_state()

        logger.info(f"Found {len(packages)} MECA packages")
        return packages

    def download_package(self, package: MECAPackageInfo) -> bool:
        """Download a single MECA package.

        Args:
            package: Package to download

        Returns:
            True if download successful, False otherwise
        """
        local_path = self.output_dir / package.filename
        package.local_path = str(local_path)
        package.status = PackageStatus.DOWNLOADING

        for attempt in range(self.max_retries):
            try:
                logger.info(f"Downloading {package.filename} ({package.size_bytes / 1024 / 1024:.1f} MB)")

                self.s3_client.download_file(
                    MEDRXIV_S3_BUCKET,
                    package.key,
                    str(local_path),
                    ExtraArgs={'RequestPayer': 'requester'}
                )

                package.status = PackageStatus.DOWNLOADED
                self.progress.downloaded_packages += 1
                self.progress.downloaded_bytes += package.size_bytes
                self._save_state()

                logger.info(f"Downloaded {package.filename}")
                return True

            except Exception as e:
                logger.warning(f"Download attempt {attempt + 1} failed for {package.filename}: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff

        package.status = PackageStatus.ERROR
        package.error_message = f"Download failed after {self.max_retries} attempts"
        self.progress.errors.append(f"Download failed: {package.filename}")
        self._save_state()
        return False

    def download_packages(
        self,
        limit: Optional[int] = None,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> int:
        """Download MECA packages.

        Args:
            limit: Maximum number of packages to download
            progress_callback: Optional callback for progress updates

        Returns:
            Number of packages successfully downloaded
        """
        if not self.packages:
            self.list_packages(limit=limit)

        packages_to_download = [
            p for p in self.packages
            if p.status in (PackageStatus.PENDING, PackageStatus.ERROR)
        ][:limit] if limit else [
            p for p in self.packages
            if p.status in (PackageStatus.PENDING, PackageStatus.ERROR)
        ]

        if not packages_to_download:
            logger.info("No packages to download")
            return 0

        self.progress.start_time = datetime.now()
        downloaded = 0

        for i, package in enumerate(packages_to_download):
            if progress_callback:
                progress_callback(f"Downloading {i + 1}/{len(packages_to_download)}: {package.filename}")

            if self.download_package(package):
                downloaded += 1

            # Polite delay between downloads
            if i < len(packages_to_download) - 1:
                time.sleep(self.delay_between_downloads)

        self.progress.last_update = datetime.now()
        self._save_state()

        logger.info(f"Downloaded {downloaded}/{len(packages_to_download)} packages")
        return downloaded

    def extract_package(self, package: MECAPackageInfo) -> Optional[MECAArticle]:
        """Extract a MECA package and parse its contents.

        Args:
            package: Package to extract

        Returns:
            MECAArticle with extracted data, or None if extraction failed
        """
        if not package.local_path or not Path(package.local_path).exists():
            logger.error(f"Package file not found: {package.local_path}")
            return None

        extract_dir = self.output_dir / 'extracted' / package.filename.replace('.meca', '')
        extract_dir.mkdir(parents=True, exist_ok=True)
        package.extracted_path = str(extract_dir)

        try:
            # MECA files are ZIP archives
            with zipfile.ZipFile(package.local_path, 'r') as zf:
                zf.extractall(extract_dir)

            # Find PDF and XML files in content/ directory
            content_dir = extract_dir / 'content'
            if not content_dir.exists():
                content_dir = extract_dir  # Some packages may not have content/ subdirectory

            pdf_path = None
            xml_path = None

            for file in content_dir.iterdir():
                if file.suffix.lower() == '.pdf':
                    pdf_path = file
                elif file.suffix.lower() == '.xml' and 'manifest' not in file.name.lower():
                    xml_path = file

            # Parse JATS XML for full text and metadata
            full_text = None
            title = None
            abstract = None
            authors: List[str] = []
            doi = None

            if xml_path and xml_path.exists():
                try:
                    with open(xml_path, 'r', encoding='utf-8') as f:
                        xml_content = f.read()

                    # Extract full text using NXMLParser
                    full_text = self.nxml_parser.parse(xml_content)

                    # Parse additional metadata from XML
                    root = ET.fromstring(xml_content)

                    # Extract DOI
                    doi_elem = root.find('.//article-id[@pub-id-type="doi"]')
                    if doi_elem is not None and doi_elem.text:
                        doi = doi_elem.text

                    # Extract title
                    title_elem = root.find('.//article-title')
                    if title_elem is not None:
                        title = ''.join(title_elem.itertext()).strip()

                    # Extract abstract
                    abstract_elem = root.find('.//abstract')
                    if abstract_elem is not None:
                        abstract = ''.join(abstract_elem.itertext()).strip()

                except Exception as e:
                    logger.warning(f"Failed to parse XML for {package.filename}: {e}")

            package.status = PackageStatus.EXTRACTED
            package.doi = doi
            self.progress.extracted_packages += 1
            self._save_state()

            return MECAArticle(
                doi=doi or package.filename.replace('.meca', ''),
                pdf_path=pdf_path,
                xml_path=xml_path,
                full_text=full_text,
                title=title,
                abstract=abstract,
                authors=authors
            )

        except Exception as e:
            logger.error(f"Failed to extract {package.filename}: {e}")
            package.status = PackageStatus.ERROR
            package.error_message = str(e)
            self.progress.errors.append(f"Extraction failed: {package.filename}")
            self._save_state()
            return None

    def import_to_database(
        self,
        limit: Optional[int] = None,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> int:
        """Import extracted packages to the database.

        Args:
            limit: Maximum number of packages to import
            progress_callback: Optional callback for progress updates

        Returns:
            Number of articles successfully imported
        """
        from bmlibrarian.database import get_db_manager
        from bmlibrarian.importers.medrxiv_importer import MedRxivImporter

        # Get source_id for medRxiv
        temp_importer = MedRxivImporter()
        source_id = temp_importer.source_id
        db_manager = get_db_manager()

        packages_to_import = [
            p for p in self.packages
            if p.status == PackageStatus.DOWNLOADED
        ][:limit] if limit else [
            p for p in self.packages
            if p.status == PackageStatus.DOWNLOADED
        ]

        if not packages_to_import:
            logger.info("No packages to import")
            return 0

        imported = 0

        for i, package in enumerate(packages_to_import):
            if progress_callback:
                progress_callback(f"Importing {i + 1}/{len(packages_to_import)}: {package.filename}")

            article = self.extract_package(package)
            if not article or not article.doi:
                continue

            try:
                with db_manager.get_connection() as conn:
                    with conn.cursor() as cur:
                        # Check if already exists
                        cur.execute(
                            "SELECT id FROM document WHERE source_id = %s AND doi = %s",
                            (source_id, article.doi)
                        )
                        existing = cur.fetchone()

                        if existing:
                            # Update with MECA full text
                            if article.full_text:
                                cur.execute("""
                                    UPDATE document
                                    SET full_text = %s, updated_date = CURRENT_TIMESTAMP
                                    WHERE source_id = %s AND doi = %s
                                """, (article.full_text, source_id, article.doi))
                                logger.debug(f"Updated full text for {article.doi}")
                        else:
                            # Insert new record
                            cur.execute("""
                                INSERT INTO document (
                                    source_id, external_id, doi, title, abstract,
                                    authors, publication, full_text
                                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            """, (
                                source_id,
                                article.doi,
                                article.doi,
                                article.title,
                                article.abstract,
                                article.authors,
                                'medRxiv',
                                article.full_text
                            ))
                            logger.debug(f"Inserted new document for {article.doi}")

                package.status = PackageStatus.IMPORTED
                self.progress.imported_packages += 1
                imported += 1

            except Exception as e:
                logger.error(f"Failed to import {article.doi}: {e}")
                package.status = PackageStatus.ERROR
                package.error_message = str(e)
                self.progress.errors.append(f"Import failed: {article.doi}")

        self.progress.last_update = datetime.now()
        self._save_state()

        logger.info(f"Imported {imported}/{len(packages_to_import)} articles")
        return imported

    def get_status(self) -> Dict[str, Any]:
        """Get current import status.

        Returns:
            Dictionary with status information
        """
        status_counts = {status.value: 0 for status in PackageStatus}
        for package in self.packages:
            status_counts[package.status.value] += 1

        return {
            'total_packages': len(self.packages),
            'status_counts': status_counts,
            'progress': self.progress.to_dict(),
            'output_dir': str(self.output_dir),
            'state_file': str(self.state_file)
        }

    def cleanup_extracted(self, keep_imported: bool = True) -> int:
        """Clean up extracted package directories.

        Args:
            keep_imported: If True, don't delete successfully imported packages

        Returns:
            Number of directories cleaned up
        """
        import shutil

        cleaned = 0
        for package in self.packages:
            if not package.extracted_path:
                continue

            if keep_imported and package.status == PackageStatus.IMPORTED:
                continue

            extracted_path = Path(package.extracted_path)
            if extracted_path.exists():
                try:
                    shutil.rmtree(extracted_path)
                    cleaned += 1
                    logger.debug(f"Cleaned up {extracted_path}")
                except Exception as e:
                    logger.warning(f"Failed to clean up {extracted_path}: {e}")

        return cleaned
