#!/usr/bin/env python3
"""
PubMed Bulk Import CLI for BMLibrarian

Command-line interface for downloading and importing complete PubMed baseline
and update files (over HTTPS, MD5-verified, resumable). This tool enables maintaining a complete local PubMed
mirror with offline capability.

Usage:
    # Download baseline files (complete PubMed snapshot)
    python pubmed_bulk_cli.py download-baseline

    # Download update files (new articles + metadata updates)
    python pubmed_bulk_cli.py download-updates

    # Import all downloaded files
    python pubmed_bulk_cli.py import

    # Import only baseline files
    python pubmed_bulk_cli.py import --type baseline

    # Show download/import status
    python pubmed_bulk_cli.py status

    # Complete workflow: download baseline + updates, then import
    python pubmed_bulk_cli.py sync
"""

import argparse
import logging
import os
import sys
from pathlib import Path

from contextlib import nullcontext
from typing import Dict, Optional

from src.bmlibrarian.importers.pubmed_bulk_importer import PubMedBulkImporter, DownloadTracker
from bmlibrarian.database import close_database
from bmlibrarian.db_conninfo import build_conninfo
from bmlibrarian.db_import_profile import ImportProfile, import_profile

# Parallel import processes. 8 measured 3.5x faster than 1 on an M3 Max with
# PostgreSQL 18 (Phase A, 2026-10-13); capped by the CPU count.
DEFAULT_IMPORT_WORKERS = max(1, min(8, (os.cpu_count() or 1)))


def current_conninfo() -> str:
    """libpq connection string from the selected env file (BMLIBRARIAN_ENV_FILE or ~/.bmlibrarian/.env)."""
    return build_conninfo(
        host=os.getenv("POSTGRES_HOST", "localhost"), port=os.getenv("POSTGRES_PORT", "5432"),
        user=os.getenv("POSTGRES_USER"), password=os.getenv("POSTGRES_PASSWORD"),
        dbname=os.getenv("POSTGRES_DB", "knowledgebase"))


def run_import(args, file_type: Optional[str]) -> Dict:
    """Import downloaded files, optionally inside the server import profile.

    The profile restarts the server on apply and restore, so the importer's
    connection pool is opened inside the profile and closed before it ends.
    """
    profile = import_profile(current_conninfo(), force=args.force_profile) if args.import_profile else nullcontext()
    with profile:
        importer = PubMedBulkImporter(data_dir=args.data_dir, use_tracking=not args.no_tracking)
        try:
            return importer.import_all_files(file_type=file_type, workers=args.workers)
        finally:
            if args.import_profile:
                importer.db_manager.close()
                close_database()


def cmd_profile(args) -> int:
    """Show, apply or restore the server import profile (manual control and recovery)."""
    controller = ImportProfile.for_server(current_conninfo())
    if args.profile_action == "status":
        print(f"Import profile active: {controller.is_active} (state file: {controller.state_file})")
    elif args.profile_action == "apply":
        print(controller.apply(force=args.force))
    else:
        print(controller.restore())
    return 0


def positive_int(value: str) -> int:
    """argparse type: an integer >= 1."""
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError(f"must be >= 1, got {number}")
    return number


def setup_logging(verbose: bool = False):
    """Configure logging for the CLI."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def format_bytes(bytes_val: int) -> str:
    """Format bytes as human-readable string."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_val < 1024.0:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.1f} PB"


def cmd_download_baseline(args):
    """Download PubMed baseline files."""
    print("=" * 70)
    print("PubMed Bulk Download - Baseline Files")
    print("=" * 70)
    print(f"Data directory: {args.data_dir}")
    print(f"Skip existing: {not args.force}")
    print("=" * 70)
    print("\nThis will download the complete PubMed baseline (~38M articles)")
    print("Download size: ~300-400 GB compressed")
    print("Time estimate: Hours to days depending on connection speed")
    print("=" * 70)

    if not args.yes:
        response = input("\nProceed with baseline download? [y/N]: ")
        if response.lower() != 'y':
            print("Cancelled.")
            return 0

    try:
        importer = PubMedBulkImporter(
            data_dir=args.data_dir,
            use_tracking=not args.no_tracking
        )

        print("\nStarting baseline download...")
        count = importer.download_baseline(skip_existing=not args.force)

        print("\n" + "=" * 70)
        print(f"Baseline download complete: {count} files downloaded")
        print("=" * 70)

        return 0

    except Exception as e:
        logging.error(f"Error during baseline download: {e}", exc_info=True)
        return 1


