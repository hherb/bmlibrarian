"""PDF source resolvers for full-text discovery.

Implements various strategies for finding PDF URLs from document identifiers.
"""

import logging
import re
import time
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse, quote

import requests

from .data_types import (
    PDFSource, ResolutionResult, ResolutionStatus,
    SourceType, AccessType, DocumentIdentifiers
)

logger = logging.getLogger(__name__)

# Default timeout for HTTP requests (seconds)
DEFAULT_TIMEOUT = 30

# User agent for requests
USER_AGENT = (
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/131.0.0.0 Safari/537.36'
)


class BaseResolver(ABC):
    """Abstract base class for PDF source resolvers."""

    def __init__(self, timeout: int = DEFAULT_TIMEOUT):
        """Initialize resolver.

        Args:
            timeout: HTTP request timeout in seconds
        """
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': USER_AGENT,
            'Accept': 'application/json, text/html, application/pdf, */*'
        })

    @property
    @abstractmethod
    def name(self) -> str:
        """Resolver name for logging and identification."""
        pass

    @abstractmethod
    def resolve(self, identifiers: DocumentIdentifiers) -> ResolutionResult:
        """Resolve document identifiers to PDF sources.

        Args:
            identifiers: Document identifiers (DOI, PMID, etc.)

        Returns:
            ResolutionResult with found sources
        """
        pass

    def _create_result(
        self,
        status: ResolutionStatus,
        sources: Optional[List[PDFSource]] = None,
        error_message: Optional[str] = None,
        duration_ms: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ResolutionResult:
        """Helper to create ResolutionResult."""
        return ResolutionResult(
            resolver_name=self.name,
            status=status,
            sources=sources or [],
            error_message=error_message,
            duration_ms=duration_ms,
            metadata=metadata or {}
        )


class DirectURLResolver(BaseResolver):
    """Resolver that uses existing PDF URL from database."""

    @property
    def name(self) -> str:
        return "direct_url"

    def resolve(self, identifiers: DocumentIdentifiers) -> ResolutionResult:
        """Check if document has a direct PDF URL."""
        start_time = time.time()

        if not identifiers.pdf_url:
            return self._create_result(
                ResolutionStatus.NOT_FOUND,
                duration_ms=(time.time() - start_time) * 1000
            )

        # Validate URL format
        try:
            parsed = urlparse(identifiers.pdf_url)
            if not parsed.scheme or not parsed.netloc:
                return self._create_result(
                    ResolutionStatus.ERROR,
                    error_message=f"Invalid URL format: {identifiers.pdf_url}",
                    duration_ms=(time.time() - start_time) * 1000
                )
        except Exception as e:
            return self._create_result(
                ResolutionStatus.ERROR,
                error_message=str(e),
                duration_ms=(time.time() - start_time) * 1000
            )

        # Create source - assume open access if URL exists
        source = PDFSource(
            url=identifiers.pdf_url,
            source_type=SourceType.DIRECT_URL,
            access_type=AccessType.UNKNOWN,  # Will be determined during download
            priority=10  # Medium priority - prefer verified OA sources
        )

        return self._create_result(
            ResolutionStatus.SUCCESS,
            sources=[source],
            duration_ms=(time.time() - start_time) * 1000
        )


class DOIResolver(BaseResolver):
    """Resolver that finds PDFs via DOI resolution."""

    DOI_API_URL = "https://doi.org"
    CROSSREF_API_URL = "https://api.crossref.org/works"

    @property
    def name(self) -> str:
        return "doi"

    def resolve(self, identifiers: DocumentIdentifiers) -> ResolutionResult:
        """Resolve DOI to find PDF URL."""
        start_time = time.time()

        if not identifiers.doi:
            return self._create_result(
                ResolutionStatus.SKIPPED,
                duration_ms=(time.time() - start_time) * 1000
            )

        doi = self._normalize_doi(identifiers.doi)
        sources = []

        # Try CrossRef API first (provides structured metadata)
        crossref_sources = self._resolve_via_crossref(doi)
        sources.extend(crossref_sources)

        # Try DOI.org content negotiation
        doi_sources = self._resolve_via_doi_org(doi)
        sources.extend(doi_sources)

        if not sources:
            return self._create_result(
                ResolutionStatus.NOT_FOUND,
                duration_ms=(time.time() - start_time) * 1000,
                metadata={'doi': doi}
            )

        return self._create_result(
            ResolutionStatus.SUCCESS,
            sources=sources,
            duration_ms=(time.time() - start_time) * 1000,
            metadata={'doi': doi}
        )

    def _normalize_doi(self, doi: str) -> str:
        """Normalize DOI format."""
        # Remove common prefixes
        doi = doi.strip()
        for prefix in ['https://doi.org/', 'http://doi.org/', 'doi:', 'DOI:']:
            if doi.lower().startswith(prefix.lower()):
                doi = doi[len(prefix):]
        return doi.strip()

    def _resolve_via_crossref(self, doi: str) -> List[PDFSource]:
        """Query CrossRef API for PDF links."""
        sources = []

        try:
            url = f"{self.CROSSREF_API_URL}/{quote(doi, safe='')}"
            response = self.session.get(url, timeout=self.timeout)

            if response.status_code == 200:
                data = response.json()
                message = data.get('message', {})

                # Check for PDF links
                links = message.get('link', [])
                for link in links:
                    content_type = link.get('content-type', '')
                    link_url = link.get('URL', '')

                    if 'pdf' in content_type.lower() and link_url:
                        sources.append(PDFSource(
                            url=link_url,
                            source_type=SourceType.DOI_REDIRECT,
                            access_type=AccessType.UNKNOWN,
                            priority=20,
                            version=link.get('content-version'),
                            metadata={'crossref_type': content_type}
                        ))

                # Check for license (indicates OA)
                licenses = message.get('license', [])
                for lic in licenses:
                    lic_url = lic.get('URL', '')
                    if 'creativecommons' in lic_url.lower():
                        # Mark sources as open access
                        for source in sources:
                            source.access_type = AccessType.OPEN
                            source.license = lic_url

        except requests.RequestException as e:
            logger.debug(f"CrossRef API error for DOI {doi}: {e}")
        except Exception as e:
            logger.warning(f"Error parsing CrossRef response for DOI {doi}: {e}")

        return sources

    def _resolve_via_doi_org(self, doi: str) -> List[PDFSource]:
        """Resolve DOI via doi.org to find landing page/PDF."""
        sources = []

        try:
            # Request with content negotiation for application/pdf
            headers = {'Accept': 'application/pdf'}
            url = f"{self.DOI_API_URL}/{quote(doi, safe='')}"

            response = self.session.head(
                url,
                headers=headers,
                timeout=self.timeout,
                allow_redirects=True
            )

            # Check if we got redirected to a PDF
            final_url = response.url
            content_type = response.headers.get('content-type', '').lower()

            if 'pdf' in content_type or final_url.endswith('.pdf'):
                sources.append(PDFSource(
                    url=final_url,
                    source_type=SourceType.DOI_REDIRECT,
                    access_type=AccessType.UNKNOWN,
                    priority=15,
                    metadata={'resolved_from': 'doi.org'}
                ))

        except requests.RequestException as e:
            logger.debug(f"DOI.org resolution error for {doi}: {e}")

        return sources


class PMCResolver(BaseResolver):
    """Resolver for PubMed Central open access PDFs."""

    PMC_API_URL = "https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi"
    PMC_ARTICLE_BASE = "https://pmc.ncbi.nlm.nih.gov/articles"
    EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    @property
    def name(self) -> str:
        return "pmc"

    def resolve(self, identifiers: DocumentIdentifiers) -> ResolutionResult:
        """Resolve via PubMed Central."""
        start_time = time.time()

        # Try PMCID first, then PMID, then DOI
        pmcid = identifiers.pmcid
        pmid = identifiers.pmid
        doi = identifiers.doi

        sources = []

        # If we have PMCID, use it directly
        if pmcid:
            sources.extend(self._resolve_by_pmcid(pmcid))

        # If we have PMID but no PMCID, try to find PMCID
        if not pmcid and pmid:
            pmcid = self._pmid_to_pmcid(pmid)
            if pmcid:
                sources.extend(self._resolve_by_pmcid(pmcid))

        # Try DOI lookup in PMC
        if not sources and doi:
            pmcid = self._doi_to_pmcid(doi)
            if pmcid:
                sources.extend(self._resolve_by_pmcid(pmcid))

        if not sources:
            return self._create_result(
                ResolutionStatus.NOT_FOUND,
                duration_ms=(time.time() - start_time) * 1000
            )

        return self._create_result(
            ResolutionStatus.SUCCESS,
            sources=sources,
            duration_ms=(time.time() - start_time) * 1000,
            metadata={'pmcid': pmcid}
        )

    def _normalize_pmcid(self, pmcid: str) -> str:
        """Normalize PMCID format."""
        pmcid = pmcid.strip().upper()
        if not pmcid.startswith('PMC'):
            pmcid = f'PMC{pmcid}'
        return pmcid

    def _resolve_by_pmcid(self, pmcid: str) -> List[PDFSource]:
        """Get PDF URL for a PMCID."""
        pmcid = self._normalize_pmcid(pmcid)
        sources = []

        # Try OA web service first (returns FTP URLs for .tar.gz or PDF)
        try:
            params = {'id': pmcid}
            response = self.session.get(
                self.PMC_API_URL,
                params=params,
                timeout=self.timeout
            )

            if response.status_code == 200:
                # Parse XML response
                import xml.etree.ElementTree as ET
                root = ET.fromstring(response.content)

                for record in root.findall('.//record'):
                    # Check for PDF link (some articles have direct PDF FTP links)
                    for link in record.findall('.//link'):
                        if link.get('format') == 'pdf':
                            pdf_url = link.get('href')
                            if pdf_url:
                                sources.append(PDFSource(
                                    url=pdf_url,
                                    source_type=SourceType.PMC,
                                    access_type=AccessType.OPEN,
                                    priority=5,  # High priority - verified OA
                                    is_best_oa=True,
                                    host_type='repository',
                                    metadata={'pmcid': pmcid}
                                ))

        except Exception as e:
            logger.debug(f"PMC OA service error for {pmcid}: {e}")

        # Fallback: fetch the article page to extract the actual PDF filename
        if not sources:
            pdf_url = self._get_pdf_url_from_article_page(pmcid)
            if pdf_url:
                sources.append(PDFSource(
                    url=pdf_url,
                    source_type=SourceType.PMC,
                    access_type=AccessType.OPEN,
                    priority=6,
                    host_type='repository',
                    metadata={'pmcid': pmcid, 'extracted': True}
                ))

        return sources

    def _get_pdf_url_from_article_page(self, pmcid: str) -> Optional[str]:
        """Fetch the PMC article page and extract the actual PDF URL.

        PMC article pages contain the PDF filename in href attributes.
        The PDF is linked as 'pdf/<filename>.pdf' relative to the article URL.

        Note: NCBI's new pmc.ncbi.nlm.nih.gov domain uses bot detection that
        blocks Python's requests library but allows curl. We use curl as a
        fallback when requests fails.

        Args:
            pmcid: Normalized PMCID (e.g., 'PMC11052067')

        Returns:
            Full PDF URL if found, None otherwise
        """
        article_url = f"{self.PMC_ARTICLE_BASE}/{pmcid}/"

        # First try with requests (works for some PMC articles)
        try:
            response = self.session.get(article_url, timeout=self.timeout)

            if response.status_code == 200:
                content = response.text
                pdf_url = self._extract_pdf_link_from_html(content, pmcid)
                if pdf_url:
                    return pdf_url

            # If requests fails (403), fall back to curl
            if response.status_code == 403:
                logger.debug(f"Requests blocked for {pmcid}, trying curl fallback")
                return self._get_pdf_url_via_curl(article_url, pmcid)

            logger.debug(f"Could not find PDF link on article page for {pmcid}")

        except requests.RequestException as e:
            logger.debug(f"Error fetching article page for {pmcid}: {e}")
            # Try curl fallback on connection errors too
            return self._get_pdf_url_via_curl(article_url, pmcid)

        return None

    def _extract_pdf_link_from_html(self, content: str, pmcid: str) -> Optional[str]:
        """Extract PDF link from HTML content.

        Args:
            content: HTML content of the article page
            pmcid: Normalized PMCID

        Returns:
            Full PDF URL if found, None otherwise
        """
        # Look for PDF link in the HTML
        # Pattern: href="pdf/<filename>.pdf"
        pdf_pattern = re.compile(r'href="(pdf/[^"]+\.pdf)"', re.IGNORECASE)
        match = pdf_pattern.search(content)

        if match:
            relative_pdf_path = match.group(1)
            full_pdf_url = f"{self.PMC_ARTICLE_BASE}/{pmcid}/{relative_pdf_path}"
            logger.debug(f"Extracted PDF URL from article page: {full_pdf_url}")
            return full_pdf_url

        return None

    def _get_pdf_url_via_curl(self, article_url: str, pmcid: str) -> Optional[str]:
        """Fetch article page via curl to bypass bot detection.

        NCBI's pmc.ncbi.nlm.nih.gov uses bot detection that blocks Python's
        requests library but allows curl. This method uses curl as a fallback.

        Args:
            article_url: Full URL to the article page
            pmcid: Normalized PMCID

        Returns:
            Full PDF URL if found, None otherwise
        """
        import subprocess

        try:
            result = subprocess.run(
                [
                    'curl', '-s',
                    '-H', f'User-Agent: {USER_AGENT}',
                    '-H', 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    '--max-time', str(self.timeout),
                    article_url
                ],
                capture_output=True,
                text=True,
                timeout=self.timeout + 5
            )

            if result.returncode == 0 and result.stdout:
                pdf_url = self._extract_pdf_link_from_html(result.stdout, pmcid)
                if pdf_url:
                    logger.debug(f"Extracted PDF URL via curl: {pdf_url}")
                    return pdf_url

        except subprocess.TimeoutExpired:
            logger.debug(f"Curl timeout for {pmcid}")
        except FileNotFoundError:
            logger.debug("Curl not available, cannot fetch article page")
        except Exception as e:
            logger.debug(f"Curl error for {pmcid}: {e}")

        return None

    def _pmid_to_pmcid(self, pmid: str) -> Optional[str]:
        """Convert PMID to PMCID using ID converter."""
        try:
            url = f"{self.EUTILS_BASE}/elink.fcgi"
            params = {
                'dbfrom': 'pubmed',
                'db': 'pmc',
                'id': pmid,
                'retmode': 'json'
            }

            response = self.session.get(url, params=params, timeout=self.timeout)
            if response.status_code == 200:
                data = response.json()
                linksets = data.get('linksets', [])
                for linkset in linksets:
                    for linksetdb in linkset.get('linksetdbs', []):
                        if linksetdb.get('dbto') == 'pmc':
                            links = linksetdb.get('links', [])
                            if links:
                                return f"PMC{links[0]}"

        except Exception as e:
            logger.debug(f"PMID to PMCID conversion error: {e}")

        return None

    def _doi_to_pmcid(self, doi: str) -> Optional[str]:
        """Find PMCID for a DOI via PubMed search."""
        try:
            # Search PubMed for the DOI
            url = f"{self.EUTILS_BASE}/esearch.fcgi"
            params = {
                'db': 'pubmed',
                'term': f'{doi}[doi]',
                'retmode': 'json'
            }

            response = self.session.get(url, params=params, timeout=self.timeout)
            if response.status_code == 200:
                data = response.json()
                id_list = data.get('esearchresult', {}).get('idlist', [])
                if id_list:
                    pmid = id_list[0]
                    return self._pmid_to_pmcid(pmid)

        except Exception as e:
            logger.debug(f"DOI to PMCID conversion error: {e}")

        return None


class UnpaywallResolver(BaseResolver):
    """Resolver using Unpaywall API for open access versions."""

    API_URL = "https://api.unpaywall.org/v2"

    def __init__(self, email: str, timeout: int = DEFAULT_TIMEOUT):
        """Initialize Unpaywall resolver.

        Args:
            email: Email address for Unpaywall API (required)
            timeout: HTTP request timeout
        """
        super().__init__(timeout)
        self.email = email

    @property
    def name(self) -> str:
        return "unpaywall"

    def resolve(self, identifiers: DocumentIdentifiers) -> ResolutionResult:
        """Query Unpaywall for open access PDF."""
        start_time = time.time()

        if not identifiers.doi:
            return self._create_result(
                ResolutionStatus.SKIPPED,
                duration_ms=(time.time() - start_time) * 1000
            )

        doi = identifiers.doi.strip()
        # Remove common prefixes
        for prefix in ['https://doi.org/', 'http://doi.org/', 'doi:']:
            if doi.lower().startswith(prefix.lower()):
                doi = doi[len(prefix):]

        try:
            url = f"{self.API_URL}/{quote(doi, safe='')}"
            params = {'email': self.email}

            response = self.session.get(url, params=params, timeout=self.timeout)

            if response.status_code == 404:
                return self._create_result(
                    ResolutionStatus.NOT_FOUND,
                    duration_ms=(time.time() - start_time) * 1000
                )

            if response.status_code != 200:
                return self._create_result(
                    ResolutionStatus.ERROR,
                    error_message=f"API error: {response.status_code}",
                    duration_ms=(time.time() - start_time) * 1000
                )

            data = response.json()
            sources = self._parse_unpaywall_response(data)

            if not sources:
                return self._create_result(
                    ResolutionStatus.NOT_FOUND,
                    duration_ms=(time.time() - start_time) * 1000,
                    metadata={'is_oa': data.get('is_oa', False)}
                )

            return self._create_result(
                ResolutionStatus.SUCCESS,
                sources=sources,
                duration_ms=(time.time() - start_time) * 1000,
                metadata={
                    'is_oa': data.get('is_oa', False),
                    'oa_status': data.get('oa_status')
                }
            )

        except requests.RequestException as e:
            return self._create_result(
                ResolutionStatus.ERROR,
                error_message=str(e),
                duration_ms=(time.time() - start_time) * 1000
            )

    def _parse_unpaywall_response(self, data: Dict[str, Any]) -> List[PDFSource]:
        """Parse Unpaywall API response into PDFSource objects."""
        sources = []

        # Check best OA location first
        best_oa = data.get('best_oa_location')
        if best_oa and best_oa.get('url_for_pdf'):
            sources.append(self._location_to_source(best_oa, is_best=True, priority=1))

        # Add other OA locations
        oa_locations = data.get('oa_locations', [])
        for i, location in enumerate(oa_locations):
            if location.get('url_for_pdf'):
                # Skip if same as best_oa
                if best_oa and location.get('url_for_pdf') == best_oa.get('url_for_pdf'):
                    continue
                sources.append(self._location_to_source(location, is_best=False, priority=2 + i))

        return sources

    def _location_to_source(
        self,
        location: Dict[str, Any],
        is_best: bool,
        priority: int
    ) -> PDFSource:
        """Convert Unpaywall location to PDFSource."""
        return PDFSource(
            url=location['url_for_pdf'],
            source_type=SourceType.UNPAYWALL,
            access_type=AccessType.OPEN,
            priority=priority,
            license=location.get('license'),
            version=location.get('version'),
            is_best_oa=is_best,
            host_type=location.get('host_type'),
            metadata={
                'evidence': location.get('evidence'),
                'pmh_id': location.get('pmh_id'),
                'repository_institution': location.get('repository_institution')
            }
        )


class OpenAthensResolver(BaseResolver):
    """Resolver that constructs OpenAthens proxy URLs for institutional access."""

    def __init__(
        self,
        proxy_base_url: str,
        timeout: int = DEFAULT_TIMEOUT
    ):
        """Initialize OpenAthens resolver.

        Args:
            proxy_base_url: Base URL for OpenAthens proxy (e.g., "https://proxy.openathens.net")
            timeout: HTTP request timeout
        """
        super().__init__(timeout)
        self.proxy_base_url = proxy_base_url.rstrip('/')

    @property
    def name(self) -> str:
        return "openathens"

    def resolve(self, identifiers: DocumentIdentifiers) -> ResolutionResult:
        """Generate OpenAthens proxy URL for document."""
        start_time = time.time()

        # Need either DOI or direct PDF URL
        target_url = None

        if identifiers.pdf_url:
            target_url = identifiers.pdf_url
        elif identifiers.doi:
            # Construct DOI URL
            doi = identifiers.doi.strip()
            for prefix in ['https://doi.org/', 'http://doi.org/', 'doi:']:
                if doi.lower().startswith(prefix.lower()):
                    doi = doi[len(prefix):]
            target_url = f"https://doi.org/{doi}"

        if not target_url:
            return self._create_result(
                ResolutionStatus.SKIPPED,
                duration_ms=(time.time() - start_time) * 1000
            )

        # Construct proxy URL
        proxy_url = self._construct_proxy_url(target_url)

        source = PDFSource(
            url=proxy_url,
            source_type=SourceType.OPENATHENS,
            access_type=AccessType.INSTITUTIONAL,
            priority=50,  # Lower priority than OA sources
            metadata={
                'original_url': target_url,
                'proxy_base': self.proxy_base_url
            }
        )

        return self._create_result(
            ResolutionStatus.SUCCESS,
            sources=[source],
            duration_ms=(time.time() - start_time) * 1000
        )

    def _construct_proxy_url(self, target_url: str) -> str:
        """Construct OpenAthens proxy URL.

        Args:
            target_url: Original URL to proxy

        Returns:
            Proxied URL
        """
        # Standard OpenAthens proxy format
        # Some institutions use: proxy.example.com/login?url=<target>
        # Others use: <target-domain>.proxy.example.com
        # We'll use the login redirect format which is more universal
        encoded_url = quote(target_url, safe='')
        return f"{self.proxy_base_url}/login?url={encoded_url}"
