"""Systematic Review plugin for BMLibrarian Qt GUI.

Provides checkpoint-based workflow monitoring and resume functionality
for systematic literature reviews.

Note: Imports are intentionally lazy to avoid circular imports when
the plugin manager loads plugin.py directly via importlib.
"""

__all__ = ["SystematicReviewPlugin", "create_plugin"]


def __getattr__(name: str):
    """Lazy import to avoid circular imports."""
    if name == "SystematicReviewPlugin":
        from .plugin import SystematicReviewPlugin
        return SystematicReviewPlugin
    elif name == "create_plugin":
        from .plugin import create_plugin
        return create_plugin
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
