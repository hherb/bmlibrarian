"""
SQLite-based queuing system for agent task management.

Provides a persistent, memory-efficient queue for managing agent tasks
with orchestration and handover capabilities.
"""

import sqlite3
import json
import uuid
import threading
import os
import signal
import atexit
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional, Dict, Any, List, Iterator, Callable
from dataclasses import dataclass, asdict
from pathlib import Path


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
        """
        if db_path is None:
            # Use project directory for queue database
            db_path = Path.cwd() / "agent_queue.db"
        
        self.db_path = str(db_path)
        self.lock = threading.Lock()
        
        # For in-memory databases, maintain a persistent connection
        self._persistent_conn = None
        if self.db_path == ":memory:":
            self._persistent_conn = sqlite3.connect(self.db_path, check_same_thread=False)
        
        # Track this process for cleanup
        self.process_id = os.getpid()
        
        self._init_database()
        
        # Register cleanup handlers
        atexit.register(self._cleanup_on_exit)
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
    
    def _get_connection(self):
        """Get database connection, using persistent connection for in-memory databases."""
        if self._persistent_conn:
            return self._persistent_conn
        return sqlite3.connect(self.db_path)
    
    def _init_database(self):
        """Initialize SQLite database with required tables."""
        conn = self._get_connection()
        needs_close = not self._persistent_conn
        
        try:
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
    
    def _cleanup_on_exit(self):
        """Clean up tasks assigned to this process on exit."""
        try:
            self._mark_process_tasks_as_failed("Process terminated")
        except Exception:
            pass  # Ignore errors during cleanup
    
    def _signal_handler(self, signum, frame):
        """Handle termination signals gracefully."""
        self._mark_process_tasks_as_failed(f"Process terminated by signal {signum}")
        exit(0)
    
    def _mark_process_tasks_as_failed(self, error_message: str):
        """Mark all processing tasks for this process as failed."""
        with self.lock:
            conn = self._get_connection()
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
                           mark_as_failed: bool = False) -> int:
        """
        Recover tasks that have been stuck in PROCESSING status.
        
        Args:
            stuck_timeout_minutes: Consider tasks stuck if processing longer than this
            mark_as_failed: If True, mark stuck tasks as failed. If False, reset to pending.
            
        Returns:
            Number of tasks recovered
        """
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=stuck_timeout_minutes)
        
        with self.lock:
            conn = self._get_connection()
            needs_close = not self._persistent_conn
            try:
                # Find stuck tasks
                cursor = conn.execute("""
                    SELECT id, process_id FROM queue_tasks 
                    WHERE status = ? AND started_at < ?
                """, (TaskStatus.PROCESSING.value, cutoff_time.isoformat()))
                
                stuck_tasks = cursor.fetchall()
                recovered_count = 0
                
                for task_id, process_id in stuck_tasks:
                    # Check if the process is still running (if we have a process_id)
                    process_dead = False
                    if process_id:
                        try:
                            os.kill(process_id, 0)  # Signal 0 checks if process exists
                        except (OSError, ProcessLookupError):
                            process_dead = True
                    
                    # Recover the task
                    if mark_as_failed or process_dead:
                        # Mark as failed
                        completed_at = datetime.now(timezone.utc).isoformat()
                        conn.execute("""
                            UPDATE queue_tasks 
                            SET status = ?, error_message = ?, completed_at = ?, 
                                process_id = NULL, worker_id = NULL
                            WHERE id = ?
                        """, (TaskStatus.FAILED.value, 
                              "Task stuck in processing (process terminated or timeout)", 
                              completed_at, task_id))
                    else:
                        # Reset to pending for retry
                        conn.execute("""
                            UPDATE queue_tasks 
                            SET status = ?, started_at = NULL, process_id = NULL, worker_id = NULL
                            WHERE id = ?
                        """, (TaskStatus.PENDING.value, task_id))
                    
                    recovered_count += 1
                
                conn.commit()
                return recovered_count
                
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
                dead_processes = []
                
                for pid in process_ids:
                    try:
                        os.kill(pid, 0)  # Check if process exists
                    except (OSError, ProcessLookupError):
                        dead_processes.append(pid)
                
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
                try:
                    os.kill(pid, 0)
                except (OSError, ProcessLookupError):
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
                cursor = conn.execute("""
                    SELECT * FROM queue_tasks 
                    WHERE target_agent = ? AND status = ?
                    ORDER BY priority DESC, created_at ASC
                    LIMIT 1
                """, (target_agent, TaskStatus.PENDING.value))
                
                row = cursor.fetchone()
                if row:
                    # Mark as processing with process and worker tracking
                    started_at = datetime.now(timezone.utc).isoformat()
                    worker_id = f"{self.process_id}-{threading.current_thread().ident}"
                    
                    conn.execute("""
                        UPDATE queue_tasks 
                        SET status = ?, started_at = ?, process_id = ?, worker_id = ?
                        WHERE id = ?
                    """, (TaskStatus.PROCESSING.value, started_at, self.process_id, worker_id, row[0]))
                    
                    conn.commit()
                    
                    # Create task object with updated status
                    task = self._row_to_task(row)
                    task.status = TaskStatus.PROCESSING
                    task.started_at = datetime.fromisoformat(started_at)
                    task.process_id = self.process_id
                    task.worker_id = worker_id
                    return task
            finally:
                if needs_close:
                    conn.close()
        
        return None
    
    def complete_task(self, task_id: str, result: Dict[str, Any]):
        """Mark a task as completed with result."""
        with self.lock:
            conn = self._get_connection()
            needs_close = not self._persistent_conn
            try:
                completed_at = datetime.now(timezone.utc).isoformat()
                conn.execute("""
                    UPDATE queue_tasks 
                    SET status = ?, result = ?, completed_at = ?
                    WHERE id = ?
                """, (TaskStatus.COMPLETED.value, json.dumps(result), completed_at, task_id))
                conn.commit()
            finally:
                if needs_close:
                    conn.close()
    
    def fail_task(self, task_id: str, error_message: str, retry: bool = True):
        """
        Mark a task as failed.
        
        Args:
            task_id: Task to fail
            error_message: Error description
            retry: Whether to retry if retries remain
        """
        with self.lock:
            conn = self._get_connection()
            needs_close = not self._persistent_conn
            try:
                # Get current task state
                cursor = conn.execute("""
                    SELECT retry_count, max_retries FROM queue_tasks WHERE id = ?
                """, (task_id,))
                row = cursor.fetchone()
                
                if not row:
                    return
                
                retry_count, max_retries = row
                new_retry_count = retry_count + 1
                
                if retry and new_retry_count <= max_retries:
                    # Reset to pending for retry
                    conn.execute("""
                        UPDATE queue_tasks 
                        SET status = ?, retry_count = ?, error_message = ?, started_at = NULL
                        WHERE id = ?
                    """, (TaskStatus.PENDING.value, new_retry_count, error_message, task_id))
                else:
                    # Mark as permanently failed
                    completed_at = datetime.now(timezone.utc).isoformat()
                    conn.execute("""
                        UPDATE queue_tasks 
                        SET status = ?, retry_count = ?, error_message = ?, completed_at = ?
                        WHERE id = ?
                    """, (TaskStatus.FAILED.value, new_retry_count, error_message, completed_at, task_id))
                
                conn.commit()
            finally:
                if needs_close:
                    conn.close()
    
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