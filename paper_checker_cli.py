#!/usr/bin/env python3
"""
PaperChecker CLI - Medical abstract fact-checking from command line.

This is the entry point for the PaperChecker command-line interface.
Uses the bmlibrarian.paperchecker.cli module for all functionality.

Usage:
    uv run python paper_checker_cli.py input.json
    uv run python paper_checker_cli.py input.json -o results.json
    uv run python paper_checker_cli.py input.json --export-markdown reports/
    uv run python paper_checker_cli.py --pmid 12345678 23456789

For full usage information:
    uv run python paper_checker_cli.py --help
"""

import sys

from src.bmlibrarian.paperchecker.cli.app import main

if __name__ == "__main__":
    sys.exit(main())
