"""
Queue follow-ups to #294: Ctrl-C, task ownership, recovery reporting.

#384: QueueManager leaves SIGINT alone, so Ctrl-C stays a KeyboardInterrupt
that callers can catch; an uncaught one still fails in-flight tasks at exit.
#385: a worker's result or failure is written only while it still holds the
task; recovery skips tasks whose process is alive unless forced.
#386: recovery reports reset/failed/skipped separately; ``task_failed`` says
whether the task will be retried.
"""

import logging
import signal
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Tuple
from unittest.mock import Mock

import pytest

import bmlibrarian.agents.queue_manager as qm
from bmlibrarian.agents import AgentOrchestrator, QueueManager, TaskStatus

AGENT = "worker"
SUBPROCESS_TIMEOUT_SECONDS = 120
DEAD_PID = 2 ** 22 + 12345  # above the default Linux/macOS pid ranges


@pytest.fixture
def queue(tmp_path: Path) -> QueueManager:
    """A file-backed queue in a temporary directory."""
    return QueueManager(str(tmp_path / "queue.db"))


def claim(queue: QueueManager, **task: Any) -> qm.QueueTask:
    """Add a task for AGENT and claim it, as a worker thread would."""
    queue.add_task(target_agent=AGENT, method_name="run", data={}, **task)
    claimed = queue.get_next_task(AGENT)
    assert claimed is not None
    return claimed


def make_stuck(queue: QueueManager, task_id: str, process_id: Any = None) -> None:
    """Backdate a processing task; optionally change its owning process."""
    with sqlite3.connect(queue.db_path) as conn:
        conn.execute("UPDATE queue_tasks SET started_at = ? WHERE id = ?",
                     (datetime(2000, 1, 1, tzinfo=timezone.utc).isoformat(), task_id))
        if process_id is not None:
            conn.execute("UPDATE queue_tasks SET process_id = ? WHERE id = ?",
                         (process_id, task_id))


def run_script(script: str, *args: str) -> subprocess.CompletedProcess:
    """Run a Python snippet in a fresh interpreter."""
    return subprocess.run([sys.executable, "-c", script, *args], capture_output=True,
                          text=True, timeout=SUBPROCESS_TIMEOUT_SECONDS)


class TestCtrlCStaysKeyboardInterrupt:
    """#384."""

    def test_ctrl_c_is_catchable_after_a_queue_exists(self, tmp_path: Path) -> None:
        """A CLI-style ``except KeyboardInterrupt`` still sees Ctrl-C."""
        proc = run_script(
            "import os, signal, sys, time\n"
            "from bmlibrarian.agents.queue_manager import QueueManager\n"
            "q = QueueManager(sys.argv[1])\n"
            "try:\n"
            "    os.kill(os.getpid(), signal.SIGINT)\n"
            "    time.sleep(5)\n"
            "except KeyboardInterrupt:\n"
            "    print('caught')\n",
            str(tmp_path / "q.db"))
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip() == "caught"

    def test_uncaught_ctrl_c_fails_in_flight_tasks_at_exit(self, tmp_path: Path) -> None:
        """The atexit hook marks this process's claimed task FAILED."""
        db = tmp_path / "q.db"
        proc = run_script(
            "import os, signal, sys, time\n"
            "from bmlibrarian.agents.queue_manager import QueueManager\n"
            "q = QueueManager(sys.argv[1])\n"
            "q.add_task(target_agent='worker', method_name='run', data={})\n"
            "q.get_next_task('worker')\n"
            "os.kill(os.getpid(), signal.SIGINT)\n"
            "time.sleep(5)\n",
            str(db))
        assert proc.returncode != 0
        assert "KeyboardInterrupt" in proc.stderr
        with sqlite3.connect(db) as conn:
            assert conn.execute("SELECT status, error_message FROM queue_tasks").fetchall() == [
                (TaskStatus.FAILED.value, "Process terminated")]


class TestOwnership:
    """#385: only the worker holding a task may finish it."""

    def test_result_of_a_recovered_task_is_discarded(
            self, queue: QueueManager, caplog: pytest.LogCaptureFixture) -> None:
        """Forced recovery resets the task; the old worker's result is not stored."""
        task = claim(queue)
        make_stuck(queue, task.id)
        assert queue.recover_stuck_tasks(stuck_timeout_minutes=1, force=True).reset == 1

        with caplog.at_level(logging.WARNING, logger=qm.__name__):
            assert queue.complete_task(task.id, {"late": True}, worker_id=task.worker_id) is False

        stored = queue.get_task_status(task.id)
        assert (stored.status, stored.result) == (TaskStatus.PENDING, None)
        assert "result was discarded" in caplog.text

    def test_old_worker_cannot_overwrite_a_re_claimed_task(self, queue: QueueManager) -> None:
        """A second claim (another worker id) keeps PROCESSING after the first fails."""
        task = claim(queue)
        make_stuck(queue, task.id)
        queue.recover_stuck_tasks(stuck_timeout_minutes=1, force=True)
        with sqlite3.connect(queue.db_path) as conn:
            conn.execute("UPDATE queue_tasks SET status = ?, worker_id = ? WHERE id = ?",
                         (TaskStatus.PROCESSING.value, "other-worker", task.id))

        assert queue.fail_task(task.id, "late", retry=False, worker_id=task.worker_id) is None
        assert queue.complete_task(task.id, {"x": 1}, worker_id=task.worker_id) is False
        stored = queue.get_task_status(task.id)
        assert (stored.status, stored.worker_id) == (TaskStatus.PROCESSING, "other-worker")

    def test_task_failed_after_retries_exhausted_stays_failed(self, queue: QueueManager) -> None:
        """Recovery fails a task out of retries; the worker's later result does not flip it."""
        task = claim(queue, max_retries=0)
        make_stuck(queue, task.id)
        assert queue.recover_stuck_tasks(stuck_timeout_minutes=1, force=True).failed == 1

        assert queue.complete_task(task.id, {"x": 1}, worker_id=task.worker_id) is False
        assert queue.get_task_status(task.id).status == TaskStatus.FAILED

    def test_owner_still_completes_and_fails_normally(self, queue: QueueManager) -> None:
        """The holding worker's writes go through; fail_task reports the outcome."""
        done = claim(queue)
        assert queue.complete_task(done.id, {"ok": 1}, worker_id=done.worker_id) is True
        assert queue.get_task_status(done.id).status == TaskStatus.COMPLETED

        retried = claim(queue, max_retries=1)
        assert queue.fail_task(retried.id, "e", worker_id=retried.worker_id) is TaskStatus.PENDING
        again = queue.get_next_task(AGENT)
        assert queue.fail_task(again.id, "e", worker_id=again.worker_id) is TaskStatus.FAILED

    def test_missing_task_failure_is_logged(
            self, queue: QueueManager, caplog: pytest.LogCaptureFixture) -> None:
        """Failing a removed task is reported, not silent."""
        with caplog.at_level(logging.WARNING, logger=qm.__name__):
            assert queue.fail_task("no-such-task", "boom") is None
        assert "no-such-task not found" in caplog.text


