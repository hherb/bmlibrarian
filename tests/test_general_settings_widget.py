"""Tests for the Configuration tab's General settings widget."""

import pytest

try:
    from PySide6.QtWidgets import QApplication

    from bmlibrarian.gui.qt.plugins.configuration.general_settings_widget import (
        GeneralSettingsWidget,
    )
    HAS_QT = True
except ImportError:  # pragma: no cover - Qt missing
    HAS_QT = False

pytestmark = pytest.mark.skipif(not HAS_QT, reason="Qt not available")


def test_ollama_url_field_edits_ollama_host() -> None:
    """The Ollama URL field shows and saves ollama.host, the key the app reads (#480)."""
    QApplication.instance() or QApplication([])
    widget = GeneralSettingsWidget({'ollama': {'host': 'http://gpu:11434'}})
    try:
        assert widget.ollama_url_input.text() == 'http://gpu:11434'
        widget.ollama_url_input.setText('http://other:11434')
        assert widget.get_config()['ollama'] == {'host': 'http://other:11434'}
    finally:
        widget.deleteLater()
