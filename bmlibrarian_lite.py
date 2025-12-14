#!/usr/bin/env python3
"""
BMLibrarian Lite - Lightweight version without PostgreSQL dependency.

A simplified interface for:
- Systematic literature review (search, score, extract, report)
- Document interrogation (Q&A with loaded documents)

Features:
- ChromaDB for vector storage (embedded, no PostgreSQL)
- SQLite for metadata (embedded)
- FastEmbed for local embeddings (CPU-optimized, no PyTorch)
- Anthropic Claude for LLM inference (online)
- NCBI E-utilities for PubMed search (online)

Usage:
    python bmlibrarian_lite.py

Requirements:
    - Python 3.12+
    - Anthropic API key (set ANTHROPIC_API_KEY or configure in Settings)
    - Internet connection for PubMed search and Claude API

First-time setup:
    1. Run the application
    2. Go to Settings
    3. Enter your Anthropic API key
    4. Optionally enter your email for PubMed (recommended)
"""

import sys
import logging
from pathlib import Path

# Add src to path if running from source
src_path = Path(__file__).parent / "src"
if src_path.exists():
    sys.path.insert(0, str(src_path))


def main() -> int:
    """
    Main entry point for BMLibrarian Lite.

    Returns:
        Application exit code
    """
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Import here to ensure path is set up
    from bmlibrarian.lite.gui.app import run_lite_app

    return run_lite_app()


if __name__ == "__main__":
    sys.exit(main())
