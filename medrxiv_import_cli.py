#!/usr/bin/env python3
"""
MedRxiv Import CLI for BMLibrarian

Command-line interface for importing medRxiv biomedical preprints into the
BMLibrarian knowledge base.

Usage:
    # Full pipeline: fetch new papers and download PDFs
    python medrxiv_import_cli.py update --download-pdfs --days-to-fetch 30

    # Fetch only metadata (no PDFs)
    python medrxiv_import_cli.py update --days-to-fetch 7

    # Download missing PDFs for existing records
    python medrxiv_import_cli.py fetch-pdfs --limit 100

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

    try:
        importer = MedRxivImporter(pdf_base_dir=args.pdf_dir)

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


def cmd_status(args):
    """Show import status and statistics."""
    print("=" * 70)
    print("MedRxiv Import Status")
    print("=" * 70)

    try:
        importer = MedRxivImporter(pdf_base_dir=args.pdf_dir)

        latest_date = importer.get_latest_date()
        missing_pdfs = importer.get_preprints_without_pdfs(limit=1)

        print(f"\nLatest paper date in database: {latest_date or 'No papers found'}")

        if latest_date:
            resume_date = importer.get_resume_date(days_back=1)
            print(f"Suggested resume date: {resume_date}")

        # Get total count of medRxiv papers
        from bmlibrarian.database import get_db_manager
        db_manager = get_db_manager()

        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                # Count total medRxiv papers
                cur.execute("""
                    SELECT COUNT(*) FROM document
                    WHERE source_id = %s
                """, (importer.source_id,))
                total_papers = cur.fetchone()[0]

                # Count papers with PDFs
                cur.execute("""
                    SELECT COUNT(*) FROM document
                    WHERE source_id = %s
                    AND pdf_filename IS NOT NULL
                    AND pdf_filename != ''
                """, (importer.source_id,))
                with_pdfs = cur.fetchone()[0]

                # Count papers with full text
                cur.execute("""
                    SELECT COUNT(*) FROM document
                    WHERE source_id = %s
                    AND full_text IS NOT NULL
                    AND full_text != ''
                """, (importer.source_id,))
                with_fulltext = cur.fetchone()[0]

        print(f"\nTotal medRxiv papers: {total_papers}")
        print(f"Papers with PDFs: {with_pdfs} ({100*with_pdfs/total_papers if total_papers else 0:.1f}%)")
        print(f"Papers with full text: {with_fulltext} ({100*with_fulltext/total_papers if total_papers else 0:.1f}%)")
        print(f"Papers missing PDFs: {total_papers - with_pdfs}")

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
        help='Number of days back to fetch if database is empty (default: 1095)'
    )
    update_parser.add_argument(
        '--max-retries',
        type=int,
        default=5,
        help='Maximum retry attempts for failed requests (default: 5)'
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
    elif args.command == 'status':
        return cmd_status(args)
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())
