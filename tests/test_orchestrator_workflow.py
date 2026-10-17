"""
Tests for dependency-managed workflow execution in AgentOrchestrator.

Covers the failure modes that used to wedge ``execute_workflow`` forever
(failed dependencies, unknown dependencies, cycles, cancelled tasks, agents
registered after processing started), the re-submission of in-flight steps
on every poll, timeouts and aborts (which cancel the run's queued tasks), and
re-running a workflow.
"""

import os
import sqlite3
import tempfile
from types import SimpleNamespace
from typing import Any, Dict, List, Tuple
from unittest.mock import Mock

import pytest

import bmlibrarian.agents.orchestrator as orchestrator_module
from bmlibrarian.agents import (
    AgentOrchestrator, QueueManager, TaskStatus, Workflow, WorkflowStep,
    WorkflowTimeoutError,
)


# Short polling keeps the tests fast; the deadline only guards against a
# regression back into an endless wait.
POLL_SECONDS = 0.01
DEADLINE_SECONDS = 10.0
# Fake-clock timeout; any reading at or past it means "deadline passed".
FAKE_TIMEOUT_SECONDS = 1.0
FAKE_TIME_PAST_DEADLINE = 100.0


def use_fake_clock(monkeypatch: pytest.MonkeyPatch, readings: List[float]) -> None:
    """
    Replace the orchestrator's clock: ``monotonic`` returns ``readings`` in
    order, then a time far past any deadline; ``sleep`` returns at once.

    Only for tests without processing threads, which would busy-loop.
    """
    ticks = iter(readings)
    fake_time = SimpleNamespace(
        monotonic=lambda: next(ticks, FAKE_TIME_PAST_DEADLINE),
        sleep=lambda _seconds: None,
    )
    monkeypatch.setattr(orchestrator_module, "time", fake_time)


class TestWorkflowState:
    """Pure state handling of the Workflow class."""

    def _chain(self) -> Workflow:
        """Build a -> b -> c plus an independent d."""
        workflow = Workflow("chain")
        workflow.add_step("a", WorkflowStep("agent", "m"))
        workflow.add_step("b", WorkflowStep("agent", "m", depends_on=["a"]))
        workflow.add_step("c", WorkflowStep("agent", "m", depends_on=["b"]))
        workflow.add_step("d", WorkflowStep("agent", "m"))
        return workflow

    def _diamond(self) -> Workflow:
        """Build a -> {b, c} -> d."""
        workflow = Workflow("diamond")
        workflow.add_step("a", WorkflowStep("agent", "m"))
        workflow.add_step("b", WorkflowStep("agent", "m", depends_on=["a"]))
        workflow.add_step("c", WorkflowStep("agent", "m", depends_on=["a"]))
        workflow.add_step("d", WorkflowStep("agent", "m", depends_on=["b", "c"]))
        return workflow

    def test_submitted_steps_are_not_ready_again(self) -> None:
        """A step in flight must not be handed out a second time."""
        workflow = self._chain()
        workflow.mark_submitted("a")
        assert workflow.get_ready_steps() == ["d"]

    def test_failure_skips_dependents_transitively(self) -> None:
        """Failing a step skips everything that depends on it, directly or not."""
        workflow = self._chain()
        skipped = workflow.mark_failed("a")
        assert set(skipped) == {"b", "c"}
        assert workflow.skipped_steps == {"b", "c"}
        assert workflow.get_ready_steps() == ["d"]
        workflow.mark_completed("d")
        assert workflow.is_complete()

    def test_failed_branch_skips_join_but_not_sibling(self) -> None:
        """In a diamond, one failed branch skips the join but not the other branch."""
        workflow = self._diamond()
        workflow.mark_completed("a")
        assert workflow.mark_failed("b") == ["d"]
        assert workflow.get_unfinished_steps() == ["c"]
        workflow.mark_completed("c")
        assert workflow.is_complete()

    def test_reset_clears_progress(self) -> None:
        """reset() makes a finished workflow runnable again."""
        workflow = self._chain()
        workflow.mark_submitted("d")
        workflow.mark_completed("d")
        workflow.mark_failed("a")
        workflow.reset()
        assert workflow.completed_steps == set()
        assert workflow.failed_steps == set()
        assert workflow.skipped_steps == set()
        assert workflow.get_ready_steps() == ["a", "d"]

    def test_reset_clears_steps_still_in_flight(self) -> None:
        """A step left submitted by a timed-out run is ready again after reset()."""
        workflow = self._chain()
        workflow.mark_submitted("a")
        workflow.reset()
        assert workflow.submitted_steps == set()
        assert "a" in workflow.get_ready_steps()

    def test_state_changes_reject_unknown_steps(self) -> None:
        """Marking a step that does not exist is a bug, not a no-op."""
        workflow = self._chain()
        for mark in (workflow.mark_submitted, workflow.mark_completed, workflow.mark_failed):
            with pytest.raises(KeyError, match="typo"):
                mark("typo")

    def test_state_changes_reject_finished_steps(self) -> None:
        """A finished step never moves into a second state."""
        workflow = self._chain()
        workflow.mark_failed("a")
        with pytest.raises(ValueError, match="already finished"):
            workflow.mark_completed("b")  # skipped
        with pytest.raises(ValueError, match="already finished"):
            workflow.mark_failed("a")
        with pytest.raises(ValueError, match="already finished"):
            workflow.mark_submitted("c")

    def test_step_cannot_be_submitted_twice(self) -> None:
        """Submitting an in-flight step again raises."""
        workflow = self._chain()
        workflow.mark_submitted("a")
        with pytest.raises(ValueError, match="already submitted"):
            workflow.mark_submitted("a")

    def test_validate_rejects_unknown_dependency(self) -> None:
        """A dependency on a step that does not exist can never be satisfied."""
        workflow = Workflow("bad")
        workflow.add_step("a", WorkflowStep("agent", "m", depends_on=["missing"]))
        with pytest.raises(ValueError, match="missing"):
            workflow.validate()

    def test_validate_rejects_cycle(self) -> None:
        """A dependency cycle can never be satisfied."""
        workflow = Workflow("cycle")
        workflow.add_step("a", WorkflowStep("agent", "m", depends_on=["b"]))
        workflow.add_step("b", WorkflowStep("agent", "m", depends_on=["a"]))
        with pytest.raises(ValueError, match="cycle"):
            workflow.validate()

    def test_validate_rejects_self_dependency(self) -> None:
        """A step depending on itself is a cycle."""
        workflow = Workflow("self")
        workflow.add_step("a", WorkflowStep("agent", "m", depends_on=["a"]))
        with pytest.raises(ValueError, match="cycle"):
            workflow.validate()

    def test_validate_accepts_diamond(self) -> None:
        """Shared dependencies are not a cycle."""
        self._diamond().validate()


