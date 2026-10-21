"""Tests for code moved or added when the Flet GUI was retired.

Covers the standalone window launcher (``gui/qt/core/standalone.py``), the
agent lifecycle helpers (``agents/lifecycle.py``), the lazy ``bmlibrarian.lab``
exports, the ``scripts/*_lab.py`` launchers and the paper-weight lab's
discovery-thread shutdown.
"""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
# Seconds allowed for the lazy-import subprocess check
SUBPROCESS_TIMEOUT_S = 120

try:
    from PySide6.QtWidgets import QApplication, QWidget
    HAS_QT = True
except ImportError:  # pragma: no cover - Qt missing
    HAS_QT = False


@pytest.fixture
def app():
    """Provide a QApplication instance."""
    return QApplication.instance() or QApplication([])


@pytest.mark.skipif(not HAS_QT, reason="Qt not available")
class TestStandaloneLauncher:
    """run_widget_standalone / run_plugin_standalone lifecycle."""

    def _patched(self):
        """Patch the QApplication, theme and window so nothing is shown."""
        from bmlibrarian.gui.qt.core import standalone

        qapp = MagicMock()
        qapp.exec.return_value = 0
        return qapp, (
            patch.object(standalone, "_ensure_application", return_value=qapp),
            patch.object(standalone, "_apply_theme"),
            patch.object(standalone, "_show_window", return_value=MagicMock()),
        )

    def test_widget_cleanup_and_status_are_wired(self, app):
        """Widget cleanup and status are wired."""
        from bmlibrarian.gui.qt.core import standalone

        widget = MagicMock()
        qapp, patches = self._patched()
        with patches[0], patches[1], patches[2] as show_window:
            assert standalone.run_widget_standalone(lambda: widget, "T") == 0
        qapp.aboutToQuit.connect.assert_called_once_with(widget.cleanup)
        assert show_window.call_args[0][3] is widget.status_changed

    def test_widget_factory_failure_exits_non_zero(self, app, capsys):
        """Widget factory failure exits non zero."""
        from bmlibrarian.gui.qt.core import standalone

        def broken_factory():
            """Fail like a widget whose database is down."""
            raise RuntimeError("database down")

        qapp, patches = self._patched()
        with patches[0], patches[1], patches[2] as show_window, \
             patch.object(standalone, "QMessageBox") as box:
            exit_code = standalone.run_widget_standalone(broken_factory, "Tool")
        assert exit_code == standalone.STARTUP_FAILURE_EXIT_CODE
        box.critical.assert_called_once()
        show_window.assert_not_called()
        qapp.exec.assert_not_called()
        assert "database down" in capsys.readouterr().err

    def test_plugin_lifecycle_matches_main_window(self, app):
        """Plugin lifecycle matches main window."""
        from bmlibrarian.gui.qt.core import standalone

        plugin = MagicMock()
        plugin.get_metadata.return_value = SimpleNamespace(display_name="Query Lab")
        qapp, patches = self._patched()
        with patches[0], patches[1], patches[2] as show_window:
            assert standalone.run_plugin_standalone(lambda: plugin) == 0
        plugin.create_widget.assert_called_once_with(None)
        qapp.aboutToQuit.connect.assert_called_once_with(plugin.cleanup)
        plugin.on_tab_activated.assert_called_once()
        assert show_window.call_args[0][2] == "BMLibrarian - Query Lab"
        assert show_window.call_args[0][3] is plugin.status_changed

    def test_plugin_failure_exits_non_zero(self, app):
        """Plugin failure exits non zero."""
        from bmlibrarian.gui.qt.core import standalone

        def broken_plugin():
            """Fail like a plugin with a missing dependency."""
            raise ImportError("missing dependency")

        qapp, patches = self._patched()
        with patches[0], patches[1], patches[2], \
             patch.object(standalone, "QMessageBox"):
            assert standalone.run_plugin_standalone(broken_plugin) == \
                standalone.STARTUP_FAILURE_EXIT_CODE

    def test_show_window_adds_status_bar(self, app):
        """Show window adds status bar."""
        from PySide6.QtCore import QObject, Signal
        from bmlibrarian.gui.qt.core.standalone import _show_window

        class Emitter(QObject):
            """QObject exposing a status_changed signal."""
            status_changed = Signal(str)

        emitter = Emitter()
        window = _show_window(app, QWidget(), "T", emitter.status_changed)
        try:
            emitter.status_changed.emit("Loaded 3 statements")
            assert window.statusBar().currentMessage() == "Loaded 3 statements"
        finally:
            window.close()
            window.deleteLater()


