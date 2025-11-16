#!/usr/bin/env python3
"""Entry point for BMLibrarian Qt GUI application.

This script launches the PySide6-based graphical user interface for BMLibrarian.
It provides a modern, plugin-based tabbed interface for biomedical literature research.

Usage:
    python bmlibrarian_qt.py
    # Or make executable and run directly:
    chmod +x bmlibrarian_qt.py
    ./bmlibrarian_qt.py

The application will:
1. Load configuration from ~/.bmlibrarian/gui_config.json
2. Discover and load enabled plugins
3. Create tabs for each plugin
4. Show the main window

Available command-line options can be added here in the future.
"""

import sys
from pathlib import Path

# Add src to path if running from repository root
src_path = Path(__file__).parent / "src"
if src_path.exists():
    sys.path.insert(0, str(src_path))

from bmlibrarian.gui.qt import main

if __name__ == "__main__":
    sys.exit(main())
