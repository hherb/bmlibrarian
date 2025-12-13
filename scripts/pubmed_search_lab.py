#!/usr/bin/env python3
"""
PubMed Search Lab launcher script.

Run this script to launch the PubMed Search Lab GUI for experimenting
with the PubMed API search functionality.

Usage:
    uv run python scripts/pubmed_search_lab.py
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bmlibrarian.lab.pubmed_search_lab import run_pubmed_search_lab


if __name__ == "__main__":
    run_pubmed_search_lab()
