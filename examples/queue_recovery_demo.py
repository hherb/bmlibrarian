#!/usr/bin/env python3
"""
Queue Recovery and Cleanup Demo

Demonstrates the queue system's ability to handle crashes, stuck tasks,
and graceful shutdown scenarios.
"""

import os
import sys
import time
import signal
import subprocess
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bmlibrarian.agents import (
    QueueManager, AgentOrchestrator, DocumentScoringAgent,
    TaskPriority, TaskStatus
)


def demo_graceful_shutdown():
    """Demonstrate graceful shutdown handling."""
    print("🔄 Graceful Shutdown Demo")
    print("=" * 40)
    
    # Create a file-based queue for persistence
    queue_db = "demo_recovery_queue.db"
    if os.path.exists(queue_db):
        os.remove(queue_db)
    
    print("1. Creating queue and adding tasks...")
    queue = QueueManager(queue_db)
    orchestrator = AgentOrchestrator(queue_manager=queue)
    
    # Add some test tasks
    task_ids = []
    for i in range(5):
        task_id = queue.add_task(
            target_agent="demo_agent",
            method_name="process_task",
            data={"task_number": i, "content": f"Demo task {i}"}
        )
        task_ids.append(task_id)
    
    print(f"   Added {len(task_ids)} tasks")
    
    # Start one task processing (simulate work in progress)
    processing_task = queue.get_next_task("demo_agent")
    print(f"   Started processing task: {processing_task.id}")
    
    # Show queue state
    stats = queue.get_queue_stats()
    print(f"   Queue state: {dict(stats)}")
    
    print("\n2. Simulating graceful shutdown...")
    print("   (Tasks being processed will be marked as failed)")
    
    # Trigger graceful cleanup
    queue._cleanup_on_exit()
    
    # Check final state
    final_stats = queue.get_queue_stats()
    print(f"   Final state: {dict(final_stats)}")
    
    print("✅ Graceful shutdown completed\n")


