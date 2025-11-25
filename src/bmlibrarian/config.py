"""
Configuration Management for BMLibrarian

Provides centralized configuration for models, settings, and other parameters.
Supports both environment variables and configuration files.
"""

import json
import os
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, TypedDict, TYPE_CHECKING
from pathlib import Path

# Type checking imports to avoid circular dependencies
if TYPE_CHECKING:
    from psycopg import Connection
    from .auth.user_settings import UserSettingsManager

logger = logging.getLogger(__name__)


# =============================================================================
# User Context for Database-Backed Settings
# =============================================================================

@dataclass
class UserContext:
    """Holds user session information for database-backed configuration.

    When a user is authenticated, this context enables the configuration system
    to load and save settings from the PostgreSQL database instead of JSON files.

    Attributes:
        user_id: The authenticated user's database ID.
        connection: Active psycopg database connection for settings operations.
        session_token: Optional session token for session validation.

    Example:
        from bmlibrarian.config import get_config, UserContext
        from bmlibrarian.database import get_db_manager

        config = get_config()
        db = get_db_manager()
        with db.get_connection() as conn:
            config.set_user_context(user_id=1, connection=conn)
            # Config now loads from database
            model = config.get_model("query_agent")
    """
    user_id: int
    connection: 'Connection'
    session_token: Optional[str] = None


# Valid settings categories for database storage
# Must match bmlsettings schema constraints
VALID_SETTINGS_CATEGORIES = frozenset([
    'models', 'ollama', 'agents', 'database', 'search',
    'query_generation', 'gui', 'openathens', 'pdf', 'general', 'document_qa',
    'discovery', 'embeddings'
])


# =============================================================================
# Paper Weight Assessment Configuration Type Definitions
# =============================================================================

class DimensionWeights(TypedDict):
    """Type definition for dimension weights in paper weight assessment.

    Each weight represents the relative importance of a dimension in the
    final weighted score calculation. All weights must be non-negative
    and sum to 1.0.
    """
    study_design: float
    sample_size: float
    methodological_quality: float
    risk_of_bias: float
    replication_status: float


class StudyTypeHierarchy(TypedDict, total=False):
    """Type definition for study type hierarchy scores.

    Each score represents the evidence quality baseline (0-10) for a
    particular study type. Higher scores indicate stronger evidence.
    """
    systematic_review: float
    meta_analysis: float
    rct: float
    cohort_prospective: float
    cohort_retrospective: float
    case_control: float
    cross_sectional: float
    case_series: float
    case_report: float


class SampleSizeScoring(TypedDict):
    """Type definition for sample size scoring parameters.

    Formula: min(10, log_base(n) * log_multiplier) + bonuses
    """
    log_base: int
    log_multiplier: float
    power_calculation_bonus: float
    ci_reported_bonus: float


class MethodologicalQualityWeights(TypedDict):
    """Type definition for methodological quality sub-component weights.

    Weights must sum to 10.0 for normalized scoring.
    """
    randomization: float
    blinding: float
    allocation_concealment: float
    protocol_preregistration: float
    itt_analysis: float
    attrition_handling: float


class RiskOfBiasWeights(TypedDict):
    """Type definition for risk of bias domain weights.

    Weights must sum to 10.0 for normalized scoring.
    """
    selection_bias: float
    performance_bias: float
    detection_bias: float
    reporting_bias: float


class AttritionThresholds(TypedDict):
    """Type definition for attrition rate quality thresholds.

    Values represent dropout rate proportions (0.0-1.0).
    Must be in ascending order: excellent < good < acceptable.
    """
    excellent: float
    good: float
    acceptable: float


class PaperWeightConfig(TypedDict, total=False):
    """Complete type definition for paper weight assessment configuration."""
    model: str
    temperature: float
    top_p: float
    version: str
    dimension_weights: DimensionWeights
    study_type_hierarchy: StudyTypeHierarchy
    study_type_keywords: Dict[str, List[str]]
    sample_size_scoring: SampleSizeScoring
    methodological_quality_weights: MethodologicalQualityWeights
    risk_of_bias_weights: RiskOfBiasWeights
    attrition_thresholds: AttritionThresholds


# =============================================================================
# Paper Weight Validation Constants
# =============================================================================

# Floating point tolerance for weight sum validation.
# ±0.01 chosen to handle typical JSON serialization precision loss while
# still catching configuration errors (e.g., typos that cause significant drift).
# JSON parsers typically preserve ~15 significant digits, so 0.01 provides
# ample margin while detecting errors like 0.9 vs 1.0.
FLOAT_TOLERANCE = 0.01

# Expected sum for dimension weights (normalized to 1.0 for probability-like interpretation)
WEIGHT_SUM_EXPECTED = 1.0

# Expected sum for quality and bias weights (scaled to 10.0 for easier human readability)
QUALITY_WEIGHT_SUM_EXPECTED = 10.0

# Tolerance multiplier for quality/bias weights validation.
# Quality weights use a scale of 10.0 (vs 1.0 for dimension weights), so we need
# 10x the tolerance to account for proportionally larger floating point errors.
QUALITY_WEIGHT_TOLERANCE_MULTIPLIER = 10

# Valid range for LLM temperature parameter (0.0 = deterministic, 1.0+ = creative)
TEMPERATURE_MIN = 0.0
TEMPERATURE_MAX = 2.0  # Some models support up to 2.0

# Valid range for nucleus sampling top_p parameter
TOP_P_MIN = 0.0
TOP_P_MAX = 1.0


# =============================================================================
# Validation Result Type
# =============================================================================

@dataclass
class ValidationResult:
    """Result of configuration validation.

    Provides structured output for validation operations, enabling
    consistent error handling and detailed error reporting.

    Attributes:
        valid: True if configuration passed all validation checks
        errors: List of validation error messages (empty if valid)
        warnings: List of non-fatal validation warnings
    """
    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        """Allow ValidationResult to be used in boolean context."""
        return self.valid

    def raise_if_invalid(self) -> None:
        """Raise ValueError if validation failed.

        Convenience method for callers who prefer exception-based error handling.

        Raises:
            ValueError: If validation failed, with all errors as message
        """
        if not self.valid:
            raise ValueError("; ".join(self.errors))


# =============================================================================
# Paper Weight Assessment Configuration Defaults
# =============================================================================

