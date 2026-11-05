"""
Queue worker robustness (#294).

Covers: an unserialisable result fails the task without re-running the agent
method, while a database error storing it re-queues the task; agent errors name
their exception type; a claimed task never stays PROCESSING silently; a worker
stops when its queue file is deleted; SIGTERM exits with 128 + signum, the
signal path neither takes the queue lock nor waits out the busy timeout, and
cleanup errors go to stderr; process-wide handlers are installed once however
many QueueManagers exist; manual stuck-task recovery spends the retry budget;
re-registering an agent takes effect on the next task without a second worker.
"""

import signal
import sqlite3
import subprocess
import sys
import threading
import time
import weakref
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

import bmlibrarian.agents.queue_manager as qm
from bmlibrarian.agents import AgentOrchestrator, QueueManager, TaskStatus

AGENT = "worker"
WAIT_SECONDS = 10.0
POLL_SECONDS = 0.01


@pytest.fixture
def queue(tmp_path: Path) -> QueueManager:
    """A file-backed queue in a temporary directory."""
    return QueueManager(str(tmp_path / "queue.db"))


@pytest.fixture
def orchestrator(queue: QueueManager) -> AgentOrchestrator:
    """An orchestrator over the temporary queue, not processing."""
    return AgentOrchestrator(queue_manager=queue, polling_interval=POLL_SECONDS)


def claim(queue: QueueManager, method: str = "run", **task: Any) -> Any:
    """Add a task for AGENT and claim it, as a worker thread would."""
    queue.add_task(target_agent=AGENT, method_name=method, data={}, **task)
    claimed = queue.get_next_task(AGENT)
    assert claimed is not None
    return claimed


def backdate_started_at(queue: QueueManager, task_id: str) -> None:
    """Make a processing task look stuck since 2000-01-01."""
    with sqlite3.connect(queue.db_path) as conn:
        conn.execute("UPDATE queue_tasks SET started_at = ? WHERE id = ?",
                     (datetime(2000, 1, 1, tzinfo=timezone.utc).isoformat(), task_id))


class TestResultStorageFailure:
    """Only the agent method's own failure is retried."""

    def test_unserialisable_result_fails_once_without_retry(
            self, queue: QueueManager, orchestrator: AgentOrchestrator) -> None:
        """A datetime in the result fails the task; the method is not re-run."""
        agent = Mock()
        agent.run.return_value = {"when": datetime(2026, 1, 1)}
        orchestrator.register_agent(AGENT, agent)
        events = []
        orchestrator.add_progress_callback(lambda e, _m, d: events.append((e, d)))
        task = claim(queue)

        orchestrator._run_task(AGENT, task)

        stored = queue.get_task_status(task.id)
        assert stored.status == TaskStatus.FAILED
        assert stored.error_message.startswith(
            "Task result is not JSON-serialisable: TypeError")
        assert agent.run.call_count == 1
        assert queue.get_next_task(AGENT) is None  # not re-queued
        assert [e for e, _ in events] == ["task_started", "task_failed"]

    def test_agent_error_is_retried_and_names_its_type(
            self, queue: QueueManager, orchestrator: AgentOrchestrator) -> None:
        """str(KeyError('x')) is "'x'", which hides the type, so the message names it."""
        agent = Mock()
        agent.run.side_effect = KeyError("x")
        orchestrator.register_agent(AGENT, agent)
        task = claim(queue)

        orchestrator._run_task(AGENT, task)

        stored = queue.get_task_status(task.id)
        assert stored.status == TaskStatus.PENDING
        assert stored.retry_count == 1
        assert stored.error_message == "Task execution failed: KeyError: 'x'"

    def test_complete_task_writes_nothing_for_an_unserialisable_result(
            self, queue: QueueManager) -> None:
        """The serialisation error is raised before any write."""
        task = claim(queue)

        with pytest.raises(qm.ResultNotSerializableError, match="TypeError"):
            queue.complete_task(task.id, {"when": datetime(2026, 1, 1)})

        assert queue.get_task_status(task.id).status == TaskStatus.PROCESSING

    def test_database_error_storing_result_requeues_the_task(
            self, queue: QueueManager, orchestrator: AgentOrchestrator,
            monkeypatch: pytest.MonkeyPatch) -> None:
        """A locked database is transient: retry rather than discard the work."""
        agent = Mock()
        agent.run.return_value = {"ok": True}
        orchestrator.register_agent(AGENT, agent)
        monkeypatch.setattr(queue, "complete_task", Mock(
            side_effect=sqlite3.OperationalError("database is locked")))
        task = claim(queue)

        orchestrator._run_task(AGENT, task)

        stored = queue.get_task_status(task.id)
        assert (stored.status, stored.retry_count) == (TaskStatus.PENDING, 1)
        assert stored.error_message == ("Task result could not be written to the "
                                        "queue: OperationalError: database is locked")

    def test_missing_method_fails_without_retry(
            self, queue: QueueManager, orchestrator: AgentOrchestrator) -> None:
        """An agent without the method fails the task once and reports it."""
        orchestrator.register_agent(AGENT, Mock(spec=["run"]))
        events = []
        orchestrator.add_progress_callback(lambda e, _m, d: events.append(e))
        task = claim(queue, method="missing")

        orchestrator._run_task(AGENT, task)

        stored = queue.get_task_status(task.id)
        assert stored.status == TaskStatus.FAILED
        assert stored.error_message == f"Method missing not found on agent {AGENT}"
        assert events == ["task_started", "task_failed"]


