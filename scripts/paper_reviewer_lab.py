#!/usr/bin/env python3
"""
Paper Reviewer Laboratory - Interactive comprehensive paper assessment interface.

A PySide6/Qt desktop application for testing and exploring PaperReviewerAgent
functionality with DOI, PMID, PDF, or text input.

Features:
- Multiple input methods: DOI, PMID, PDF file, or pasted text
- Real-time workflow progress visualization (11 assessment steps)
- Model selection from available Ollama models
- Optional PubMed search for contradictory evidence
- Results display in Markdown and JSON formats
- Export to Markdown, PDF, or JSON files
- Abort button for long-running reviews

Assessment Steps:
1. Resolve Input - Fetch document metadata
2. Generate Summary - Create 2-3 sentence summary
3. Extract Hypothesis - Identify core claims
4. Detect Study Type - Classify research type
5. PICO Analysis - Population, Intervention, Comparison, Outcome (if applicable)
6. PRISMA Assessment - Systematic review checklist (if applicable)
7. Paper Weight - Evidential weight assessment
8. Study Assessment - Quality and trustworthiness evaluation
9. Synthesize Strengths/Weaknesses - Summary of findings
10. Search Contradictory - Find opposing literature (optional)
11. Compile Report - Generate final comprehensive report

Usage:
    # Launch laboratory
    uv run python scripts/paper_reviewer_lab.py

    # Enable debug logging
    uv run python scripts/paper_reviewer_lab.py --debug
"""

import argparse
import logging
import sys


def main() -> None:
    """Main entry point for Paper Reviewer Laboratory."""
    parser = argparse.ArgumentParser(
        description="Paper Reviewer Laboratory - Comprehensive paper assessment"
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

    # Start PySide6/Qt interface
    logger.info("Starting Paper Reviewer Laboratory (PySide6)")
    try:
        from bmlibrarian.lab.paper_reviewer_lab import main as qt_main
        qt_main()
    except ImportError as e:
        logger.error(f"Qt interface not available: {e}")
        print(f"Error: PySide6/Qt interface not available: {e}")
        print("Please ensure PySide6 is installed: uv add PySide6")
        sys.exit(1)


if __name__ == "__main__":
    main()