DEFAULT_PAPER_WEIGHT_CONFIG = {
    "model": "gpt-oss:20b",
    "temperature": 0.3,
    "top_p": 0.9,
    "version": "1.0.0",
    "dimension_weights": {
        "study_design": 0.25,
        "sample_size": 0.15,
        "methodological_quality": 0.30,
        "risk_of_bias": 0.20,
        "replication_status": 0.10
    },
    "study_type_hierarchy": {
        "systematic_review": 10.0,
        "meta_analysis": 10.0,
        "rct": 8.0,
        "cohort_prospective": 6.0,
        "cohort_retrospective": 5.0,
        "case_control": 4.0,
        "cross_sectional": 3.0,
        "case_series": 2.0,
        "case_report": 1.0
    },
    "study_type_keywords": {
        "systematic_review": ["systematic review", "systematic literature review"],
        "meta_analysis": ["meta-analysis", "meta analysis", "pooled analysis"],
        "rct": [
            "randomized controlled trial", "randomised controlled trial", "RCT",
            "randomized trial", "randomised trial", "random allocation", "randomly assigned"
        ],
        "cohort_prospective": ["prospective cohort", "prospective study", "longitudinal cohort"],
        "cohort_retrospective": ["retrospective cohort", "retrospective study"],
        "case_control": ["case-control", "case control study"],
        "cross_sectional": ["cross-sectional", "cross sectional study", "prevalence study"],
        "case_series": ["case series", "case-series"],
        "case_report": ["case report", "case study"]
    },
    "sample_size_scoring": {
        "log_base": 10,
        "log_multiplier": 2.0,
        "power_calculation_bonus": 2.0,
        "ci_reported_bonus": 0.5
    },
    "methodological_quality_weights": {
        "randomization": 2.0,
        "blinding": 3.0,
        "allocation_concealment": 1.5,
        "protocol_preregistration": 1.5,
        "itt_analysis": 1.0,
        "attrition_handling": 1.0
    },
    "risk_of_bias_weights": {
        "selection_bias": 2.5,
        "performance_bias": 2.5,
        "detection_bias": 2.5,
        "reporting_bias": 2.5
    },
    "attrition_thresholds": {
        "excellent": 0.05,
        "good": 0.10,
        "acceptable": 0.20
    }
}

