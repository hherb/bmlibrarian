"""GUI configuration manager for PySide6 application.

This module provides the GUIConfigManager class which handles loading, saving,
and managing GUI-specific configuration including window geometry, enabled plugins,
and plugin-specific settings.
"""

from pathlib import Path
import json
from typing import Dict, Any, Optional
import logging


class GUIConfigManager:
    """Manages GUI-specific configuration.

    This class handles configuration for:
    - Window geometry and state
    - Theme selection
    - Enabled plugins and tab order
    - Plugin-specific settings
    - UI preferences

    Configuration File:
        Default location: ~/.bmlibrarian/gui_config.json

    Configuration Structure:
        {
            "gui": {
                "theme": "default",
                "window": {
                    "width": 1400,
                    "height": 900,
                    "remember_geometry": true
                },
                "tabs": {
                    "enabled_plugins": ["research", "search", ...],
                    "tab_order": ["research", "search", ...],
                    "default_tab": "research"
                },
                "research_tab": { ... plugin-specific config ... },
                "search_tab": { ... },
                ...
            }
        }
    """

    DEFAULT_CONFIG = {
        "gui": {
            "theme": "default",
            "window": {
                "width": 1400,
                "height": 900,
                "remember_geometry": True,
                "x": None,  # Window position
                "y": None,
                "maximized": False
            },
            "tabs": {
                "enabled_plugins": [
                    "research",
                    "search",
                    "configuration"
                ],
                "tab_order": [
                    "research",
                    "search",
                    "configuration"
                ],
                "default_tab": "research"
            },
            "research_tab": {
                "show_workflow_steps": True,
                "auto_scroll_to_active": True,
                "max_documents_display": 100
            },
            "search_tab": {
                "max_results": 100,
                "show_abstracts": True
            },
            "fact_checker_tab": {
                "auto_save": True,
                "show_confidence_timer": True
            },
            "configuration_tab": {
                "show_advanced": False
            }
        }
    }

    def __init__(self, config_path: Optional[Path] = None):
        """Initialize the configuration manager.

        Args:
            config_path: Optional path to configuration file.
                        If None, uses ~/.bmlibrarian/gui_config.json
        """
        if config_path is None:
            config_path = Path.home() / ".bmlibrarian" / "gui_config.json"

        self.config_path = config_path
        self.logger = logging.getLogger("bmlibrarian.gui.qt.core.GUIConfigManager")

        # Load configuration
        self._config = self._load_config()

        self.logger.info(f"Configuration loaded from {self.config_path}")

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file.

        If the config file doesn't exist, creates it with default values.
        If loading fails, returns default config and logs error.

        Returns:
            Dict[str, Any]: Configuration dictionary
        """
        if not self.config_path.exists():
            self.logger.info(
                f"Configuration file not found, creating with defaults: "
                f"{self.config_path}"
            )
            # Create default config
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            self.save_config(self.DEFAULT_CONFIG)
            return self.DEFAULT_CONFIG.copy()

        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
                # Merge with defaults (for new keys added in updates)
                merged = self._merge_configs(self.DEFAULT_CONFIG, config)
                self.logger.debug("Configuration loaded and merged with defaults")
                return merged
        except json.JSONDecodeError as e:
            self.logger.error(
                f"Invalid JSON in configuration file: {e}. "
                f"Using defaults."
            )
            return self.DEFAULT_CONFIG.copy()
        except Exception as e:
            self.logger.error(
                f"Error loading GUI config: {e}. Using defaults.",
                exc_info=True
            )
            return self.DEFAULT_CONFIG.copy()

    def _merge_configs(self, default: Dict, user: Dict) -> Dict:
        """Recursively merge user config with defaults.

        This ensures that new configuration keys added in updates are
        available even if the user's config file is older.

        Args:
            default: Default configuration dictionary
            user: User's configuration dictionary

        Returns:
            Dict: Merged configuration with user values taking precedence
        """
        result = default.copy()

        for key, value in user.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                # Recursively merge nested dictionaries
                result[key] = self._merge_configs(result[key], value)
            else:
                # Use user value
                result[key] = value

        return result

    def get_config(self) -> Dict[str, Any]:
        """Get current configuration.

        Returns:
            Dict[str, Any]: Complete configuration dictionary
        """
        return self._config.copy()

    def save_config(self, config: Optional[Dict[str, Any]] = None):
        """Save configuration to file.

        Args:
            config: Configuration dictionary to save.
                   If None, saves current configuration.
        """
        if config is not None:
            self._config = config

        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, 'w') as f:
                json.dump(self._config, f, indent=2)
            self.logger.debug(f"Configuration saved to {self.config_path}")
        except Exception as e:
            self.logger.error(
                f"Error saving configuration: {e}",
                exc_info=True
            )
            raise

    def get_plugin_config(self, plugin_id: str) -> Dict[str, Any]:
        """Get configuration for a specific plugin.

        Args:
            plugin_id: ID of plugin (e.g., "research")

        Returns:
            Dict[str, Any]: Plugin-specific configuration

        Example:
            config = manager.get_plugin_config("research")
            show_steps = config.get("show_workflow_steps", True)
        """
        return self._config.get("gui", {}).get(f"{plugin_id}_tab", {})

    def set_plugin_config(self, plugin_id: str, config: Dict[str, Any]):
        """Set configuration for a specific plugin.

        Args:
            plugin_id: ID of plugin
            config: Plugin configuration dictionary
        """
        if "gui" not in self._config:
            self._config["gui"] = {}

        self._config["gui"][f"{plugin_id}_tab"] = config
        self.save_config(self._config)

        self.logger.debug(f"Updated configuration for plugin '{plugin_id}'")

    def get_window_config(self) -> Dict[str, Any]:
        """Get window configuration.

        Returns:
            Dict with window geometry and state
        """
        return self._config.get("gui", {}).get("window", {})

    def set_window_config(self, window_config: Dict[str, Any]):
        """Set window configuration.

        Args:
            window_config: Dictionary with window settings
        """
        if "gui" not in self._config:
            self._config["gui"] = {}

        self._config["gui"]["window"] = window_config
        self.save_config(self._config)

    def get_enabled_plugins(self) -> list:
        """Get list of enabled plugin IDs.

        Returns:
            List[str]: Plugin IDs to load
        """
        return self._config.get("gui", {}).get("tabs", {}).get(
            "enabled_plugins",
            ["research", "search", "configuration"]
        )

    def set_enabled_plugins(self, plugin_ids: list):
        """Set list of enabled plugins.

        Args:
            plugin_ids: List of plugin IDs to enable
        """
        if "gui" not in self._config:
            self._config["gui"] = {}
        if "tabs" not in self._config["gui"]:
            self._config["gui"]["tabs"] = {}

        self._config["gui"]["tabs"]["enabled_plugins"] = plugin_ids
        self.save_config(self._config)

    def get_tab_order(self) -> list:
        """Get preferred tab order.

        Returns:
            List[str]: Plugin IDs in display order
        """
        return self._config.get("gui", {}).get("tabs", {}).get(
            "tab_order",
            self.get_enabled_plugins()
        )

    def set_tab_order(self, tab_order: list):
        """Set tab display order.

        Args:
            tab_order: List of plugin IDs in desired order
        """
        if "gui" not in self._config:
            self._config["gui"] = {}
        if "tabs" not in self._config["gui"]:
            self._config["gui"]["tabs"] = {}

        self._config["gui"]["tabs"]["tab_order"] = tab_order
        self.save_config(self._config)

    def get_default_tab(self) -> str:
        """Get default tab to show on startup.

        Returns:
            str: Plugin ID of default tab
        """
        return self._config.get("gui", {}).get("tabs", {}).get(
            "default_tab",
            "research"
        )

    def set_default_tab(self, plugin_id: str):
        """Set default tab for startup.

        Args:
            plugin_id: Plugin ID to show by default
        """
        if "gui" not in self._config:
            self._config["gui"] = {}
        if "tabs" not in self._config["gui"]:
            self._config["gui"]["tabs"] = {}

        self._config["gui"]["tabs"]["default_tab"] = plugin_id
        self.save_config(self._config)

    def get_theme(self) -> str:
        """Get current theme name.

        Returns:
            str: Theme name ("default", "dark", etc.)
        """
        return self._config.get("gui", {}).get("theme", "default")

    def set_theme(self, theme: str):
        """Set application theme.

        Args:
            theme: Theme name ("default", "dark", etc.)
        """
        if "gui" not in self._config:
            self._config["gui"] = {}

        self._config["gui"]["theme"] = theme
        self.save_config(self._config)

        self.logger.info(f"Theme changed to '{theme}'")

    def reset_to_defaults(self):
        """Reset configuration to defaults.

        Warning: This will overwrite all current settings.
        """
        self._config = self.DEFAULT_CONFIG.copy()
        self.save_config(self._config)
        self.logger.warning("Configuration reset to defaults")

    def export_config(self, export_path: Path):
        """Export configuration to a different file.

        Args:
            export_path: Path to export configuration to
        """
        with open(export_path, 'w') as f:
            json.dump(self._config, f, indent=2)
        self.logger.info(f"Configuration exported to {export_path}")

    def import_config(self, import_path: Path):
        """Import configuration from a file.

        Args:
            import_path: Path to configuration file to import
        """
        with open(import_path, 'r') as f:
            imported_config = json.load(f)

        # Merge with defaults
        self._config = self._merge_configs(self.DEFAULT_CONFIG, imported_config)
        self.save_config(self._config)

        self.logger.info(f"Configuration imported from {import_path}")
