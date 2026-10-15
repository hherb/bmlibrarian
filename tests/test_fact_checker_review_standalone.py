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

    def test_validate_db_file(self, tmp_path, review_package):
        """Validate db file."""
        launcher = _load_launcher()
        assert launcher.validate_db_file(None) is None
        missing = str(tmp_path / "missing.db")
        assert "not found" in launcher.validate_db_file(missing)
        assert missing in launcher.validate_db_file(missing)
        wrong = tmp_path / "package.sqlite"
        wrong.write_bytes(b"")
        assert ".db" in launcher.validate_db_file(str(wrong))
        assert launcher.validate_db_file(str(review_package)) is None

    def test_validate_rejects_non_package_without_changing_it(self, tmp_path):
        """Any other SQLite .db is rejected read-only (no WAL switch)."""
        launcher = _load_launcher()
        other = tmp_path / "other.db"
        conn = sqlite3.connect(other)
        conn.execute("CREATE TABLE unrelated (x INTEGER)")
        conn.commit()
        conn.close()

        error = launcher.validate_db_file(str(other))
        assert "not a BMLibrarian review package" in error
        assert "export_review_package.py" in error
        conn = sqlite3.connect(other)
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] != "wal"
        conn.close()

    def test_main_rejects_missing_package(self, tmp_path, capsys):
        launcher = _load_launcher()
        assert launcher.main(["--db-file", str(tmp_path / "missing.db")]) == 1
        assert "not found" in capsys.readouterr().err

    def test_main_passes_every_option_to_the_tab(self, review_package):
        """All four flags reach FactCheckerTabWidget, under the right names."""
        launcher = _load_launcher()
        captured = {}

        def fake_run(widget_factory, title, argv=None):
            """Build the widget via its factory instead of starting Qt."""
            captured['widget'] = widget_factory()
            captured['title'] = title
            return 0

        with patch("bmlibrarian.gui.qt.core.standalone.run_widget_standalone",
                   side_effect=fake_run), \
             patch("bmlibrarian.gui.qt.plugins.fact_checker.fact_checker_tab."
                   "FactCheckerTabWidget") as tab_cls:
            exit_code = launcher.main([
                "--user", "alice", "--blind", "--incremental",
                "--db-file", str(review_package),
            ])

        assert exit_code == 0
        tab_cls.assert_called_once_with(
            db_file=str(review_package), default_username="alice",
            blind_mode=True, incremental=True,
        )
        assert "Fact-Checker" in captured['title']


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

    @staticmethod
    def _annotations(review_package):
        """Return {(statement_id, username): annotation} from the package."""
        conn = sqlite3.connect(review_package)
        rows = conn.execute(
            "SELECT h.statement_id, a.username, h.annotation "
            "FROM human_annotations h JOIN annotators a USING (annotator_id)"
        ).fetchall()
        conn.close()
        return {(sid, user): annotation for sid, user, annotation in rows}

    @staticmethod
    def _add_annotation(review_package, username, annotator_id, statement_ids):
        """Give ``username`` annotations on ``statement_ids``."""
        conn = sqlite3.connect(review_package)
        conn.execute(
            "INSERT OR IGNORE INTO annotators (annotator_id, username) VALUES (?, ?)",
            (annotator_id, username),
        )
        conn.executemany(
            "INSERT INTO human_annotations (statement_id, annotator_id, annotation) "
            "VALUES (?, ?, 'no')",
            [(sid, annotator_id) for sid in statement_ids],
        )
        conn.commit()
        conn.close()

    @staticmethod
    def _choose(tab, annotation):
        """Select an annotation in the human dropdown (saves immediately)."""
        tab.human_dropdown.setCurrentIndex(tab.human_dropdown.findData(annotation))

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

    def test_blind_mode_hides_reference_answers(self, app, review_package):
        """Blind reviewers can neither see nor reveal the AI/original answers."""
        tab, _ = self._make_tab(review_package, default_username="alice", blind_mode=True)
        tab.show()
        try:
            assert not tab.original_col.isVisible()
            assert not tab.ai_col.isVisible()
            assert tab.ai_text.toPlainText() == ""
            assert "r1" not in tab.ai_text.toPlainText()
            assert tab.original_tag.text() in ("", "N/A")
            assert not tab.show_review_toggle.isVisible()
            tab._on_toggle_review()  # even if triggered, it cannot un-blind
            assert not tab.ai_col.isVisible()
            tab._on_next()
            assert tab.ai_text.toPlainText() == ""
        finally:
            tab.close()
            tab.deleteLater()

    def test_without_blind_mode_answers_are_shown(self, app, review_package):
        """Without blind mode answers are shown."""
        tab, _ = self._make_tab(review_package, default_username="alice")
        assert tab.ai_text.toPlainText() == "r1"
        tab.deleteLater()

    def test_incremental_all_annotated_is_not_an_error(self, app, review_package):
        """Having nothing left is a finished state, with no stale rows."""
        self._add_annotation(review_package, "alice", 1, [2, 3])
        tab, box = self._make_tab(
            review_package, default_username="alice", incremental=True
        )
        assert not box.critical.called
        assert tab.results == [] and tab.reviews == []
        assert "nothing left" in tab.status_label.text()
        assert not tab.human_dropdown.isEnabled()
        assert not tab.prev_button.isEnabled() and not tab.next_button.isEnabled()
        tab.deleteLater()

    def test_incremental_switch_after_all_annotated(self, app, review_package):
        """From the finished state, switching user reloads that user's subset."""
        self._add_annotation(review_package, "alice", 1, [2, 3])
        self._add_annotation(review_package, "bob", 2, [3])
        tab, _ = self._make_tab(review_package, default_username="alice", incremental=True)
        tab.username_field.setText("bob")
        tab._on_username_changed()
        assert [r['statement_id'] for r in tab.results] == [1, 2]
        assert tab.human_dropdown.isEnabled()
        tab.deleteLater()

    def test_incremental_switch_saves_to_the_right_statement(self, app, review_package):
        """Reloading on a user switch keeps annotations on the right row."""
        self._add_annotation(review_package, "bob", 2, [3])
        tab, _ = self._make_tab(review_package, default_username="alice", incremental=True)
        assert [r['statement_id'] for r in tab.results] == [2, 3]

        tab.username_field.setText("bob")
        tab._on_username_changed()
        assert [r['statement_id'] for r in tab.results] == [1, 2]
        self._choose(tab, "yes")
        assert self._annotations(review_package)[(1, "bob")] == "yes"
        tab.deleteLater()

    def test_navigating_without_annotating_writes_nothing(self, app, review_package):
        """'n/a' is never written (the schema rejects it) and no error shows."""
        tab, _ = self._make_tab(review_package, default_username="alice")
        tab._on_next()   # leave statement 1 (annotated 'yes')
        tab._on_next()   # leave statement 2 without annotating
        assert (2, "alice") not in self._annotations(review_package)
        assert "NOT saved" not in tab.status_label.text()
        assert tab.auto_save_label.text() == tab.AUTO_SAVE_OK_TEXT
        tab.deleteLater()

    def test_unclear_annotation_is_saved(self, app, review_package):
        """Unclear annotation is saved."""
        tab, _ = self._make_tab(review_package, default_username="alice")
        tab._on_next()
        self._choose(tab, "unclear")
        assert self._annotations(review_package)[(2, "alice")] == "unclear"
        tab.deleteLater()

    def test_save_failure_is_reported(self, app, review_package):
        """A failed save is shown, and the local review is not updated."""
        tab, _ = self._make_tab(review_package, default_username="alice")
        tab._on_next()
        with patch.object(tab.fact_checker_db, "insert_human_annotation",
                          side_effect=RuntimeError("disk full")):
            self._choose(tab, "no")
        assert "NOT saved" in tab.status_label.text()
        assert "disk full" in tab.status_label.text()
        assert tab.auto_save_label.text() == tab.AUTO_SAVE_FAILED_TEXT
        assert not tab.reviews[1].get('human_annotation')
        tab.deleteLater()

    def test_unknown_user_is_not_created_silently(self, app, review_package):
        """A --user typo must be confirmed before it becomes an annotator."""
        tab, box = self._make_tab(review_package, default_username="alcie")
        assert tab.annotator_id is None
        assert "Unknown annotator 'alcie'" in tab.status_label.text()
        self._choose(tab, "maybe")
        users = {user for _, user in self._annotations(review_package)}
        assert "alcie" not in users
        conn = sqlite3.connect(review_package)
        assert conn.execute(
            "SELECT COUNT(*) FROM annotators WHERE username = 'alcie'"
        ).fetchone()[0] == 0
        conn.close()
        tab.deleteLater()

    def test_load_failure_is_shown_and_can_be_retried(self, app, tmp_path, review_package):
        """A failed load shows the reason (no modal) and retries on confirm."""
        broken = tmp_path / "broken.db"
        sqlite3.connect(broken).close()  # empty database: no tables
        tab, box = self._make_tab(broken, default_username="alice")
        assert not box.critical.called
        assert tab._load_failed
        assert "Error loading data" in tab.status_label.text()
        assert not tab.human_dropdown.isEnabled()

        tab.db_file = str(review_package)  # e.g. the user fixed the file
        tab._on_username_changed()
        assert not tab._load_failed
        assert len(tab.results) == 3
        tab.deleteLater()


class TestStandaloneHelper:
    """gui.qt.core.standalone theme helper."""

    @pytest.mark.skipif(not HAS_QT, reason="Qt not available")
    def test_build_theme_stylesheet(self):
        from bmlibrarian.gui.qt.core.standalone import build_theme_stylesheet
        assert build_theme_stylesheet("light")
        assert build_theme_stylesheet("dark")
