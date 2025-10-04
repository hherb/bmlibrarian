"""Utility modules for BMLibrarian."""

from .path_utils import (
    expand_path,
    ensure_directory,
    get_config_dir,
    get_default_config_path,
    get_legacy_config_path
)

from .config_loader import (
    find_config_file,
    load_json_config,
    save_json_config
)

from .validation import (
    # Configuration validation
    validate_config_dict,
    validate_ollama_config,
    validate_agent_config,
    validate_database_config,
    # Data validation
    validate_url,
    validate_port,
    validate_positive_int,
    validate_float_range,
    validate_file_path,
    validate_directory_path,
    # Input sanitization
    sanitize_string,
    sanitize_filename,
    sanitize_sql_identifier,
    # Type coercion
    ensure_list,
    ensure_dict,
    ensure_string,
    ensure_int,
    ensure_float
)

__all__ = [
    # Path utilities
    'expand_path',
    'ensure_directory',
    'get_config_dir',
    'get_default_config_path',
    'get_legacy_config_path',
    # Config utilities
    'find_config_file',
    'load_json_config',
    'save_json_config',
    # Configuration validation
    'validate_config_dict',
    'validate_ollama_config',
    'validate_agent_config',
    'validate_database_config',
    # Data validation
    'validate_url',
    'validate_port',
    'validate_positive_int',
    'validate_float_range',
    'validate_file_path',
    'validate_directory_path',
    # Input sanitization
    'sanitize_string',
    'sanitize_filename',
    'sanitize_sql_identifier',
    # Type coercion
    'ensure_list',
    'ensure_dict',
    'ensure_string',
    'ensure_int',
    'ensure_float'
]
