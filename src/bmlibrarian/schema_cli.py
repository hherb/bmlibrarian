"""CLI interface for bmlibrarian migration system."""

import argparse
import sys
from pathlib import Path

from .migrations import MigrationManager


def create_parser():
    """Create the argument parser for the CLI."""
    parser = argparse.ArgumentParser(
        prog="bmlibrarian",
        description="Biomedical Literature Librarian CLI"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Migration command
    migrate_parser = subparsers.add_parser("migrate", help="Database migration commands")
    migrate_subparsers = migrate_parser.add_subparsers(dest="migrate_action", help="Migration actions")
    
    # Init database command
    init_parser = migrate_subparsers.add_parser("init", help="Initialize database with baseline schema")
    init_parser.add_argument("--host", required=True, help="PostgreSQL host")
    init_parser.add_argument("--port", default="5432", help="PostgreSQL port (default: 5432)")
    init_parser.add_argument("--user", required=True, help="PostgreSQL username")
    init_parser.add_argument("--password", required=True, help="PostgreSQL password")
    init_parser.add_argument("--database", required=True, help="Database name to create")
    init_parser.add_argument("--baseline-schema", help="Path to baseline schema file")
    
    # Apply migrations command
    apply_parser = migrate_subparsers.add_parser("apply", help="Apply pending migrations")
    apply_parser.add_argument("--host", required=True, help="PostgreSQL host")
    apply_parser.add_argument("--port", default="5432", help="PostgreSQL port (default: 5432)")
    apply_parser.add_argument("--user", required=True, help="PostgreSQL username")
    apply_parser.add_argument("--password", required=True, help="PostgreSQL password")
    apply_parser.add_argument("--database", required=True, help="Database name")
    apply_parser.add_argument("--migrations-dir", help="Custom migrations directory")
    
    return parser


def main():
    """Main CLI entry point."""
    parser = create_parser()
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    if args.command == "migrate":
        if not args.migrate_action:
            parser.print_help()
            sys.exit(1)
            
        migration_manager = MigrationManager(
            host=args.host,
            port=args.port,
            user=args.user,
            password=args.password,
            database=args.database
        )
        
        if args.migrate_action == "init":
            baseline_schema = args.baseline_schema
            if not baseline_schema:
                # Look for baseline_schema.sql in the project root
                package_dir = Path(__file__).parent.parent.parent.parent
                baseline_schema = package_dir / "baseline_schema.sql"
                if not baseline_schema.exists():
                    print("Error: baseline_schema.sql not found. Please specify --baseline-schema")
                    sys.exit(1)
            
            migration_manager.initialize_database(baseline_schema)
            print("Database initialized successfully!")
            
        elif args.migrate_action == "apply":
            migrations_dir = args.migrations_dir
            if not migrations_dir:
                migrations_dir = Path.home() / ".bmlibrarian" / "migrations"
            
            applied_count = migration_manager.apply_pending_migrations(migrations_dir)
            if applied_count > 0:
                print(f"Applied {applied_count} migration(s) successfully!")
            else:
                print("No pending migrations to apply.")


if __name__ == "__main__":
    main()