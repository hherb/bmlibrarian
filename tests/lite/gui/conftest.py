"""Conftest for GUI tests.

Handles skipping GUI tests when PySide6 is not available.
"""

import pytest
import sys


def pytest_configure(config):
    """Configure pytest for GUI tests."""
    config.addinivalue_line(
        "markers",
        "gui: marks tests as requiring PySide6/GUI capabilities"
    )


def pytest_collection_modifyitems(config, items):
    """Skip GUI tests if PySide6 is not available."""
    try:
        import PySide6  # noqa: F401
    except (ImportError, OSError):
        skip_gui = pytest.mark.skip(
            reason="PySide6 not available in headless environment"
        )
        for item in items:
            # Skip all tests in gui module that require PySide6 imports
            if "gui" in item.nodeid:
                item.add_marker(skip_gui)
