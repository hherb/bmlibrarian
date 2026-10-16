#!/usr/bin/env python3
"""
Study Assessment Laboratory - evaluate study quality and trustworthiness (PySide6/Qt).

Opens the main Qt application's "study_assessment" plugin in a standalone window.

Usage:
    uv run python scripts/study_assessment_lab.py
"""

import sys
from pathlib import Path

# Add src to path for imports when run from a source checkout
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def main() -> int:
    """Launch the study_assessment plugin in its own window.

    Returns:
        Process exit code
    """
    from bmlibrarian.gui.qt.core.standalone import run_plugin_standalone
    from bmlibrarian.gui.qt.plugins.study_assessment.plugin import create_plugin

    return run_plugin_standalone(create_plugin)


if __name__ == "__main__":
    sys.exit(main())
