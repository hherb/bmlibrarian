#!/usr/bin/env python3

"""Full-text discovery CLI.

 

Discovers and downloads PDF full-text from multiple sources, prioritizing

open access when available.

 

Usage:

    # Discover sources for a DOI

    uv run python fulltext_discovery_cli.py discover --doi "10.1038/s41586-024-07386-0"

 

    # Discover sources for a PMID

    uv run python fulltext_discovery_cli.py discover --pmid 12345678

 

    # Download PDF for a DOI

    uv run python fulltext_discovery_cli.py download --doi "10.1038/s41586-024-07386-0" -o paper.pdf

 

    # Batch download missing PDFs from database

    uv run python fulltext_discovery_cli.py batch --limit 100

 

    # Show statistics

    uv run python fulltext_discovery_cli.py status

"""

 

import argparse

import json

import logging

import os

import sys

from pathlib import Path

from typing import Optional

 

from dotenv import load_dotenv

 

# Add src to path

sys.path.insert(0, str(Path(__file__).parent / 'src'))

 

from bmlibrarian.discovery import (

    FullTextFinder, DocumentIdentifiers, DiscoveryResult,

    SourceType, AccessType

)

 

# Configure logging

logging.basicConfig(

    level=logging.INFO,

    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'

)

logger = logging.getLogger(__name__)

 

 

def print_banner():

    """Print CLI banner."""

    print("=" * 70)

    print("Full-Text Discovery Tool")

    print("=" * 70)

    print()

 

 

def print_discovery_result(result: DiscoveryResult, verbose: bool = False):

    """Print discovery result in formatted output.

 

    Args:

        result: DiscoveryResult to print

        verbose: Show detailed information

    """

    print("\n" + "-" * 70)

    print("Discovery Results")

    print("-" * 70)

 

    # Print identifiers

    ids = result.identifiers

    print(f"\nIdentifiers:")

    if ids.doi:

        print(f"  DOI:   {ids.doi}")

    if ids.pmid:

        print(f"  PMID:  {ids.pmid}")

    if ids.pmcid:

        print(f"  PMCID: {ids.pmcid}")

    if ids.pdf_url:

        print(f"  URL:   {ids.pdf_url}")

 

    # Print timing

    print(f"\nTotal time: {result.total_duration_ms:.0f}ms")

 

    # Print resolver results

    if verbose:

        print(f"\nResolver Results:")

        for res in result.resolution_results:

            status_icon = "✓" if res.sources else "✗"

            print(f"  {status_icon} {res.resolver_name}: {res.status.value} "

                  f"({res.duration_ms:.0f}ms)")

            if res.error_message:

                print(f"      Error: {res.error_message}")

 

    # Print sources

    print(f"\nFound {len(result.sources)} source(s):")

    if not result.sources:

        print("  No PDF sources found")

    else:

        for i, source in enumerate(result.sources, 1):

            access_icon = "🔓" if source.access_type == AccessType.OPEN else "🔒"

            best_marker = " ⭐" if source == result.best_source else ""

            print(f"\n  {i}. {access_icon} {source.source_type.value}{best_marker}")

            print(f"     URL: {source.url[:80]}{'...' if len(source.url) > 80 else ''}")

            print(f"     Access: {source.access_type.value}")

            print(f"     Priority: {source.priority}")

            if source.license:

                print(f"     License: {source.license}")

            if source.version:

                print(f"     Version: {source.version}")

            if source.host_type:

                print(f"     Host: {source.host_type}")

 

    # Summary

    print("\n" + "-" * 70)

    if result.has_open_access():

        print("✓ Open access PDF available!")

    elif result.sources:

        print("⚠ No open access found, institutional access may be required")

    else:

        print("✗ No PDF sources found")

    print("-" * 70)

 

 

