#!/usr/bin/env python3
"""Missing PDF Download Tool

Downloads PDFs for documents that have pdf_url but no local PDF file.
Processes in batches of 100 with progress tracking and error handling.

Usage:
    # Download first batch (100 PDFs)
    python download_missing_pdfs.py --max-batches 1

    # Download first 500 PDFs (5 batches)
    python download_missing_pdfs.py --max-batches 5

    # Download ALL missing PDFs
    python download_missing_pdfs.py

    # Check how many PDFs are missing (dry run)
    python download_missing_pdfs.py --check-only

    # Custom batch size
    python download_missing_pdfs.py --batch-size 50

    # Custom timeout per PDF
    python download_missing_pdfs.py --timeout 60
"""

import argparse
import sys
import os
import time
from pathlib import Path
from dotenv import load_dotenv
import psycopg

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from bmlibrarian.utils.pdf_manager import PDFManager


def print_banner():
    """Print tool banner."""
    print("=" * 70)
    print("Missing PDF Download Tool")
    print("=" * 70)
    print()


def print_summary(stats: dict, elapsed_time: float):
    """Print download summary statistics.

    Args:
        stats: Statistics dictionary from download
        elapsed_time: Time elapsed in seconds
    """
    print("\n" + "=" * 70)
    print("Download Summary")
    print("=" * 70)
    print(f"Total missing PDFs found:   {stats.get('total_missing', 0)}")
    print(f"Already exists (skipped):   {stats.get('already_exists', 0)}")
    print(f"PDFs processed:             {stats.get('processed', 0)}")
    print(f"Successfully downloaded:    {stats.get('downloaded', 0)}")
    print(f"Failed:                     {stats.get('failed', 0)}")

    if elapsed_time > 0:
        print(f"\nTime elapsed:               {elapsed_time:.1f} seconds")
        if stats.get('downloaded', 0) > 0:
            rate = stats['downloaded'] / elapsed_time
            print(f"Download rate:              {rate:.2f} PDFs/second")

    if 'error' in stats:
        print(f"\nError: {stats['error']}")

    print("=" * 70)


def print_failure_details(stats: dict):
    """Print details of failed downloads.

    Args:
        stats: Statistics dictionary from download
    """
    if not stats.get('details'):
        return

    failures = [d for d in stats['details'] if d['status'] == 'failed']
    if not failures:
        return

    print("\nFailed Downloads:")
    print("-" * 70)

    for detail in failures[:20]:  # Show first 20 failures
        doc_id = detail['doc_id']
        reason = detail.get('reason', 'unknown')
        error = detail.get('error', '')

        print(f"✗ Document {doc_id}: {reason}")
        if error:
            print(f"  Error: {error}")
        if 'url' in detail:
            print(f"  URL: {detail['url']}")

    if len(failures) > 20:
        print(f"\n... and {len(failures) - 20} more failures")


def check_missing_count(pdf_manager: PDFManager) -> int:
    """Check how many PDFs are missing without downloading.

    Args:
        pdf_manager: PDFManager instance with database connection

    Returns:
        Number of missing PDFs
    """
    try:
        with pdf_manager.db_conn.cursor() as cursor:
            cursor.execute("""
                SELECT id, pdf_url, pdf_filename
                FROM document
                WHERE pdf_url IS NOT NULL
                ORDER BY id
            """)
            candidates = cursor.fetchall()

        print(f"Found {len(candidates)} documents with pdf_url")
        print("Checking which PDFs are missing...")

        missing_count = 0
        for doc_id, pdf_url, pdf_filename in candidates:
            if pdf_filename:
                existing_path = pdf_manager._find_current_pdf_path(pdf_filename)
                if existing_path:
                    continue

            missing_count += 1

        return missing_count

    except Exception as e:
        print(f"Error checking missing PDFs: {e}")
        return 0


def progress_callback(current: int, total: int, doc_id: int, status: str):
    """Progress callback for download tracking.

    Args:
        current: Current download number
        total: Total downloads to process
        doc_id: Document ID being processed
        status: Status message
    """
    percent = (current / total * 100) if total > 0 else 0
    print(f"  [{current}/{total}] ({percent:.1f}%) - Document {doc_id}: {status}",
          end='\r', flush=True)


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
    """Main download function."""
    parser = argparse.ArgumentParser(
        description="Download missing PDFs in batches",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        '--batch-size',
        type=int,
        default=100,
        help='Number of PDFs to download per batch (default: 100)'
    )

    parser.add_argument(
        '--max-batches',
        type=int,
        help='Maximum number of batches to process (default: unlimited)'
    )

    parser.add_argument(
        '--timeout',
        type=int,
        default=30,
        help='Download timeout in seconds per PDF (default: 30)'
    )

    parser.add_argument(
        '--check-only',
        action='store_true',
        help='Only check how many PDFs are missing without downloading'
    )

    parser.add_argument(
        '--no-db-update',
        action='store_true',
        help='Download files but do not update database (not recommended)'
    )

    parser.add_argument(
        '--base-dir',
        type=str,
        help='PDF base directory (overrides PDF_BASE_DIR from .env)'
    )

    parser.add_argument(
        '--show-failures',
        action='store_true',
        help='Show detailed information about failed downloads'
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
    print(f"PDF Base Directory: {pdf_manager.base_dir}\n")

    # Check-only mode
    if args.check_only:
        print("Checking for missing PDFs...\n")
        missing_count = check_missing_count(pdf_manager)
        print(f"\n✓ Found {missing_count} missing PDFs")
        print(f"\nTo download them, run:")
        print(f"  python download_missing_pdfs.py --max-batches {(missing_count // args.batch_size) + 1}")
        conn.close()
        return 0

    # Download mode
    print(f"Configuration:")
    print(f"  Batch size: {args.batch_size}")
    if args.max_batches:
        print(f"  Max batches: {args.max_batches} ({args.max_batches * args.batch_size} PDFs max)")
    else:
        print(f"  Max batches: unlimited")
    print(f"  Timeout: {args.timeout} seconds per PDF")
    print(f"  Update database: {not args.no_db_update}")
    print()

    print("Starting download process...\n")

    # Track time
    start_time = time.time()

    try:
        stats = pdf_manager.download_missing_pdfs(
            batch_size=args.batch_size,
            max_batches=args.max_batches,
            timeout=args.timeout,
            update_database=not args.no_db_update,
            progress_callback=progress_callback
        )

        elapsed_time = time.time() - start_time

        # Clear progress line
        print(" " * 80, end='\r')

        # Print results
        if args.show_failures:
            print_failure_details(stats)

        print_summary(stats, elapsed_time)

        # Success message
        print(f"\n✓ Download process completed!")
        if stats.get('failed', 0) > 0:
            print(f"⚠️  {stats['failed']} downloads failed. "
                  f"Use --show-failures to see details.")

    except KeyboardInterrupt:
        elapsed_time = time.time() - start_time
        print("\n\nDownload cancelled by user.")
        print(f"Time elapsed: {elapsed_time:.1f} seconds")
        return 130

    except Exception as e:
        print(f"\n✗ Download process failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1

    finally:
        conn.close()

    return 0


if __name__ == '__main__':
    sys.exit(main())
