"""Tests for transparency_analyzer_cli.py: failures are reported, NULLs stay unassessed."""

import argparse
import json
from typing import List, Optional, Tuple
from unittest.mock import MagicMock, patch

import pytest

import transparency_analyzer_cli as cli
from src.bmlibrarian.agents import TransparencyAssessmentError, TransparencyBatchResult


def _args(output: Optional[str] = None) -> argparse.Namespace:
    """Arguments for `assess` with no filters."""
    return argparse.Namespace(
        doc_id=None, has_fulltext=False, query=None, limit=None, output=output
    )


def _run_assess(
    agent: MagicMock,
    documents: list,
    output: Optional[str] = None,
    save_side_effect: object = None,
) -> Tuple[Optional[int], MagicMock, MagicMock]:
    """Run cmd_assess with the DB and agent replaced.

    Returns:
        ``(exit code or None, save mock, connection mock)``.
    """
    conn = MagicMock()
    with patch.object(cli, "get_db_connection", return_value=conn), \
            patch.object(cli, "create_agent", return_value=agent), \
            patch.object(cli, "fetch_documents_for_assessment", return_value=documents), \
            patch.object(cli, "save_assessment", side_effect=save_side_effect) as save:
        try:
            cli.cmd_assess(_args(output))
        except SystemExit as e:
            return e.code, save, conn
    return None, save, conn


def _agent(assessments: list, failures: List[Tuple[str, str]]) -> MagicMock:
    """A mock agent whose assess_batch returns the given outcome."""
    agent = MagicMock()
    agent.assess_batch.return_value = TransparencyBatchResult(
        assessments=assessments, failures=failures
    )
    agent.format_assessment_summary.return_value = "summary"
    return agent


def _assessment(doc_id: str) -> cli.TransparencyAssessment:
    """A minimal successful assessment."""
    return cli.TransparencyAssessment(document_id=doc_id, document_title="ok")


def test_failures_are_listed_and_exit_nonzero(capsys) -> None:
    """Each failed document and its reason is printed; successes are still saved."""
    good = _assessment("1")
    agent = _agent([good], [("2", "No text found for document 2")])

    code, save, conn = _run_assess(agent, [{"id": 1}, {"id": 2}])

    assert code == 1
    save.assert_called_once_with(conn, good)
    out = capsys.readouterr().out
    assert "FAILED: 1 of 2 documents" in out
    assert "Document 2: No text found for document 2" in out


def test_failures_still_export_successes(tmp_path) -> None:
    """The export runs before the non-zero exit and names the failures."""
    good = _assessment("1")
    failures = [("2", "No text found for document 2")]
    agent = _agent([good], failures)
    output = str(tmp_path / "r.json")

    code, _, _ = _run_assess(agent, [{"id": 1}, {"id": 2}], output=output)

    assert code == 1
    agent.export_to_json.assert_called_once_with([good], output, failures=failures)


def test_all_succeeded_exits_normally(capsys) -> None:
    """No failures: no failure report, no exit."""
    good = _assessment("1")

    code, save, conn = _run_assess(_agent([good], []), [{"id": 1}])

    assert code is None
    save.assert_called_once_with(conn, good)
    assert "FAILED" not in capsys.readouterr().out


def test_enrichment_failure_is_not_saved(capsys) -> None:
    """Without the metadata lookup the retraction status is unknown: not saved, reported."""
    good, unchecked = _assessment("1"), _assessment("2")
    agent = _agent([good, unchecked], [])
    agent.enrich_with_metadata.side_effect = [
        good,
        TransparencyAssessmentError("Metadata lookup failed for document 2"),
    ]

    code, save, conn = _run_assess(agent, [{"id": 1}, {"id": 2}])

    assert code == 1
    save.assert_called_once_with(conn, good)
    out = capsys.readouterr().out
    assert "FAILED: 1 of 2 documents" in out
    assert "NOT ASSESSED (1)" in out
    assert "Document 2: Metadata lookup failed for document 2" in out


def test_save_failure_rolls_back_and_exits_nonzero(capsys) -> None:
    """A failed save rolls back so later saves work, and the run exits 1."""
    first, second = _assessment("1"), _assessment("2")

    code, save, conn = _run_assess(
        _agent([first, second], []),
        [{"id": 1}, {"id": 2}],
        save_side_effect=[RuntimeError("constraint violated"), None],
    )

    assert code == 1
    assert save.call_count == 2
    conn.rollback.assert_called_once()
    out = capsys.readouterr().out
    assert "Saved to database: 1" in out
    assert "NOT SAVED (1)" in out
    assert "Document 1: constraint violated" in out


def test_save_rejects_non_numeric_document_id() -> None:
    """A document that cannot be saved is not silently counted as saved."""
    conn = MagicMock()
    with pytest.raises(ValueError, match="non-numeric"):
        cli.save_assessment(conn, _assessment("abc"))
    conn.cursor.assert_not_called()


def _fake_connection(fetchone: Optional[list] = None, fetchall: Optional[list] = None) -> MagicMock:
    """A connection whose cursor returns the given rows."""
    cursor = MagicMock()
    if fetchone is not None:
        cursor.fetchone.side_effect = fetchone
    cursor.fetchall.return_value = fetchall
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    return conn


def test_show_null_columns_are_not_assessed(capsys) -> None:
    """NULL quality/confidence columns print as 'not assessed', not 0%."""
    # Columns in cmd_show's SELECT order
    row = (
        42, 5.0, "medium", 0.2,                 # id, score, risk, overall_confidence
        True, "Funded by X.", ["X"], True,      # funding disclosure, statement, sources, industry
        None, None,                             # industry_funding_confidence, funding quality
        True, "None declared.", [], None,       # COI disclosure, statement, conflicts, quality
        "not_stated", None, False, None,        # data availability, contributions
        False, [], [], [], [],                  # registration, ids, indicators, strengths, weaknesses
        False, None, None, "model", "1.0", None,  # retraction, sponsor, model, version, assessed_at
    )
    conn = _fake_connection(fetchone=[("joined",), row, ("Title",)])

    with patch.object(cli, "get_db_connection", return_value=conn):
        cli.cmd_show(argparse.Namespace(doc_id=42))

    out = capsys.readouterr().out
    assert "quality: not assessed" in out
    assert "confidence: not assessed" in out
    assert "quality: 0%" not in out
    assert "LOW CONFIDENCE" in out


def test_export_keeps_nulls_and_industry_confidence(tmp_path) -> None:
    """Export carries the stored industry confidence and leaves NULL qualities unassessed."""
    # Columns in cmd_export's SELECT order
    row = (
        7, "Title", "10.1/x", 3.0, "high", 0.3,  # id, title, doi, score, risk, confidence
        True, ["Pfizer"], True, None,            # funding disclosure, sources, industry, quality
        True, None,                              # COI disclosure, quality
        "not_stated", False, False, [],          # data, contributions, registration, ids
        [], [], [], False, "INDUSTRY",           # indicators, strengths, weaknesses, retraction, sponsor
        0.95,                                    # industry_funding_confidence
    )
    output = tmp_path / "e.json"
    conn = _fake_connection(fetchall=[row])

    with patch.object(cli, "get_db_connection", return_value=conn):
        cli.cmd_export(argparse.Namespace(output=str(output), format="json"))

    exported = json.loads(output.read_text())["assessments"][0]
    assert exported["industry_funding_confidence"] == 0.95
    assert exported["funding_disclosure_quality"] is None
    assert exported["coi_disclosure_quality"] is None
    assert exported["low_confidence"] is True
