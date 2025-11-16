"""Core framework components for the Qt GUI."""

from .application import BMLibrarianApplication, main
from .main_window import BMLibrarianMainWindow
from .plugin_manager import PluginManager, PluginLoadError
from .tab_registry import TabRegistry, DependencyError, CircularDependencyError
from .config_manager import GUIConfigManager
from .event_bus import EventBus

__all__ = [
    "BMLibrarianApplication",
    "main",
    "BMLibrarianMainWindow",
    "PluginManager",
    "PluginLoadError",
    "TabRegistry",
    "DependencyError",
    "CircularDependencyError",
    "GUIConfigManager",
    "EventBus",
]
