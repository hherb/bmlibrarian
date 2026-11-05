"""
SQLite-based queuing system for agent task management.

Provides a persistent, memory-efficient queue for managing agent tasks
with orchestration and handover capabilities.
"""

import sqlite3
import json
import logging
import uuid
import threading
import os
import signal
import atexit
import sys
import weakref
import psutil  # type: ignore[import-untyped]  # no stubs installed
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional, Dict, Any, List, Iterator
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# The atomic dequeue (get_next_task) relies on the SQL ``RETURNING`` clause,
# which SQLite added in 3.35.0 (2021-03-12). Guard against older engines so a
# stale libsqlite3 fails loudly at construction rather than mid-dequeue. The
# stdlib ``sqlite3`` module links whatever libsqlite3 the interpreter was built
# against, so this cannot be pinned via packaging — hence a runtime check.
MIN_SQLITE_VERSION: tuple = (3, 35, 0)

# Milliseconds a queue connection waits for a competing writer to release the
# database lock before raising ``sqlite3.OperationalError("database is
# locked")``. Multiple worker processes claim tasks concurrently (each with its
# own connection), so without this they would fail immediately on contention
# instead of briefly blocking and retrying.
QUEUE_BUSY_TIMEOUT_MS: int = 30_000

# Busy timeout for the SIGTERM-handler cleanup. The interrupted code may hold
# the write lock itself (e.g. between executemany and commit), so waiting the
# full QUEUE_BUSY_TIMEOUT_MS would stall termination; the atexit pass retries
# once the interrupted frame has unwound and released it.
SIGNAL_CLEANUP_BUSY_TIMEOUT_MS: int = 1_000

# Shell convention for a process killed by a signal: exit status 128 + signum.
SIGNAL_EXIT_STATUS_BASE: int = 128

# Process-wide cleanup: one atexit hook and one SIGTERM handler cover every
# live QueueManager. SIGINT is left alone: Ctrl-C stays a KeyboardInterrupt
# (callers catch it), and if it ends the process the atexit hook cleans up.
# The once-flags below install them a single time however many managers are
# created; the WeakSet lets garbage-collected managers drop out instead of
# being kept alive by the registry.
_live_managers: "weakref.WeakSet[QueueManager]" = weakref.WeakSet()
_registry_lock = threading.Lock()
_atexit_registered = False
_signal_handlers_installed = False


class ResultNotSerializableError(ValueError):
    """A task result cannot be stored because json cannot serialise it."""


def _report_cleanup_error(manager: "QueueManager", error: Exception,
                          note: str = "") -> None:
    """Write a cleanup failure to stderr (logging may be shut down at exit)."""
    print(
        f"QueueManager cleanup failed for {manager.db_path}: "
        f"{type(error).__name__}: {error}{note}",
        file=sys.stderr,
    )


def _cleanup_all_on_exit() -> None:
    """atexit hook: mark this process's in-flight tasks failed in every live queue."""
    for manager in list(_live_managers):
        manager._cleanup_on_exit()


def _handle_termination_signal(signum: int, frame: Any) -> None:
    """SIGTERM handler: fail in-flight tasks, then exit 128 + signum."""
    for manager in list(_live_managers):
        manager._signal_handler(signum, frame)
    sys.exit(SIGNAL_EXIT_STATUS_BASE + signum)


def _register_manager(manager: "QueueManager") -> None:
    """Track a manager and install the process-wide handlers once.

    The SIGTERM handler can only be installed from the main thread (signal.signal()
    raises ValueError otherwise), so a manager built on a worker thread (e.g. a
    Qt background worker) leaves them for the first main-thread construction.
    """
    global _atexit_registered, _signal_handlers_installed
    with _registry_lock:
        _live_managers.add(manager)
        if not _atexit_registered:
            atexit.register(_cleanup_all_on_exit)
            _atexit_registered = True
        if (not _signal_handlers_installed
                and threading.current_thread() is threading.main_thread()):
            signal.signal(signal.SIGTERM, _handle_termination_signal)
            _signal_handlers_installed = True


def _process_alive(pid: int) -> bool:
    """Whether a process with this id exists (owned by any user).

    psutil, not ``os.kill(pid, 0)``: on Windows signal 0 is CTRL_C_EVENT and
    would interrupt the process instead of probing it. (On POSIX psutil does
    use signal 0, treating EPERM as "exists".)
    """
    # shortcut: a reused pid reads as alive, so a dead worker's task then needs
    # ``force`` (issue #388: compare the process start time with started_at).
    return psutil.pid_exists(pid)


