"""
Tests for the fact-checker CLI's reporting of failed statements.

The batch run must never claim success while statements were left without a
verdict (issue #273): the exit code is non-zero and the summary marks them.
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from bmlibrarian.factchecker.agent.fact_checker_agent import (
    EVALUATION_ERROR,
    FactCheckResult,
)
from bmlibrarian.factchecker.cli import app
from bmlibrarian.factchecker.cli.formatters import print_result_summary


def _result(evaluation: str) -> FactCheckResult:
    """A minimal fact-check result with the given evaluation."""
    return FactCheckResult(
        statement="s", evaluation=evaluation, reason="r", evidence_list=[], confidence=None
    )


def _run_cli(
    tmp_path: Path, check_failures: int, storage_failures: int = 0
) -> tuple[int, Mock]:
    """Run the CLI main() against a mocked agent and return (exit code, agent)."""
    input_file = tmp_path / "statements.json"
    input_file.write_text("[]", encoding="utf-8")
    agent = Mock()
    agent.test_connection.return_value = True
    agent.check_failures = check_failures
    agent.storage_failures = storage_failures
    agent.check_batch_from_file.return_value = [_result("yes")] + [
        _result(EVALUATION_ERROR) for _ in range(check_failures)
    ]
    with patch.object(app, "create_agent", return_value=agent), patch(
        "sys.argv", ["fact_checker_cli.py", str(input_file)]
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
    assert "Maybe:   1" in out
    assert "Error:   1" in out
    assert "no verdict stored" in out
