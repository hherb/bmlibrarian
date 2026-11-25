#!/usr/bin/env python3
"""
PDF Import CLI for BMLibrarian

This CLI tool analyzes PDF files, extracts metadata using LLMs, matches them to
existing documents in the BMLibrarian database, and imports them with proper
naming and organization.

Usage:
    # Import single PDF file
    uv run python pdf_import_cli.py file /path/to/paper.pdf

    # Import all PDFs from a directory
    uv run python pdf_import_cli.py directory /path/to/pdfs/

    # Dry run to see what would be done
    uv run python pdf_import_cli.py file paper.pdf --dry-run

    # Import with custom model
    uv run python pdf_import_cli.py directory /pdfs/ --model medgemma4B_it_q8:latest

    # Recursive directory search
    uv run python pdf_import_cli.py directory /pdfs/ --recursive
"""

import sys
import argparse
import logging
from pathlib import Path
from typing import Dict, Any

from bmlibrarian.importers import PDFMatcher

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def print_result(result: Dict[str, Any], verbose: bool = False):
    """Print formatted result for a single PDF."""
    status = result.get('status', 'unknown')
    filename = result.get('pdf_filename', 'unknown')

    # Status emoji
    status_icon = {
        'imported': '✅',
        'would_import': '🔄',
        'linked': '🔗',
        'would_link': '🔄',
        'no_match': '❌',
        'already_exists': '📋',
        'duplicate': '📋',
        'skipped': '⏭️',
        'failed': '⚠️',
        'not_found': '🔍',
        'extraction_failed': '📄',
        'no_metadata': '📝'
    }.get(status, '❓')

    print(f"\n{status_icon} {filename}")

    if status == 'imported':
        doc = result.get('matched_document', {})
        print(f"  ✓ Imported successfully")
        print(f"  Document ID: {result.get('doc_id')}")
        print(f"  DOI: {result.get('doi', 'N/A')}")
        print(f"  Title: {result.get('title', 'N/A')}")
        print(f"  Target: {result.get('target')}")

    elif status == 'would_import':
        doc = result.get('matched_document', {})
        print(f"  🔄 Would import (dry run)")
        print(f"  Document ID: {result.get('doc_id')}")
        print(f"  Title: {doc.get('title', 'N/A')}")
        print(f"  Source: {result.get('source')}")
        print(f"  Target: {result.get('target')}")

    elif status == 'no_match':
        metadata = result.get('metadata', {})
        print(f"  ❌ No matching document found in database")
        if metadata.get('doi'):
            print(f"  Extracted DOI: {metadata['doi']}")
        if metadata.get('pmid'):
            print(f"  Extracted PMID: {metadata['pmid']}")
        if metadata.get('title'):
            print(f"  Extracted title: {metadata['title'][:80]}...")

    elif status == 'linked':
        print(f"  🔗 {result.get('message', 'Linked existing PDF')}")
        print(f"  Path: {result.get('path') or result.get('existing_path')}")

    elif status == 'would_link':
        print(f"  🔄 Would link the existing PDF to document {result.get('doc_id')} (dry run)")
        print(f"  Path: {result.get('path') or result.get('existing_path')}")

    elif status in ['already_exists', 'duplicate']:
        print(f"  📋 {result.get('message', 'Already exists')}")
        if result.get('existing_path'):
            print(f"  Existing: {result.get('existing_path')}")

    elif status == 'skipped':
        print(f"  ⏭️ {result.get('reason', 'Skipped')}")

    elif status == 'failed':
        print(f"  ⚠️ Failed: {result.get('reason', result.get('error', 'Unknown error'))}")

    elif status == 'extraction_failed':
        print(f"  📄 Could not extract text from PDF")

    elif status == 'no_metadata':
        print(f"  📝 Could not extract metadata from PDF")

    # Verbose output
    if verbose and result.get('metadata'):
        print("\n  Extracted metadata:")
        metadata = result['metadata']
        if metadata.get('doi'):
            print(f"    DOI: {metadata['doi']}")
        if metadata.get('pmid'):
            print(f"    PMID: {metadata['pmid']}")
        if metadata.get('title'):
            print(f"    Title: {metadata['title'][:100]}")
        if metadata.get('authors'):
            print(f"    Authors: {', '.join(metadata['authors'][:3])}...")


def print_stats(stats: Dict[str, Any]):
    """Print summary statistics."""
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Total PDFs processed:     {stats['total']}")
    print(f"Successfully imported:    {stats['imported']}")
    print(f"No database match:        {stats['no_match']}")
    print(f"Linked existing PDF:      {stats.get('linked', 0)}")
    print(f"Already exists:           {stats['already_exists']}")
    print(f"Skipped:                  {stats['skipped']}")
    print(f"Failed:                   {stats['failed']}")
    print("="*60)


def cmd_import_file(args):
    """Import a single PDF file."""
    pdf_path = Path(args.path)

    if not pdf_path.exists():
        logger.error(f"File not found: {pdf_path}")
        return 1

    if not pdf_path.suffix.lower() == '.pdf':
        logger.error(f"Not a PDF file: {pdf_path}")
        return 1

    # Initialize matcher
    matcher = PDFMatcher(
        pdf_base_dir=args.pdf_dir,
        ollama_url=args.ollama_url,
        model=args.model
    )

    # Process PDF
    print(f"\n{'DRY RUN - ' if args.dry_run else ''}Processing: {pdf_path.name}")
    print("-" * 60)

    result = matcher.match_and_import_pdf(pdf_path, dry_run=args.dry_run)
    print_result(result, verbose=args.verbose)

    if result['status'] == 'imported':
        print("\n✅ Import successful!")
        return 0
    elif result['status'] == 'linked':
        print("\n✅ Existing PDF linked to its document")
        return 0
    elif result['status'] in ('would_import', 'would_link'):
        print("\n🔄 Dry run complete. Use without --dry-run to actually import.")
        return 0
    else:
        print(f"\n⚠️  Import failed or skipped")
        return 1