def demo_stuck_task_recovery():
    """Demonstrate stuck task detection and recovery."""
    print("🕐 Stuck Task Recovery Demo")
    print("=" * 40)
    
    queue_db = "demo_recovery_queue.db" 
    queue = QueueManager(queue_db)
    
    print("1. Creating artificially stuck tasks...")
    
    # Manually create a stuck task by updating database directly
    conn = queue._get_connection()
    needs_close = not queue._persistent_conn
    try:
        # Add a task that appears to be stuck (started 45 minutes ago)
        from datetime import datetime, timezone, timedelta
        
        stuck_time = (datetime.now(timezone.utc) - timedelta(minutes=45)).isoformat()
        fake_process_id = 99999  # Non-existent process
        
        conn.execute("""
            INSERT INTO queue_tasks (
                id, target_agent, method_name, data, status, priority,
                retry_count, max_retries, created_at, started_at, process_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "stuck-task-123", "demo_agent", "stuck_method", '{"stuck": true}',
            TaskStatus.PROCESSING.value, TaskPriority.NORMAL.value,
            0, 3, stuck_time, stuck_time, fake_process_id
        ))
        conn.commit()
    finally:
        if needs_close:
            conn.close()
    
    print("   Created artificial stuck task (45 minutes old)")
    
    # Check queue health
    health = queue.get_queue_health()
    print(f"   Stuck tasks detected: {health['stuck_tasks']}")
    print(f"   Orphaned tasks detected: {health['orphaned_tasks']}")
    
    print("\n2. Recovering stuck tasks...")
    
    # Recover stuck tasks (reset to pending)
    recovered = queue.recover_stuck_tasks(stuck_timeout_minutes=30, mark_as_failed=False)
    print(f"   Reset {recovered} stuck tasks to PENDING")
    
    # Clean up orphaned tasks from dead processes
    cleaned = queue.cleanup_dead_process_tasks()
    print(f"   Cleaned up {cleaned} orphaned tasks")
    
    # Check final health
    final_health = queue.get_queue_health()
    print(f"   Final stuck tasks: {final_health['stuck_tasks']}")
    print(f"   Final orphaned tasks: {final_health['orphaned_tasks']}")
    
    print("✅ Stuck task recovery completed\n")


def demo_crash_simulation():
    """Demonstrate what happens when a process crashes."""
    print("💥 Crash Simulation Demo")
    print("=" * 40)
    
    queue_db = "demo_recovery_queue.db"
    
    print("1. Starting background processing in subprocess...")
    
    # Create a subprocess script that will simulate a crash
    crash_script = '''
import sys
import time
sys.path.insert(0, "src")

from bmlibrarian.agents import QueueManager, DocumentScoringAgent, AgentOrchestrator

# Create queue and start processing
queue = QueueManager("demo_recovery_queue.db")
orchestrator = AgentOrchestrator(queue_manager=queue)
agent = DocumentScoringAgent(orchestrator=orchestrator)
orchestrator.register_agent("document_scoring_agent", agent)

# Add some tasks
for i in range(3):
    queue.add_task("document_scoring_agent", "evaluate_document", 
                   {"question": "test", "document": {"title": f"Doc {i}"}})

print("Starting background processing...")
orchestrator.start_processing()

# Process for a short time then "crash"
time.sleep(2)
print("Simulating crash...")
exit(1)  # Sudden exit without cleanup
'''
    
    # Write the crash script
    with open("crash_simulation.py", "w") as f:
        f.write(crash_script)
    
    try:
        # Run the crash script
        process = subprocess.run([sys.executable, "crash_simulation.py"], 
                               capture_output=True, text=True, timeout=10)
        
        print(f"   Subprocess exit code: {process.returncode}")
        print(f"   Subprocess output: {process.stdout.strip()}")
        
    except subprocess.TimeoutExpired:
        print("   Subprocess timed out (as expected)")
    
    print("\n2. Checking queue state after crash...")
    
    # Check what happened to the queue
    queue = QueueManager(queue_db)
    health = queue.get_queue_health()
    
    print(f"   Queue health after crash:")
    print(f"   - Status counts: {health['status_counts']}")
    print(f"   - Stuck tasks: {health['stuck_tasks']}")
    print(f"   - Orphaned tasks: {health['orphaned_tasks']}")
    
    print("\n3. Recovering from crash...")
    
    # Clean up any orphaned tasks
    cleaned = queue.cleanup_dead_process_tasks()
    print(f"   Cleaned up {cleaned} orphaned tasks from dead processes")
    
    # Recover any stuck tasks
    recovered = queue.recover_stuck_tasks(stuck_timeout_minutes=1, mark_as_failed=False)
    print(f"   Recovered {recovered} stuck tasks")
    
    print("✅ Crash recovery completed\n")
    
    # Cleanup
    if os.path.exists("crash_simulation.py"):
        os.remove("crash_simulation.py")


def demo_cli_usage():
    """Demonstrate CLI tool usage."""
    print("🖥️  CLI Tool Demo")
    print("=" * 40)
    
    queue_db = "demo_recovery_queue.db"
    
    print("Available CLI commands for queue management:")
    print()
    
    # Show example CLI commands
    cli_examples = [
        ("Check queue health", f"python -m bmlibrarian.queue_cli status -d {queue_db}"),
        ("List pending tasks", f"python -m bmlibrarian.queue_cli list --status pending -d {queue_db}"),
        ("Recover stuck tasks", f"python -m bmlibrarian.queue_cli recover --timeout 15 -d {queue_db}"),
        ("Clean dead processes", f"python -m bmlibrarian.queue_cli cleanup-dead -d {queue_db}"),
        ("Cancel pending tasks", f"python -m bmlibrarian.queue_cli cancel -d {queue_db}"),
        ("Export queue data", f"python -m bmlibrarian.queue_cli export queue_backup.json -d {queue_db}"),
    ]
    
    for description, command in cli_examples:
        print(f"📋 {description}:")
        print(f"   {command}")
        print()
    
    print("💡 Try running these commands to manage your queue!")
    print("✅ CLI demo completed\n")


def demo_preservation_options():
    """Demonstrate queue preservation strategies."""
    print("💾 Queue Preservation Options")
    print("=" * 40)
    
    print("🔐 Option 1: Preserve Queue (for intentional restarts)")
    print("   - Use recover_stuck_tasks(mark_as_failed=False)")
    print("   - Resets stuck tasks to PENDING for retry")
    print("   - Suitable for: Planned maintenance, intentional restarts")
    print()
    
    print("❌ Option 2: Mark as Failed (for crashes)")
    print("   - Use recover_stuck_tasks(mark_as_failed=True)")
    print("   - Marks stuck tasks as permanently FAILED")
    print("   - Suitable for: Unrecoverable crashes, data corruption")
    print()
    
    print("🧹 Option 3: Clean Slate")
    print("   - Use cleanup_completed_tasks(older_than_hours=0)")
    print("   - Removes all completed/failed tasks")
    print("   - Use cancel_tasks() to cancel all pending")
    print("   - Suitable for: Fresh start, testing")
    print()
    
    queue_db = "demo_recovery_queue.db"
    queue = QueueManager(queue_db)
    
    # Show current queue state
    health = queue.get_queue_health()
    print(f"📊 Current queue state:")
    print(f"   Status counts: {health['status_counts']}")
    
    print("\n💡 Choose the appropriate strategy based on your situation!")
    print("✅ Preservation options demo completed\n")


def cleanup_demo_files():
    """Clean up demo files."""
    demo_files = ["demo_recovery_queue.db", "crash_simulation.py", "queue_backup.json"]
    
    print("🧹 Cleaning up demo files...")
    for file in demo_files:
        if os.path.exists(file):
            os.remove(file)
            print(f"   Removed {file}")
    
    print("✅ Cleanup completed")


def main():
    """Run all recovery demos."""
    print("🔧 Queue Recovery and Cleanup Demonstration")
    print("=" * 60)
    print("This demo shows how the queue system handles crashes,")
    print("stuck tasks, and provides recovery mechanisms.")
    print()
    
    try:
        # Run all demos
        demo_graceful_shutdown()
        demo_stuck_task_recovery()
        demo_crash_simulation()
        demo_cli_usage()
        demo_preservation_options()
        
        print("🎉 All recovery demos completed successfully!")
        print()
        print("Key Takeaways:")
        print("✅ Graceful shutdown automatically cleans up processing tasks")
        print("✅ Stuck task detection identifies tasks processing too long")  
        print("✅ Dead process cleanup removes orphaned tasks")
        print("✅ CLI tools provide easy queue management")
        print("✅ Multiple recovery strategies for different scenarios")
        print()
        print("Your queue system is robust and production-ready! 🚀")
        
    except KeyboardInterrupt:
        print("\n⏹️  Demo interrupted by user")
    except Exception as e:
        print(f"\n❌ Demo failed with error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cleanup_demo_files()


if __name__ == "__main__":
    main()