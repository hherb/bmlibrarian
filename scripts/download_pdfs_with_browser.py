#!/usr/bin/env python3
"""Download PDFs using browser automation for Cloudflare-protected URLs.

This script finds documents with pdf_url but no local PDF, and attempts to download
them using browser automation to handle Cloudflare verification and other anti-bot
protections.
"""

import os
import sys
import logging
from pathlib import Path
from typing import Optional

# Add src directory to path
src_path = Path(__file__).parent / 'src'
sys.path.insert(0, str(src_path))

import psycopg
from dotenv import load_dotenv

from bmlibrarian.utils.pdf_manager import PDFManager
from bmlibrarian.utils.browser_downloader import BrowserDownloader
import asyncio

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_database_connection():
    """Create database connection from environment variables."""
    load_dotenv()

    db_params = {
        'dbname': os.getenv('POSTGRES_DB', 'knowledgebase'),
        'user': os.getenv('POSTGRES_USER'),
        'password': os.getenv('POSTGRES_PASSWORD'),
        'host': os.getenv('POSTGRES_HOST', 'localhost'),
        'port': os.getenv('POSTGRES_PORT', '5432')
    }

    try:
        conn = psycopg.connect(**db_params)
        logger.info(f"Connected to database: {db_params['dbname']}")
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        raise


