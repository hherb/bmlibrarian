"""
GUI configuration manager for BMLibrarian Qt GUI.

Handles loading, saving, and managing GUI-specific configuration separate
from the main BMLibrarian configuration.
"""

import json
from pathlib import Path
from typing import Dict, Any


class GUIConfigManager:
    """Manages GUI configuration for the Qt application."""

    DEFAULT_CONFIG = {
        "gui": {
            "theme": "default",
            "window": {
                "width": 1400,
                "height": 900,
                "remember_geometry": True,
                "position_x": None,
                "position_y": None,
            },
            "tabs": {
                "enabled_plugins": [
                    "research",
                    "search",
                    "fact_checker",
                    "query_lab",
                    "configuration",
                ],
                "tab_order": [
                    "research",
                    "search",
                    "fact_checker",
                    "query_lab",
                    "configuration",
                ],
                "default_tab": "research",
            },
            "research_tab": {
                "show_workflow_steps": True,
                "auto_scroll_to_active": True,
                "max_documents_display": 100,
            },
            "fact_checker_tab": {
                "auto_save": True,
                "show_confidence_timer": True,
            },
        }
    }

    def __init__(self, config_path: Path | None = None):
        """
        Initialize configuration manager.

        Args:
            config_path: Optional custom path to config file.
                        Defaults to ~/.bmlibrarian/gui_config.json
        """
        if config_path is None:
            config_dir = Path.home() / ".bmlibrarian"
            config_dir.mkdir(parents=True, exist_ok=True)
            self.config_path = config_dir / "gui_config.json"
        else:
            self.config_path = Path(config_path)

        self._config = None

    def get_config(self) -> Dict[str, Any]:
        """
        Get the current configuration.

        Loads from file if not already loaded, returns default if file doesn't exist.

        Returns:
            Configuration dictionary
        """
        if self._config is None:
            self._config = self._load_config()
        return self._config

    def _load_config(self) -> Dict[str, Any]:
        """
        Load configuration from file.

        Returns:
            Configuration dictionary (defaults if file doesn't exist)
        """
        if not self.config_path.exists():
            # Return default config if file doesn't exist
            return self._deep_copy(self.DEFAULT_CONFIG)

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            # Merge with defaults to ensure all keys exist
            return self._merge_with_defaults(config)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error loading GUI config from {self.config_path}: {e}")
            print("Using default configuration")
            return self._deep_copy(self.DEFAULT_CONFIG)

    def save_config(self, config: Dict[str, Any] | None = None):
        """
        Save configuration to file.

        Args:
            config: Optional configuration dictionary to save.
                   If None, saves current config.
        """
        if config is not None:
            self._config = config

        if self._config is None:
            self._config = self._deep_copy(self.DEFAULT_CONFIG)

        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self._config, f, indent=2)
        except IOError as e:
            print(f"Error saving GUI config to {self.config_path}: {e}")

    def reset_to_defaults(self):
        """Reset configuration to defaults and save."""
        self._config = self._deep_copy(self.DEFAULT_CONFIG)
        self.save_config()

    def update_config(self, updates: Dict[str, Any]):
        """
        Update configuration with new values.

        Args:
            updates: Dictionary of updates to merge into config
        """
        config = self.get_config()
        self._deep_update(config, updates)
        self.save_config(config)

    def get_value(self, *keys: str, default: Any = None) -> Any:
        """
        Get a nested configuration value.

        Args:
            *keys: Keys to navigate nested dict (e.g., "gui", "window", "width")
            default: Default value if key path doesn't exist

        Returns:
            Configuration value or default
        """
        config = self.get_config()
        for key in keys:
            if isinstance(config, dict) and key in config:
                config = config[key]
            else:
                return default
        return config

    def set_value(self, *keys: str, value: Any):
        """
        Set a nested configuration value.

        Args:
            *keys: Keys to navigate nested dict, with last key being the value key
            value: Value to set
        """
        if len(keys) == 0:
            raise ValueError("At least one key must be provided")

        config = self.get_config()
        current = config
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        current[keys[-1]] = value
        self.save_config(config)

    @staticmethod
    def _deep_copy(d: Dict) -> Dict:
        """Deep copy a dictionary."""
        return json.loads(json.dumps(d))

    @staticmethod
    def _deep_update(target: Dict, source: Dict):
        """Deep update target dict with source dict."""
        for key, value in source.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                GUIConfigManager._deep_update(target[key], value)
            else:
                target[key] = value

    def _merge_with_defaults(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Merge loaded config with defaults to ensure all keys exist.

        Args:
            config: Loaded configuration

        Returns:
            Merged configuration
        """
        result = self._deep_copy(self.DEFAULT_CONFIG)
        self._deep_update(result, config)
        return result
