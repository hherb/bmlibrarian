"""
Tests for dependency-managed workflow execution in AgentOrchestrator.

Covers the failure modes that used to wedge ``execute_workflow`` forever
(failed dependencies, unknown dependencies, cycles, cancelled tasks), the
re-submission of in-flight steps on every poll, and re-running a workflow.
"""

import os
import tempfile
from typing import Any, Dict, List
from unittest.mock import Mock

import pytest

from bmlibrarian.agents import (
    AgentOrchestrator, QueueManager, Workflow, WorkflowStep, WorkflowTimeoutError,
)


# Short polling keeps the tests fast; the deadline only guards against a
# regression back into an endless wait.
POLL_SECONDS = 0.01
DEADLINE_SECONDS = 10.0


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

    def test_validate_accepts_diamond(self) -> None:
        """Shared dependencies are not a cycle."""
        workflow = Workflow("diamond")
        workflow.add_step("a", WorkflowStep("agent", "m"))
        workflow.add_step("b", WorkflowStep("agent", "m", depends_on=["a"]))
        workflow.add_step("c", WorkflowStep("agent", "m", depends_on=["a"]))
        workflow.add_step("d", WorkflowStep("agent", "m", depends_on=["b", "c"]))
        workflow.validate()


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
        self.events: List[str] = []
        self.orchestrator.add_progress_callback(
            lambda event, _msg, _data: self.events.append(event)
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
        assert "workflow_step_failed" in self.events
        assert self.events.count("workflow_step_skipped") == 2
        # Not events[-1]: a worker may still emit task_failed after the loop ends.
        assert "workflow_completed" in self.events

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

    def test_workflow_can_be_executed_twice(self) -> None:
        """Re-running a workflow runs its steps again instead of returning at once."""
        workflow = self.orchestrator.create_workflow("wf")
        workflow.add_step("only", WorkflowStep("good", "run"))

        self._run("wf", {})
        results = self.orchestrator.execute_workflow("wf", {}, timeout=DEADLINE_SECONDS)

        assert results == {"only": {"value": "ok"}}
        assert self.good.run.call_count == 2

    def test_invalid_workflow_is_rejected_before_submitting(self) -> None:
        """An unsatisfiable workflow raises instead of waiting forever."""
        workflow = self.orchestrator.create_workflow("wf")
        workflow.add_step("a", WorkflowStep("good", "run", depends_on=["nope"]))

        with pytest.raises(ValueError):
            self.orchestrator.execute_workflow("wf", {}, timeout=DEADLINE_SECONDS)
        assert sum(self.orchestrator.queue.get_queue_stats().values()) == 0

    def test_unregistered_agent_is_rejected_before_submitting(self) -> None:
        """A step no agent can run would never finish, so it is refused up front."""
        workflow = self.orchestrator.create_workflow("wf")
        workflow.add_step("a", WorkflowStep("nobody", "run"))

        with pytest.raises(ValueError, match="nobody"):
            self.orchestrator.execute_workflow("wf", {}, timeout=DEADLINE_SECONDS)
        assert sum(self.orchestrator.queue.get_queue_stats().values()) == 0

    def test_no_new_steps_submitted_after_deadline(self) -> None:
        """A dependency finishing past the deadline does not queue its dependents."""
        workflow = self.orchestrator.create_workflow("wf")
        workflow.add_step("a", WorkflowStep("good", "run"))
        workflow.add_step("b", WorkflowStep("good", "run", depends_on=["a"]))

        # Without workers, complete "a" by hand once it is queued; the poll that
        # sees it completed runs only after the (tiny) deadline has passed.
        original_submit = self.orchestrator.submit_task

        def submit_and_complete(**kwargs: Any) -> str:
            task_id = original_submit(**kwargs)
            self.orchestrator.queue.complete_task(task_id, {"value": "ok"})
            return task_id

        self.orchestrator.submit_task = submit_and_complete  # type: ignore[method-assign]
        self.orchestrator.polling_interval = POLL_SECONDS * 5

        with pytest.raises(WorkflowTimeoutError) as excinfo:
            self.orchestrator.execute_workflow("wf", {}, timeout=POLL_SECONDS)

        assert excinfo.value.results == {"a": {"value": "ok"}}
        assert excinfo.value.unfinished_steps == ["b"]
        assert sum(self.orchestrator.queue.get_queue_stats().values()) == 1

    def test_cancelled_task_counts_as_failed(self) -> None:
        """A cancelled task ends its step instead of leaving it pending forever."""
        workflow = self.orchestrator.create_workflow("wf")
        workflow.add_step("a", WorkflowStep("good", "run"))
        workflow.add_step("b", WorkflowStep("good", "run", depends_on=["a"]))

        # No processing threads: cancel the queued task before anyone runs it.
        original_submit = self.orchestrator.submit_task

        def submit_then_cancel(**kwargs: Any) -> str:
            task_id = original_submit(**kwargs)
            self.orchestrator.queue.cancel_tasks(target_agent="good")
            return task_id

        self.orchestrator.submit_task = submit_then_cancel  # type: ignore[method-assign]
        results = self.orchestrator.execute_workflow("wf", {}, timeout=DEADLINE_SECONDS)

        assert results == {}
        assert workflow.failed_steps == {"a"}
        assert workflow.skipped_steps == {"b"}

    def test_timeout_raises_with_partial_state(self) -> None:
        """Without workers the deadline fires and names the unfinished steps."""
        workflow = self.orchestrator.create_workflow("wf")
        workflow.add_step("a", WorkflowStep("good", "run"))

        with pytest.raises(WorkflowTimeoutError) as excinfo:
            self.orchestrator.execute_workflow("wf", {}, timeout=POLL_SECONDS * 5)

        assert excinfo.value.workflow_name == "wf"
        assert excinfo.value.unfinished_steps == ["a"]
        assert excinfo.value.results == {}
        assert "workflow_timed_out" in self.events

    def test_task_status_missing_counts_as_failed(self) -> None:
        """A task that vanished from the queue ends its step as failed."""
        workflow = self.orchestrator.create_workflow("wf")
        workflow.add_step("a", WorkflowStep("good", "run"))
        self.orchestrator.queue.get_task_status = Mock(return_value=None)  # type: ignore[method-assign]

        results = self.orchestrator.execute_workflow("wf", {}, timeout=DEADLINE_SECONDS)

        assert results == {}
        assert workflow.failed_steps == {"a"}
