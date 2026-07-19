"""Regression tests for CLI workflow branch handling.

Guards against the bug where ``_handle_extract_citations`` and
``_handle_generate_report`` returned ``StepResult.BRANCH`` without setting
``context['branch_to_step']`` — the executor then fell through linearly, so
"zero citations" proceeded straight to report generation and ultimately
exported a ``None`` report instead of retrying with adjusted thresholds.

Also guards the retry loop itself: the threshold-adjustment step must be
bounded (no infinite EXTRACT_CITATIONS <-> ADJUST_SCORING_THRESHOLDS loop).

Hermetic: no Ollama, PostgreSQL, or user interaction required.
"""

from unittest.mock import Mock

import pytest

from bmlibrarian.cli.workflow_handlers import WorkflowStepHandlers
from bmlibrarian.cli.workflow_steps import StepResult, WorkflowStep


def _make_handlers(score_threshold: float = 2.5) -> WorkflowStepHandlers:
    """Build WorkflowStepHandlers with fully mocked collaborators."""
    config = Mock()
    config.auto_mode = True
    config.default_score_threshold = score_threshold
    return WorkflowStepHandlers(
        config=config,
        ui=Mock(),
        agent_manager=Mock(),
        state_manager=Mock(),
        execution_manager=Mock(),
    )


def test_extract_citations_failure_sets_branch_target() -> None:
    """No citations -> BRANCH with an explicit, existing branch target."""
    handlers = _make_handlers()
    handlers.execution_manager.execute_citation_extraction.return_value = []
    context = {"research_question": "q", "scored_documents": [({"id": 1}, {"score": 3})]}

    result = handlers._handle_extract_citations(context)

    assert result == StepResult.BRANCH
    assert context.get("branch_to_step") == WorkflowStep.ADJUST_SCORING_THRESHOLDS


def test_generate_report_failure_sets_branch_target() -> None:
    """No report -> BRANCH with an explicit, existing branch target."""
    handlers = _make_handlers()
    handlers.execution_manager.execute_report_generation.return_value = None
    context = {"research_question": "q", "citations": [Mock()]}

    result = handlers._handle_generate_report(context)

    assert result == StepResult.BRANCH
    assert context.get("branch_to_step") == WorkflowStep.REQUEST_MORE_CITATIONS


def test_threshold_adjustment_lowers_threshold_and_retries() -> None:
    """First adjustment lowers the threshold and branches back to extraction."""
    handlers = _make_handlers(score_threshold=2.5)
    context: dict = {}

    result = handlers._handle_adjust_scoring_thresholds(context)

    assert result == StepResult.BRANCH
    assert context.get("branch_to_step") == WorkflowStep.EXTRACT_CITATIONS
    assert handlers.config.default_score_threshold < 2.5


def test_threshold_adjustment_is_bounded() -> None:
    """Repeated adjustment must terminate with FAILURE, not loop forever."""
    handlers = _make_handlers(score_threshold=2.5)
    context: dict = {}

    results = [
        handlers._handle_adjust_scoring_thresholds(context) for _ in range(10)
    ]

    assert StepResult.FAILURE in results, (
        "threshold adjustment never terminates - infinite workflow loop"
    )
    # Once it fails it must not keep branching afterwards
    first_failure = results.index(StepResult.FAILURE)
    assert all(r == StepResult.FAILURE for r in results[first_failure:])


def test_request_more_citations_is_bounded() -> None:
    """The more-citations path shares the bounded retry budget."""
    handlers = _make_handlers(score_threshold=2.5)
    context: dict = {}

    results = [handlers._handle_request_more_citations(context) for _ in range(10)]

    assert StepResult.FAILURE in results, (
        "request-more-citations never terminates - infinite workflow loop"
    )
