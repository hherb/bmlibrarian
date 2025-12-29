"""Europe PMC Open Access PDF bulk downloader.

Downloads PDF files from Europe PMC Open Access FTP for offline access
to biomedical literature.

Europe PMC provides bulk PDF downloads organized in packages similar to
the XML downloads. PDFs are grouped by PMCID ranges in tar.gz archives.

Features:
- Resumable downloads with state persistence
- Download verification (gzip and PDF integrity check)
- Configurable rate limiting (polite to servers)
- PMCID range filtering for selective downloads
- Progress tracking with real-time updates
- PDF extraction from tar.gz packages
- Year-based local storage organization

Usage:
    from bmlibrarian.importers.europe_pmc_pdf_downloader import EuropePMCPDFDownloader
    from pathlib import Path

    downloader = EuropePMCPDFDownloader(
        output_dir=Path('~/europepmc_pdf'),
        delay_between_files=60  # 1 minute between downloads
    )

    # List available packages
    packages = downloader.list_available_packages()

    # Download all packages
    downloader.download_packages()

    # Check status
    status = downloader.get_status()
"""

import io
import json
import logging
import random
import re
import tarfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

# Europe PMC FTP server details for PDFs
# The PDF packages are served alongside XML packages
EUROPE_PMC_PDF_BASE_URL = "https://europepmc.org/ftp/oa/"

# Default configuration
DEFAULT_DELAY_SECONDS = 60  # 1 minute between files (polite)
DEFAULT_TIMEOUT = 600  # 10 minutes for large PDF packages
DEFAULT_MAX_RETRIES = 3
DEFAULT_CHUNK_SIZE = 8192  # 8KB chunks for streaming
DEFAULT_RETRY_BASE_DELAY = 5  # Base delay for retries in seconds
DEFAULT_JITTER_FACTOR = 0.25  # 25% jitter on retry delays
PROGRESS_LOG_INTERVAL_BYTES = 50 * 1024 * 1024  # Log progress every 50MB
MAX_ERRORS_TO_KEEP = 100  # Maximum number of errors to keep in state


@dataclass
class PDFPackageInfo:
    """Information about a Europe PMC OA PDF package file."""

    filename: str  # e.g., "PMC13900_PMC17829.pdf.tar.gz" or similar
    pmcid_start: int  # e.g., 13900
    pmcid_end: int  # e.g., 17829
    size_bytes: int = 0
    url: str = ""
    downloaded: bool = False
    verified: bool = False
    extracted: bool = False
    download_date: Optional[str] = None
    pdf_count: int = 0  # Number of PDFs extracted

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'filename': self.filename,
            'pmcid_start': self.pmcid_start,
            'pmcid_end': self.pmcid_end,
            'size_bytes': self.size_bytes,
            'url': self.url,
            'downloaded': self.downloaded,
            'verified': self.verified,
            'extracted': self.extracted,
            'download_date': self.download_date,
            'pdf_count': self.pdf_count
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PDFPackageInfo':
        """Create from dictionary."""
        return cls(
            filename=data['filename'],
            pmcid_start=data['pmcid_start'],
            pmcid_end=data['pmcid_end'],
            size_bytes=data.get('size_bytes', 0),
            url=data.get('url', ''),
            downloaded=data.get('downloaded', False),
            verified=data.get('verified', False),
            extracted=data.get('extracted', False),
            download_date=data.get('download_date'),
            pdf_count=data.get('pdf_count', 0)
        )


@dataclass
class PDFDownloadProgress:
    """Tracks overall PDF download progress."""

    total_packages: int = 0
    downloaded_packages: int = 0
    verified_packages: int = 0
    extracted_packages: int = 0
    total_pdfs: int = 0
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
            'verified_packages': self.verified_packages,
            'extracted_packages': self.extracted_packages,
            'total_pdfs': self.total_pdfs,
            'total_bytes': self.total_bytes,
            'downloaded_bytes': self.downloaded_bytes,
            'errors': self.errors[-MAX_ERRORS_TO_KEEP:],
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'last_update': self.last_update.isoformat() if self.last_update else None
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PDFDownloadProgress':
        """Create from dictionary."""
        return cls(
            total_packages=data.get('total_packages', 0),
            downloaded_packages=data.get('downloaded_packages', 0),
            verified_packages=data.get('verified_packages', 0),
            extracted_packages=data.get('extracted_packages', 0),
            total_pdfs=data.get('total_pdfs', 0),
            total_bytes=data.get('total_bytes', 0),
            downloaded_bytes=data.get('downloaded_bytes', 0),
            errors=data.get('errors', []),
            start_time=datetime.fromisoformat(data['start_time']) if data.get('start_time') else None,
            last_update=datetime.fromisoformat(data['last_update']) if data.get('last_update') else None
        )


