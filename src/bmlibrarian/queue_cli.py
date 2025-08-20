#!/usr/bin/env python3
"""
CLI tool for managing BMLibrarian agent queues.

Provides commands for queue inspection, cleanup, and recovery operations.
"""

import argparse
import sys
import json
from pathlib import Path
from datetime import datetime

from .agents.queue_manager import QueueManager, TaskStatus


def format_datetime(dt_str):
    """Format datetime string for display."""
    if not dt_str:
        return "N/A"
    try:
        dt = datetime.fromisoformat(dt_str)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return dt_str


def cmd_status(args):
    """Show queue status and health information."""
    queue = QueueManager(args.database)
    
    print("🔍 Queue Health Report")
    print("=" * 50)
    
    health = queue.get_queue_health()
    
    # Basic status counts
    print("\n📊 Task Status Summary:")
    status_counts = health["status_counts"]
    for status in TaskStatus:
        count = status_counts.get(status.value, 0)
        print(f"   {status.value.capitalize():12} {count:6d}")
    
    print(f"\n🚨 Problem Detection:")
    print(f"   Stuck tasks:     {health['stuck_tasks']:6d} (processing > 30 minutes)")
    print(f"   Orphaned tasks:  {health['orphaned_tasks']:6d} (dead processes)")
    
    print(f"\n⏰ Queue Timing:")
    print(f"   Oldest pending:  {format_datetime(health['oldest_pending_task'])}")
    print(f"   Newest task:     {format_datetime(health['newest_task'])}")
    print(f"   Active tasks:    {health['active_tasks']:6d}")
    
    print(f"\n🖥️  Process Info:")
    print(f"   Current PID:     {health['current_process_id']:6d}")
    print(f"   Database:        {health['queue_database']}")
    
    # Recommendations
    if health['stuck_tasks'] > 0:
        print(f"\n💡 Recommendation: Run 'queue-cli recover' to handle stuck tasks")
    
    if health['orphaned_tasks'] > 0:
        print(f"💡 Recommendation: Run 'queue-cli cleanup-dead' to clean orphaned tasks")


def cmd_list_tasks(args):
    """List tasks with optional filtering."""
    queue = QueueManager(args.database)
    
    # Get all tasks
    conn = queue._get_connection()
    needs_close = not queue._persistent_conn
    try:
        # Build query based on filters
        where_conditions = []
        params = []
        
        if args.status:
            where_conditions.append("status = ?")
            params.append(args.status)
        
        if args.agent:
            where_conditions.append("target_agent = ?")
            params.append(args.agent)
        
        where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
        
        cursor = conn.execute(f"""
            SELECT id, target_agent, method_name, status, priority, created_at, started_at, error_message
            FROM queue_tasks 
            {where_clause}
            ORDER BY created_at DESC
            LIMIT ?
        """, params + [args.limit])
        
        tasks = cursor.fetchall()
        
        if not tasks:
            print("No tasks found matching criteria.")
            return
        
        print(f"📋 Found {len(tasks)} tasks:")
        print()
        
        # Header
        print(f"{'ID':<36} {'Agent':<20} {'Method':<20} {'Status':<12} {'Created':<19}")
        print("-" * 107)
        
        # Tasks
        for task in tasks:
            task_id, agent, method, status, priority, created, started, error = task
            created_fmt = format_datetime(created)
            
            print(f"{task_id:<36} {agent:<20} {method:<20} {status:<12} {created_fmt}")
            
            if error and args.verbose:
                print(f"   Error: {error}")
    
    finally:
        if needs_close:
            conn.close()


def cmd_recover(args):
    """Recover stuck tasks."""
    queue = QueueManager(args.database)
    
    print(f"🔧 Recovering tasks stuck for > {args.timeout} minutes...")
    
    if args.mark_failed:
        print("   Mode: Mark stuck tasks as FAILED")
    else:
        print("   Mode: Reset stuck tasks to PENDING for retry")
    
    recovered = queue.recover_stuck_tasks(
        stuck_timeout_minutes=args.timeout,
        mark_as_failed=args.mark_failed
    )
    
    if recovered > 0:
        print(f"✅ Recovered {recovered} stuck tasks")
    else:
        print("✅ No stuck tasks found")


def cmd_cleanup_dead(args):
    """Clean up tasks from dead processes."""
    queue = QueueManager(args.database)
    
    print("🧹 Cleaning up tasks from dead processes...")
    
    cleaned = queue.cleanup_dead_process_tasks()
    
    if cleaned > 0:
        print(f"✅ Cleaned up {cleaned} orphaned tasks")
    else:
        print("✅ No orphaned tasks found")


