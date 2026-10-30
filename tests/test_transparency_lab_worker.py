"""Tests for the transparency lab's AssessmentWorker: failures reach the user."""

from typing import List
from unittest.mock import MagicMock

import pytest

pytest.importorskip("PySide6")

from bmlibrarian.agents import TransparencyAssessmentError  # noqa: E402
from bmlibrarian.lab.transparency_lab import AssessmentWorker  # noqa: E402


def _run(agent: MagicMock) -> tuple:
    """Run the worker synchronously; return (finished payloads, error messages)."""
    finished: List[object] = []
    errors: List[str] = []
    worker = AssessmentWorker(agent, {"id": 1})
    worker.finished.connect(finished.append)
    worker.error.connect(errors.append)
    worker.run()
    return finished, errors


def test_assessment_error_is_emitted_with_reason() -> None:
    """A failed assessment shows its reason and is not enriched."""
    agent = MagicMock()
    agent.assess_transparency.side_effect = TransparencyAssessmentError("No text found for document 1")

    finished, errors = _run(agent)

    assert finished == []
    assert errors == ["No text found for document 1"]
    agent.enrich_with_metadata.assert_not_called()


def test_enrichment_error_is_emitted_not_shown_as_result() -> None:
    """An unchecked retraction status is reported, not displayed as a clean result."""
    agent = MagicMock()
    agent.enrich_with_metadata.side_effect = TransparencyAssessmentError("Metadata lookup failed")

    finished, errors = _run(agent)

    assert finished == []
    assert errors == ["Metadata lookup failed"]


def test_success_emits_assessment() -> None:
    """A successful, enriched assessment is emitted."""
    agent = MagicMock()

    finished, errors = _run(agent)

    assert finished == [agent.assess_transparency.return_value]
    assert errors == []
