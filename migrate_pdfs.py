#!/usr/bin/env python3
"""PDF Migration Tool

Migrates existing PDFs to year-based directory structure and updates database
to use relative paths (without base directory).

Usage:
    # Dry run (preview changes without making them)
    python migrate_pdfs.py --dry-run

    # Actually perform migration
    python migrate_pdfs.py

    # Migrate specific year range
    python migrate_pdfs.py --year-from 2020 --year-to 2023

    # Show detailed output
    python migrate_pdfs.py --verbose
"""

import argparse
import sys
import os
from pathlib import Path
from dotenv import load_dotenv
import psycopg

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from bmlibrarian.utils.pdf_manager import PDFManager


def print_banner():
    """Print tool banner."""
    print("=" * 70)
    print("PDF Migration Tool - Year-Based Organization")
    print("=" * 70)
    print()


def print_summary(stats: dict):
    """Print migration summary statistics.

    Args:
        stats: Statistics dictionary from migration
    """
    print("\n" + "=" * 70)
    print("Migration Summary")
    print("=" * 70)
    print(f"Total documents processed:  {stats['total']}")
    print(f"Successfully migrated:      {stats['migrated']}")
    print(f"Already organized:          {stats['already_organized']}")
    print(f"PDF not found:              {stats['not_found']}")
    print(f"Failed:                     {stats['failed']}")
    print(f"Skipped:                    {stats['skipped']}")

    if 'error' in stats:
        print(f"\nError: {stats['error']}")

    print("=" * 70)


def print_details(stats: dict, verbose: bool = False):
    """Print detailed migration results.

    Args:
        stats: Statistics dictionary from migration
        verbose: If True, show all details. If False, only show failures.
    """
    if not stats.get('details'):
        return

    print("\nDetailed Results:")
    print("-" * 70)

    for detail in stats['details']:
        status = detail['status']

        # Skip success entries in non-verbose mode
        if not verbose and status in ['already_organized', 'migrated']:
            continue

        doc_id = detail['doc_id']

        if status == 'migrated':
            print(f"✓ Document {doc_id}: Migrated")
            print(f"  From: {detail['from']}")
            print(f"  To:   {detail['to']}")

        elif status == 'would_migrate':
            print(f"→ Document {doc_id}: Would migrate")
            print(f"  From: {detail['from']}")
            print(f"  To:   {detail['to']}")

        elif status == 'already_organized':
            if verbose:
                print(f"✓ Document {doc_id}: Already organized at {detail['path']}")

        elif status == 'not_found':
            print(f"✗ Document {doc_id}: PDF not found")
            print(f"  Expected: {detail['current_path']}")

        elif status == 'failed':
            print(f"✗ Document {doc_id}: Failed")
            print(f"  Reason: {detail.get('message', detail.get('error', 'Unknown'))}")

        print()


def get_database_connection():
    """Create database connection from environment variables.

    Returns:
        Database connection object
    """
    load_dotenv()

    db_params = {
        'dbname': os.getenv('POSTGRES_DB', 'knowledgebase'),
        'user': os.getenv('POSTGRES_USER', 'postgres'),
        'password': os.getenv('POSTGRES_PASSWORD', ''),
        'host': os.getenv('POSTGRES_HOST', 'localhost'),
        'port': os.getenv('POSTGRES_PORT', '5432')
    }

    conn = psycopg.connect(**db_params)
    return conn


def main():
    """Main migration function."""
    parser = argparse.ArgumentParser(
        description="Migrate PDFs to year-based directory structure",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without actually moving files or updating database'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Show detailed output for all documents'
    )

    parser.add_argument(
        '--base-dir',
        type=str,
        help='PDF base directory (overrides PDF_BASE_DIR from .env)'
    )

    parser.add_argument(
        '--no-db-update',
        action='store_true',
        help='Move files but do not update database (not recommended)'
    )

    args = parser.parse_args()

    # Print banner
    print_banner()

    # Connect to database
    print("Connecting to database...")
    try:
        conn = get_database_connection()
        print("✓ Connected successfully\n")
    except Exception as e:
        print(f"✗ Failed to connect to database: {e}")
        return 1

    # Initialize PDF manager
    pdf_manager = PDFManager(base_dir=args.base_dir, db_conn=conn)
    print(f"PDF Base Directory: {pdf_manager.base_dir}\n")

    if args.dry_run:
        print("⚠️  DRY RUN MODE - No changes will be made\n")

    # Run migration
    print("Starting migration...\n")

    try:
        stats = pdf_manager.migrate_pdfs_to_year_structure(
            dry_run=args.dry_run,
            update_database=not args.no_db_update
        )

        # Print results
        print_details(stats, verbose=args.verbose)
        print_summary(stats)

        # Success message
        if args.dry_run:
            print("\n✓ Dry run completed. Use without --dry-run to perform migration.")
        else:
            print("\n✓ Migration completed!")
            if stats['failed'] > 0:
                print("⚠️  Some documents failed to migrate. Check logs above.")

    except KeyboardInterrupt:
        print("\n\nMigration cancelled by user.")
        return 130

    except Exception as e:
        print(f"\n✗ Migration failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1

    finally:
        conn.close()

    return 0


if __name__ == '__main__':
    sys.exit(main())
