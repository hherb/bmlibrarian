#!/usr/bin/env python3
"""
PRISMA 2020 Laboratory - assess systematic reviews against PRISMA 2020 (PySide6/Qt).

Opens the main Qt application's "prisma2020_lab" plugin in a standalone window.

Usage:
    uv run python scripts/prisma2020_lab.py
"""

import sys
from pathlib import Path

# Add src to path for imports when run from a source checkout
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def main() -> int:
    """Launch the prisma2020_lab plugin in its own window.

    Returns:
        Process exit code
    """
    from bmlibrarian.gui.qt.core.standalone import run_plugin_standalone
    from bmlibrarian.gui.qt.plugins.prisma2020_lab.plugin import create_plugin

    return run_plugin_standalone(create_plugin)


if __name__ == "__main__":
    sys.exit(main())
