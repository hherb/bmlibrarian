#!/usr/bin/env python3
"""
PaperChecker Laboratory - Interactive testing interface for medical abstract fact-checking.

A PySide6/Qt desktop application for testing and exploring PaperChecker functionality
on single abstracts with step-by-step workflow visualization and PDF upload support.

Features:
- Text input for direct abstract entry or PMID lookup
- PDF upload with AI-based abstract extraction
- Real-time workflow progress visualization (11 steps)
- Multi-tab results display (Summary, Statements, Evidence, Verdicts, Export)
- JSON and Markdown export options

Usage:
    # Launch laboratory (default desktop mode)
    uv run python paper_checker_lab.py

    # Enable debug logging
    uv run python paper_checker_lab.py --debug

"""

import argparse
import logging
import sys


def main() -> None:
    """Main entry point for PaperChecker Laboratory."""
    parser = argparse.ArgumentParser(
        description="PaperChecker Laboratory - Interactive medical abstract fact-checking"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )
    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    logger = logging.getLogger(__name__)

    # PySide6/Qt interface
    logger.info("Starting PaperChecker Laboratory (PySide6)")
    try:
        from bmlibrarian.lab.paper_checker_lab import main as qt_main
        qt_main()
    except ImportError as e:
        logger.error(f"Qt interface not available: {e}")
        print(f"Error: PySide6/Qt interface not available: {e}")
        print("Please ensure PySide6 is installed: uv add PySide6")
        sys.exit(1)


if __name__ == "__main__":
    main()
