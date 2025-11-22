"""
PaperChecker CLI module.

Provides command-line interface for batch fact-checking of medical abstracts.
This module enables users to check abstracts from JSON files or by PMID,
with support for progress tracking, error recovery, and multiple output formats.

Modules:
    app: Main CLI entry point and argument parsing
    commands: Command handlers for abstract loading and processing
    formatters: Output formatting for results and statistics
"""

from .app import main
from .commands import (
    load_abstracts_from_json,
    load_abstracts_from_pmids,
    check_abstracts,
    export_results_json,
    export_markdown_reports,
)
from .formatters import (
    print_statistics,
    print_abstract_summary,
    format_verdict_summary,
)

__all__ = [
    "main",
    "load_abstracts_from_json",
    "load_abstracts_from_pmids",
    "check_abstracts",
    "export_results_json",
    "export_markdown_reports",
    "print_statistics",
    "print_abstract_summary",
    "format_verdict_summary",
]
