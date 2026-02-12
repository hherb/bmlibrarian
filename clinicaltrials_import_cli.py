#!/usr/bin/env python3
"""
ClinicalTrials.gov Bulk Import CLI

Downloads and imports clinical trial metadata from ClinicalTrials.gov
for offline transparency analysis.

Usage:
    # Download bulk data (~10GB)
    python clinicaltrials_import_cli.py download --output-dir ~/clinicaltrials

    # Import trials and match to documents
    python clinicaltrials_import_cli.py import --input-dir ~/clinicaltrials

    # Import with limit
    python clinicaltrials_import_cli.py import --input-dir ~/clinicaltrials --limit 10000

    # Show import status
    python clinicaltrials_import_cli.py status
"""

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.bmlibrarian.importers.clinicaltrials_importer import ClinicalTrialsBulkImporter


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the CLI.

    Args:
        verbose: Enable debug-level logging.
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def progress_printer(message: str) -> None:
    """Print progress messages to stdout.

    Args:
        message: Progress message to display.
    """
    print(f"  {message}")


def cmd_download(args: argparse.Namespace) -> None:
    """Download ClinicalTrials.gov bulk data.

    Args:
        args: Parsed command line arguments.
    """
    importer = ClinicalTrialsBulkImporter(data_dir=Path(args.output_dir))
    print(f"\nDownloading ClinicalTrials.gov bulk data to {args.output_dir}...")
    print("Note: This file is approximately 10GB. Download may take a while.\n")

    zip_path = importer.download(progress_callback=progress_printer)
    print(f"\nDownload complete: {zip_path}")


def cmd_import(args: argparse.Namespace) -> None:
    """Import clinical trials from downloaded data.

    Args:
        args: Parsed command line arguments.
    """
    # Load environment for database connection
    user_env_path = Path.home() / ".bmlibrarian" / ".env"
    if user_env_path.exists():
        load_dotenv(user_env_path)
    else:
        load_dotenv()

    importer = ClinicalTrialsBulkImporter(data_dir=Path(args.input_dir))
    print(f"\nImporting clinical trials from {args.input_dir}...")

    stats = importer.import_trials(
        limit=args.limit,
        progress_callback=progress_printer,
    )

    print(f"\n{'='*50}")
    print(f"Import Results:")
    print(f"  Parsed:  {stats['parsed']}")
    print(f"  Stored:  {stats['stored']}")
    print(f"  Errors:  {stats['errors']}")
    print(f"  Skipped: {stats['skipped']}")
    print(f"{'='*50}\n")


def cmd_status(args: argparse.Namespace) -> None:
    """Show import status.

    Args:
        args: Parsed command line arguments.
    """
    # Load environment for database connection
    user_env_path = Path.home() / ".bmlibrarian" / ".env"
    if user_env_path.exists():
        load_dotenv(user_env_path)
    else:
        load_dotenv()

    importer = ClinicalTrialsBulkImporter(
        data_dir=Path(args.data_dir) if args.data_dir else None
    )
    status = importer.get_status()

    print(f"\n{'='*50}")
    print(f"ClinicalTrials.gov Import Status")
    print(f"{'='*50}")
    print(f"Data directory: {status.get('data_dir', 'N/A')}")
    print(f"ZIP file exists: {status.get('zip_exists', False)}")
    if status.get("zip_exists"):
        print(f"ZIP file size: {status.get('zip_size_gb', 0):.1f} GB")
    if "matched_documents" in status:
        print(f"Matched documents: {status['matched_documents']}")
    if "sponsor_distribution" in status:
        print(f"\nSponsor distribution:")
        for cls, count in status["sponsor_distribution"].items():
            print(f"  {cls}: {count}")
    if "db_error" in status:
        print(f"Database error: {status['db_error']}")
    print(f"{'='*50}\n")


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser.

    Returns:
        Configured ArgumentParser.
    """
    parser = argparse.ArgumentParser(
        description="ClinicalTrials.gov Bulk Import - Download and import trial metadata",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # download
    dl = subparsers.add_parser("download", help="Download bulk data")
    dl.add_argument("--output-dir", type=str, default="~/clinicaltrials",
                     help="Directory for downloaded data (default: ~/clinicaltrials)")

    # import
    imp = subparsers.add_parser("import", help="Import trials from downloaded data")
    imp.add_argument("--input-dir", type=str, default="~/clinicaltrials",
                      help="Directory with downloaded data")
    imp.add_argument("--limit", type=int, default=0,
                      help="Maximum trials to process (0 = unlimited)")

    # status
    st = subparsers.add_parser("status", help="Show import status")
    st.add_argument("--data-dir", type=str, help="Data directory to check")

    return parser


def main() -> None:
    """Main entry point for the CLI."""
    parser = build_parser()
    args = parser.parse_args()

    setup_logging(getattr(args, "verbose", False))

    if not args.command:
        parser.print_help()
        sys.exit(0)

    commands = {
        "download": cmd_download,
        "import": cmd_import,
        "status": cmd_status,
    }

    cmd_func = commands.get(args.command)
    if cmd_func:
        cmd_func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
