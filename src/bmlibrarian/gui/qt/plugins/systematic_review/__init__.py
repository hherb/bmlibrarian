"""Systematic Review plugin for BMLibrarian Qt GUI.

Provides checkpoint-based workflow monitoring and resume functionality
for systematic literature reviews.
"""

from .plugin import SystematicReviewPlugin, create_plugin

__all__ = ["SystematicReviewPlugin", "create_plugin"]
