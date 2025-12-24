#!/usr/bin/env python3
"""
MedRxiv Import CLI for BMLibrarian

Command-line interface for importing medRxiv biomedical preprints into the
BMLibrarian knowledge base.

Supports multiple extraction strategies:
- 'auto': Try text → HTML → JATS XML → PDF in priority order (recommended)
- 'pdf_only': Only use PDF extraction (legacy behavior)
- 'web_only': Only try web formats (text, HTML, XML), skip PDF

Usage:
    # Full pipeline with multi-format extraction (default)
    python medrxiv_import_cli.py update --download-pdfs --days-to-fetch 30

    # Update with specific extraction strategy
    python medrxiv_import_cli.py update --download-pdfs --extraction-strategy auto

    # Fetch only metadata (no PDFs)
    python medrxiv_import_cli.py update --days-to-fetch 7

    # Download missing PDFs for existing records
    python medrxiv_import_cli.py fetch-pdfs --limit 100

    # Re-extract full text for existing records with better formats
    python medrxiv_import_cli.py extract-text --limit 100 --missing-only

    # Full update with specific date range
    python medrxiv_import_cli.py update --start-date 2024-01-01 --end-date 2024-12-31 --download-pdfs
"""

import argparse
import logging
import sys
from datetime import datetime

from src.bmlibrarian.importers import MedRxivImporter


