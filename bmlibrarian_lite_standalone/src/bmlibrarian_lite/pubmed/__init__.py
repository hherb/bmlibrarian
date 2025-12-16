"""
PubMed E-utilities API client module for BMLibrarian Lite.

Provides search functionality against PubMed via NCBI E-utilities API,
with proper rate limiting, retry logic, and batch fetching.

Usage:
    from bmlibrarian_lite.pubmed import PubMedSearchClient, PubMedQuery

    client = PubMedSearchClient(email="user@example.com")
    result = client.search_simple("cardiovascular exercise", max_results=100)
    articles = client.fetch_articles(result.pmids)
"""

from .data_types import (
    ArticleMetadata,
    DateRange,
    ImportResult,
    MeSHTerm,
    PublicationType,
    PubMedQuery,
    QueryConcept,
    QueryConversionResult,
    SearchResult,
    SearchSession,
    SearchStatus,
)
from .search_client import PubMedSearchClient, validate_email
from .constants import (
    DEFAULT_MAX_RESULTS,
    DEFAULT_BATCH_SIZE,
    ESEARCH_URL,
    EFETCH_URL,
)

__all__ = [
    # Data types
    "ArticleMetadata",
    "DateRange",
    "ImportResult",
    "MeSHTerm",
    "PublicationType",
    "PubMedQuery",
    "QueryConcept",
    "QueryConversionResult",
    "SearchResult",
    "SearchSession",
    "SearchStatus",
    # Client
    "PubMedSearchClient",
    "validate_email",
    # Constants
    "DEFAULT_MAX_RESULTS",
    "DEFAULT_BATCH_SIZE",
    "ESEARCH_URL",
    "EFETCH_URL",
]
