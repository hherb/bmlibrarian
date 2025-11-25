#!/usr/bin/env python3
"""
Importer Test Laboratory - Entry Point

A PySide6-based GUI for testing and validating importer functionality
without affecting the production database.

Features:
- Fetch articles from medRxiv/PubMed without storing in database
- View raw and formatted abstracts side-by-side
- Export test results to JSON or SQLite for visual verification
- Test abstract formatting transformations

Usage:
    uv run python importer_test_lab.py
"""

from bmlibrarian.lab.importer_test_lab import main

if __name__ == "__main__":
    main()
