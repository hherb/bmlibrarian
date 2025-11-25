#!/usr/bin/env python3
"""
QueryAgent Laboratory - Interactive GUI for experimenting with QueryAgent

A Flet-based desktop application for testing and experimenting with natural language
to PostgreSQL query conversion using BMLibrarian's QueryAgent.

Features:
- Interactive query input and generated output display
- Model selection with live model refresh from Ollama
- Parameter adjustment (temperature, top-p, max tokens)
- Save/load query examples for testing
- Connection testing for Ollama and database
- Real-time query statistics

Usage:
    python query_lab.py
    
    # Or with the module
    uv run python query_lab.py

Requirements:
- Flet GUI framework
- BMLibrarian with QueryAgent
- Ollama server running locally
- PostgreSQL database with BMLibrarian schema
"""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from bmlibrarian.lab.query_lab import run_query_lab

if __name__ == "__main__":
    print("🧪 Starting QueryAgent Laboratory...")
    print("🔬 Interactive GUI for query generation experiments")
    print("📡 Make sure Ollama server is running on http://localhost:11434")
    print()
    
    try:
        run_query_lab()
    except KeyboardInterrupt:
        print("\n👋 Exiting QueryAgent Lab...")
    except Exception as e:
        print(f"\n❌ Error starting QueryAgent Lab: {e}")
        sys.exit(1)