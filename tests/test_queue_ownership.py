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
import os
import signal
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Tuple
from unittest.mock import Mock

import psutil  # type: ignore[import-untyped]
import pytest

import bmlibrarian.agents.queue_manager as qm
from bmlibrarian.agents import AgentOrchestrator, QueueManager, TaskStatus

AGENT = "worker"
SUBPROCESS_TIMEOUT_SECONDS = 120
DEAD_PID = 2 ** 22 + 12345  # above the default Linux/macOS pid ranges

# Recover every processing task: a stuck task "started" when this test process
# did, so the process still counts as its live claiming worker (#388), and
# backdating further would make it read as a reused pid.
STUCK_TIMEOUT_MINUTES = 0


def stuck_since() -> str:
    """ISO time this process started, as a stuck task's started_at."""
    return datetime.fromtimestamp(psutil.Process().create_time(), timezone.utc).isoformat()


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
                     (stuck_since(), task_id))
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
            # A shell background job starts with SIGINT ignored; restore Python's
            # default so the test does not depend on how pytest was launched.
            "signal.signal(signal.SIGINT, signal.default_int_handler)\n"
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
            # A shell background job starts with SIGINT ignored; restore Python's
            # default so the test does not depend on how pytest was launched.
            "signal.signal(signal.SIGINT, signal.default_int_handler)\n"
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
        assert queue.recover_stuck_tasks(stuck_timeout_minutes=STUCK_TIMEOUT_MINUTES, force=True).reset == 1

        with caplog.at_level(logging.WARNING, logger=qm.__name__):
            assert queue.complete_task(task.id, {"late": True}, worker_id=task.worker_id) is False

        stored = queue.get_task_status(task.id)
        assert (stored.status, stored.result) == (TaskStatus.PENDING, None)
        assert "result discarded" in caplog.text
        assert "now status=pending" in caplog.text

    def test_old_worker_cannot_overwrite_a_re_claimed_task(self, queue: QueueManager) -> None:
        """A second claim (another worker id) keeps PROCESSING after the first fails."""
        task = claim(queue)
        make_stuck(queue, task.id)
        queue.recover_stuck_tasks(stuck_timeout_minutes=STUCK_TIMEOUT_MINUTES, force=True)
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
        assert queue.recover_stuck_tasks(stuck_timeout_minutes=STUCK_TIMEOUT_MINUTES, force=True).failed == 1

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

    def test_without_worker_id_finished_tasks_are_left_alone(self, queue: QueueManager) -> None:
        """Legacy callers (no worker_id) cannot revive a cancelled or completed task."""
        cancelled = queue.add_task(target_agent=AGENT, method_name="run", data={})
        queue.cancel_task(cancelled)
        assert queue.complete_task(cancelled, {"x": 1}) is False
        assert queue.get_task_status(cancelled).status == TaskStatus.CANCELLED

        done = claim(queue)
        queue.complete_task(done.id, {"x": 1})
        assert queue.fail_task(done.id, "late", retry=True) is None
        assert queue.get_task_status(done.id).status == TaskStatus.COMPLETED

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

        assert queue.recover_stuck_tasks(stuck_timeout_minutes=STUCK_TIMEOUT_MINUTES) == qm.RecoveryCounts(
            skipped_running=1)
        assert queue.get_task_status(task.id).status == TaskStatus.PROCESSING

    def test_counts_reset_failed_and_skipped_separately(self, queue: QueueManager) -> None:
        """Dead process → failed, unknown owner → reset, live process → skipped."""
        dead, unowned, live = claim(queue), claim(queue), claim(queue)
        make_stuck(queue, dead.id, process_id=DEAD_PID)
        make_stuck(queue, unowned.id, process_id=0)  # falsy: no recorded owner
        make_stuck(queue, live.id)

        counts = queue.recover_stuck_tasks(stuck_timeout_minutes=STUCK_TIMEOUT_MINUTES)

        assert counts == qm.RecoveryCounts(reset=1, failed=1, skipped_running=1)
        assert counts.recovered == 2
        assert queue.get_task_status(dead.id).status == TaskStatus.FAILED
        assert queue.get_task_status(unowned.id).status == TaskStatus.PENDING

    def test_process_alive(self) -> None:
        """This process is alive; an impossible pid is not."""
        assert qm._process_alive(os.getpid()) is True
        assert qm._process_alive(DEAD_PID) is False

    def test_task_finished_during_recovery_is_not_overwritten(
            self, queue: QueueManager, monkeypatch: pytest.MonkeyPatch) -> None:
        """A worker finishing between recovery's SELECT and UPDATE keeps its result."""
        task = claim(queue)
        make_stuck(queue, task.id)

        def finish_then_report_alive(pid: int, started_at: Any = None) -> bool:
            """Another process completes the task while recovery inspects it."""
            other = QueueManager(queue.db_path)
            assert other.complete_task(task.id, {"done": 1}, worker_id=task.worker_id)
            return True

        monkeypatch.setattr(qm, "_process_alive", finish_then_report_alive)
        counts = queue.recover_stuck_tasks(stuck_timeout_minutes=STUCK_TIMEOUT_MINUTES, force=True)

        assert counts == qm.RecoveryCounts()
        stored = queue.get_task_status(task.id)
        assert (stored.status, stored.result) == (TaskStatus.COMPLETED, {"done": 1})

    def test_mark_failed_skips_live_process_unless_forced(self, queue: QueueManager) -> None:
        """--mark-failed no longer fails a live worker's task without --force."""
        task = claim(queue)
        make_stuck(queue, task.id)

        assert queue.recover_stuck_tasks(stuck_timeout_minutes=STUCK_TIMEOUT_MINUTES, mark_as_failed=True) == \
            qm.RecoveryCounts(skipped_running=1)
        assert queue.recover_stuck_tasks(stuck_timeout_minutes=STUCK_TIMEOUT_MINUTES, mark_as_failed=True,
                                         force=True) == qm.RecoveryCounts(failed=1)
        assert "forcibly recovered" in queue.get_task_status(task.id).error_message

    def test_cleanup_dead_fails_only_dead_process_tasks(self, queue: QueueManager) -> None:
        """cleanup-dead fails a dead process's task and leaves a live one running."""
        dead, live = claim(queue), claim(queue)
        make_stuck(queue, dead.id, process_id=DEAD_PID)

        assert queue.get_queue_health()["orphaned_tasks"] == 1
        assert queue.cleanup_dead_process_tasks() == 1
        assert queue.get_task_status(dead.id).status == TaskStatus.FAILED
        assert queue.get_task_status(live.id).status == TaskStatus.PROCESSING

    def test_cli_prints_each_count(self, queue: QueueManager,
                                   capsys: pytest.CaptureFixture) -> None:
        """queue-cli recover says how many were reset, failed and skipped."""
        from bmlibrarian import queue_cli

        dead, live = claim(queue), claim(queue)
        make_stuck(queue, dead.id, process_id=DEAD_PID)
        make_stuck(queue, live.id)

        queue_cli.cmd_recover(Mock(database=queue.db_path, timeout=STUCK_TIMEOUT_MINUTES,
                                   mark_failed=False, force=False))

        out = capsys.readouterr().out
        assert "0 reset to PENDING, 1 marked FAILED" in out
        assert "list --status failed" in out
        assert "1 skipped" in out and "--force" in out

    def test_cli_force_flag_recovers_live_tasks(
            self, queue: QueueManager, capsys: pytest.CaptureFixture,
            monkeypatch: pytest.MonkeyPatch) -> None:
        """`recover --force` is parsed and resets a live process's stuck task."""
        from bmlibrarian import queue_cli

        task = claim(queue)
        make_stuck(queue, task.id)
        monkeypatch.setattr(sys, "argv", ["queue_cli", "--database", queue.db_path,
                                          "recover", "--timeout", str(STUCK_TIMEOUT_MINUTES), "--force"])
        queue_cli.main()

        assert "1 reset to PENDING" in capsys.readouterr().out
        assert queue.get_task_status(task.id).status == TaskStatus.PENDING

    def test_cli_reports_nothing_stuck(self, queue: QueueManager,
                                       capsys: pytest.CaptureFixture) -> None:
        """An empty queue says so instead of printing nothing."""
        from bmlibrarian import queue_cli

        queue_cli.cmd_recover(Mock(database=queue.db_path, timeout=STUCK_TIMEOUT_MINUTES,
                                   mark_failed=False, force=False))
        assert "No stuck tasks found" in capsys.readouterr().out