def cmd_discover(args):

    """Handle discover command."""

    # Build identifiers

    identifiers = DocumentIdentifiers(

        doi=args.doi,

        pmid=args.pmid,

        pmcid=args.pmcid,

        pdf_url=args.url

    )

 

    if not identifiers.has_identifiers():

        print("Error: At least one identifier (--doi, --pmid, --pmcid, --url) is required")

        return 1

 

    # Create finder

    finder = FullTextFinder(

        unpaywall_email=args.email,

        openathens_proxy_url=args.openathens_url,

        timeout=args.timeout

    )

 

    # Progress callback

    def progress(resolver: str, status: str):

        if args.verbose:

            print(f"  [{resolver}] {status}")

 

    print("Discovering PDF sources...")

    result = finder.discover(

        identifiers,

        stop_on_first_oa=not args.all_sources,

        progress_callback=progress if args.verbose else None

    )

 

    # Print results

    print_discovery_result(result, verbose=args.verbose)

 

    # Output JSON if requested

    if args.json:

        output = {

            'identifiers': {

                'doi': identifiers.doi,

                'pmid': identifiers.pmid,

                'pmcid': identifiers.pmcid,

                'pdf_url': identifiers.pdf_url

            },

            'sources': [

                {

                    'url': s.url,

                    'source_type': s.source_type.value,

                    'access_type': s.access_type.value,

                    'priority': s.priority,

                    'license': s.license,

                    'version': s.version,

                    'is_best': s == result.best_source

                }

                for s in result.sources

            ],

            'has_open_access': result.has_open_access(),

            'total_duration_ms': result.total_duration_ms

        }

        print(f"\nJSON Output:\n{json.dumps(output, indent=2)}")

 

    return 0 if result.sources else 1

 

 

def cmd_download(args):

    """Handle download command."""

    # Build identifiers

    identifiers = DocumentIdentifiers(

        doi=args.doi,

        pmid=args.pmid,

        pmcid=args.pmcid,

        pdf_url=args.url

    )

 

    if not identifiers.has_identifiers():

        print("Error: At least one identifier (--doi, --pmid, --pmcid, --url) is required")

        return 1

 

    # Determine output path

    output_path = Path(args.output) if args.output else None

    if not output_path:

        # Generate filename from DOI or PMID

        if identifiers.doi:

            safe_doi = identifiers.doi.replace('/', '_').replace('\\', '_')

            output_path = Path(f"{safe_doi}.pdf")

        elif identifiers.pmid:

            output_path = Path(f"pmid_{identifiers.pmid}.pdf")

        elif identifiers.pmcid:

            output_path = Path(f"{identifiers.pmcid}.pdf")

        else:

            output_path = Path("download.pdf")

 

    # Check if file exists

    if output_path.exists() and not args.force:

        print(f"Error: File already exists: {output_path}")

        print("Use --force to overwrite")

        return 1

 

    # Create finder with optional OpenAthens

    openathens_auth = None

    if args.openathens_url:

        try:

            from bmlibrarian.utils.openathens_auth import OpenAthensConfig, OpenAthensAuth

            config = OpenAthensConfig(institution_url=args.openathens_url)

            openathens_auth = OpenAthensAuth(config=config)

        except ImportError:

            logger.warning("OpenAthens auth not available")

 

    finder = FullTextFinder(

        unpaywall_email=args.email,

        openathens_proxy_url=args.openathens_url,

        openathens_auth=openathens_auth,

        timeout=args.timeout

    )

 

    # Progress callback

    def progress(stage: str, status: str):

        print(f"  [{stage}] {status}")

 

    print(f"Discovering and downloading PDF...")

    print(f"Output: {output_path}")

 

    result = finder.discover_and_download(

        identifiers,

        output_path=output_path,

        max_attempts=args.retries,

        progress_callback=progress

    )

 

    if result.success:

        print(f"\n✓ Downloaded successfully!")

        print(f"  File: {result.file_path}")

        print(f"  Size: {result.file_size:,} bytes")

        print(f"  Source: {result.source.source_type.value if result.source else 'unknown'}")

        print(f"  Time: {result.duration_ms:.0f}ms")

        return 0

    else:

        print(f"\n✗ Download failed: {result.error_message}")

        return 1

 

 

