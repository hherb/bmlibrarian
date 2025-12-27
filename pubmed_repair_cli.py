#!/usr/bin/env python3
"""
PubMed Download Repair CLI for BMLibrarian

Scans downloaded PubMed files for corruption, re-downloads corrupted files,
and re-imports them into the database.

Usage:
    # Scan all files and report corruption (no changes)
    python pubmed_repair_cli.py scan

    # Scan and repair: re-download corrupted files
    python pubmed_repair_cli.py repair

    # Repair and re-import corrupted files
    python pubmed_repair_cli.py repair --reimport

    # Scan specific directory type
    python pubmed_repair_cli.py scan --type baseline
    python pubmed_repair_cli.py scan --type update
"""

import argparse
import gzip
import logging
import sys
from pathlib import Path
from typing import Optional

from src.bmlibrarian.importers.pubmed_bulk_importer import (
    PubMedBulkImporter,
    DownloadTracker,
)


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the CLI."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def verify_gzip_integrity(filepath: Path) -> tuple[bool, Optional[str]]:
    """
    Verify gzip file integrity by reading entire file.

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        with gzip.open(filepath, 'rb') as gz:
            while gz.read(65536):  # Read in 64KB chunks
                pass
        return True, None
    except gzip.BadGzipFile as e:
        return False, f"Bad gzip file: {e}"
    except EOFError as e:
        return False, f"Truncated file: {e}"
    except Exception as e:
        return False, f"Error: {e}"


def scan_directory(
    directory: Path,
    file_type: str,
    verbose: bool = False
) -> list[Path]:
    """
    Scan a directory for corrupted gzip files.

    Args:
        directory: Path to scan
        file_type: 'baseline' or 'update' for display
        verbose: Show progress for each file

    Returns:
        List of corrupted file paths
    """
    corrupted = []
    files = sorted(directory.glob('*.xml.gz'))
    total = len(files)

    if total == 0:
        print(f"  No files found in {directory}")
        return corrupted

    print(f"  Scanning {total} {file_type} files...")

    for i, filepath in enumerate(files, 1):
        if verbose or i % 100 == 0:
            print(f"    [{i}/{total}] Checking {filepath.name}...", end='\r')

        is_valid, error = verify_gzip_integrity(filepath)
        if not is_valid:
            corrupted.append(filepath)
            print(f"\n    CORRUPTED: {filepath.name} - {error}")

    print(f"  Completed: {total} files scanned, {len(corrupted)} corrupted")
    return corrupted


def reset_file_for_redownload(tracker: DownloadTracker, filename: str) -> None:
    """Reset a file's tracking status so it will be re-downloaded."""
    from bmlibrarian.database import get_db_manager
    db_manager = get_db_manager()

    with db_manager.get_connection() as conn:
        with conn.cursor() as cur:
            # Delete the tracking record so the file will be re-downloaded
            cur.execute(
                "DELETE FROM pubmed_download_log WHERE file_name = %s",
                (filename,)
            )
            conn.commit()


