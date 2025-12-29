#!/usr/bin/env python3
"""
Europe PMC PDF Bulk Download CLI for BMLibrarian

Command-line interface for downloading PDF files from Europe PMC Open Access
for offline access to biomedical literature.

Features:
- Resumable downloads with state persistence
- Download verification (archive integrity check)
- PDF extraction from packages
- Configurable rate limiting
- PMCID range filtering
- Year-based PDF organization

Usage:
    # List available PDF packages
    python europe_pmc_pdf_cli.py list --output-dir ~/europepmc_pdf

    # Download all PDF packages
    python europe_pmc_pdf_cli.py download --output-dir ~/europepmc_pdf

    # Download with limit and custom delay
    python europe_pmc_pdf_cli.py download --output-dir ~/europepmc_pdf --limit 10 --delay 120

    # Download specific PMCID range only
    python europe_pmc_pdf_cli.py download --output-dir ~/europepmc_pdf --range 1-1000000

    # Download without extracting PDFs
    python europe_pmc_pdf_cli.py download --output-dir ~/europepmc_pdf --no-extract

    # Show download status
    python europe_pmc_pdf_cli.py status --output-dir ~/europepmc_pdf

    # Verify downloaded files
    python europe_pmc_pdf_cli.py verify --output-dir ~/europepmc_pdf

    # Extract PDFs from downloaded packages
    python europe_pmc_pdf_cli.py extract --output-dir ~/europepmc_pdf

    # Estimate download time
    python europe_pmc_pdf_cli.py estimate --output-dir ~/europepmc_pdf

    # Find a specific PDF by PMCID
    python europe_pmc_pdf_cli.py find --output-dir ~/europepmc_pdf --pmcid PMC123456
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Tuple

# Import constants from the downloader module
from src.bmlibrarian.importers.europe_pmc_pdf_downloader import (
    DEFAULT_OUTPUT_DIR,
    DEFAULT_DELAY_SECONDS,
    DEFAULT_MAX_RETRIES,
    MIN_PMCID,
    MAX_PMCID,
)

# Logging configuration
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the CLI.

    Args:
        verbose: Enable debug logging if True
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format=LOG_FORMAT,
        datefmt=LOG_DATE_FORMAT
    )


def parse_range(range_str: str) -> Tuple[int, int]:
    """Parse a PMCID range string like '1-1000000'.

    Args:
        range_str: Range string in format 'start-end'

    Returns:
        Tuple of (start, end) PMCID values

    Raises:
        ValueError: If format is invalid or values are out of range
    """
    parts = range_str.split('-')
    if len(parts) != 2:
        raise ValueError(f"Invalid range format: {range_str}. Use 'start-end'")

    try:
        start = int(parts[0])
        end = int(parts[1])
    except ValueError as e:
        raise ValueError(f"Invalid PMCID values in range: {range_str}") from e

    # Validate range bounds
    if start < MIN_PMCID or end < MIN_PMCID:
        raise ValueError(
            f"PMCID values must be >= {MIN_PMCID}"
        )
    if start > MAX_PMCID or end > MAX_PMCID:
        raise ValueError(
            f"PMCID values must be <= {MAX_PMCID}"
        )

    return (start, end)


def cmd_list(args: argparse.Namespace) -> int:
    """Execute the list command.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0 for success)
    """
    from src.bmlibrarian.importers.europe_pmc_pdf_downloader import EuropePMCPDFDownloader
    import requests

    print("=" * 70)
    print("Europe PMC Open Access PDF Package Listing")
    print("=" * 70)

    pmcid_ranges = None
    if args.range:
        try:
            pmcid_ranges = [parse_range(args.range)]
        except ValueError as e:
            print(f"Error: {e}")
            return 1

    try:
        with EuropePMCPDFDownloader(
            output_dir=Path(args.output_dir),
            pmcid_ranges=pmcid_ranges
        ) as downloader:
            packages = downloader.list_available_packages(refresh=args.refresh)

            print(f"\nFound {len(packages)} PDF packages")
            print("-" * 70)

            # Show first 20 packages
            for pkg in packages[:20]:
                status = ""
                if pkg.extracted:
                    status = f"[EXTRACTED: {pkg.pdf_count} PDFs]"
                elif pkg.verified:
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
            extracted = sum(1 for p in packages if p.extracted)
            total_pdfs = sum(p.pdf_count for p in packages)
            total_size = sum(p.size_bytes for p in packages if p.size_bytes)

            print("-" * 70)
            print(f"Downloaded: {downloaded}/{len(packages)}")
            print(f"Verified: {verified}/{len(packages)}")
            print(f"Extracted: {extracted}/{len(packages)}")
            print(f"Total PDFs extracted: {total_pdfs}")
            if total_size:
                print(f"Total size (known): {downloader._format_bytes(total_size)}")
            print("=" * 70)

            return 0

    except ValueError as e:
        print(f"Configuration error: {e}")
        return 1
    except requests.exceptions.RequestException as e:
        logging.error(f"Network error: {e}")
        print(f"Network error while contacting Europe PMC. Please check your connection.")
        return 1
    except PermissionError as e:
        logging.error(f"Permission error: {e}")
        print(f"Permission denied. Check that you have write access to: {args.output_dir}")
        return 1
    except OSError as e:
        logging.error(f"File system error: {e}")
        print(f"File system error: {e}")
        return 1


def cmd_download(args: argparse.Namespace) -> int:
    """Execute the download command.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0 for success)
    """
    from src.bmlibrarian.importers.europe_pmc_pdf_downloader import EuropePMCPDFDownloader
    import requests

    print("=" * 70)
    print("Europe PMC PDF Bulk Download")
    print("=" * 70)
    print(f"Output directory: {args.output_dir}")
    if args.limit:
        print(f"Limit: {args.limit} packages")
    print(f"Delay between files: {args.delay} seconds")
    print(f"Extract PDFs: {not args.no_extract}")
    print("=" * 70)

    pmcid_ranges = None
    if args.range:
        try:
            pmcid_ranges = [parse_range(args.range)]
            print(f"PMCID range filter: {args.range}")
        except ValueError as e:
            print(f"Error: {e}")
            return 1

    try:
        with EuropePMCPDFDownloader(
            output_dir=Path(args.output_dir),
            pmcid_ranges=pmcid_ranges,
            delay_between_files=args.delay,
            max_retries=args.max_retries,
            extract_pdfs=not args.no_extract
        ) as downloader:
            # List packages first
            packages = downloader.list_available_packages()
            print(f"\nFound {len(packages)} PDF packages available")

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
            print(f"Total extracted: {status['packages']['extracted']}/{status['packages']['total']}")
            print(f"Total PDFs: {status['pdfs']['total']}")
            print(f"Bytes downloaded: {status['bytes']['downloaded_formatted']}")

            if status['errors']:
                print(f"Errors: {status['errors']}")

            print("=" * 70)

            return 0

    except KeyboardInterrupt:
        print("\n\nDownload interrupted by user. Progress has been saved.")
        print("Run the command again to resume downloading.")
        return 130

    except ValueError as e:
        print(f"Configuration error: {e}")
        return 1
    except requests.exceptions.RequestException as e:
        logging.error(f"Network error: {e}")
        print(f"Network error while contacting Europe PMC. Please check your connection.")
        return 1
    except PermissionError as e:
        logging.error(f"Permission error: {e}")
        print(f"Permission denied. Check that you have write access to: {args.output_dir}")
        return 1
    except OSError as e:
        logging.error(f"File system error: {e}")
        print(f"File system error: {e}")
        return 1


def cmd_status(args: argparse.Namespace) -> int:
    """Execute the status command.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0 for success)
    """
    from src.bmlibrarian.importers.europe_pmc_pdf_downloader import EuropePMCPDFDownloader

    print("=" * 70)
    print("Europe PMC PDF Download Status")
    print("=" * 70)

    try:
        with EuropePMCPDFDownloader(output_dir=Path(args.output_dir)) as downloader:
            status = downloader.get_status()

            print(f"\nOutput directory: {status['output_dir']}")
            print(f"PDF directory: {status['pdf_dir']}")

            print(f"\nPackages:")
            print(f"  Total: {status['packages']['total']}")
            print(f"  Downloaded: {status['packages']['downloaded']}")
            print(f"  Verified: {status['packages']['verified']}")
            print(f"  Extracted: {status['packages']['extracted']}")
            print(f"  Pending: {status['packages']['pending']}")

            print(f"\nPDFs:")
            print(f"  Total extracted: {status['pdfs']['total']}")

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

    except PermissionError as e:
        logging.error(f"Permission error: {e}")
        print(f"Permission denied. Check that you have access to: {args.output_dir}")
        return 1
    except OSError as e:
        logging.error(f"File system error: {e}")
        print(f"File system error: {e}")
        return 1


def cmd_verify(args: argparse.Namespace) -> int:
    """Execute the verify command.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0 for success)
    """
    from src.bmlibrarian.importers.europe_pmc_pdf_downloader import EuropePMCPDFDownloader

    print("=" * 70)
    print("Europe PMC PDF Download Verification")
    print("=" * 70)

    try:
        with EuropePMCPDFDownloader(output_dir=Path(args.output_dir)) as downloader:
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

    except PermissionError as e:
        logging.error(f"Permission error: {e}")
        print(f"Permission denied. Check that you have access to: {args.output_dir}")
        return 1
    except OSError as e:
        logging.error(f"File system error: {e}")
        print(f"File system error: {e}")
        return 1


def cmd_extract(args: argparse.Namespace) -> int:
    """Execute the extract command.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0 for success)
    """
    from src.bmlibrarian.importers.europe_pmc_pdf_downloader import EuropePMCPDFDownloader

    print("=" * 70)
    print("Europe PMC PDF Extraction")
    print("=" * 70)

    try:
        with EuropePMCPDFDownloader(output_dir=Path(args.output_dir)) as downloader:
            def progress_callback(filename: str, current: int, total: int) -> None:
                print(f"[{current}/{total}] Extracting {filename}...")

            results = downloader.extract_all_pdfs(
                limit=args.limit,
                progress_callback=progress_callback
            )

            print(f"\nExtraction Results:")
            print(f"  Packages processed: {results['extracted']}")
            print(f"  PDFs extracted: {results['total_pdfs']}")

            print("=" * 70)

            return 0

    except PermissionError as e:
        logging.error(f"Permission error: {e}")
        print(f"Permission denied. Check that you have write access to: {args.output_dir}")
        return 1
    except OSError as e:
        logging.error(f"File system error: {e}")
        print(f"File system error: {e}")
        return 1


def cmd_estimate(args: argparse.Namespace) -> int:
    """Execute the estimate command.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0 for success)
    """
    from src.bmlibrarian.importers.europe_pmc_pdf_downloader import EuropePMCPDFDownloader

    print("=" * 70)
    print("Europe PMC PDF Download Time Estimate")
    print("=" * 70)

    try:
        with EuropePMCPDFDownloader(output_dir=Path(args.output_dir)) as downloader:
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

    except PermissionError as e:
        logging.error(f"Permission error: {e}")
        print(f"Permission denied. Check that you have access to: {args.output_dir}")
        return 1
    except OSError as e:
        logging.error(f"File system error: {e}")
        print(f"File system error: {e}")
        return 1


def cmd_find(args: argparse.Namespace) -> int:
    """Execute the find command.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0 for success)
    """
    from src.bmlibrarian.importers.europe_pmc_pdf_downloader import EuropePMCPDFDownloader

    print("=" * 70)
    print("Europe PMC PDF Lookup")
    print("=" * 70)

    try:
        with EuropePMCPDFDownloader(output_dir=Path(args.output_dir)) as downloader:
            pdf_path = downloader.get_pdf_path(args.pmcid)

            print(f"\nLooking for: {args.pmcid}")

            if pdf_path:
                print(f"Found: {pdf_path}")
                print(f"Size: {downloader._format_bytes(pdf_path.stat().st_size)}")
            else:
                print("Not found in local storage.")
                print("\nThis PDF may need to be downloaded first.")

            print("=" * 70)

            return 0 if pdf_path else 1

    except ValueError as e:
        print(f"\nError: {e}")
        print(f"\nPMCID should be in format 'PMC123456' or '123456'")
        print(f"Valid range: {MIN_PMCID} to {MAX_PMCID}")
        print("=" * 70)
        return 1

    except PermissionError as e:
        logging.error(f"Permission error: {e}")
        print(f"Permission denied. Check that you have access to: {args.output_dir}")
        return 1
    except OSError as e:
        logging.error(f"File system error: {e}")
        print(f"File system error: {e}")
        return 1


def main() -> int:
    """Main entry point for the CLI.

    Returns:
        Exit code
    """
    parser = argparse.ArgumentParser(
        description='Download PDF files from Europe PMC Open Access',
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
        help='List available PDF packages from Europe PMC'
    )
    list_parser.add_argument(
        '--output-dir',
        type=str,
        default=DEFAULT_OUTPUT_DIR,
        help=f'Output directory (default: {DEFAULT_OUTPUT_DIR})'
    )
    list_parser.add_argument(
        '--range',
        type=str,
        help=f'PMCID range filter (e.g., "1-1000000", valid: {MIN_PMCID}-{MAX_PMCID})'
    )
    list_parser.add_argument(
        '--refresh',
        action='store_true',
        help='Force refresh package list from server'
    )

    # Download command
    download_parser = subparsers.add_parser(
        'download',
        help='Download PDF packages from Europe PMC'
    )
    download_parser.add_argument(
        '--output-dir',
        type=str,
        default=DEFAULT_OUTPUT_DIR,
        help=f'Output directory (default: {DEFAULT_OUTPUT_DIR})'
    )
    download_parser.add_argument(
        '--limit',
        type=int,
        help='Maximum number of packages to download'
    )
    download_parser.add_argument(
        '--delay',
        type=int,
        default=DEFAULT_DELAY_SECONDS,
        help=f'Delay between downloads in seconds (default: {DEFAULT_DELAY_SECONDS})'
    )
    download_parser.add_argument(
        '--range',
        type=str,
        help=f'PMCID range filter (e.g., "1-1000000", valid: {MIN_PMCID}-{MAX_PMCID})'
    )
    download_parser.add_argument(
        '--max-retries',
        type=int,
        default=DEFAULT_MAX_RETRIES,
        help=f'Maximum retry attempts per file (default: {DEFAULT_MAX_RETRIES})'
    )
    download_parser.add_argument(
        '--no-extract',
        action='store_true',
        help='Do not extract PDFs from packages after download'
    )

    # Status command
    status_parser = subparsers.add_parser(
        'status',
        help='Show download status'
    )
    status_parser.add_argument(
        '--output-dir',
        type=str,
        default=DEFAULT_OUTPUT_DIR,
        help=f'Output directory (default: {DEFAULT_OUTPUT_DIR})'
    )

    # Verify command
    verify_parser = subparsers.add_parser(
        'verify',
        help='Verify integrity of downloaded files'
    )
    verify_parser.add_argument(
        '--output-dir',
        type=str,
        default=DEFAULT_OUTPUT_DIR,
        help=f'Output directory (default: {DEFAULT_OUTPUT_DIR})'
    )

    # Extract command
    extract_parser = subparsers.add_parser(
        'extract',
        help='Extract PDFs from downloaded packages'
    )
    extract_parser.add_argument(
        '--output-dir',
        type=str,
        default=DEFAULT_OUTPUT_DIR,
        help=f'Output directory (default: {DEFAULT_OUTPUT_DIR})'
    )
    extract_parser.add_argument(
        '--limit',
        type=int,
        help='Maximum number of packages to process'
    )

    # Estimate command
    estimate_parser = subparsers.add_parser(
        'estimate',
        help='Estimate remaining download time'
    )
    estimate_parser.add_argument(
        '--output-dir',
        type=str,
        default=DEFAULT_OUTPUT_DIR,
        help=f'Output directory (default: {DEFAULT_OUTPUT_DIR})'
    )

    # Find command
    find_parser = subparsers.add_parser(
        'find',
        help='Find a specific PDF by PMCID'
    )
    find_parser.add_argument(
        '--output-dir',
        type=str,
        default=DEFAULT_OUTPUT_DIR,
        help=f'Output directory (default: {DEFAULT_OUTPUT_DIR})'
    )
    find_parser.add_argument(
        '--pmcid',
        type=str,
        required=True,
        help=f'PMCID to find (e.g., "PMC123456" or "123456", valid: {MIN_PMCID}-{MAX_PMCID})'
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
    elif args.command == 'extract':
        return cmd_extract(args)
    elif args.command == 'estimate':
        return cmd_estimate(args)
    elif args.command == 'find':
        return cmd_find(args)
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())
