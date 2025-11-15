#!/usr/bin/env python3
"""
PubMed Bulk Import CLI for BMLibrarian

Command-line interface for downloading and importing complete PubMed baseline
and update files via FTP. This tool enables maintaining a complete local PubMed
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
import sys
from pathlib import Path

from src.bmlibrarian.importers.pubmed_bulk_importer import PubMedBulkImporter, DownloadTracker


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
    print(f"Batch size: {args.batch_size}")
    print("=" * 70)

    try:
        importer = PubMedBulkImporter(
            data_dir=args.data_dir,
            use_tracking=not args.no_tracking
        )

        print("\nStarting import...")
        stats = importer.import_all_files(file_type=args.type)

        print("\n" + "=" * 70)
        print("Import Complete!")
        print("=" * 70)
        print(f"Files processed: {stats['files_processed']}")
        print(f"Total articles: {stats['total_articles']}")
        print(f"Errors: {stats['total_errors']}")
        print("=" * 70)

        return 0

    except Exception as e:
        logging.error(f"Error during import: {e}", exc_info=True)
        return 1


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
            print(f"  Total articles imported: {stats['total_articles']:,}")

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

        stats = importer.import_all_files(file_type=import_type)

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


def main():
    """Main entry point for the CLI."""
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
        '--batch-size',
        type=int,
        default=100,
        help='Articles per database batch (default: 100)'
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
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())
