#!/usr/bin/env python3
"""
BMLibrarian Qt GUI entry point.

Modern PySide6-based GUI with plugin architecture for biomedical literature research.

Usage:
    uv run python bmlibrarian_qt.py
"""

import sys
from src.bmlibrarian.gui.qt import main

if __name__ == "__main__":
    sys.exit(main())