class TestClaimedTaskNeverSilentlyStuck:
    """A claimed task is always finished or reported."""

    def test_unexpected_error_fails_the_task(
            self, queue: QueueManager, orchestrator: AgentOrchestrator) -> None:
        """An error escaping _run_task fails the task without retry."""
        task = claim(queue)

        orchestrator._abandon_task(AGENT, task, RuntimeError("boom"))

        stored = queue.get_task_status(task.id)
        assert stored.status == TaskStatus.FAILED
        assert stored.error_message == "Worker error: RuntimeError: boom"

    def test_unwritable_queue_reports_the_stuck_task(
            self, queue: QueueManager, orchestrator: AgentOrchestrator,
            monkeypatch: pytest.MonkeyPatch) -> None:
        """If failing the task also fails, a task_stuck event says so."""
        monkeypatch.setattr(queue, "fail_task", Mock(
            side_effect=sqlite3.OperationalError("disk I/O error")))
        events = []
        orchestrator.add_progress_callback(lambda e, m, _d: events.append((e, m)))
        task = claim(queue)

        orchestrator._abandon_task(AGENT, task, RuntimeError("boom"))

        assert [e for e, _ in events] == ["task_stuck"]
        assert "queue_cli recover" in events[0][1]

    def test_worker_stops_when_its_queue_file_is_deleted(
            self, queue: QueueManager, orchestrator: AgentOrchestrator) -> None:
        """The loop returns instead of recreating an empty file every poll."""
        orchestrator.register_agent(AGENT, Mock())
        events = []
        orchestrator.add_progress_callback(lambda e, _m, _d: events.append(e))
        Path(queue.db_path).unlink()

        orchestrator._process_agent_tasks(AGENT)  # returns, does not loop

        assert events == ["worker_stopped"]
        assert not Path(queue.db_path).exists()


class TestReRegisteredAgent:
    """The worker looks the agent up per task."""

    def test_running_worker_uses_the_new_agent(
            self, orchestrator: AgentOrchestrator) -> None:
        """Re-registering while processing replaces the agent for the next task."""
        old, new = Mock(), Mock()
        old.run.return_value = {"by": "old"}
        new.run.return_value = {"by": "new"}
        orchestrator.register_agent(AGENT, old)
        orchestrator.start_processing()
        try:
            orchestrator.register_agent(AGENT, new)
            task_id = orchestrator.submit_task(AGENT, "run", {})
            done = orchestrator.wait_for_completion([task_id], timeout=WAIT_SECONDS)
        finally:
            orchestrator.stop_processing()

        assert done[task_id].status == TaskStatus.COMPLETED
        assert done[task_id].result == {"by": "new"}
        old.run.assert_not_called()

    def test_re_registering_does_not_start_a_second_worker(
            self, orchestrator: AgentOrchestrator) -> None:
        """The running worker for the type is reused."""
        orchestrator.register_agent(AGENT, Mock())
        orchestrator.start_processing()
        try:
            orchestrator.register_agent(AGENT, Mock())
            assert len(orchestrator._processing_threads) == 1
        finally:
            orchestrator.stop_processing()


class TestRecoverStuckTasks:
    """Resetting a stuck task to pending counts as a retry."""

    def test_reset_spends_retries_then_fails(self, queue: QueueManager) -> None:
        """With max_retries=1 the first recovery resets, the second fails."""
        task = claim(queue, max_retries=1)
        backdate_started_at(queue, task.id)

        assert queue.recover_stuck_tasks(stuck_timeout_minutes=1) == 1
        reset = queue.get_task_status(task.id)
        assert (reset.status, reset.retry_count) == (TaskStatus.PENDING, 1)

        assert queue.get_next_task(AGENT).id == task.id
        backdate_started_at(queue, task.id)
        assert queue.recover_stuck_tasks(stuck_timeout_minutes=1) == 1
        failed = queue.get_task_status(task.id)
        assert failed.status == TaskStatus.FAILED
        assert failed.retry_count == 2
        assert "retries exhausted" in failed.error_message