class TestRecoveryCounts:
    """#385/#386: recovery skips live processes and reports what it did."""

    def test_running_process_is_skipped_unless_forced(self, queue: QueueManager) -> None:
        """This test process is alive, so its stuck task is left PROCESSING."""
        task = claim(queue)
        make_stuck(queue, task.id)

        assert queue.recover_stuck_tasks(stuck_timeout_minutes=1) == qm.RecoveryCounts(
            skipped_running=1)
        assert queue.get_task_status(task.id).status == TaskStatus.PROCESSING

    def test_counts_reset_failed_and_skipped_separately(self, queue: QueueManager) -> None:
        """Dead process → failed, unknown owner → reset, live process → skipped."""
        dead, unowned, live = claim(queue), claim(queue), claim(queue)
        make_stuck(queue, dead.id, process_id=DEAD_PID)
        make_stuck(queue, unowned.id, process_id=0)  # falsy: no recorded owner
        make_stuck(queue, live.id)

        counts = queue.recover_stuck_tasks(stuck_timeout_minutes=1)

        assert counts == qm.RecoveryCounts(reset=1, failed=1, skipped_running=1)
        assert counts.recovered == 2
        assert queue.get_task_status(dead.id).status == TaskStatus.FAILED
        assert queue.get_task_status(unowned.id).status == TaskStatus.PENDING

    def test_another_users_process_counts_as_alive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """os.kill raising PermissionError means the process exists."""
        monkeypatch.setattr(qm.os, "kill", Mock(side_effect=PermissionError))
        assert qm._process_alive(1) is True
        monkeypatch.setattr(qm.os, "kill", Mock(side_effect=ProcessLookupError))
        assert qm._process_alive(1) is False

    def test_cli_prints_each_count(self, queue: QueueManager,
                                   capsys: pytest.CaptureFixture) -> None:
        """queue-cli recover says how many were reset, failed and skipped."""
        from bmlibrarian import queue_cli

        dead, live = claim(queue), claim(queue)
        make_stuck(queue, dead.id, process_id=DEAD_PID)
        make_stuck(queue, live.id)

        queue_cli.cmd_recover(Mock(database=queue.db_path, timeout=1,
                                   mark_failed=False, force=False))

        out = capsys.readouterr().out
        assert "0 reset to PENDING, 1 marked FAILED" in out
        assert "list --status failed" in out
        assert "1 skipped" in out and "--force" in out


class TestTaskFailedEvent:
    """#386: ``task_failed`` says whether the task will be retried."""

    def _failed_events(self, queue: QueueManager, max_retries: int) -> List[Tuple[str, dict]]:
        orchestrator = AgentOrchestrator(queue_manager=queue)
        agent = Mock()
        agent.run.side_effect = RuntimeError("boom")
        orchestrator.register_agent(AGENT, agent)
        events: List[Tuple[str, dict]] = []
        orchestrator.add_progress_callback(lambda e, m, d: events.append((m, d)))
        orchestrator._run_task(AGENT, claim(queue, max_retries=max_retries))
        return [(m, d) for m, d in events if "will_retry" in d]

    def test_retryable_failure_says_will_retry(self, queue: QueueManager) -> None:
        """A retried task's event has will_retry=True."""
        [(message, data)] = self._failed_events(queue, max_retries=1)
        assert data["will_retry"] is True
        assert message.endswith("will retry")

    def test_final_failure_says_no_retry(self, queue: QueueManager) -> None:
        """A task out of retries has will_retry=False."""
        [(message, data)] = self._failed_events(queue, max_retries=0)
        assert data["will_retry"] is False
        assert message.endswith("failed")

    def test_no_event_when_the_task_was_taken_away(self, queue: QueueManager) -> None:
        """A failure discarded because the task was recovered sends no task_failed."""
        orchestrator = AgentOrchestrator(queue_manager=queue)
        events: List[str] = []
        orchestrator.add_progress_callback(lambda e, _m, _d: events.append(e))
        task = claim(queue)
        with sqlite3.connect(queue.db_path) as conn:  # taken away while running
            conn.execute("UPDATE queue_tasks SET status = ? WHERE id = ?",
                         (TaskStatus.CANCELLED.value, task.id))

        orchestrator._fail_task(task, AGENT, "late", retry=True)

        assert events == []
