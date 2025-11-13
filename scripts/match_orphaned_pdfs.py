#!/usr/bin/env python3
"""Orphaned PDF Matching Tool

Finds orphaned PDF files in the base directory, reconstructs DOIs from filenames,
searches the database for matching documents, and links them together.

This tool is useful for:
- PDFs left in the base directory from failed migrations
- PDFs downloaded with DOI-based filenames but not linked to documents
- Recovering from incomplete batch operations

Usage:
    # Dry run - see what would be matched without making changes
    python match_orphaned_pdfs.py --dry-run

    # Actually link orphaned PDFs to documents
    # (searches base dir + failed/ + unknown/ subdirectories)
    python match_orphaned_pdfs.py

    # Only search main directory (skip subdirectories)
    python match_orphaned_pdfs.py --no-subdirs

    # Check specific directory
    python match_orphaned_pdfs.py --directory /path/to/pdfs --dry-run

    # Show detailed results
    python match_orphaned_pdfs.py --verbose
"""

import argparse
import sys
import os
from pathlib import Path
from dotenv import load_dotenv
import psycopg

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from bmlibrarian.utils.pdf_manager import PDFManager


def print_banner():
    """Print tool banner."""
    print("=" * 70)
    print("Orphaned PDF Matching Tool")
    print("=" * 70)
    print()


def print_summary(stats: dict):
    """Print matching summary statistics.

    Args:
        stats: Statistics dictionary from matching
    """
    print("\n" + "=" * 70)
    print("Matching Summary")
    print("=" * 70)
    print(f"Total PDFs found:           {stats['total_pdfs']}")
    print(f"DOI-format filenames:       {stats['doi_reconstructed']}")
    print(f"Non-DOI filenames:          {stats['not_doi_format']}")
    print(f"Matched to documents:       {stats['matched']}")
    print(f"Successfully linked:        {stats['linked']}")
    print(f"Already linked (correct):   {stats['already_linked']}")
    print(f"Replaced older files:       {stats.get('replaced', 0)}")
    print(f"Duplicates deleted:         {stats.get('duplicates_deleted', 0)}")
    print(f"No database match:          {stats['no_match']}")
    print(f"Failed to link:             {stats['failed']}")

    if 'error' in stats:
        print(f"\nError: {stats['error']}")

    print("=" * 70)


def print_details(stats: dict, verbose: bool = False):
    """Print detailed matching results.

    Args:
        stats: Statistics dictionary from matching
        verbose: If True, show all details. If False, only show matches and failures.
    """
    if not stats.get('details'):
        return

    print("\nDetailed Results:")
    print("-" * 70)

    # Group by status
    linked = [d for d in stats['details'] if d['status'] in ['linked', 'would_link']]
    already = [d for d in stats['details'] if d['status'] in ['already_linked', 'already_in_correct_location']]
    replaced = [d for d in stats['details'] if 'replace' in d['status']]
    duplicates = [d for d in stats['details'] if d['status'] == 'duplicate_deleted_older']
    no_match = [d for d in stats['details'] if d['status'] == 'no_match']
    not_doi = [d for d in stats['details'] if d['status'] == 'not_doi_format']
    failed = [d for d in stats['details'] if d['status'] == 'failed']

    # Show linked PDFs
    if linked:
        print(f"\n✓ Linked PDFs ({len(linked)}):")
        for detail in linked:
            filename = detail['filename']
            doi = detail.get('doi', 'N/A')
            doc_id = detail.get('doc_id', 'N/A')
            title = detail.get('doc_title', 'Unknown')[:60]
            status = "Would link" if detail['status'] == 'would_link' else "Linked"

            print(f"  {status}: {filename}")
            print(f"    DOI: {doi}")
            print(f"    Document {doc_id}: {title}")
            if 'to' in detail:
                print(f"    Target: {detail['to']}")
            print()

    # Show replaced files
    if replaced:
        print(f"\n🔄 Replaced Older Files ({len(replaced)}):")
        for detail in replaced:
            filename = detail['filename']
            newer = detail.get('newer', 'N/A')
            deleted = detail.get('deleted', 'N/A')
            print(f"  {filename}")
            print(f"    Kept newer: {newer}")
            print(f"    Deleted: {deleted}")
            print()

    # Show deleted duplicates
    if duplicates:
        print(f"\n🗑️  Deleted Duplicate Files ({len(duplicates)}):")
        for detail in duplicates[:10]:  # Show first 10
            filename = detail['filename']
            kept = detail.get('kept', 'N/A')
            deleted = detail.get('deleted', 'N/A')
            print(f"  Deleted: {deleted}")
            print(f"  Kept: {kept}")
        if len(duplicates) > 10:
            print(f"  ... and {len(duplicates) - 10} more")
        print()

    # Show already linked
    if already and verbose:
        print(f"\n✓ Already Linked ({len(already)}):")
        for detail in already[:10]:  # Show first 10
            filename = detail['filename']
            path = detail.get('path') or detail.get('existing_path', 'N/A')
            print(f"  {filename} -> {path}")
        if len(already) > 10:
            print(f"  ... and {len(already) - 10} more")
        print()

    # Show no match
    if no_match:
        print(f"\n✗ No Database Match ({len(no_match)}):")
        for detail in no_match[:20]:  # Show first 20
            filename = detail['filename']
            doi = detail.get('doi', 'N/A')
            print(f"  {filename} (DOI: {doi})")
        if len(no_match) > 20:
            print(f"  ... and {len(no_match) - 20} more")
        print()

    # Show non-DOI format
    if not_doi and verbose:
        print(f"\n⚠ Non-DOI Format ({len(not_doi)}):")
        for detail in not_doi[:10]:  # Show first 10
            print(f"  {detail['filename']}")
        if len(not_doi) > 10:
            print(f"  ... and {len(not_doi) - 10} more")
        print()

    # Show failures
    if failed:
        print(f"\n✗ Failed to Link ({len(failed)}):")
        for detail in failed:
            filename = detail['filename']
            reason = detail.get('reason', 'Unknown')
            print(f"  {filename}: {reason}")
        print()