@pytest.mark.parametrize("script,plugin_module", [
    ("query_lab.py", "bmlibrarian.gui.qt.plugins.query_lab.plugin"),
    ("pico_lab.py", "bmlibrarian.gui.qt.plugins.pico_lab.plugin"),
    ("prisma2020_lab.py", "bmlibrarian.gui.qt.plugins.prisma2020_lab.plugin"),
    ("study_assessment_lab.py", "bmlibrarian.gui.qt.plugins.study_assessment.plugin"),
])
@pytest.mark.skipif(not HAS_QT, reason="Qt not available")
def test_lab_launchers_open_their_plugin(app, script, plugin_module):
    """Each scripts/*_lab.py hands its plugin's create_plugin to the launcher."""
    spec = importlib.util.spec_from_file_location(
        f"launcher_{script[:-3]}", REPO_ROOT / "scripts" / script
    )
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    with patch("bmlibrarian.gui.qt.core.standalone.run_plugin_standalone",
               return_value=0) as run:
        assert launcher.main() == 0
    create_plugin = run.call_args[0][0]
    assert create_plugin.__module__ == plugin_module


class TestAgentLifecycle:
    """agents/lifecycle.py: audit connection borrowing and return."""

    def test_cleanup_ignores_missing_agents(self):
        """Cleanup ignores missing agents."""
        from bmlibrarian.agents.lifecycle import cleanup_agents
        cleanup_agents(None)
        cleanup_agents({})

    def test_cleanup_returns_audit_connection_once(self):
        """Cleanup returns audit connection once."""
        from bmlibrarian.agents.lifecycle import cleanup_agents
        db_manager, conn = MagicMock(), object()
        cleanup_agents({'_audit_conn': conn, '_db_manager': db_manager})
        db_manager._pool.putconn.assert_called_once_with(conn)

    def test_cleanup_logs_putconn_errors(self):
        """Cleanup logs putconn errors."""
        from bmlibrarian.agents.lifecycle import cleanup_agents
        db_manager = MagicMock()
        db_manager._pool.putconn.side_effect = RuntimeError("pool closed")
        cleanup_agents({'_audit_conn': object(), '_db_manager': db_manager})

    @staticmethod
    def _db_manager(audit_schema_exists):
        """DatabaseManager stand-in answering the audit-schema query."""
        db_manager = MagicMock()
        cursor = db_manager.get_connection.return_value.__enter__.return_value \
            .cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (audit_schema_exists,)
        return db_manager

    def test_no_audit_schema_means_no_connection(self):
        """No audit schema means no connection."""
        from bmlibrarian.agents import lifecycle
        db_manager = self._db_manager(False)
        with patch("bmlibrarian.database.get_db_manager", return_value=db_manager), \
             patch.object(lifecycle.AgentFactory, "create_all_agents",
                          return_value={'query_agent': MagicMock()}) as create:
            agents = lifecycle.initialize_agents_in_main_thread()
        db_manager._pool.getconn.assert_not_called()
        assert create.call_args.kwargs['audit_conn'] is None
        assert agents['_audit_conn'] is None

    def test_audit_schema_borrows_a_connection(self):
        """Audit schema borrows a connection."""
        from bmlibrarian.agents import lifecycle
        db_manager = self._db_manager(True)
        with patch("bmlibrarian.database.get_db_manager", return_value=db_manager), \
             patch.object(lifecycle.AgentFactory, "create_all_agents",
                          return_value={}) as create:
            agents = lifecycle.initialize_agents_in_main_thread()
        conn = db_manager._pool.getconn.return_value
        assert create.call_args.kwargs['audit_conn'] is conn
        assert agents['_audit_conn'] is conn

    def test_failed_agent_creation_returns_the_connection(self):
        """Failed agent creation returns the connection."""
        from bmlibrarian.agents import lifecycle
        db_manager = self._db_manager(True)
        with patch("bmlibrarian.database.get_db_manager", return_value=db_manager), \
             patch.object(lifecycle.AgentFactory, "create_all_agents",
                          side_effect=RuntimeError("ollama down")):
            assert lifecycle.initialize_agents_in_main_thread() is None
        db_manager._pool.putconn.assert_called_once_with(
            db_manager._pool.getconn.return_value
        )

    def test_agents_created_without_database(self):
        """Agents created without database."""
        from bmlibrarian.agents import lifecycle
        with patch("bmlibrarian.database.get_db_manager",
                   side_effect=RuntimeError("no database")), \
             patch.object(lifecycle.AgentFactory, "create_all_agents",
                          return_value={'query_agent': MagicMock()}) as create:
            agents = lifecycle.initialize_agents_in_main_thread()
        assert create.call_args.kwargs['audit_conn'] is None
        assert '_db_manager' not in agents


