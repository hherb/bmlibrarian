"""The PICO lab's model picker lists models through the LLM layer (#250).

It used to GET ``{host}/api/tags`` with ``requests``, bypassing
``bmlibrarian.llm``; an unreachable server must still reach the user, through
the status line rather than a modal dialog (the refresh runs while the tab is
being built).
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
    tab = SimpleNamespace(
        config=config, model_combo=combo, status_message=Mock(), status_label=Mock()
    )
    tab._report_status = lambda message: PICOLabTabWidget._report_status(tab, message)
    return tab


def test_refresh_lists_models_from_configured_host() -> None:
    """Models come from list_ollama_models(host) and fill the combo box."""
    tab = _tab()
    models = ["qwen3:8b", "gpt-oss:20b"]

    with patch.object(
        pico_lab_tab, "list_ollama_models", return_value=models
    ) as lister, patch.object(pico_lab_tab, "QMessageBox") as msgbox:
        PICOLabTabWidget._refresh_models(tab)

    lister.assert_called_once_with(HOST)
    tab.model_combo.addItems.assert_called_once_with(models)
    tab.model_combo.setCurrentText.assert_called_once_with("gpt-oss:20b")
    tab.status_message.emit.assert_called_once_with("Refreshed models - 2 available")
    tab.status_label.setText.assert_called_once_with("Refreshed models - 2 available")
    msgbox.warning.assert_not_called()


def test_refresh_keeps_current_selection() -> None:
    """A still-available current model stays selected over the configured one."""
    tab = _tab(current="qwen3:8b")

    with patch.object(
        pico_lab_tab, "list_ollama_models", return_value=["qwen3:8b", "gpt-oss:20b"]
    ):
        PICOLabTabWidget._refresh_models(tab)

    tab.model_combo.setCurrentText.assert_called_once_with("qwen3:8b")


def test_reachable_server_without_models_says_so() -> None:
    """An empty list means reachable-but-empty: say how to fix it, not "0 available"."""
    tab = _tab()

    with patch.object(pico_lab_tab, "list_ollama_models", return_value=[]):
        PICOLabTabWidget._refresh_models(tab)

    tab.model_combo.clear.assert_called_once()
    message = tab.status_message.emit.call_args.args[0]
    assert "no models installed" in message


def test_unreachable_server_is_reported() -> None:
    """A ConnectionError is shown in the status line without a modal dialog."""
    tab = _tab()

    with patch.object(
        pico_lab_tab, "list_ollama_models", side_effect=ConnectionError("refused")
    ), patch.object(pico_lab_tab, "QMessageBox") as msgbox:
        PICOLabTabWidget._refresh_models(tab)

    msgbox.warning.assert_not_called()
    message = tab.status_label.setText.call_args.args[0]
    assert "unreachable" in message and "refused" in message
    tab.model_combo.setPlaceholderText.assert_called_once()
    tab.model_combo.clear.assert_not_called()


def test_other_errors_are_not_reported_as_connection_failures() -> None:
    """A config error names its own type instead of claiming Ollama is down."""
    tab = _tab()
    tab.config.get_ollama_config.return_value = {}

    with patch.object(pico_lab_tab, "list_ollama_models") as lister:
        PICOLabTabWidget._refresh_models(tab)

    lister.assert_not_called()
    message = tab.status_message.emit.call_args.args[0]
    assert "KeyError" in message and "unreachable" not in message