def cmd_cleanup_old(args):
    """Clean up old completed/failed tasks."""
    queue = QueueManager(args.database)
    
    print(f"🗑️  Cleaning up completed/failed tasks older than {args.hours} hours...")
    
    queue.cleanup_completed_tasks(older_than_hours=args.hours)
    
    print("✅ Cleanup completed")


def cmd_cancel(args):
    """Cancel pending tasks."""
    queue = QueueManager(args.database)
    
    print("❌ Canceling pending tasks...")
    
    if args.agent:
        print(f"   Target agent: {args.agent}")
    
    queue.cancel_tasks(target_agent=args.agent)
    
    print("✅ Pending tasks canceled")


def cmd_export(args):
    """Export queue data to JSON."""
    queue = QueueManager(args.database)
    
    conn = queue._get_connection()
    needs_close = not queue._persistent_conn
    try:
        cursor = conn.execute("SELECT * FROM queue_tasks ORDER BY created_at")
        columns = [desc[0] for desc in cursor.description]
        
        tasks = []
        for row in cursor.fetchall():
            task_dict = dict(zip(columns, row))
            tasks.append(task_dict)
        
        export_data = {
            "export_time": datetime.now().isoformat(),
            "database": args.database,
            "task_count": len(tasks),
            "tasks": tasks
        }
        
        with open(args.output, 'w') as f:
            json.dump(export_data, f, indent=2)
        
        print(f"✅ Exported {len(tasks)} tasks to {args.output}")
    
    finally:
        if needs_close:
            conn.close()


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="BMLibrarian Queue Management CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  queue-cli status                          # Show queue health
  queue-cli list --status pending          # List pending tasks
  queue-cli recover --timeout 15           # Recover tasks stuck > 15 minutes
  queue-cli cleanup-dead                   # Clean tasks from dead processes
  queue-cli cancel --agent scoring_agent   # Cancel tasks for specific agent
        """
    )
    
    parser.add_argument('--database', '-d', 
                       default='agent_queue.db',
                       help='Path to queue database (default: agent_queue.db)')
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Status command
    status_parser = subparsers.add_parser('status', help='Show queue health status')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List tasks')
    list_parser.add_argument('--status', choices=[s.value for s in TaskStatus],
                            help='Filter by task status')
    list_parser.add_argument('--agent', help='Filter by target agent')
    list_parser.add_argument('--limit', type=int, default=50,
                           help='Maximum number of tasks to show (default: 50)')
    list_parser.add_argument('--verbose', '-v', action='store_true',
                           help='Show additional details')
    
    # Recover command
    recover_parser = subparsers.add_parser('recover', help='Recover stuck tasks')
    recover_parser.add_argument('--timeout', type=int, default=30,
                               help='Minutes after which tasks are considered stuck (default: 30)')
    recover_parser.add_argument('--mark-failed', action='store_true',
                               help='Mark stuck tasks as failed instead of retrying')
    
    # Cleanup commands
    cleanup_dead_parser = subparsers.add_parser('cleanup-dead', help='Clean up tasks from dead processes')
    
    cleanup_old_parser = subparsers.add_parser('cleanup-old', help='Clean up old completed tasks')
    cleanup_old_parser.add_argument('--hours', type=int, default=24,
                                   help='Remove tasks older than this many hours (default: 24)')
    
    # Cancel command
    cancel_parser = subparsers.add_parser('cancel', help='Cancel pending tasks')
    cancel_parser.add_argument('--agent', help='Cancel tasks for specific agent only')
    
    # Export command
    export_parser = subparsers.add_parser('export', help='Export queue data to JSON')
    export_parser.add_argument('output', help='Output JSON file path')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Check if database exists for read operations
    if args.command != 'status' and not Path(args.database).exists():
        print(f"❌ Database not found: {args.database}")
        sys.exit(1)
    
    try:
        # Dispatch to command handlers
        if args.command == 'status':
            cmd_status(args)
        elif args.command == 'list':
            cmd_list_tasks(args)
        elif args.command == 'recover':
            cmd_recover(args)
        elif args.command == 'cleanup-dead':
            cmd_cleanup_dead(args)
        elif args.command == 'cleanup-old':
            cmd_cleanup_old(args)
        elif args.command == 'cancel':
            cmd_cancel(args)
        elif args.command == 'export':
            cmd_export(args)
    
    except KeyboardInterrupt:
        print("\n❌ Operation canceled by user")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()