#!/usr/bin/env python3
"""
Europe PMC Bulk Download and Import CLI for BMLibrarian

Command-line interface for downloading and importing full-text XML articles
from Europe PMC Open Access for offline access.

Features:
- Resumable downloads with state persistence
- Download verification (gzip integrity check)
- Configurable rate limiting
- PMCID range filtering
- Database import with Markdown full-text conversion
- Figure/image reference handling

Usage:
    # List available packages
    python europe_pmc_bulk_cli.py list --output-dir ~/europepmc

    # Download all packages
    python europe_pmc_bulk_cli.py download --output-dir ~/europepmc

    # Download with limit and custom delay
    python europe_pmc_bulk_cli.py download --output-dir ~/europepmc --limit 10 --delay 120

    # Download specific PMCID range only
    python europe_pmc_bulk_cli.py download --output-dir ~/europepmc --range 1-1000000

    # Show download status
    python europe_pmc_bulk_cli.py status --output-dir ~/europepmc

    # Verify downloaded files
    python europe_pmc_bulk_cli.py verify --output-dir ~/europepmc

    # Estimate download time
    python europe_pmc_bulk_cli.py estimate --output-dir ~/europepmc

    # Import downloaded packages to database
    python europe_pmc_bulk_cli.py import --output-dir ~/europepmc

    # Import with limit
    python europe_pmc_bulk_cli.py import --output-dir ~/europepmc --limit 5

    # Show import status
    python europe_pmc_bulk_cli.py import-status --output-dir ~/europepmc

    # Verify a specific package can be parsed
    python europe_pmc_bulk_cli.py verify-import --output-dir ~/europepmc --package PMC13900_PMC17829.xml.gz
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional, List, Tuple


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the CLI.

    Args:
        verbose: Enable debug logging if True
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def parse_range(range_str: str) -> Tuple[int, int]:
    """Parse a PMCID range string like '1-1000000'.

    Args:
        range_str: Range string in format 'start-end'

    Returns:
        Tuple of (start, end) PMCID values
    """
    parts = range_str.split('-')
    if len(parts) != 2:
        raise ValueError(f"Invalid range format: {range_str}. Use 'start-end'")
    return (int(parts[0]), int(parts[1]))


def cmd_list(args: argparse.Namespace) -> int:
    """Execute the list command.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0 for success)
    """
    from src.bmlibrarian.importers.europe_pmc_bulk_downloader import EuropePMCBulkDownloader

    print("=" * 70)
    print("Europe PMC Open Access Package Listing")
    print("=" * 70)

    pmcid_ranges = None
    if args.range:
        pmcid_ranges = [parse_range(args.range)]

    try:
        downloader = EuropePMCBulkDownloader(
            output_dir=Path(args.output_dir),
            pmcid_ranges=pmcid_ranges
        )

        packages = downloader.list_available_packages(refresh=args.refresh)

        print(f"\nFound {len(packages)} packages")
        print("-" * 70)

        # Show first 20 packages
        for pkg in packages[:20]:
            status = ""
            if pkg.verified:
                status = "[VERIFIED]"
            elif pkg.downloaded:
                status = "[DOWNLOADED]"
            else:
                status = "[PENDING]"

            size_str = f"({downloader._format_bytes(pkg.size_bytes)})" if pkg.size_bytes else ""
            print(f"  {pkg.filename} {size_str} {status}")

        if len(packages) > 20:
            print(f"  ... and {len(packages) - 20} more")

        # Summary
        downloaded = sum(1 for p in packages if p.downloaded)
        verified = sum(1 for p in packages if p.verified)
        total_size = sum(p.size_bytes for p in packages if p.size_bytes)

        print("-" * 70)
        print(f"Downloaded: {downloaded}/{len(packages)}")
        print(f"Verified: {verified}/{len(packages)}")
        if total_size:
            print(f"Total size (known): {downloader._format_bytes(total_size)}")
        print("=" * 70)

        return 0

    except Exception as e:
        logging.error(f"Error listing packages: {e}", exc_info=True)
        return 1


def cmd_download(args: argparse.Namespace) -> int:
    """Execute the download command.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0 for success)
    """
    from src.bmlibrarian.importers.europe_pmc_bulk_downloader import EuropePMCBulkDownloader

    print("=" * 70)
    print("Europe PMC Bulk Download")
    print("=" * 70)
    print(f"Output directory: {args.output_dir}")
    if args.limit:
        print(f"Limit: {args.limit} packages")
    print(f"Delay between files: {args.delay} seconds")
    print("=" * 70)

    pmcid_ranges = None
    if args.range:
        pmcid_ranges = [parse_range(args.range)]
        print(f"PMCID range filter: {args.range}")

    try:
        downloader = EuropePMCBulkDownloader(
            output_dir=Path(args.output_dir),
            pmcid_ranges=pmcid_ranges,
            delay_between_files=args.delay,
            max_retries=args.max_retries
        )

        # List packages first
        packages = downloader.list_available_packages()
        print(f"\nFound {len(packages)} packages available")

        # Download with progress callback
        def progress_callback(filename: str, current: int, total: int) -> None:
            print(f"\n[{current}/{total}] Downloading {filename}...")

        downloaded = downloader.download_packages(
            limit=args.limit,
            progress_callback=progress_callback
        )

        print("\n" + "=" * 70)
        print("Download Complete!")
        print("=" * 70)
        print(f"Packages downloaded and verified: {downloaded}")

        status = downloader.get_status()
        print(f"Total downloaded: {status['packages']['downloaded']}/{status['packages']['total']}")
        print(f"Total verified: {status['packages']['verified']}/{status['packages']['total']}")
        print(f"Bytes downloaded: {status['bytes']['downloaded_formatted']}")

        if status['errors']:
            print(f"Errors: {status['errors']}")

        print("=" * 70)

        return 0

    except KeyboardInterrupt:
        print("\n\nDownload interrupted by user. Progress has been saved.")
        print("Run the command again to resume downloading.")
        return 130

    except Exception as e:
        logging.error(f"Error during download: {e}", exc_info=True)
        return 1


def cmd_status(args: argparse.Namespace) -> int:
    """Execute the status command.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0 for success)
    """
    from src.bmlibrarian.importers.europe_pmc_bulk_downloader import EuropePMCBulkDownloader

    print("=" * 70)
    print("Europe PMC Download Status")
    print("=" * 70)

    try:
        downloader = EuropePMCBulkDownloader(output_dir=Path(args.output_dir))
        status = downloader.get_status()

        print(f"\nOutput directory: {status['output_dir']}")
        print(f"\nPackages:")
        print(f"  Total: {status['packages']['total']}")
        print(f"  Downloaded: {status['packages']['downloaded']}")
        print(f"  Verified: {status['packages']['verified']}")
        print(f"  Pending: {status['packages']['pending']}")

        print(f"\nBytes:")
        print(f"  Downloaded: {status['bytes']['downloaded_formatted']}")

        if status['start_time']:
            print(f"\nStarted: {status['start_time']}")
        if status['last_update']:
            print(f"Last update: {status['last_update']}")

        if status['errors']:
            print(f"\nErrors: {status['errors']}")
            print("Recent errors:")
            for error in status['recent_errors']:
                print(f"  - {error}")

        print("=" * 70)

        return 0

    except Exception as e:
        logging.error(f"Error getting status: {e}", exc_info=True)
        return 1


def cmd_verify(args: argparse.Namespace) -> int:
    """Execute the verify command.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0 for success)
    """
    from src.bmlibrarian.importers.europe_pmc_bulk_downloader import EuropePMCBulkDownloader

    print("=" * 70)
    print("Europe PMC Download Verification")
    print("=" * 70)

    try:
        downloader = EuropePMCBulkDownloader(output_dir=Path(args.output_dir))
        results = downloader.verify_all_downloads()

        print(f"\nVerification Results:")
        print(f"  Verified: {results['verified']}")
        print(f"  Failed: {results['failed']}")
        print(f"  Missing: {results['missing']}")

        if results['failed_files']:
            print(f"\nFailed files:")
            for filename in results['failed_files'][:10]:
                print(f"  - {filename}")
            if len(results['failed_files']) > 10:
                print(f"  ... and {len(results['failed_files']) - 10} more")

        print("=" * 70)

        return 0 if results['failed'] == 0 else 1

    except Exception as e:
        logging.error(f"Error during verification: {e}", exc_info=True)
        return 1


def cmd_estimate(args: argparse.Namespace) -> int:
    """Execute the estimate command.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0 for success)
    """
    from src.bmlibrarian.importers.europe_pmc_bulk_downloader import EuropePMCBulkDownloader

    print("=" * 70)
    print("Europe PMC Download Time Estimate")
    print("=" * 70)

    try:
        downloader = EuropePMCBulkDownloader(output_dir=Path(args.output_dir))
        estimate = downloader.estimate_download_time()

        if not estimate['estimated']:
            print(f"\n{estimate['message']}")
            print("\nStart downloading to get time estimates.")
        else:
            print(f"\nElapsed time: {estimate['elapsed_formatted']}")
            print(f"Remaining packages: {estimate['remaining_packages']}")
            print(f"Download rate: {estimate['packages_per_hour']:.1f} packages/hour")
            print(f"Estimated remaining time: {estimate['remaining_formatted']}")

        print("=" * 70)

        return 0

    except Exception as e:
        logging.error(f"Error estimating time: {e}", exc_info=True)
        return 1


def cmd_import(args: argparse.Namespace) -> int:
    """Execute the import command.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0 for success)
    """
    from src.bmlibrarian.importers.europe_pmc_importer import EuropePMCImporter

    print("=" * 70)
    print("Europe PMC Database Import")
    print("=" * 70)

    output_dir = Path(args.output_dir).expanduser()
    packages_dir = output_dir / 'packages'

    print(f"Packages directory: {packages_dir}")
    if args.limit:
        print(f"Limit: {args.limit} packages")
    print("=" * 70)

    try:
        importer = EuropePMCImporter(
            packages_dir=packages_dir,
            batch_size=args.batch_size,
            update_existing=not args.no_update
        )

        packages = importer.list_packages()
        print(f"\nFound {len(packages)} packages to import")

        if not packages:
            print("No packages found. Run 'download' command first.")
            return 1

        # Import with progress callback
        def progress_callback(
            package_name: str,
            pkg_num: int,
            total_pkgs: int,
            articles_imported: int
        ) -> None:
            print(f"\n[{pkg_num}/{total_pkgs}] Importing {package_name}...")
            print(f"  Total articles imported so far: {articles_imported}")

        result = importer.import_all_packages(
            progress_callback=progress_callback,
            limit=args.limit
        )

        print("\n" + "=" * 70)
        print("Import Complete!")
        print("=" * 70)
        print(f"Packages processed: {result['imported_packages']}/{result['total_packages']}")
        print(f"Articles inserted: {result['imported_articles']}")
        print(f"Articles updated: {result['updated_articles']}")
        print(f"Articles skipped: {result['skipped_articles']}")
        print(f"Articles failed: {result['failed_articles']}")

        if result['errors']:
            print(f"\nErrors: {result['errors']}")
            print("Recent errors:")
            for error in result['recent_errors']:
                print(f"  - {error}")

        print("=" * 70)

        return 0

    except KeyboardInterrupt:
        print("\n\nImport interrupted by user. Progress has been saved.")
        print("Run the command again to resume importing.")
        return 130

    except Exception as e:
        logging.error(f"Error during import: {e}", exc_info=True)
        return 1


def cmd_import_status(args: argparse.Namespace) -> int:
    """Execute the import-status command.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0 for success)
    """
    from src.bmlibrarian.importers.europe_pmc_importer import EuropePMCImporter

    print("=" * 70)
    print("Europe PMC Import Status")
    print("=" * 70)

    output_dir = Path(args.output_dir).expanduser()
    packages_dir = output_dir / 'packages'

    try:
        importer = EuropePMCImporter(packages_dir=packages_dir)
        status = importer.get_status()

        print(f"\nPackages directory: {status['packages_dir']}")
        print(f"\nPackages:")
        print(f"  Total available: {status['total_packages']}")
        print(f"  Imported: {status['imported_packages']}")

        print(f"\nArticles:")
        print(f"  Total processed: {status['total_articles']}")
        print(f"  Inserted: {status['imported_articles']}")
        print(f"  Updated: {status['updated_articles']}")
        print(f"  Skipped: {status['skipped_articles']}")
        print(f"  Failed: {status['failed_articles']}")

        if status['start_time']:
            print(f"\nStarted: {status['start_time']}")
        if status['last_update']:
            print(f"Last update: {status['last_update']}")

        if status['errors']:
            print(f"\nErrors: {status['errors']}")
            print("Recent errors:")
            for error in status['recent_errors']:
                print(f"  - {error}")

        print("=" * 70)

        return 0

    except Exception as e:
        logging.error(f"Error getting import status: {e}", exc_info=True)
        return 1


def cmd_verify_import(args: argparse.Namespace) -> int:
    """Execute the verify-import command.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0 for success)
    """
    from src.bmlibrarian.importers.europe_pmc_importer import EuropePMCImporter

    print("=" * 70)
    print("Europe PMC Package Verification")
    print("=" * 70)

    output_dir = Path(args.output_dir).expanduser()
    packages_dir = output_dir / 'packages'
    package_path = packages_dir / args.package

    if not package_path.exists():
        print(f"Package not found: {package_path}")
        return 1

    try:
        importer = EuropePMCImporter(packages_dir=packages_dir)
        result = importer.verify_package(package_path)

        print(f"\nPackage: {result['package']}")
        print(f"Valid: {result['valid']}")

        if result['valid']:
            print(f"Article count: {result['article_count']}")

            if result['sample_articles']:
                print(f"\nSample articles:")
                for article in result['sample_articles']:
                    print(f"\n  PMCID: {article['pmcid']}")
                    print(f"  DOI: {article['doi']}")
                    if article['title']:
                        print(f"  Title: {article['title'][:60]}...")
                    print(f"  Has full text: {article['has_fulltext']}")
                    print(f"  Full text length: {article['fulltext_length']:,} chars")
                    print(f"  Figures: {article['figures_count']}")
        else:
            print(f"Error: {result['error']}")

        print("=" * 70)

        return 0 if result['valid'] else 1

    except Exception as e:
        logging.error(f"Error verifying package: {e}", exc_info=True)
        return 1


def main() -> int:
    """Main entry point for the CLI.

    Returns:
        Exit code
    """
    parser = argparse.ArgumentParser(
        description='Download full-text XML from Europe PMC Open Access',
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
        help='List available packages from Europe PMC'
    )
    list_parser.add_argument(
        '--output-dir',
        type=str,
        default='~/europepmc',
        help='Output directory (default: ~/europepmc)'
    )
    list_parser.add_argument(
        '--range',
        type=str,
        help='PMCID range filter (e.g., "1-1000000")'
    )
    list_parser.add_argument(
        '--refresh',
        action='store_true',
        help='Force refresh package list from server'
    )

    # Download command
    download_parser = subparsers.add_parser(
        'download',
        help='Download packages from Europe PMC'
    )
    download_parser.add_argument(
        '--output-dir',
        type=str,
        default='~/europepmc',
        help='Output directory (default: ~/europepmc)'
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
        '--range',
        type=str,
        help='PMCID range filter (e.g., "1-1000000")'
    )
    download_parser.add_argument(
        '--max-retries',
        type=int,
        default=3,
        help='Maximum retry attempts per file (default: 3)'
    )

    # Status command
    status_parser = subparsers.add_parser(
        'status',
        help='Show download status'
    )
    status_parser.add_argument(
        '--output-dir',
        type=str,
        default='~/europepmc',
        help='Output directory (default: ~/europepmc)'
    )

    # Verify command
    verify_parser = subparsers.add_parser(
        'verify',
        help='Verify integrity of downloaded files'
    )
    verify_parser.add_argument(
        '--output-dir',
        type=str,
        default='~/europepmc',
        help='Output directory (default: ~/europepmc)'
    )

    # Estimate command
    estimate_parser = subparsers.add_parser(
        'estimate',
        help='Estimate remaining download time'
    )
    estimate_parser.add_argument(
        '--output-dir',
        type=str,
        default='~/europepmc',
        help='Output directory (default: ~/europepmc)'
    )

    # Import command
    import_parser = subparsers.add_parser(
        'import',
        help='Import downloaded packages to database'
    )
    import_parser.add_argument(
        '--output-dir',
        type=str,
        default='~/europepmc',
        help='Output directory containing packages/ subdirectory (default: ~/europepmc)'
    )
    import_parser.add_argument(
        '--limit',
        type=int,
        help='Maximum number of packages to import'
    )
    import_parser.add_argument(
        '--batch-size',
        type=int,
        default=100,
        help='Number of articles per database commit (default: 100)'
    )
    import_parser.add_argument(
        '--no-update',
        action='store_true',
        help='Skip updating existing records (only insert new)'
    )

    # Import status command
    import_status_parser = subparsers.add_parser(
        'import-status',
        help='Show import progress and statistics'
    )
    import_status_parser.add_argument(
        '--output-dir',
        type=str,
        default='~/europepmc',
        help='Output directory (default: ~/europepmc)'
    )

    # Verify import command
    verify_import_parser = subparsers.add_parser(
        'verify-import',
        help='Verify a package can be parsed correctly'
    )
    verify_import_parser.add_argument(
        '--output-dir',
        type=str,
        default='~/europepmc',
        help='Output directory (default: ~/europepmc)'
    )
    verify_import_parser.add_argument(
        '--package',
        type=str,
        required=True,
        help='Package filename to verify (e.g., PMC13900_PMC17829.xml.gz)'
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(args.verbose)

    # Execute command
    if args.command == 'list':
        return cmd_list(args)
    elif args.command == 'download':
        return cmd_download(args)
    elif args.command == 'status':
        return cmd_status(args)
    elif args.command == 'verify':
        return cmd_verify(args)
    elif args.command == 'estimate':
        return cmd_estimate(args)
    elif args.command == 'import':
        return cmd_import(args)
    elif args.command == 'import-status':
        return cmd_import_status(args)
    elif args.command == 'verify-import':
        return cmd_verify_import(args)
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())
