"""
Tests for how the systematic review tab's worker presents agent progress events.

Warnings (``EVENT_REVIEW_WARNING``, ``synthesis_failed``) must reach the
activity log, and events without a mapped progress percentage must not move
the overall progress bar.
"""

from __future__ import annotations

from typing import Iterator, List, Tuple
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QCoreApplication

from bmlibrarian.agents.systematic_review import EVENT_REVIEW_WARNING
from bmlibrarian.gui.qt.plugins.systematic_review.systematic_review_tab import (
    ReviewWorker,
)


@pytest.fixture
def worker() -> Iterator[ReviewWorker]:
    """A review worker that is never started."""
    app = QCoreApplication.instance() or QCoreApplication([])
    assert app is not None
    yield ReviewWorker(db_manager=MagicMock(), mode="new")


@pytest.mark.parametrize("event", [EVENT_REVIEW_WARNING, "synthesis_failed"])
def test_warnings_are_shown_in_the_activity_log(worker: ReviewWorker, event: str) -> None:
    """A warning event becomes a visible activity-log entry with its message."""
    entry = worker._format_activity_entry(event, "3 papers could not be scored")
    assert entry is not None
    assert "Warning" in entry and "3 papers could not be scored" in entry


def test_unmapped_events_keep_the_current_progress(worker: ReviewWorker) -> None:
    """An event without a percentage leaves the progress bar where it was."""
    emitted: List[Tuple[str, int]] = []
    worker.progress_update.connect(lambda message, pct: emitted.append((message, pct)))

    worker._progress_callback("quality_assessment_started", "Assessing 3 papers")
    worker._progress_callback(EVENT_REVIEW_WARNING, "something went wrong")

    assert [pct for _, pct in emitted] == [75, 75]