def cmd_batch(args):

    """Handle batch download command."""

    import psycopg

 

    load_dotenv()

 

    # Connect to database

    db_params = {

        'dbname': os.getenv('POSTGRES_DB', 'knowledgebase'),

        'user': os.getenv('POSTGRES_USER', 'postgres'),

        'password': os.getenv('POSTGRES_PASSWORD', ''),

        'host': os.getenv('POSTGRES_HOST', 'localhost'),

        'port': os.getenv('POSTGRES_PORT', '5432')

    }

 

    print("Connecting to database...")

    try:

        conn = psycopg.connect(**db_params)

        print(f"✓ Connected to {db_params['dbname']}")

    except Exception as e:

        print(f"✗ Failed to connect: {e}")

        return 1

 

    # Get PDF base directory

    pdf_base_dir = Path(os.getenv('PDF_BASE_DIR', '~/knowledgebase/pdf')).expanduser()

    print(f"PDF directory: {pdf_base_dir}")

 

    # Create finder

    finder = FullTextFinder(

        unpaywall_email=args.email,

        openathens_proxy_url=args.openathens_url,

        timeout=args.timeout

    )

 

    # Query documents needing PDFs

    print("\nFinding documents without local PDFs...")

    with conn.cursor() as cursor:

        cursor.execute("""

            SELECT id, doi, title, publication_date, pdf_filename, pdf_url

            FROM document

            WHERE doi IS NOT NULL

            AND (pdf_filename IS NULL OR pdf_filename = '')

            ORDER BY publication_date DESC NULLS LAST

            LIMIT %s

        """, (args.limit,))

        documents = cursor.fetchall()

 

    print(f"Found {len(documents)} documents to process")

 

    if not documents:

        print("No documents need PDF downloads")

        conn.close()

        return 0

 

    # Process documents

    stats = {

        'processed': 0,

        'downloaded': 0,

        'failed': 0,

        'no_source': 0

    }

 

    for doc_id, doi, title, pub_date, pdf_filename, pdf_url in documents:

        stats['processed'] += 1

 

        # Extract year for directory

        year = 'unknown'

        if pub_date:

            year = str(pub_date.year) if hasattr(pub_date, 'year') else str(pub_date)[:4]

 

        # Generate output path

        safe_doi = doi.replace('/', '_').replace('\\', '_')

        output_path = pdf_base_dir / year / f"{safe_doi}.pdf"

 

        print(f"\n[{stats['processed']}/{len(documents)}] {doi}")

        if title:

            print(f"  Title: {title[:60]}...")

 

        # Build identifiers

        identifiers = DocumentIdentifiers(

            doc_id=doc_id,

            doi=doi,

            pdf_url=pdf_url

        )

 

        # Check if already exists

        if output_path.exists():

            print(f"  ✓ Already exists: {output_path}")

            stats['downloaded'] += 1

            continue

 

        # Discover and download

        result = finder.discover_and_download(

            identifiers,

            output_path=output_path,

            max_attempts=2

        )

 

        if result.success:

            print(f"  ✓ Downloaded ({result.file_size:,} bytes)")

 

            # Update database

            relative_path = f"{year}/{safe_doi}.pdf"

            try:

                with conn.cursor() as cursor:

                    cursor.execute(

                        "UPDATE document SET pdf_filename = %s WHERE id = %s",

                        (relative_path, doc_id)

                    )

                conn.commit()

            except Exception as e:

                logger.error(f"Failed to update database: {e}")

                conn.rollback()

 

            stats['downloaded'] += 1

        else:

            if "No PDF sources found" in str(result.error_message):

                print(f"  ✗ No sources found")

                stats['no_source'] += 1

            else:

                print(f"  ✗ Failed: {result.error_message}")

                stats['failed'] += 1

 

    # Print summary

    print("\n" + "=" * 70)

    print("Batch Download Summary")

    print("=" * 70)

    print(f"Processed:    {stats['processed']}")

    print(f"Downloaded:   {stats['downloaded']}")

    print(f"No source:    {stats['no_source']}")

    print(f"Failed:       {stats['failed']}")

    print("=" * 70)

 

    conn.close()

    return 0

 

 

