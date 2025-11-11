#!/usr/bin/env python3
"""
Fact Checker CLI - Audit biomedical statements in LLM training data

Entry point for the fact-checker command-line interface.
Uses the refactored BMLibrarian factchecker module.
"""

import sys

from src.bmlibrarian.factchecker.cli.app import main

if __name__ == "__main__":
    sys.exit(main())
