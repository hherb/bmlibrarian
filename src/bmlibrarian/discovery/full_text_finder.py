"""Full-text discovery orchestrator.

Coordinates multiple resolvers to find and download PDF full-text
for documents, prioritizing open access sources.
"""

import logging
import time
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable

import requests

from .data_types import (
    PDFSource, DiscoveryResult, DownloadResult, DocumentIdentifiers,
    ResolutionStatus, SourceType, AccessType
)
from .resolvers import (
    BaseResolver, DirectURLResolver, DOIResolver,
    PMCResolver, UnpaywallResolver, OpenAthensResolver
)

logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_TIMEOUT = 30
DEFAULT_UNPAYWALL_EMAIL = "bmlibrarian@example.com"


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
        max_attempts: int = 3,
        progress_callback: Optional[Callable[[str, str], None]] = None
    ) -> DownloadResult:
        """Discover PDF sources and download the best one.

        Args:
            identifiers: Document identifiers
            output_path: Path to save PDF file
            max_attempts: Maximum download attempts per source
            progress_callback: Optional callback(stage, status)

        Returns:
            DownloadResult with download status
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

        # Try downloading from each source in priority order
        if progress_callback:
            progress_callback("download", "starting")

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
                return result

            logger.debug(f"Download failed from {source.source_type.value}: {result.error_message}")

        # All sources failed
        if progress_callback:
            progress_callback("download", "failed")

        return DownloadResult(
            success=False,
            error_message=f"All {len(discovery.sources)} sources failed",
            duration_ms=(time.time() - start_time) * 1000,
            attempts=len(discovery.sources)
        )

    def _download_from_source(
        self,
        source: PDFSource,
        output_path: Path,
        max_attempts: int
    ) -> DownloadResult:
        """Download PDF from a specific source.

        Args:
            source: PDFSource to download from
            output_path: Path to save file
            max_attempts: Maximum retry attempts

        Returns:
            DownloadResult
        """
        start_time = time.time()

        # Prepare headers and cookies
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

        Returns:
            Configured FullTextFinder instance
        """
        discovery_config = config.get('discovery', {})
        openathens_config = config.get('openathens', {})

        openathens_url = None
        if openathens_config.get('enabled', False):
            openathens_url = openathens_config.get('institution_url')

        return cls(
            unpaywall_email=config.get('unpaywall_email'),
            openathens_proxy_url=openathens_url,
            timeout=discovery_config.get('timeout', DEFAULT_TIMEOUT),
            prefer_open_access=discovery_config.get('prefer_open_access', True),
            skip_resolvers=discovery_config.get('skip_resolvers')
        )


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