def cmd_status(args):

    """Handle status command."""

    import psycopg

 

    load_dotenv()

 

    # Connect to database

    db_params = {

        'dbname': os.getenv('POSTGRES_DB', 'knowledgebase'),

        'user': os.getenv('POSTGRES_USER', 'postgres'),

        'password': os.getenv('POSTGRES_PASSWORD', ''),

        'host': os.getenv('POSTGRES_HOST', 'localhost'),

        'port': os.getenv('POSTGRES_PORT', '5432')

    }

 

    print("Connecting to database...")

    try:

        conn = psycopg.connect(**db_params)

    except Exception as e:

        print(f"✗ Failed to connect: {e}")

        return 1

 

    print("\n" + "=" * 70)

    print("Full-Text Coverage Statistics")

    print("=" * 70)

 

    with conn.cursor() as cursor:

        # Total documents

        cursor.execute("SELECT COUNT(*) FROM document")

        total = cursor.fetchone()[0]

        print(f"\nTotal documents: {total:,}")

 

        # Documents with DOI

        cursor.execute("SELECT COUNT(*) FROM document WHERE doi IS NOT NULL")

        with_doi = cursor.fetchone()[0]

        print(f"With DOI: {with_doi:,} ({with_doi/total*100:.1f}%)")

 

        # Documents with PDF filename

        cursor.execute("""

            SELECT COUNT(*) FROM document

            WHERE pdf_filename IS NOT NULL AND pdf_filename != ''

        """)

        with_pdf = cursor.fetchone()[0]

        print(f"With local PDF: {with_pdf:,} ({with_pdf/total*100:.1f}%)")

 

        # Documents with PDF URL but no local file

        cursor.execute("""

            SELECT COUNT(*) FROM document

            WHERE pdf_url IS NOT NULL

            AND (pdf_filename IS NULL OR pdf_filename = '')

        """)

        need_download = cursor.fetchone()[0]

        print(f"Have URL, need download: {need_download:,}")

 

        # Documents with DOI but no PDF

        cursor.execute("""

            SELECT COUNT(*) FROM document

            WHERE doi IS NOT NULL

            AND (pdf_filename IS NULL OR pdf_filename = '')

        """)

        doi_no_pdf = cursor.fetchone()[0]

        print(f"Have DOI, no PDF: {doi_no_pdf:,}")

 

        # Coverage gap

        gap = total - with_pdf

        print(f"\nCoverage gap: {gap:,} documents ({gap/total*100:.1f}%)")

 

    print("=" * 70)

    conn.close()

    return 0

 

 

def main():

    """Main entry point."""

    parser = argparse.ArgumentParser(

        description='Full-text PDF discovery and download tool',

        formatter_class=argparse.RawDescriptionHelpFormatter,

        epilog=__doc__

    )

 

    # Global options

    parser.add_argument(

        '--email',

        default=os.getenv('UNPAYWALL_EMAIL', 'bmlibrarian@example.com'),

        help='Email for Unpaywall API'

    )

    parser.add_argument(

        '--openathens-url',

        default=os.getenv('OPENATHENS_URL'),

        help='OpenAthens proxy URL for institutional access'

    )

    parser.add_argument(

        '--timeout',

        type=int,

        default=30,

        help='HTTP request timeout in seconds (default: 30)'

    )

    parser.add_argument(

        '-v', '--verbose',

        action='store_true',

        help='Verbose output'

    )

 

    subparsers = parser.add_subparsers(dest='command', help='Commands')

 

    # Discover command

    discover_parser = subparsers.add_parser(

        'discover',

        help='Discover PDF sources for a document'

    )

    discover_parser.add_argument('--doi', help='Document DOI')

    discover_parser.add_argument('--pmid', help='PubMed ID')

    discover_parser.add_argument('--pmcid', help='PubMed Central ID')

    discover_parser.add_argument('--url', help='Direct PDF URL')

    discover_parser.add_argument(

        '--all-sources',

        action='store_true',

        help='Find all sources, not just first OA'

    )

    discover_parser.add_argument(

        '--json',

        action='store_true',

        help='Output results as JSON'

    )

 

    # Download command

    download_parser = subparsers.add_parser(

        'download',

        help='Download PDF for a document'

    )

    download_parser.add_argument('--doi', help='Document DOI')

    download_parser.add_argument('--pmid', help='PubMed ID')

    download_parser.add_argument('--pmcid', help='PubMed Central ID')

    download_parser.add_argument('--url', help='Direct PDF URL')

    download_parser.add_argument(

        '-o', '--output',

        help='Output file path (default: generated from identifier)'

    )

    download_parser.add_argument(

        '-f', '--force',

        action='store_true',

        help='Overwrite existing file'

    )

    download_parser.add_argument(

        '--retries',

        type=int,

        default=3,

        help='Maximum retry attempts (default: 3)'

    )

 

    # Batch command

    batch_parser = subparsers.add_parser(

        'batch',

        help='Batch download missing PDFs from database'

    )

    batch_parser.add_argument(

        '--limit',

        type=int,

        default=100,

        help='Maximum documents to process (default: 100)'

    )

 

    # Status command

    subparsers.add_parser(

        'status',

        help='Show full-text coverage statistics'

    )

 

    args = parser.parse_args()

 

    if args.verbose:

        logging.getLogger().setLevel(logging.DEBUG)

 

    print_banner()

 

    if args.command == 'discover':

        return cmd_discover(args)

    elif args.command == 'download':

        return cmd_download(args)

    elif args.command == 'batch':

        return cmd_batch(args)

    elif args.command == 'status':

        return cmd_status(args)

    else:

        parser.print_help()

        return 0

 

 

if __name__ == '__main__':

    sys.exit(main())