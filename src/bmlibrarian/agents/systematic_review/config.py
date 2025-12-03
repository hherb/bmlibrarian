"""
Configuration Management for SystematicReviewAgent

Provides configuration loading, validation, and defaults for the
SystematicReviewAgent. Integrates with the main BMLibrarianConfig system.

Configuration Categories:
- Agent-specific settings (model, temperature, etc.)
- Scoring dimension weights
- Search strategy parameters
- Quality gate thresholds
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ...config import (
    get_config,
    get_model,
    get_ollama_host,
    get_agent_config,
    ValidationResult,
)
from .data_models import ScoringWeights

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Agent name for configuration lookup
AGENT_TYPE = "systematic_review"
AGENT_MODEL_KEY = "systematic_review_agent"

# Default configuration values
DEFAULT_MODEL = "gpt-oss:20b"
DEFAULT_EMBEDDING_MODEL = "nomic-embed-text:latest"
DEFAULT_TEMPERATURE = 0.2
DEFAULT_TOP_P = 0.9
DEFAULT_MAX_TOKENS = 4000

# Search defaults
DEFAULT_MAX_SEARCH_RESULTS = 500
DEFAULT_MAX_RESULTS_PER_QUERY = 100
DEFAULT_RELEVANCE_THRESHOLD = 2.5
DEFAULT_QUALITY_THRESHOLD = 4.0

# Batch processing defaults
DEFAULT_BATCH_SIZE = 50
DEFAULT_MAX_RETRIES = 3

# Checkpoint defaults
DEFAULT_CHECKPOINT_ENABLED = True
DEFAULT_CHECKPOINT_DIR = "~/.bmlibrarian/checkpoints"

# Output defaults
DEFAULT_OUTPUT_DIR = "~/.bmlibrarian/systematic_reviews"


# =============================================================================
# Configuration Dataclass
# =============================================================================

@dataclass
class SystematicReviewConfig:
    """
    Configuration container for SystematicReviewAgent.

    Consolidates all settings needed for running a systematic review,
    including model parameters, search settings, and thresholds.

    Attributes:
        model: Ollama model name for LLM operations
        host: Ollama server URL
        temperature: LLM temperature (0.0-1.0)
        top_p: LLM nucleus sampling parameter
        max_tokens: Maximum tokens per LLM response

        max_search_results: Maximum papers to retrieve from search
        max_results_per_query: Maximum results per individual search query
        relevance_threshold: Minimum relevance score (1-5) for inclusion
        quality_threshold: Minimum quality score (0-10) for final ranking
        batch_size: Papers to process per batch
        max_retries: Maximum retry attempts for failed operations

        scoring_weights: Weights for composite score calculation
        checkpoint_enabled: Whether to save checkpoints
        checkpoint_dir: Directory for checkpoint files

        search_strategies: Which search strategies to use
        study_type_filter: Allowed study types (None = all)

    Example:
        >>> config = SystematicReviewConfig.load_from_bmlibrarian_config()
        >>> agent = SystematicReviewAgent(config=config)
    """

    # Model settings
    model: str = DEFAULT_MODEL
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    host: str = "http://localhost:11434"
    temperature: float = DEFAULT_TEMPERATURE
    top_p: float = DEFAULT_TOP_P
    max_tokens: int = DEFAULT_MAX_TOKENS

    # Search settings
    max_search_results: int = DEFAULT_MAX_SEARCH_RESULTS
    max_results_per_query: int = DEFAULT_MAX_RESULTS_PER_QUERY
    relevance_threshold: float = DEFAULT_RELEVANCE_THRESHOLD
    quality_threshold: float = DEFAULT_QUALITY_THRESHOLD
    batch_size: int = DEFAULT_BATCH_SIZE
    max_retries: int = DEFAULT_MAX_RETRIES

    # Scoring settings
    scoring_weights: ScoringWeights = field(default_factory=ScoringWeights)

    # Checkpoint settings
    checkpoint_enabled: bool = DEFAULT_CHECKPOINT_ENABLED
    checkpoint_dir: str = DEFAULT_CHECKPOINT_DIR

    # Output settings
    output_dir: str = DEFAULT_OUTPUT_DIR

    # Search strategy settings
    search_strategies: List[str] = field(
        default_factory=lambda: ["semantic", "keyword"]
    )
    study_type_filter: Optional[List[str]] = None

    # Feature flags (partial assessment support)
    run_study_assessment: bool = True
    run_paper_weight: bool = True
    run_pico_extraction: bool = True
    run_prisma_assessment: bool = True

    # Cache settings
    use_results_cache: bool = True
    force_recompute: bool = False  # Bypass cache and recompute assessments

    # Evidence synthesis settings
    enable_evidence_synthesis: bool = True
    synthesis_model: Optional[str] = None  # Defaults to main model
    citation_min_relevance: float = 0.7
    max_citations_per_paper: int = 3
    synthesis_temperature: float = 0.3

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert configuration to dictionary.

        Returns:
            Dictionary representation suitable for JSON serialization
        """
        return {
            "model": self.model,
            "embedding_model": self.embedding_model,
            "host": self.host,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
            "max_search_results": self.max_search_results,
            "max_results_per_query": self.max_results_per_query,
            "relevance_threshold": self.relevance_threshold,
            "quality_threshold": self.quality_threshold,
            "batch_size": self.batch_size,
            "max_retries": self.max_retries,
            "scoring_weights": self.scoring_weights.to_dict(),
            "checkpoint_enabled": self.checkpoint_enabled,
            "checkpoint_dir": self.checkpoint_dir,
            "output_dir": self.output_dir,
            "search_strategies": self.search_strategies,
            "study_type_filter": self.study_type_filter,
            "run_study_assessment": self.run_study_assessment,
            "run_paper_weight": self.run_paper_weight,
            "run_pico_extraction": self.run_pico_extraction,
            "run_prisma_assessment": self.run_prisma_assessment,
            "use_results_cache": self.use_results_cache,
            "force_recompute": self.force_recompute,
            "enable_evidence_synthesis": self.enable_evidence_synthesis,
            "synthesis_model": self.synthesis_model,
            "citation_min_relevance": self.citation_min_relevance,
            "max_citations_per_paper": self.max_citations_per_paper,
            "synthesis_temperature": self.synthesis_temperature,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SystematicReviewConfig":
        """
        Create configuration from dictionary.

        Args:
            data: Dictionary with configuration values

        Returns:
            New SystematicReviewConfig instance
        """
        # Handle scoring_weights specially
        weights_data = data.get("scoring_weights")
        if weights_data:
            scoring_weights = ScoringWeights.from_dict(weights_data)
        else:
            scoring_weights = ScoringWeights()

        return cls(
            model=data.get("model", DEFAULT_MODEL),
            embedding_model=data.get("embedding_model", DEFAULT_EMBEDDING_MODEL),
            host=data.get("host", "http://localhost:11434"),
            temperature=data.get("temperature", DEFAULT_TEMPERATURE),
            top_p=data.get("top_p", DEFAULT_TOP_P),
            max_tokens=data.get("max_tokens", DEFAULT_MAX_TOKENS),
            max_search_results=data.get("max_search_results", DEFAULT_MAX_SEARCH_RESULTS),
            max_results_per_query=data.get("max_results_per_query", DEFAULT_MAX_RESULTS_PER_QUERY),
            relevance_threshold=data.get("relevance_threshold", DEFAULT_RELEVANCE_THRESHOLD),
            quality_threshold=data.get("quality_threshold", DEFAULT_QUALITY_THRESHOLD),
            batch_size=data.get("batch_size", DEFAULT_BATCH_SIZE),
            max_retries=data.get("max_retries", DEFAULT_MAX_RETRIES),
            scoring_weights=scoring_weights,
            checkpoint_enabled=data.get("checkpoint_enabled", DEFAULT_CHECKPOINT_ENABLED),
            checkpoint_dir=data.get("checkpoint_dir", DEFAULT_CHECKPOINT_DIR),
            output_dir=data.get("output_dir", DEFAULT_OUTPUT_DIR),
            search_strategies=data.get("search_strategies", ["semantic", "keyword"]),
            study_type_filter=data.get("study_type_filter"),
            run_study_assessment=data.get("run_study_assessment", True),
            run_paper_weight=data.get("run_paper_weight", True),
            run_pico_extraction=data.get("run_pico_extraction", True),
            run_prisma_assessment=data.get("run_prisma_assessment", True),
            use_results_cache=data.get("use_results_cache", True),
            force_recompute=data.get("force_recompute", False),
            enable_evidence_synthesis=data.get("enable_evidence_synthesis", True),
            synthesis_model=data.get("synthesis_model"),
            citation_min_relevance=data.get("citation_min_relevance", 0.7),
            max_citations_per_paper=data.get("max_citations_per_paper", 3),
            synthesis_temperature=data.get("synthesis_temperature", 0.3),
        )

    @classmethod
    def load_from_bmlibrarian_config(cls) -> "SystematicReviewConfig":
        """
        Load configuration from BMLibrarian's central config system.

        Reads settings from ~/.bmlibrarian/config.json and merges
        with defaults. Falls back to DEFAULT_MODEL if model not configured.

        Returns:
            SystematicReviewConfig with values from config file
        """
        try:
            config = get_config()

            # Get model (fall back to complex_model if specific not set)
            model = get_model(AGENT_MODEL_KEY, default=None)
            if model is None:
                model = get_model("complex_model", default=DEFAULT_MODEL)

            # Get host from ollama config
            host = get_ollama_host()

            # Get agent-specific config
            agent_config = get_agent_config(AGENT_TYPE)

            # Get search config for some defaults
            search_config = config.get_search_config()

            # Build scoring weights from config if present
            weights_config = agent_config.get("scoring_weights")
            if weights_config:
                scoring_weights = ScoringWeights.from_dict(weights_config)
            else:
                scoring_weights = ScoringWeights()

            # Get embedding model from config or use default
            embedding_model = agent_config.get(
                "embedding_model",
                DEFAULT_EMBEDDING_MODEL
            )

            return cls(
                model=model,
                embedding_model=embedding_model,
                host=host,
                temperature=agent_config.get("temperature", DEFAULT_TEMPERATURE),
                top_p=agent_config.get("top_p", DEFAULT_TOP_P),
                max_tokens=agent_config.get("max_tokens", DEFAULT_MAX_TOKENS),
                max_search_results=agent_config.get(
                    "max_search_results",
                    search_config.get("max_results", DEFAULT_MAX_SEARCH_RESULTS)
                ),
                max_results_per_query=agent_config.get(
                    "max_results_per_query",
                    DEFAULT_MAX_RESULTS_PER_QUERY
                ),
                relevance_threshold=agent_config.get(
                    "relevance_threshold",
                    search_config.get("score_threshold", DEFAULT_RELEVANCE_THRESHOLD)
                ),
                quality_threshold=agent_config.get(
                    "quality_threshold",
                    DEFAULT_QUALITY_THRESHOLD
                ),
                batch_size=agent_config.get("batch_size", DEFAULT_BATCH_SIZE),
                max_retries=agent_config.get("max_retries", DEFAULT_MAX_RETRIES),
                scoring_weights=scoring_weights,
                checkpoint_enabled=agent_config.get(
                    "checkpoint_enabled",
                    DEFAULT_CHECKPOINT_ENABLED
                ),
                checkpoint_dir=agent_config.get(
                    "checkpoint_dir",
                    DEFAULT_CHECKPOINT_DIR
                ),
                output_dir=agent_config.get(
                    "output_dir",
                    DEFAULT_OUTPUT_DIR
                ),
                search_strategies=agent_config.get(
                    "search_strategies",
                    ["semantic", "keyword"]
                ),
                study_type_filter=agent_config.get("study_type_filter"),
                run_study_assessment=agent_config.get("run_study_assessment", True),
                run_paper_weight=agent_config.get("run_paper_weight", True),
                run_pico_extraction=agent_config.get("run_pico_extraction", True),
                run_prisma_assessment=agent_config.get("run_prisma_assessment", True),
                use_results_cache=agent_config.get("use_results_cache", True),
                force_recompute=agent_config.get("force_recompute", False),
            )

        except Exception as e:
            logger.warning(
                f"Failed to load config from BMLibrarian config system: {e}. "
                "Using defaults."
            )
            return cls()

    def validate(self) -> ValidationResult:
        """
        Validate configuration settings.

        Checks all parameters are within valid ranges and
        scoring weights sum to 1.0.

        Returns:
            ValidationResult with errors and warnings
        """
        errors: List[str] = []
        warnings: List[str] = []

        # Validate model
        if not self.model or not self.model.strip():
            errors.append("Model name cannot be empty")

        # Validate temperature
        if not (0.0 <= self.temperature <= 2.0):
            errors.append(f"Temperature must be between 0.0 and 2.0, got {self.temperature}")

        # Validate top_p
        if not (0.0 <= self.top_p <= 1.0):
            errors.append(f"Top_p must be between 0.0 and 1.0, got {self.top_p}")

        # Validate max_tokens
        if self.max_tokens < 100:
            errors.append(f"Max tokens must be at least 100, got {self.max_tokens}")

        # Validate thresholds
        if not (1.0 <= self.relevance_threshold <= 5.0):
            errors.append(
                f"Relevance threshold must be between 1.0 and 5.0, "
                f"got {self.relevance_threshold}"
            )

        if not (0.0 <= self.quality_threshold <= 10.0):
            errors.append(
                f"Quality threshold must be between 0.0 and 10.0, "
                f"got {self.quality_threshold}"
            )

        # Validate batch size
        if self.batch_size < 1:
            errors.append(f"Batch size must be at least 1, got {self.batch_size}")

        # Validate max_search_results
        if self.max_search_results < 1:
            errors.append(
                f"Max search results must be at least 1, got {self.max_search_results}"
            )

        # Validate max_results_per_query
        if self.max_results_per_query < 1:
            errors.append(
                f"Max results per query must be at least 1, got {self.max_results_per_query}"
            )

        # Validate scoring weights
        weight_errors = self.scoring_weights.get_validation_errors()
        errors.extend(weight_errors)

        # Validate search strategies
        valid_strategies = {"semantic", "keyword", "hybrid", "sql", "hyde"}
        for strategy in self.search_strategies:
            if strategy not in valid_strategies:
                warnings.append(
                    f"Unknown search strategy '{strategy}'. "
                    f"Valid strategies: {valid_strategies}"
                )

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )


