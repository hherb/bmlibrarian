"""Tests for transparency_analyzer_cli.py `assess`: failures are reported."""

import argparse
from unittest.mock import MagicMock, patch

import pytest

import transparency_analyzer_cli as cli
from src.bmlibrarian.agents import TransparencyBatchResult


def _args() -> argparse.Namespace:
    """Arguments for `assess` with no filters and no export."""
    return argparse.Namespace(
        doc_id=None, has_fulltext=False, query=None, limit=None, output=None
    )


def _run_assess(agent: MagicMock, documents: list) -> MagicMock:
    """Run cmd_assess with the DB and agent replaced; return the save mock."""
    with patch.object(cli, "get_db_connection", return_value=MagicMock()), \
            patch.object(cli, "create_agent", return_value=agent), \
            patch.object(cli, "fetch_documents_for_assessment", return_value=documents), \
            patch.object(cli, "save_assessment") as save:
        cli.cmd_assess(_args())
    return save


def _agent(assessments: list, failures: list) -> MagicMock:
    """A mock agent whose assess_batch returns the given outcome."""
    agent = MagicMock()
    agent.assess_batch.return_value = TransparencyBatchResult(
        assessments=assessments, failures=failures
    )
    agent.format_assessment_summary.return_value = "summary"
    return agent


def test_failures_are_listed_and_exit_nonzero(capsys) -> None:
    """Each failed document and its reason is printed; successes are still saved."""
    good = cli.TransparencyAssessment(document_id="1", document_title="ok")
    agent = _agent([good], [("2", "No text found for document 2")])

    with pytest.raises(SystemExit) as exc:
        _run_assess(agent, [{"id": 1}, {"id": 2}])

    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "FAILED: 1 of 2 documents" in out
    assert "Document 2: No text found for document 2" in out


def test_all_succeeded_exits_normally(capsys) -> None:
    """No failures: no failure report, no exit."""
    good = cli.TransparencyAssessment(document_id="1", document_title="ok")
    save = _run_assess(_agent([good], []), [{"id": 1}])

    save.assert_called_once()
    assert "FAILED" not in capsys.readouterr().out
