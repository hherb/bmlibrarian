"""The PICO lab's model picker lists models through the LLM layer (#250).

It used to GET ``{host}/api/tags`` with ``requests``, bypassing
``bmlibrarian.llm``; an unreachable server must still reach the user.
"""

from types import SimpleNamespace
from unittest.mock import Mock, patch

from bmlibrarian.gui.qt.plugins.pico_lab import pico_lab_tab
from bmlibrarian.gui.qt.plugins.pico_lab.pico_lab_tab import PICOLabTabWidget

HOST = "http://ollama.example:11434"


def _tab(current: str = "") -> SimpleNamespace:
    """Build the attributes _refresh_models touches."""
    config = Mock()
    config.get_ollama_config.return_value = {"host": HOST}
    config.get_model.return_value = "gpt-oss:20b"
    combo = Mock()
    combo.currentText.return_value = current
    return SimpleNamespace(config=config, model_combo=combo, status_message=Mock())


def test_refresh_lists_models_from_configured_host() -> None:
    """Models come from list_ollama_models(host) and fill the combo box."""
    tab = _tab()
    models = ["qwen3:8b", "gpt-oss:20b"]

    with patch.object(pico_lab_tab, "list_ollama_models", return_value=models) as lister:
        PICOLabTabWidget._refresh_models(tab)

    lister.assert_called_once_with(HOST)
    tab.model_combo.addItems.assert_called_once_with(models)
    tab.model_combo.setCurrentText.assert_called_once_with("gpt-oss:20b")
    tab.status_message.emit.assert_called_once_with("Refreshed models - 2 available")


def test_unreachable_server_is_reported() -> None:
    """A ConnectionError from the LLM layer is shown, not swallowed."""
    tab = _tab()

    with patch.object(
        pico_lab_tab, "list_ollama_models", side_effect=ConnectionError("refused")
    ), patch.object(pico_lab_tab, "QMessageBox") as msgbox:
        PICOLabTabWidget._refresh_models(tab)

    msgbox.warning.assert_called_once()
    assert "refused" in msgbox.warning.call_args.args[2]
    tab.model_combo.clear.assert_not_called()
