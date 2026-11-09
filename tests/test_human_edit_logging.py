"""Tests for HumanEditLogger: what it decides to log (database insert mocked)."""

import json
from typing import Iterator
from unittest.mock import MagicMock, patch

import pytest

from bmlibrarian.agents.human_edit_logger import HumanEditLogger

QUESTION = "What are the cardiovascular benefits of exercise in elderly populations?"
DOCUMENT = {
    "id": 12345,
    "title": "Cardiovascular Benefits of Exercise in Elderly Patients",
    "abstract": "Regular aerobic exercise improved blood pressure in patients over 65.",
    "authors": ["Smith, J.", "Johnson, A."],
    "publication": "Journal of Cardiology",
    "publication_date": "2023-05-15",
}


@pytest.fixture
def insert() -> Iterator[MagicMock]:
    """Patch the database insert and return the mock."""
    with patch.object(HumanEditLogger, "_insert_to_database", return_value=True) as mock:
        yield mock


def test_score_override_is_logged(insert: MagicMock) -> None:
    """A human score that differs from the AI score is logged as an override."""
    assert HumanEditLogger().log_document_score_edit(QUESTION, DOCUMENT, 3, "partial", human_score=4)
    context, machine, human = insert.call_args.args
    assert DOCUMENT["title"] in context and QUESTION in context
    assert json.loads(machine) == {"score": 3, "reasoning": "partial"}
    assert json.loads(human) == {"score": 4, "edit_type": "override", "original_ai_score": 3}


def test_same_score_is_logged_as_approval(insert: MagicMock) -> None:
    """A human score equal to the AI score is logged as an approval."""
    HumanEditLogger().log_document_score_edit(QUESTION, DOCUMENT, 4, "good", human_score=4)
    assert json.loads(insert.call_args.args[2])["edit_type"] == "approval"


def test_passively_accepted_score_is_not_logged(insert: MagicMock) -> None:
    """No human score and no explicit approval: nothing is written."""
    assert HumanEditLogger().log_document_score_edit(QUESTION, DOCUMENT, 4, "good")
    insert.assert_not_called()


def test_query_edit_and_approval(insert: MagicMock) -> None:
    """An edited query is logged verbatim; the same query as APPROVED."""
    logger = HumanEditLogger()
    logger.log_query_edit(QUESTION, "prompt", "a & b", human_query="a & c")
    assert insert.call_args.args[1:] == ("a & b", "a & c")
    logger.log_query_edit(QUESTION, "prompt", "a & b", human_query="a & b")
    assert insert.call_args.args[2] == "APPROVED"


def test_insert_failure_returns_false() -> None:
    """An exception while logging is reported as False, not raised."""
    with patch.object(HumanEditLogger, "_insert_to_database", side_effect=RuntimeError("down")):
        assert HumanEditLogger().log_edit("ctx", "out", human_edit="edit") is False