def cmd_download_updates(args):
    """Download PubMed update files."""
    print("=" * 70)
    print("PubMed Bulk Download - Update Files")
    print("=" * 70)
    print(f"Data directory: {args.data_dir}")
    print(f"Skip existing: {not args.force}")
    print("=" * 70)
    print("\nThis will download PubMed daily update files")
    print("Update files contain new articles + metadata updates to existing records")
    print("=" * 70)

    try:
        importer = PubMedBulkImporter(
            data_dir=args.data_dir,
            use_tracking=not args.no_tracking
        )

        print("\nStarting update files download...")
        count = importer.download_updates(skip_existing=not args.force)

        print("\n" + "=" * 70)
        print(f"Update files download complete: {count} files downloaded")
        print("=" * 70)

        return 0

    except Exception as e:
        logging.error(f"Error during update download: {e}", exc_info=True)
        return 1


def cmd_import(args):
    """Import downloaded XML files."""
    print("=" * 70)
    print("PubMed Bulk Import - XML Files")
    print("=" * 70)
    print(f"Data directory: {args.data_dir}")
    if args.type:
        print(f"Import type: {args.type}")
    else:
        print("Import type: All (baseline + updates)")
    print(f"Workers: {args.workers}")
    print("=" * 70)

    try:
        print("\nStarting import...")
        stats = run_import(args, args.type)

        print("\n" + "=" * 70)
        print("Import Complete!")
        print("=" * 70)
        print(f"Files processed: {stats['files_processed']}")
        print(f"Files skipped (already imported): {stats.get('files_skipped', 0)}")
        print(f"Total articles: {stats['total_articles']}")
        print(f"Errors: {stats['total_errors']}")
        print("=" * 70)

        return 0

    except Exception as e:
        logging.error(f"Error during import: {e}", exc_info=True)
        return 1


WITHDRAWAL_FILE_TYPES = {'update': 'update', 'baseline': 'baseline', 'all': None}


def cmd_backfill_withdrawals(args):
    """Apply DeleteCitation withdrawals from files imported before they were handled."""
    print("=" * 70)
    print("PubMed Withdrawal Backfill")
    print("=" * 70)
    try:
        importer = PubMedBulkImporter(data_dir=args.data_dir, use_tracking=not args.no_tracking)
        result = importer.backfill_withdrawals(file_type=WITHDRAWAL_FILE_TYPES[args.type],
                                               progress_callback=print)
    except Exception as e:
        logging.error(f"Withdrawal backfill failed: {e}", exc_info=True)
        print(f"\nError: {e}")
        return 1
    print(f"\nFiles scanned:      {result['files_scanned']}")
    print(f"PMIDs listed:       {result['pmids_listed']}")
    print(f"PMIDs newly marked: {result['pmids_recorded']}")
    return 0


