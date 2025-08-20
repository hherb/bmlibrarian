# Queue Management Guide

This guide explains how to manage and recover BMLibrarian agent queues when processes are interrupted or encounter problems.

## What is the Queue System?

BMLibrarian uses a SQLite-based queue system to process large numbers of documents efficiently. When you submit tasks (like scoring thousands of documents), they're stored in a queue and processed in the background. This prevents memory issues and allows you to track progress.

## When Do You Need Queue Recovery?

You might need queue recovery in these situations:

- **Process interrupted**: You stopped the application while it was processing tasks
- **System crash**: Your computer crashed or lost power during processing  
- **Stuck tasks**: Tasks that seem to run forever without completing
- **Application freeze**: The application stopped responding

## Quick Recovery Commands

### Check Queue Status
See what's currently in your queue:

```bash
python -m bmlibrarian.queue_cli status
```

This shows you:
- How many tasks are pending, processing, completed, or failed
- Whether any tasks are stuck or orphaned
- When tasks were created

### Handle Common Problems

**Problem**: Tasks are stuck (processing for too long)
```bash
# Reset stuck tasks to retry them
python -m bmlibrarian.queue_cli recover --timeout 30

# Or mark stuck tasks as failed if they can't be recovered
python -m bmlibrarian.queue_cli recover --timeout 30 --mark-failed
```

**Problem**: Process crashed and left orphaned tasks
```bash
# Clean up tasks from dead processes
python -m bmlibrarian.queue_cli cleanup-dead
```

**Problem**: Want to start fresh
```bash
# Cancel all pending tasks
python -m bmlibrarian.queue_cli cancel

# Remove old completed/failed tasks  
python -m bmlibrarian.queue_cli cleanup-old --hours 0
```

## Detailed Recovery Scenarios

### Scenario 1: You Stopped the Application Mid-Process

**What happened**: You pressed Ctrl+C or closed the terminal while documents were being processed.

**What to do**:
1. Check the queue status:
   ```bash
   python -m bmlibrarian.queue_cli status
   ```

2. If you see "processing" tasks that are no longer running, recover them:
   ```bash
   python -m bmlibrarian.queue_cli recover --timeout 5
   ```

3. Restart your application to continue processing.

### Scenario 2: System Crashed or Lost Power

**What happened**: Your computer crashed, lost power, or the application crashed unexpectedly.

**What to do**:
1. Check for orphaned tasks:
   ```bash
   python -m bmlibrarian.queue_cli status
   ```

2. Clean up tasks from dead processes:
   ```bash
   python -m bmlibrarian.queue_cli cleanup-dead
   ```

3. Recover any stuck tasks:
   ```bash
   python -m bmlibrarian.queue_cli recover --timeout 10
   ```

### Scenario 3: Tasks Seem Stuck Forever

**What happened**: Some tasks have been "processing" for hours without completing.

**What to do**:
1. Check which tasks are stuck:
   ```bash
   python -m bmlibrarian.queue_cli list --status processing
   ```

2. If they're genuinely stuck, recover them:
   ```bash
   # Try to retry them
   python -m bmlibrarian.queue_cli recover --timeout 60
   
   # Or mark as failed if they keep getting stuck
   python -m bmlibrarian.queue_cli recover --timeout 60 --mark-failed
   ```

### Scenario 4: Want to Start Over Completely

**What happened**: You want to cancel everything and start fresh.

**What to do**:
```bash
# Cancel all pending tasks
python -m bmlibrarian.queue_cli cancel

# Remove all completed/failed tasks
python -m bmlibrarian.queue_cli cleanup-old --hours 0
```

## Understanding Queue Status

When you run `python -m bmlibrarian.queue_cli status`, you'll see:

- **Pending**: Tasks waiting to be processed
- **Processing**: Tasks currently being worked on  
- **Completed**: Successfully finished tasks
- **Failed**: Tasks that encountered errors
- **Cancelled**: Tasks that were manually cancelled

- **Stuck tasks**: Tasks processing longer than 30 minutes
- **Orphaned tasks**: Tasks from processes that no longer exist

## Recovery Strategy Guide

### When to Retry Tasks (Preserve Queue)
Use this when you had a planned interruption and want to continue where you left off:

```bash
python -m bmlibrarian.queue_cli recover --timeout 30
```

**Good for**: Intentional stops, system updates, planned restarts

### When to Mark Tasks as Failed
Use this when tasks are genuinely broken and shouldn't be retried:

```bash
python -m bmlibrarian.queue_cli recover --timeout 30 --mark-failed
```

**Good for**: System crashes, out-of-memory errors, corrupted data

### When to Start Fresh  
Use this when you want to completely reset:

```bash
python -m bmlibrarian.queue_cli cancel
python -m bmlibrarian.queue_cli cleanup-old --hours 0
```

**Good for**: Testing, major changes, debugging

## Viewing Your Tasks

### List All Tasks
```bash
python -m bmlibrarian.queue_cli list
```

### Filter by Status
```bash
python -m bmlibrarian.queue_cli list --status pending
python -m bmlibrarian.queue_cli list --status failed
```

### Filter by Agent
```bash
python -m bmlibrarian.queue_cli list --agent document_scoring_agent
```

### Show More Details
```bash
python -m bmlibrarian.queue_cli list --verbose
```

## Backup and Export

### Export Queue Data
Save your queue data to a JSON file for analysis or backup:

```bash
python -m bmlibrarian.queue_cli export my_queue_backup.json
```

This creates a file with all your task data that you can examine or share for troubleshooting.

## Prevention Tips

### 1. Monitor Progress
Check queue status periodically during long processing runs:

```bash
# In another terminal window
python -m bmlibrarian.queue_cli status
```

### 2. Use Reasonable Timeouts
If you know your tasks typically take 10 minutes, set recovery timeout to 20-30 minutes:

```bash
python -m bmlibrarian.queue_cli recover --timeout 20
```

### 3. Regular Cleanup
Clean up old completed tasks periodically to keep your queue database small:

```bash
# Remove tasks older than 1 week
python -m bmlibrarian.queue_cli cleanup-old --hours 168
```

## Troubleshooting

### "Database not found" Error
Make sure you're running the commands from the correct directory, or specify the database path:

```bash
python -m bmlibrarian.queue_cli status -d /path/to/your/agent_queue.db
```

### Commands Don't Work
Make sure you have BMLibrarian installed and are using the correct Python environment:

```bash
# Check if module is installed
python -c "import bmlibrarian; print('Installed successfully')"
```

### Tasks Keep Getting Stuck
This might indicate:
- Tasks are too complex for available memory
- Network issues (if using remote services like Ollama)
- Database performance problems

Try:
1. Reducing batch sizes in your processing
2. Checking system resources (memory, CPU)
3. Verifying external services are running

### Recovery Commands Don't Find Problems
The system may have already cleaned up automatically. BMLibrarian includes automatic cleanup when processes shut down gracefully.

## Getting Help

If you encounter problems not covered in this guide:

1. **Check the queue status first**: `python -m bmlibrarian.queue_cli status`
2. **Export queue data**: `python -m bmlibrarian.queue_cli export debug.json`
3. **Check application logs** for error messages
4. **Try the recovery demo**: `python examples/queue_recovery_demo.py`

The recovery system is designed to be safe - it won't delete your data unless you explicitly ask it to. When in doubt, try the gentler recovery options first (like `recover` without `--mark-failed`).