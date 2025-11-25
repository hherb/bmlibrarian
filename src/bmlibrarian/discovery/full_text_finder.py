"""Full-text discovery orchestrator.

Coordinates multiple resolvers to find and download PDF full-text
for documents, prioritizing open access sources.

Supports a two-phase download approach:
1. Direct HTTP downloads (fast, works for OA and properly configured sites)
2. Browser-based fallback (handles Cloudflare, anti-bot protections, embedded viewers)
"""

import logging
import time
import ftplib
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable
from urllib.parse import urlparse

import requests

from .data_types import (
    PDFSource, DiscoveryResult, DownloadResult, DocumentIdentifiers,
    ResolutionStatus, SourceType, AccessType
)
from .resolvers import (
    BaseResolver, DirectURLResolver, DOIResolver,
    PMCResolver, UnpaywallResolver, OpenAthensResolver
)
from .pmc_package_downloader import PMCPackageDownloader

logger = logging.getLogger(__name__)

# Default configuration constants
DEFAULT_TIMEOUT = 30
DEFAULT_UNPAYWALL_EMAIL = "bmlibrarian@example.com"
DEFAULT_BROWSER_TIMEOUT_MS = 60000
DEFAULT_BROWSER_HEADLESS = True
DEFAULT_MAX_DOWNLOAD_ATTEMPTS = 3


