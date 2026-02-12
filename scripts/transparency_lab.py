#!/usr/bin/env python3
"""
Transparency Assessment Lab - Interactive GUI for bias risk assessment.

A PySide6/Qt desktop application for testing and exploring TransparencyAgent
functionality. Assess transparency, funding disclosure, COI, and data
availability for documents in the database.

Features:
- Document input by ID, DOI, or PMID
- Model selection from available Ollama models
- Real-time transparency assessment with progress
- Color-coded risk badges (green/orange/red)
- Detailed breakdown of all transparency dimensions
- Export results to JSON

Usage:
    uv run python scripts/transparency_lab.py
    uv run python scripts/transparency_lab.py --debug
"""

import argparse
import logging
import sys


def main() -> None:
    """Main entry point for Transparency Assessment Laboratory."""
    parser = argparse.ArgumentParser(
        description="Transparency Assessment Laboratory - Bias risk detection"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    logger = logging.getLogger(__name__)

    logger.info("Starting Transparency Assessment Laboratory (PySide6)")
    try:
        from bmlibrarian.lab.transparency_lab import main as qt_main
        qt_main()
    except ImportError as e:
        logger.error(f"Qt interface not available: {e}")
        print(f"Error: PySide6/Qt interface not available: {e}")
        print("Please ensure PySide6 is installed: uv add PySide6")
        sys.exit(1)


if __name__ == "__main__":
    main()
