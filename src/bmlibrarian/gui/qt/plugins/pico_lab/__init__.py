"""
PICO Lab Plugin for BMLibrarian Qt GUI.

Provides an interactive interface for extracting PICO (Population, Intervention,
Comparison, Outcome) components from biomedical research papers.
"""

from .plugin import create_plugin

__all__ = ["create_plugin"]
