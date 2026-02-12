#!/usr/bin/env python3
"""
Retraction Watch Import CLI

Imports retraction data from the Retraction Watch database CSV for offline
transparency analysis. Matches retracted papers to existing documents
in the database by DOI or PMID.

Usage:
    # Import retraction data from CSV
    python retraction_watch_cli.py import --file retraction_watch.csv

    # Import with limit
    python retraction_watch_cli.py import --file retraction_watch.csv --limit 5000

    # Look up retraction status for a DOI
    python retraction_watch_cli.py lookup --doi 10.1234/example

    # Look up by PMID
    python retraction_watch_cli.py lookup --pmid 12345678

    # Show import status
    python retraction_watch_cli.py status
"""

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.bmlibrarian.importers.retraction_watch_importer import RetractionWatchImporter


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


def cmd_import(args: argparse.Namespace) -> None:
    """Import retraction data from CSV.

    Args:
        args: Parsed command line arguments.
    """
    user_env_path = Path.home() / ".bmlibrarian" / ".env"
    if user_env_path.exists():
        load_dotenv(user_env_path)
    else:
        load_dotenv()

    importer = RetractionWatchImporter()
    csv_path = Path(args.file)

    print(f"\nImporting retraction data from {csv_path}...")

    stats = importer.import_csv(
        csv_path=csv_path,
        limit=args.limit,
        progress_callback=progress_printer,
    )

    matched = stats["matched_by_doi"] + stats["matched_by_pmid"]
    print(f"\n{'='*50}")
    print(f"Import Results:")
    print(f"  Total records:    {stats['total_rows']}")
    print(f"  Matched:          {matched}")
    print(f"    By DOI:         {stats['matched_by_doi']}")
    print(f"    By PMID:        {stats['matched_by_pmid']}")
    print(f"  Unmatched:        {stats['unmatched']}")
    print(f"  Errors:           {stats['errors']}")
    print(f"{'='*50}\n")


def cmd_lookup(args: argparse.Namespace) -> None:
    """Look up retraction status.

    Args:
        args: Parsed command line arguments.
    """
    user_env_path = Path.home() / ".bmlibrarian" / ".env"
    if user_env_path.exists():
        load_dotenv(user_env_path)
    else:
        load_dotenv()

    importer = RetractionWatchImporter()
    result = importer.lookup(doi=args.doi, pmid=args.pmid)

    if result:
        print(f"\n{'='*50}")
        print(f"RETRACTION FOUND")
        print(f"{'='*50}")
        print(f"Title: {result.get('title', 'Unknown')}")
        print(f"DOI: {result.get('doi', 'N/A')}")
        print(f"Retracted: {result.get('is_retracted', False)}")
        print(f"Reason: {result.get('retraction_reason', 'Not specified')}")
        print(f"Date: {result.get('retraction_date', 'Unknown')}")
        print(f"{'='*50}\n")
    else:
        identifier = args.doi or args.pmid or "unknown"
        print(f"\nNo retraction found for {identifier}")


def cmd_status(args: argparse.Namespace) -> None:
    """Show import status.

    Args:
        args: Parsed command line arguments.
    """
    user_env_path = Path.home() / ".bmlibrarian" / ".env"
    if user_env_path.exists():
        load_dotenv(user_env_path)
    else:
        load_dotenv()

    importer = RetractionWatchImporter()
    status = importer.get_status()

    print(f"\n{'='*50}")
    print(f"Retraction Watch Import Status")
    print(f"{'='*50}")
    if "error" in status:
        print(f"Error: {status['error']}")
    else:
        print(f"Retraction Watch records: {status.get('retraction_watch_records', 0)}")
        print(f"Total retracted documents: {status.get('total_retracted_documents', 0)}")
    print(f"{'='*50}\n")


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser.

    Returns:
        Configured ArgumentParser.
    """
    parser = argparse.ArgumentParser(
        description="Retraction Watch Import - Import retraction data for transparency analysis",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # import
    imp = subparsers.add_parser("import", help="Import retraction data from CSV")
    imp.add_argument("--file", type=str, required=True,
                      help="Path to Retraction Watch CSV file")
    imp.add_argument("--limit", type=int, default=0,
                      help="Maximum records to process (0 = unlimited)")

    # lookup
    lk = subparsers.add_parser("lookup", help="Look up retraction status")
    lk.add_argument("--doi", type=str, help="DOI to look up")
    lk.add_argument("--pmid", type=str, help="PMID to look up")

    # status
    subparsers.add_parser("status", help="Show import status")

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
        "import": cmd_import,
        "lookup": cmd_lookup,
        "status": cmd_status,
    }

    cmd_func = commands.get(args.command)
    if cmd_func:
        cmd_func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
