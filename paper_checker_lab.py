#!/usr/bin/env python3
"""
PaperChecker Laboratory - Interactive testing interface for medical abstract fact-checking.

An interactive GUI for testing and exploring PaperChecker functionality on single
abstracts with step-by-step visualization.

Usage:
    # Launch laboratory
    uv run python paper_checker_lab.py

    # Launch in web mode
    uv run python paper_checker_lab.py --view web --port 8080

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
        "--view",
        choices=["desktop", "web"],
        default="desktop",
        help="Launch mode: desktop (native window) or web (browser-based)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port for web mode (default: 8080)"
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

    # Import and run laboratory
    from bmlibrarian.lab.paper_checker_lab import PaperCheckerLab
    import flet as ft

    app = PaperCheckerLab()

    if args.view == "web":
        ft.app(target=app.main, view=ft.AppView.WEB_BROWSER, port=args.port)
    else:
        ft.app(target=app.main)


if __name__ == "__main__":
    main()