# Default configuration
DEFAULT_CONFIG = {
    "models": {
        "counterfactual_agent": "medgemma-27b-text-it-Q8_0:latest",
        "query_agent": "medgemma-27b-text-it-Q8_0:latest",
        "scoring_agent": "medgemma-27b-text-it-Q8_0:latest",
        "citation_agent": "medgemma-27b-text-it-Q8_0:latest",
        "reporting_agent": "gpt-oss:20b",  # Keep larger model for complex report generation
        "editor_agent": "gpt-oss:20b",     # Use larger model for comprehensive editing
        "fact_checker_agent": "gpt-oss:20b",  # Use larger model for statement evaluation
        "document_interrogation_agent": "gpt-oss:20b",  # Use larger model for complex document Q&A
        "document_interrogation_embedding": "snowflake-arctic-embed2:latest",  # Embedding model for semantic search
        "pico_agent": "gpt-oss:20b",  # Use larger model for PICO extraction
        "study_assessment_agent": "gpt-oss:20b",  # Use larger model for study quality assessment
        "prisma2020_agent": "gpt-oss:20b",  # Use larger model for PRISMA 2020 compliance assessment
        "paper_weight_assessment_agent": "gpt-oss:20b",  # Use larger model for paper weight assessment
        "paper_checker_agent": "gpt-oss:20b",  # Use larger model for abstract fact-checking
        "document_qa_agent": "gpt-oss:20b",  # Use larger model for document Q&A

        # Alternative models for different use cases
        "fast_model": "medgemma4B_it_q8:latest",
        "complex_model": "gpt-oss:20b",
        "medical_model": "medgemma-27b-text-it-Q8_0:latest"
    },
    "ollama": {
        "host": "http://localhost:11434",
        "timeout": 120,
        "max_retries": 3
    },
    "agents": {
        "counterfactual": {
            "temperature": 0.2,
            "top_p": 0.9,
            "max_tokens": 4000,
            "retry_attempts": 3
        },
        "scoring": {
            "temperature": 0.1,
            "top_p": 0.9,
            "max_tokens": 300,
            "min_relevance_score": 3
        },
        "query": {
            "temperature": 0.1,
            "top_p": 0.9,
            "max_tokens": 500  # Minimum 400 required for models like gpt-oss:20b
        },
        "citation": {
            "temperature": 0.2,
            "top_p": 0.9,
            "max_tokens": 1000,
            "min_relevance": 0.7
        },
        "reporting": {
            "temperature": 0.1,
            "top_p": 0.9,
            "max_tokens": 3000
        },
        "editor": {
            "temperature": 0.1,
            "top_p": 0.8,
            "max_tokens": 6000,
            "comprehensive_format": True
        },
        "fact_checker": {
            "temperature": 0.1,
            "top_p": 0.9,
            "max_tokens": 2000,
            "score_threshold": 2.5,
            "max_search_results": 50,
            "max_citations": None  # None = no limit, use all scored documents
        },
        "document_interrogation": {
            "temperature": 0.1,
            "top_p": 0.9,
            "max_tokens": 3000,
            "chunk_size": 10000,  # Maximum characters per chunk
            "chunk_overlap": 250,  # Overlap between chunks in characters
            "processing_mode": "sequential",  # Default: sequential, embedding, or hybrid
            "embedding_threshold": 0.5,  # Minimum cosine similarity for embedding mode (0-1)
            "max_sections": 10  # Maximum number of relevant sections to extract
        },
        "pico": {
            "temperature": 0.1,
            "top_p": 0.9,
            "max_tokens": 2000,
            "min_confidence": 0.5,  # Minimum confidence threshold to accept extraction
            "max_retries": 3  # Maximum retry attempts for failed extractions
        },
        "study_assessment": {
            "temperature": 0.1,
            "top_p": 0.9,
            "max_tokens": 3000,
            "min_confidence": 0.4,  # Minimum confidence threshold for assessments
            "max_retries": 3  # Maximum retry attempts for failed assessments
        },
        "prisma2020": {
            "temperature": 0.1,
            "top_p": 0.9,
            "max_tokens": 4000,  # PRISMA assessments need more tokens (27 items)
            "min_confidence": 0.4,  # Minimum confidence threshold for assessments
            "max_retries": 3  # Maximum retry attempts for failed assessments
        },
        "paper_weight_assessment": {
            "temperature": 0.3,
            "top_p": 0.9,
            "max_tokens": 3000,
            "version": "1.0.0",  # Increment when methodology changes
            "dimension_weights": {
                "study_design": 0.25,
                "sample_size": 0.15,
                "methodological_quality": 0.30,
                "risk_of_bias": 0.20,
                "replication_status": 0.10
            },
            "study_type_hierarchy": {
                "systematic_review": 10.0,
                "meta_analysis": 10.0,
                "rct": 8.0,
                "quasi_experimental": 7.0,
                "pilot_feasibility": 6.5,
                "cohort_prospective": 6.0,
                "cohort_retrospective": 5.0,
                "case_control": 4.0,
                "cross_sectional": 3.0,
                "case_series": 2.0,
                "case_report": 1.0
            },
            "study_type_keywords": {
                "systematic_review": ["systematic review", "systematic literature review"],
                "meta_analysis": ["meta-analysis", "meta analysis", "pooled analysis"],
                "quasi_experimental": [
                    "non-randomized trial", "non-randomised trial", "nonrandomized trial",
                    "nonrandomised trial", "quasi-experimental", "quasi experimental",
                    "single-arm trial", "single arm trial", "open-label trial"
                ],
                "rct": [
                    "randomized controlled trial", "randomised controlled trial", "RCT",
                    "randomized trial", "randomised trial", "random allocation", "randomly assigned",
                    "double-blind randomized", "double-blind randomised"
                ],
                "pilot_feasibility": [
                    "pilot study", "pilot trial", "feasibility study", "feasibility trial",
                    "proof-of-concept study", "proof of concept study"
                ],
                "cohort_prospective": ["prospective cohort", "prospective study", "longitudinal cohort"],
                "cohort_retrospective": ["retrospective cohort", "retrospective study"],
                "case_control": ["case-control", "case control study"],
                "cross_sectional": ["cross-sectional", "cross sectional study", "prevalence study"],
                "case_series": ["case series", "case-series"],
                "case_report": ["case report", "case study"]
            },
            "sample_size_scoring": {
                "log_base": 10,
                "log_multiplier": 2.0,
                "power_calculation_bonus": 2.0,
                "ci_reported_bonus": 0.5
            },
            "methodological_quality_weights": {
                "randomization": 2.0,
                "blinding": 3.0,
                "allocation_concealment": 1.5,
                "protocol_preregistration": 1.5,
                "itt_analysis": 1.0,
                "attrition_handling": 1.0
            },
            "risk_of_bias_weights": {
                "selection_bias": 2.5,
                "performance_bias": 2.5,
                "detection_bias": 2.5,
                "reporting_bias": 2.5
            },
            "attrition_thresholds": {
                "excellent": 0.05,
                "good": 0.10,
                "acceptable": 0.20
            }
        },
        "paper_checker": {
            "temperature": 0.3,
            "top_p": 0.9,
            "max_statements": 2,  # Maximum statements to extract from abstract
            "score_threshold": 3.0,  # Minimum relevance score for document inclusion
            "search": {
                "semantic_limit": 50,  # Maximum documents from semantic search
                "hyde_limit": 50,  # Maximum documents from HyDE search
                "keyword_limit": 50,  # Maximum documents from keyword search
                "max_deduplicated": 100  # Maximum unique documents after deduplication
            },
            "citation": {
                "min_score": 3,  # Minimum score for citation extraction
                "max_citations_per_statement": 10  # Maximum citations per statement
            },
            "hyde": {
                "num_abstracts": 2,  # Number of hypothetical abstracts to generate
                "max_keywords": 10  # Maximum keywords to generate
            }
        },
        "document_qa": {
            "temperature": 0.3,
            "top_p": 0.9,
            "max_tokens": 2000,
            "max_chunks": 5,  # Maximum context chunks to use for answer generation
            "similarity_threshold": 0.7,  # Minimum similarity for semantic search (0.0-1.0)
            "use_fulltext": True,  # Prefer full-text over abstract when available
            "download_missing_fulltext": True,  # Attempt to download PDFs if full-text missing
            "use_proxy": True,  # Use OpenAthens proxy for paywalled content
            "use_thinking": True,  # Enable thinking mode for supported models
            "embedding_model": "snowflake-arctic-embed2:latest"
        },
        "formatting": {
            "require_specific_years": True,  # Use specific years instead of "recent study"
            "temporal_precision": True  # Enforce precise temporal references in reports
        }
    },
    "database": {
        "max_results_per_query": 10,
        "batch_size": 50,
        "use_ranking": False
    },
    "search": {
        "max_results": 100,  # Default maximum number of documents to retrieve
        "score_threshold": 2.5,  # Minimum relevance score threshold
        "max_documents_to_score": None,  # None = score all documents
        "max_documents_for_citations": None,  # None = use all scored documents
        "counterfactual_max_results": 10,  # Max results per counterfactual query (defaults to main max_results if not set)
        "counterfactual_min_score": 3,  # Min score for counterfactual evidence
        "query_retry_attempts": 3,  # Number of times to retry failed tsquery with reformulation
        "auto_fix_tsquery_syntax": True,  # Automatically fix common tsquery syntax errors
        "min_relevant": 10,  # Minimum number of high-scoring documents to find through iterative search
        "max_retry": 3,  # Max retries per strategy (offset-based, then query modification)
        "batch_size": 100  # Number of documents to fetch per iteration
    },
    "query_generation": {
        "multi_model_enabled": False,  # Feature flag - default disabled for backward compatibility
        "models": [
            "medgemma-27b-text-it-Q8_0:latest"  # Default: single model (same as query_agent)
        ],
        "queries_per_model": 1,  # 1-3 queries per model (1 = single query like original behavior)
        "execution_mode": "serial",  # Always serial for local Ollama + PostgreSQL instances
        "deduplicate_results": True,  # Remove duplicate documents across queries
        "show_all_queries_to_user": True,  # Display all generated queries in CLI
        "allow_query_selection": True  # Let user select which queries to execute
    },
    "search_strategy": {
        # Multiple strategies can be enabled for hybrid search
        "keyword": {
            "enabled": True,  # Keyword fulltext search (default enabled)
            "max_results": 100,
            "operator": "AND",  # AND/OR for combining search terms
            "case_sensitive": False
        },
        "bm25": {
            "enabled": False,  # BM25 probabilistic ranking
            "max_results": 100,
            "k1": 1.2,  # Term frequency saturation (typical: 1.2-2.0)
            "b": 0.75   # Document length normalization (0=none, 1=full)
        },
        "semantic": {
            "enabled": False,  # Vector similarity search
            "max_results": 100,
            "embedding_model": "nomic-embed-text:latest",
            "similarity_threshold": 0.7  # Cosine similarity threshold (0-1)
        },
        "hyde": {
            "enabled": False,  # Hypothetical Document Embeddings
            "max_results": 100,
            "generation_model": "medgemma-27b-text-it-Q8_0:latest",
            "embedding_model": "nomic-embed-text:latest",
            "num_hypothetical_docs": 3,  # Number of hypothetical documents to generate
            "similarity_threshold": 0.7   # Cosine similarity threshold (0-1)
        },
        "reranking": {
            # Re-ranking method for combining results from multiple strategies
            "method": "sum_scores",  # Options: sum_scores, rrf, max_score, weighted
            "rrf_k": 60,  # RRF constant (Cormack et al., 2009)
            "weights": {  # Weights for "weighted" method
                "keyword": 1.0,
                "bm25": 1.5,
                "semantic": 2.0,
                "hyde": 2.0
            }
        }
    },
    "openathens": {
        "enabled": False,  # Enable OpenAthens proxy for PDF downloads
        "institution_url": "",  # Your institution's OpenAthens URL (e.g., "https://institution.openathens.net")
        "session_timeout_hours": 24,  # Session timeout in hours (default: 24)
        "auto_login": True,  # Automatically login on startup if session expired
        "login_timeout": 300,  # Maximum seconds to wait for login completion (default: 300 = 5 minutes)
        "headless": False  # Run browser in headless mode for login (False = visible for 2FA)
    },
    "discovery": {
        "timeout": 30,  # HTTP request timeout in seconds (5-120)
        "browser_timeout": 60000,  # Browser timeout in milliseconds (5000-300000)
        "prefer_open_access": True,  # Prioritize open access sources
        "use_browser_fallback": True,  # Use browser automation when HTTP fails (Cloudflare bypass)
        "browser_headless": True,  # Run browser in headless mode for PDF downloads
        "skip_resolvers": None,  # List of resolvers to skip (e.g., ["openathens", "pmc"])
        "use_openathens_proxy": False  # Use OpenAthens proxy as last resort for paywalled content
    },
    "embeddings": {
        # Backend for generating embeddings
        # Options: "ollama", "ollama_http", "sentence_transformers", "llama_cpp"
        # "sentence_transformers" is recommended for stability with larger chunks
        "backend": "sentence_transformers",
        "model": "snowflake-arctic-embed2:latest",  # Model name (Ollama) or HuggingFace model ID
        "huggingface_model": "Snowflake/snowflake-arctic-embed-l-v2.0",  # HuggingFace model for sentence_transformers
        "batch_size": 32,  # Batch size for embedding generation
        "n_ctx": 8192,  # Context window size (for llama_cpp backend)
        "device": "auto"  # Device for sentence_transformers: "auto", "cpu", "cuda", "mps"
    }
}

