"""
PubMed E-utilities API client.

This module provides a client for searching PubMed via the NCBI E-utilities API,
with proper rate limiting, retry logic, and history server support for large
result sets.

Example usage:
    from bmlibrarian.pubmed_search import PubMedSearchClient, PubMedQuery

    client = PubMedSearchClient(email="user@example.com")

    # Search with a query object
    query = PubMedQuery(
        original_question="cardiovascular exercise",
        query_string='"Exercise"[MeSH] AND "Cardiovascular Diseases"[MeSH]'
    )
    result = client.search(query, max_results=100)

    print(f"Found {result.total_count} articles, retrieved {result.retrieved_count}")
"""

import logging
import os
import re
import time
import xml.etree.ElementTree as ET
from typing import Optional, List, Dict, Any, Callable, Generator
import requests

from .constants import (
    ESEARCH_URL,
    EFETCH_URL,
    REQUEST_TIMEOUT_SECONDS,
    MAX_RETRIES,
    INITIAL_RETRY_DELAY_SECONDS,
    RETRY_BACKOFF_MULTIPLIER,
    REQUEST_DELAY_WITH_KEY,
    REQUEST_DELAY_WITHOUT_KEY,
    DEFAULT_MAX_RESULTS,
    MAX_RESULTS_LIMIT,
    DEFAULT_BATCH_SIZE,
    HISTORY_SERVER_THRESHOLD,
    ENV_NCBI_EMAIL,
    ENV_NCBI_API_KEY,
    EMAIL_VALIDATION_PATTERN,
    URL_LENGTH_POST_THRESHOLD,
)
from .data_types import (
    PubMedQuery,
    SearchResult,
    ArticleMetadata,
)

logger = logging.getLogger(__name__)

# Compiled regex pattern for email validation
_EMAIL_PATTERN = re.compile(EMAIL_VALIDATION_PATTERN)


def validate_email(email: str) -> bool:
    """
    Validate email format for NCBI API requirements.

    NCBI requires a valid email address for identification purposes.
    This validates the basic email format.

    Args:
        email: Email address to validate

    Returns:
        True if email format is valid, False otherwise
    """
    if not email:
        return False
    return bool(_EMAIL_PATTERN.match(email))


