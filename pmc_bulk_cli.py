#!/usr/bin/env python3
"""PMC Open Access bulk download CLI.

Downloads PMC Open Access baseline and incremental packages for offline
access to biomedical literature. Designed for users with limited or
intermittent internet access.

Features:
- Resumable downloads (can stop and restart anytime)
- Rate limiting (polite to NCBI servers - default 2 min between files)
- License filtering (commercial, non-commercial, other)
- PMCID range filtering for selective downloads
- Automatic PDF and full-text extraction
- Database import with metadata

Usage:
    # List available packages
    uv run python pmc_bulk_cli.py list

    # Download commercial-use baseline (CC BY, CC0, etc.)
    uv run python pmc_bulk_cli.py download --license oa_comm

    # Download specific PMCID ranges
    uv run python pmc_bulk_cli.py download --range PMC001xxxxxx --range PMC002xxxxxx

    # Extract downloaded packages
    uv run python pmc_bulk_cli.py extract

    # Import to database
    uv run python pmc_bulk_cli.py import

    # Show status
    uv run python pmc_bulk_cli.py status

    # Full workflow (download + extract + import)
    uv run python pmc_bulk_cli.py sync
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional, List

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def get_default_output_dir() -> Path:
    """Get default output directory from config or use ~/pmc_archive."""
    try:
        from bmlibrarian.config import get_config
        config = get_config()
        pdf_base = config.get('pdf', {}).get('base_dir')
        if pdf_base:
            return Path(pdf_base).expanduser().parent / 'pmc_archive'
    except Exception:
        pass
    return Path.home() / 'pmc_archive'


def cmd_list(args: argparse.Namespace) -> int:
    """List available PMC packages."""
    from bmlibrarian.importers.pmc_bulk_importer import PMCBulkImporter

    importer = PMCBulkImporter(
        output_dir=args.output_dir,
        license_types=args.license,
        pmcid_ranges=args.range
    )

    packages = importer.list_available_packages(refresh=args.refresh)

    if not packages:
        print("No packages found matching criteria")
        return 1

    # Group by license type
    by_license = {}
    for pkg in packages:
        key = pkg.license_type.value
        if key not in by_license:
            by_license[key] = []
        by_license[key].append(pkg)

    print(f"\nAvailable PMC Open Access Packages")
    print("=" * 60)

    total_size = 0
    total_count = 0

    for license_type, pkgs in sorted(by_license.items()):
        license_size = sum(p.size_bytes for p in pkgs)
        total_size += license_size
        total_count += len(pkgs)

        print(f"\n{license_type}:")
        print(f"  Packages: {len(pkgs)}")
        print(f"  Total size: {_format_bytes(license_size)}")

        if args.verbose:
            # Show baseline packages
            baselines = [p for p in pkgs if p.is_baseline]
            incrementals = [p for p in pkgs if not p.is_baseline]

            print(f"  Baseline packages: {len(baselines)}")
            for pkg in sorted(baselines, key=lambda p: p.pmcid_range):
                status = "✓" if pkg.downloaded else " "
                print(f"    [{status}] {pkg.filename}")

            if incrementals:
                print(f"  Incremental packages: {len(incrementals)}")

    print(f"\n{'=' * 60}")
    print(f"Total: {total_count} packages, {_format_bytes(total_size)}")

    # Show download progress
    downloaded = sum(1 for p in packages if p.downloaded)
    if downloaded > 0:
        print(f"Downloaded: {downloaded}/{total_count}")

    return 0


def cmd_download(args: argparse.Namespace) -> int:
    """Download PMC packages."""
    from bmlibrarian.importers.pmc_bulk_importer import PMCBulkImporter

    importer = PMCBulkImporter(
        output_dir=args.output_dir,
        license_types=args.license,
        pmcid_ranges=args.range,
        delay_between_files=args.delay,
        use_https=not args.use_ftp
    )

    # First list available packages
    packages = importer.list_available_packages()
    to_download = [p for p in packages if not p.downloaded]

    if not to_download:
        print("All packages already downloaded!")
        return 0

    total_size = sum(p.size_bytes for p in to_download)
    print(f"\nPackages to download: {len(to_download)}")
    print(f"Total size: {_format_bytes(total_size)}")
    print(f"Delay between files: {args.delay}s")

    if args.dry_run:
        print("\n[DRY RUN] Would download:")
        for pkg in to_download[:10]:
            print(f"  - {pkg.filename}")
        if len(to_download) > 10:
            print(f"  ... and {len(to_download) - 10} more")
        return 0

    if not args.yes:
        confirm = input("\nProceed with download? [y/N] ")
        if confirm.lower() != 'y':
            print("Cancelled")
            return 1

    # Progress callback
    def progress(filename: str, current: int, total: int) -> None:
        print(f"\n[{current}/{total}] Downloading {filename}...")

    downloaded = importer.download_packages(
        baseline_only=args.baseline_only,
        progress_callback=progress
    )

    print(f"\nDownloaded {downloaded} packages")
    return 0


def cmd_extract(args: argparse.Namespace) -> int:
    """Extract downloaded packages."""
    from bmlibrarian.importers.pmc_bulk_importer import PMCBulkImporter

    importer = PMCBulkImporter(
        output_dir=args.output_dir,
        license_types=args.license
    )

    # Check what needs extraction
    importer.list_available_packages()
    to_extract = [p for p in importer.packages.values() if p.downloaded and not p.extracted]

    if not to_extract:
        print("All downloaded packages already extracted!")
        return 0

    print(f"\nPackages to extract: {len(to_extract)}")

    if args.dry_run:
        print("\n[DRY RUN] Would extract:")
        for pkg in to_extract[:10]:
            print(f"  - {pkg.filename}")
        if len(to_extract) > 10:
            print(f"  ... and {len(to_extract) - 10} more")
        return 0

    def progress(filename: str, current: int, total: int) -> None:
        print(f"[{current}/{total}] Extracting {filename}...")

    extracted = importer.extract_packages(progress_callback=progress)
    print(f"\nExtracted {extracted} packages")
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    """Import extracted articles to database."""
    from bmlibrarian.importers.pmc_bulk_importer import PMCBulkImporter

    importer = PMCBulkImporter(
        output_dir=args.output_dir,
        license_types=args.license
    )

    print("Importing articles to database...")
    print("This may take a while for large archives.\n")

    def progress(imported: int, total: int) -> None:
        pct = (imported / total * 100) if total > 0 else 0
        print(f"  Imported {imported}/{total} ({pct:.1f}%)")

    imported = importer.import_to_database(
        batch_size=args.batch_size,
        progress_callback=progress
    )

    print(f"\nImported {imported} articles")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    """Full sync: download + extract + import."""
    print("Starting full PMC sync workflow...\n")

    # Download
    print("=" * 60)
    print("STEP 1: Download packages")
    print("=" * 60)
    result = cmd_download(args)
    if result != 0:
        return result

    # Extract
    print("\n" + "=" * 60)
    print("STEP 2: Extract packages")
    print("=" * 60)
    result = cmd_extract(args)
    if result != 0:
        return result

    # Import
    if not args.skip_import:
        print("\n" + "=" * 60)
        print("STEP 3: Import to database")
        print("=" * 60)
        result = cmd_import(args)
        if result != 0:
            return result

    print("\n" + "=" * 60)
    print("Sync complete!")
    print("=" * 60)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Show current status."""
    from bmlibrarian.importers.pmc_bulk_importer import PMCBulkImporter

    importer = PMCBulkImporter(
        output_dir=args.output_dir
    )

    status = importer.get_status()

    print(f"\nPMC Bulk Import Status")
    print("=" * 60)
    print(f"Output directory: {status['output_dir']}")
    print(f"License types: {', '.join(status['license_types'])}")

    if status['pmcid_ranges']:
        print(f"PMCID ranges: {', '.join(status['pmcid_ranges'])}")

    print(f"\nPackages:")
    print(f"  Total:      {status['packages']['total']}")
    print(f"  Downloaded: {status['packages']['downloaded']}")
    print(f"  Extracted:  {status['packages']['extracted']}")
    print(f"  Imported:   {status['packages']['imported']}")

    print(f"\nData size:")
    print(f"  Total:      {status['bytes']['total_formatted']}")
    print(f"  Downloaded: {status['bytes']['downloaded_formatted']}")

    print(f"\nArticles imported: {status['articles']['imported']}")

    if status['errors'] > 0:
        print(f"\nErrors: {status['errors']}")

    if status['start_time']:
        print(f"\nStarted: {status['start_time']}")
    if status['last_update']:
        print(f"Last update: {status['last_update']}")

    return 0