class TestExecuteWorkflow:
    """End-to-end execute_workflow runs against a real SQLite queue."""

    def setup_method(self) -> None:
        """Create an orchestrator with a temporary queue and two mock agents."""
        temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        temp_db.close()
        self.temp_db_path = temp_db.name
        self.orchestrator = AgentOrchestrator(
            queue_manager=QueueManager(self.temp_db_path),
            polling_interval=POLL_SECONDS,
        )
        self.good = Mock()
        self.good.run.return_value = {"value": "ok"}
        self.bad = Mock()
        self.bad.run.side_effect = RuntimeError("boom")
        self.orchestrator.register_agent("good", self.good)
        self.orchestrator.register_agent("bad", self.bad)
        self.events: List[Tuple[str, Any]] = []
        self.orchestrator.add_progress_callback(
            lambda event, _msg, data: self.events.append((event, data))
        )

    def teardown_method(self) -> None:
        """Stop workers and remove the queue database."""
        self.orchestrator.stop_processing()
        try:
            os.unlink(self.temp_db_path)
        except OSError:
            pass

    def _run(self, workflow_name: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a workflow with background processing and a safety deadline."""
        self.orchestrator.start_processing()
        return self.orchestrator.execute_workflow(
            workflow_name, data, timeout=DEADLINE_SECONDS
        )

    def _event_names(self) -> List[str]:
        """Names of the progress events received so far."""
        return [name for name, _data in self.events]

    def _event_data(self, name: str) -> List[Any]:
        """Payloads of every progress event with the given name."""
        return [data for event, data in self.events if event == name]

    def _queued_task_count(self) -> int:
        """Number of tasks in the queue, whatever their status."""
        return sum(self.orchestrator.queue.get_queue_stats().values())

    def test_failed_dependency_finishes_instead_of_wedging(self) -> None:
        """Dependents of a failed step are skipped and the workflow returns."""
        workflow = self.orchestrator.create_workflow("wf")
        workflow.add_step("first", WorkflowStep("bad", "run", max_retries=0))
        workflow.add_step("second", WorkflowStep("good", "run", depends_on=["first"]))
        workflow.add_step("third", WorkflowStep("good", "run", depends_on=["second"]))

        results = self._run("wf", {})

        assert results == {}
        assert workflow.failed_steps == {"first"}
        assert workflow.skipped_steps == {"second", "third"}
        self.good.run.assert_not_called()
        [failed] = self._event_data("workflow_step_failed")
        assert failed["status"] == "failed"
        assert "boom" in failed["error"]
        skipped = self._event_data("workflow_step_skipped")
        assert {d["step_name"] for d in skipped} == {"second", "third"}
        # Not events[-1]: a worker may still emit task_failed after the loop ends.
        [completed] = self._event_data("workflow_completed")
        assert completed["success"] is False

    def test_independent_branch_result_survives_a_failure(self) -> None:
        """Completed steps are returned even when another branch failed."""
        workflow = self.orchestrator.create_workflow("wf")
        workflow.add_step("ok", WorkflowStep("good", "run"))
        workflow.add_step("broken", WorkflowStep("bad", "run", max_retries=0))
        workflow.add_step("after", WorkflowStep("good", "run", depends_on=["broken"]))

        results = self._run("wf", {})

        assert results == {"ok": {"value": "ok"}}
        assert workflow.failed_steps == {"broken"}
        assert workflow.skipped_steps == {"after"}

    def test_each_step_runs_exactly_once(self) -> None:
        """In-flight steps are not resubmitted on every poll."""
        workflow = self.orchestrator.create_workflow("wf")
        workflow.add_step("first", WorkflowStep("good", "run"))
        workflow.add_step("second", WorkflowStep("good", "run", depends_on=["first"]))

        results = self._run("wf", {"question": "q"})

        assert set(results) == {"first", "second"}
        assert self.good.run.call_count == 2
        # The dependent step receives its dependency's result.
        second_kwargs = self.good.run.call_args_list[1].kwargs
        assert second_kwargs["question"] == "q"
        assert second_kwargs["first_result"] == {"value": "ok"}
        [completed] = self._event_data("workflow_completed")
        assert completed["success"] is True

    def test_join_step_receives_every_dependency_result(self) -> None:
        """A step with two dependencies gets both results as keyword arguments."""
        workflow = self.orchestrator.create_workflow("wf")
        workflow.add_step("a", WorkflowStep("good", "run"))
        workflow.add_step("b", WorkflowStep("good", "run", depends_on=["a"]))
        workflow.add_step("c", WorkflowStep("good", "run", depends_on=["a"]))
        workflow.add_step("d", WorkflowStep("good", "run", depends_on=["b", "c"]))

        results = self._run("wf", {"question": "q"})

        assert set(results) == {"a", "b", "c", "d"}
        [join_kwargs] = [call.kwargs for call in self.good.run.call_args_list
                         if "b_result" in call.kwargs]
        assert join_kwargs == {"question": "q", "b_result": {"value": "ok"},
                               "c_result": {"value": "ok"}}

    def test_retried_step_completes(self) -> None:
        """A failed attempt with retries left is not mistaken for a failed step."""
        self.bad.run.side_effect = [RuntimeError("flaky"), {"value": "ok"}]
        workflow = self.orchestrator.create_workflow("wf")
        workflow.add_step("a", WorkflowStep("bad", "run", max_retries=1))

        results = self._run("wf", {})

        assert results == {"a": {"value": "ok"}}
        assert self.bad.run.call_count == 2
        assert workflow.failed_steps == set()

    def test_workflow_can_be_executed_twice(self) -> None:
        """Re-running a workflow runs its steps again instead of returning at once."""
        workflow = self.orchestrator.create_workflow("wf")
        workflow.add_step("only", WorkflowStep("good", "run"))

        self._run("wf", {})
        results = self.orchestrator.execute_workflow("wf", {}, timeout=DEADLINE_SECONDS)

        assert results == {"only": {"value": "ok"}}
        assert self.good.run.call_count == 2

    def test_rerun_after_timeout_completes(self) -> None:
        """A timed-out run cancels its queued task, and a re-run starts afresh."""
        workflow = self.orchestrator.create_workflow("wf")
        workflow.add_step("a", WorkflowStep("good", "run"))

        with pytest.raises(WorkflowTimeoutError):
            self.orchestrator.execute_workflow("wf", {}, timeout=POLL_SECONDS * 5)
        results = self._run("wf", {})

        assert results == {"a": {"value": "ok"}}
        # The first run's task was cancelled, so it never ran.
        assert self.good.run.call_count == 1

    def test_agent_registered_after_start_processing_runs(self) -> None:
        """A late-registered agent gets a processing thread instead of hanging."""
        self.orchestrator.start_processing()
        late = Mock()
        late.run.return_value = {"value": "late"}
        self.orchestrator.register_agent("late", late)
        workflow = self.orchestrator.create_workflow("wf")
        workflow.add_step("a", WorkflowStep("late", "run"))

        results = self.orchestrator.execute_workflow("wf", {}, timeout=DEADLINE_SECONDS)

        assert results == {"a": {"value": "late"}}

    def test_missing_processing_thread_is_warned_about(
            self, caplog: pytest.LogCaptureFixture) -> None:
        """Running without processing threads logs which agents have none."""
        workflow = self.orchestrator.create_workflow("wf")
        workflow.add_step("a", WorkflowStep("good", "run"))

        with pytest.raises(WorkflowTimeoutError):
            self.orchestrator.execute_workflow("wf", {}, timeout=POLL_SECONDS)

        assert "no processing thread for agent type(s) good" in caplog.text

    def test_concurrent_execution_of_same_workflow_is_rejected(self) -> None:
        """A second execution while the first is running raises instead of corrupting it."""
        workflow = self.orchestrator.create_workflow("wf")
        workflow.add_step("a", WorkflowStep("good", "run"))
        nested_errors: List[Exception] = []

        def run_again(event: str, _msg: str, _data: Any) -> None:
            """Try to start the same workflow from inside its first run."""
            if event == "workflow_started" and not nested_errors:
                try:
                    self.orchestrator.execute_workflow("wf", {}, timeout=DEADLINE_SECONDS)
                except RuntimeError as e:
                    nested_errors.append(e)

        self.orchestrator.add_progress_callback(run_again)
        results = self._run("wf", {})

        assert results == {"a": {"value": "ok"}}
        assert len(nested_errors) == 1
        assert "already being executed" in str(nested_errors[0])

    def test_invalid_workflow_is_rejected_before_submitting(self) -> None:
        """An unsatisfiable workflow raises instead of waiting forever."""
        workflow = self.orchestrator.create_workflow("wf")
        workflow.add_step("a", WorkflowStep("good", "run", depends_on=["nope"]))

        with pytest.raises(ValueError, match="unknown step"):
            self.orchestrator.execute_workflow("wf", {}, timeout=DEADLINE_SECONDS)
        assert self._queued_task_count() == 0

    def test_unregistered_agent_is_rejected_before_submitting(self) -> None:
        """A step for an agent type nobody registered is refused up front."""
        workflow = self.orchestrator.create_workflow("wf")
        workflow.add_step("a", WorkflowStep("nobody", "run"))

        with pytest.raises(ValueError, match="nobody"):
            self.orchestrator.execute_workflow("wf", {}, timeout=DEADLINE_SECONDS)
        assert self._queued_task_count() == 0

    def _complete_on_submit(self) -> None:
        """Without workers, complete each task by hand as soon as it is queued."""
        original_submit = self.orchestrator.submit_task

        def submit_and_complete(**kwargs: Any) -> str:
            """Submit the task, then mark it completed as a worker would."""
            task_id = original_submit(**kwargs)
            self.orchestrator.queue.complete_task(task_id, {"value": "ok"})
            return task_id

        self.orchestrator.submit_task = submit_and_complete  # type: ignore[method-assign]

    def test_no_new_steps_submitted_after_deadline(
            self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A dependency finishing past the deadline does not queue its dependents."""
        workflow = self.orchestrator.create_workflow("wf")
        workflow.add_step("a", WorkflowStep("good", "run"))
        workflow.add_step("b", WorkflowStep("good", "run", depends_on=["a"]))
        self._complete_on_submit()
        # Clock readings: deadline set, first deadline check, sleep length;
        # the second deadline check (after "a" completed) is past it.
        use_fake_clock(monkeypatch, [0.0, 0.0, 0.0])

        with pytest.raises(WorkflowTimeoutError) as excinfo:
            self.orchestrator.execute_workflow("wf", {}, timeout=FAKE_TIMEOUT_SECONDS)

        assert excinfo.value.results == {"a": {"value": "ok"}}
        assert excinfo.value.unfinished_steps == ["b"]
        assert self._queued_task_count() == 1

    def test_completion_wins_over_a_passed_deadline(
            self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A workflow that finishes in the poll crossing the deadline returns normally."""
        workflow = self.orchestrator.create_workflow("wf")
        workflow.add_step("a", WorkflowStep("good", "run"))
        self._complete_on_submit()
        # Deadline set and first check at 0; every later reading is past it.
        use_fake_clock(monkeypatch, [0.0, 0.0])

        results = self.orchestrator.execute_workflow("wf", {}, timeout=FAKE_TIMEOUT_SECONDS)

        assert results == {"a": {"value": "ok"}}

    def test_cancelled_task_counts_as_failed(self) -> None:
        """A cancelled task ends its step instead of leaving it pending forever."""
        workflow = self.orchestrator.create_workflow("wf")
        workflow.add_step("a", WorkflowStep("good", "run"))
        workflow.add_step("b", WorkflowStep("good", "run", depends_on=["a"]))

        # No processing threads: cancel the queued task before anyone runs it.
        original_submit = self.orchestrator.submit_task

        def submit_then_cancel(**kwargs: Any) -> str:
            """Submit the task, then cancel it before any worker sees it."""
            task_id = original_submit(**kwargs)
            self.orchestrator.queue.cancel_tasks(target_agent="good")
            return task_id

        self.orchestrator.submit_task = submit_then_cancel  # type: ignore[method-assign]
        results = self.orchestrator.execute_workflow("wf", {}, timeout=DEADLINE_SECONDS)

        assert results == {}
        assert workflow.failed_steps == {"a"}
        assert workflow.skipped_steps == {"b"}
        [failed] = self._event_data("workflow_step_failed")
        assert failed["status"] == "cancelled"
        assert failed["error"] == "task cancelled"

    def test_timeout_raises_and_cancels_queued_tasks(self) -> None:
        """Without workers the deadline fires, names the unfinished steps and
        cancels the task nobody started."""
        workflow = self.orchestrator.create_workflow("wf")
        workflow.add_step("a", WorkflowStep("good", "run"))

        with pytest.raises(WorkflowTimeoutError) as excinfo:
            self.orchestrator.execute_workflow("wf", {}, timeout=POLL_SECONDS * 5)

        assert isinstance(excinfo.value, TimeoutError)
        assert excinfo.value.workflow_name == "wf"
        assert excinfo.value.unfinished_steps == ["a"]
        assert excinfo.value.results == {}
        assert excinfo.value.running_steps == {}
        assert "workflow_timed_out" in self._event_names()
        stats = self.orchestrator.queue.get_queue_stats()
        assert stats[TaskStatus.CANCELLED.value] == 1
        assert self._queued_task_count() == 1

    def test_queue_error_aborts_and_cancels_queued_tasks(self) -> None:
        """A queue failure mid-run is re-raised after reporting and cleanup."""
        workflow = self.orchestrator.create_workflow("wf")
        workflow.add_step("a", WorkflowStep("good", "run"))
        self.orchestrator.queue.get_task_status = Mock(  # type: ignore[method-assign]
            side_effect=sqlite3.OperationalError("database is locked"))

        with pytest.raises(sqlite3.OperationalError):
            self.orchestrator.execute_workflow("wf", {}, timeout=DEADLINE_SECONDS)

        [aborted] = self._event_data("workflow_aborted")
        assert "database is locked" in aborted["error"]
        stats = self.orchestrator.queue.get_queue_stats()
        assert stats[TaskStatus.CANCELLED.value] == 1
        # The aborted run no longer counts as running.
        with pytest.raises(sqlite3.OperationalError):
            self.orchestrator.execute_workflow("wf", {}, timeout=DEADLINE_SECONDS)

    def test_task_status_missing_counts_as_failed(self) -> None:
        """A task that vanished from the queue fails its step and skips dependents."""
        workflow = self.orchestrator.create_workflow("wf")
        workflow.add_step("a", WorkflowStep("good", "run"))
        workflow.add_step("b", WorkflowStep("good", "run", depends_on=["a"]))
        self.orchestrator.queue.get_task_status = Mock(return_value=None)  # type: ignore[method-assign]

        results = self.orchestrator.execute_workflow("wf", {}, timeout=DEADLINE_SECONDS)

        assert results == {}
        assert workflow.failed_steps == {"a"}
        assert workflow.skipped_steps == {"b"}
        [failed] = self._event_data("workflow_step_failed")
        assert failed["status"] == "missing"