def reset_file_for_reimport(tracker: DownloadTracker, filename: str) -> None:
    """Reset a file's processed status so it will be re-imported."""
    from bmlibrarian.database import get_db_manager
    db_manager = get_db_manager()

    with db_manager.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE pubmed_download_log
                SET processed = FALSE,
                    process_date = NULL,
                    status = 'downloaded'
                WHERE file_name = %s
            """, (filename,))
            conn.commit()


def cmd_scan(args) -> int:
    """Scan for corrupted files."""
    print("=" * 70)
    print("PubMed Download Integrity Scan")
    print("=" * 70)
    print(f"Data directory: {args.data_dir}")
    print("=" * 70)

    importer = PubMedBulkImporter(
        data_dir=args.data_dir,
        use_tracking=True
    )

    all_corrupted = []

    # Scan baseline files
    if args.type in (None, 'baseline'):
        print("\nScanning baseline files...")
        baseline_corrupted = scan_directory(
            importer.baseline_dir, 'baseline', args.verbose
        )
        all_corrupted.extend(baseline_corrupted)

    # Scan update files
    if args.type in (None, 'update'):
        print("\nScanning update files...")
        update_corrupted = scan_directory(
            importer.update_dir, 'update', args.verbose
        )
        all_corrupted.extend(update_corrupted)

    print("\n" + "=" * 70)
    print("Scan Complete")
    print("=" * 70)

    if all_corrupted:
        print(f"\nFound {len(all_corrupted)} corrupted file(s):")
        for filepath in all_corrupted:
            print(f"  - {filepath.name}")
        print("\nRun 'pubmed_repair_cli.py repair' to fix these files.")
        return 1
    else:
        print("\nAll files are intact. No corruption detected.")
        return 0


def cmd_repair(args) -> int:
    """Repair corrupted files by re-downloading and optionally re-importing."""
    print("=" * 70)
    print("PubMed Download Repair")
    print("=" * 70)
    print(f"Data directory: {args.data_dir}")
    print(f"Re-import after repair: {args.reimport}")
    print("=" * 70)

    importer = PubMedBulkImporter(
        data_dir=args.data_dir,
        use_tracking=True
    )
    tracker = DownloadTracker()

    # First, scan for corrupted files
    all_corrupted = []

    if args.type in (None, 'baseline'):
        print("\nScanning baseline files...")
        baseline_corrupted = scan_directory(
            importer.baseline_dir, 'baseline', args.verbose
        )
        all_corrupted.extend([(f, 'baseline') for f in baseline_corrupted])

    if args.type in (None, 'update'):
        print("\nScanning update files...")
        update_corrupted = scan_directory(
            importer.update_dir, 'update', args.verbose
        )
        all_corrupted.extend([(f, 'update') for f in update_corrupted])

    if not all_corrupted:
        print("\n" + "=" * 70)
        print("No corrupted files found. Nothing to repair.")
        print("=" * 70)
        return 0

    print(f"\nFound {len(all_corrupted)} corrupted file(s) to repair.")

    if not args.yes:
        response = input("\nProceed with repair? [y/N]: ")
        if response.lower() != 'y':
            print("Cancelled.")
            return 0

    # Delete corrupted files and reset tracking
    print("\nRemoving corrupted files and resetting tracking...")
    for filepath, file_type in all_corrupted:
        print(f"  Removing {filepath.name}...")
        filepath.unlink()
        reset_file_for_redownload(tracker, filepath.name)

    # Re-download files
    repaired_baseline = []
    repaired_update = []

    baseline_to_repair = [f for f, t in all_corrupted if t == 'baseline']
    update_to_repair = [f for f, t in all_corrupted if t == 'update']

    if baseline_to_repair:
        print(f"\nRe-downloading {len(baseline_to_repair)} baseline file(s)...")
        # Download baseline (will only download missing files)
        importer.download_baseline(skip_existing=True)

        # Verify the re-downloaded files
        for filepath in baseline_to_repair:
            new_path = importer.baseline_dir / filepath.name
            if new_path.exists():
                is_valid, error = verify_gzip_integrity(new_path)
                if is_valid:
                    repaired_baseline.append(new_path)
                    print(f"  ✓ {filepath.name} - repaired successfully")
                else:
                    print(f"  ✗ {filepath.name} - still corrupted: {error}")
            else:
                print(f"  ✗ {filepath.name} - failed to re-download")

    if update_to_repair:
        print(f"\nRe-downloading {len(update_to_repair)} update file(s)...")
        # Download updates (will only download missing files)
        importer.download_updates(skip_existing=True)

        # Verify the re-downloaded files
        for filepath in update_to_repair:
            new_path = importer.update_dir / filepath.name
            if new_path.exists():
                is_valid, error = verify_gzip_integrity(new_path)
                if is_valid:
                    repaired_update.append(new_path)
                    print(f"  ✓ {filepath.name} - repaired successfully")
                else:
                    print(f"  ✗ {filepath.name} - still corrupted: {error}")
            else:
                print(f"  ✗ {filepath.name} - failed to re-download")

    all_repaired = repaired_baseline + repaired_update

    # Re-import if requested
    if args.reimport and all_repaired:
        print(f"\nRe-importing {len(all_repaired)} repaired file(s)...")

        for filepath in all_repaired:
            print(f"  Importing {filepath.name}...")
            reset_file_for_reimport(tracker, filepath.name)

        # Import will pick up files marked as unprocessed
        stats = importer.import_all_files()

        print(f"\nImport complete:")
        print(f"  Files processed: {stats['files_processed']}")
        print(f"  Articles imported: {stats['total_articles']}")
        print(f"  Errors: {stats['total_errors']}")

    print("\n" + "=" * 70)
    print("Repair Complete")
    print("=" * 70)
    print(f"Corrupted files found: {len(all_corrupted)}")
    print(f"Successfully repaired: {len(all_repaired)}")
    print(f"Failed to repair: {len(all_corrupted) - len(all_repaired)}")
    print("=" * 70)

    return 0 if len(all_repaired) == len(all_corrupted) else 1


def main() -> int:
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description='Scan and repair corrupted PubMed download files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose output'
    )

    parser.add_argument(
        '--data-dir',
        type=str,
        default='~/knowledgebase/pubmed_data',
        help='Directory for PubMed data files (default: ~/knowledgebase/pubmed_data)'
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to execute')

    # Scan command
    scan_parser = subparsers.add_parser(
        'scan',
        help='Scan for corrupted files (no changes made)'
    )
    scan_parser.add_argument(
        '--type',
        choices=['baseline', 'update'],
        help='Scan only specific file type'
    )

    # Repair command
    repair_parser = subparsers.add_parser(
        'repair',
        help='Re-download and optionally re-import corrupted files'
    )
    repair_parser.add_argument(
        '--type',
        choices=['baseline', 'update'],
        help='Repair only specific file type'
    )
    repair_parser.add_argument(
        '--reimport',
        action='store_true',
        help='Re-import files after re-downloading'
    )
    repair_parser.add_argument(
        '-y', '--yes',
        action='store_true',
        help='Skip confirmation prompt'
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(args.verbose)

    # Expand data directory path
    args.data_dir = Path(args.data_dir).expanduser()

    # Execute command
    if args.command == 'scan':
        return cmd_scan(args)
    elif args.command == 'repair':
        return cmd_repair(args)
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())
