#!/usr/bin/env python3
"""
Fact-Checker Review GUI for BMLibrarian

A graphical interface for human reviewers to annotate and review fact-checking results.
Entry point for the fact-checker review GUI application.
Uses the refactored BMLibrarian factchecker module.
"""

import argparse
import sys
from pathlib import Path

import flet as ft

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from bmlibrarian.factchecker.gui.review_app import FactCheckerReviewApp


def main():
    """Main entry point for the application."""
    parser = argparse.ArgumentParser(
        description="BMLibrarian Fact-Checker Review GUI - Human annotation interface for fact-checking results"
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Incremental mode: only show statements you haven't annotated yet"
    )
    parser.add_argument(
        "--user",
        type=str,
        help="Username to use (suppresses login dialog)"
    )
    parser.add_argument(
        "--blind",
        action="store_true",
        help="Blind mode: hide original and AI annotations from human annotator"
    )
    parser.add_argument(
        "--db-file",
        type=str,
        help="SQLite database file to use (for portable review packages). If not specified, uses PostgreSQL."
    )

    args = parser.parse_args()

    # Validate db-file if provided
    if args.db_file:
        db_path = Path(args.db_file)
        if not db_path.exists():
            print(f"Error: SQLite database file not found: {args.db_file}")
            return 1
        if db_path.suffix != '.db':
            print(f"Error: Database file must have .db extension: {args.db_file}")
            return 1

    # Create and run app
    app = FactCheckerReviewApp(
        incremental=args.incremental,
        default_username=args.user,
        blind_mode=args.blind,
        db_file=args.db_file
    )
    ft.app(target=app.main)

    return 0


if __name__ == "__main__":
    sys.exit(main())