def claimed_before_this_process() -> str:
    """A claim time this process cannot have made: an hour before it started."""
    return datetime.fromtimestamp(psutil.Process().create_time() - 3600, timezone.utc).isoformat()


class TestReusedPid:
    """#388: a process created after the claim is not the claiming worker."""

    def test_process_alive_compares_start_and_claim_time(self) -> None:
        """Alive only if the process existed at the claim; unknown claim times check the pid only."""
        pid = os.getpid()
        assert qm._process_alive(pid, stuck_since()) is True
        assert qm._process_alive(pid, datetime.now(timezone.utc).isoformat()) is True
        assert qm._process_alive(pid, claimed_before_this_process()) is False
        assert qm._process_alive(pid, "2000-01-01T00:00:00") is True  # naive: zone unknown
        assert qm._process_alive(pid, "not a time") is True
        assert qm._process_alive(DEAD_PID, stuck_since()) is False

    def test_unreadable_start_time_checks_the_pid_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Access denied → alive (as before); exited meanwhile → dead."""
        def process(error: type) -> Any:
            """A psutil.Process stand-in whose create_time raises ``error``."""
            def create_time() -> float:
                """Fail like psutil."""
                raise error(os.getpid())
            return lambda pid: Mock(create_time=create_time)

        claimed = claimed_before_this_process()  # before psutil.Process is replaced
        monkeypatch.setattr(qm.psutil, "Process", process(psutil.AccessDenied))
        assert qm._process_alive(os.getpid(), claimed) is True
        monkeypatch.setattr(qm.psutil, "Process", process(psutil.NoSuchProcess))
        assert qm._process_alive(os.getpid(), claimed) is False

    def test_recover_fails_a_task_whose_pid_was_reused(self, queue: QueueManager) -> None:
        """Not skipped as running: the task is failed like any dead worker's."""
        task = claim(queue)
        with sqlite3.connect(queue.db_path) as conn:
            conn.execute("UPDATE queue_tasks SET started_at = ? WHERE id = ?",
                         (claimed_before_this_process(), task.id))

        assert queue.recover_stuck_tasks(stuck_timeout_minutes=STUCK_TIMEOUT_MINUTES) == \
            qm.RecoveryCounts(failed=1)
        assert "no longer running" in queue.get_task_status(task.id).error_message

    def test_cleanup_dead_checks_each_task_of_a_pid(self, queue: QueueManager) -> None:
        """Same pid: the task claimed before the process started is failed, the other kept."""
        reused, live = claim(queue), claim(queue)
        with sqlite3.connect(queue.db_path) as conn:
            conn.execute("UPDATE queue_tasks SET started_at = ? WHERE id = ?",
                         (claimed_before_this_process(), reused.id))

        assert queue.get_queue_health()["orphaned_tasks"] == 1
        assert queue.cleanup_dead_process_tasks() == 1
        assert queue.get_task_status(reused.id).status == TaskStatus.FAILED
        assert queue.get_task_status(live.id).status == TaskStatus.PROCESSING


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

    def test_discarded_failure_reports_task_discarded(self, queue: QueueManager) -> None:
        """A failure discarded because the task was taken away sends task_discarded."""
        orchestrator = AgentOrchestrator(queue_manager=queue)
        events: List[str] = []
        orchestrator.add_progress_callback(lambda e, _m, _d: events.append(e))
        task = claim(queue)
        with sqlite3.connect(queue.db_path) as conn:  # taken away while running
            conn.execute("UPDATE queue_tasks SET status = ? WHERE id = ?",
                         (TaskStatus.CANCELLED.value, task.id))

        orchestrator._fail_task(task, AGENT, "late", retry=True)

        assert events == ["task_discarded"]

    def test_discarded_result_sends_no_task_completed(self, queue: QueueManager) -> None:
        """A result rejected by the queue is reported as discarded, not completed."""
        orchestrator = AgentOrchestrator(queue_manager=queue)
        task = claim(queue)

        def taken_away_while_running() -> dict:
            """Recovery resets the task while the agent is still working."""
            make_stuck(queue, task.id)
            queue.recover_stuck_tasks(stuck_timeout_minutes=STUCK_TIMEOUT_MINUTES, force=True)
            return {"late": True}

        agent = Mock()
        agent.run.side_effect = taken_away_while_running
        orchestrator.register_agent(AGENT, agent)
        events: List[str] = []
        orchestrator.add_progress_callback(lambda e, _m, _d: events.append(e))

        orchestrator._run_task(AGENT, task)

        assert events == ["task_started", "task_discarded"]
        assert queue.get_task_status(task.id).status == TaskStatus.PENDING
