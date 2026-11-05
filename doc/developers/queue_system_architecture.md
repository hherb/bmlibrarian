# Queue System Architecture - Developer Documentation

## Overview

The BMLibrarian queue system provides a scalable, memory-efficient solution for processing large volumes of documents through AI agents. Built on SQLite for persistence and designed for multi-threaded operation, it enables processing thousands of documents while maintaining low memory usage and providing robust error handling.

## Architecture Principles

### 1. Persistence Over Memory
- **SQLite backend**: All tasks stored on disk, not in RAM
- **Crash recovery**: System survives application restarts
- **No memory limits**: Can queue unlimited tasks (disk permitting)

### 2. Thread Safety
- **Concurrent access**: Multiple agents can safely access the queue
- **Atomic operations**: Task state changes are transactional
- **Lock management**: Proper locking prevents race conditions

### 3. Scalable Processing
- **Background workers**: Agents process tasks in separate threads
- **Batch operations**: Efficient handling of multiple tasks
- **Priority queuing**: Important tasks processed first

### 4. Fault Tolerance
- **Automatic retries**: Tasks whose agent method raises are re-queued (no delay) up to `max_retries`
- **Error isolation**: One failed task doesn't affect others
- **Progress tracking**: Detailed status monitoring and recovery

## Core Components

### QueueManager (`queue_manager.py`)

The foundation component providing SQLite-based task persistence.

#### Database Schema
```sql
CREATE TABLE queue_tasks (
    id TEXT PRIMARY KEY,                -- UUID task identifier
    source_agent TEXT,                  -- Agent that created task (NULL for external)
    target_agent TEXT NOT NULL,        -- Agent that should process task  
    method_name TEXT NOT NULL,          -- Method to call on target agent
    data TEXT NOT NULL,                 -- JSON-encoded task parameters
    status TEXT NOT NULL,               -- TaskStatus enum value
    priority INTEGER NOT NULL,          -- TaskPriority enum value
    result TEXT,                        -- JSON-encoded result (when completed)
    error_message TEXT,                 -- Error description (when failed)
    retry_count INTEGER DEFAULT 0,     -- Current retry attempt
    max_retries INTEGER DEFAULT 3,     -- Maximum retry attempts
    created_at TEXT NOT NULL,           -- Task creation timestamp
    started_at TEXT,                    -- Processing start timestamp  
    completed_at TEXT                   -- Completion timestamp
);

-- Indexes for efficient querying
CREATE INDEX idx_status_priority ON queue_tasks(status, priority DESC, created_at ASC);
CREATE INDEX idx_target_agent ON queue_tasks(target_agent, status);
```

#### Key Methods

**Task Lifecycle Management**:
```python
def add_task(target_agent: str, method_name: str, data: Dict) -> str
def add_batch_tasks(target_agent: str, method_name: str, data_list: List[Dict]) -> List[str]
def get_next_task(target_agent: str) -> Optional[QueueTask]
def complete_task(task_id: str, result: Dict, worker_id: Optional[str] = None) -> bool
def fail_task(task_id: str, error_message: str, retry: bool = True,
              worker_id: Optional[str] = None) -> Optional[TaskStatus]
```

**Monitoring and Management**:
```python
def get_task_status(task_id: str) -> Optional[QueueTask]
def get_queue_stats(target_agent: Optional[str] = None) -> Dict[str, int]
def cleanup_completed_tasks(older_than_hours: int = 24)
def cancel_tasks(target_agent: Optional[str] = None)
```

#### Thread Safety Implementation
`self.lock` serialises access within a process; across processes, a task is
claimed with a single atomic statement (SQLite >= 3.35 for `RETURNING`), on a
connection from `_get_connection()` with `busy_timeout` applied:

```sql
UPDATE queue_tasks
SET status = 'processing', started_at = :now_utc, process_id = :pid, worker_id = :worker
WHERE id = (SELECT id FROM queue_tasks
            WHERE target_agent = :agent AND status = 'pending'
            ORDER BY priority DESC, created_at ASC LIMIT 1)
RETURNING *
```

### AgentOrchestrator (`orchestrator.py`)

Coordinates multiple agents and manages complex workflows.

#### Core Responsibilities

1. **Agent Registration and Management**
2. **Background Task Processing** 
3. **Workflow Coordination**
4. **Progress Monitoring**
5. **Error Handling and Recovery**

#### Agent Processing Loop

