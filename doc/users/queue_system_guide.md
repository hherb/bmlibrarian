# Agent Queue System Guide

## Overview

The BMLibrarian queue system enables memory-efficient processing of large document sets through SQLite-based task queuing and orchestration. This is essential when scoring thousands of documents where keeping everything in memory would be problematic.

## When to Use the Queue System

Use the queue system when:

- **Processing thousands of documents** - Memory usage would be excessive with direct processing
- **Long-running operations** - Tasks that take significant time and may need interruption/resumption
- **Multi-step workflows** - Operations requiring handoffs between different agents
- **Background processing** - Tasks that can run independently while doing other work
- **Scalable processing** - Need to process varying workloads efficiently

## Key Components

### QueueManager
SQLite-based persistent task queue with features:
- **Memory efficient**: Uses disk storage instead of RAM
- **Persistent**: Tasks survive application restarts
- **Thread-safe**: Safe for concurrent access
- **Priority-based**: Process high-priority tasks first
- **Retry logic**: Automatic retry for failed tasks

### AgentOrchestrator  
Coordinates multi-agent workflows:
- **Agent registration**: Manages different agent types
- **Task routing**: Routes tasks to appropriate agents
- **Progress tracking**: Monitors processing status
- **Workflow management**: Handles complex multi-step processes
- **Background processing**: Runs agents in separate threads

## Basic Usage

### Setting Up the Queue System

```python
from bmlibrarian.agents import (
    QueueManager, AgentOrchestrator, DocumentScoringAgent,
    TaskPriority
)

# Create queue manager (uses SQLite file)
queue_manager = QueueManager("agent_queue.db")

# Create orchestrator
orchestrator = AgentOrchestrator(queue_manager=queue_manager)

# Create and register agents
scoring_agent = DocumentScoringAgent(orchestrator=orchestrator)
orchestrator.register_agent("document_scoring_agent", scoring_agent)
```

### Processing Documents via Queue

```python
# Sample documents (could be thousands)
documents = [
    {"title": "Study 1", "abstract": "Research on topic A"},
    {"title": "Study 2", "abstract": "Analysis of topic B"},
    # ... thousands more
]

# Submit tasks to queue
task_ids = scoring_agent.submit_scoring_tasks(
    user_question="effectiveness of treatment approaches",
    documents=documents,
    priority=TaskPriority.HIGH
)

# Start background processing
orchestrator.start_processing()

# Monitor progress
while True:
    stats = orchestrator.get_stats()
    completed = stats["overall"].get("completed", 0)
    total = len(task_ids)
    
    if completed >= total:
        break
        
    print(f"Progress: {completed}/{total}")
    time.sleep(1)

# Get results
results = orchestrator.wait_for_completion(task_ids)
orchestrator.stop_processing()
```

## Memory-Efficient Processing

### Stream Processing
Process documents without loading all results into memory:

```python
def progress_callback(completed, total):
    print(f"Processed {completed}/{total} documents")

# Process documents as a stream
for doc, score_result in scoring_agent.process_scoring_queue(
    user_question="heart disease treatment",
    documents=large_document_set,
    progress_callback=progress_callback,
    batch_size=50  # Process in batches of 50
):
    # Handle each result as it completes
    if score_result['score'] >= 4:
        print(f"High relevance: {doc['title']} (Score: {score_result['score']})")
```

### Batch Processing
Process large sets efficiently:

```python
# Get top documents using queue processing
top_documents = scoring_agent.get_top_documents_queued(
    user_question="COVID vaccine effectiveness",
    documents=thousands_of_documents,
    top_k=20,
    min_score=3,
    progress_callback=lambda c, t: print(f"Progress: {c}/{t}")
)

print("Top relevant documents:")
for i, (doc, result) in enumerate(top_documents, 1):
    print(f"{i}. {doc['title']} - Score: {result['score']}/5")
```

## Task Priority Management

### Priority Levels
```python
from bmlibrarian.agents import TaskPriority

# Priority levels (processed in order)
TaskPriority.URGENT   # Highest priority
TaskPriority.HIGH     
TaskPriority.NORMAL   # Default
TaskPriority.LOW      # Lowest priority
```

### Using Priorities
```python
# Submit urgent tasks first
urgent_task_ids = scoring_agent.submit_scoring_tasks(
    user_question="emergency medical research",
    documents=urgent_documents,
    priority=TaskPriority.URGENT
)

# Background tasks with lower priority
background_task_ids = scoring_agent.submit_scoring_tasks(
    user_question="general research analysis", 
    documents=general_documents,
    priority=TaskPriority.LOW
)
```

## Progress Monitoring

### Progress Callbacks
Track processing progress in real-time:

```python
def detailed_progress_callback(event_type, message, data=None):
    timestamp = time.strftime("%H:%M:%S")
    
    if event_type == "task_completed":
        print(f"[{timestamp}] ✅ Task completed: {message}")
    elif event_type == "task_failed":
        print(f"[{timestamp}] ❌ Task failed: {message}")
    elif event_type == "batch_tasks_submitted":
        count = data.get("count", 0) if data else 0
        print(f"[{timestamp}] 📤 Submitted {count} tasks")

# Add callback to orchestrator
orchestrator.add_progress_callback(detailed_progress_callback)
```

### Queue Statistics
Monitor queue status:

