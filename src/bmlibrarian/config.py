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
            "max_tokens": 100
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
        "counterfactual_max_results": 10,  # Max results per counterfactual query
        "counterfactual_min_score": 3,  # Min score for counterfactual evidence
        "query_retry_attempts": 3,  # Number of times to retry failed tsquery with reformulation
        "auto_fix_tsquery_syntax": True  # Automatically fix common tsquery syntax errors
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
        config_paths = [
            os.path.expanduser("~/.bmlibrarian/config.json"),  # Primary location
            os.path.join(os.getcwd(), "bmlibrarian_config.json"),  # Fallback for current directory
            os.path.join(os.path.dirname(__file__), "..", "..", "bmlibrarian_config.json")  # Project root fallback
        ]
        
        for config_path in config_paths:
            if os.path.exists(config_path):
                try:
                    with open(config_path, 'r') as f:
                        file_config = json.load(f)
                    self._merge_config(file_config)
                    logger.info(f"Loaded configuration from: {config_path}")
                    break
                except (json.JSONDecodeError, IOError) as e:
                    logger.warning(f"Failed to load config from {config_path}: {e}")
        
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
    
    def get_model(self, agent_type: str) -> str:
        """
        Get the model name for a specific agent type.
        
        Args:
            agent_type: Type of agent (counterfactual_agent, query_agent, etc.)
            
        Returns:
            Model name string
        """
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
        if file_path is None:
            file_path = os.path.expanduser("~/.bmlibrarian/config.json")
        
        try:
            # Ensure the directory exists (OS agnostic)
            config_dir = os.path.dirname(file_path)
            os.makedirs(config_dir, exist_ok=True)
            
            with open(file_path, 'w') as f:
                json.dump(self._config, f, indent=2)
            logger.info(f"Configuration saved to: {file_path}")
            print(f"📁 Configuration saved to: {file_path}")  # Debug output
        except IOError as e:
            logger.error(f"Failed to save configuration: {e}")
            print(f"❌ Failed to save configuration: {e}")  # Debug output
            raise
    
    def create_sample_config(self, file_path: Optional[str] = None):
        """
        Create a sample configuration file for editing.
        
        Args:
            file_path: Path to create the sample config. If None, uses default location.
        """
        if file_path is None:
            file_path = os.path.join(os.getcwd(), "bmlibrarian_config.json")
        
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
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'w') as f:
                json.dump(sample_config, f, indent=2)
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
def get_model(agent_type: str) -> str:
    """Get model name for an agent type."""
    return get_config().get_model(agent_type)

def get_agent_config(agent_type: str) -> Dict[str, Any]:
    """Get agent configuration."""
    return get_config().get_agent_config(agent_type)

def get_ollama_host() -> str:
    """Get Ollama host URL."""
    return get_config().get_ollama_config()["host"]

def get_search_config() -> Dict[str, Any]:
    """Get search configuration."""
    return get_config().get_search_config()