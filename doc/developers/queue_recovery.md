# Queue Recovery and Process Management

This document describes the BMLibrarian queue system's recovery mechanisms for handling process termination, stuck tasks, and system failures.

## Overview

The SQLite-based queue system includes comprehensive recovery features to ensure robust operation in production environments. These mechanisms handle various failure scenarios including:

- Graceful process termination
- Unexpected crashes
- Stuck or orphaned tasks
- Dead process cleanup
- Queue preservation strategies

## Architecture

### Process Tracking

Each queue task tracks:
- `process_id`: The operating system process ID handling the task
- `worker_id`: The specific worker thread identifier (`{process_id}-{thread_id}`)
- `started_at`: Timestamp when processing began

### Recovery Components

1. **QueueManager**: Core recovery methods and signal handling
2. **CLI Tool**: Management interface for recovery operations
3. **Process Monitoring**: Automatic detection of stuck/orphaned tasks
4. **Graceful Shutdown**: Signal handlers for clean termination

## Recovery Methods

### 1. Graceful Shutdown

Automatically triggered when process receives SIGTERM or SIGINT:

```python
# Signal handlers automatically registered in QueueManager.__init__()
signal.signal(signal.SIGTERM, self._signal_handler)
signal.signal(signal.SIGINT, self._signal_handler)

# Also registered as atexit handler
atexit.register(self._cleanup_on_exit)
```

**Behavior**: All tasks with status `PROCESSING` and matching `process_id` are marked as `FAILED` with error message "Process terminated".

### 2. Stuck Task Recovery

Detects and recovers tasks processing longer than specified timeout:

```python
recovered = queue.recover_stuck_tasks(
    stuck_timeout_minutes=30,    # Consider stuck after 30 minutes
    mark_as_failed=False        # Reset to PENDING for retry
)
```

**Options**:
- `mark_as_failed=False`: Reset stuck tasks to PENDING status for retry
- `mark_as_failed=True`: Permanently mark stuck tasks as FAILED

### 3. Dead Process Cleanup

Identifies and cleans up tasks from processes that no longer exist:

```python
cleaned = queue.cleanup_dead_process_tasks()
```

**Process**: 
1. Finds all `PROCESSING` tasks with `process_id` values
2. Checks if each process is still running using `os.kill(pid, 0)`
3. Marks tasks from dead processes as `FAILED`

### 4. Queue Health Monitoring

Comprehensive health check including problem detection:

```python
health = queue.get_queue_health()
# Returns:
# {
#     "status_counts": {"pending": 10, "processing": 2, "completed": 50},
#     "stuck_tasks": 1,           # Tasks processing > 30 minutes  
#     "orphaned_tasks": 0,        # Tasks from dead processes
#     "oldest_pending_task": "2023-12-01T10:00:00",
#     "newest_task": "2023-12-01T15:30:00",
#     "active_tasks": 12,
#     "current_process_id": 12345,
#     "queue_database": "agent_queue.db"
# }
```

## CLI Management

The `queue_cli.py` tool provides command-line access to all recovery functions:

### Status and Monitoring
```bash
# Show comprehensive queue health
python -m bmlibrarian.queue_cli status -d queue.db

# List tasks with filtering
python -m bmlibrarian.queue_cli list --status pending -d queue.db
python -m bmlibrarian.queue_cli list --agent scoring_agent -d queue.db
```

### Recovery Operations
```bash
# Recover stuck tasks (reset to pending)
python -m bmlibrarian.queue_cli recover --timeout 15 -d queue.db

# Recover stuck tasks (mark as failed)
python -m bmlibrarian.queue_cli recover --timeout 15 --mark-failed -d queue.db

# Clean up orphaned tasks from dead processes  
python -m bmlibrarian.queue_cli cleanup-dead -d queue.db

# Remove old completed/failed tasks
python -m bmlibrarian.queue_cli cleanup-old --hours 24 -d queue.db
```

### Task Management
```bash
# Cancel pending tasks
python -m bmlibrarian.queue_cli cancel -d queue.db
python -m bmlibrarian.queue_cli cancel --agent specific_agent -d queue.db

# Export queue data for analysis
python -m bmlibrarian.queue_cli export backup.json -d queue.db
```

## Recovery Strategies

### Strategy 1: Preserve Queue (Planned Restarts)
Best for planned maintenance or intentional process restarts:

```python
# Reset stuck tasks to pending for retry
queue.recover_stuck_tasks(stuck_timeout_minutes=30, mark_as_failed=False)
queue.cleanup_dead_process_tasks()  # Clean orphaned tasks
```

**Use cases**: System updates, planned restarts, configuration changes

### Strategy 2: Mark as Failed (Crash Recovery)
Best for handling unrecoverable crashes or data corruption:

```python
# Mark stuck tasks as permanently failed
queue.recover_stuck_tasks(stuck_timeout_minutes=10, mark_as_failed=True)
queue.cleanup_dead_process_tasks()
```

**Use cases**: System crashes, out-of-memory errors, corrupted data

### Strategy 3: Clean Slate (Fresh Start)
Complete queue reset for testing or major changes:

```python
# Cancel all pending tasks
queue.cancel_tasks()
# Remove all completed/failed tasks
queue.cleanup_completed_tasks(older_than_hours=0)
```

**Use cases**: Testing, major system changes, debugging

## Implementation Details

### Database Schema Extensions

The recovery system extends the base queue schema with process tracking:

```sql
ALTER TABLE queue_tasks ADD COLUMN process_id INTEGER;
ALTER TABLE queue_tasks ADD COLUMN worker_id TEXT;

CREATE INDEX IF NOT EXISTS idx_process_status 
ON queue_tasks(process_id, status);
```

### Error Handling

All recovery methods include comprehensive error handling:

```python
try:
    recovered = queue.recover_stuck_tasks()
    logger.info(f"Recovered {recovered} stuck tasks")
except Exception as e:
    logger.error(f"Recovery failed: {e}")
    # Continue with fallback strategy
```

### Thread Safety

All recovery operations are thread-safe using the queue manager's lock:

```python
with self.lock:
    # All database operations are protected
    conn = self._get_connection()
    # ... recovery logic
```

## Best Practices

### 1. Regular Health Monitoring
```python
# Check queue health periodically
health = queue.get_queue_health()
if health['stuck_tasks'] > 0:
    logger.warning(f"Found {health['stuck_tasks']} stuck tasks")
    queue.recover_stuck_tasks()
```

### 2. Automated Recovery in Production
```python
# Set up periodic recovery in production systems
import schedule
import time

def automated_recovery():
    queue.cleanup_dead_process_tasks()
    queue.recover_stuck_tasks(stuck_timeout_minutes=60)
    queue.cleanup_completed_tasks(older_than_hours=48)

# Run recovery every hour
schedule.every().hour.do(automated_recovery)

while True:
    schedule.run_pending()
    time.sleep(60)
```

### 3. Graceful Application Shutdown
```python
import signal
import sys

def signal_handler(signum, frame):
    logger.info("Shutting down gracefully...")
    orchestrator.stop_processing()
    # QueueManager cleanup happens automatically
    sys.exit(0)

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)
```

### 4. Recovery Logging
```python
# Enable detailed logging for recovery operations
logging.getLogger('bmlibrarian.agents.queue_manager').setLevel(logging.DEBUG)
```

## Testing Recovery

The `examples/queue_recovery_demo.py` script demonstrates all recovery scenarios:

```bash
python examples/queue_recovery_demo.py
```

This demo shows:
- Graceful shutdown behavior
- Stuck task detection and recovery
- Crash simulation and cleanup
- CLI tool usage examples
- Different preservation strategies

## Performance Considerations

### Recovery Operation Costs
- **Stuck task recovery**: O(n) where n = number of processing tasks
- **Dead process cleanup**: O(p) where p = number of unique process IDs
- **Health monitoring**: O(1) with indexed queries

### Optimization Tips
1. Run recovery operations during low-traffic periods
2. Use appropriate timeouts (longer for complex tasks)
3. Monitor recovery operation duration
4. Consider batching cleanup operations

## Troubleshooting

### Common Issues

**Issue**: Recovery operations fail with "database locked"
**Solution**: Ensure no other processes are accessing the database, or increase SQLite timeout

**Issue**: Process cleanup doesn't find dead processes
**Solution**: Check that process IDs are being properly recorded during task processing

**Issue**: Stuck task detection too aggressive
**Solution**: Increase `stuck_timeout_minutes` for long-running tasks

### Debugging Recovery

```python
# Enable debug logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Check queue health
health = queue.get_queue_health()
print(f"Queue health: {health}")

# Examine specific task status
task = queue.get_task_status(task_id)
print(f"Task {task_id}: {task.status}, process_id: {task.process_id}")
```

## Security Considerations

1. **Process ID Validation**: System validates process existence before cleanup
2. **Permission Checks**: Only processes with appropriate permissions can signal other processes
3. **Database Access**: Queue database should be readable/writable only by application user
4. **Signal Handling**: Signal handlers perform minimal operations to avoid security issues

## Future Enhancements

Potential improvements for the recovery system:

1. **Distributed Recovery**: Support for multi-machine queue recovery
2. **Recovery Metrics**: Detailed metrics and alerting for recovery operations  
3. **Custom Recovery Strategies**: Pluggable recovery behavior for different task types
4. **Backup/Restore**: Queue state backup and restore capabilities
5. **Recovery Scheduling**: Built-in scheduling for automated recovery operations