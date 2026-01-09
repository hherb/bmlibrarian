"""
Paper Reviewer Constants

Centralized constants for the paper reviewer module.
Follows Rule 2 (no magic numbers) and Rule 3 (no hardcoded paths).
"""

# Version
VERSION = "1.0.0"

# Text processing limits
# Maximum text length for LLM prompts (characters)
# This is a conservative limit to fit within LLM context windows
MAX_TEXT_LENGTH = 10000

# Length threshold above which text is classified as full_text rather than abstract
ABSTRACT_LENGTH_THRESHOLD = 3000

# Minimum abstract length to consider it valid/useful for analysis
MIN_ABSTRACT_LENGTH = 200

# Rate limiting delays (seconds)
PUBMED_API_DELAY = 0.34  # 3 requests/second without API key
PUBMED_API_DELAY_WITH_KEY = 0.1  # 10 requests/second with API key
CROSSREF_API_DELAY = 0.05  # 20 requests/second for polite pool

# Request timeouts (seconds)
REQUEST_TIMEOUT = 30

# LLM generation parameters
DEFAULT_TEMPERATURE_LOW = 0.1  # For consistent/deterministic output
DEFAULT_TEMPERATURE_MODERATE = 0.3  # For creative tasks like counter-statements
DEFAULT_MAX_TOKENS = 2000
DEFAULT_MAX_TOKENS_SHORT = 500  # For short responses
DEFAULT_MAX_TOKENS_LONG = 1500  # For longer responses like summaries

# Search limits
DEFAULT_SEMANTIC_SEARCH_LIMIT = 30
DEFAULT_HYDE_SEARCH_LIMIT = 30
DEFAULT_KEYWORD_SEARCH_LIMIT = 30
DEFAULT_MAX_SEARCH_RESULTS = 20  # Maximum results to return after reranking
DEFAULT_PUBMED_SEARCH_LIMIT = 20

# Reranking limits
MAX_PAPERS_TO_RERANK = 50  # Maximum papers to pass through LLM reranking
ABSTRACT_PREVIEW_LENGTH = 200  # Characters of abstract to show in ranking prompt

# Synthesis limits
MAX_STRENGTHS_TO_EXTRACT = 3  # From each assessment
MAX_WEAKNESSES_TO_EXTRACT = 3  # From each assessment
MAX_STRENGTHS_IN_SUMMARY = 6  # Total in final summary
MAX_WEAKNESSES_IN_SUMMARY = 6  # Total in final summary

# Study design scoring thresholds
STRONG_SCORE_THRESHOLD = 7.0  # Score >= this is considered strong
WEAK_SCORE_THRESHOLD = 4.0  # Score < this is considered weak

# Confidence thresholds
HIGH_CONFIDENCE_THRESHOLD = 0.8
MODERATE_CONFIDENCE_THRESHOLD = 0.6
LOW_CONFIDENCE_THRESHOLD = 0.5  # For rule-based only fallback

# Date format for reports
DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'

# API URLs
PUBMED_EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
PUBMED_ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
CROSSREF_API_URL = "https://api.crossref.org/works"
DOI_ORG_URL = "https://doi.org"

# User agent for API requests
USER_AGENT = "BMLibrarian/1.0 (Paper Reviewer; mailto:contact@bmlibrarian.org)"


__all__ = [
    'VERSION',
    'MAX_TEXT_LENGTH',
    'ABSTRACT_LENGTH_THRESHOLD',
    'MIN_ABSTRACT_LENGTH',
    'PUBMED_API_DELAY',
    'PUBMED_API_DELAY_WITH_KEY',
    'CROSSREF_API_DELAY',
    'REQUEST_TIMEOUT',
    'DEFAULT_TEMPERATURE_LOW',
    'DEFAULT_TEMPERATURE_MODERATE',
    'DEFAULT_MAX_TOKENS',
    'DEFAULT_MAX_TOKENS_SHORT',
    'DEFAULT_MAX_TOKENS_LONG',
    'DEFAULT_SEMANTIC_SEARCH_LIMIT',
    'DEFAULT_HYDE_SEARCH_LIMIT',
    'DEFAULT_KEYWORD_SEARCH_LIMIT',
    'DEFAULT_MAX_SEARCH_RESULTS',
    'DEFAULT_PUBMED_SEARCH_LIMIT',
    'MAX_PAPERS_TO_RERANK',
    'ABSTRACT_PREVIEW_LENGTH',
    'MAX_STRENGTHS_TO_EXTRACT',
    'MAX_WEAKNESSES_TO_EXTRACT',
    'MAX_STRENGTHS_IN_SUMMARY',
    'MAX_WEAKNESSES_IN_SUMMARY',
    'STRONG_SCORE_THRESHOLD',
    'WEAK_SCORE_THRESHOLD',
    'HIGH_CONFIDENCE_THRESHOLD',
    'MODERATE_CONFIDENCE_THRESHOLD',
    'LOW_CONFIDENCE_THRESHOLD',
    'DATETIME_FORMAT',
    'PUBMED_EFETCH_URL',
    'PUBMED_ESEARCH_URL',
    'CROSSREF_API_URL',
    'DOI_ORG_URL',
    'USER_AGENT',
]
