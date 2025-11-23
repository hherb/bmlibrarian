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

    # Use old Flet-based interface (deprecated)
    uv run python paper_checker_lab.py --flet
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
    parser.add_argument(
        "--flet",
        action="store_true",
        help="Use legacy Flet-based interface (deprecated)"
    )
    parser.add_argument(
        "--view",
        choices=["desktop", "web"],
        default="desktop",
        help="Launch mode for Flet interface (only used with --flet)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port for web mode (only used with --flet --view web)"
    )

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    logger = logging.getLogger(__name__)

    if args.flet:
        # Legacy Flet interface
        logger.info("Using legacy Flet-based interface")
        try:
            from bmlibrarian.lab.paper_checker_lab_flet import PaperCheckerLab
            import flet as ft

            app = PaperCheckerLab()

            if args.view == "web":
                ft.app(target=app.main, view=ft.AppView.WEB_BROWSER, port=args.port)
            else:
                ft.app(target=app.main)
        except ImportError as e:
            logger.error(f"Flet interface not available: {e}")
            print("Error: Flet interface not available. Use without --flet flag.")
            sys.exit(1)
    else:
        # New PySide6/Qt interface
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