def get_database_connection():
    """Create database connection from environment variables.

    Returns:
        Database connection object
    """
    load_dotenv()

    db_params = {
        'dbname': os.getenv('POSTGRES_DB', 'knowledgebase'),
        'user': os.getenv('POSTGRES_USER', 'postgres'),
        'password': os.getenv('POSTGRES_PASSWORD', ''),
        'host': os.getenv('POSTGRES_HOST', 'localhost'),
        'port': os.getenv('POSTGRES_PORT', '5432')
    }

    conn = psycopg.connect(**db_params)
    return conn


def main():
    """Main matching function."""
    parser = argparse.ArgumentParser(
        description="Match orphaned PDFs to documents by DOI reconstruction",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview matches without actually linking files or updating database'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Show detailed output for all PDFs'
    )

    parser.add_argument(
        '--directory',
        type=str,
        help='Directory to search for orphaned PDFs (default: PDF_BASE_DIR from .env)'
    )

    parser.add_argument(
        '--base-dir',
        type=str,
        help='PDF base directory for organized storage (default: PDF_BASE_DIR from .env)'
    )

    parser.add_argument(
        '--no-subdirs',
        action='store_true',
        help='Only search main directory, skip failed/ and unknown/ subdirectories'
    )

    args = parser.parse_args()

    # Print banner
    print_banner()

    # Connect to database
    print("Connecting to database...")
    try:
        conn = get_database_connection()
        print("✓ Connected successfully\n")
    except Exception as e:
        print(f"✗ Failed to connect to database: {e}")
        return 1

    # Initialize PDF manager
    pdf_manager = PDFManager(base_dir=args.base_dir, db_conn=conn)

    # Determine search directory
    search_dir = Path(args.directory) if args.directory else pdf_manager.base_dir

    print(f"PDF Base Directory: {pdf_manager.base_dir}")
    print(f"Search Directory: {search_dir}")

    if not args.no_subdirs:
        print("Also searching: failed/ and unknown/ subdirectories")
    print()

    if args.dry_run:
        print("⚠️  DRY RUN MODE - No changes will be made\n")

    # Run matching
    print("Searching for orphaned PDFs and matching to documents...\n")

    try:
        stats = pdf_manager.match_orphaned_pdfs(
            directory=search_dir,
            dry_run=args.dry_run,
            include_subdirs=not args.no_subdirs
        )

        # Print results
        print_details(stats, verbose=args.verbose)
        print_summary(stats)

        # Success message
        if args.dry_run:
            print("\n✓ Dry run completed. Use without --dry-run to link PDFs.")
            if stats['matched'] > 0:
                print(f"   {stats['matched']} PDFs would be linked to documents.")
            print("\n⚠️  IMPORTANT: No files were moved (dry-run mode)")
            print(f"   To actually move and link PDFs, run:")
            print(f"   python match_orphaned_pdfs.py")
        else:
            print("\n✓ Matching completed!")
            if stats['linked'] > 0:
                print(f"   ✅ {stats['linked']} orphaned PDFs moved and linked to documents.")
                print(f"   📁 PDFs have been moved from their original locations to year-based directories.")
            if stats['failed'] > 0:
                print(f"⚠️  {stats['failed']} PDFs failed to link. Check logs for details.")
            if stats['linked'] == 0 and stats['failed'] == 0 and stats['matched'] == 0:
                print("   No PDFs needed to be linked (all already organized or no matches found).")

        # Suggestions
        if stats['no_match'] > 0:
            print(f"\n💡 Tip: {stats['no_match']} PDFs have DOI-format names but no matching")
            print(f"   documents in the database. These may be from deleted or external sources.")

        if stats['not_doi_format'] > 0:
            print(f"\n💡 Tip: {stats['not_doi_format']} PDFs don't have DOI-format filenames.")
            print(f"   These need manual review or alternative matching strategies.")

    except KeyboardInterrupt:
        print("\n\nMatching cancelled by user.")
        return 130

    except Exception as e:
        print(f"\n✗ Matching failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1

    finally:
        conn.close()

    return 0


if __name__ == '__main__':
    sys.exit(main())
