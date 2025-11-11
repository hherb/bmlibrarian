"""
Fact Checker CLI Module

Provides command-line interface for batch fact-checking of biomedical statements.
"""

from .app import main
from .commands import create_agent, load_input_file, save_output_file
from .formatters import print_result_summary, print_detailed_results

__all__ = [
    'main',
    'create_agent',
    'load_input_file',
    'save_output_file',
    'print_result_summary',
    'print_detailed_results'
]
