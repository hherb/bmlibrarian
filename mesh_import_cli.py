#!/usr/bin/env python3
"""
MeSH Import CLI - Download and import MeSH vocabulary into BMLibrarian.

This CLI tool downloads MeSH XML files from NLM and imports them into the
local PostgreSQL database for fast lookup and term expansion.

Usage:
    # Download and import MeSH 2025 (descriptors, qualifiers, and SCRs)
    uv run python mesh_import_cli.py import --year 2025

    # Import without supplementary concepts (faster, smaller)
    uv run python mesh_import_cli.py import --year 2025 --no-supplementary

    # Show current database statistics
    uv run python mesh_import_cli.py status

    # Show import history
    uv run python mesh_import_cli.py history

    # Look up a MeSH term
    uv run python mesh_import_cli.py lookup "heart attack"

    # Search MeSH
    uv run python mesh_import_cli.py search "cardio" --limit 20
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Set up logging before imports
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def get_current_mesh_year() -> int:
    """Get the current MeSH year (typically previous year until mid-year)."""
    now = datetime.now()
    # MeSH is typically released in November/December for the next year
    # But we should default to the current year
    return now.year


def format_size(size_bytes: int) -> str:
    """Format byte size for display."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def format_duration(seconds: float) -> str:
    """Format duration for display."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"


def cmd_import(args: argparse.Namespace) -> int:
    """Import MeSH vocabulary from NLM."""
    from bmlibrarian.importers.mesh_importer import MeSHImporter

    year = args.year or get_current_mesh_year()
    include_supplementary = not args.no_supplementary

    print(f"\nMeSH {year} Import")
    print("=" * 50)
    print(f"Year: {year}")
    print(f"Include supplementary concepts: {include_supplementary}")
    print(f"Download directory: {args.download_dir or 'default'}")
    print()

    if not args.yes:
        confirm = input("Proceed with import? [y/N]: ").strip().lower()
        if confirm != "y":
            print("Import cancelled.")
            return 1

    try:
        download_dir = Path(args.download_dir) if args.download_dir else None
        importer = MeSHImporter(
            download_dir=download_dir,
            keep_downloads=not args.delete_downloads,
        )

        def progress_callback(phase: str, processed: int, total: int) -> None:
            if total > 0:
                pct = (processed / total) * 100
                print(f"\r{phase}: {processed:,}/{total:,} ({pct:.1f}%)    ", end="", flush=True)
            else:
                print(f"\r{phase}: {processed:,}    ", end="", flush=True)

        print("Starting import...")
        stats = importer.import_mesh(
            year=year,
            include_supplementary=include_supplementary,
            progress_callback=progress_callback,
        )
        print()  # New line after progress

        print("\nImport Complete!")
        print("-" * 50)
        print(f"Descriptors: {stats.descriptors:,}")
        print(f"Concepts: {stats.concepts:,}")
        print(f"Terms: {stats.terms:,}")
        print(f"Tree numbers: {stats.tree_numbers:,}")
        print(f"Qualifiers: {stats.qualifiers:,}")
        print(f"Supplementary concepts: {stats.supplementary_concepts:,}")
        print(f"Duration: {format_duration(stats.duration_seconds or 0)}")
        print(f"Status: {stats.status}")

        return 0

    except Exception as e:
        logger.error(f"Import failed: {e}")
        return 1


def cmd_status(args: argparse.Namespace) -> int:
    """Show MeSH database statistics."""
    from bmlibrarian.mesh import MeSHService

    print("\nMeSH Database Status")
    print("=" * 50)

    try:
        service = MeSHService()
        stats = service.get_statistics()

        print(f"Local database available: {stats.get('local_db_available', False)}")
        print(f"API fallback enabled: {stats.get('api_fallback_enabled', True)}")
        print()

        if stats.get("local_db_available"):
            print("Local Database Contents:")
            print("-" * 30)
            print(f"  Descriptors: {stats.get('local_descriptors', 0):,}")
            print(f"  Concepts: {stats.get('local_concepts', 0):,}")
            print(f"  Terms: {stats.get('local_terms', 0):,}")
            print(f"  Tree numbers: {stats.get('local_tree_numbers', 0):,}")
            print(f"  Qualifiers: {stats.get('local_qualifiers', 0):,}")
            print(f"  Supplementary concepts: {stats.get('local_supplementary_concepts', 0):,}")
        else:
            print("Local database not available or empty.")
            print("Run 'mesh_import_cli.py import' to import MeSH data.")

        print()
        print("API Cache:")
        print("-" * 30)
        print(f"  Cache entries: {stats.get('cache_entries', 0):,}")
        print(f"  Cache TTL: {stats.get('cache_ttl_days', 30)} days")
        print(f"  Cache path: {stats.get('cache_path', 'N/A')}")

        return 0

    except Exception as e:
        logger.error(f"Could not get status: {e}")
        return 1


def cmd_history(args: argparse.Namespace) -> int:
    """Show import history."""
    from bmlibrarian.importers.mesh_importer import MeSHImporter

    print("\nMeSH Import History")
    print("=" * 50)

    try:
        importer = MeSHImporter()
        history = importer.get_import_history()

        if not history:
            print("No import history found.")
            return 0

        for i, record in enumerate(history[:args.limit]):
            print(f"\n[{i + 1}] Import #{record['id']}")
            print("-" * 30)
            print(f"  Year: {record['mesh_year']}")
            print(f"  Type: {record['import_type']}")
            print(f"  Status: {record['status']}")
            print(f"  Started: {record['started_at']}")
            if record.get("completed_at"):
                print(f"  Completed: {record['completed_at']}")
            print(f"  Descriptors: {record['descriptors']:,}")
            print(f"  Concepts: {record['concepts']:,}")
            print(f"  Terms: {record['terms']:,}")
            print(f"  Qualifiers: {record['qualifiers']:,}")
            print(f"  SCRs: {record['scrs']:,}")
            if record.get("error_message"):
                print(f"  Error: {record['error_message']}")

        return 0

    except Exception as e:
        logger.error(f"Could not get history: {e}")
        return 1


def cmd_lookup(args: argparse.Namespace) -> int:
    """Look up a MeSH term."""
    from bmlibrarian.mesh import MeSHService

    term = " ".join(args.term)
    print(f"\nLooking up: '{term}'")
    print("=" * 50)

    try:
        service = MeSHService()
        result = service.lookup(term)

        if result.found:
            print(f"Found: Yes")
            print(f"Source: {result.source.value}")
            print(f"Descriptor UI: {result.descriptor_ui}")
            print(f"Descriptor Name: {result.descriptor_name}")

            if result.scope_note:
                print(f"\nScope Note:")
                # Word wrap at 70 chars
                words = result.scope_note.split()
                line = "  "
                for word in words:
                    if len(line) + len(word) + 1 > 70:
                        print(line)
                        line = "  "
                    line += word + " "
                if line.strip():
                    print(line)

            if result.tree_numbers:
                print(f"\nTree Numbers ({len(result.tree_numbers)}):")
                for tn in result.tree_numbers[:10]:
                    print(f"  {tn}")
                if len(result.tree_numbers) > 10:
                    print(f"  ... and {len(result.tree_numbers) - 10} more")

            if result.entry_terms:
                print(f"\nEntry Terms ({len(result.entry_terms)}):")
                for et in result.entry_terms[:20]:
                    print(f"  {et}")
                if len(result.entry_terms) > 20:
                    print(f"  ... and {len(result.entry_terms) - 20} more")

            print(f"\nPubMed Syntax: {result.to_pubmed_syntax()}")
        else:
            print(f"Found: No")
            print(f"The term '{term}' was not found in MeSH.")

        return 0

    except Exception as e:
        logger.error(f"Lookup failed: {e}")
        return 1


def cmd_search(args: argparse.Namespace) -> int:
    """Search MeSH by partial match."""
    from bmlibrarian.mesh import MeSHService

    query = " ".join(args.query)
    print(f"\nSearching MeSH for: '{query}'")
    print("=" * 50)

    try:
        service = MeSHService()
        results = service.search(query, limit=args.limit)

        if not results:
            print("No results found.")
            return 0

        print(f"Found {len(results)} result(s):\n")

        for i, result in enumerate(results):
            print(f"[{i + 1}] {result.descriptor_name}")
            print(f"    UI: {result.descriptor_ui}")
            print(f"    Matched: '{result.matched_term}'")
            print(f"    Match type: {result.match_type}")
            if result.score > 0:
                print(f"    Score: {result.score:.4f}")
            print()

        return 0

    except Exception as e:
        logger.error(f"Search failed: {e}")
        return 1


def cmd_expand(args: argparse.Namespace) -> int:
    """Expand a MeSH term to all synonyms."""
    from bmlibrarian.mesh import MeSHService

    term = " ".join(args.term)
    print(f"\nExpanding: '{term}'")
    print("=" * 50)

    try:
        service = MeSHService()
        terms = service.expand(term)

        if len(terms) <= 1:
            print(f"No expansion found for '{term}'.")
            return 0

        print(f"Found {len(terms)} terms:\n")
        for t in terms:
            if t.lower() == term.lower():
                print(f"  * {t}  (searched term)")
            else:
                print(f"    {t}")

        return 0

    except Exception as e:
        logger.error(f"Expansion failed: {e}")
        return 1


def cmd_clear_cache(args: argparse.Namespace) -> int:
    """Clear the MeSH API cache."""
    from bmlibrarian.mesh import MeSHService

    if not args.yes:
        confirm = input("Clear MeSH API cache? [y/N]: ").strip().lower()
        if confirm != "y":
            print("Cancelled.")
            return 1

    try:
        service = MeSHService()
        count = service.clear_cache()
        print(f"Cleared {count} cache entries.")
        return 0

    except Exception as e:
        logger.error(f"Clear cache failed: {e}")
        return 1


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="MeSH Import CLI - Download and import MeSH vocabulary into BMLibrarian",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s import --year 2025        Download and import MeSH 2025
  %(prog)s import --no-supplementary Import without SCRs (faster)
  %(prog)s status                    Show database statistics
  %(prog)s history                   Show import history
  %(prog)s lookup "heart attack"     Look up a MeSH term
  %(prog)s search "cardio"           Search MeSH by partial match
  %(prog)s expand "MI"               Expand term to all synonyms
        """,
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Import command
    import_parser = subparsers.add_parser(
        "import",
        help="Download and import MeSH vocabulary",
    )
    import_parser.add_argument(
        "--year",
        type=int,
        help=f"MeSH year to import (default: {get_current_mesh_year()})",
    )
    import_parser.add_argument(
        "--no-supplementary",
        action="store_true",
        help="Skip supplementary concept records (faster, smaller)",
    )
    import_parser.add_argument(
        "--download-dir",
        help="Directory for downloaded files",
    )
    import_parser.add_argument(
        "--delete-downloads",
        action="store_true",
        help="Delete downloaded files after import",
    )
    import_parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Skip confirmation prompt",
    )
    import_parser.set_defaults(func=cmd_import)

    # Status command
    status_parser = subparsers.add_parser(
        "status",
        help="Show MeSH database statistics",
    )
    status_parser.set_defaults(func=cmd_status)

    # History command
    history_parser = subparsers.add_parser(
        "history",
        help="Show import history",
    )
    history_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum history records to show (default: 10)",
    )
    history_parser.set_defaults(func=cmd_history)

    # Lookup command
    lookup_parser = subparsers.add_parser(
        "lookup",
        help="Look up a MeSH term",
    )
    lookup_parser.add_argument(
        "term",
        nargs="+",
        help="MeSH term to look up",
    )
    lookup_parser.set_defaults(func=cmd_lookup)

    # Search command
    search_parser = subparsers.add_parser(
        "search",
        help="Search MeSH by partial match",
    )
    search_parser.add_argument(
        "query",
        nargs="+",
        help="Search query",
    )
    search_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum results (default: 20)",
    )
    search_parser.set_defaults(func=cmd_search)

    # Expand command
    expand_parser = subparsers.add_parser(
        "expand",
        help="Expand a MeSH term to all synonyms",
    )
    expand_parser.add_argument(
        "term",
        nargs="+",
        help="MeSH term to expand",
    )
    expand_parser.set_defaults(func=cmd_expand)

    # Clear cache command
    clear_parser = subparsers.add_parser(
        "clear-cache",
        help="Clear the MeSH API cache",
    )
    clear_parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Skip confirmation prompt",
    )
    clear_parser.set_defaults(func=cmd_clear_cache)

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if not args.command:
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
