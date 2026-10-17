"""
Tests for the fact-checker CLI's reporting of failed statements.

The batch run must never claim success while statements were left without a
verdict (issue #273): the exit code is non-zero and the summary marks them.
"""

import re
from pathlib import Path
from typing import List, Optional
from unittest.mock import Mock, patch

import pytest

from bmlibrarian.factchecker.agent.fact_checker_agent import (
    EVALUATION_ERROR,
    STAGE_SCORING,
    FactCheckResult,
    FactCheckStageError,
)
from bmlibrarian.factchecker.cli import app
from bmlibrarian.factchecker.cli.formatters import (
    print_detailed_results,
    print_result_summary,
)


def _result(
    evaluation: str, statement: str = "s", notes: Optional[List[str]] = None
) -> FactCheckResult:
    """A minimal fact-check result: a verdict, or a failed check for EVALUATION_ERROR."""
    if evaluation == EVALUATION_ERROR:
        return FactCheckResult.failed(
            statement=statement,
            error=FactCheckStageError(STAGE_SCORING, "ollama down"),
            expected_answer="yes",
        )
    return FactCheckResult(
        statement=statement, evaluation=evaluation, reason="r", evidence_list=[],
        confidence="medium", degradation_notes=notes or [],
    )


def _run_cli(
    tmp_path: Path,
    check_failures: int,
    storage_failures: int = 0,
    degraded: int = 0,
    export_failed: bool = False,
    extra_args: tuple = (),
) -> tuple[int, Mock]:
    """Run the CLI main() against a mocked agent and return (exit code, agent)."""
    input_file = tmp_path / "statements.json"
    input_file.write_text("[]", encoding="utf-8")
    agent = Mock()
    agent.test_connection.return_value = True
    agent.check_failures = check_failures
    agent.storage_failures = storage_failures
    agent.degraded_results = degraded
    agent.export_failed = export_failed
    agent.session_bookkeeping_failed = False
    verdicts = [_result("yes", notes=["bm25 search failed"] if degraded else None)]
    agent.stored_results = len(verdicts) - storage_failures
    agent.check_batch_from_file.return_value = verdicts + [
        _result(EVALUATION_ERROR, statement=f"failed statement {i}")
        for i in range(check_failures)
    ]
    with patch.object(app, "create_agent", return_value=agent), patch(
        "sys.argv", ["fact_checker_cli.py", str(input_file), *extra_args]
    ):
        return app.main(), agent


def test_cli_exits_zero_when_every_statement_got_a_verdict(tmp_path: Path) -> None:
    """A clean batch exits 0."""
    exit_code, _ = _run_cli(tmp_path, check_failures=0)

    assert exit_code == 0


def test_cli_exits_non_zero_and_warns_on_failed_checks(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Statements that could not be checked fail the run and are explained."""
    exit_code, _ = _run_cli(tmp_path, check_failures=2)

    out = capsys.readouterr().out
    assert exit_code == 1
    assert "2 statement(s) could not be checked" in out
    assert "--incremental" in out


def test_cli_exits_non_zero_on_storage_failures(tmp_path: Path) -> None:
    """Results that failed to persist also fail the run."""
    exit_code, _ = _run_cli(tmp_path, check_failures=0, storage_failures=1)

    assert exit_code == 1


def test_summary_of_no_results_does_not_divide_by_zero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An incremental run with nothing left to check prints a summary, not a crash."""
    print_result_summary([])

    assert "No statements were checked" in capsys.readouterr().out


def test_summary_marks_errors_as_unstored(capsys: pytest.CaptureFixture[str]) -> None:
    """Failed checks are listed separately from the verdicts."""
    print_result_summary([_result("maybe"), _result(EVALUATION_ERROR)])

    out = capsys.readouterr().out
    assert re.search(r"Maybe:\s+1\b", out)
    assert re.search(r"Error:\s+1\b", out)
    assert "no verdict stored" in out


def test_failed_statements_are_listed_without_verbose(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The user learns which statements failed, and at which stage."""
    _run_cli(tmp_path, check_failures=2)

    out = capsys.readouterr().out
    assert "failed statement 0" in out
    assert "failed statement 1" in out
    assert "relevance scoring" in out


def test_stored_count_is_reported_from_the_real_count(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """'Stored' is not claimed for results that failed to store or to check."""
    _run_cli(tmp_path, check_failures=1)

    out = capsys.readouterr().out
    assert "1 verdict(s) stored" in out
    assert re.search(r"Total statements attempted:\s+2", out)


def test_failed_export_fails_the_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A JSON export that was not written is not reported as saved."""
    exit_code, _ = _run_cli(
        tmp_path, check_failures=0, export_failed=True, extra_args=("-o", "out.json")
    )

    out = capsys.readouterr().out
    assert exit_code == 1
    assert "JSON export saved" not in out
    assert "JSON export FAILED" in out


def test_partial_evidence_verdicts_are_flagged(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verdicts based on partial evidence are pointed out (but are stored verdicts)."""
    exit_code, _ = _run_cli(tmp_path, check_failures=0, degraded=1)

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "1 verdict(s) are based on partial evidence" in out


def test_summary_counts_partial_evidence_verdicts(capsys: pytest.CaptureFixture[str]) -> None:
    """The summary separates complete checks from partial-evidence ones."""
    print_result_summary([_result("yes", notes=["semantic search failed"]), _result("no")])

    assert re.search(r"partial evidence:\s+1\b", capsys.readouterr().out, re.IGNORECASE)


def test_detailed_output_of_a_failed_check_is_not_a_mismatch(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A failed check shows its stage and no '✗' against the expected answer."""
    print_detailed_results([_result(EVALUATION_ERROR)])

    out = capsys.readouterr().out
    assert "✗" not in out
    assert "relevance scoring" in out
    assert "no verdict" in out.lower()


def test_detailed_output_lists_partial_evidence_notes(capsys: pytest.CaptureFixture[str]) -> None:
    """The notes of a partial-evidence verdict are printed."""
    print_detailed_results([_result("maybe", notes=["2 of 9 documents could not be scored"])])

    assert "2 of 9 documents could not be scored" in capsys.readouterr().out
