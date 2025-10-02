"""
Formatters for BMLibrarian agent outputs.

This package contains formatting functions for reports, protocols, and other
agent output structures.
"""

from .counterfactual_formatter import (
    format_counterfactual_report,
    generate_research_protocol
)

__all__ = [
    'format_counterfactual_report',
    'generate_research_protocol'
]
