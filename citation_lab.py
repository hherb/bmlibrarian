#!/usr/bin/env python3
"""
CitationAgent Laboratory - Interactive GUI for experimenting with CitationFinderAgent

Usage:
    python citation_lab.py
    uv run python citation_lab.py

Features:
    - Interactive citation extraction from document abstracts
    - Custom prompt editing and testing
    - Model selection and parameter tuning
    - Sample medical documents for testing
    - Visual validation feedback (exact match / fuzzy match)
"""

import sys
from pathlib import Path

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from bmlibrarian.lab.citation_lab import run_citation_lab


if __name__ == "__main__":
    print("🧪 Starting CitationAgent Laboratory...")
    print("🔬 Interactive GUI for citation extraction experiments")
    print("📡 Make sure Ollama server is running on http://localhost:11434")
    print()

    try:
        run_citation_lab()
    except KeyboardInterrupt:
        print("\n👋 Exiting CitationAgent Lab...")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error starting CitationAgent Lab: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
