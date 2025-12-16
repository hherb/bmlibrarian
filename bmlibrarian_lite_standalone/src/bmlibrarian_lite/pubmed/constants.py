"""
Constants for PubMed API Search module.

This module defines all constants used throughout the PubMed search system,
following BMLibrarian's golden rule of no magic numbers or hardcoded values.
"""

# NCBI E-utilities API endpoints
EUTILS_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
ESEARCH_URL = f"{EUTILS_BASE_URL}/esearch.fcgi"
EFETCH_URL = f"{EUTILS_BASE_URL}/efetch.fcgi"
EINFO_URL = f"{EUTILS_BASE_URL}/einfo.fcgi"

# MeSH lookup endpoints
MESH_BROWSER_API_URL = "https://id.nlm.nih.gov/mesh/lookup/descriptor"
MESH_SPARQL_URL = "https://id.nlm.nih.gov/mesh/sparql"

# Rate limiting (NCBI policy)
RATE_LIMIT_WITH_KEY = 10  # requests per second with API key
RATE_LIMIT_WITHOUT_KEY = 3  # requests per second without API key
REQUEST_DELAY_WITH_KEY = 0.1  # seconds between requests with key
REQUEST_DELAY_WITHOUT_KEY = 0.34  # seconds between requests without key

# Default search parameters
DEFAULT_MAX_RESULTS = 200
MAX_RESULTS_LIMIT = 10000
DEFAULT_BATCH_SIZE = 200  # PMIDs per efetch request
HISTORY_SERVER_THRESHOLD = 1000  # Use history server above this count

# Timeouts
REQUEST_TIMEOUT_SECONDS = 30
MAX_RETRIES = 3
INITIAL_RETRY_DELAY_SECONDS = 1.0
RETRY_BACKOFF_MULTIPLIER = 2.0

# MeSH cache settings
MESH_CACHE_FILENAME = "mesh_cache.db"
MESH_CACHE_TTL_DAYS = 30

# MeSH descriptor identifier prefix (e.g., D001234 for descriptor UI)
MESH_DESCRIPTOR_PREFIX = "D"

# LLM configuration
DEFAULT_QUERY_MODEL = "gpt-oss:20b"
DEFAULT_TEMPERATURE = 0.1
DEFAULT_TOP_P = 0.9
DEFAULT_MAX_TOKENS = 2000

# PubMed field tags for query building
FIELD_TAGS = {
    "mesh": "[MeSH Terms]",
    "mesh_major": "[MeSH Major Topic]",
    "tiab": "[Title/Abstract]",
    "ti": "[Title]",
    "ab": "[Abstract]",
    "tw": "[Text Word]",
    "au": "[Author]",
    "pt": "[Publication Type]",
    "dp": "[Date - Publication]",
    "la": "[Language]",
    "sb": "[Subset]",
}

# Common publication type filters
PUBLICATION_TYPE_FILTERS = {
    "clinical_trial": "Clinical Trial[pt]",
    "rct": "Randomized Controlled Trial[pt]",
    "meta_analysis": "Meta-Analysis[pt]",
    "systematic_review": "Systematic Review[pt]",
    "review": "Review[pt]",
    "case_report": "Case Reports[pt]",
    "guideline": "Guideline[pt]",
    "observational": "Observational Study[pt]",
}

# Common subset filters
SUBSET_FILTERS = {
    "humans": "humans[MeSH Terms]",
    "animals": "animals[MeSH Terms]",
    "english": "english[la]",
    "free_full_text": "free full text[sb]",
    "has_abstract": "hasabstract",
}

# Query validation
MIN_QUERY_LENGTH = 3
MAX_QUERY_LENGTH = 10000
QUERY_LENGTH_WARNING_THRESHOLD = 8000  # Warn when query approaches PubMed's limit

# URL length threshold for automatic POST fallback
# Most servers/browsers limit URLs to ~8000 characters, PubMed API has similar limits
# Using 2000 as a safe threshold to trigger POST before hitting 414 errors
URL_LENGTH_POST_THRESHOLD = 2000

# Email validation pattern for NCBI API requirements
EMAIL_VALIDATION_PATTERN = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

# Environment variable names
ENV_NCBI_EMAIL = "NCBI_EMAIL"
ENV_NCBI_API_KEY = "NCBI_API_KEY"
