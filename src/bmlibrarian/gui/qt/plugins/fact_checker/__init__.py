"""
Fact-Checker Review Tab Plugin.

Provides interface for reviewing and annotating fact-checking results.
"""

from .plugin import create_plugin, FactCheckerPlugin

__all__ = ['create_plugin', 'FactCheckerPlugin']