class TestProcessWideHandlers:
    """atexit and signal handlers are installed once per process."""

    def test_many_managers_install_handlers_once(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Three managers register one atexit hook and two signal handlers."""
        monkeypatch.setattr(qm, "_live_managers", weakref.WeakSet())
        monkeypatch.setattr(qm, "_atexit_registered", False)
        monkeypatch.setattr(qm, "_signal_handlers_installed", False)
        atexit_register, signal_install = Mock(), Mock()
        monkeypatch.setattr(qm.atexit, "register", atexit_register)
        monkeypatch.setattr(qm.signal, "signal", signal_install)

        managers = [QueueManager(str(tmp_path / f"q{i}.db")) for i in range(3)]

        atexit_register.assert_called_once_with(qm._cleanup_all_on_exit)
        assert sorted(c.args[0] for c in signal_install.call_args_list) == sorted(
            [signal.SIGINT, signal.SIGTERM])
        assert set(qm._live_managers) == set(managers)

    def test_signal_handlers_wait_for_a_main_thread_manager(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """A manager built off the main thread installs none; a later main-thread one does."""
        monkeypatch.setattr(qm, "_live_managers", weakref.WeakSet())
        monkeypatch.setattr(qm, "_atexit_registered", False)
        monkeypatch.setattr(qm, "_signal_handlers_installed", False)
        monkeypatch.setattr(qm.atexit, "register", Mock())
        signal_install = Mock()
        monkeypatch.setattr(qm.signal, "signal", signal_install)

        worker = threading.Thread(target=QueueManager, args=(str(tmp_path / "w.db"),))
        worker.start()
        worker.join(WAIT_SECONDS)
        signal_install.assert_not_called()

        QueueManager(str(tmp_path / "m.db"))
        assert sorted(c.args[0] for c in signal_install.call_args_list) == sorted(
            [signal.SIGINT, signal.SIGTERM])

    def test_signal_cleanup_does_not_take_the_queue_lock(
            self, queue: QueueManager) -> None:
        """The interrupted code may hold queue.lock; the handler must not wait for it."""
        task = claim(queue)
        with queue.lock:
            handler = threading.Thread(
                target=queue._signal_handler, args=(signal.SIGTERM, None), daemon=True)
            handler.start()
            handler.join(WAIT_SECONDS)
            assert not handler.is_alive()
        assert queue.get_task_status(task.id).status == TaskStatus.FAILED

    def test_signal_cleanup_gives_up_quickly_on_a_held_write_lock(
            self, queue: QueueManager, capsys: pytest.CaptureFixture) -> None:
        """A write lock held by the interrupted frame does not freeze Ctrl-C."""
        claim(queue)
        blocker = sqlite3.connect(queue.db_path)
        blocker.execute("BEGIN IMMEDIATE")
        try:
            start = time.monotonic()
            queue._signal_handler(signal.SIGTERM, None)
            elapsed = time.monotonic() - start
        finally:
            blocker.rollback()
            blocker.close()

        assert elapsed < qm.QUEUE_BUSY_TIMEOUT_MS / 1000 / 2
        assert "retrying at exit" in capsys.readouterr().err

    def test_exit_cleanup_skips_a_deleted_queue_file(self, tmp_path: Path) -> None:
        """Cleanup does not recreate an empty database for a deleted queue."""
        path = tmp_path / "gone.db"
        manager = QueueManager(str(path))
        path.unlink()

        manager._cleanup_on_exit()

        assert not path.exists()

    def test_cleanup_error_goes_to_stderr(
            self, queue: QueueManager, monkeypatch: pytest.MonkeyPatch,
            capsys: pytest.CaptureFixture) -> None:
        """A failing cleanup is reported, not swallowed."""
        monkeypatch.setattr(queue, "_mark_process_tasks_as_failed",
                            Mock(side_effect=sqlite3.OperationalError("locked")))

        queue._cleanup_on_exit()
        queue._signal_handler(signal.SIGTERM, None)

        err = capsys.readouterr().err
        assert err.count("QueueManager cleanup failed") == 2
        assert "OperationalError: locked" in err

    def test_signal_fails_in_flight_tasks_and_exits_128_plus_signum(
            self, queue: QueueManager, monkeypatch: pytest.MonkeyPatch) -> None:
        """The handler marks this process's tasks failed, then exits 143."""
        monkeypatch.setattr(qm, "_live_managers", weakref.WeakSet([queue]))
        task = claim(queue)

        with pytest.raises(SystemExit) as exc:
            qm._handle_termination_signal(signal.SIGTERM, None)

        assert exc.value.code == qm.SIGNAL_EXIT_STATUS_BASE + signal.SIGTERM
        stored = queue.get_task_status(task.id)
        assert stored.status == TaskStatus.FAILED
        assert stored.error_message == f"Process terminated by signal {signal.SIGTERM}"

    def test_sigterm_exit_status_in_a_real_process(self, tmp_path: Path) -> None:
        """A process holding a QueueManager reports SIGTERM to its shell as 143."""
        script = (
            "import os, signal, sys\n"
            "from bmlibrarian.agents.queue_manager import QueueManager\n"
            "q = QueueManager(sys.argv[1])\n"
            "os.kill(os.getpid(), signal.SIGTERM)\n"
        )
        proc = subprocess.run(
            [sys.executable, "-c", script, str(tmp_path / "q.db")],
            capture_output=True, text=True, timeout=120,
        )
        assert proc.returncode == qm.SIGNAL_EXIT_STATUS_BASE + signal.SIGTERM, proc.stderr
