"""
Data models for BMLibrarian agents.

This package contains dataclass definitions and data structures used by agents.
"""

from .counterfactual import CounterfactualQuestion, CounterfactualAnalysis

__all__ = [
    'CounterfactualQuestion',
    'CounterfactualAnalysis'
]
