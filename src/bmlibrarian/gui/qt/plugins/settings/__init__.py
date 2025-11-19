"""
Settings plugin for BMLibrarian Qt GUI.
"""

# Note: create_plugin is imported directly by PluginManager from plugin.py
# Export SettingsPlugin and SettingsWidget for use by other plugins (e.g., research tab)
from .plugin import SettingsPlugin, SettingsWidget

__all__ = ['SettingsPlugin', 'SettingsWidget']
