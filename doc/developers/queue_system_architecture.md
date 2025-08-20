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
- **Automatic retries**: Failed tasks automatically retry with backoff
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
def complete_task(task_id: str, result: Dict)
def fail_task(task_id: str, error_message: str, retry: bool = True)
```

**Monitoring and Management**:
```python
def get_task_status(task_id: str) -> Optional[QueueTask]
def get_queue_stats(target_agent: Optional[str] = None) -> Dict[str, int]
def cleanup_completed_tasks(older_than_hours: int = 24)
def cancel_tasks(target_agent: Optional[str] = None)
```

#### Thread Safety Implementation
```python
def __init__(self):
    self.lock = threading.Lock()
    
def get_next_task(self, target_agent: str) -> Optional[QueueTask]:
    with self.lock:
        with sqlite3.connect(self.db_path) as conn:
            # Atomic: query + update status in single transaction
            cursor = conn.execute("""
                SELECT * FROM queue_tasks 
                WHERE target_agent = ? AND status = ?
                ORDER BY priority DESC, created_at ASC
                LIMIT 1
            """, (target_agent, TaskStatus.PENDING.value))
            
            row = cursor.fetchone()
            if row:
                # Atomically mark as processing
                conn.execute("""
                    UPDATE queue_tasks SET status = ?, started_at = ?
                    WHERE id = ?
                """, (TaskStatus.PROCESSING.value, datetime.now().isoformat(), row[0]))
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
```python
def _process_agent_tasks(self, agent_type: str, agent: BaseAgent):
    """Main processing loop for each agent type."""
    logger.info(f"Started processing tasks for agent: {agent_type}")
    
    while not self._stop_processing.is_set():
        try:
            # Get next task for this agent type
            task = self.queue.get_next_task(agent_type)
            if task is None:
                time.sleep(self.polling_interval)
                continue
            
            # Execute the task method
            method = getattr(agent, task.method_name, None)
            if method is None:
                self.queue.fail_task(task.id, f"Method {task.method_name} not found", retry=False)
                continue
            
            # Call method with task data
            result = method(**task.data)
            
            # Handle result format conversion
            if hasattr(result, '__dict__'):
                result_dict = result.__dict__
            elif isinstance(result, dict):
                result_dict = result
            else:
                result_dict = {"result": result}
            
            self.queue.complete_task(task.id, result_dict)
            
        except Exception as e:
            logger.error(f"Task {task.id} failed: {str(e)}")
            self.queue.fail_task(task.id, str(e))
```

#### Workflow Management
```python
class Workflow:
    def __init__(self, name: str):
        self.steps: Dict[str, WorkflowStep] = {}
        self.completed_steps: set = set()
        self.failed_steps: set = set()
    
    def get_ready_steps(self) -> List[str]:
        """Get steps ready to execute (dependencies satisfied)."""
        ready = []
        for name, step in self.steps.items():
            if (name not in self.completed_steps and 
                name not in self.failed_steps and
                all(dep in self.completed_steps for dep in step.depends_on)):
                ready.append(name)
        return ready
```

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
AgentOrchestrator.get_next_task() → TaskStatus.PROCESSING
                                  ↓
                      Agent.method(**task.data)
                                  ↓
                     Success: TaskStatus.COMPLETED
                     Failure: TaskStatus.PENDING (retry) or FAILED (max retries)
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
```python
def fail_task(self, task_id: str, error_message: str, retry: bool = True):
    if retry and retry_count < max_retries:
        # Reset to PENDING for retry with exponential backoff
        self.update_task_status(task_id, TaskStatus.PENDING, retry_count + 1)
    else:
        # Mark as permanently FAILED
        self.update_task_status(task_id, TaskStatus.FAILED)
```

### Error Categories
1. **Transient errors**: Network issues, temporary Ollama unavailability
   - **Action**: Automatic retry with backoff
   
2. **Configuration errors**: Missing model, invalid method name
   - **Action**: Immediate failure, no retry
   
3. **Data errors**: Invalid document format, empty content
   - **Action**: Log error, continue processing other tasks

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