One thread per agent type (`_process_agent_tasks(agent_type)`) claims tasks
with `get_next_task` and runs each with `_run_task`:

- The agent is looked up in `self.agents` **per task**, so
  `register_agent(t, new_agent)` while processing takes effect on the next
  task (a type registered after `start_processing()` gets its own thread).
- A missing method fails the task without retry.
- An exception from the agent method fails the task **with** retry; the
  message is `Task execution failed: <ExceptionType>: <message>` and the
  traceback is logged.
- Once the method has succeeded, a failure to store its result (most often
  a value `json.dumps` cannot serialise, e.g. a `datetime`) fails the task
  **without** retry (`Task result could not be stored: TypeError: ...`), so
  the method's side effects (LLM calls, database writes) are not repeated.
- Results are stored as-is if they are a `dict`, as `__dict__` for objects,
  and as `{"result": value}` otherwise.

#### Workflow Management

`Workflow` tracks each step through *submitted* (handed to the queue) to
exactly one terminal state: **completed**, **failed** or **skipped**.

- `get_ready_steps()` returns steps that are neither submitted nor finished
  and whose dependencies all completed — an in-flight step is never handed
  out twice.
- `mark_failed(step)` also skips every transitive dependent and returns their
  names, so a failure can never leave dependents waiting forever.
- `validate()` rejects unknown dependency names and cycles (Kahn's
  algorithm); `reset()` clears progress.
- `is_complete()` is true once no step is unfinished.
- `mark_submitted` / `mark_completed` / `mark_failed` raise on an unknown
  step (`KeyError`) or one already finished (`ValueError`), so a step can
  never hold two states. The four state sets are still public attributes;
  a single step-state map is a ROADMAP follow-up.

`AgentOrchestrator.execute_workflow(name, initial_data, timeout=None)`
validates the workflow and that every step's `agent_type` is registered,
warns about agent types with no live processing thread, refuses a second
concurrent run of the same workflow (`RuntimeError`), then `_run_workflow`
resets it and loops:

1. stop if complete — checked before the deadline, so a run finishing in
   the poll that crosses the deadline still returns its results;
2. past the deadline, cancel this run's pending tasks and raise
   `WorkflowTimeoutError` (`unfinished_steps`, partial `results`, and
   `running_steps` for tasks an agent had already started);
3. submit ready steps (after the deadline check, so nothing is queued once
   the caller has stopped waiting);
4. sleep `polling_interval`, but not past the deadline;
5. `_poll_workflow_tasks`: `COMPLETED` records the result; `FAILED`,
   `CANCELLED` or a task missing from the queue fails the step (event
   `status` `failed` / `cancelled` / `missing`) and skips its dependents.