def cmd_status(args):
    """Show download and import status."""
    print("=" * 70)
    print("PubMed Bulk Import Status")
    print("=" * 70)

    try:
        importer = PubMedBulkImporter(
            data_dir=args.data_dir,
            use_tracking=not args.no_tracking
        )

        if not args.no_tracking:
            tracker = DownloadTracker()
            stats = tracker.get_stats()

            print("\nDownload Statistics:")
            print(f"  Total files: {stats['total_files']}")
            print(f"  Baseline files: {stats['baseline_files']}")
            print(f"  Update files: {stats['update_files']}")
            print(f"  Total size: {format_bytes(stats['total_size_bytes'])}")

            print("\nProcessing Statistics:")
            print(f"  Processed files: {stats['processed_files']}")
            print(f"  Pending files: {stats['total_files'] - stats['processed_files']}")
            # Article counts are not tracked per file; the real total is
            # shown under "Database Statistics" below.

            if stats['total_files'] > 0:
                progress = 100 * stats['processed_files'] / stats['total_files']
                print(f"  Progress: {progress:.1f}%")
        else:
            print("\nTracking disabled - showing file counts only")

        # Count files in directories
        baseline_count = len(list(importer.baseline_dir.glob('*.xml.gz')))
        update_count = len(list(importer.update_dir.glob('*.xml.gz')))

        print("\nLocal Files:")
        print(f"  Baseline directory: {baseline_count} files")
        print(f"  Update directory: {update_count} files")
        print(f"  Total: {baseline_count + update_count} files")

        # Database statistics
        from bmlibrarian.database import get_db_manager
        db_manager = get_db_manager()

        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                # Count PubMed articles
                cur.execute("""
                    SELECT COUNT(*) FROM document d
                    JOIN sources s ON d.source_id = s.id
                    WHERE LOWER(s.name) LIKE '%pubmed%'
                """)
                total_articles = cur.fetchone()[0]

                # Count with MeSH terms
                cur.execute("""
                    SELECT COUNT(*) FROM document d
                    JOIN sources s ON d.source_id = s.id
                    WHERE LOWER(s.name) LIKE '%pubmed%'
                    AND d.mesh_terms IS NOT NULL
                    AND array_length(d.mesh_terms, 1) > 0
                """)
                with_mesh = cur.fetchone()[0]

                # Most recent import
                cur.execute("""
                    SELECT MAX(d.added_date) FROM document d
                    JOIN sources s ON d.source_id = s.id
                    WHERE LOWER(s.name) LIKE '%pubmed%'
                """)
                last_import = cur.fetchone()[0]

        print("\nDatabase Statistics:")
        print(f"  Total PubMed articles: {total_articles:,}")
        print(f"  Articles with MeSH terms: {with_mesh:,}")
        if last_import:
            print(f"  Last import: {last_import}")

        print("=" * 70)

        return 0

    except Exception as e:
        logging.error(f"Error getting status: {e}", exc_info=True)
        return 1