class EuropePMCPDFDownloader:
    """Bulk downloader for Europe PMC Open Access PDF packages.

    Downloads tar.gz packages containing PDF files from Europe PMC's
    Open Access FTP. Extracts PDFs to year-based local directories.
    """

    def __init__(
        self,
        output_dir: Path,
        pmcid_ranges: Optional[List[Tuple[int, int]]] = None,
        delay_between_files: int = DEFAULT_DELAY_SECONDS,
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        extract_pdfs: bool = True,
        pdf_output_dir: Optional[Path] = None
    ):
        """Initialize PDF bulk downloader.

        Args:
            output_dir: Base directory for downloaded package files
            pmcid_ranges: List of (start, end) PMCID ranges to download.
                Default: None (download all)
            delay_between_files: Seconds to wait between file downloads
            timeout: HTTP timeout in seconds
            max_retries: Maximum retry attempts per file
            extract_pdfs: If True, extract PDFs from packages after download
            pdf_output_dir: Directory for extracted PDFs. Defaults to output_dir/pdf
        """
        self.output_dir = Path(output_dir).expanduser()
        self.pmcid_ranges = pmcid_ranges
        self.delay_between_files = delay_between_files
        self.timeout = timeout
        self.max_retries = max_retries
        self.extract_pdfs = extract_pdfs

        # Create directory structure
        self.packages_dir = self.output_dir / 'packages'
        self.pdf_dir = pdf_output_dir or (self.output_dir / 'pdf')
        self.state_file = self.output_dir / 'pdf_download_state.json'

        self.packages_dir.mkdir(parents=True, exist_ok=True)
        self.pdf_dir.mkdir(parents=True, exist_ok=True)

        # Load or initialize state
        self.packages: Dict[str, PDFPackageInfo] = {}
        self.progress = PDFDownloadProgress()
        self._load_state()

        # Session for HTTP requests
        self._session = requests.Session()
        self._session.headers.update({
            'User-Agent': 'BMLibrarian/1.0 (PDF Bulk Downloader; mailto:contact@example.com)'
        })

    def _load_state(self) -> None:
        """Load download state from file."""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    state = json.load(f)

                self.packages = {
                    k: PDFPackageInfo.from_dict(v)
                    for k, v in state.get('packages', {}).items()
                }
                self.progress = PDFDownloadProgress.from_dict(
                    state.get('progress', {})
                )
                logger.info(
                    f"Loaded PDF state: {self.progress.downloaded_packages}/"
                    f"{self.progress.total_packages} packages downloaded, "
                    f"{self.progress.total_pdfs} PDFs extracted"
                )
            except Exception as e:
                logger.warning(f"Failed to load PDF state: {e}")

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
    ) -> List[PDFPackageInfo]:
        """List available PDF packages from Europe PMC FTP.

        Europe PMC PDF packages follow patterns like:
        - PMC#_PMC#.pdf.tar.gz (bundled PDFs by PMCID range)
        - Individual article tar.gz with PDFs inside

        Args:
            refresh: Force refresh from server

        Returns:
            List of available PDFPackageInfo objects
        """
        if self.packages and not refresh:
            return list(self.packages.values())

        logger.info("Fetching PDF package list from Europe PMC FTP...")

        packages = []

        try:
            response = self._session.get(
                EUROPE_PMC_PDF_BASE_URL,
                timeout=self.timeout
            )
            response.raise_for_status()

            # Parse HTML directory listing for PDF packages
            # Look for patterns like:
            # - PMC#_PMC#.pdf.tar.gz (PDF bundle format)
            # - PMC#_PMC#.tar.gz that contain PDFs
            # The actual pattern depends on Europe PMC's current offering

            # Pattern 1: Explicit PDF tar.gz packages
            pdf_pattern = r'href="(PMC(\d+)_PMC(\d+)\.pdf\.tar\.gz)"'
            for match in re.finditer(pdf_pattern, response.text):
                filename = match.group(1)
                pmcid_start = int(match.group(2))
                pmcid_end = int(match.group(3))

                if self._in_pmcid_range(pmcid_start, pmcid_end):
                    pkg = self._create_package_info(
                        filename, pmcid_start, pmcid_end
                    )
                    packages.append(pkg)

            # Pattern 2: Generic tar.gz packages (may contain PDFs)
            # These are the same packages as XML but contain PDFs
            tar_pattern = r'href="(PMC(\d+)_PMC(\d+)\.tar\.gz)"'
            for match in re.finditer(tar_pattern, response.text):
                filename = match.group(1)
                pmcid_start = int(match.group(2))
                pmcid_end = int(match.group(3))

                # Skip if already added as PDF package
                if filename.replace('.tar.gz', '.pdf.tar.gz') in [p.filename for p in packages]:
                    continue

                if self._in_pmcid_range(pmcid_start, pmcid_end):
                    pkg = self._create_package_info(
                        filename, pmcid_start, pmcid_end
                    )
                    packages.append(pkg)

            # Sort by PMCID start
            packages.sort(key=lambda p: p.pmcid_start)

            if not packages:
                logger.warning(
                    "No PDF packages found. Europe PMC may have a different PDF structure. "
                    "Please check https://europepmc.org/downloads for current availability."
                )

        except Exception as e:
            logger.error(f"Failed to list PDF packages: {e}")
            raise

        # Update state
        self.packages = {p.filename: p for p in packages}
        self.progress.total_packages = len(packages)
        self._save_state()

        logger.info(f"Found {len(packages)} PDF packages")

        return packages

    def _in_pmcid_range(self, start: int, end: int) -> bool:
        """Check if package overlaps with configured PMCID ranges."""
        if not self.pmcid_ranges:
            return True

        return any(
            (start >= r[0] and end <= r[1]) or
            (start <= r[1] and end >= r[0])
            for r in self.pmcid_ranges
        )

    def _create_package_info(
        self,
        filename: str,
        pmcid_start: int,
        pmcid_end: int
    ) -> PDFPackageInfo:
        """Create PDFPackageInfo, preserving existing state if available."""
        pkg = PDFPackageInfo(
            filename=filename,
            pmcid_start=pmcid_start,
            pmcid_end=pmcid_end,
            url=f"{EUROPE_PMC_PDF_BASE_URL}{filename}"
        )

        # Preserve existing download status
        if filename in self.packages:
            existing = self.packages[filename]
            pkg.downloaded = existing.downloaded
            pkg.verified = existing.verified
            pkg.extracted = existing.extracted
            pkg.download_date = existing.download_date
            pkg.size_bytes = existing.size_bytes
            pkg.pdf_count = existing.pdf_count

        return pkg

    def download_packages(
        self,
        limit: Optional[int] = None,
        progress_callback: Optional[Callable[[str, int, int], None]] = None
    ) -> int:
        """Download PDF packages from Europe PMC.

        Args:
            limit: Maximum number of packages to download (None for all)
            progress_callback: Callback(filename, current, total)

        Returns:
            Number of packages successfully downloaded and verified
        """
        if not self.packages:
            self.list_available_packages()

        packages_to_download = [
            p for p in self.packages.values()
            if not p.downloaded or not p.verified
        ]

        if limit:
            packages_to_download = packages_to_download[:limit]

        if not packages_to_download:
            logger.info("No PDF packages to download")
            return 0

        logger.info(f"Downloading {len(packages_to_download)} PDF packages...")

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
                    pkg.download_date = datetime.now().isoformat()
                    self.progress.downloaded_packages = sum(
                        1 for p in self.packages.values() if p.downloaded
                    )
                    self.progress.downloaded_bytes = sum(
                        p.size_bytes for p in self.packages.values() if p.downloaded
                    )

                    # Verify the download
                    package_path = self.packages_dir / pkg.filename
                    if self._verify_archive(package_path):
                        pkg.verified = True
                        self.progress.verified_packages = sum(
                            1 for p in self.packages.values() if p.verified
                        )

                        # Extract PDFs if configured
                        if self.extract_pdfs:
                            pdf_count = self._extract_pdfs_from_package(pkg)
                            if pdf_count > 0:
                                pkg.extracted = True
                                pkg.pdf_count = pdf_count
                                self.progress.total_pdfs += pdf_count
                                self.progress.extracted_packages = sum(
                                    1 for p in self.packages.values() if p.extracted
                                )

                        downloaded += 1
                        logger.info(
                            f"Downloaded and verified {pkg.filename} "
                            f"({self.progress.downloaded_packages}/{self.progress.total_packages})"
                        )
                    else:
                        logger.warning(f"Verification failed for {pkg.filename}, will retry")
                        pkg.downloaded = False
                        # Delete corrupted file
                        corrupted_path = self.packages_dir / pkg.filename
                        if corrupted_path.exists():
                            corrupted_path.unlink()

                    self._save_state()

            except Exception as e:
                error_msg = f"Failed to download {pkg.filename}: {e}"
                logger.error(error_msg)
                self.progress.errors.append(error_msg)
                self._save_state()

            # Rate limiting - be polite to Europe PMC
            if i < len(packages_to_download) - 1:
                logger.info(f"Waiting {self.delay_between_files}s before next download...")
                time.sleep(self.delay_between_files)

        return downloaded

    def _download_package(self, pkg: PDFPackageInfo) -> bool:
        """Download a single package.

        Args:
            pkg: Package to download

        Returns:
            True if download successful
        """
        output_path = self.packages_dir / pkg.filename

        # Skip if already exists and verified
        if output_path.exists() and output_path.stat().st_size > 0:
            if pkg.verified or self._verify_archive(output_path):
                logger.info(f"Package already exists and verified: {pkg.filename}")
                pkg.downloaded = True
                pkg.verified = True
                return True

        return self._download_via_https(pkg.url, output_path, pkg)

    def _download_via_https(
        self,
        url: str,
        output_path: Path,
        pkg: PDFPackageInfo
    ) -> bool:
        """Download file via HTTPS with progress and retry.

        Args:
            url: URL to download from
            output_path: Path to save file
            pkg: Package info to update with size

        Returns:
            True if download successful
        """
        for attempt in range(self.max_retries):
            try:
                if attempt > 0:
                    logger.info(f"Retry attempt {attempt + 1}/{self.max_retries}")
                    # Linear backoff with jitter to prevent thundering herd
                    base_delay = DEFAULT_RETRY_BASE_DELAY * attempt
                    jitter = base_delay * DEFAULT_JITTER_FACTOR * random.random()
                    time.sleep(base_delay + jitter)

                response = self._session.get(
                    url,
                    stream=True,
                    timeout=self.timeout
                )
                response.raise_for_status()

                total_size = int(response.headers.get('content-length', 0))
                pkg.size_bytes = total_size
                downloaded = 0

                with open(output_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=DEFAULT_CHUNK_SIZE):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)

                            # Log progress periodically
                            if total_size > 0 and downloaded % PROGRESS_LOG_INTERVAL_BYTES < DEFAULT_CHUNK_SIZE:
                                pct = (downloaded / total_size * 100)
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

    def _verify_archive(self, file_path: Path) -> bool:
        """Verify tar.gz file integrity.

        Args:
            file_path: Path to archive file

        Returns:
            True if file is valid tar.gz
        """
        try:
            with tarfile.open(file_path, 'r:gz') as tar:
                # Just try to list members to verify integrity
                members = tar.getmembers()
                return len(members) > 0
        except Exception as e:
            logger.warning(f"Archive verification error for {file_path.name}: {e}")
            return False

    def _extract_pdfs_from_package(self, pkg: PDFPackageInfo) -> int:
        """Extract PDF files from a downloaded package.

        PDFs are extracted to year-based subdirectories for organization.
        Files are named by their PMCID: PMC{id}.pdf

        Args:
            pkg: Package to extract PDFs from

        Returns:
            Number of PDFs successfully extracted
        """
        package_path = self.packages_dir / pkg.filename
        if not package_path.exists():
            return 0

        pdf_count = 0

        try:
            with tarfile.open(package_path, 'r:gz') as tar:
                for member in tar.getmembers():
                    if not member.isfile():
                        continue

                    name_lower = member.name.lower()
                    if not name_lower.endswith('.pdf'):
                        continue

                    # Extract PMCID from filename
                    pmcid_match = re.search(r'PMC(\d+)', member.name, re.IGNORECASE)
                    if not pmcid_match:
                        continue

                    pmcid = f"PMC{pmcid_match.group(1)}"

                    # Determine output path with year-based organization
                    # For now, use a simple PMCID-based structure
                    # Could be enhanced to use publication year from database
                    pdf_subdir = self.pdf_dir / self._get_pmcid_subdir(int(pmcid_match.group(1)))
                    pdf_subdir.mkdir(parents=True, exist_ok=True)
                    pdf_path = pdf_subdir / f"{pmcid}.pdf"

                    # Skip if already exists
                    if pdf_path.exists():
                        pdf_count += 1
                        continue

                    # Extract PDF
                    try:
                        pdf_file = tar.extractfile(member)
                        if pdf_file:
                            pdf_content = pdf_file.read()

                            # Verify it's a valid PDF
                            if pdf_content[:4] == b'%PDF':
                                pdf_path.write_bytes(pdf_content)
                                pdf_count += 1
                                logger.debug(f"Extracted {pmcid}.pdf ({len(pdf_content)} bytes)")
                            else:
                                logger.debug(f"Skipping invalid PDF: {member.name}")
                    except Exception as e:
                        logger.debug(f"Failed to extract {member.name}: {e}")

        except Exception as e:
            logger.warning(f"Error extracting PDFs from {pkg.filename}: {e}")

        if pdf_count > 0:
            logger.info(f"Extracted {pdf_count} PDFs from {pkg.filename}")

        return pdf_count

    def _get_pmcid_subdir(self, pmcid: int) -> str:
        """Get subdirectory name for a PMCID.

        Uses a two-level directory structure based on PMCID ranges
        to avoid too many files in a single directory.

        Args:
            pmcid: Numeric PMCID (without 'PMC' prefix)

        Returns:
            Subdirectory path like "1000/1000-1099"
        """
        # Group by 1000s, then by 100s
        thousands = (pmcid // 1000) * 1000
        hundreds = (pmcid // 100) * 100
        return f"{thousands}/{hundreds}-{hundreds + 99}"

    def verify_all_downloads(self) -> Dict[str, Any]:
        """Verify integrity of all downloaded packages.

        Returns:
            Dictionary with verification results
        """
        logger.info("Verifying all downloaded PDF packages...")

        results = {
            'verified': 0,
            'failed': 0,
            'missing': 0,
            'failed_files': []
        }

        for pkg in self.packages.values():
            file_path = self.packages_dir / pkg.filename

            if not pkg.downloaded or not file_path.exists():
                results['missing'] += 1
                continue

            if self._verify_archive(file_path):
                pkg.verified = True
                results['verified'] += 1
            else:
                pkg.verified = False
                results['failed'] += 1
                results['failed_files'].append(pkg.filename)
                logger.warning(f"Verification failed: {pkg.filename}")

        self.progress.verified_packages = results['verified']
        self._save_state()

        logger.info(
            f"Verification complete: {results['verified']} verified, "
            f"{results['failed']} failed, {results['missing']} missing"
        )

        return results

    def extract_all_pdfs(
        self,
        limit: Optional[int] = None,
        progress_callback: Optional[Callable[[str, int, int], None]] = None
    ) -> Dict[str, Any]:
        """Extract PDFs from all downloaded and verified packages.

        Args:
            limit: Maximum number of packages to process
            progress_callback: Callback(filename, current, total)

        Returns:
            Extraction statistics
        """
        packages_to_extract = [
            p for p in self.packages.values()
            if p.verified and not p.extracted
        ]

        if limit:
            packages_to_extract = packages_to_extract[:limit]

        if not packages_to_extract:
            logger.info("No packages to extract")
            return {'extracted': 0, 'total_pdfs': 0}

        logger.info(f"Extracting PDFs from {len(packages_to_extract)} packages...")

        total_pdfs = 0
        extracted = 0

        for i, pkg in enumerate(packages_to_extract):
            if progress_callback:
                progress_callback(pkg.filename, i + 1, len(packages_to_extract))

            pdf_count = self._extract_pdfs_from_package(pkg)
            if pdf_count > 0:
                pkg.extracted = True
                pkg.pdf_count = pdf_count
                total_pdfs += pdf_count
                extracted += 1
                self._save_state()

        self.progress.total_pdfs = sum(p.pdf_count for p in self.packages.values())
        self.progress.extracted_packages = sum(
            1 for p in self.packages.values() if p.extracted
        )
        self._save_state()

        logger.info(
            f"Extraction complete: {extracted} packages, {total_pdfs} PDFs"
        )

        return {
            'extracted': extracted,
            'total_pdfs': total_pdfs
        }

    def get_status(self) -> Dict[str, Any]:
        """Get current download status.

        Returns:
            Status dictionary
        """
        return {
            'output_dir': str(self.output_dir),
            'pdf_dir': str(self.pdf_dir),
            'packages': {
                'total': self.progress.total_packages,
                'downloaded': self.progress.downloaded_packages,
                'verified': self.progress.verified_packages,
                'extracted': self.progress.extracted_packages,
                'pending': self.progress.total_packages - self.progress.downloaded_packages
            },
            'pdfs': {
                'total': self.progress.total_pdfs
            },
            'bytes': {
                'total': self.progress.total_bytes,
                'downloaded': self.progress.downloaded_bytes,
                'total_formatted': self._format_bytes(self.progress.total_bytes),
                'downloaded_formatted': self._format_bytes(self.progress.downloaded_bytes)
            },
            'errors': len(self.progress.errors),
            'recent_errors': self.progress.errors[-5:] if self.progress.errors else [],
            'start_time': self.progress.start_time.isoformat() if self.progress.start_time else None,
            'last_update': self.progress.last_update.isoformat() if self.progress.last_update else None
        }

    def estimate_download_time(self) -> Dict[str, Any]:
        """Estimate remaining download time based on current progress.

        Returns:
            Estimation dictionary
        """
        if not self.progress.start_time or self.progress.downloaded_packages == 0:
            return {
                'estimated': False,
                'message': 'Not enough data to estimate'
            }

        elapsed = (datetime.now() - self.progress.start_time).total_seconds()
        packages_per_second = self.progress.downloaded_packages / elapsed
        remaining_packages = self.progress.total_packages - self.progress.downloaded_packages

        if packages_per_second > 0:
            remaining_seconds = remaining_packages / packages_per_second
            remaining_hours = remaining_seconds / 3600

            return {
                'estimated': True,
                'remaining_packages': remaining_packages,
                'packages_per_hour': packages_per_second * 3600,
                'remaining_hours': remaining_hours,
                'remaining_formatted': self._format_duration(remaining_seconds),
                'elapsed_formatted': self._format_duration(elapsed)
            }

        return {
            'estimated': False,
            'message': 'Download rate too slow to estimate'
        }

    def get_pdf_path(self, pmcid: str) -> Optional[Path]:
        """Get the local path for a PDF by PMCID.

        Args:
            pmcid: PMCID (with or without 'PMC' prefix)

        Returns:
            Path to PDF file if it exists, None otherwise

        Raises:
            ValueError: If PMCID is invalid (not numeric after removing PMC prefix)
        """
        if not pmcid or not isinstance(pmcid, str):
            raise ValueError(f"Invalid PMCID: {pmcid!r} - must be a non-empty string")

        # Normalize PMCID
        pmcid_clean = pmcid.strip().upper()
        if pmcid_clean.startswith('PMC'):
            pmcid_str = pmcid_clean[3:]
        else:
            pmcid_str = pmcid_clean

        # Validate numeric portion
        if not pmcid_str.isdigit():
            raise ValueError(
                f"Invalid PMCID: {pmcid!r} - must be numeric (with optional PMC prefix)"
            )

        pmcid_num = int(pmcid_str)
        subdir = self._get_pmcid_subdir(pmcid_num)
        pdf_path = self.pdf_dir / subdir / f"PMC{pmcid_num}.pdf"

        return pdf_path if pdf_path.exists() else None

    def _format_bytes(self, size: int) -> str:
        """Format bytes as human-readable string."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"

    def _format_duration(self, seconds: float) -> str:
        """Format duration as human-readable string."""
        if seconds < 60:
            return f"{seconds:.0f} seconds"
        elif seconds < 3600:
            minutes = seconds / 60
            return f"{minutes:.1f} minutes"
        elif seconds < 86400:
            hours = seconds / 3600
            return f"{hours:.1f} hours"
        else:
            days = seconds / 86400
            return f"{days:.1f} days"