@dataclass(frozen=True)
class RecoveryCounts:
    """What ``recover_stuck_tasks`` did with the stuck tasks it found."""
    reset: int = 0             # back to PENDING (one retry spent)
    failed: int = 0            # marked FAILED (dead process, out of retries, or mark_as_failed)
    skipped_running: int = 0   # left PROCESSING: their process is still running

    @property
    def recovered(self) -> int:
        """Tasks reset or failed."""
        return self.reset + self.failed


class TaskStatus(Enum):
    """Task processing status."""
    PENDING = "pending"
    PROCESSING = "processing" 
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(Enum):
    """Task priority levels."""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4


@dataclass
class QueueTask:
    """Represents a task in the processing queue."""
    id: str
    source_agent: Optional[str]  # None for user/database originated tasks
    target_agent: str
    method_name: str
    data: Dict[str, Any]
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.NORMAL
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    process_id: Optional[int] = None  # Track which process is handling this task
    worker_id: Optional[str] = None   # Track which worker thread is handling this
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)


class QueueManager:
    """
    SQLite-based queue manager for agent tasks.
    
    Provides persistent, thread-safe task queuing with support for:
    - Task prioritization
    - Retry logic
    - Progress tracking
    - Agent handovers
    - Batch processing
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize queue manager.
        
        Args:
            db_path: Path to SQLite database file. If None, uses default location.

        Raises:
            RuntimeError: If the linked SQLite engine predates 3.35.0, which is
                required for the ``RETURNING``-based atomic dequeue.
        """
        if sqlite3.sqlite_version_info < MIN_SQLITE_VERSION:
            required = ".".join(str(p) for p in MIN_SQLITE_VERSION)
            raise RuntimeError(
                f"QueueManager requires SQLite >= {required} for atomic task "
                f"claiming (RETURNING clause), but the linked engine is "
                f"{sqlite3.sqlite_version}. Upgrade the SQLite library your "
                f"Python interpreter links against."
            )

        # Default: project directory. Absolute, so a later os.chdir cannot point
        # exit cleanup at another file.
        path = str(Path.cwd() / "agent_queue.db") if db_path is None else str(db_path)
        self.db_path: str = path if path == ":memory:" else os.path.abspath(path)
        self.lock = threading.Lock()
        
        # For in-memory databases, maintain a persistent connection
        self._persistent_conn = None
        if self.db_path == ":memory:":
            self._persistent_conn = sqlite3.connect(self.db_path, check_same_thread=False)
        
        # Track this process for cleanup
        self.process_id = os.getpid()
        
        self._init_database()
        
        _register_manager(self)
    
    def _get_connection(self, busy_timeout_ms: int = QUEUE_BUSY_TIMEOUT_MS):
        """Get database connection, using persistent connection for in-memory databases.

        Fresh file-based connections get ``busy_timeout`` applied so that a
        worker contending with another process's claim blocks briefly and
        retries instead of failing immediately with "database is locked".
        """
        if self._persistent_conn:
            return self._persistent_conn
        conn = sqlite3.connect(self.db_path)
        conn.execute(f"PRAGMA busy_timeout = {int(busy_timeout_ms)}")
        return conn
    
    def _init_database(self):
        """Initialize SQLite database with required tables."""
        conn = self._get_connection()
        needs_close = not self._persistent_conn

        try:
            # Use WAL journaling for file-based databases so concurrent readers
            # don't block the writer claiming a task (and vice versa). WAL is a
            # persistent property of the database file, so setting it once here
            # applies to every later connection. It is a no-op for :memory:.
            if self.db_path != ":memory:":
                conn.execute("PRAGMA journal_mode = WAL")

            # Create the main table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS queue_tasks (
                    id TEXT PRIMARY KEY,
                    source_agent TEXT,
                    target_agent TEXT NOT NULL,
                    method_name TEXT NOT NULL,
                    data TEXT NOT NULL,
                    status TEXT NOT NULL,
                    priority INTEGER NOT NULL,
                    result TEXT,
                    error_message TEXT,
                    retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    process_id INTEGER,
                    worker_id TEXT
                )
            """)
            
            # Add new columns to existing tables (migration)
            try:
                conn.execute("ALTER TABLE queue_tasks ADD COLUMN process_id INTEGER")
            except sqlite3.OperationalError:
                pass  # Column already exists
            
            try:
                conn.execute("ALTER TABLE queue_tasks ADD COLUMN worker_id TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists
            
            # Create indexes for performance
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_status_priority 
                ON queue_tasks(status, priority DESC, created_at ASC)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_target_agent 
                ON queue_tasks(target_agent, status)
            """)
            
            # Explicit commit to ensure tables are created
            conn.commit()
            
        finally:
            if needs_close:
                conn.close()
    
    def queue_file_missing(self) -> bool:
        """True if the queue file is gone; reconnecting would recreate it empty."""
        return self._persistent_conn is None and not os.path.exists(self.db_path)

    def _cleanup_on_exit(self) -> None:
        """Mark this process's in-flight tasks failed on exit; errors go to stderr."""
        if self.queue_file_missing():
            return
        try:
            self._mark_process_tasks_as_failed("Process terminated")
        except Exception as e:
            _report_cleanup_error(self, e)

    def _signal_handler(self, signum: int, frame: Any) -> None:
        """Mark this process's in-flight tasks failed for a termination signal.

        Called by the process-wide handler, which then exits. It runs
        synchronously on the main thread in the context of whatever code was
        interrupted, which may already hold ``self.lock``. Acquiring it here
        would deadlock (threading.Lock is non-reentrant), so mark tasks failed
        without taking the lock. The interrupted code may also hold the SQLite
        write lock, so wait only briefly for it; on failure the atexit pass that
        follows the exit retries. Errors go to stderr; we are exiting anyway.
        """
        if self.queue_file_missing():
            return
        try:
            self._mark_process_tasks_as_failed(
                f"Process terminated by signal {signum}", acquire_lock=False,
                busy_timeout_ms=SIGNAL_CLEANUP_BUSY_TIMEOUT_MS,
            )
        except Exception as e:
            _report_cleanup_error(self, e, "; retrying at exit")

    def _mark_process_tasks_as_failed(self, error_message: str, acquire_lock: bool = True,
                                      busy_timeout_ms: int = QUEUE_BUSY_TIMEOUT_MS) -> None:
        """Mark all processing tasks for this process as failed.

        Args:
            error_message: Reason recorded on each failed task.
            acquire_lock: Whether to take ``self.lock``. Must be False when
                called from the signal handler, which may have interrupted code
                that already holds the lock (non-reentrant → deadlock).
            busy_timeout_ms: How long to wait for a competing SQLite writer.
        """
        if acquire_lock:
            with self.lock:
                self._do_mark_process_tasks_as_failed(error_message, busy_timeout_ms)
        else:
            self._do_mark_process_tasks_as_failed(error_message, busy_timeout_ms)

    def _do_mark_process_tasks_as_failed(self, error_message: str,
                                         busy_timeout_ms: int = QUEUE_BUSY_TIMEOUT_MS) -> None:
        """Perform the failed-task update. Caller manages locking."""
        conn = self._get_connection(busy_timeout_ms)
        needs_close = not self._persistent_conn
        try:
            completed_at = datetime.now(timezone.utc).isoformat()
            conn.execute("""
                UPDATE queue_tasks
                SET status = ?, error_message = ?, completed_at = ?
                WHERE process_id = ? AND status = ?
            """, (TaskStatus.FAILED.value, error_message, completed_at,
                  self.process_id, TaskStatus.PROCESSING.value))
            conn.commit()
        finally:
            if needs_close:
                conn.close()
    
    def recover_stuck_tasks(self, stuck_timeout_minutes: int = 30,
                            mark_as_failed: bool = False,
                            force: bool = False) -> RecoveryCounts:
        """
        Recover tasks that have been stuck in PROCESSING status.

        A task whose process is still running is left alone unless ``force``:
        its worker may just be slow (a long LLM call), and resetting it would
        let a second worker repeat its side effects. When forced, the original
        worker's later result is discarded (see ``complete_task``).

        Args:
            stuck_timeout_minutes: Consider tasks stuck if processing longer than this
            mark_as_failed: If True, mark stuck tasks as failed. If False, the
                task is reset to pending; the reset counts as a retry, so a task
                that has used up ``max_retries`` is marked failed instead. A task
                whose process has died is marked failed in either mode.
            force: Also recover tasks whose process is still running.

        Returns:
            How many tasks were reset, failed, or skipped as still running.
        """
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=stuck_timeout_minutes)
        reset = failed = skipped_running = 0

        with self.lock:
            conn = self._get_connection()
            needs_close = not self._persistent_conn
            try:
                cursor = conn.execute("""
                    SELECT id, process_id, worker_id, started_at, retry_count, max_retries
                    FROM queue_tasks
                    WHERE status = ? AND started_at < ?
                """, (TaskStatus.PROCESSING.value, cutoff_time.isoformat()))

                for (task_id, process_id, worker_id, started_at,
                     retry_count, max_retries) in cursor.fetchall():
                    # A task without a process id has an unknown owner: recoverable.
                    process_alive = bool(process_id) and _process_alive(process_id)
                    process_dead = bool(process_id) and not process_alive
                    if process_alive and not force:
                        skipped_running += 1
                        continue

                    # Write only if the task is still the claim we inspected: a
                    # worker in another process may have finished it (or it was
                    # re-claimed) since the SELECT, which holds no lock.
                    still_claimed = ("status = ? AND worker_id IS ? AND started_at IS ?",
                                     (TaskStatus.PROCESSING.value, worker_id, started_at))
                    # A reset to pending is a retry and spends the retry budget.
                    new_retry_count = retry_count + 1
                    completed_at = datetime.now(timezone.utc).isoformat()
                    if mark_as_failed or process_dead:
                        if process_dead:
                            reason = f"Task stuck in processing; process {process_id} no longer running"
                        elif process_alive:
                            reason = (f"Task forcibly recovered while process "
                                      f"{process_id} was still running")
                        else:
                            reason = "Task stuck in processing (timeout)"
                        update = conn.execute(f"""
                            UPDATE queue_tasks
                            SET status = ?, error_message = ?, completed_at = ?,
                                process_id = NULL, worker_id = NULL
                            WHERE id = ? AND {still_claimed[0]}
                        """, (TaskStatus.FAILED.value, reason, completed_at, task_id,
                              *still_claimed[1]))
                        failed += update.rowcount
                    elif new_retry_count > max_retries:
                        update = conn.execute(f"""
                            UPDATE queue_tasks
                            SET status = ?, retry_count = ?, error_message = ?,
                                completed_at = ?, process_id = NULL, worker_id = NULL
                            WHERE id = ? AND {still_claimed[0]}
                        """, (TaskStatus.FAILED.value, new_retry_count,
                              "Task stuck in processing; retries exhausted",
                              completed_at, task_id, *still_claimed[1]))
                        failed += update.rowcount
                    else:
                        update = conn.execute(f"""
                            UPDATE queue_tasks
                            SET status = ?, retry_count = ?, started_at = NULL,
                                process_id = NULL, worker_id = NULL
                            WHERE id = ? AND {still_claimed[0]}
                        """, (TaskStatus.PENDING.value, new_retry_count, task_id,
                              *still_claimed[1]))
                        reset += update.rowcount

                conn.commit()
                return RecoveryCounts(reset=reset, failed=failed,
                                      skipped_running=skipped_running)

            finally:
                if needs_close:
                    conn.close()

    def cleanup_dead_process_tasks(self) -> int:
        """
        Clean up tasks from processes that are no longer running.
        
        Returns:
            Number of tasks cleaned up
        """
        with self.lock:
            conn = self._get_connection()
            needs_close = not self._persistent_conn
            try:
                # Find all processing tasks with process IDs
                cursor = conn.execute("""
                    SELECT DISTINCT process_id FROM queue_tasks 
                    WHERE status = ? AND process_id IS NOT NULL
                """, (TaskStatus.PROCESSING.value,))
                
                process_ids = [row[0] for row in cursor.fetchall()]
                dead_processes = [pid for pid in process_ids if not _process_alive(pid)]
                
                # Clean up tasks from dead processes
                cleaned_count = 0
                for dead_pid in dead_processes:
                    cursor = conn.execute("""
                        UPDATE queue_tasks 
                        SET status = ?, error_message = ?, completed_at = ?, 
                            process_id = NULL, worker_id = NULL
                        WHERE process_id = ? AND status = ?
                    """, (TaskStatus.FAILED.value, 
                          f"Process {dead_pid} no longer running",
                          datetime.now(timezone.utc).isoformat(),
                          dead_pid, TaskStatus.PROCESSING.value))
                    
                    cleaned_count += cursor.rowcount
                
                conn.commit()
                return cleaned_count
                
            finally:
                if needs_close:
                    conn.close()
    
    def get_queue_health(self) -> Dict[str, Any]:
        """
        Get comprehensive queue health information.
        
        Returns:
            Dictionary with queue health metrics
        """
        conn = self._get_connection()
        needs_close = not self._persistent_conn
        try:
            # Basic stats
            cursor = conn.execute("""
                SELECT status, COUNT(*) FROM queue_tasks GROUP BY status
            """)
            status_counts = dict(cursor.fetchall())
            
            # Stuck tasks (processing > 30 minutes)
            stuck_cutoff = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
            cursor = conn.execute("""
                SELECT COUNT(*) FROM queue_tasks 
                WHERE status = ? AND started_at < ?
            """, (TaskStatus.PROCESSING.value, stuck_cutoff))
            stuck_tasks = cursor.fetchone()[0]
            
            # Orphaned tasks (processing with dead process)
            cursor = conn.execute("""
                SELECT DISTINCT process_id FROM queue_tasks 
                WHERE status = ? AND process_id IS NOT NULL
            """, (TaskStatus.PROCESSING.value,))
            
            orphaned_tasks = 0
            for (pid,) in cursor.fetchall():
                if not _process_alive(pid):
                    cursor2 = conn.execute("""
                        SELECT COUNT(*) FROM queue_tasks 
                        WHERE process_id = ? AND status = ?
                    """, (pid, TaskStatus.PROCESSING.value))
                    orphaned_tasks += cursor2.fetchone()[0]
            
            # Queue age stats
            cursor = conn.execute("""
                SELECT 
                    MIN(created_at) as oldest_task,
                    MAX(created_at) as newest_task,
                    COUNT(*) as total_tasks
                FROM queue_tasks
                WHERE status IN (?, ?)
            """, (TaskStatus.PENDING.value, TaskStatus.PROCESSING.value))
            
            age_stats = cursor.fetchone()
            
            return {
                "status_counts": status_counts,
                "stuck_tasks": stuck_tasks,
                "orphaned_tasks": orphaned_tasks,
                "oldest_pending_task": age_stats[0],
                "newest_task": age_stats[1],
                "active_tasks": age_stats[2],
                "current_process_id": self.process_id,
                "queue_database": self.db_path
            }
            
        finally:
            if needs_close:
                conn.close()
    
    def add_task(self, 
                 target_agent: str,
                 method_name: str,
                 data: Dict[str, Any],
                 source_agent: Optional[str] = None,
                 priority: TaskPriority = TaskPriority.NORMAL,
                 max_retries: int = 3) -> str:
        """
        Add a new task to the queue.
        
        Args:
            target_agent: Agent type that should process this task
            method_name: Method to call on the target agent
            data: Task data/parameters
            source_agent: Agent that created this task (None for external)
            priority: Task priority
            max_retries: Maximum retry attempts
            
        Returns:
            Task ID
        """
        task = QueueTask(
            id=str(uuid.uuid4()),
            source_agent=source_agent,
            target_agent=target_agent,
            method_name=method_name,
            data=data,
            priority=priority,
            max_retries=max_retries
        )
        
        with self.lock:
            conn = self._get_connection()
            needs_close = not self._persistent_conn
            try:
                conn.execute("""
                    INSERT INTO queue_tasks (
                        id, source_agent, target_agent, method_name, data,
                        status, priority, retry_count, max_retries, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    task.id, task.source_agent, task.target_agent, task.method_name,
                    json.dumps(task.data), task.status.value, task.priority.value,
                    task.retry_count, task.max_retries, task.created_at.isoformat()
                ))
                conn.commit()
            finally:
                if needs_close:
                    conn.close()
        
        return task.id
    
    def add_batch_tasks(self,
                       target_agent: str,
                       method_name: str,
                       data_list: List[Dict[str, Any]],
                       source_agent: Optional[str] = None,
                       priority: TaskPriority = TaskPriority.NORMAL,
                       max_retries: int = 3) -> List[str]:
        """
        Add multiple tasks efficiently in a single transaction.
        
        Returns:
            List of task IDs
        """
        task_ids = []
        tasks_data = []
        
        for data in data_list:
            task_id = str(uuid.uuid4())
            task_ids.append(task_id)
            created_at = datetime.now(timezone.utc).isoformat()
            
            tasks_data.append((
                task_id, source_agent, target_agent, method_name,
                json.dumps(data), TaskStatus.PENDING.value, priority.value,
                0, max_retries, created_at
            ))
        
        with self.lock:
            conn = self._get_connection()
            needs_close = not self._persistent_conn
            try:
                conn.executemany("""
                    INSERT INTO queue_tasks (
                        id, source_agent, target_agent, method_name, data,
                        status, priority, retry_count, max_retries, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, tasks_data)
                conn.commit()
            finally:
                if needs_close:
                    conn.close()
        
        return task_ids
    
    def get_next_task(self, target_agent: str) -> Optional[QueueTask]:
        """
        Get the next pending task for a specific agent.
        
        Tasks are prioritized by: priority (high to low), then creation time (oldest first).
        
        Args:
            target_agent: Agent type to get tasks for
            
        Returns:
            Next task or None if no pending tasks
        """
        with self.lock:
            conn = self._get_connection()
            needs_close = not self._persistent_conn
            try:
                started_at = datetime.now(timezone.utc).isoformat()
                worker_id = f"{self.process_id}-{threading.current_thread().ident}"

                # Claim the highest-priority pending task in a single atomic
                # statement. The in-process threading.Lock does not coordinate
                # separate processes (each with its own SQLite connection), so a
                # SELECT-then-UPDATE could let two workers claim the same row.
                # UPDATE ... WHERE id = (SELECT ... LIMIT 1) RETURNING * runs as
                # one write transaction, so at most one worker claims each task.
                cursor = conn.execute("""
                    UPDATE queue_tasks
                    SET status = ?, started_at = ?, process_id = ?, worker_id = ?
                    WHERE id = (
                        SELECT id FROM queue_tasks
                        WHERE target_agent = ? AND status = ?
                        ORDER BY priority DESC, created_at ASC
                        LIMIT 1
                    )
                    RETURNING *
                """, (
                    TaskStatus.PROCESSING.value, started_at, self.process_id, worker_id,
                    target_agent, TaskStatus.PENDING.value
                ))

                row = cursor.fetchone()
                conn.commit()

                if row:
                    # The returned row already reflects the claimed state
                    # (status=PROCESSING, started_at, process_id, worker_id).
                    return self._row_to_task(row)
            finally:
                if needs_close:
                    conn.close()

        return None
    
    @staticmethod
    def _owner_clause(worker_id: Optional[str]) -> tuple:
        """SQL condition (and params) guarding a complete/fail write.

        With ``worker_id``: the task is still PROCESSING and claimed by that
        worker. A worker id is ``{pid}-{thread ident}``, so this relies on each
        thread running one claimed task at a time (the orchestrator's loop).
        Without it: the task is merely not finished yet (pending or processing).
        """
        if worker_id is None:
            return (" AND status IN (?, ?)",
                    (TaskStatus.PENDING.value, TaskStatus.PROCESSING.value))
        return " AND status = ? AND worker_id = ?", (TaskStatus.PROCESSING.value, worker_id)

    @staticmethod
    def _lost_reason(worker_id: Optional[str]) -> str:
        """Why a guarded complete/fail write matched no row, for the warning."""
        if worker_id is None:
            return "task already finished"
        return f"worker {worker_id} no longer holds it (recovered, maybe re-claimed since)"

    @staticmethod
    def _describe_task_state(conn: sqlite3.Connection, task_id: str) -> str:
        """Short "status=…, worker=…" note for a log line, or "task missing"."""
        row = conn.execute("SELECT status, worker_id FROM queue_tasks WHERE id = ?",
                           (task_id,)).fetchone()
        return "task missing" if row is None else f"now status={row[0]}, worker={row[1]}"

    def complete_task(self, task_id: str, result: Dict[str, Any],
                      worker_id: Optional[str] = None) -> bool:
        """Mark a task as completed with result.

        Args:
            task_id: Task to complete.
            result: Result to store (must be JSON-serialisable).
            worker_id: The claiming worker (``QueueTask.worker_id``). When
                given, the result is stored only if that worker still holds the
                task; if it was recovered meanwhile (and possibly re-claimed
                or cancelled since), the result is discarded with a warning.
                Without it, a task that is already completed, failed or
                cancelled is left unchanged.

        Returns:
            True if the result was stored.

        Raises:
            ResultNotSerializableError: ``result`` cannot be stored as JSON
                (nothing is written). Database errors propagate unchanged.
        """
        try:
            payload = json.dumps(result)
        except (TypeError, ValueError) as e:
            raise ResultNotSerializableError(f"{type(e).__name__}: {e}") from e
        owner_sql, owner_params = self._owner_clause(worker_id)
        with self.lock:
            conn = self._get_connection()
            needs_close = not self._persistent_conn
            try:
                completed_at = datetime.now(timezone.utc).isoformat()
                cursor = conn.execute(f"""
                    UPDATE queue_tasks
                    SET status = ?, result = ?, completed_at = ?
                    WHERE id = ?{owner_sql}
                """, (TaskStatus.COMPLETED.value, payload, completed_at, task_id,
                      *owner_params))
                conn.commit()
                state = "" if cursor.rowcount else self._describe_task_state(conn, task_id)
            finally:
                if needs_close:
                    conn.close()
        if state:
            logger.warning(f"Task {task_id} result discarded: {self._lost_reason(worker_id)} "
                           f"({state})")
            return False
        return True

    def fail_task(self, task_id: str, error_message: str, retry: bool = True,
                  worker_id: Optional[str] = None) -> Optional[TaskStatus]:
        """
        Mark a task as failed.

        Args:
            task_id: Task to fail
            error_message: Error description
            retry: Whether to retry if retries remain
            worker_id: The claiming worker (``QueueTask.worker_id``). When
                given, nothing is written unless that worker still holds the
                task (see ``complete_task``). Without it, a finished task is
                left unchanged.

        Returns:
            ``TaskStatus.PENDING`` if the task will be retried,
            ``TaskStatus.FAILED`` if it failed for good, or None if nothing was
            written (task missing, or no longer held by ``worker_id``).
        """
        owner_sql, owner_params = self._owner_clause(worker_id)
        outcome: Optional[TaskStatus] = None
        state = ""
        with self.lock:
            conn = self._get_connection()
            needs_close = not self._persistent_conn
            try:
                cursor = conn.execute("""
                    SELECT retry_count, max_retries FROM queue_tasks WHERE id = ?
                """, (task_id,))
                row = cursor.fetchone()

                if row:
                    retry_count, max_retries = row
                    new_retry_count = retry_count + 1

                    if retry and new_retry_count <= max_retries:
                        cursor = conn.execute(f"""
                            UPDATE queue_tasks
                            SET status = ?, retry_count = ?, error_message = ?, started_at = NULL
                            WHERE id = ?{owner_sql}
                        """, (TaskStatus.PENDING.value, new_retry_count, error_message,
                              task_id, *owner_params))
                        new_status = TaskStatus.PENDING
                    else:
                        completed_at = datetime.now(timezone.utc).isoformat()
                        cursor = conn.execute(f"""
                            UPDATE queue_tasks
                            SET status = ?, retry_count = ?, error_message = ?, completed_at = ?
                            WHERE id = ?{owner_sql}
                        """, (TaskStatus.FAILED.value, new_retry_count, error_message,
                              completed_at, task_id, *owner_params))
                        new_status = TaskStatus.FAILED
                    conn.commit()
                    if cursor.rowcount:
                        outcome = new_status
                    else:
                        state = self._describe_task_state(conn, task_id)
            finally:
                if needs_close:
                    conn.close()

        if not row:
            logger.warning(f"Task {task_id} not found; failure not recorded: {error_message}")
        elif outcome is None:
            logger.warning(f"Task {task_id} failure discarded: {self._lost_reason(worker_id)} "
                           f"({state}): {error_message}")
        return outcome

    def get_task_status(self, task_id: str) -> Optional[QueueTask]:
        """Get current status of a specific task."""
        conn = self._get_connection()
        needs_close = not self._persistent_conn
        try:
            cursor = conn.execute("""
                SELECT * FROM queue_tasks WHERE id = ?
            """, (task_id,))
            row = cursor.fetchone()
            return self._row_to_task(row) if row else None
        finally:
            if needs_close:
                conn.close()
    
    def get_queue_stats(self, target_agent: Optional[str] = None) -> Dict[str, int]:
        """Get queue statistics."""
        conn = self._get_connection()
        needs_close = not self._persistent_conn
        try:
            where_clause = "WHERE target_agent = ?" if target_agent else ""
            params = (target_agent,) if target_agent else ()
            
            cursor = conn.execute(f"""
                SELECT status, COUNT(*) FROM queue_tasks 
                {where_clause}
                GROUP BY status
            """, params)
            
            stats = {status.value: 0 for status in TaskStatus}
            for status, count in cursor.fetchall():
                stats[status] = count
            
            return stats
        finally:
            if needs_close:
                conn.close()
    
    def cleanup_completed_tasks(self, older_than_hours: int = 24):
        """Remove completed/failed tasks older than specified hours."""
        from datetime import timedelta
        
        if older_than_hours == 0:
            # Special case: clean up everything
            cutoff_time = datetime.now(timezone.utc) + timedelta(hours=1)  # Future time
        else:
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=older_than_hours)
        
        with self.lock:
            conn = self._get_connection()
            needs_close = not self._persistent_conn
            try:
                conn.execute("""
                    DELETE FROM queue_tasks 
                    WHERE status IN (?, ?) AND completed_at < ?
                """, (TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, cutoff_time.isoformat()))
                conn.commit()
            finally:
                if needs_close:
                    conn.close()
    
    def cancel_tasks(self, target_agent: Optional[str] = None, source_agent: Optional[str] = None):
        """Cancel pending tasks matching criteria."""
        conditions = ["status = ?"]
        params = [TaskStatus.PENDING.value]
        
        if target_agent:
            conditions.append("target_agent = ?")
            params.append(target_agent)
        
        if source_agent:
            conditions.append("source_agent = ?")
            params.append(source_agent)
        
        with self.lock:
            conn = self._get_connection()
            needs_close = not self._persistent_conn
            try:
                conn.execute(f"""
                    UPDATE queue_tasks 
                    SET status = ?, completed_at = ?
                    WHERE {' AND '.join(conditions)}
                """, [TaskStatus.CANCELLED.value, datetime.now(timezone.utc).isoformat()] + params)
                conn.commit()
            finally:
                if needs_close:
                    conn.close()
    
    def cancel_task(self, task_id: str) -> bool:
        """
        Cancel one task if no agent has started it yet.

        Args:
            task_id: The task to cancel

        Returns:
            True if the task was pending and is now cancelled; False if it
            is unknown or already processing or finished.
        """
        with self.lock:
            conn = self._get_connection()
            needs_close = not self._persistent_conn
            try:
                cursor = conn.execute("""
                    UPDATE queue_tasks
                    SET status = ?, completed_at = ?
                    WHERE id = ? AND status = ?
                """, (TaskStatus.CANCELLED.value, datetime.now(timezone.utc).isoformat(),
                      task_id, TaskStatus.PENDING.value))
                conn.commit()
                return cursor.rowcount == 1
            finally:
                if needs_close:
                    conn.close()

    def _row_to_task(self, row) -> QueueTask:
        """Convert database row to QueueTask object."""
        return QueueTask(
            id=row[0],
            source_agent=row[1],
            target_agent=row[2],
            method_name=row[3],
            data=json.loads(row[4]),
            status=TaskStatus(row[5]),
            priority=TaskPriority(row[6]),
            result=json.loads(row[7]) if row[7] else None,
            error_message=row[8],
            retry_count=row[9],
            max_retries=row[10],
            created_at=datetime.fromisoformat(row[11]),
            started_at=datetime.fromisoformat(row[12]) if row[12] else None,
            completed_at=datetime.fromisoformat(row[13]) if row[13] else None,
            process_id=row[14] if len(row) > 14 and row[14] else None,
            worker_id=row[15] if len(row) > 15 and row[15] else None,
        )
    
    def get_pending_tasks_iter(self, target_agent: str, batch_size: int = 10) -> Iterator[List[QueueTask]]:
        """
        Iterate over pending tasks in batches.
        
        Args:
            target_agent: Agent to get tasks for
            batch_size: Number of tasks per batch
            
        Yields:
            Batches of tasks
        """
        while True:
            batch = []
            for _ in range(batch_size):
                task = self.get_next_task(target_agent)
                if task:
                    batch.append(task)
                else:
                    break
            
            if not batch:
                break
                
            yield batch