def cmd_import_directory(args):
    """Import all PDFs from a directory."""
    directory = Path(args.path)

    if not directory.exists():
        logger.error(f"Directory not found: {directory}")
        return 1

    if not directory.is_dir():
        logger.error(f"Not a directory: {directory}")
        return 1

    # Initialize matcher
    matcher = PDFMatcher(
        pdf_base_dir=args.pdf_dir,
        ollama_url=args.ollama_url,
        model=args.model
    )

    # Process directory
    print(f"\n{'DRY RUN - ' if args.dry_run else ''}Processing directory: {directory}")
    if args.recursive:
        print("(including subdirectories)")
    print("-" * 60)

    stats = matcher.match_and_import_directory(
        directory,
        dry_run=args.dry_run,
        recursive=args.recursive
    )

    # Print detailed results if verbose
    if args.verbose:
        for result in stats['details']:
            print_result(result, verbose=True)

    # Print summary
    print_stats(stats)

    if args.dry_run:
        print("\n🔄 Dry run complete. Use without --dry-run to actually import.")

    if stats['imported'] > 0 or stats.get('linked', 0) > 0:
        print(f"\n✅ Successfully imported {stats['imported']} PDFs, "
              f"linked {stats.get('linked', 0)} existing PDFs")
        return 0
    else:
        print(f"\n⚠️  No PDFs were imported")
        return 1


def cmd_status(args):
    """Show PDF import status and statistics."""
    from bmlibrarian.database import get_db_manager

    db_manager = get_db_manager()

    with db_manager.get_connection() as conn:
        with conn.cursor() as cur:
            # Count total documents
            cur.execute("SELECT COUNT(*) FROM document")
            total_docs = cur.fetchone()[0]

            # Count documents with PDFs
            cur.execute("SELECT COUNT(*) FROM document WHERE pdf_filename IS NOT NULL AND pdf_filename != ''")
            docs_with_pdf = cur.fetchone()[0]

            # Count documents without PDFs but with URL
            cur.execute("SELECT COUNT(*) FROM document WHERE (pdf_filename IS NULL OR pdf_filename = '') AND pdf_url IS NOT NULL")
            docs_missing_pdf = cur.fetchone()[0]

            # Count by source
            cur.execute("""
                SELECT s.name,
                       COUNT(*) as total,
                       COUNT(d.pdf_filename) as with_pdf
                FROM document d
                JOIN sources s ON d.source_id = s.id
                GROUP BY s.name
                ORDER BY total DESC
            """)
            by_source = cur.fetchall()

    print("\n" + "="*60)
    print("PDF IMPORT STATUS")
    print("="*60)
    print(f"Total documents:               {total_docs:,}")
    print(f"Documents with PDFs:           {docs_with_pdf:,} ({100*docs_with_pdf/total_docs:.1f}%)")
    print(f"Documents missing PDFs:        {docs_missing_pdf:,}")
    print("\nBy source:")
    for source_name, total, with_pdf in by_source:
        pct = 100 * with_pdf / total if total > 0 else 0
        print(f"  {source_name:20s}: {with_pdf:,}/{total:,} ({pct:.1f}%)")
    print("="*60)

    return 0


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Import PDFs and match them to BMLibrarian documents using LLM-based metadata extraction',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Import single PDF
  uv run python pdf_import_cli.py file /path/to/paper.pdf

  # Import directory (dry run first)
  uv run python pdf_import_cli.py directory /path/to/pdfs/ --dry-run

  # Import directory with custom settings
  uv run python pdf_import_cli.py directory /pdfs/ --recursive --model gpt-oss:20b

  # Check import status
  uv run python pdf_import_cli.py status
        """
    )

    # Global options
    parser.add_argument('--pdf-dir', help='Base directory for PDF storage (overrides PDF_BASE_DIR env var)')
    parser.add_argument('--ollama-url', default='http://localhost:11434', help='Ollama service URL')
    parser.add_argument('--model', help='LLM model for metadata extraction (default: gpt-oss:20b)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    parser.add_argument('--dry-run', action='store_true', help='Dry run - show what would be done without making changes')

    # Subcommands
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')

    # File command
    file_parser = subparsers.add_parser('file', help='Import a single PDF file')
    file_parser.add_argument('path', help='Path to PDF file')
    file_parser.set_defaults(func=cmd_import_file)

    # Directory command
    dir_parser = subparsers.add_parser('directory', help='Import all PDFs from a directory')
    dir_parser.add_argument('path', help='Path to directory containing PDFs')
    dir_parser.add_argument('--recursive', '-r', action='store_true', help='Search subdirectories recursively')
    dir_parser.set_defaults(func=cmd_import_directory)

    # Status command
    status_parser = subparsers.add_parser('status', help='Show PDF import statistics')
    status_parser.set_defaults(func=cmd_status)

    args = parser.parse_args()

    # Show help if no command specified
    if not args.command:
        parser.print_help()
        return 1

    # Execute command
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        return 130
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=args.verbose)
        return 1


if __name__ == '__main__':
    sys.exit(main())