```python
# Get overall queue statistics
stats = orchestrator.get_stats()
print("Overall queue status:")
print(f"  Pending: {stats['overall']['pending']}")
print(f"  Processing: {stats['overall']['processing']}")
print(f"  Completed: {stats['overall']['completed']}")
print(f"  Failed: {stats['overall']['failed']}")

# Get agent-specific statistics
for agent_name, agent_stats in stats["by_agent"].items():
    print(f"{agent_name}: {dict(agent_stats)}")
```

## Error Handling and Recovery

### Automatic Retry
Failed tasks are automatically retried:

```python
# Tasks are retried up to max_retries (default: 3)
task_ids = orchestrator.submit_batch_tasks(
    target_agent="document_scoring_agent",
    method_name="evaluate_document_from_queue",
    data_list=task_data,
    max_retries=5  # Custom retry limit
)
```

### Handling Failed Tasks
```python
# Wait for completion and handle failures
completed_tasks = orchestrator.wait_for_completion(task_ids, timeout=300)

failed_tasks = []
successful_tasks = []

for task_id, task in completed_tasks.items():
    if task.status == TaskStatus.FAILED:
        failed_tasks.append((task_id, task.error_message))
        print(f"Task {task_id} failed: {task.error_message}")
    elif task.status == TaskStatus.COMPLETED:
        successful_tasks.append((task_id, task.result))

print(f"Success rate: {len(successful_tasks)}/{len(task_ids)}")
```

## Multi-Agent Workflows

### Creating Workflows
Define multi-step processes with dependencies:

```python
from bmlibrarian.agents import Workflow, WorkflowStep

# Create workflow
workflow = orchestrator.create_workflow("research_analysis")

# Define steps with dependencies
search_step = WorkflowStep(
    agent_type="query_agent",
    method_name="find_abstracts",
    priority=TaskPriority.HIGH
)

scoring_step = WorkflowStep(
    agent_type="document_scoring_agent", 
    method_name="batch_evaluate_documents",
    depends_on=["search"]  # Waits for search to complete
)

workflow.add_step("search", search_step)
workflow.add_step("score", scoring_step)
```

### Executing Workflows
```python
# Execute workflow with initial data
results = orchestrator.execute_workflow("research_analysis", {
    "question": "diabetes treatment effectiveness",
    "max_results": 100
})

# Access step results
search_results = results.get("search")
scoring_results = results.get("score")
```

## Best Practices

### Memory Management
1. **Use appropriate batch sizes**: Start with 50-100 documents per batch
2. **Stream processing**: Use iterators instead of loading all results
3. **Cleanup old tasks**: Regularly clean completed tasks from queue
4. **Monitor memory usage**: Watch for memory leaks in long-running processes

```python
# Clean up old completed tasks (older than 24 hours)
orchestrator.cleanup(older_than_hours=24)

# Or manual cleanup
queue_manager.cleanup_completed_tasks(older_than_hours=6)
```

### Performance Optimization
1. **Adjust worker count**: Match to your system capabilities
2. **Use priorities effectively**: Urgent tasks first, background tasks later
3. **Batch similar operations**: Group similar tasks together
4. **Monitor processing times**: Identify bottlenecks

```python
# Configure orchestrator for your system
orchestrator = AgentOrchestrator(
    max_workers=8,          # Match your CPU cores
    polling_interval=0.5    # Check for tasks every 0.5 seconds
)
```

### Error Resilience
1. **Set appropriate retry limits**: Balance between persistence and giving up
2. **Handle partial failures**: Process successful results even if some fail
3. **Save progress**: Use persistent queues to survive application restarts
4. **Monitor failure rates**: Alert if failure rate is too high

### Queue Management
```python
# Cancel pending tasks if needed
orchestrator.queue.cancel_tasks(target_agent="document_scoring_agent")

# Check queue health
stats = orchestrator.queue.get_queue_stats()
if stats["failed"] > stats["completed"]:
    print("⚠️  High failure rate detected")
```

## Troubleshooting

### Common Issues

**High memory usage**
- Reduce batch sizes
- Use streaming processing
- Clean up completed tasks more frequently

**Slow processing**
- Increase worker count if CPU allows
- Check if Ollama model is appropriate size
- Use task priorities to process important items first

**Tasks stuck in processing state**
- Check if agents are registered correctly
- Verify Ollama is running and accessible  
- Look for exceptions in agent methods

**Queue database locks**
- Ensure only one QueueManager instance per database file
- Check file permissions on queue database
- Monitor for long-running transactions

### Debug Information
```python
# Enable detailed logging
import logging
logging.getLogger('bmlibrarian.agents').setLevel(logging.DEBUG)

# Check agent registration
print("Registered agents:", list(orchestrator.agents.keys()))

# Verify agent connectivity
for agent_name, agent in orchestrator.agents.items():
    if hasattr(agent, 'test_connection'):
        connected = agent.test_connection()
        print(f"{agent_name} connected: {connected}")
```

## Performance Guidelines

### Recommended Configurations

**Small scale (< 1000 documents)**:
```python
orchestrator = AgentOrchestrator(max_workers=2, polling_interval=1.0)
batch_size = 25
```

**Medium scale (1000-10000 documents)**:
```python
orchestrator = AgentOrchestrator(max_workers=4, polling_interval=0.5)
batch_size = 50
```

**Large scale (> 10000 documents)**:
```python
orchestrator = AgentOrchestrator(max_workers=8, polling_interval=0.2)
batch_size = 100
```

The queue system transforms BMLibrarian from a tool that processes documents one-by-one to a scalable system that can handle thousands of documents efficiently while managing memory usage and providing robust error handling.