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

import json
import logging
import random
import re
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

# Europe PMC FTP server details for PDFs
# PDFs are served from a separate /pdf/ directory with a two-level structure:
# - Top level: PMCxxxx000/, PMCxxxx001/, etc. directories
# - Inside each: PMC#######.zip files containing individual PDFs
EUROPE_PMC_PDF_BASE_URL = "https://europepmc.org/ftp/pdf/"

# Default configuration constants
# Timing and rate limiting
DEFAULT_DELAY_SECONDS = 60  # 1 minute between files (polite to servers)
DEFAULT_TIMEOUT = 600  # 10 minutes for large PDF packages
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_BASE_DELAY = 5  # Base delay for retries in seconds
DEFAULT_JITTER_FACTOR = 0.25  # 25% jitter on retry delays

# Download configuration
DEFAULT_CHUNK_SIZE = 8192  # 8KB chunks for streaming
PROGRESS_LOG_INTERVAL_BYTES = 50 * 1024 * 1024  # Log progress every 50MB
MAX_ERRORS_TO_KEEP = 100  # Maximum number of errors to keep in state

# PMCID validation bounds
MIN_PMCID = 1
MAX_PMCID = 99_999_999  # Upper bound for reasonable PMCID values

# Regex timeout protection (max matches to prevent ReDoS)
MAX_REGEX_MATCHES = 10000

# User-Agent identifier (base without closing paren - allows adding contact email)
USER_AGENT_BASE = "BMLibrarian/1.0 (PDF Bulk Downloader"

