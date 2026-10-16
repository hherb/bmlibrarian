"""Guard: the Qt GUI must import and run without Flet.

Dependabot's oauthlib 4.0 bump pulled flet 1.0, whose API changes made the
eager Flet re-exports in ``bmlibrarian.gui`` raise on import, which broke
every Qt GUI. This test blocks ``flet`` and imports every
``bmlibrarian.gui.qt`` module in a fresh interpreter, so a stray Flet import
on the Qt path fails here instead of in the user's hands.
"""

import os
import subprocess
import sys

import pytest

# Seconds allowed for importing every Qt GUI module in a subprocess
IMPORT_SWEEP_TIMEOUT_S = 180

IMPORT_SWEEP = """
import importlib, pkgutil, sys
sys.modules['flet'] = None  # any 'import flet' now raises ImportError
import bmlibrarian.gui
import bmlibrarian.gui.qt as qt
failures = []
for info in pkgutil.walk_packages(qt.__path__, qt.__name__ + '.'):
    try:
        importlib.import_module(info.name)
    except Exception as exc:
        failures.append(f"{info.name}: {type(exc).__name__}: {exc}")
assert not failures, "\\n".join(failures)
"""


def test_qt_gui_imports_without_flet() -> None:
    """Every bmlibrarian.gui.qt module imports with flet unavailable."""
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    result = subprocess.run(
        [sys.executable, "-c", IMPORT_SWEEP],
        env=env,
        capture_output=True,
        text=True,
        timeout=IMPORT_SWEEP_TIMEOUT_S,
    )
    assert result.returncode == 0, result.stderr[-4000:]


def test_unknown_gui_attribute_raises_attribute_error() -> None:
    """The lazy ``__getattr__`` only resolves known exports."""
    import bmlibrarian.gui as gui

    with pytest.raises(AttributeError):
        gui.NotAThing  # noqa: B018
    assert not hasattr(gui, "NotAThing")