Any other exception (queue errors, `KeyboardInterrupt`, or the `SystemExit`
raised by QueueManager's SIGTERM handler) cancels the run's
pending tasks, emits `workflow_aborted` and is re-raised. Cancellation uses
`QueueManager.cancel_task(task_id)`, which only moves a `PENDING` task to
`CANCELLED`; workers claim tasks with one atomic `UPDATE … WHERE status =
'pending'`, so a task is either cancelled or run, never both.
`workflow_completed` carries `success` (no failed or skipped steps).

Processing threads are tracked per agent type (`_agent_threads`):
`register_agent` starts a thread for a new agent type when processing is
already running, so a late-registered agent's steps are not left pending.

Tests: `tests/test_orchestrator_workflow.py`.

### BaseAgent Integration (`base.py`)

Extended BaseAgent class with queue integration methods.

#### Queue Integration Methods
```python
def submit_task(self, method_name: str, data: Dict[str, Any], 
               target_agent: Optional[str] = None) -> Optional[str]:
    """Submit a task to the orchestrator queue."""
    if not self.orchestrator:
        return None
    
    return self.orchestrator.submit_task(
        target_agent=target_agent or self.get_agent_type(),
        method_name=method_name,
        data=data,
        source_agent=self.get_agent_type()
    )

def submit_batch_tasks(self, method_name: str, data_list: list[Dict[str, Any]],
                      target_agent: Optional[str] = None) -> Optional[list[str]]:
    """Submit multiple tasks efficiently."""
    if not self.orchestrator:
        return None
    
    return self.orchestrator.submit_batch_tasks(
        target_agent=target_agent or self.get_agent_type(),
        method_name=method_name,
        data_list=data_list,
        source_agent=self.get_agent_type()
    )
```

### DocumentScoringAgent Queue Methods (`scoring_agent.py`)

Queue-aware methods for memory-efficient document processing.

#### Memory-Efficient Stream Processing
```python
def process_scoring_queue(self, user_question: str, documents: List[Dict],
                         progress_callback: Optional[Callable] = None,
                         batch_size: int = 50) -> Iterator[Tuple[Dict, ScoringResult]]:
    """Process documents via queue with memory efficiency."""
    
    if not self.orchestrator:
        # Fallback to direct processing
        for i, doc in enumerate(documents):
            result = self.evaluate_document(user_question, doc)
            if progress_callback:
                progress_callback(i + 1, len(documents))
            yield (doc, result)
        return
    
    total_docs = len(documents)
    processed = 0
    
    # Process in batches to manage memory
    for i in range(0, total_docs, batch_size):
        batch = documents[i:i + batch_size]
        
        # Submit batch to queue
        task_ids = self.submit_scoring_tasks(user_question, batch)
        
        # Wait for batch completion and yield results
        completed_tasks = self.orchestrator.wait_for_completion(task_ids)
        
        for task_id, task in completed_tasks.items():
            if task.status == TaskStatus.COMPLETED and task.result:
                # Find corresponding document and yield result
                task_idx = task_ids.index(task_id)
                doc = batch[task_idx]
                
                scoring_result = {
                    'score': task.result.get('score', 0),
                    'reasoning': task.result.get('reasoning', 'Unknown result')
                }
                
                processed += 1
                if progress_callback:
                    progress_callback(processed, total_docs)
                
                yield (doc, scoring_result)
```

## Task Lifecycle

### 1. Task Creation
```
User/Agent → QueueManager.add_task() → SQLite Database
                                     ↓
                            TaskStatus.PENDING
```

### 2. Task Processing
```
QueueManager.get_next_task() → TaskStatus.PROCESSING
                              ↓
                  Agent.method(**task.data)
                              ↓
   Success: TaskStatus.COMPLETED
   Method raised / DB error storing result:
            TaskStatus.PENDING (retry) or FAILED (max retries)
   Missing method / result not JSON-serialisable / unexpected worker error:
            TaskStatus.FAILED, no retry
```

### 3. Result Collection
```
TaskStatus.COMPLETED → QueueTask.result → User/Calling Agent
TaskStatus.FAILED → QueueTask.error_message → Error Handling
```

## Performance Characteristics

### Memory Usage
- **Queue overhead**: ~1KB per task (SQLite storage)  
- **Active processing**: Only processes batches in memory
- **Result streaming**: Results yielded as completed, not accumulated

### Processing Throughput
- **Parallel processing**: Up to `max_workers` concurrent tasks
- **Priority queuing**: High-priority tasks processed first
- **Batch operations**: Efficient multi-task submission

### Database Performance
- **Indexed queries**: Efficient task retrieval by status/priority
- **Connection pooling**: SQLite connection reuse
- **Transaction batching**: Multiple operations per transaction

## Error Handling Strategy

### Retry Logic
`QueueManager.fail_task(task_id, error_message, retry=True)`:

```
new_retry_count = retry_count + 1
if retry and new_retry_count <= max_retries:
    PENDING, retry_count = new_retry_count   # re-queued at once, no delay
else:
    FAILED,  retry_count = new_retry_count
```

With `worker_id` the write applies only while the task is still PROCESSING
and held by that worker; without it, only while it is pending or processing.

### Error Categories
1. **Agent method raises** (network issues, Ollama unavailable, missing model,
   bad document data): retried up to `max_retries`, then FAILED. The message
   names the exception type (`Task execution failed: KeyError: 'x'`).
2. **Method not found on the agent**: FAILED at once, no retry.
3. **Result not JSON-serialisable**: FAILED at once, no retry; the method is
   not re-run, since it would repeat its side effects and fail the same way.
4. **Database error while storing the result** (e.g. locked after the busy
   timeout): re-queued like case 1, so the work is not discarded for good.
5. **Any other error after the task was claimed**: FAILED, no retry
   (`Worker error: ...`). If even that write fails, a `task_stuck` progress
   event and log entry say how to release the task (`python -m
   bmlibrarian.queue_cli recover --force --timeout 0` while this process runs,
   `cleanup-dead` after it has exited).
6. **Task taken away while running** (recovered, and possibly re-claimed or
   cancelled since): the worker's result or failure is discarded with a
   warning; the queue keeps the new state and a `task_discarded` event is sent
   instead of `task_completed`/`task_failed`.

`task_failed` events carry `will_retry` (True when the task went back to
PENDING), so a progress display need not report a retried task as lost.

### Recovery Mechanisms
- **Queue persistence**: Tasks survive application crashes
- **Status tracking**: Clear visibility into failed operations  
- **Manual intervention**: Ability to cancel/requeue tasks

## Scaling Considerations

### Vertical Scaling (Single Machine)
- **Worker threads**: Scale with CPU cores (typically 2-8 workers)
- **Database location**: Use SSD for better SQLite performance
- **Memory management**: Tune batch sizes based on available RAM

### Horizontal Scaling (Multiple Machines)
Current limitation: Single SQLite database per queue

**Future extensions**:
- **Distributed queues**: Redis/PostgreSQL backend options
- **Work stealing**: Multiple machines sharing task queue
- **Coordination**: Distributed orchestrator with leader election

### Performance Monitoring
```python
def get_performance_stats(self) -> Dict[str, Any]:
    """Get detailed performance statistics."""
    return {
        "queue_size": self.queue.get_queue_stats(),
        "processing_rate": self.calculate_processing_rate(),
        "average_task_time": self.calculate_average_task_time(),
        "error_rate": self.calculate_error_rate(),
        "worker_utilization": self.get_worker_utilization()
    }
```

## Testing Strategy

### Unit Tests (`test_queue_system.py`)

**QueueManager Tests**:
- Task lifecycle operations
- Priority ordering
- Thread safety
- Retry logic
- Statistics and cleanup

**AgentOrchestrator Tests**:
- Agent registration
- Task routing
- Progress callbacks
- Workflow execution
- Background processing

**Integration Tests**:
- End-to-end task processing
- Multi-agent workflows
- Error handling scenarios
- Performance under load

### Test Database Management
```python
def setup_method(self):
    """Use temporary database for each test."""
    self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
    self.temp_db.close()
    self.queue = QueueManager(self.temp_db.name)

def teardown_method(self):
    """Clean up temporary database."""
    os.unlink(self.temp_db.name)
```

## Security Considerations

### Data Protection
- **Task data**: Sensitive information only in temporary SQLite file
- **Result security**: Results cleared after processing
- **Access control**: File-system level protection for queue database

### Input Validation
```python
def add_task(self, target_agent: str, method_name: str, data: Dict) -> str:
    # Validate inputs
    if not target_agent or not method_name:
        raise ValueError("target_agent and method_name are required")
    
    if not isinstance(data, dict):
        raise ValueError("data must be a dictionary")
    
    # Sanitize data for JSON storage
    try:
        json.dumps(data)  # Ensure serializable
    except (TypeError, ValueError) as e:
        raise ValueError(f"data must be JSON serializable: {e}")
```

### Process Isolation
- **Agent methods**: Executed in separate threads
- **Error isolation**: Exceptions don't crash orchestrator
- **Resource limits**: Configurable timeouts and retries

## Future Enhancements

### Planned Features

1. **Queue Backends**
   - PostgreSQL backend for distributed setups
   - Redis backend for high-performance scenarios
   - S3 backend for serverless architectures

2. **Advanced Scheduling**
   - Cron-like scheduling for recurring tasks
   - Resource-aware scheduling based on system load
   - Geographic distribution for multi-region processing

3. **Monitoring and Observability**
   - Prometheus metrics integration
   - Distributed tracing support
   - Real-time dashboard for queue health

4. **Performance Optimizations**
   - Connection pooling for database backends
   - Result caching for repeated tasks
   - Adaptive batch sizing based on performance

### Extension Points

**Custom Queue Backends**:
```python
class CustomQueueBackend(ABC):
    @abstractmethod
    def add_task(self, task: QueueTask) -> str: pass
    
    @abstractmethod  
    def get_next_task(self, agent_type: str) -> Optional[QueueTask]: pass
```

**Custom Orchestration Strategies**:
```python
class CustomOrchestrationStrategy(ABC):
    @abstractmethod
    def select_next_agent(self, available_agents: List[str]) -> Optional[str]: pass
    
    @abstractmethod
    def should_scale_workers(self, queue_stats: Dict) -> int: pass
```

The queue system architecture provides a robust foundation for scalable document processing while maintaining simplicity in common use cases. Its SQLite-based design eliminates external dependencies while providing enterprise-grade reliability and performance for most use cases.