def setup_logging(verbose: bool = False):
    """Configure logging for the CLI."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def cmd_update(args):
    """Execute the update command."""
    print("=" * 70)
    print("MedRxiv Database Update")
    print("=" * 70)
    print(f"Extraction strategy: {args.extraction_strategy}")
    print("=" * 70)

    try:
        importer = MedRxivImporter(
            pdf_base_dir=args.pdf_dir,
            extraction_strategy=args.extraction_strategy
        )

        stats = importer.update_database(
            download_pdfs=args.download_pdfs,
            max_retries=args.max_retries,
            start_date_override=args.start_date,
            days_to_fetch=args.days_to_fetch,
            end_date=args.end_date
        )

        print("\n" + "=" * 70)
        print("Update Complete!")
        print("=" * 70)
        print(f"Total papers processed: {stats['total_processed']}")
        print(f"Dates processed: {stats['dates_processed']}")
        print("=" * 70)

        return 0

    except Exception as e:
        logging.error(f"Error during update: {e}", exc_info=True)
        return 1


def cmd_fetch_pdfs(args):
    """Execute the fetch-pdfs command."""
    print("=" * 70)
    print("Fetching Missing PDFs")
    print("=" * 70)

    try:
        importer = MedRxivImporter(pdf_base_dir=args.pdf_dir)

        count = importer.fetch_missing_pdfs(
            max_retries=args.max_retries,
            limit=args.limit,
            convert_to_markdown=args.convert_to_markdown
        )

        print("\n" + "=" * 70)
        print("PDF Download Complete!")
        print("=" * 70)
        print(f"Total PDFs downloaded: {count}")
        print("=" * 70)

        return 0

    except Exception as e:
        logging.error(f"Error during PDF download: {e}", exc_info=True)
        return 1


def cmd_extract_text(args):
    """Execute the extract-text command to re-extract full text."""
    print("=" * 70)
    print("MedRxiv Full-Text Re-Extraction")
    print("=" * 70)
    print(f"Extraction strategy: {args.extraction_strategy}")
    print(f"Missing only: {args.missing_only}")
    if args.limit:
        print(f"Limit: {args.limit}")
    print("=" * 70)

    try:
        importer = MedRxivImporter(
            pdf_base_dir=args.pdf_dir,
            extraction_strategy=args.extraction_strategy
        )

        stats = importer.reextract_full_text(
            limit=args.limit,
            missing_only=args.missing_only
        )

        print("\n" + "=" * 70)
        print("Re-Extraction Complete!")
        print("=" * 70)
        print(f"Total processed: {stats['total_processed']}")
        print(f"Successfully extracted: {stats['extracted']}")
        print(f"Failed: {stats['failed']}")
        print("\nExtraction by format:")
        for fmt, count in stats.get('by_format', {}).items():
            if count > 0:
                print(f"  {fmt}: {count}")
        print("=" * 70)

        return 0

    except Exception as e:
        logging.error(f"Error during extraction: {e}", exc_info=True)
        return 1


def cmd_status(args):
    """Show import status and statistics."""
    print("=" * 70)
    print("MedRxiv Import Status")
    print("=" * 70)

    try:
        importer = MedRxivImporter(pdf_base_dir=args.pdf_dir)

        # Use the new get_extraction_statistics method
        stats = importer.get_extraction_statistics()
        latest_date = importer.get_latest_date()

        print(f"\nLatest paper date in database: {latest_date or 'No papers found'}")

        if latest_date:
            resume_date = importer.get_resume_date(days_back=1)
            print(f"Suggested resume date: {resume_date}")

        print(f"\nTotal medRxiv papers: {stats['total_papers']}")
        print(f"Papers with PDFs: {stats['with_pdf']} ({100*stats['with_pdf']/stats['total_papers'] if stats['total_papers'] else 0:.1f}%)")
        print(f"Papers with full text: {stats['with_fulltext']} ({stats['fulltext_percentage']}%)")
        print(f"Papers missing full text: {stats['missing_fulltext']}")
        print(f"\nCurrent extraction strategy: {stats['extraction_strategy']}")
        print(f"Extraction priority: {' → '.join(stats['extraction_priority'])}")

        print("=" * 70)

        return 0

    except Exception as e:
        logging.error(f"Error getting status: {e}", exc_info=True)
        return 1


def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description='Import medRxiv biomedical preprints into BMLibrarian',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )

    parser.add_argument(
        '--pdf-dir',
        type=str,
        help='Base directory for PDF storage (overrides PDF_BASE_DIR env var)'
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to execute')

    # Update command
    update_parser = subparsers.add_parser(
        'update',
        help='Update database with new papers from medRxiv API'
    )
    update_parser.add_argument(
        '--download-pdfs',
        action='store_true',
        help='Download PDFs for each paper'
    )
    update_parser.add_argument(
        '--start-date',
        type=str,
        help='Start date in YYYY-MM-DD format'
    )
    update_parser.add_argument(
        '--end-date',
        type=str,
        help='End date in YYYY-MM-DD format (defaults to today)'
    )
    update_parser.add_argument(
        '--days-to-fetch',
        type=int,
        default=1095,
        help='Number of days back to fetch if database is empty (default: 1095). '
             'Note: medRxiv launched June 6, 2019 - dates before this are automatically skipped.'
    )
    update_parser.add_argument(
        '--max-retries',
        type=int,
        default=5,
        help='Maximum retry attempts for failed requests (default: 5)'
    )
    update_parser.add_argument(
        '--extraction-strategy',
        type=str,
        choices=['auto', 'pdf_only', 'web_only'],
        default='auto',
        help='Full-text extraction strategy: '
             'auto = try text→HTML→XML→PDF (default), '
             'pdf_only = only use PDF extraction, '
             'web_only = only try web formats (no PDF)'
    )

    # Fetch PDFs command
    fetch_parser = subparsers.add_parser(
        'fetch-pdfs',
        help='Download missing PDFs for existing database records'
    )
    fetch_parser.add_argument(
        '--limit',
        type=int,
        help='Maximum number of PDFs to download'
    )
    fetch_parser.add_argument(
        '--max-retries',
        type=int,
        default=5,
        help='Maximum retry attempts for failed downloads (default: 5)'
    )
    fetch_parser.add_argument(
        '--no-convert',
        dest='convert_to_markdown',
        action='store_false',
        default=True,
        help='Skip PDF to markdown conversion'
    )

    # Extract text command
    extract_parser = subparsers.add_parser(
        'extract-text',
        help='Re-extract full text for existing records using multi-format extraction'
    )
    extract_parser.add_argument(
        '--limit',
        type=int,
        help='Maximum number of papers to process'
    )
    extract_parser.add_argument(
        '--missing-only',
        action='store_true',
        help='Only process papers without full text'
    )
    extract_parser.add_argument(
        '--extraction-strategy',
        type=str,
        choices=['auto', 'pdf_only', 'web_only'],
        default='auto',
        help='Full-text extraction strategy: '
             'auto = try text→HTML→XML→PDF (default), '
             'pdf_only = only use PDF extraction, '
             'web_only = only try web formats (no PDF)'
    )

    # Status command
    status_parser = subparsers.add_parser(
        'status',
        help='Show import status and statistics'
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(args.verbose)

    # Execute command
    if args.command == 'update':
        return cmd_update(args)
    elif args.command == 'fetch-pdfs':
        return cmd_fetch_pdfs(args)
    elif args.command == 'extract-text':
        return cmd_extract_text(args)
    elif args.command == 'status':
        return cmd_status(args)
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())
