"""
Configuration Management for BMLibrarian

Provides centralized configuration for models, settings, and other parameters.
Supports both environment variables and configuration files.
"""

import json
import os
import logging
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

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
    }
}

class BMLibrarianConfig:
    """
    Configuration manager for BMLibrarian.
    
    Handles loading configuration from files, environment variables,
    and provides easy access to configuration values.
    """
    
    def __init__(self):
        self._config = DEFAULT_CONFIG.copy()
        self._config_loaded = False
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