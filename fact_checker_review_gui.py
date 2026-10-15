#!/usr/bin/env python3
"""
Fact-Checker Review GUI for BMLibrarian (PySide6/Qt).

Standalone window for human reviewers to annotate fact-checking results,
using the same review tab as the main Qt application's "Fact Checker" tab.
Works against PostgreSQL (default) or a portable SQLite review package
(``--db-file``) for external reviewers without PostgreSQL.

Usage:
    uv run python fact_checker_review_gui.py
    uv run python fact_checker_review_gui.py --user alice --incremental
    uv run python fact_checker_review_gui.py --user bob --blind
    uv run python fact_checker_review_gui.py --user alice --db-file review_package.db
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import List, Optional

# Add src to path for imports when run from a source checkout
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Review packages are SQLite files with this extension (export_review_package.py)
REVIEW_PACKAGE_SUFFIX = ".db"


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Argument list (defaults to sys.argv[1:])

    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="BMLibrarian Fact-Checker Review GUI - Human annotation "
                    "interface for fact-checking results"
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Incremental mode: only show statements you haven't annotated yet",
    )
    parser.add_argument(
        "--user",
        type=str,
        help="Annotator username to start with",
    )
    parser.add_argument(
        "--blind",
        action="store_true",
        help="Blind mode: hide original and AI annotations from the annotator",
    )
    parser.add_argument(
        "--db-file",
        type=str,
        help="SQLite review package to use. If not specified, uses PostgreSQL.",
    )
    return parser.parse_args(argv)


def validate_db_file(db_file: Optional[str]) -> Optional[str]:
    """Check a review-package path; return an error message or None if OK.

    Args:
        db_file: Path given with --db-file, or None

    Returns:
        Error message, or None when the path is acceptable (or not given)
    """
    if not db_file:
        return None
    db_path = Path(db_file)
    if not db_path.is_file():
        return f"SQLite database file not found: {db_file}"
    if db_path.suffix != REVIEW_PACKAGE_SUFFIX:
        return f"Database file must have {REVIEW_PACKAGE_SUFFIX} extension: {db_file}"
    return None


def main(argv: Optional[List[str]] = None) -> int:
    """Main entry point for the application.

    Args:
        argv: Argument list (defaults to sys.argv[1:])

    Returns:
        Process exit code
    """
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO)

    error = validate_db_file(args.db_file)
    if error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    from bmlibrarian.gui.qt.core.standalone import run_widget_standalone
    from bmlibrarian.gui.qt.plugins.fact_checker.fact_checker_tab import FactCheckerTabWidget

    return run_widget_standalone(
        lambda: FactCheckerTabWidget(
            db_file=args.db_file,
            default_username=args.user,
            blind_mode=args.blind,
            incremental=args.incremental,
        ),
        title="BMLibrarian - Fact-Checker Review",
        argv=[sys.argv[0]],
    )


if __name__ == "__main__":
    sys.exit(main())
