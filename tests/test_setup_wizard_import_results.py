"""Setup wizard: failed or partial imports must not be reported as success (#441 follow-up)."""

from bmlibrarian.gui.qt.setup_wizard.complete import CompletePage
from bmlibrarian.gui.qt.setup_wizard.import_progress import import_problems, source_result


def summary(import_results: dict) -> str:
    """The completion page's summary text (the method does not use the page)."""
    return CompletePage._build_summary(None, {}, import_results)  # type: ignore[arg-type]


class TestImportProblems:
    """What makes the worker report "finished with errors"."""

    def test_clean_run_has_no_problems(self) -> None:
        assert import_problems({"pubmed": {"total_articles": 5, "total_errors": 0}}) == []

    def test_failed_files_are_a_problem(self) -> None:
        problems = import_problems({"pubmed": {"total_articles": 5, "total_errors": 3}})
        assert len(problems) == 1 and "3 errors" in problems[0]

    def test_a_raised_source_is_a_problem(self) -> None:
        assert import_problems({"pubmed_error": "no network"}) == ["pubmed import failed: no network"]


class TestSourceResult:
    """What the wizard records per source for the completion page."""

    def test_errors_inside_a_run_are_not_success(self) -> None:
        stats = {"pubmed": {"total_articles": 5, "total_errors": 2}}
        assert source_result(stats, "pubmed") == (False, stats["pubmed"])

    def test_raised_source_keeps_its_message(self) -> None:
        assert source_result({"pubmed_error": "boom"}, "pubmed") == (False, {"error": "boom"})

    def test_source_that_did_not_run(self) -> None:
        assert source_result({"pubmed": {}}, "mesh") == (False, {})

    def test_clean_run_is_success(self) -> None:
        assert source_result({"mesh": {"descriptors": 1}}, "mesh") == (True, {"descriptors": 1})


class TestCompletionSummary:
    """The completion page shows bulk article counts, errors and failures."""

    def test_bulk_import_shows_total_articles(self) -> None:
        text = summary({"pubmed_success": True, "pubmed_stats": {"total_articles": 1234, "total_errors": 0}})
        assert "PubMed: 1,234 articles imported" in text

    def test_quick_test_shows_imported(self) -> None:
        assert "PubMed: 7 articles imported" in summary({"pubmed_success": True, "pubmed_stats": {"imported": 7}})

    def test_partial_import_shows_errors(self) -> None:
        text = summary({"pubmed_success": False, "pubmed_stats": {"total_articles": 10, "total_errors": 2}})
        assert "10 articles imported, 2 errors" in text

    def test_raised_import_shows_failure(self) -> None:
        _, stats = source_result({"pubmed_error": "boom"}, "pubmed")
        assert "PubMed: Import skipped or failed" in summary({"pubmed_success": False, "pubmed_stats": stats})
