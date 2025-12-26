"""Europe PMC Open Access bulk downloader.

Downloads full-text XML articles from Europe PMC Open Access FTP
for offline access to biomedical literature.

Features:
- Resumable downloads with state persistence
- Download verification (gzip integrity check)
- Configurable rate limiting (polite to servers)
- PMCID range filtering for selective downloads
- Progress tracking with real-time updates

Usage:
    from bmlibrarian.importers.europe_pmc_bulk_downloader import EuropePMCBulkDownloader
    from pathlib import Path

    downloader = EuropePMCBulkDownloader(
        output_dir=Path('~/europepmc'),
        delay_between_files=60  # 1 minute between downloads
    )

    # List available packages
    packages = downloader.list_available_packages()

    # Download all packages
    downloader.download_packages()

    # Check status
    status = downloader.get_status()
"""

import gzip
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

# Europe PMC FTP server details
EUROPE_PMC_BASE_URL = "https://europepmc.org/ftp/oa/"

# Default configuration
DEFAULT_DELAY_SECONDS = 60  # 1 minute between files (polite)
DEFAULT_TIMEOUT = 300  # 5 minutes for large files
DEFAULT_MAX_RETRIES = 3
DEFAULT_CHUNK_SIZE = 8192  # 8KB chunks for streaming


@dataclass
class EuropePMCPackageInfo:
    """Information about a Europe PMC OA package file."""

    filename: str  # e.g., "PMC13900_PMC17829.xml.gz"
    pmcid_start: int  # e.g., 13900
    pmcid_end: int  # e.g., 17829
    size_bytes: int = 0
    url: str = ""
    downloaded: bool = False
    verified: bool = False
    download_date: Optional[str] = None

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
            'download_date': self.download_date
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EuropePMCPackageInfo':
        """Create from dictionary."""
        return cls(
            filename=data['filename'],
            pmcid_start=data['pmcid_start'],
            pmcid_end=data['pmcid_end'],
            size_bytes=data.get('size_bytes', 0),
            url=data.get('url', ''),
            downloaded=data.get('downloaded', False),
            verified=data.get('verified', False),
            download_date=data.get('download_date')
        )


@dataclass
class DownloadProgress:
    """Tracks overall download progress."""

    total_packages: int = 0
    downloaded_packages: int = 0
    verified_packages: int = 0
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
            'total_bytes': self.total_bytes,
            'downloaded_bytes': self.downloaded_bytes,
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
            verified_packages=data.get('verified_packages', 0),
            total_bytes=data.get('total_bytes', 0),
            downloaded_bytes=data.get('downloaded_bytes', 0),
            errors=data.get('errors', []),
            start_time=datetime.fromisoformat(data['start_time']) if data.get('start_time') else None,
            last_update=datetime.fromisoformat(data['last_update']) if data.get('last_update') else None
        )