def cmd_sync(args):
    """Complete sync workflow: download + import."""
    print("=" * 70)
    print("PubMed Bulk Sync - Complete Workflow")
    print("=" * 70)
    print(f"Data directory: {args.data_dir}")
    print("\nThis will:")
    if args.baseline_only:
        print("  1. Download baseline files")
        print("  2. Import baseline files")
    elif args.updates_only:
        print("  1. Download update files")
        print("  2. Import update files")
    else:
        print("  1. Download baseline files (if --from-scratch)")
        print("  2. Download update files")
        print("  3. Import all downloaded files")
    print("=" * 70)

    if not args.yes:
        response = input("\nProceed with sync? [y/N]: ")
        if response.lower() != 'y':
            print("Cancelled.")
            return 0

    try:
        importer = PubMedBulkImporter(
            data_dir=args.data_dir,
            use_tracking=not args.no_tracking
        )

        # Download phase
        if not args.updates_only:
            if args.from_scratch or args.baseline_only:
                print("\n" + "=" * 70)
                print("Phase 1: Downloading baseline files...")
                print("=" * 70)
                importer.download_baseline(skip_existing=not args.force)

        if not args.baseline_only:
            print("\n" + "=" * 70)
            print(f"Phase {'2' if args.from_scratch else '1'}: Downloading update files...")
            print("=" * 70)
            importer.download_updates(skip_existing=not args.force)

        # Import phase
        print("\n" + "=" * 70)
        print(f"Phase {'3' if args.from_scratch and not args.baseline_only else '2'}: Importing files...")
        print("=" * 70)

        import_type = None
        if args.baseline_only:
            import_type = 'baseline'
        elif args.updates_only:
            import_type = 'update'

        if args.import_profile:
            # The profile restarts the server: release the download-phase pool first.
            importer.db_manager.close()
            close_database()
            stats = run_import(args, import_type)
        else:
            stats = importer.import_all_files(file_type=import_type, workers=args.workers)

        print("\n" + "=" * 70)
        print("Sync Complete!")
        print("=" * 70)
        print(f"Files processed: {stats['files_processed']}")
        print(f"Total articles: {stats['total_articles']}")
        print(f"Errors: {stats['total_errors']}")
        print("=" * 70)

        return 0

    except Exception as e:
        logging.error(f"Error during sync: {e}", exc_info=True)
        return 1


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(
        description='PubMed bulk download and import for complete local mirror',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )

    parser.add_argument(
        '--data-dir',
        type=str,
        default='~/knowledgebase/pubmed_data',
        help='Directory for PubMed data files (default: ~/knowledgebase/pubmed_data)'
    )

    parser.add_argument(
        '--no-tracking',
        action='store_true',
        help='Disable database tracking of downloads/imports'
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to execute')

    # Download baseline command
    baseline_parser = subparsers.add_parser(
        'download-baseline',
        help='Download PubMed baseline files (~38M articles, ~400GB)'
    )
    baseline_parser.add_argument(
        '--force',
        action='store_true',
        help='Re-download existing files'
    )
    baseline_parser.add_argument(
        '-y', '--yes',
        action='store_true',
        help='Skip confirmation prompt'
    )

    # Download updates command
    updates_parser = subparsers.add_parser(
        'download-updates',
        help='Download PubMed daily update files'
    )
    updates_parser.add_argument(
        '--force',
        action='store_true',
        help='Re-download existing files'
    )

    # Import command
    import_parser = subparsers.add_parser(
        'import',
        help='Import downloaded XML files into database'
    )
    import_parser.add_argument(
        '--type',
        choices=['baseline', 'update'],
        help='Import only specific file type'
    )
    import_parser.add_argument(
        '--workers',
        type=positive_int,
        default=DEFAULT_IMPORT_WORKERS,
        help=f'Parallel import processes; each file is one resumable transaction '
             f'(default: {DEFAULT_IMPORT_WORKERS})'
    )
    import_parser.add_argument(
        '--import-profile',
        action='store_true',
        help='Borrow RAM for the import: apply the server import profile (restarts the server) '
             'and restore the day-to-day settings afterwards'
    )
    import_parser.add_argument(
        '--force-profile',
        action='store_true',
        help='Apply the import profile even if other client sessions are connected'
    )

    # Status command
    status_parser = subparsers.add_parser(
        'status',
        help='Show download and import status'
    )

    # Sync command
    sync_parser = subparsers.add_parser(
        'sync',
        help='Complete workflow: download + import'
    )
    sync_parser.add_argument(
        '--from-scratch',
        action='store_true',
        help='Include baseline download (complete mirror)'
    )
    sync_parser.add_argument(
        '--baseline-only',
        action='store_true',
        help='Download and import baseline only'
    )
    sync_parser.add_argument(
        '--updates-only',
        action='store_true',
        help='Download and import updates only'
    )
    sync_parser.add_argument(
        '--force',
        action='store_true',
        help='Re-download existing files'
    )
    sync_parser.add_argument(
        '-y', '--yes',
        action='store_true',
        help='Skip confirmation prompts'
    )
    sync_parser.add_argument(
        '--workers',
        type=positive_int,
        default=DEFAULT_IMPORT_WORKERS,
        help=f'Parallel import processes (default: {DEFAULT_IMPORT_WORKERS})'
    )
    sync_parser.add_argument(
        '--import-profile',
        action='store_true',
        help='Borrow RAM for the import: apply the server import profile (restarts the server) '
             'and restore the day-to-day settings afterwards'
    )
    sync_parser.add_argument(
        '--force-profile',
        action='store_true',
        help='Apply the import profile even if other client sessions are connected'
    )

    # Import-profile command (manual control / recovery after an abandoned import)
    profile_parser = subparsers.add_parser(
        'profile',
        help='Show, apply or restore the server import profile'
    )
    profile_parser.add_argument('profile_action', choices=['status', 'apply', 'restore'])
    profile_parser.add_argument('--force', action='store_true',
                                help='apply: even if other client sessions are connected')

    # Withdrawals from files imported before DeleteCitation was handled
    withdraw_parser = subparsers.add_parser(
        'backfill-withdrawals',
        help='Mark records withdrawn by PubMed (DeleteCitation) in already imported files'
    )
    withdraw_parser.add_argument('--type', choices=sorted(WITHDRAWAL_FILE_TYPES), default='update',
                                 help='Which downloaded files to scan (default: update)')

    return parser


def main():
    """Main entry point for the CLI."""
    parser = build_parser()
    args = parser.parse_args()

    # Setup logging
    setup_logging(args.verbose)

    # Expand data directory path
    args.data_dir = Path(args.data_dir).expanduser()

    # Execute command
    if args.command == 'download-baseline':
        return cmd_download_baseline(args)
    elif args.command == 'download-updates':
        return cmd_download_updates(args)
    elif args.command == 'import':
        return cmd_import(args)
    elif args.command == 'status':
        return cmd_status(args)
    elif args.command == 'sync':
        return cmd_sync(args)
    elif args.command == 'profile':
        return cmd_profile(args)
    elif args.command == 'backfill-withdrawals':
        return cmd_backfill_withdrawals(args)
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())