class FullTextFinder:
    """Orchestrates full-text PDF discovery from multiple sources.

    Tries resolvers in order of preference:
    1. PubMed Central (verified open access)
    2. Unpaywall (open access aggregator)
    3. DOI resolution (CrossRef, doi.org)
    4. Direct URL (from database)
    5. OpenAthens proxy (institutional access, if configured)
    """

    def __init__(
        self,
        unpaywall_email: Optional[str] = None,
        openathens_proxy_url: Optional[str] = None,
        openathens_auth: Optional[Any] = None,
        timeout: int = DEFAULT_TIMEOUT,
        prefer_open_access: bool = True,
        skip_resolvers: Optional[List[str]] = None
    ):
        """Initialize FullTextFinder.

        Args:
            unpaywall_email: Email for Unpaywall API (required for Unpaywall)
            openathens_proxy_url: Base URL for OpenAthens proxy
            openathens_auth: OpenAthensAuth instance for authenticated downloads
            timeout: HTTP request timeout in seconds
            prefer_open_access: If True, prioritize OA sources over others
            skip_resolvers: List of resolver names to skip
        """
        self.timeout = timeout
        self.prefer_open_access = prefer_open_access
        self.openathens_auth = openathens_auth
        self.skip_resolvers = set(skip_resolvers or [])

        # Initialize resolvers in priority order
        self.resolvers: List[BaseResolver] = []

        # PMC - highest priority for OA
        if 'pmc' not in self.skip_resolvers:
            self.resolvers.append(PMCResolver(timeout=timeout))

        # Unpaywall - excellent OA coverage
        if 'unpaywall' not in self.skip_resolvers:
            email = unpaywall_email or DEFAULT_UNPAYWALL_EMAIL
            self.resolvers.append(UnpaywallResolver(email=email, timeout=timeout))

        # DOI resolution
        if 'doi' not in self.skip_resolvers:
            self.resolvers.append(DOIResolver(timeout=timeout))

        # Direct URL from database
        if 'direct_url' not in self.skip_resolvers:
            self.resolvers.append(DirectURLResolver(timeout=timeout))

        # OpenAthens - last resort for paywalled content
        if 'openathens' not in self.skip_resolvers and openathens_proxy_url:
            self.resolvers.append(OpenAthensResolver(
                proxy_base_url=openathens_proxy_url,
                timeout=timeout
            ))

        # HTTP session for downloads
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': (
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/131.0.0.0 Safari/537.36'
            ),
            'Accept': 'application/pdf,*/*'
        })

        # PMC package downloader for tar.gz files
        self._pmc_package_downloader = PMCPackageDownloader(timeout=timeout)

    def discover(
        self,
        identifiers: DocumentIdentifiers,
        stop_on_first_oa: bool = True,
        progress_callback: Optional[Callable[[str, str], None]] = None
    ) -> DiscoveryResult:
        """Discover PDF sources for a document.

        Args:
            identifiers: Document identifiers (DOI, PMID, etc.)
            stop_on_first_oa: Stop searching after finding first OA source
            progress_callback: Optional callback(resolver_name, status)

        Returns:
            DiscoveryResult with all found sources
        """
        start_time = time.time()

        result = DiscoveryResult(
            identifiers=identifiers,
            sources=[],
            resolution_results=[]
        )

        if not identifiers.has_identifiers():
            logger.warning("No usable identifiers provided")
            result.total_duration_ms = (time.time() - start_time) * 1000
            return result

        # Run each resolver
        for resolver in self.resolvers:
            if progress_callback:
                progress_callback(resolver.name, "resolving")

            try:
                resolution = resolver.resolve(identifiers)
                result.resolution_results.append(resolution)

                if resolution.status == ResolutionStatus.SUCCESS:
                    # Add sources, avoiding duplicates
                    for source in resolution.sources:
                        if not self._is_duplicate_source(source, result.sources):
                            result.sources.append(source)

                    # Check if we should stop early
                    if stop_on_first_oa and self.prefer_open_access:
                        oa_sources = [s for s in resolution.sources
                                     if s.access_type == AccessType.OPEN]
                        if oa_sources:
                            logger.info(f"Found OA source via {resolver.name}, stopping search")
                            if progress_callback:
                                progress_callback(resolver.name, "found_oa")
                            break

                if progress_callback:
                    status = "found" if resolution.sources else "not_found"
                    progress_callback(resolver.name, status)

            except Exception as e:
                logger.error(f"Resolver {resolver.name} failed: {e}")
                if progress_callback:
                    progress_callback(resolver.name, "error")

        # Sort sources by priority
        result.sources.sort(key=lambda s: s.priority)

        # Select best source
        result.best_source = result.select_best_source()
        result.total_duration_ms = (time.time() - start_time) * 1000

        return result

    def discover_and_download(
        self,
        identifiers: DocumentIdentifiers,
        output_path: Path,
        max_attempts: int = DEFAULT_MAX_DOWNLOAD_ATTEMPTS,
        use_browser_fallback: bool = True,
        browser_headless: bool = DEFAULT_BROWSER_HEADLESS,
        browser_timeout: int = DEFAULT_BROWSER_TIMEOUT_MS,
        progress_callback: Optional[Callable[[str, str], None]] = None,
        verify_content: bool = False,
        delete_on_mismatch: bool = False
    ) -> DownloadResult:
        """Discover PDF sources and download the best one.

        Uses a two-phase approach:
        1. First tries direct HTTP downloads from discovered sources
        2. If all HTTP attempts fail, falls back to browser-based download

        Args:
            identifiers: Document identifiers
            output_path: Path to save PDF file
            max_attempts: Maximum download attempts per source
            use_browser_fallback: If True, use browser automation when HTTP fails
            browser_headless: Run browser in headless mode (default True)
            browser_timeout: Browser operation timeout in ms (default 60000)
            progress_callback: Optional callback(stage, status)
            verify_content: If True, verify downloaded PDF matches expected DOI/title
            delete_on_mismatch: If True and verify_content=True, delete mismatched PDFs

        Returns:
            DownloadResult with download status and verification results
        """
        start_time = time.time()

        # First, discover sources
        if progress_callback:
            progress_callback("discovery", "starting")

        discovery = self.discover(
            identifiers,
            stop_on_first_oa=self.prefer_open_access,
            progress_callback=progress_callback
        )

        if not discovery.sources:
            return DownloadResult(
                success=False,
                error_message="No PDF sources found",
                duration_ms=(time.time() - start_time) * 1000
            )

        # Try downloading from each source in priority order via HTTP
        if progress_callback:
            progress_callback("download", "starting")

        last_error = None
        for source in discovery.sources:
            result = self._download_from_source(
                source=source,
                output_path=output_path,
                max_attempts=max_attempts
            )

            if result.success:
                result.duration_ms = (time.time() - start_time) * 1000
                if progress_callback:
                    progress_callback("download", "success")

                # Verify content if requested
                if verify_content:
                    result = self._verify_downloaded_pdf(
                        result, identifiers, delete_on_mismatch, progress_callback
                    )

                return result

            last_error = result.error_message
            logger.debug(f"HTTP download failed from {source.source_type.value}: {result.error_message}")

        # All HTTP attempts failed - try browser fallback
        if use_browser_fallback and discovery.sources:
            if progress_callback:
                progress_callback("browser_download", "starting")

            result = self._download_with_browser(
                sources=discovery.sources,
                output_path=output_path,
                headless=browser_headless,
                timeout=browser_timeout
            )

            if result.success:
                result.duration_ms = (time.time() - start_time) * 1000
                if progress_callback:
                    progress_callback("browser_download", "success")

                # Verify content if requested
                if verify_content:
                    result = self._verify_downloaded_pdf(
                        result, identifiers, delete_on_mismatch, progress_callback
                    )

                return result

            last_error = result.error_message
            logger.debug(f"Browser download failed: {result.error_message}")

        # All sources and methods failed
        if progress_callback:
            progress_callback("download", "failed")

        return DownloadResult(
            success=False,
            error_message=f"All {len(discovery.sources)} sources failed. Last error: {last_error}",
            duration_ms=(time.time() - start_time) * 1000,
            attempts=len(discovery.sources)
        )

    def _download_with_browser(
        self,
        sources: List[PDFSource],
        output_path: Path,
        headless: bool = DEFAULT_BROWSER_HEADLESS,
        timeout: int = DEFAULT_BROWSER_TIMEOUT_MS
    ) -> DownloadResult:
        """Download PDF using browser automation.

        Tries each source URL with browser-based download.
        Handles Cloudflare, anti-bot protections, and embedded PDF viewers.

        Args:
            sources: List of PDF sources to try
            output_path: Path to save the PDF
            headless: Run browser in headless mode
            timeout: Browser operation timeout in ms

        Returns:
            DownloadResult with download status
        """
        start_time = time.time()

        try:
            from bmlibrarian.utils.browser_downloader import download_pdf_with_browser
        except ImportError:
            logger.warning(
                "Browser downloader not available. Install with: "
                "uv add playwright && uv run python -m playwright install chromium"
            )
            return DownloadResult(
                success=False,
                error_message="Browser downloader not available (playwright not installed)",
                duration_ms=(time.time() - start_time) * 1000
            )

        # Try each source URL with browser download (skip FTP URLs - browsers can't handle them)
        last_error = None
        for source in sources:
            # Skip FTP URLs - browsers don't support FTP protocol
            if self._is_ftp_url(source.url):
                logger.debug(f"Skipping FTP URL for browser download: {source.url}")
                continue

            logger.info(f"Trying browser download from {source.source_type.value}: {source.url}")

            try:
                result = download_pdf_with_browser(
                    url=source.url,
                    save_path=output_path,
                    headless=headless,
                    timeout=timeout
                )

                if result.get('status') == 'success':
                    file_size = result.get('size', 0)
                    if output_path.exists():
                        file_size = output_path.stat().st_size

                    logger.info(f"Browser download successful: {output_path} ({file_size} bytes)")

                    return DownloadResult(
                        success=True,
                        source=source,
                        file_path=str(output_path),
                        file_size=file_size,
                        duration_ms=(time.time() - start_time) * 1000
                    )

                last_error = result.get('error', 'Unknown browser download error')
                logger.debug(f"Browser download failed for {source.url}: {last_error}")

            except Exception as e:
                last_error = str(e)
                logger.error(f"Browser download exception for {source.url}: {e}")

        return DownloadResult(
            success=False,
            error_message=f"Browser download failed: {last_error}",
            duration_ms=(time.time() - start_time) * 1000,
            attempts=len(sources)
        )

    def _is_ftp_url(self, url: str) -> bool:
        """Check if URL uses FTP protocol.

        Args:
            url: URL to check

        Returns:
            True if URL is an FTP URL
        """
        return url.lower().startswith('ftp://')

    def _download_via_ftp(
        self,
        url: str,
        output_path: Path,
        max_attempts: int
    ) -> DownloadResult:
        """Download file via FTP protocol.

        Args:
            url: FTP URL (e.g., ftp://ftp.ncbi.nlm.nih.gov/pub/pmc/oa_pdf/...)
            output_path: Path to save file
            max_attempts: Maximum retry attempts

        Returns:
            DownloadResult
        """
        start_time = time.time()
        last_error = None

        # Parse FTP URL
        parsed = urlparse(url)
        host = parsed.hostname
        port = parsed.port or 21
        path = parsed.path

        if not host or not path:
            return DownloadResult(
                success=False,
                error_message=f"Invalid FTP URL: {url}",
                duration_ms=(time.time() - start_time) * 1000
            )

        for attempt in range(max_attempts):
            try:
                if attempt > 0:
                    logger.info(f"FTP retry attempt {attempt + 1}/{max_attempts}")
                    time.sleep(2 ** attempt)  # Exponential backoff

                # Connect to FTP server
                ftp = ftplib.FTP()
                ftp.connect(host, port, timeout=self.timeout)
                ftp.login()  # Anonymous login

                # Create output directory if needed
                output_path.parent.mkdir(parents=True, exist_ok=True)

                # Download file
                total_size = 0
                with open(output_path, 'wb') as f:
                    def write_chunk(data: bytes) -> None:
                        nonlocal total_size
                        f.write(data)
                        total_size += len(data)

                    ftp.retrbinary(f'RETR {path}', write_chunk)

                ftp.quit()

                # Verify file was written
                if total_size == 0:
                    last_error = "Downloaded file is empty"
                    if output_path.exists():
                        output_path.unlink()
                    continue

                # Verify it's actually a PDF
                if not self._verify_pdf(output_path):
                    last_error = "Downloaded file is not a valid PDF"
                    output_path.unlink()
                    continue

                logger.info(f"Downloaded PDF via FTP ({total_size} bytes) from {host}")

                return DownloadResult(
                    success=True,
                    file_path=str(output_path),
                    file_size=total_size,
                    duration_ms=(time.time() - start_time) * 1000,
                    attempts=attempt + 1
                )

            except ftplib.error_perm as e:
                last_error = f"FTP permission error: {e}"
                logger.debug(f"FTP permission denied for {url}: {e}")
                break  # Don't retry on permission errors

            except ftplib.error_temp as e:
                last_error = f"FTP temporary error: {e}"
                logger.debug(f"FTP temporary error for {url}: {e}")

            except (TimeoutError, ftplib.error_reply) as e:
                last_error = f"FTP connection error: {e}"
                logger.debug(f"FTP connection error for {url}: {e}")

            except Exception as e:
                last_error = f"FTP error: {e}"
                logger.debug(f"FTP download error for {url}: {e}")

        return DownloadResult(
            success=False,
            error_message=last_error,
            duration_ms=(time.time() - start_time) * 1000,
            attempts=max_attempts
        )

    def _download_from_source(
        self,
        source: PDFSource,
        output_path: Path,
        max_attempts: int,
        fulltext_output_dir: Optional[Path] = None
    ) -> DownloadResult:
        """Download PDF from a specific source.

        Args:
            source: PDFSource to download from
            output_path: Path to save file
            max_attempts: Maximum retry attempts
            fulltext_output_dir: Directory for full-text NXML (for PMC packages)

        Returns:
            DownloadResult
        """
        start_time = time.time()

        # Handle PMC package (tar.gz) sources
        if source.source_type == SourceType.PMC_PACKAGE:
            return self._download_pmc_package(
                source=source,
                pdf_output_path=output_path,
                fulltext_output_dir=fulltext_output_dir
            )

        # Check if this is an FTP URL - use FTP download
        if self._is_ftp_url(source.url):
            result = self._download_via_ftp(source.url, output_path, max_attempts)
            if result.success:
                result.source = source
            return result

        # Prepare headers and cookies for HTTP download
        headers = dict(self.session.headers)
        cookies = {}

        # Use OpenAthens auth if available and source is institutional
        if (source.source_type == SourceType.OPENATHENS or
            source.access_type == AccessType.INSTITUTIONAL):
            if self.openathens_auth and self.openathens_auth.is_authenticated():
                # Get user agent from session
                session_ua = self.openathens_auth.get_user_agent()
                if session_ua:
                    headers['User-Agent'] = session_ua

                # Get cookies
                for cookie in self.openathens_auth.get_cookies():
                    cookies[cookie['name']] = cookie['value']

                logger.info("Using OpenAthens authenticated session")

        # Attempt download with retries
        last_error = None
        for attempt in range(max_attempts):
            try:
                if attempt > 0:
                    logger.info(f"Retry attempt {attempt + 1}/{max_attempts}")
                    time.sleep(2 ** attempt)  # Exponential backoff

                response = self.session.get(
                    source.url,
                    headers=headers,
                    cookies=cookies,
                    timeout=self.timeout,
                    stream=True,
                    allow_redirects=True
                )
                response.raise_for_status()

                # Verify content type
                content_type = response.headers.get('content-type', '').lower()
                if 'html' in content_type and 'pdf' not in content_type:
                    # Got HTML instead of PDF - likely a login page
                    last_error = "Received HTML instead of PDF (access denied?)"
                    continue

                # Create output directory if needed
                output_path.parent.mkdir(parents=True, exist_ok=True)

                # Save file
                total_size = 0
                with open(output_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            total_size += len(chunk)

                # Verify file was written
                if total_size == 0:
                    last_error = "Downloaded file is empty"
                    if output_path.exists():
                        output_path.unlink()
                    continue

                # Verify it's actually a PDF
                if not self._verify_pdf(output_path):
                    last_error = "Downloaded file is not a valid PDF"
                    output_path.unlink()
                    continue

                logger.info(f"Downloaded PDF ({total_size} bytes) from {source.source_type.value}")

                return DownloadResult(
                    success=True,
                    source=source,
                    file_path=str(output_path),
                    file_size=total_size,
                    duration_ms=(time.time() - start_time) * 1000,
                    attempts=attempt + 1
                )

            except requests.exceptions.HTTPError as e:
                if e.response.status_code in [401, 403]:
                    last_error = f"Access denied (HTTP {e.response.status_code})"
                    break  # Don't retry on auth errors
                elif e.response.status_code == 404:
                    last_error = "PDF not found (HTTP 404)"
                    break
                else:
                    last_error = f"HTTP error: {e}"

            except requests.exceptions.Timeout:
                last_error = "Download timeout"

            except requests.exceptions.ConnectionError as e:
                last_error = f"Connection error: {e}"

            except Exception as e:
                last_error = str(e)

        return DownloadResult(
            success=False,
            source=source,
            error_message=last_error,
            duration_ms=(time.time() - start_time) * 1000,
            attempts=max_attempts
        )

    def _verify_pdf(self, file_path: Path) -> bool:
        """Verify that a file is a valid PDF.

        Args:
            file_path: Path to file

        Returns:
            True if file appears to be a valid PDF
        """
        try:
            with open(file_path, 'rb') as f:
                header = f.read(8)
                # PDF files start with %PDF-
                return header.startswith(b'%PDF-')
        except Exception:
            return False

    def _verify_downloaded_pdf(
        self,
        download_result: DownloadResult,
        identifiers: DocumentIdentifiers,
        delete_on_mismatch: bool,
        progress_callback: Optional[Callable[[str, str], None]] = None
    ) -> DownloadResult:
        """Verify that downloaded PDF matches expected document identifiers.

        Extracts DOI/PMID/title from the PDF and compares against expected values.
        Updates the DownloadResult with verification status.

        Args:
            download_result: Successful download result to verify
            identifiers: Expected document identifiers
            delete_on_mismatch: If True, delete PDF on verification failure
            progress_callback: Optional progress callback

        Returns:
            Updated DownloadResult with verification fields populated
        """
        if not download_result.success or not download_result.file_path:
            return download_result

        if progress_callback:
            progress_callback("verification", "starting")

        try:
            from .pdf_verifier import PDFVerifier

            verifier = PDFVerifier()
            verification = verifier.verify_pdf(
                pdf_path=Path(download_result.file_path),
                expected_doi=identifiers.doi,
                expected_pmid=identifiers.pmid,
                expected_title=identifiers.title
            )

            # Update download result with verification info
            download_result.verified = verification.verified
            download_result.verification_confidence = verification.confidence
            download_result.verification_match_type = verification.match_type
            download_result.verification_warnings = verification.warnings

            if verification.verified:
                logger.info(
                    f"PDF verified ({verification.match_type}, "
                    f"confidence={verification.confidence:.2f})"
                )
                if progress_callback:
                    progress_callback("verification", "success")
            else:
                warning_msg = "; ".join(verification.warnings) if verification.warnings else "Unknown"
                logger.warning(
                    f"PDF verification FAILED for {download_result.file_path}: {warning_msg}"
                )
                if progress_callback:
                    progress_callback("verification", "mismatch")

                # Delete mismatched PDF if requested
                if delete_on_mismatch:
                    try:
                        Path(download_result.file_path).unlink()
                        logger.info(f"Deleted mismatched PDF: {download_result.file_path}")
                        download_result.success = False
                        download_result.error_message = f"PDF content mismatch: {warning_msg}"
                        download_result.file_path = None
                    except Exception as e:
                        logger.error(f"Failed to delete mismatched PDF: {e}")

        except ImportError:
            logger.warning("PDF verifier not available - skipping verification")
            if progress_callback:
                progress_callback("verification", "skipped")

        except Exception as e:
            logger.error(f"PDF verification error: {e}")
            download_result.verification_warnings = [f"Verification error: {e}"]
            if progress_callback:
                progress_callback("verification", "error")

        return download_result

    def _download_pmc_package(
        self,
        source: PDFSource,
        pdf_output_path: Path,
        fulltext_output_dir: Optional[Path] = None
    ) -> DownloadResult:
        """Download and extract PMC tar.gz package.

        Extracts both PDF and NXML full-text from the package.

        Args:
            source: PDFSource with PMC_PACKAGE type
            pdf_output_path: Path to save extracted PDF
            fulltext_output_dir: Directory to save NXML (optional)

        Returns:
            DownloadResult with PDF path and full-text content
        """
        # Determine output directories
        pdf_output_dir = pdf_output_path.parent
        base_filename = pdf_output_path.stem

        # Default fulltext directory: sibling to pdf directory
        if fulltext_output_dir is None:
            # e.g., ~/knowledgebase/pdf/2024 -> ~/knowledgebase/fulltext/2024
            base_dir = pdf_output_dir.parent
            year_dir = pdf_output_dir.name
            fulltext_output_dir = base_dir.parent / 'fulltext' / year_dir

        return self._pmc_package_downloader.download_and_extract(
            source=source,
            pdf_output_dir=pdf_output_dir,
            fulltext_output_dir=fulltext_output_dir,
            base_filename=base_filename
        )

    def _is_duplicate_source(
        self,
        source: PDFSource,
        existing: List[PDFSource]
    ) -> bool:
        """Check if source URL already exists in list."""
        return any(s.url == source.url for s in existing)

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "FullTextFinder":
        """Create FullTextFinder from configuration dictionary.

        Args:
            config: Configuration dictionary with keys:
                - unpaywall_email: Email for Unpaywall API
                - openathens.institution_url: OpenAthens proxy URL
                - openathens.enabled: Whether to enable OpenAthens
                - discovery.timeout: Request timeout
                - discovery.prefer_open_access: Prefer OA sources
                - discovery.skip_resolvers: List of resolvers to skip
                - discovery.use_browser_fallback: Use browser for protected PDFs
                - discovery.browser_headless: Run browser in headless mode
                - discovery.browser_timeout: Browser timeout in ms

        Returns:
            Configured FullTextFinder instance
        """
        discovery_config = config.get('discovery', {})
        openathens_config = config.get('openathens', {})

        openathens_url = None
        if openathens_config.get('enabled', False):
            openathens_url = openathens_config.get('institution_url')

        instance = cls(
            unpaywall_email=config.get('unpaywall_email'),
            openathens_proxy_url=openathens_url,
            timeout=discovery_config.get('timeout', DEFAULT_TIMEOUT),
            prefer_open_access=discovery_config.get('prefer_open_access', True),
            skip_resolvers=discovery_config.get('skip_resolvers')
        )

        # Store browser fallback settings for use in discover_and_download
        instance._browser_fallback_config = {
            'enabled': discovery_config.get('use_browser_fallback', True),
            'headless': discovery_config.get('browser_headless', DEFAULT_BROWSER_HEADLESS),
            'timeout': discovery_config.get('browser_timeout', DEFAULT_BROWSER_TIMEOUT_MS)
        }

        return instance

    def download_for_document(
        self,
        document: Dict[str, Any],
        output_dir: Optional[Path] = None,
        use_browser_fallback: Optional[bool] = None,
        progress_callback: Optional[Callable[[str, str], None]] = None,
        verify_content: bool = False,
        delete_on_mismatch: bool = False
    ) -> DownloadResult:
        """Download PDF for a document using discovery + direct download + browser fallback.

        This is a convenience method for the common use case of downloading a PDF
        for a document that has identifiers (DOI, PMID, etc.) stored in a dictionary.

        Args:
            document: Document dictionary with keys:
                - doi: DOI string (optional)
                - pmid: PubMed ID (optional)
                - pmcid: PubMed Central ID (optional)
                - title: Document title (optional)
                - pdf_url: Direct PDF URL (optional)
                - id: Document ID for filename generation (optional)
                - publication_date: For year-based storage (optional)
            output_dir: Directory to save PDF. If None, uses current directory.
            use_browser_fallback: Override browser fallback setting (None uses config)
            progress_callback: Optional callback(stage, status)
            verify_content: If True, verify downloaded PDF matches expected DOI/title
            delete_on_mismatch: If True and verify_content=True, delete mismatched PDFs

        Returns:
            DownloadResult with download status, file path, and verification results
        """
        # Extract identifiers from document
        identifiers = DocumentIdentifiers(
            doc_id=document.get('id'),
            doi=document.get('doi'),
            pmid=str(document.get('pmid')) if document.get('pmid') else None,
            pmcid=document.get('pmcid'),
            title=document.get('title'),
            pdf_url=document.get('pdf_url')
        )

        if not identifiers.has_identifiers():
            return DownloadResult(
                success=False,
                error_message="Document has no usable identifiers (DOI, PMID, PMCID, or pdf_url)"
            )

        # Generate output path
        output_path = self._generate_output_path(document, output_dir)

        # Determine browser fallback settings
        browser_config = getattr(self, '_browser_fallback_config', {
            'enabled': True,
            'headless': DEFAULT_BROWSER_HEADLESS,
            'timeout': DEFAULT_BROWSER_TIMEOUT_MS
        })

        if use_browser_fallback is None:
            use_browser_fallback = browser_config.get('enabled', True)

        return self.discover_and_download(
            identifiers=identifiers,
            output_path=output_path,
            use_browser_fallback=use_browser_fallback,
            browser_headless=browser_config.get('headless', DEFAULT_BROWSER_HEADLESS),
            browser_timeout=browser_config.get('timeout', DEFAULT_BROWSER_TIMEOUT_MS),
            progress_callback=progress_callback,
            verify_content=verify_content,
            delete_on_mismatch=delete_on_mismatch
        )

    def _generate_output_path(
        self,
        document: Dict[str, Any],
        output_dir: Optional[Path] = None
    ) -> Path:
        """Generate output path for a document PDF.

        Uses DOI-based naming if available, falls back to document ID.
        Organizes by year if publication_date is available.

        Args:
            document: Document dictionary
            output_dir: Base output directory (default: current directory)

        Returns:
            Path for the PDF file
        """
        if output_dir is None:
            output_dir = Path.cwd()
        output_dir = Path(output_dir)

        # Extract year for subdirectory
        year = self._extract_year(document)
        if year:
            output_dir = output_dir / str(year)
        else:
            output_dir = output_dir / 'unknown'

        output_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename
        doi = document.get('doi')
        if doi:
            # DOI-based filename (replace slashes)
            safe_doi = doi.replace('/', '_').replace('\\', '_')
            filename = f"{safe_doi}.pdf"
        else:
            # Document ID-based filename
            doc_id = document.get('id', 'unknown')
            filename = f"doc_{doc_id}.pdf"

        return output_dir / filename

    def _extract_year(self, document: Dict[str, Any]) -> Optional[int]:
        """Extract publication year from document.

        Checks field names in priority order:
        1. publication_date (datetime or string like "2011-01-15" or "2011")
        2. year (int or string)

        Args:
            document: Document dictionary

        Returns:
            Year as integer, or None if not found
        """
        from datetime import datetime

        # Check publication_date first (handles datetime, date, and string formats)
        pub_date = document.get('publication_date')
        if pub_date:
            if isinstance(pub_date, datetime):
                return pub_date.year
            elif hasattr(pub_date, 'year'):  # date object
                return pub_date.year
            elif isinstance(pub_date, str):
                try:
                    if '-' in pub_date:
                        return int(pub_date.split('-')[0])
                    elif len(pub_date) >= 4:
                        return int(pub_date[:4])
                except (ValueError, IndexError):
                    pass

        # Check year (int or string)
        year = document.get('year')
        if year:
            if isinstance(year, int):
                return year
            elif isinstance(year, str):
                try:
                    return int(year[:4]) if len(year) >= 4 else int(year)
                except (ValueError, IndexError):
                    pass

        return None


def discover_full_text(
    doi: Optional[str] = None,
    pmid: Optional[str] = None,
    pmcid: Optional[str] = None,
    title: Optional[str] = None,
    pdf_url: Optional[str] = None,
    unpaywall_email: Optional[str] = None
) -> DiscoveryResult:
    """Convenience function to discover PDF sources.

    Args:
        doi: Document DOI
        pmid: PubMed ID
        pmcid: PubMed Central ID
        title: Document title
        pdf_url: Direct PDF URL
        unpaywall_email: Email for Unpaywall API

    Returns:
        DiscoveryResult with found sources
    """
    identifiers = DocumentIdentifiers(
        doi=doi,
        pmid=pmid,
        pmcid=pmcid,
        title=title,
        pdf_url=pdf_url
    )

    finder = FullTextFinder(unpaywall_email=unpaywall_email)
    return finder.discover(identifiers)


def download_pdf_for_document(
    document: Dict[str, Any],
    output_dir: Optional[Path] = None,
    unpaywall_email: Optional[str] = None,
    openathens_proxy_url: Optional[str] = None,
    use_browser_fallback: bool = True,
    browser_headless: bool = DEFAULT_BROWSER_HEADLESS,
    browser_timeout: int = DEFAULT_BROWSER_TIMEOUT_MS,
    progress_callback: Optional[Callable[[str, str], None]] = None,
    verify_content: bool = True,
    delete_on_mismatch: bool = False
) -> DownloadResult:
    """Convenience function to download PDF for a document.

    This is the main entry point for downloading PDFs from document dictionaries.
    It uses the full discovery + HTTP download + browser fallback workflow.

    Workflow:
    1. Discovers available PDF sources (PMC, Unpaywall, DOI, direct URL)
    2. Tries direct HTTP download from each source in priority order
    3. If all HTTP attempts fail, uses browser-based download as fallback
    4. Verifies downloaded PDF matches expected document metadata (if verify_content=True)

    Args:
        document: Document dictionary with keys:
            - doi: DOI string (optional but recommended)
            - pmid: PubMed ID (optional)
            - pmcid: PubMed Central ID (optional)
            - title: Document title (for verification)
            - pdf_url: Direct PDF URL (optional)
            - id: Document ID for filename generation (optional)
            - publication_date: For year-based storage (optional)
        output_dir: Directory to save PDF. If None, uses current directory.
        unpaywall_email: Email for Unpaywall API requests
        openathens_proxy_url: OpenAthens proxy URL for institutional access
        use_browser_fallback: If True, use browser when HTTP fails (default True)
        browser_headless: Run browser in headless mode (default True)
        browser_timeout: Browser operation timeout in ms (default 60000)
        progress_callback: Optional callback(stage, status) for progress updates
            Stages: 'discovery', 'download', 'browser_download', 'verification'
            Statuses: 'starting', 'found', 'not_found', 'success', 'failed', 'mismatch'
        verify_content: Verify downloaded PDF matches document metadata (default True)
        delete_on_mismatch: Delete PDF if verification fails (default False)

    Returns:
        DownloadResult with:
            - success: True if download succeeded
            - source: PDFSource that worked (if successful)
            - file_path: Path to downloaded file (if successful)
            - file_size: Size in bytes (if successful)
            - error_message: Error description (if failed)
            - duration_ms: Total time taken
            - verified: True if verified, False if mismatch, None if not checked
            - verification_match_type: 'doi', 'pmid', 'title' or mismatch type
            - verification_warnings: List of warnings from verification

    Example:
        from bmlibrarian.discovery import download_pdf_for_document
        from pathlib import Path

        document = {
            'doi': '10.1038/nature12373',
            'id': 12345,
            'title': 'Example Paper Title',
            'publication_date': '2024-01-15'
        }

        result = download_pdf_for_document(
            document=document,
            output_dir=Path('~/pdfs').expanduser(),
            unpaywall_email='user@example.com',
            verify_content=True
        )

        if result.success:
            if result.verified is False:
                print(f"WARNING: Downloaded wrong PDF! {result.verification_warnings}")
            print(f"Downloaded to: {result.file_path}")
        else:
            print(f"Failed: {result.error_message}")
    """
    finder = FullTextFinder(
        unpaywall_email=unpaywall_email,
        openathens_proxy_url=openathens_proxy_url
    )

    # Set browser fallback config
    finder._browser_fallback_config = {
        'enabled': use_browser_fallback,
        'headless': browser_headless,
        'timeout': browser_timeout
    }

    return finder.download_for_document(
        document=document,
        output_dir=output_dir,
        use_browser_fallback=use_browser_fallback,
        progress_callback=progress_callback,
        verify_content=verify_content,
        delete_on_mismatch=delete_on_mismatch
    )