class EuropePMCBulkDownloader:
    """Bulk downloader for Europe PMC Open Access XML packages.

    Downloads gzip-compressed XML files containing JATS-formatted
    full-text articles from Europe PMC's Open Access FTP.
    """

    def __init__(
        self,
        output_dir: Path,
        pmcid_ranges: Optional[List[Tuple[int, int]]] = None,
        delay_between_files: int = DEFAULT_DELAY_SECONDS,
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES
    ):
        """Initialize bulk downloader.

        Args:
            output_dir: Base directory for downloaded files
            pmcid_ranges: List of (start, end) PMCID ranges to download.
                Default: None (download all)
            delay_between_files: Seconds to wait between file downloads
            timeout: HTTP timeout in seconds
            max_retries: Maximum retry attempts per file
        """
        self.output_dir = Path(output_dir).expanduser()
        self.pmcid_ranges = pmcid_ranges
        self.delay_between_files = delay_between_files
        self.timeout = timeout
        self.max_retries = max_retries

        # Create directory structure
        self.packages_dir = self.output_dir / 'packages'
        self.state_file = self.output_dir / 'download_state.json'

        self.packages_dir.mkdir(parents=True, exist_ok=True)

        # Load or initialize state
        self.packages: Dict[str, EuropePMCPackageInfo] = {}
        self.progress = DownloadProgress()
        self._load_state()

    def _load_state(self) -> None:
        """Load download state from file."""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    state = json.load(f)

                self.packages = {
                    k: EuropePMCPackageInfo.from_dict(v)
                    for k, v in state.get('packages', {}).items()
                }
                self.progress = DownloadProgress.from_dict(
                    state.get('progress', {})
                )
                logger.info(
                    f"Loaded state: {self.progress.downloaded_packages}/"
                    f"{self.progress.total_packages} packages downloaded, "
                    f"{self.progress.verified_packages} verified"
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
    ) -> List[EuropePMCPackageInfo]:
        """List available packages from Europe PMC FTP.

        Args:
            refresh: Force refresh from server

        Returns:
            List of available EuropePMCPackageInfo objects
        """
        if self.packages and not refresh:
            return list(self.packages.values())

        logger.info("Fetching package list from Europe PMC FTP...")

        packages = []

        try:
            response = requests.get(EUROPE_PMC_BASE_URL, timeout=self.timeout)
            response.raise_for_status()

            # Parse HTML directory listing
            # Look for patterns like: PMC13900_PMC17829.xml.gz
            pattern = r'href="(PMC(\d+)_PMC(\d+)\.xml\.gz)"'

            for match in re.finditer(pattern, response.text):
                filename = match.group(1)
                pmcid_start = int(match.group(2))
                pmcid_end = int(match.group(3))

                # Filter by PMCID range if specified
                if self.pmcid_ranges:
                    in_range = any(
                        (pmcid_start >= r[0] and pmcid_end <= r[1]) or
                        (pmcid_start <= r[1] and pmcid_end >= r[0])
                        for r in self.pmcid_ranges
                    )
                    if not in_range:
                        continue

                pkg = EuropePMCPackageInfo(
                    filename=filename,
                    pmcid_start=pmcid_start,
                    pmcid_end=pmcid_end,
                    url=f"{EUROPE_PMC_BASE_URL}{filename}"
                )

                # Preserve download status from existing state
                if filename in self.packages:
                    existing = self.packages[filename]
                    pkg.downloaded = existing.downloaded
                    pkg.verified = existing.verified
                    pkg.download_date = existing.download_date
                    pkg.size_bytes = existing.size_bytes

                packages.append(pkg)

            # Sort by PMCID start
            packages.sort(key=lambda p: p.pmcid_start)

        except Exception as e:
            logger.error(f"Failed to list packages: {e}")
            raise

        # Update state
        self.packages = {p.filename: p for p in packages}
        self.progress.total_packages = len(packages)
        self._save_state()

        logger.info(f"Found {len(packages)} packages")

        return packages

    def download_packages(
        self,
        limit: Optional[int] = None,
        progress_callback: Optional[Callable[[str, int, int], None]] = None
    ) -> int:
        """Download packages from Europe PMC.

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
                    pkg.download_date = datetime.now().isoformat()
                    self.progress.downloaded_packages = sum(
                        1 for p in self.packages.values() if p.downloaded
                    )
                    self.progress.downloaded_bytes = sum(
                        p.size_bytes for p in self.packages.values() if p.downloaded
                    )

                    # Verify the download
                    if self._verify_gzip(self.packages_dir / pkg.filename):
                        pkg.verified = True
                        self.progress.verified_packages = sum(
                            1 for p in self.packages.values() if p.verified
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

    def _download_package(self, pkg: EuropePMCPackageInfo) -> bool:
        """Download a single package.

        Args:
            pkg: Package to download

        Returns:
            True if download successful
        """
        output_path = self.packages_dir / pkg.filename

        # Skip if already exists and verified
        if output_path.exists() and output_path.stat().st_size > 0:
            if pkg.verified or self._verify_gzip(output_path):
                logger.info(f"Package already exists and verified: {pkg.filename}")
                pkg.downloaded = True
                pkg.verified = True
                return True

        return self._download_via_https(pkg.url, output_path, pkg)

    def _download_via_https(
        self,
        url: str,
        output_path: Path,
        pkg: EuropePMCPackageInfo
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
                    time.sleep(5 * attempt)  # Linear backoff

                response = requests.get(url, stream=True, timeout=self.timeout)
                response.raise_for_status()

                total_size = int(response.headers.get('content-length', 0))
                pkg.size_bytes = total_size
                downloaded = 0

                with open(output_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=DEFAULT_CHUNK_SIZE):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)

                            # Log progress every 10MB
                            if total_size > 0 and downloaded % (10 * 1024 * 1024) < DEFAULT_CHUNK_SIZE:
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

    def _verify_gzip(self, file_path: Path) -> bool:
        """Verify gzip file integrity by reading through it.

        Args:
            file_path: Path to gzip file

        Returns:
            True if file is valid gzip
        """
        try:
            with gzip.open(file_path, 'rb') as f:
                # Read in chunks to verify full file
                while f.read(65536):  # 64KB chunks
                    pass
            return True
        except Exception as e:
            logger.warning(f"Gzip verification error for {file_path.name}: {e}")
            return False

    def verify_all_downloads(self) -> Dict[str, Any]:
        """Verify integrity of all downloaded packages.

        Returns:
            Dictionary with verification results
        """
        logger.info("Verifying all downloaded packages...")

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

            if self._verify_gzip(file_path):
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

    def get_status(self) -> Dict[str, Any]:
        """Get current download status.

        Returns:
            Status dictionary
        """
        return {
            'output_dir': str(self.output_dir),
            'packages': {
                'total': self.progress.total_packages,
                'downloaded': self.progress.downloaded_packages,
                'verified': self.progress.verified_packages,
                'pending': self.progress.total_packages - self.progress.downloaded_packages
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