# =============================================================================
# Default Configuration
# =============================================================================

# Default configuration that can be added to DEFAULT_CONFIG in config.py
DEFAULT_SYSTEMATIC_REVIEW_CONFIG: Dict[str, Any] = {
    "model": DEFAULT_MODEL,
    "embedding_model": DEFAULT_EMBEDDING_MODEL,
    "temperature": DEFAULT_TEMPERATURE,
    "top_p": DEFAULT_TOP_P,
    "max_tokens": DEFAULT_MAX_TOKENS,
    "max_search_results": DEFAULT_MAX_SEARCH_RESULTS,
    "max_results_per_query": DEFAULT_MAX_RESULTS_PER_QUERY,
    "relevance_threshold": DEFAULT_RELEVANCE_THRESHOLD,
    "quality_threshold": DEFAULT_QUALITY_THRESHOLD,
    "batch_size": DEFAULT_BATCH_SIZE,
    "max_retries": DEFAULT_MAX_RETRIES,
    "checkpoint_enabled": DEFAULT_CHECKPOINT_ENABLED,
    "checkpoint_dir": DEFAULT_CHECKPOINT_DIR,
    "output_dir": DEFAULT_OUTPUT_DIR,
    "search_strategies": ["semantic", "keyword"],
    "study_type_filter": None,
    "run_study_assessment": True,
    "run_paper_weight": True,
    "run_pico_extraction": True,
    "run_prisma_assessment": True,
    "use_results_cache": True,
    "force_recompute": False,
    "scoring_weights": {
        "relevance": 0.30,
        "study_quality": 0.25,
        "methodological_rigor": 0.20,
        "sample_size": 0.10,
        "recency": 0.10,
        "replication_status": 0.05,
    }
}


# =============================================================================
# Helper Functions
# =============================================================================

def get_systematic_review_config() -> SystematicReviewConfig:
    """
    Get SystematicReviewAgent configuration from the config system.

    Convenience function that loads and validates configuration.

    Returns:
        Validated SystematicReviewConfig instance

    Raises:
        ValueError: If configuration is invalid
    """
    config = SystematicReviewConfig.load_from_bmlibrarian_config()
    result = config.validate()

    if result.warnings:
        for warning in result.warnings:
            logger.warning(f"Config warning: {warning}")

    if not result.valid:
        raise ValueError(
            f"Invalid SystematicReviewAgent configuration: {'; '.join(result.errors)}"
        )

    return config


def get_default_config() -> SystematicReviewConfig:
    """
    Get default SystematicReviewAgent configuration.

    Uses hardcoded defaults without loading from config files.
    Useful for testing or when config system is unavailable.

    Returns:
        SystematicReviewConfig with default values
    """
    return SystematicReviewConfig()