def cmd_estimate(args: argparse.Namespace) -> int:
    """Estimate download time and storage requirements."""
    from bmlibrarian.importers.pmc_bulk_importer import PMCBulkImporter

    importer = PMCBulkImporter(
        output_dir=args.output_dir,
        license_types=args.license,
        pmcid_ranges=args.range,
        delay_between_files=args.delay
    )

    packages = importer.list_available_packages()
    to_download = [p for p in packages if not p.downloaded]

    if not to_download:
        print("All packages already downloaded!")
        return 0

    total_size = sum(p.size_bytes for p in to_download)
    num_packages = len(to_download)

    # Estimate times
    # Assume average download speed (conservative estimate for remote locations)
    speeds = {
        'slow': 500 * 1024,      # 500 KB/s (poor connection)
        'medium': 2 * 1024 * 1024,  # 2 MB/s (moderate connection)
        'fast': 10 * 1024 * 1024,   # 10 MB/s (good connection)
    }

    # Total delay time
    delay_time = (num_packages - 1) * args.delay

    print(f"\nDownload Estimate")
    print("=" * 60)
    print(f"Packages to download: {num_packages}")
    print(f"Total size: {_format_bytes(total_size)}")
    print(f"Delay between files: {args.delay}s")
    print(f"Total delay time: {_format_time(delay_time)}")

    print(f"\nEstimated download time:")
    for name, speed in speeds.items():
        download_time = total_size / speed
        total_time = download_time + delay_time
        print(f"  {name:8} ({_format_bytes(speed)}/s): {_format_time(total_time)}")

    print(f"\nStorage requirements:")
    print(f"  Packages (compressed): {_format_bytes(total_size)}")
    print(f"  Extracted (estimate):  {_format_bytes(total_size * 3)}")
    print(f"  Total (estimate):      {_format_bytes(total_size * 4)}")

    return 0


