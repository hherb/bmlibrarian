"""Tests for the Qt fact-checker review launcher and tab launch options.

The Flet review GUI was retired (October 2026); ``fact_checker_review_gui.py``
now opens the Qt ``FactCheckerTabWidget`` standalone with the same options:
``--db-file`` (SQLite review package), ``--user``, ``--blind`` and
``--incremental``.
"""

import importlib.util
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "src" / "bmlibrarian" / "factchecker" / "db" / "sqlite_schema.sql"

try:
    from PySide6.QtWidgets import QApplication
    HAS_QT = True
except ImportError:  # pragma: no cover - Qt missing
    HAS_QT = False


def _load_launcher():
    """Import the top-level fact_checker_review_gui.py script as a module."""
    spec = importlib.util.spec_from_file_location(
        "fact_checker_review_gui", REPO_ROOT / "fact_checker_review_gui.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestLauncherArgs:
    """CLI parsing and review-package validation."""

    def test_parse_all_options(self):
        launcher = _load_launcher()
        args = launcher.parse_args(
            ["--user", "alice", "--blind", "--incremental", "--db-file", "x.db"]
        )
        assert (args.user, args.blind, args.incremental, args.db_file) == (
            "alice", True, True, "x.db"
        )

    def test_validate_db_file(self, tmp_path):
        launcher = _load_launcher()
        assert launcher.validate_db_file(None) is None
        assert "not found" in launcher.validate_db_file(str(tmp_path / "missing.db"))
        wrong = tmp_path / "package.sqlite"
        wrong.write_bytes(b"")
        assert ".db" in launcher.validate_db_file(str(wrong))
        ok = tmp_path / "package.db"
        ok.write_bytes(b"")
        assert launcher.validate_db_file(str(ok)) is None

    def test_main_rejects_missing_package(self, tmp_path, capsys):
        launcher = _load_launcher()
        assert launcher.main(["--db-file", str(tmp_path / "missing.db")]) == 1
        assert "not found" in capsys.readouterr().err


class TestReviewHelpers:
    """Pure helpers behind per-annotator reviews and incremental mode."""

    RESULTS = [
        {'statement_id': 1, 'human_annotations': [
            {'annotator_id': 7, 'annotation': 'yes', 'explanation': 'e'}]},
        {'statement_id': 2, 'human_annotations': [
            {'annotator_id': 8, 'annotation': 'no'}]},
        {'statement_id': 3, 'human_annotations': []},
    ]

    def test_reviews_for_annotator(self):
        from bmlibrarian.gui.qt.plugins.fact_checker.fact_checker_tab import (
            reviews_for_annotator,
        )
        reviews = reviews_for_annotator(self.RESULTS, 7)
        assert reviews[0]['human_annotation'] == 'yes'
        assert reviews[1] == {} and reviews[2] == {}
        assert reviews[1] is not reviews[2]  # distinct dicts, not [{}] * n

    def test_reviews_for_no_annotator(self):
        from bmlibrarian.gui.qt.plugins.fact_checker.fact_checker_tab import (
            reviews_for_annotator,
        )
        assert reviews_for_annotator(self.RESULTS, None) == [{}, {}, {}]

    def test_filter_unannotated_keeps_alignment(self):
        from bmlibrarian.gui.qt.plugins.fact_checker.fact_checker_tab import (
            filter_unannotated, reviews_for_annotator,
        )
        reviews = reviews_for_annotator(self.RESULTS, 7)
        results, kept_reviews = filter_unannotated(self.RESULTS, reviews)
        assert [r['statement_id'] for r in results] == [2, 3]
        assert kept_reviews == [{}, {}]


@pytest.fixture
def review_package(tmp_path):
    """SQLite review package: 3 statements, alice annotated statement 1."""
    db_path = tmp_path / "review_package.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_PATH.read_text())
    conn.executemany(
        "INSERT INTO statements (statement_id, statement_text, expected_answer) "
        "VALUES (?, ?, ?)",
        [(1, "Statement one", "yes"), (2, "Statement two", "no"),
         (3, "Statement three", "maybe")],
    )
    conn.executemany(
        "INSERT INTO ai_evaluations (evaluation_id, statement_id, evaluation, reason) "
        "VALUES (?, ?, ?, ?)",
        [(10, 1, "yes", "r1"), (20, 2, "no", "r2"), (30, 3, "maybe", "r3")],
    )
    conn.execute("INSERT INTO annotators (annotator_id, username) VALUES (1, 'alice')")
    conn.execute(
        "INSERT INTO human_annotations (statement_id, annotator_id, annotation) "
        "VALUES (1, 1, 'yes')"
    )
    conn.commit()
    conn.close()
    return db_path


@pytest.mark.skipif(not HAS_QT, reason="Qt not available")
class TestTabWithReviewPackage:
    """FactCheckerTabWidget honours the launch options with a SQLite package."""

    @pytest.fixture
    def app(self):
        """Provide a QApplication instance."""
        return QApplication.instance() or QApplication([])

    def _make_tab(self, review_package, **kwargs):
        from bmlibrarian.gui.qt.plugins.fact_checker.fact_checker_tab import (
            FactCheckerTabWidget,
        )
        # Never let an error dialog block the test run
        with patch(
            "bmlibrarian.gui.qt.plugins.fact_checker.fact_checker_tab.QMessageBox"
        ) as box:
            tab = FactCheckerTabWidget(db_file=str(review_package), **kwargs)
        return tab, box

    def test_loads_sqlite_package_not_postgres(self, app, review_package):
        tab, box = self._make_tab(review_package, default_username="alice")
        assert not box.critical.called
        assert tab.db_type == "sqlite"
        assert len(tab.results) == 3
        assert tab.annotator_username == "alice"
        assert tab.reviews[0].get('human_annotation') == 'yes'
        tab.deleteLater()

    def test_incremental_hides_annotated_statements(self, app, review_package):
        tab, box = self._make_tab(
            review_package, default_username="alice", incremental=True
        )
        assert not box.critical.called
        assert [r['statement_id'] for r in tab.results] == [2, 3]
        assert "[INCREMENTAL]" in tab.status_label.text()
        tab.deleteLater()

    def test_blind_mode_flag_applied(self, app, review_package):
        tab, _ = self._make_tab(review_package, default_username="bob", blind_mode=True)
        blind_style = tab._get_blind_mode_column_stylesheet()
        assert tab.original_col.styleSheet() == blind_style
        assert tab.ai_col.styleSheet() == blind_style
        tab.deleteLater()


class TestStandaloneHelper:
    """gui.qt.core.standalone theme helper."""

    @pytest.mark.skipif(not HAS_QT, reason="Qt not available")
    def test_build_theme_stylesheet(self):
        from bmlibrarian.gui.qt.core.standalone import build_theme_stylesheet
        assert build_theme_stylesheet("light")
        assert build_theme_stylesheet("dark")
