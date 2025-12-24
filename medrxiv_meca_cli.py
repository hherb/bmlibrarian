#!/usr/bin/env python3
"""
MedRxiv MECA Import CLI for BMLibrarian

Command-line interface for downloading and importing medRxiv MECA packages
from AWS S3 for comprehensive offline access to full-text JATS XML content.

IMPORTANT: This requires AWS credentials and incurs requester-pays S3 costs.
Install AWS dependencies with: uv pip install bmlibrarian[aws]

Usage:
    # List available MECA packages
    python medrxiv_meca_cli.py list --limit 10

    # Download MECA packages
    python medrxiv_meca_cli.py download --limit 10 --output-dir ~/medrxiv_meca

    # Import downloaded packages to database
    python medrxiv_meca_cli.py import --meca-dir ~/medrxiv_meca

    # Full sync workflow (download + import)
    python medrxiv_meca_cli.py sync --output-dir ~/medrxiv_meca --limit 100

    # Show import status
    python medrxiv_meca_cli.py status --meca-dir ~/medrxiv_meca
"""

import argparse
import logging
import sys
from pathlib import Path

# Check for boto3 availability
try:
    import boto3
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False


def setup_logging(verbose: bool = False):
    """Configure logging for the CLI."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def check_boto3():
    """Check if boto3 is available and provide helpful message if not."""
    if not BOTO3_AVAILABLE:
        print("=" * 70)
        print("ERROR: AWS SDK (boto3) is required for MECA import")
        print("=" * 70)
        print("\nInstall with: uv pip install bmlibrarian[aws]")
        print("Or: uv pip install boto3")
        print("\nNote: MECA import requires AWS credentials and incurs")
        print("requester-pays S3 costs. See medRxiv TDM page for details:")
        print("https://www.medrxiv.org/tdm")
        print("=" * 70)
        return False
    return True


def cmd_list(args):
    """List available MECA packages."""
    if not check_boto3():
        return 1

    print("=" * 70)
    print("MedRxiv MECA Package Listing")
    print("=" * 70)

    try:
        from src.bmlibrarian.importers.medrxiv_meca_importer import MedRxivMECAImporter

        importer = MedRxivMECAImporter(
            output_dir=Path(args.output_dir),
            aws_access_key=args.aws_access_key,
            aws_secret_key=args.aws_secret_key
        )

        packages = importer.list_packages(
            prefix=args.prefix,
            limit=args.limit,
            refresh=True
        )

        print(f"\nFound {len(packages)} MECA packages")
        print("-" * 70)

        total_size = 0
        for pkg in packages[:20]:  # Show first 20
            size_mb = pkg.size_bytes / 1024 / 1024
            total_size += pkg.size_bytes
            print(f"  {pkg.filename} ({size_mb:.1f} MB)")

        if len(packages) > 20:
            print(f"  ... and {len(packages) - 20} more")

        total_gb = total_size / 1024 / 1024 / 1024
        print("-" * 70)
        print(f"Total size: {total_gb:.2f} GB")
        print("=" * 70)

        return 0

    except Exception as e:
        logging.error(f"Error listing packages: {e}", exc_info=True)
        return 1


def cmd_download(args):
    """Download MECA packages."""
    if not check_boto3():
        return 1

    print("=" * 70)
    print("MedRxiv MECA Package Download")
    print("=" * 70)
    print(f"Output directory: {args.output_dir}")
    if args.limit:
        print(f"Limit: {args.limit}")
    print("=" * 70)

    try:
        from src.bmlibrarian.importers.medrxiv_meca_importer import MedRxivMECAImporter

        importer = MedRxivMECAImporter(
            output_dir=Path(args.output_dir),
            aws_access_key=args.aws_access_key,
            aws_secret_key=args.aws_secret_key,
            delay_between_downloads=args.delay
        )

        # List packages first
        importer.list_packages(prefix=args.prefix, limit=args.limit)

        # Download
        downloaded = importer.download_packages(
            limit=args.limit,
            progress_callback=lambda msg: print(f"  {msg}")
        )

        print("\n" + "=" * 70)
        print("Download Complete!")
        print("=" * 70)
        print(f"Packages downloaded: {downloaded}")
        print("=" * 70)

        return 0

    except Exception as e:
        logging.error(f"Error downloading packages: {e}", exc_info=True)
        return 1


def cmd_import(args):
    """Import downloaded packages to database."""
    print("=" * 70)
    print("MedRxiv MECA Package Import")
    print("=" * 70)
    print(f"MECA directory: {args.meca_dir}")
    print("=" * 70)

    try:
        from src.bmlibrarian.importers.medrxiv_meca_importer import MedRxivMECAImporter

        importer = MedRxivMECAImporter(output_dir=Path(args.meca_dir))

        imported = importer.import_to_database(
            limit=args.limit,
            progress_callback=lambda msg: print(f"  {msg}")
        )

        print("\n" + "=" * 70)
        print("Import Complete!")
        print("=" * 70)
        print(f"Articles imported: {imported}")
        print("=" * 70)

        return 0

    except Exception as e:
        logging.error(f"Error importing packages: {e}", exc_info=True)
        return 1


def cmd_sync(args):
    """Full sync workflow: download + import."""
    if not check_boto3():
        return 1

    print("=" * 70)
    print("MedRxiv MECA Full Sync")
    print("=" * 70)
    print(f"Output directory: {args.output_dir}")
    if args.limit:
        print(f"Limit: {args.limit}")
    print("=" * 70)

    try:
        from src.bmlibrarian.importers.medrxiv_meca_importer import MedRxivMECAImporter

        importer = MedRxivMECAImporter(
            output_dir=Path(args.output_dir),
            aws_access_key=args.aws_access_key,
            aws_secret_key=args.aws_secret_key,
            delay_between_downloads=args.delay
        )

        # List packages
        print("\nListing packages...")
        importer.list_packages(prefix=args.prefix, limit=args.limit)

        # Download
        print("\nDownloading packages...")
        downloaded = importer.download_packages(
            limit=args.limit,
            progress_callback=lambda msg: print(f"  {msg}")
        )

        # Import
        print("\nImporting to database...")
        imported = importer.import_to_database(
            progress_callback=lambda msg: print(f"  {msg}")
        )

        print("\n" + "=" * 70)
        print("Sync Complete!")
        print("=" * 70)
        print(f"Packages downloaded: {downloaded}")
        print(f"Articles imported: {imported}")
        print("=" * 70)

        return 0

    except Exception as e:
        logging.error(f"Error during sync: {e}", exc_info=True)
        return 1


def cmd_status(args):
    """Show import status."""
    print("=" * 70)
    print("MedRxiv MECA Import Status")
    print("=" * 70)

    try:
        from src.bmlibrarian.importers.medrxiv_meca_importer import MedRxivMECAImporter

        importer = MedRxivMECAImporter(output_dir=Path(args.meca_dir))
        status = importer.get_status()

        print(f"\nOutput directory: {status['output_dir']}")
        print(f"Total packages tracked: {status['total_packages']}")
        print("\nPackage status:")
        for status_name, count in status['status_counts'].items():
            if count > 0:
                print(f"  {status_name}: {count}")

        progress = status['progress']
        print(f"\nProgress:")
        print(f"  Downloaded: {progress['downloaded_packages']}")
        print(f"  Extracted: {progress['extracted_packages']}")
        print(f"  Imported: {progress['imported_packages']}")
        print(f"  Downloaded bytes: {progress['downloaded_bytes'] / 1024 / 1024:.1f} MB")

        if progress['errors']:
            print(f"\nErrors: {len(progress['errors'])}")
            for error in progress['errors'][:5]:
                print(f"  - {error}")
            if len(progress['errors']) > 5:
                print(f"  ... and {len(progress['errors']) - 5} more")

        print("=" * 70)

        return 0

    except Exception as e:
        logging.error(f"Error getting status: {e}", exc_info=True)
        return 1


def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description='Download and import medRxiv MECA packages from AWS S3',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to execute')

    # List command
    list_parser = subparsers.add_parser(
        'list',
        help='List available MECA packages in S3'
    )
    list_parser.add_argument(
        '--output-dir',
        type=str,
        default='~/medrxiv_meca',
        help='Output directory for state files (default: ~/medrxiv_meca)'
    )
    list_parser.add_argument(
        '--prefix',
        type=str,
        help='S3 key prefix to filter (e.g., "Current_Content/2024-01/")'
    )
    list_parser.add_argument(
        '--limit',
        type=int,
        help='Maximum number of packages to list'
    )
    list_parser.add_argument(
        '--aws-access-key',
        type=str,
        help='AWS access key (or use environment/credentials file)'
    )
    list_parser.add_argument(
        '--aws-secret-key',
        type=str,
        help='AWS secret key (or use environment/credentials file)'
    )

    # Download command
    download_parser = subparsers.add_parser(
        'download',
        help='Download MECA packages from S3'
    )
    download_parser.add_argument(
        '--output-dir',
        type=str,
        default='~/medrxiv_meca',
        help='Output directory for downloads (default: ~/medrxiv_meca)'
    )
    download_parser.add_argument(
        '--prefix',
        type=str,
        help='S3 key prefix to filter'
    )
    download_parser.add_argument(
        '--limit',
        type=int,
        help='Maximum number of packages to download'
    )
    download_parser.add_argument(
        '--delay',
        type=int,
        default=60,
        help='Delay between downloads in seconds (default: 60)'
    )
    download_parser.add_argument(
        '--aws-access-key',
        type=str,
        help='AWS access key'
    )
    download_parser.add_argument(
        '--aws-secret-key',
        type=str,
        help='AWS secret key'
    )

    # Import command
    import_parser = subparsers.add_parser(
        'import',
        help='Import downloaded packages to database'
    )
    import_parser.add_argument(
        '--meca-dir',
        type=str,
        default='~/medrxiv_meca',
        help='Directory containing downloaded MECA packages (default: ~/medrxiv_meca)'
    )
    import_parser.add_argument(
        '--limit',
        type=int,
        help='Maximum number of packages to import'
    )

    # Sync command
    sync_parser = subparsers.add_parser(
        'sync',
        help='Full sync: download + import'
    )
    sync_parser.add_argument(
        '--output-dir',
        type=str,
        default='~/medrxiv_meca',
        help='Output directory (default: ~/medrxiv_meca)'
    )
    sync_parser.add_argument(
        '--prefix',
        type=str,
        help='S3 key prefix to filter'
    )
    sync_parser.add_argument(
        '--limit',
        type=int,
        help='Maximum number of packages'
    )
    sync_parser.add_argument(
        '--delay',
        type=int,
        default=60,
        help='Delay between downloads in seconds (default: 60)'
    )
    sync_parser.add_argument(
        '--aws-access-key',
        type=str,
        help='AWS access key'
    )
    sync_parser.add_argument(
        '--aws-secret-key',
        type=str,
        help='AWS secret key'
    )

    # Status command
    status_parser = subparsers.add_parser(
        'status',
        help='Show import status'
    )
    status_parser.add_argument(
        '--meca-dir',
        type=str,
        default='~/medrxiv_meca',
        help='Directory containing MECA imports (default: ~/medrxiv_meca)'
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(args.verbose)

    # Execute command
    if args.command == 'list':
        return cmd_list(args)
    elif args.command == 'download':
        return cmd_download(args)
    elif args.command == 'import':
        return cmd_import(args)
    elif args.command == 'sync':
        return cmd_sync(args)
    elif args.command == 'status':
        return cmd_status(args)
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())