def find_documents_needing_browser_download(
    conn,
    batch_size: int = 50,
    offset: int = 0
) -> list:
    """Find documents with pdf_url but no local PDF.

    Args:
        conn: Database connection
        batch_size: Number of documents to retrieve
        offset: Offset for pagination

    Returns:
        List of document dictionaries
    """
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT id, doi, title, publication_date, pdf_filename, pdf_url
            FROM document
            WHERE pdf_url IS NOT NULL
            AND pdf_url != ''
            ORDER BY id
            LIMIT %s OFFSET %s
        """, (batch_size, offset))

        documents = []
        for row in cursor.fetchall():
            doc_id, doi, title, pub_date, pdf_filename, pdf_url = row
            documents.append({
                'id': doc_id,
                'doi': doi,
                'title': title,
                'publication_date': str(pub_date) if pub_date else None,
                'pdf_filename': pdf_filename,
                'pdf_url': pdf_url
            })

        return documents


async def download_batch_with_browser(
    documents: list,
    pdf_manager: PDFManager,
    headless: bool = True,
    max_wait_cloudflare: int = 30
) -> dict:
    """Download a batch of PDFs using browser automation.

    Args:
        documents: List of document dictionaries
        pdf_manager: PDFManager instance
        headless: Run browser in headless mode
        max_wait_cloudflare: Maximum seconds to wait for Cloudflare

    Returns:
        Dictionary with download statistics
    """
    stats = {
        'total': len(documents),
        'already_exists': 0,
        'success': 0,
        'failed': 0,
        'details': []
    }

    # Start browser once for entire batch
    async with BrowserDownloader(headless=headless) as downloader:
        for doc in documents:
            doc_id = doc['id']
            pdf_url = doc['pdf_url']
            title = doc.get('title', 'Unknown')[:60]

            # Check if PDF already exists
            if pdf_manager.pdf_exists(doc):
                logger.info(f"Document {doc_id}: PDF already exists, skipping")
                stats['already_exists'] += 1
                continue

            # Generate filename if needed
            if not doc.get('pdf_filename'):
                doc['pdf_filename'] = pdf_manager._generate_filename(doc)

            # Get target path
            pdf_path = pdf_manager.get_pdf_path(doc, create_dirs=True)
            if not pdf_path:
                logger.error(f"Document {doc_id}: Could not determine PDF path")
                stats['failed'] += 1
                stats['details'].append({
                    'doc_id': doc_id,
                    'title': title,
                    'status': 'failed',
                    'error': 'Could not determine PDF path'
                })
                continue

            logger.info(f"Document {doc_id}: Downloading from {pdf_url}")

            # Download with browser
            result = await downloader.download_pdf(
                url=pdf_url,
                save_path=pdf_path,
                wait_for_cloudflare=True,
                max_wait=max_wait_cloudflare
            )

            if result['status'] == 'success':
                # Update database with relative path
                relative_path = pdf_manager.get_relative_pdf_path(doc)
                if relative_path:
                    success = pdf_manager.update_database_pdf_path(doc_id, relative_path)
                    if success:
                        logger.info(f"Document {doc_id}: Successfully downloaded ({result['size']} bytes)")
                        stats['success'] += 1
                        stats['details'].append({
                            'doc_id': doc_id,
                            'title': title,
                            'status': 'success',
                            'path': str(relative_path),
                            'size': result['size']
                        })
                    else:
                        logger.error(f"Document {doc_id}: Download succeeded but database update failed")
                        pdf_path.unlink()  # Clean up
                        stats['failed'] += 1
                        stats['details'].append({
                            'doc_id': doc_id,
                            'title': title,
                            'status': 'failed',
                            'error': 'Database update failed'
                        })
            else:
                logger.error(f"Document {doc_id}: Download failed - {result.get('error', 'Unknown error')}")
                stats['failed'] += 1
                stats['details'].append({
                    'doc_id': doc_id,
                    'title': title,
                    'status': 'failed',
                    'error': result.get('error', 'Unknown error')
                })

    return stats


def print_summary(stats: dict):
    """Print download summary statistics."""
    print("\n" + "=" * 70)
    print("Browser Download Summary")
    print("=" * 70)
    print(f"Total documents processed:  {stats['total']}")
    print(f"Already had PDFs:           {stats['already_exists']}")
    print(f"Successfully downloaded:    {stats['success']}")
    print(f"Failed downloads:           {stats['failed']}")
    print("=" * 70)


def print_details(stats: dict, show_success: bool = True):
    """Print detailed download results."""
    if not stats['details']:
        return

    print("\nDetailed Results:")
    print("-" * 70)

    success = [d for d in stats['details'] if d['status'] == 'success']
    failed = [d for d in stats['details'] if d['status'] == 'failed']

    if success and show_success:
        print(f"\n✓ Successfully Downloaded ({len(success)}):")
        for detail in success:
            doc_id = detail['doc_id']
            title = detail['title']
            size = detail.get('size', 0)
            path = detail.get('path', 'N/A')
            print(f"  Document {doc_id}: {title}")
            print(f"    Size: {size:,} bytes")
            print(f"    Path: {path}")
            print()

    if failed:
        print(f"\n✗ Failed Downloads ({len(failed)}):")
        for detail in failed:
            doc_id = detail['doc_id']
            title = detail['title']
            error = detail.get('error', 'Unknown')
            print(f"  Document {doc_id}: {title}")
            print(f"    Error: {error}")
            print()


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Download PDFs using browser automation for Cloudflare-protected URLs'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=20,
        help='Number of documents to process in one batch (default: 20)'
    )
    parser.add_argument(
        '--max-batches',
        type=int,
        default=1,
        help='Maximum number of batches to process (default: 1)'
    )
    parser.add_argument(
        '--offset',
        type=int,
        default=0,
        help='Starting offset for document selection (default: 0)'
    )
    parser.add_argument(
        '--visible',
        action='store_true',
        help='Run browser in visible mode (default: headless)'
    )
    parser.add_argument(
        '--cloudflare-wait',
        type=int,
        default=30,
        help='Maximum seconds to wait for Cloudflare verification (default: 30)'
    )
    parser.add_argument(
        '--show-success',
        action='store_true',
        help='Show details of successful downloads (default: only failures)'
    )

    args = parser.parse_args()

    print("=" * 70)
    print("Browser-Based PDF Download Tool")
    print("=" * 70)
    print(f"Batch size: {args.batch_size}")
    print(f"Max batches: {args.max_batches}")
    print(f"Browser mode: {'visible' if args.visible else 'headless'}")
    print(f"Cloudflare wait: {args.cloudflare_wait}s")
    print("=" * 70)

    # Connect to database
    print("\nConnecting to database...")
    conn = get_database_connection()
    print("✓ Connected successfully")

    # Initialize PDF manager
    pdf_base_dir = os.getenv('PDF_BASE_DIR', '~/knowledgebase/pdf')
    pdf_base_dir = Path(pdf_base_dir).expanduser()
    print(f"\nPDF Base Directory: {pdf_base_dir}")

    pdf_manager = PDFManager(base_dir=pdf_base_dir, db_conn=conn)

    total_stats = {
        'total': 0,
        'already_exists': 0,
        'success': 0,
        'failed': 0,
        'details': []
    }

    # Process batches
    for batch_num in range(args.max_batches):
        offset = args.offset + (batch_num * args.batch_size)

        print(f"\n{'='*70}")
        print(f"Processing Batch {batch_num + 1}/{args.max_batches} (offset: {offset})")
        print(f"{'='*70}")

        # Find documents
        documents = find_documents_needing_browser_download(
            conn,
            batch_size=args.batch_size,
            offset=offset
        )

        if not documents:
            print("No more documents to process")
            break

        print(f"Found {len(documents)} documents with pdf_url")

        # Download batch
        batch_stats = await download_batch_with_browser(
            documents=documents,
            pdf_manager=pdf_manager,
            headless=not args.visible,
            max_wait_cloudflare=args.cloudflare_wait
        )

        # Accumulate stats
        total_stats['total'] += batch_stats['total']
        total_stats['already_exists'] += batch_stats['already_exists']
        total_stats['success'] += batch_stats['success']
        total_stats['failed'] += batch_stats['failed']
        total_stats['details'].extend(batch_stats['details'])

        print_summary(batch_stats)

    # Print final summary
    print("\n" + "=" * 70)
    print("FINAL SUMMARY (All Batches)")
    print_summary(total_stats)
    print_details(total_stats, show_success=args.show_success)

    print("\n✓ Browser download completed!")
    if total_stats['success'] > 0:
        print(f"   ✅ {total_stats['success']} PDFs successfully downloaded.")
    if total_stats['failed'] > 0:
        print(f"   ⚠️  {total_stats['failed']} downloads failed.")

    conn.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nDownload interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
