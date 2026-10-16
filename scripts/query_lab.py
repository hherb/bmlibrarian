#!/usr/bin/env python3
"""
Query Laboratory - experiment with QueryAgent natural-language to SQL (PySide6/Qt).

Opens the main Qt application's "query_lab" plugin in a standalone window.

Usage:
    uv run python scripts/query_lab.py
"""

import sys
from pathlib import Path

# Add src to path for imports when run from a source checkout
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def main() -> int:
    """Launch the query_lab plugin in its own window.

    Returns:
        Process exit code
    """
    from bmlibrarian.gui.qt.core.standalone import run_plugin_standalone
    from bmlibrarian.gui.qt.plugins.query_lab.plugin import create_plugin

    return run_plugin_standalone(create_plugin)


if __name__ == "__main__":
    sys.exit(main())