# Default output directory
DEFAULT_OUTPUT_DIR = "~/europepmc_pdf"


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
        pdf_output_dir: Optional[Path] = None,
        contact_email: Optional[str] = None
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
            contact_email: Optional contact email for User-Agent header

        Raises:
            ValueError: If pmcid_ranges contains invalid ranges
        """
        self.output_dir = Path(output_dir).expanduser()
        self.pmcid_ranges = self._validate_pmcid_ranges(pmcid_ranges)
        self.delay_between_files = delay_between_files
        self.timeout = timeout
        self.max_retries = max_retries
        self.extract_pdfs = extract_pdfs
        self._session: Optional[requests.Session] = None

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

        # Build User-Agent header
        if contact_email:
            user_agent = f"{USER_AGENT_BASE}; mailto:{contact_email})"
        else:
            user_agent = f"{USER_AGENT_BASE})"
        self._user_agent = user_agent

    def _validate_pmcid_ranges(
        self,
        ranges: Optional[List[Tuple[int, int]]]
    ) -> Optional[List[Tuple[int, int]]]:
        """Validate and normalize PMCID ranges.

        Args:
            ranges: List of (start, end) tuples

        Returns:
            Validated ranges or None

        Raises:
            ValueError: If ranges are invalid
        """
        if ranges is None:
            return None

        validated = []
        for start, end in ranges:
            # Validate bounds
            if start < MIN_PMCID or end < MIN_PMCID:
                raise ValueError(
                    f"PMCID range ({start}, {end}) contains invalid values. "
                    f"PMCIDs must be >= {MIN_PMCID}"
                )
            if start > MAX_PMCID or end > MAX_PMCID:
                raise ValueError(
                    f"PMCID range ({start}, {end}) exceeds maximum value {MAX_PMCID}"
                )
            # Ensure start <= end
            if start > end:
                logger.warning(
                    f"Swapping reversed PMCID range: ({start}, {end}) -> ({end}, {start})"
                )
                start, end = end, start
            validated.append((start, end))

        return validated if validated else None

    def _get_session(self) -> requests.Session:
        """Get or create HTTP session (lazy initialization).

        Returns:
            HTTP session with configured headers
        """
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update({
                'User-Agent': self._user_agent
            })
        return self._session

    def close(self) -> None:
        """Close HTTP session and release resources."""
        if self._session is not None:
            self._session.close()
            self._session = None

    def __enter__(self) -> 'EuropePMCPDFDownloader':
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit - close resources."""
        self.close()

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
        refresh: bool = False,
        max_directories: Optional[int] = None,
        progress_callback: Optional[Callable[[str, int, int], None]] = None
    ) -> List[PDFPackageInfo]:
        """List available PDF packages from Europe PMC FTP.

        Europe PMC PDF structure (as of 2025):
        - Top-level directories: PMCxxxx000/, PMCxxxx001/, etc.
        - Inside each directory: PMC#######.zip files (e.g., PMC1034000.zip)
        - Each zip contains a single PDF for that PMCID

        Note: There are 1000+ directories with potentially millions of zip files.
        Use max_directories to limit scanning scope or pmcid_ranges in constructor.

        Args:
            refresh: Force refresh from server
            max_directories: Maximum number of directories to scan (None for all)
            progress_callback: Callback(dir_name, current, total) for progress updates

        Returns:
            List of available PDFPackageInfo objects
        """
        if self.packages and not refresh:
            return list(self.packages.values())

        logger.info("Fetching PDF package list from Europe PMC FTP...")

        packages = []

        try:
            session = self._get_session()

            # First, get the list of top-level directories
            response = session.get(
                EUROPE_PMC_PDF_BASE_URL,
                timeout=self.timeout
            )
            response.raise_for_status()

            # Find all PMCxxxx### directories
            # Pattern matches: PMCxxxx000/, PMCxxxx001/, ..., PMCxxxx1400/, etc.
            # Uses \d{3,4} to match 3-4 digits (directories go from 000 to 1400+)
            dir_pattern = r'href="(PMCxxxx\d{3,4})/"'
            directories = []
            match_count = 0
            for match in re.finditer(dir_pattern, response.text):
                match_count += 1
                if match_count > MAX_REGEX_MATCHES:
                    logger.warning(
                        f"Reached maximum regex matches ({MAX_REGEX_MATCHES}), "
                        "stopping directory discovery"
                    )
                    break
                directories.append(match.group(1))

            # Sort directories for consistent ordering
            directories.sort()

            # Apply max_directories limit if specified
            total_dirs = len(directories)
            if max_directories is not None and max_directories < total_dirs:
                directories = directories[:max_directories]
                logger.info(
                    f"Limiting scan to first {max_directories} of {total_dirs} directories"
                )

            logger.info(f"Scanning {len(directories)} PDF directories...")

            # Now scan each directory for zip files
            for i, dir_name in enumerate(directories):
                if progress_callback:
                    progress_callback(dir_name, i + 1, len(directories))

                try:
                    dir_url = f"{EUROPE_PMC_PDF_BASE_URL}{dir_name}/"
                    dir_response = session.get(dir_url, timeout=self.timeout)
                    dir_response.raise_for_status()

                    # Find all PMC#######.zip files in this directory
                    # Pattern: PMC followed by 7+ digits, then .zip
                    zip_pattern = r'href="(PMC(\d{7,9})\.zip)"'
                    match_count = 0
                    for match in re.finditer(zip_pattern, dir_response.text):
                        match_count += 1
                        if match_count > MAX_REGEX_MATCHES:
                            logger.warning(
                                f"Reached maximum regex matches ({MAX_REGEX_MATCHES}) "
                                f"in directory {dir_name}"
                            )
                            break

                        filename = match.group(1)
                        pmcid_num = int(match.group(2))

                        # Validate PMCID bounds
                        if pmcid_num < MIN_PMCID or pmcid_num > MAX_PMCID:
                            logger.debug(f"Skipping out-of-range PMCID: {filename}")
                            continue

                        # Check if this PMCID is in our configured range
                        if self._in_pmcid_range(pmcid_num, pmcid_num):
                            # Extract size from the HTML if available
                            # Format: <td align="right">247K</td>
                            size_bytes = self._parse_size_from_html(
                                dir_response.text, filename
                            )

                            pkg = PDFPackageInfo(
                                filename=filename,
                                pmcid_start=pmcid_num,
                                pmcid_end=pmcid_num,  # Single PMCID per zip
                                size_bytes=size_bytes,
                                url=f"{dir_url}{filename}"
                            )

                            # Preserve existing download status
                            if filename in self.packages:
                                existing = self.packages[filename]
                                pkg.downloaded = existing.downloaded
                                pkg.verified = existing.verified
                                pkg.extracted = existing.extracted
                                pkg.download_date = existing.download_date
                                pkg.pdf_count = existing.pdf_count

                            packages.append(pkg)

                    logger.debug(
                        f"Scanned {dir_name}: found {match_count} packages "
                        f"({i+1}/{len(directories)})"
                    )

                except Exception as e:
                    logger.warning(f"Failed to scan directory {dir_name}: {e}")
                    continue

            # Sort by PMCID
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

    def list_directories(self) -> List[str]:
        """List available top-level PDF directories without scanning contents.

        This is much faster than list_available_packages() as it only fetches
        the top-level directory listing.

        Returns:
            List of directory names (e.g., ['PMCxxxx000', 'PMCxxxx001', ...])
        """
        logger.info("Fetching PDF directory list from Europe PMC FTP...")

        try:
            session = self._get_session()
            response = session.get(
                EUROPE_PMC_PDF_BASE_URL,
                timeout=self.timeout
            )
            response.raise_for_status()

            # Find all PMCxxxx### directories (000 to 1400+)
            dir_pattern = r'href="(PMCxxxx\d{3,4})/"'
            directories = []
            for match in re.finditer(dir_pattern, response.text):
                directories.append(match.group(1))

            directories.sort()
            logger.info(f"Found {len(directories)} PDF directories")
            return directories

        except Exception as e:
            logger.error(f"Failed to list directories: {e}")
            raise

    def _parse_size_from_html(self, html: str, filename: str) -> int:
        """Parse file size from HTML directory listing.

        Args:
            html: HTML content of directory listing
            filename: Name of the file to find size for

        Returns:
            Size in bytes, or 0 if not found
        """
        # Look for pattern like: href="PMC1034000.zip">PMC1034000.zip</a>...247K
        escaped_filename = re.escape(filename)
        pattern = rf'{escaped_filename}</a>.*?<td[^>]*>\s*([\d.]+)([KMGT]?)\s*</td>'
        match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)

        if match:
            try:
                size_num = float(match.group(1))
                unit = match.group(2).upper() if match.group(2) else ''

                multipliers = {'': 1, 'K': 1024, 'M': 1024**2, 'G': 1024**3, 'T': 1024**4}
                return int(size_num * multipliers.get(unit, 1))
            except (ValueError, KeyError):
                pass

        return 0

    def _in_pmcid_range(self, start: int, end: int) -> bool:
        """Check if package overlaps with configured PMCID ranges."""
        if not self.pmcid_ranges:
            return True

        return any(
            (start >= r[0] and end <= r[1]) or
            (start <= r[1] and end >= r[0])
            for r in self.pmcid_ranges
        )

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
        session = self._get_session()
        last_progress_log = 0

        for attempt in range(self.max_retries):
            try:
                if attempt > 0:
                    logger.info(f"Retry attempt {attempt + 1}/{self.max_retries}")
                    # Linear backoff with jitter to prevent thundering herd
                    base_delay = DEFAULT_RETRY_BASE_DELAY * attempt
                    jitter = base_delay * DEFAULT_JITTER_FACTOR * random.random()
                    time.sleep(base_delay + jitter)

                response = session.get(
                    url,
                    stream=True,
                    timeout=self.timeout
                )
                response.raise_for_status()

                total_size = int(response.headers.get('content-length', 0))
                pkg.size_bytes = total_size
                downloaded = 0
                last_progress_log = 0

                with open(output_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=DEFAULT_CHUNK_SIZE):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)

                            # Log progress using byte threshold (more efficient than modulo)
                            if total_size > 0 and (downloaded - last_progress_log) >= PROGRESS_LOG_INTERVAL_BYTES:
                                pct = (downloaded / total_size * 100)
                                logger.debug(
                                    f"  {self._format_bytes(downloaded)} / "
                                    f"{self._format_bytes(total_size)} ({pct:.1f}%)"
                                )
                                last_progress_log = downloaded

                return True

            except Exception as e:
                logger.warning(f"Download error: {e}")
                if output_path.exists():
                    output_path.unlink()

        return False

    def _verify_archive(self, file_path: Path) -> bool:
        """Verify zip file integrity.

        Args:
            file_path: Path to archive file

        Returns:
            True if file is valid zip
        """
        try:
            with zipfile.ZipFile(file_path, 'r') as zf:
                # Test CRC of all files in the archive
                bad_file = zf.testzip()
                if bad_file is not None:
                    logger.warning(f"Corrupted file in archive: {bad_file}")
                    return False
                # Verify there's at least one file
                return len(zf.namelist()) > 0
        except zipfile.BadZipFile as e:
            logger.warning(f"Invalid zip file {file_path.name}: {e}")
            return False
        except Exception as e:
            logger.warning(f"Archive verification error for {file_path.name}: {e}")
            return False

    def _is_safe_zip_member(self, member_name: str) -> bool:
        """Check if a zip archive member has a safe path.

        Prevents path traversal attacks by rejecting:
        - Absolute paths
        - Paths containing '..' components
        - Paths starting with '/'

        Args:
            member_name: Name/path of the archive member

        Returns:
            True if the path is safe
        """
        # Normalize path separators
        member_path = Path(member_name)

        # Reject absolute paths (both Unix and Windows style)
        if member_path.is_absolute() or member_name.startswith('/'):
            logger.warning(f"Skipping unsafe absolute path: {member_name}")
            return False

        # Reject paths with traversal components
        # Check each path component for '..' or absolute markers
        for part in member_path.parts:
            if part == '..':
                logger.warning(f"Skipping path traversal attempt: {member_name}")
                return False
            if part.startswith('/'):
                logger.warning(f"Skipping unsafe path component: {member_name}")
                return False

        return True

    def _extract_pdfs_from_package(self, pkg: PDFPackageInfo) -> int:
        """Extract PDF files from a downloaded zip package.

        PDFs are extracted to PMCID-based subdirectories for organization.
        Files are named by their PMCID: PMC{id}.pdf

        Implements path traversal protection to prevent malicious archives
        from extracting files outside the intended directory.

        Args:
            pkg: Package to extract PDFs from

        Returns:
            Number of PDFs successfully extracted
        """
        package_path = self.packages_dir / pkg.filename
        if not package_path.exists():
            return 0

        pdf_count = 0
        skipped_unsafe = 0

        try:
            with zipfile.ZipFile(package_path, 'r') as zf:
                for member in zf.namelist():
                    # Security check: validate archive member path
                    if not self._is_safe_zip_member(member):
                        skipped_unsafe += 1
                        continue

                    name_lower = member.lower()
                    if not name_lower.endswith('.pdf'):
                        continue

                    # Extract PMCID from filename using bounded regex
                    pmcid_match = re.search(r'PMC(\d{1,9})', member, re.IGNORECASE)
                    if not pmcid_match:
                        continue

                    pmcid_num = int(pmcid_match.group(1))

                    # Validate PMCID is within bounds
                    if pmcid_num < MIN_PMCID or pmcid_num > MAX_PMCID:
                        logger.debug(f"Skipping out-of-range PMCID: {pmcid_num}")
                        continue

                    pmcid = f"PMC{pmcid_num}"

                    # Determine output path with PMCID-based organization
                    pdf_subdir = self.pdf_dir / self._get_pmcid_subdir(pmcid_num)
                    pdf_subdir.mkdir(parents=True, exist_ok=True)
                    pdf_path = pdf_subdir / f"{pmcid}.pdf"

                    # Skip if already exists
                    if pdf_path.exists():
                        pdf_count += 1
                        continue

                    # Extract PDF using read() instead of extract() for safety
                    try:
                        pdf_content = zf.read(member)

                        # Verify it's a valid PDF
                        if pdf_content[:4] == b'%PDF':
                            pdf_path.write_bytes(pdf_content)
                            pdf_count += 1
                            logger.debug(f"Extracted {pmcid}.pdf ({len(pdf_content)} bytes)")
                        else:
                            logger.debug(f"Skipping invalid PDF: {member}")
                    except Exception as e:
                        logger.debug(f"Failed to extract {member}: {e}")

        except zipfile.BadZipFile as e:
            logger.warning(f"Invalid zip file {pkg.filename}: {e}")
        except Exception as e:
            logger.warning(f"Error extracting PDFs from {pkg.filename}: {e}")

        if skipped_unsafe > 0:
            logger.warning(
                f"Skipped {skipped_unsafe} unsafe paths in {pkg.filename}"
            )

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

        Raises:
            ValueError: If PMCID is out of valid range
        """
        # Validate PMCID bounds to prevent integer overflow
        if pmcid < MIN_PMCID or pmcid > MAX_PMCID:
            raise ValueError(
                f"PMCID {pmcid} out of valid range ({MIN_PMCID}-{MAX_PMCID})"
            )

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