def _format_bytes(size: int) -> str:
    """Format bytes as human-readable string."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def _format_time(seconds: float) -> str:
    """Format seconds as human-readable duration."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        return f"{seconds / 60:.0f}m"
    elif seconds < 86400:
        hours = seconds / 3600
        return f"{hours:.1f}h"
    else:
        days = seconds / 86400
        return f"{days:.1f}d"


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="PMC Open Access bulk download tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List available packages
  %(prog)s list

  # Download commercial-use baseline packages
  %(prog)s download --license oa_comm

  # Download with longer delay (politer to servers)
  %(prog)s download --delay 300  # 5 minutes between files

  # Download specific PMCID ranges only
  %(prog)s download --range PMC001xxxxxx --range PMC002xxxxxx

  # Extract and import after download
  %(prog)s extract
  %(prog)s import

  # Full sync workflow
  %(prog)s sync --license oa_comm

License types:
  oa_comm     - Commercial use allowed (CC0, CC BY, CC BY-SA, CC BY-ND)
  oa_noncomm  - Non-commercial only (CC BY-NC variants)
  oa_other    - Custom or no license
"""
    )

    parser.add_argument(
        '-o', '--output-dir',
        type=Path,
        default=get_default_output_dir(),
        help='Output directory for downloaded files (default: ~/pmc_archive)'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Verbose output'
    )

    subparsers = parser.add_subparsers(dest='command', help='Command')

    # List command
    list_parser = subparsers.add_parser('list', help='List available packages')
    list_parser.add_argument(
        '--license',
        action='append',
        choices=['oa_comm', 'oa_noncomm', 'oa_other'],
        help='License types to list (can specify multiple)'
    )
    list_parser.add_argument(
        '--range',
        action='append',
        help='PMCID ranges (e.g., PMC001xxxxxx)'
    )
    list_parser.add_argument(
        '--refresh',
        action='store_true',
        help='Refresh package list from server'
    )

    # Download command
    dl_parser = subparsers.add_parser('download', help='Download packages')
    dl_parser.add_argument(
        '--license',
        action='append',
        choices=['oa_comm', 'oa_noncomm', 'oa_other'],
        default=None,
        help='License types to download (default: oa_comm)'
    )
    dl_parser.add_argument(
        '--range',
        action='append',
        help='PMCID ranges to download (e.g., PMC001xxxxxx)'
    )
    dl_parser.add_argument(
        '--delay',
        type=int,
        default=120,
        help='Seconds between file downloads (default: 120)'
    )
    dl_parser.add_argument(
        '--baseline-only',
        action='store_true',
        default=True,
        help='Only download baseline packages (default: True)'
    )
    dl_parser.add_argument(
        '--include-incremental',
        action='store_false',
        dest='baseline_only',
        help='Also download incremental packages'
    )
    dl_parser.add_argument(
        '--use-ftp',
        action='store_true',
        help='Use FTP instead of HTTPS'
    )
    dl_parser.add_argument(
        '-y', '--yes',
        action='store_true',
        help='Skip confirmation prompt'
    )
    dl_parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be downloaded without downloading'
    )

    # Extract command
    ext_parser = subparsers.add_parser('extract', help='Extract downloaded packages')
    ext_parser.add_argument(
        '--license',
        action='append',
        choices=['oa_comm', 'oa_noncomm', 'oa_other'],
        default=None,
        help='License types to extract'
    )
    ext_parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be extracted without extracting'
    )

    # Import command
    imp_parser = subparsers.add_parser('import', help='Import to database')
    imp_parser.add_argument(
        '--license',
        action='append',
        choices=['oa_comm', 'oa_noncomm', 'oa_other'],
        default=None,
        help='License types to import'
    )
    imp_parser.add_argument(
        '--batch-size',
        type=int,
        default=100,
        help='Articles per database batch (default: 100)'
    )

    # Sync command
    sync_parser = subparsers.add_parser('sync', help='Full sync (download + extract + import)')
    sync_parser.add_argument(
        '--license',
        action='append',
        choices=['oa_comm', 'oa_noncomm', 'oa_other'],
        default=None,
        help='License types to sync'
    )
    sync_parser.add_argument(
        '--range',
        action='append',
        help='PMCID ranges to sync'
    )
    sync_parser.add_argument(
        '--delay',
        type=int,
        default=120,
        help='Seconds between file downloads (default: 120)'
    )
    sync_parser.add_argument(
        '--baseline-only',
        action='store_true',
        default=True,
        help='Only sync baseline packages'
    )
    sync_parser.add_argument(
        '--skip-import',
        action='store_true',
        help='Skip database import step'
    )
    sync_parser.add_argument(
        '-y', '--yes',
        action='store_true',
        help='Skip confirmation prompts'
    )
    sync_parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without doing it'
    )
    sync_parser.add_argument(
        '--use-ftp',
        action='store_true',
        help='Use FTP instead of HTTPS'
    )
    sync_parser.add_argument(
        '--batch-size',
        type=int,
        default=100,
        help='Articles per database batch (default: 100)'
    )

    # Status command
    status_parser = subparsers.add_parser('status', help='Show current status')

    # Estimate command
    est_parser = subparsers.add_parser('estimate', help='Estimate download time and storage')
    est_parser.add_argument(
        '--license',
        action='append',
        choices=['oa_comm', 'oa_noncomm', 'oa_other'],
        default=None,
        help='License types to estimate'
    )
    est_parser.add_argument(
        '--range',
        action='append',
        help='PMCID ranges to estimate'
    )
    est_parser.add_argument(
        '--delay',
        type=int,
        default=120,
        help='Seconds between file downloads (default: 120)'
    )

    args = parser.parse_args()

    # Set default license if not specified
    if hasattr(args, 'license') and args.license is None:
        args.license = ['oa_comm']

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Dispatch command
    commands = {
        'list': cmd_list,
        'download': cmd_download,
        'extract': cmd_extract,
        'import': cmd_import,
        'sync': cmd_sync,
        'status': cmd_status,
        'estimate': cmd_estimate,
    }

    if args.command is None:
        parser.print_help()
        return 1

    try:
        return commands[args.command](args)
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        return 130
    except Exception as e:
        logger.error(f"Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