class BMLibrarianConfig:
    """Configuration manager for BMLibrarian.

    Handles loading configuration from files, environment variables, and
    database-backed user settings. Supports per-user configuration when
    a user context is set.

    The configuration resolution priority is:
    1. User settings from database (if user context is set)
    2. Default settings from database (if connected)
    3. JSON configuration file (~/.bmlibrarian/config.json)
    4. Environment variable overrides
    5. Hardcoded DEFAULT_CONFIG

    Attributes:
        _config: In-memory configuration dictionary.
        _config_loaded: Whether configuration has been loaded from files.
        _user_context: Optional user context for database-backed settings.
        _settings_manager: UserSettingsManager instance when user context is set.

    Example:
        # Without user context (uses JSON/defaults)
        config = get_config()
        model = config.get_model("query_agent")

        # With user context (uses database)
        config.set_user_context(user_id=1, connection=conn)
        model = config.get_model("query_agent")  # Now loads from DB
    """

    def __init__(self) -> None:
        """Initialize the configuration manager.

        Loads configuration from JSON files and environment variables.
        User context can be set later via set_user_context().
        """
        self._config: Dict[str, Any] = self._deep_copy_config(DEFAULT_CONFIG)
        self._config_loaded: bool = False
        self._user_context: Optional[UserContext] = None
        self._settings_manager: Optional['UserSettingsManager'] = None
        self._load_config()
    
    def _load_config(self):
        """Load configuration from various sources in priority order."""
        if self._config_loaded:
            return

        # 1. Load from config file if it exists
        from .utils.config_loader import load_config_with_fallback

        file_config = load_config_with_fallback()
        if file_config:
            self._merge_config(file_config)

        # 2. Override with environment variables
        self._load_env_overrides()

        self._config_loaded = True
    
    def _merge_config(self, new_config: Dict[str, Any]):
        """Recursively merge new configuration into existing config."""
        def merge_dict(base: Dict, update: Dict):
            for key, value in update.items():
                if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                    merge_dict(base[key], value)
                else:
                    base[key] = value
        
        merge_dict(self._config, new_config)
    
    def _load_env_overrides(self):
        """Load configuration overrides from environment variables."""
        # Model overrides
        env_mappings = {
            "BMLIB_COUNTERFACTUAL_MODEL": ["models", "counterfactual_agent"],
            "BMLIB_QUERY_MODEL": ["models", "query_agent"],
            "BMLIB_SCORING_MODEL": ["models", "scoring_agent"],
            "BMLIB_CITATION_MODEL": ["models", "citation_agent"],
            "BMLIB_REPORTING_MODEL": ["models", "reporting_agent"],
            "BMLIB_OLLAMA_HOST": ["ollama", "host"],
            "BMLIB_OLLAMA_TIMEOUT": ["ollama", "timeout"],
        }
        
        for env_var, config_path in env_mappings.items():
            value = os.getenv(env_var)
            if value:
                # Navigate to the config location
                current = self._config
                for key in config_path[:-1]:
                    current = current[key]
                
                # Convert value to appropriate type
                if config_path[-1] == "timeout":
                    try:
                        value = int(value)
                    except ValueError:
                        logger.warning(f"Invalid integer value for {env_var}: {value}")
                        continue
                
                current[config_path[-1]] = value
                logger.info(f"Environment override: {env_var} = {value}")

    @staticmethod
    def _deep_copy_config(config: Dict[str, Any]) -> Dict[str, Any]:
        """Create a deep copy of a configuration dictionary.

        Args:
            config: Configuration dictionary to copy.

        Returns:
            Deep copy of the configuration.
        """
        import copy
        return copy.deepcopy(config)

    # =========================================================================
    # User Context Management
    # =========================================================================

    def set_user_context(
        self,
        user_id: int,
        connection: 'Connection',
        session_token: Optional[str] = None
    ) -> None:
        """Set user context for database-backed settings.

        When user context is set, configuration values are loaded from the
        user's settings in the PostgreSQL database, with fallback to system
        defaults and then to in-memory/JSON configuration.

        Args:
            user_id: The authenticated user's database ID.
            connection: Active psycopg database connection.
            session_token: Optional session token for validation.

        Example:
            from bmlibrarian.database import get_db_manager

            config = get_config()
            db = get_db_manager()
            with db.get_connection() as conn:
                config.set_user_context(user_id=1, connection=conn)
                # Config now uses database-backed settings
        """
        from .auth.user_settings import UserSettingsManager

        self._user_context = UserContext(
            user_id=user_id,
            connection=connection,
            session_token=session_token
        )
        self._settings_manager = UserSettingsManager(connection, user_id)

        # Sync settings from database to in-memory config
        self._sync_from_database()

        logger.info(f"User context set for user_id={user_id}")

    def clear_user_context(self) -> None:
        """Clear user context, reverting to JSON/default configuration.

        After clearing, configuration values will be loaded from JSON files
        and hardcoded defaults instead of the database.
        """
        if self._user_context is not None:
            logger.info(f"Clearing user context for user_id={self._user_context.user_id}")

        self._user_context = None
        self._settings_manager = None

        # Reload from JSON/defaults
        self._config = self._deep_copy_config(DEFAULT_CONFIG)
        self._config_loaded = False
        self._load_config()

    def has_user_context(self) -> bool:
        """Check if user context is currently set.

        Returns:
            True if a user is authenticated and context is set.
        """
        return self._user_context is not None

    def get_user_id(self) -> Optional[int]:
        """Get the current user ID if context is set.

        Returns:
            User ID if context is set, None otherwise.
        """
        return self._user_context.user_id if self._user_context else None

    def get_user_context(self) -> Optional[UserContext]:
        """Get the current user context.

        Returns:
            UserContext if set, None otherwise.
        """
        return self._user_context

    # =========================================================================
    # Configuration Access Methods
    # =========================================================================

    def get_model(self, agent_type: str, default: Optional[str] = None) -> str:
        """
        Get the model name for a specific agent type.

        Args:
            agent_type: Type of agent (counterfactual_agent, query_agent, etc.)
            default: Optional default model to use if agent_type not found

        Returns:
            Model name string
        """
        if default is not None:
            return self._config["models"].get(agent_type, default)
        return self._config["models"].get(agent_type, self._config["models"]["medical_model"])
    
    def get_agent_config(self, agent_type: str) -> Dict[str, Any]:
        """
        Get configuration for a specific agent type.
        
        Args:
            agent_type: Type of agent (counterfactual, scoring, etc.)
            
        Returns:
            Dictionary of agent configuration
        """
        return self._config["agents"].get(agent_type, {})
    
    def get_ollama_config(self) -> Dict[str, Any]:
        """Get Ollama server configuration."""
        return self._config["ollama"]
    
    def get_database_config(self) -> Dict[str, Any]:
        """Get database configuration."""
        return self._config["database"]
    
    def get_search_config(self) -> Dict[str, Any]:
        """Get search configuration."""
        return self._config["search"]
    
    def get(self, key_path: str, default=None):
        """
        Get a configuration value using dot notation.
        
        Args:
            key_path: Path to the configuration key (e.g., "models.query_agent")
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        keys = key_path.split('.')
        current = self._config
        
        try:
            for key in keys:
                current = current[key]
            return current
        except KeyError:
            return default
    
    def set(self, key_path: str, value: Any):
        """
        Set a configuration value using dot notation.
        
        Args:
            key_path: Path to the configuration key (e.g., "models.query_agent")
            value: Value to set
        """
        print(f"🔧 Setting config: {key_path} = {value}")  # Debug
        keys = key_path.split('.')
        current = self._config
        
        # Navigate to the parent dictionary
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        
        # Set the final value
        old_value = current.get(keys[-1], "<not set>")
        current[keys[-1]] = value
        print(f"  Changed from: {old_value} → {value}")  # Debug
    
    def save_config(self, file_path: Optional[str] = None):
        """
        Save current configuration to a file.

        Args:
            file_path: Path to save the config file. If None, saves to ~/.bmlibrarian/config.json
        """
        from .utils.config_loader import save_json_config
        from .utils.path_utils import get_default_config_path
        from pathlib import Path

        if file_path is None:
            file_path = get_default_config_path()
        else:
            file_path = Path(file_path)

        try:
            save_json_config(self._config, file_path)
            print(f"📁 Configuration saved to: {file_path}")  # Debug output
        except IOError as e:
            print(f"❌ Failed to save configuration: {e}")  # Debug output
            raise
    
    def create_sample_config(self, file_path: Optional[str] = None):
        """
        Create a sample configuration file for editing.

        Args:
            file_path: Path to create the sample config. If None, uses default location.
        """
        from .utils.config_loader import save_json_config
        from .utils.path_utils import get_legacy_config_path
        from pathlib import Path

        if file_path is None:
            file_path = get_legacy_config_path()
        else:
            file_path = Path(file_path)

        # Add comments to the sample config
        sample_config = {
            "_comment": "BMLibrarian Configuration File - Edit this file to customize models and settings",
            "_model_options": {
                "fast": "medgemma4B_it_q8:latest",
                "medical": "medgemma-27b-text-it-Q8_0:latest",
                "complex": "gpt-oss:20b",
                "note": "You can use any model available in your Ollama installation"
            },
            **DEFAULT_CONFIG
        }

        try:
            save_json_config(sample_config, file_path)
            print(f"✅ Sample configuration created at: {file_path}")
            print("📝 Edit this file to customize your model settings")
        except IOError as e:
            logger.error(f"Failed to create sample configuration: {e}")

    # =========================================================================
    # Database Sync Operations
    # =========================================================================

    def _sync_from_database(self) -> None:
        """Sync settings from database to in-memory configuration.

        Called internally when user context is set. Loads all user settings
        from the database and merges them into the in-memory configuration.

        Note:
            This is an internal method. Use set_user_context() to trigger
            database synchronization.
        """
        if self._settings_manager is None:
            logger.warning("Cannot sync from database: no user context set")
            return

        try:
            db_settings = self._settings_manager.get_all(use_cache=False)
            for category, settings in db_settings.items():
                if category in self._config and settings:
                    # Merge database settings with defaults
                    self._merge_config({category: settings})
            logger.debug("Synced settings from database to in-memory config")
        except Exception as e:
            logger.warning(f"Failed to sync settings from database: {e}")
            # Continue with in-memory/JSON settings

    def sync_to_database(self) -> bool:
        """Push current in-memory configuration to user's database settings.

        Saves all valid settings categories from the in-memory configuration
        to the database. Requires user context to be set.

        Returns:
            True if sync was successful, False otherwise.

        Raises:
            RuntimeError: If no user context is set.

        Example:
            config = get_config()
            config.set_user_context(user_id=1, connection=conn)
            config.set("models.query_agent", "gpt-oss:20b")
            config.sync_to_database()  # Persists the change
        """
        if self._settings_manager is None:
            raise RuntimeError("Cannot sync to database: no user context set")

        success = True
        for category in VALID_SETTINGS_CATEGORIES:
            if category in self._config:
                try:
                    self._settings_manager.set(category, self._config[category])
                except Exception as e:
                    logger.error(f"Failed to sync category '{category}' to database: {e}")
                    success = False

        if success:
            logger.info("Successfully synced all settings to database")
        return success

    def export_to_json(self, file_path: Path) -> None:
        """Export current configuration to a JSON file.

        Exports the effective configuration (merged user settings + defaults).
        Useful for backing up settings or sharing configuration.

        Args:
            file_path: Path to the JSON file to create/overwrite.

        Example:
            config = get_config()
            config.export_to_json(Path("~/backup_config.json"))
        """
        from .utils.config_loader import save_json_config
        from .utils.path_utils import expand_path

        expanded_path = expand_path(str(file_path))
        save_json_config(self._config, expanded_path)
        logger.info(f"Exported configuration to: {expanded_path}")

    def import_from_json(self, file_path: Path, sync_to_db: bool = True) -> None:
        """Import configuration from a JSON file.

        Loads settings from a JSON file and merges them into the current
        configuration. If user context is set and sync_to_db is True,
        the imported settings are also saved to the database.

        Args:
            file_path: Path to the JSON configuration file.
            sync_to_db: If True and user context is set, sync to database.

        Raises:
            FileNotFoundError: If the file does not exist.
            json.JSONDecodeError: If the file is not valid JSON.

        Example:
            config = get_config()
            config.set_user_context(user_id=1, connection=conn)
            config.import_from_json(Path("~/backup_config.json"))
            # Settings are now loaded and saved to database
        """
        from .utils.config_loader import load_json_config
        from .utils.path_utils import expand_path

        expanded_path = expand_path(str(file_path))
        imported_config = load_json_config(expanded_path)

        if imported_config:
            self._merge_config(imported_config)
            logger.info(f"Imported configuration from: {expanded_path}")

            # Optionally sync to database if user context is set
            if sync_to_db and self._settings_manager is not None:
                self.sync_to_database()
        else:
            logger.warning(f"No valid configuration found in: {expanded_path}")

    def reset_to_defaults(self, categories: Optional[List[str]] = None) -> None:
        """Reset configuration to defaults.

        If user context is set, deletes user settings from database for
        the specified categories (or all categories if not specified).
        Always resets in-memory configuration.

        Args:
            categories: List of category names to reset. If None, resets all.

        Example:
            config = get_config()
            config.reset_to_defaults(['models', 'agents'])  # Reset specific
            config.reset_to_defaults()  # Reset all
        """
        target_categories = categories or list(VALID_SETTINGS_CATEGORIES)

        # Reset in-memory config for specified categories
        for category in target_categories:
            if category in DEFAULT_CONFIG:
                self._config[category] = self._deep_copy_config(DEFAULT_CONFIG[category])

        # If user context is set, also reset database settings
        if self._settings_manager is not None:
            for category in target_categories:
                if category in VALID_SETTINGS_CATEGORIES:
                    try:
                        self._settings_manager.reset_category(category)
                    except Exception as e:
                        logger.error(f"Failed to reset category '{category}' in database: {e}")

        logger.info(f"Reset configuration to defaults for categories: {target_categories}")


# Global configuration instance
_config_instance = None

def get_config() -> BMLibrarianConfig:
    """Get the global configuration instance."""
    global _config_instance
    if _config_instance is None:
        _config_instance = BMLibrarianConfig()
    return _config_instance

def reload_config():
    """Reload configuration from files."""
    global _config_instance
    _config_instance = BMLibrarianConfig()

# Convenience functions for common operations
def get_model(agent_type: str, default: Optional[str] = None) -> str:
    """Get model name for an agent type.

    Args:
        agent_type: Type of agent (counterfactual_agent, query_agent, etc.)
        default: Optional default model to use if agent_type not found

    Returns:
        Model name string
    """
    return get_config().get_model(agent_type, default=default)

def get_agent_config(agent_type: str) -> Dict[str, Any]:
    """Get agent configuration."""
    return get_config().get_agent_config(agent_type)

def get_ollama_host() -> str:
    """Get Ollama host URL."""
    return get_config().get_ollama_config()["host"]

def get_search_config() -> Dict[str, Any]:
    """Get search configuration."""
    return get_config().get_search_config()

def get_query_generation_config() -> Dict[str, Any]:
    """Get query generation configuration."""
    return get_config().get("query_generation", DEFAULT_CONFIG["query_generation"])

def get_openathens_config(validate: bool = False) -> Dict[str, Any]:
    """Get OpenAthens proxy configuration.

    Args:
        validate: If True, validate the configuration and raise ValueError
            if the institution_url is invalid. Default is False for backward
            compatibility.

    Returns:
        Dictionary with OpenAthens configuration:
        - enabled (bool): Enable OpenAthens proxy
        - institution_url (str): Institution's OpenAthens URL
        - session_timeout_hours (int): Session timeout in hours
        - auto_login (bool): Auto-login on startup
        - login_timeout (int): Maximum seconds to wait for login
        - headless (bool): Run browser in headless mode

    Raises:
        ValueError: If validate=True and the configuration is invalid.
    """
    config = get_config().get("openathens", DEFAULT_CONFIG["openathens"])
    if validate and config.get("enabled", False):
        result = validate_openathens_config(config)
        result.raise_if_invalid()
    return config


def validate_openathens_url(url: str) -> ValidationResult:
    """Validate an OpenAthens institution URL.

    Validates that:
    - URL is not empty
    - URL uses HTTPS protocol (required for security)
    - URL has a valid hostname

    Args:
        url: The institution URL to validate.

    Returns:
        ValidationResult with valid=True if URL is valid,
        or valid=False with errors explaining why.
    """
    from urllib.parse import urlparse

    errors: List[str] = []
    warnings: List[str] = []

    if not url:
        errors.append("Institution URL cannot be empty")
        return ValidationResult(valid=False, errors=errors, warnings=warnings)

    if not isinstance(url, str):
        errors.append(f"Institution URL must be a string, got {type(url).__name__}")
        return ValidationResult(valid=False, errors=errors, warnings=warnings)

    url = url.strip()
    if not url:
        errors.append("Institution URL cannot be empty or whitespace only")
        return ValidationResult(valid=False, errors=errors, warnings=warnings)

    try:
        parsed = urlparse(url)
    except Exception as e:
        errors.append(f"Invalid URL format: {e}")
        return ValidationResult(valid=False, errors=errors, warnings=warnings)

    # Require HTTPS for security
    if parsed.scheme != 'https':
        if parsed.scheme == 'http':
            errors.append(
                f"Institution URL must use HTTPS (not HTTP) for security: {url}"
            )
        elif not parsed.scheme:
            errors.append(
                f"Institution URL must include https:// scheme: {url}"
            )
        else:
            errors.append(
                f"Institution URL must use HTTPS, got scheme '{parsed.scheme}': {url}"
            )

    # Require hostname
    if not parsed.netloc:
        errors.append(f"Institution URL must include a hostname: {url}")

    # Warn about suspicious patterns
    if parsed.netloc and '..' in parsed.netloc:
        warnings.append(f"Institution URL hostname contains unusual '..' pattern: {url}")

    if parsed.netloc and len(parsed.netloc) > 253:
        errors.append(f"Institution URL hostname exceeds maximum length (253 chars): {url}")

    return ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings
    )


def validate_openathens_config(config: Dict[str, Any]) -> ValidationResult:
    """Validate OpenAthens configuration.

    Validates that:
    - If enabled, institution_url is valid (HTTPS, has hostname)
    - session_timeout_hours is a positive integer
    - login_timeout is a positive integer

    Args:
        config: OpenAthens configuration dictionary.

    Returns:
        ValidationResult with valid=True if configuration is valid,
        or valid=False with errors list containing all validation failures.
    """
    errors: List[str] = []
    warnings: List[str] = []

    enabled = config.get("enabled", False)

    # If not enabled, configuration is valid (URL not required)
    if not enabled:
        return ValidationResult(valid=True, errors=[], warnings=[])

    # Validate institution_url
    institution_url = config.get("institution_url", "")
    url_result = validate_openathens_url(institution_url)
    errors.extend(url_result.errors)
    warnings.extend(url_result.warnings)

    # Validate session_timeout_hours
    timeout_hours = config.get("session_timeout_hours")
    if timeout_hours is not None:
        if not isinstance(timeout_hours, (int, float)):
            errors.append(
                f"session_timeout_hours must be a number, got {type(timeout_hours).__name__}"
            )
        elif timeout_hours <= 0:
            errors.append(
                f"session_timeout_hours must be positive, got {timeout_hours}"
            )

    # Validate login_timeout
    login_timeout = config.get("login_timeout")
    if login_timeout is not None:
        if not isinstance(login_timeout, (int, float)):
            errors.append(
                f"login_timeout must be a number, got {type(login_timeout).__name__}"
            )
        elif login_timeout <= 0:
            errors.append(
                f"login_timeout must be positive, got {login_timeout}"
            )

    return ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings
    )


def get_discovery_config() -> Dict[str, Any]:
    """Get PDF discovery configuration.

    Returns:
        Dictionary with discovery configuration:
        - timeout (int): HTTP request timeout in seconds
        - prefer_open_access (bool): Prioritize open access sources
        - use_browser_fallback (bool): Use browser when HTTP fails
        - browser_headless (bool): Run browser in headless mode
        - browser_timeout (int): Browser timeout in milliseconds
        - use_openathens_proxy (bool): Use OpenAthens as last resort
    """
    return get_config().get("discovery", DEFAULT_CONFIG["discovery"])


def get_embeddings_config() -> Dict[str, Any]:
    """Get embeddings configuration.

    Returns:
        Dictionary with embeddings configuration:
        - backend (str): Embedding backend ("ollama", "ollama_http", "sentence_transformers", "llama_cpp")
        - model (str): Ollama-style model name
        - huggingface_model (str): HuggingFace model ID for sentence_transformers
        - batch_size (int): Batch size for embedding generation
        - n_ctx (int): Context window size (for llama_cpp)
        - device (str): Device for sentence_transformers ("auto", "cpu", "cuda", "mps")
    """
    return get_config().get("embeddings", DEFAULT_CONFIG["embeddings"])


def get_paper_weight_config() -> Dict[str, Any]:
    """Get paper weight assessment configuration.

    Returns:
        Dictionary with paper weight assessment configuration including:
        - model (str): Ollama model to use
        - temperature (float): LLM temperature
        - top_p (float): Nucleus sampling parameter
        - version (str): Assessor version for database versioning
        - dimension_weights (dict): Weights for each assessment dimension
        - study_type_hierarchy (dict): Baseline scores for study types
        - study_type_keywords (dict): Keywords for study type detection
        - sample_size_scoring (dict): Parameters for sample size scoring
        - methodological_quality_weights (dict): Sub-component weights
        - risk_of_bias_weights (dict): Risk of bias domain weights
        - attrition_thresholds (dict): Attrition rate quality thresholds
    """
    return get_config().get_agent_config("paper_weight_assessment")


def validate_paper_weight_config(config: Dict[str, Any]) -> ValidationResult:
    """
    Validate paper weight assessment configuration.

    Validates that:
    - Model name is in valid format (non-empty string with model:tag pattern)
    - Temperature is within valid range (0.0-2.0)
    - Top_p is within valid range (0.0-1.0)
    - Dimension weights sum to 1.0 (±FLOAT_TOLERANCE for JSON serialization precision)
    - All dimension weights are non-negative
    - Study type hierarchy scores are in valid range (0-10)
    - Study type keywords lists are non-empty when defined
    - Methodological quality weights sum to 10.0
    - Risk of bias weights sum to 10.0
    - Attrition thresholds are in ascending order

    Args:
        config: Paper weight assessment configuration dictionary

    Returns:
        ValidationResult with valid=True if configuration is valid,
        or valid=False with errors list containing all validation failures

    Note:
        For backward compatibility, callers can use result.raise_if_invalid()
        to get the previous exception-based behavior.
    """
    errors: List[str] = []
    warnings: List[str] = []

    # ==========================================================================
    # Model name validation
    # ==========================================================================
    model = config.get("model", "")
    if model:
        # Basic format check: model name should be non-empty and reasonably formatted
        # Ollama models typically follow "name:tag" or "name" pattern
        if not isinstance(model, str) or len(model.strip()) == 0:
            errors.append("model must be a non-empty string")
        elif len(model) > 256:
            errors.append(f"model name exceeds maximum length (256 chars), got {len(model)}")
        elif not all(c.isalnum() or c in '-_:./' for c in model):
            warnings.append(
                f"model '{model}' contains unusual characters; "
                "typical format is 'name:tag' (e.g., 'gpt-oss:20b')"
            )

    # ==========================================================================
    # Temperature validation
    # ==========================================================================
    temperature = config.get("temperature")
    if temperature is not None:
        if not isinstance(temperature, (int, float)):
            errors.append(f"temperature must be a number, got {type(temperature).__name__}")
        elif not (TEMPERATURE_MIN <= temperature <= TEMPERATURE_MAX):
            errors.append(
                f"temperature must be between {TEMPERATURE_MIN} and {TEMPERATURE_MAX}, "
                f"got {temperature}"
            )

    # ==========================================================================
    # Top_p validation
    # ==========================================================================
    top_p = config.get("top_p")
    if top_p is not None:
        if not isinstance(top_p, (int, float)):
            errors.append(f"top_p must be a number, got {type(top_p).__name__}")
        elif not (TOP_P_MIN <= top_p <= TOP_P_MAX):
            errors.append(
                f"top_p must be between {TOP_P_MIN} and {TOP_P_MAX}, got {top_p}"
            )

    # ==========================================================================
    # Dimension weights validation
    # ==========================================================================
    weights = config.get("dimension_weights", {})
    if not weights:
        errors.append("dimension_weights is required")
    else:
        weight_sum = sum(weights.values())
        weight_lower = WEIGHT_SUM_EXPECTED - FLOAT_TOLERANCE
        weight_upper = WEIGHT_SUM_EXPECTED + FLOAT_TOLERANCE
        if not (weight_lower <= weight_sum <= weight_upper):
            errors.append(
                f"Dimension weights must sum to {WEIGHT_SUM_EXPECTED} "
                f"(±{FLOAT_TOLERANCE} for floating point precision), got {weight_sum:.4f}"
            )

        # Check all dimension weights are non-negative
        for key, value in weights.items():
            if value < 0:
                errors.append(f"Dimension weight '{key}' must be non-negative, got {value}")

    # ==========================================================================
    # Study type hierarchy validation
    # ==========================================================================
    hierarchy = config.get("study_type_hierarchy", {})
    for study_type, score in hierarchy.items():
        if not (0 <= score <= 10):
            errors.append(
                f"Study type hierarchy score for '{study_type}' must be between 0 and 10, "
                f"got {score}"
            )

    # ==========================================================================
    # Study type keywords validation
    # ==========================================================================
    keywords = config.get("study_type_keywords", {})
    for study_type, keyword_list in keywords.items():
        if not isinstance(keyword_list, list):
            errors.append(
                f"study_type_keywords['{study_type}'] must be a list, "
                f"got {type(keyword_list).__name__}"
            )
        elif len(keyword_list) == 0:
            errors.append(
                f"study_type_keywords['{study_type}'] must contain at least one keyword"
            )
        else:
            # Check that all keywords are non-empty strings
            for i, kw in enumerate(keyword_list):
                if not isinstance(kw, str) or len(kw.strip()) == 0:
                    errors.append(
                        f"study_type_keywords['{study_type}'][{i}] must be a non-empty string"
                    )

    # ==========================================================================
    # Methodological quality weights validation
    # ==========================================================================
    mq_weights = config.get("methodological_quality_weights", {})
    if mq_weights:
        mq_sum = sum(mq_weights.values())
        mq_lower = QUALITY_WEIGHT_SUM_EXPECTED - FLOAT_TOLERANCE * QUALITY_WEIGHT_TOLERANCE_MULTIPLIER
        mq_upper = QUALITY_WEIGHT_SUM_EXPECTED + FLOAT_TOLERANCE * QUALITY_WEIGHT_TOLERANCE_MULTIPLIER
        if not (mq_lower <= mq_sum <= mq_upper):
            errors.append(
                f"Methodological quality weights must sum to {QUALITY_WEIGHT_SUM_EXPECTED}, "
                f"got {mq_sum:.4f}"
            )
        # Check all weights are non-negative
        for key, value in mq_weights.items():
            if value < 0:
                errors.append(
                    f"Methodological quality weight '{key}' must be non-negative, got {value}"
                )

    # ==========================================================================
    # Risk of bias weights validation
    # ==========================================================================
    rob_weights = config.get("risk_of_bias_weights", {})
    if rob_weights:
        rob_sum = sum(rob_weights.values())
        rob_lower = QUALITY_WEIGHT_SUM_EXPECTED - FLOAT_TOLERANCE * QUALITY_WEIGHT_TOLERANCE_MULTIPLIER
        rob_upper = QUALITY_WEIGHT_SUM_EXPECTED + FLOAT_TOLERANCE * QUALITY_WEIGHT_TOLERANCE_MULTIPLIER
        if not (rob_lower <= rob_sum <= rob_upper):
            errors.append(
                f"Risk of bias weights must sum to {QUALITY_WEIGHT_SUM_EXPECTED}, "
                f"got {rob_sum:.4f}"
            )
        # Check all weights are non-negative
        for key, value in rob_weights.items():
            if value < 0:
                errors.append(
                    f"Risk of bias weight '{key}' must be non-negative, got {value}"
                )

    # ==========================================================================
    # Attrition thresholds validation
    # ==========================================================================
    thresholds = config.get("attrition_thresholds", {})
    if thresholds:
        excellent = thresholds.get("excellent", 0)
        good = thresholds.get("good", 0)
        acceptable = thresholds.get("acceptable", 0)

        if not (excellent < good < acceptable):
            errors.append(
                f"Attrition thresholds must be in ascending order "
                f"(excellent < good < acceptable), got excellent={excellent}, "
                f"good={good}, acceptable={acceptable}"
            )

        # Check thresholds are valid proportions (0-1)
        for key, value in thresholds.items():
            if not (0 <= value <= 1):
                errors.append(
                    f"Attrition threshold '{key}' must be between 0 and 1, got {value}"
                )

    # ==========================================================================
    # Sample size scoring parameters validation
    # ==========================================================================
    sample_scoring = config.get("sample_size_scoring", {})
    if sample_scoring:
        # Validate log_base (must be a positive integer >= 2)
        log_base = sample_scoring.get("log_base")
        if log_base is not None:
            if not isinstance(log_base, int):
                errors.append(
                    f"sample_size_scoring.log_base must be an integer, got {type(log_base).__name__}"
                )
            elif log_base < 2:
                errors.append(
                    f"sample_size_scoring.log_base must be >= 2, got {log_base}"
                )

        log_multiplier = sample_scoring.get("log_multiplier", 2.0)
        if log_multiplier <= 0:
            errors.append(
                f"sample_size_scoring.log_multiplier must be positive, got {log_multiplier}"
            )

        power_bonus = sample_scoring.get("power_calculation_bonus", 0)
        if power_bonus < 0:
            errors.append(
                f"sample_size_scoring.power_calculation_bonus must be non-negative, "
                f"got {power_bonus}"
            )

        ci_bonus = sample_scoring.get("ci_reported_bonus", 0)
        if ci_bonus < 0:
            errors.append(
                f"sample_size_scoring.ci_reported_bonus must be non-negative, got {ci_bonus}"
            )

    return ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings
    )


def validate_paper_weight_config_legacy(config: Dict[str, Any]) -> None:
    """
    Legacy validation function that raises ValueError on validation failure.

    This function provides backward compatibility for code that expects
    exception-based error handling rather than the ValidationResult approach.

    Args:
        config: Paper weight assessment configuration dictionary

    Raises:
        ValueError: If validation fails, with all errors concatenated as message

    Example:
        >>> validate_paper_weight_config_legacy(invalid_config)
        ValueError: dimension_weights is required; temperature must be between 0.0 and 2.0
    """
    result = validate_paper_weight_config(config)
    result.raise_if_invalid()