class TestLabLazyExports:
    """bmlibrarian.lab imports no lab until one is asked for."""

    def test_importing_lab_package_loads_no_lab(self):
        """Importing lab package loads no lab."""
        code = (
            "import sys, bmlibrarian.lab\n"
            "loaded = [m for m in sys.modules if m.startswith('bmlibrarian.lab.')]\n"
            "assert not loaded, loaded\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True,
            timeout=SUBPROCESS_TIMEOUT_S,
            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        )
        assert result.returncode == 0, result.stderr[-2000:]

    def test_unknown_or_removed_export_raises_attribute_error(self):
        """Unknown or removed export raises attribute error."""
        import bmlibrarian.lab as lab
        with pytest.raises(AttributeError):
            lab.QueryAgentLab  # noqa: B018 - removed with the Flet labs
        assert "QueryAgentLab" not in dir(lab)

    def test_import_time_attribute_error_becomes_import_error(self):
        """Import time attribute error becomes import error."""
        import bmlibrarian.lab as lab
        lab.__dict__.pop("ImporterTestLab", None)
        with patch("importlib.import_module", side_effect=AttributeError("enum renamed")):
            with pytest.raises(ImportError, match="enum renamed"):
                lab.__getattr__("ImporterTestLab")


@pytest.mark.skipif(not HAS_QT, reason="Qt not available")
class TestPaperWeightSearchTabShutdown:
    """The paper-weight search tab stops discovery threads on close."""

    def test_terminate_workers_stops_running_discovery(self, app):
        """Terminate workers stops running discovery."""
        import threading
        from bmlibrarian.lab.paper_weight_lab.tabs.search_tab import SearchTab

        release = threading.Event()

        def blocking_discovery(card_data, progress_cb):
            """Block until released, simulating slow discovery."""
            release.wait(SUBPROCESS_TIMEOUT_S)
            return SimpleNamespace(full_text=None, file_path=None, error_message=None)

        with patch.object(SearchTab, '_setup_ui'):
            tab = SearchTab()
        tab._card_factory = MagicMock(discover_and_download=blocking_discovery)
        timer = threading.Timer(0.2, release.set)
        with patch.object(tab, '_on_full_text_result') as on_result:
            tab._find_full_text_online({'id': 7, 'title': 'T'})
            worker = next(iter(tab._discovery_sessions)).worker
            timer.start()
            try:
                tab._terminate_workers()
            finally:
                release.set()
                timer.join()
            assert not worker.isRunning()
            assert not tab._discovery_sessions
            app.processEvents()
            on_result.assert_not_called()  # late result dropped

    def test_database_failure_is_not_reported_as_success(self, app, tmp_path):
        """Database failure is not reported as success."""
        from bmlibrarian.gui.document_card_factory_base import DocumentCardData
        from bmlibrarian.gui.qt.qt_document_card_factory import QtDocumentCardFactory
        from bmlibrarian.lab.paper_weight_lab.tabs.search_tab import SearchTab

        pdf_path = tmp_path / "paper.pdf"
        pdf_path.write_bytes(b"%PDF-1.4")
        with patch.object(SearchTab, '_setup_ui'):
            tab = SearchTab()
        tab._card_factory = QtDocumentCardFactory(base_pdf_dir=tmp_path)
        doc = {'id': 7, 'title': 'T'}
        result = SimpleNamespace(
            success=True, verified=True, full_text=None, file_path=str(pdf_path),
            error_message=None, discovered_doi=None,
        )
        dialog = MagicMock()
        downloaded = []
        tab.full_text_downloaded.connect(lambda *a: downloaded.append(a))
        with patch.object(tab._card_factory, '_update_pdf_filename_in_database',
                          return_value=False), \
             patch('bmlibrarian.lab.paper_weight_lab.tabs.search_tab.is_widget_valid',
                   return_value=True), \
             patch('bmlibrarian.lab.paper_weight_lab.tabs.search_tab.QTimer'), \
             patch('bmlibrarian.lab.paper_weight_lab.tabs.search_tab.QMessageBox') as box:
            tab._on_full_text_result(doc, DocumentCardData(doc_id=7, title='T'), dialog, result)

        dialog.set_success.assert_not_called()
        failure_text = dialog.set_failure.call_args[0][0]
        assert "could not be saved to the database" in failure_text
        assert pdf_path.name in failure_text
        assert 'has_pdf' not in doc
        assert downloaded == []
        box.warning.assert_called_once()


class TestReportBuilder:
    """The relocated research ReportBuilder keeps the report content intact."""

    @pytest.mark.parametrize("counterfactual", [None, {}, SimpleNamespace()])
    def test_report_contains_question_and_content(self, counterfactual):
        """Report contains question and content."""
        from bmlibrarian.gui.qt.plugins.research.report_builder import ReportBuilder

        content = "## Findings\n\nExercise lowers blood pressure [1].\n\n## References\n1. Smith J"
        report = ReportBuilder(workflow_steps=[]).build_final_report(
            research_question="Does exercise lower blood pressure?",
            report_content=content,
            counterfactual_analysis=counterfactual,
            documents=[{'id': 1}],
            scored_documents=[({'id': 1}, {'score': 4})],
            citations=[],
            human_in_loop=False,
        )
        assert "# Research Report: Does exercise lower blood pressure?" in report
        assert content in report