class PubMedSearchClient:
    """
    Client for searching PubMed via E-utilities API.

    Provides methods for searching PubMed with structured queries,
    fetching article metadata, and handling large result sets using
    the NCBI history server.
    """

    def __init__(
        self,
        email: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: int = REQUEST_TIMEOUT_SECONDS,
        max_retries: int = MAX_RETRIES,
    ) -> None:
        """
        Initialize the PubMed search client.

        Args:
            email: Email for NCBI (recommended for identification)
            api_key: NCBI API key for higher rate limits (10/sec vs 3/sec)
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts for failed requests
        """
        self.email = email or os.environ.get(ENV_NCBI_EMAIL, "")
        self.api_key = api_key or os.environ.get(ENV_NCBI_API_KEY, "")
        self.timeout = timeout
        self.max_retries = max_retries

        # Validate email format if provided
        if self.email and not validate_email(self.email):
            logger.warning(
                f"Email '{self.email}' does not appear to be a valid email format. "
                "NCBI recommends providing a valid email for identification."
            )

        # Rate limiting based on API key presence
        self.request_delay = REQUEST_DELAY_WITH_KEY if self.api_key else REQUEST_DELAY_WITHOUT_KEY

        rate_desc = f"{1/self.request_delay:.1f} req/s" if self.request_delay > 0 else "unlimited"
        logger.info(f"PubMed search client initialized (rate limit: {rate_desc})")

    def _make_request(
        self,
        url: str,
        params: Dict[str, Any],
        method: str = "GET",
    ) -> Optional[requests.Response]:
        """
        Make an HTTP request with retry logic and rate limiting.

        Args:
            url: API endpoint URL
            params: Query parameters
            method: HTTP method (GET or POST)

        Returns:
            Response object or None if all retries failed
        """
        # Add authentication
        if self.email:
            params["email"] = self.email
        if self.api_key:
            params["api_key"] = self.api_key

        delay = INITIAL_RETRY_DELAY_SECONDS

        for attempt in range(self.max_retries):
            try:
                # Rate limiting
                time.sleep(self.request_delay)

                if method.upper() == "POST":
                    response = requests.post(url, data=params, timeout=self.timeout)
                else:
                    response = requests.get(url, params=params, timeout=self.timeout)

                response.raise_for_status()
                return response

            except requests.exceptions.Timeout:
                logger.warning(
                    f"PubMed API timeout (attempt {attempt + 1}/{self.max_retries})"
                )
                if attempt < self.max_retries - 1:
                    time.sleep(delay)
                    delay *= RETRY_BACKOFF_MULTIPLIER
                else:
                    logger.error(f"PubMed API request timed out after {self.max_retries} attempts")
                    return None

            except requests.exceptions.ConnectionError:
                logger.warning(
                    f"PubMed API connection error (attempt {attempt + 1}/{self.max_retries})"
                )
                if attempt < self.max_retries - 1:
                    time.sleep(delay)
                    delay *= RETRY_BACKOFF_MULTIPLIER
                else:
                    logger.error(f"PubMed API connection failed after {self.max_retries} attempts")
                    return None

            except requests.exceptions.HTTPError as e:
                if e.response is not None and e.response.status_code == 429:
                    logger.warning(
                        f"Rate limited by PubMed (attempt {attempt + 1}/{self.max_retries})"
                    )
                else:
                    status_code = e.response.status_code if e.response is not None else "unknown"
                    logger.warning(
                        f"PubMed API HTTP error {status_code} (attempt {attempt + 1}/{self.max_retries})"
                    )
                if attempt < self.max_retries - 1:
                    time.sleep(delay)
                    delay *= RETRY_BACKOFF_MULTIPLIER
                else:
                    logger.error(f"PubMed API HTTP error after {self.max_retries} attempts")
                    return None

            except requests.exceptions.RequestException as e:
                logger.warning(
                    f"PubMed API request failed (attempt {attempt + 1}/{self.max_retries}): {e}"
                )
                if attempt < self.max_retries - 1:
                    time.sleep(delay)
                    delay *= RETRY_BACKOFF_MULTIPLIER
                else:
                    logger.error(f"PubMed API request failed after {self.max_retries} attempts")
                    return None

        return None

    def search(
        self,
        query: PubMedQuery,
        max_results: int = DEFAULT_MAX_RESULTS,
        use_history: bool = True,
        sort: str = "relevance",
        progress_callback: Optional[Callable[[str, str], None]] = None,
    ) -> SearchResult:
        """
        Search PubMed with a structured query.

        Args:
            query: PubMedQuery object with search parameters
            max_results: Maximum number of results to retrieve
            use_history: Use history server for large result sets
            sort: Sort order ('relevance', 'pub_date', 'first_author')
            progress_callback: Optional callback(step, message) for progress updates

        Returns:
            SearchResult with PMIDs and metadata
        """
        def report_progress(step: str, message: str) -> None:
            logger.info(f"[{step}] {message}")
            if progress_callback:
                progress_callback(step, message)

        # Validate max_results
        max_results = min(max_results, MAX_RESULTS_LIMIT)

        report_progress("search", f"Searching PubMed: {query.query_string[:100]}...")

        start_time = time.time()

        # Build search parameters
        params = query.to_url_params()
        params["retmax"] = max_results
        params["sort"] = sort

        # Use history server for large result sets
        if use_history and max_results > HISTORY_SERVER_THRESHOLD:
            params["usehistory"] = "y"
            params["retmax"] = 0  # Just get count and WebEnv

        # Use POST for long queries to avoid HTTP 414 (URI Too Long) errors
        # Estimate URL length based on query string length
        query_length = len(query.query_string)
        method = "POST" if query_length > URL_LENGTH_POST_THRESHOLD else "GET"
        if method == "POST":
            logger.debug(f"Using POST method for long query ({query_length} chars)")

        response = self._make_request(ESEARCH_URL, params, method=method)

        if not response:
            return SearchResult(
                query=query,
                total_count=0,
                retrieved_count=0,
                search_time_seconds=time.time() - start_time,
            )

        try:
            data = response.json()
            result = data.get("esearchresult", {})

            total_count = int(result.get("count", 0))
            pmids = result.get("idlist", [])

            # Get history server info
            web_env = result.get("webenv")
            query_key = result.get("querykey")

            report_progress("results", f"Found {total_count} total results")

            # If using history server and we need more results
            if use_history and web_env and query_key and max_results > len(pmids):
                report_progress("fetch", "Fetching additional PMIDs from history server...")
                pmids = self._fetch_pmids_from_history(
                    web_env=web_env,
                    query_key=query_key,
                    total_count=min(total_count, max_results),
                    progress_callback=progress_callback,
                )

            search_time = time.time() - start_time
            report_progress("complete", f"Retrieved {len(pmids)} PMIDs in {search_time:.2f}s")

            return SearchResult(
                query=query,
                total_count=total_count,
                retrieved_count=len(pmids),
                pmids=pmids,
                search_time_seconds=search_time,
                web_env=web_env,
                query_key=query_key,
            )

        except Exception as e:
            logger.error(f"Error parsing search results: {e}")
            return SearchResult(
                query=query,
                total_count=0,
                retrieved_count=0,
                search_time_seconds=time.time() - start_time,
            )

    def _fetch_pmids_from_history(
        self,
        web_env: str,
        query_key: str,
        total_count: int,
        progress_callback: Optional[Callable[[str, str], None]] = None,
    ) -> List[str]:
        """
        Fetch PMIDs from history server in batches.

        Args:
            web_env: WebEnv from initial search
            query_key: QueryKey from initial search
            total_count: Total number of PMIDs to fetch
            progress_callback: Optional progress callback

        Returns:
            List of PMIDs
        """
        all_pmids = []
        batch_size = DEFAULT_BATCH_SIZE

        for start in range(0, total_count, batch_size):
            params = {
                "db": "pubmed",
                "WebEnv": web_env,
                "query_key": query_key,
                "retstart": start,
                "retmax": min(batch_size, total_count - start),
                "retmode": "json",
            }

            response = self._make_request(ESEARCH_URL, params)
            if not response:
                logger.warning(f"Failed to fetch PMIDs batch at offset {start}")
                break

            try:
                data = response.json()
                batch_pmids = data.get("esearchresult", {}).get("idlist", [])
                all_pmids.extend(batch_pmids)

                if progress_callback:
                    progress_callback("fetch", f"Retrieved {len(all_pmids)}/{total_count} PMIDs")

            except Exception as e:
                logger.error(f"Error parsing PMID batch: {e}")
                break

        return all_pmids

    def search_simple(
        self,
        query_string: str,
        max_results: int = DEFAULT_MAX_RESULTS,
    ) -> SearchResult:
        """
        Simple search with just a query string.

        Args:
            query_string: PubMed query string
            max_results: Maximum results to retrieve

        Returns:
            SearchResult with PMIDs
        """
        query = PubMedQuery(
            original_question=query_string,
            query_string=query_string,
        )
        return self.search(query, max_results=max_results)

    def get_count(self, query: PubMedQuery) -> int:
        """
        Get the count of results for a query without retrieving PMIDs.

        Args:
            query: PubMedQuery to count

        Returns:
            Number of matching articles
        """
        params = query.to_url_params()
        params["retmax"] = 0
        params["rettype"] = "count"

        # Use POST for long queries to avoid HTTP 414 (URI Too Long) errors
        query_length = len(query.query_string)
        method = "POST" if query_length > URL_LENGTH_POST_THRESHOLD else "GET"

        response = self._make_request(ESEARCH_URL, params, method=method)
        if not response:
            return 0

        try:
            data = response.json()
            return int(data.get("esearchresult", {}).get("count", 0))
        except Exception as e:
            logger.error(f"Error getting count: {e}")
            return 0

    def fetch_articles(
        self,
        pmids: List[str],
        batch_size: int = DEFAULT_BATCH_SIZE,
        progress_callback: Optional[Callable[[str, str], None]] = None,
    ) -> List[ArticleMetadata]:
        """
        Fetch article metadata for a list of PMIDs.

        Args:
            pmids: List of PubMed IDs
            batch_size: Number of articles per request
            progress_callback: Optional progress callback

        Returns:
            List of ArticleMetadata objects
        """
        if not pmids:
            return []

        def report_progress(step: str, message: str) -> None:
            logger.info(f"[{step}] {message}")
            if progress_callback:
                progress_callback(step, message)

        all_articles = []
        total_batches = (len(pmids) + batch_size - 1) // batch_size

        for batch_num, i in enumerate(range(0, len(pmids), batch_size), 1):
            batch = pmids[i:i + batch_size]
            report_progress("fetch", f"Fetching batch {batch_num}/{total_batches}...")

            params = {
                "db": "pubmed",
                "id": ",".join(batch),
                "retmode": "xml",
            }

            response = self._make_request(EFETCH_URL, params)
            if not response:
                logger.warning(f"Failed to fetch batch {batch_num}")
                continue

            try:
                articles = self._parse_articles_xml(response.content)
                all_articles.extend(articles)
                report_progress(
                    "progress",
                    f"Fetched {len(all_articles)}/{len(pmids)} articles"
                )
            except Exception as e:
                logger.error(f"Error parsing batch {batch_num}: {e}")

        return all_articles

    def fetch_articles_generator(
        self,
        pmids: List[str],
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> Generator[ArticleMetadata, None, None]:
        """
        Fetch articles as a generator for memory efficiency.

        Args:
            pmids: List of PubMed IDs
            batch_size: Number of articles per request

        Yields:
            ArticleMetadata objects one at a time
        """
        for i in range(0, len(pmids), batch_size):
            batch = pmids[i:i + batch_size]

            params = {
                "db": "pubmed",
                "id": ",".join(batch),
                "retmode": "xml",
            }

            response = self._make_request(EFETCH_URL, params)
            if not response:
                continue

            try:
                articles = self._parse_articles_xml(response.content)
                for article in articles:
                    yield article
            except Exception as e:
                logger.error(f"Error parsing batch: {e}")

    def _parse_articles_xml(self, xml_content: bytes) -> List[ArticleMetadata]:
        """
        Parse PubMed XML response to ArticleMetadata objects.

        Args:
            xml_content: Raw XML response content

        Returns:
            List of ArticleMetadata objects
        """
        try:
            root = ET.fromstring(xml_content)
            articles = []

            for article_elem in root.findall(".//PubmedArticle"):
                metadata = self._parse_single_article(article_elem)
                if metadata:
                    articles.append(metadata)

            return articles

        except ET.ParseError as e:
            logger.error(f"XML parse error: {e}")
            return []

    def _parse_single_article(
        self,
        article_elem: ET.Element,
    ) -> Optional[ArticleMetadata]:
        """
        Parse a single PubmedArticle XML element.

        Args:
            article_elem: XML element for a PubmedArticle

        Returns:
            ArticleMetadata or None if parsing failed
        """
        try:
            # Extract PMID
            pmid_elem = article_elem.find(".//PMID")
            if pmid_elem is None or not pmid_elem.text:
                return None
            pmid = pmid_elem.text

            # Extract title
            title_elem = article_elem.find(".//ArticleTitle")
            title = self._get_element_text(title_elem) if title_elem is not None else ""

            # Extract abstract with Markdown formatting
            abstract = self._format_abstract_markdown(article_elem)

            # Extract authors
            authors = []
            for author in article_elem.findall(".//Author"):
                last_name = author.find(".//LastName")
                fore_name = author.find(".//ForeName")

                author_name = ""
                if last_name is not None:
                    author_name = self._get_element_text(last_name)
                if fore_name is not None:
                    fore_text = self._get_element_text(fore_name)
                    author_name = f"{author_name} {fore_text}" if author_name else fore_text

                if author_name:
                    authors.append(author_name)

            # Extract publication date
            pubdate_elem = article_elem.find(".//PubDate")
            publication_date = self._extract_date(pubdate_elem)

            # Extract journal name
            journal_elem = article_elem.find(".//Journal/Title")
            journal = self._get_element_text(journal_elem) if journal_elem is not None else "PubMed"

            # Extract DOI
            doi = None
            for article_id in article_elem.findall(".//ArticleId"):
                if article_id.get("IdType") == "doi":
                    doi = article_id.text
                    break

            # Extract PMC ID
            pmc_id = None
            for article_id in article_elem.findall(".//ArticleId"):
                if article_id.get("IdType") == "pmc":
                    pmc_id = article_id.text
                    break

            # Extract MeSH terms
            mesh_terms = []
            for descriptor in article_elem.findall(".//MeshHeading/DescriptorName"):
                mesh_term = self._get_element_text(descriptor)
                if mesh_term:
                    mesh_terms.append(mesh_term)

            # Extract keywords
            keywords = []
            for keyword in article_elem.findall(".//Keyword"):
                kw = self._get_element_text(keyword)
                if kw:
                    keywords.append(kw)

            return ArticleMetadata(
                pmid=pmid,
                doi=doi,
                title=title,
                abstract=abstract,
                authors=authors,
                publication=journal,
                publication_date=publication_date,
                mesh_terms=mesh_terms,
                keywords=keywords,
                pmc_id=pmc_id,
            )

        except Exception as e:
            logger.error(f"Error parsing article: {e}")
            return None

    def _get_element_text(self, elem: Optional[ET.Element]) -> str:
        """Get complete text from an XML element, handling mixed content."""
        if elem is None:
            return ""

        if not list(elem):
            return elem.text or ""

        text = elem.text or ""
        for child in elem:
            text += self._get_element_text(child)
            if child.tail:
                text += child.tail

        return text

    def _get_element_text_with_formatting(self, elem: Optional[ET.Element]) -> str:
        """
        Extract text with inline formatting converted to Markdown.

        Handles: <b>/<bold> → **text**, <i>/<italic> → *text*,
                 <sup> → ^text^, <sub> → ~text~
        """
        if elem is None:
            return ""

        if not list(elem):
            return (elem.text or "").strip()

        parts = []
        if elem.text:
            parts.append(elem.text)

        for child in elem:
            tag = child.tag.lower()
            child_text = self._get_element_text_with_formatting(child)

            if tag in ("b", "bold"):
                parts.append(f"**{child_text}**")
            elif tag in ("i", "italic"):
                parts.append(f"*{child_text}*")
            elif tag == "sup":
                parts.append(f"^{child_text}^")
            elif tag == "sub":
                parts.append(f"~{child_text}~")
            elif tag in ("u", "underline"):
                parts.append(f"__{child_text}__")
            else:
                parts.append(child_text)

            if child.tail:
                parts.append(child.tail)

        return "".join(parts).strip()

    def _format_abstract_markdown(self, article_elem: ET.Element) -> str:
        """
        Format abstract with section labels and Markdown formatting.
        """
        abstract_texts = article_elem.findall(".//AbstractText")
        if not abstract_texts:
            return ""

        markdown_parts = []

        for abstract_text in abstract_texts:
            label = abstract_text.get("Label", "").strip()
            if not label:
                nlm_category = abstract_text.get("NlmCategory", "").strip()
                if nlm_category and nlm_category not in ("UNASSIGNED", "UNLABELLED"):
                    label = nlm_category

            text = self._get_element_text_with_formatting(abstract_text)
            if not text:
                continue

            if label:
                markdown_parts.append(f"**{label.upper()}:** {text}")
            else:
                markdown_parts.append(text)

        return "\n\n".join(markdown_parts)

    def _extract_date(self, date_elem: Optional[ET.Element]) -> Optional[str]:
        """Extract date from a PubMed date element."""
        if date_elem is None:
            return None

        year = date_elem.find("Year")
        month = date_elem.find("Month")
        day = date_elem.find("Day")

        if year is not None and year.text:
            year_text = year.text

            month_text = "01"
            if month is not None and month.text:
                month_val = month.text.strip()
                month_map = {
                    "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04",
                    "May": "05", "Jun": "06", "Jul": "07", "Aug": "08",
                    "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12",
                }
                month_text = month_map.get(
                    month_val,
                    month_val.zfill(2) if month_val.isdigit() else "01"
                )

            day_text = (
                day.text.zfill(2)
                if day is not None and day.text and day.text.isdigit()
                else "01"
            )

            try:
                return f"{year_text}-{month_text}-{day_text}"
            except Exception:
                return year_text

        return None

    def test_connection(self) -> bool:
        """
        Test connection to PubMed API.

        Returns:
            True if connection is successful
        """
        try:
            params = {
                "db": "pubmed",
                "term": "test",
                "retmax": 1,
                "retmode": "json",
            }
            response = self._make_request(ESEARCH_URL, params)
            return response is not None and response.status_code == 200
        except Exception:
            return False
