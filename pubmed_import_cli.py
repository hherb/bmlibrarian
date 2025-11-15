#!/usr/bin/env python3
"""
PubMed Import CLI for BMLibrarian

Command-line interface for importing biomedical articles from PubMed into the
BMLibrarian knowledge base.

Usage:
    # Import by search query
    python pubmed_import_cli.py search "COVID-19 vaccine" --max-results 100

    # Import by PMID list
    python pubmed_import_cli.py pmids 12345678 23456789 34567890

    # Import from PMID file
    python pubmed_import_cli.py pmids --from-file pmids.txt

    # Show import status
    python pubmed_import_cli.py status
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from src.bmlibrarian.importers import PubMedImporter


def setup_logging(verbose: bool = False):
    """Configure logging for the CLI."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def cmd_search(args):
    """Execute the search command."""
    print("=" * 70)
    print("PubMed Import - Search")
    print("=" * 70)
    print(f"Query: {args.query}")
    print(f"Max results: {args.max_results}")
    if args.min_date:
        print(f"Min date: {args.min_date}")
    if args.max_date:
        print(f"Max date: {args.max_date}")
    print("=" * 70)

    try:
        importer = PubMedImporter(email=args.email, api_key=args.api_key)

        stats = importer.import_by_search(
            query=args.query,
            max_results=args.max_results,
            min_date=args.min_date,
            max_date=args.max_date
        )

        print("\n" + "=" * 70)
        print("Import Complete!")
        print("=" * 70)
        print(f"Total found: {stats['total_found']}")
        print(f"Parsed: {stats.get('parsed', stats['total_found'])}")
        print(f"Imported: {stats['imported']}")
        if stats['total_found'] > 0:
            import_rate = 100 * stats['imported'] / stats['total_found']
            print(f"Import rate: {import_rate:.1f}%")
        print("=" * 70)

        return 0

    except Exception as e:
        logging.error(f"Error during import: {e}", exc_info=True)
        return 1


def cmd_pmids(args):
    """Execute the PMIDs import command."""
    print("=" * 70)
    print("PubMed Import - PMIDs")
    print("=" * 70)

    # Collect PMIDs from command line or file
    pmids = []

    if args.from_file:
        print(f"Reading PMIDs from: {args.from_file}")
        try:
            with open(args.from_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        # Handle comma-separated values
                        pmids.extend([p.strip() for p in line.split(',') if p.strip()])
        except Exception as e:
            print(f"Error reading file: {e}")
            return 1
    elif args.pmids:
        pmids = args.pmids
    else:
        print("Error: No PMIDs provided. Use --pmids or --from-file")
        return 1

    print(f"Total PMIDs to import: {len(pmids)}")
    print("=" * 70)

    try:
        importer = PubMedImporter(email=args.email, api_key=args.api_key)

        stats = importer.import_by_pmids(pmids)

        print("\n" + "=" * 70)
        print("Import Complete!")
        print("=" * 70)
        print(f"Total requested: {stats['total_requested']}")
        print(f"Parsed: {stats.get('parsed', stats['total_requested'])}")
        print(f"Imported: {stats['imported']}")
        if stats['total_requested'] > 0:
            import_rate = 100 * stats['imported'] / stats['total_requested']
            print(f"Import rate: {import_rate:.1f}%")
        print("=" * 70)

        return 0

    except Exception as e:
        logging.error(f"Error during import: {e}", exc_info=True)
        return 1


def cmd_status(args):
    """Show PubMed import status."""
    print("=" * 70)
    print("PubMed Import Status")
    print("=" * 70)

    try:
        from bmlibrarian.database import get_db_manager

        importer = PubMedImporter(email=args.email, api_key=args.api_key)
        db_manager = get_db_manager()

        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                # Count total PubMed articles
                cur.execute("""
                    SELECT COUNT(*) FROM document d
                    JOIN sources s ON d.source_id = s.id
                    WHERE LOWER(s.name) LIKE '%pubmed%'
                """)
                total_count = cur.fetchone()[0]

                # Count with abstracts
                cur.execute("""
                    SELECT COUNT(*) FROM document d
                    JOIN sources s ON d.source_id = s.id
                    WHERE LOWER(s.name) LIKE '%pubmed%'
                    AND d.abstract IS NOT NULL AND d.abstract != ''
                """)
                with_abstract = cur.fetchone()[0]

                # Count with DOI
                cur.execute("""
                    SELECT COUNT(*) FROM document d
                    JOIN sources s ON d.source_id = s.id
                    WHERE LOWER(s.name) LIKE '%pubmed%'
                    AND d.doi IS NOT NULL
                """)
                with_doi = cur.fetchone()[0]

                # Count with MeSH terms
                cur.execute("""
                    SELECT COUNT(*) FROM document d
                    JOIN sources s ON d.source_id = s.id
                    WHERE LOWER(s.name) LIKE '%pubmed%'
                    AND d.mesh_terms IS NOT NULL
                    AND array_length(d.mesh_terms, 1) > 0
                """)
                with_mesh = cur.fetchone()[0]

                # Most recent import
                cur.execute("""
                    SELECT MAX(d.added_date) FROM document d
                    JOIN sources s ON d.source_id = s.id
                    WHERE LOWER(s.name) LIKE '%pubmed%'
                """)
                last_import = cur.fetchone()[0]

                # Publication date range
                cur.execute("""
                    SELECT MIN(d.publication_date), MAX(d.publication_date)
                    FROM document d
                    JOIN sources s ON d.source_id = s.id
                    WHERE LOWER(s.name) LIKE '%pubmed%'
                    AND d.publication_date IS NOT NULL
                """)
                date_range = cur.fetchone()
                min_date, max_date = date_range if date_range else (None, None)

        print(f"\nTotal PubMed articles: {total_count}")
        print(f"With abstracts: {with_abstract} ({100*with_abstract/total_count if total_count else 0:.1f}%)")
        print(f"With DOI: {with_doi} ({100*with_doi/total_count if total_count else 0:.1f}%)")
        print(f"With MeSH terms: {with_mesh} ({100*with_mesh/total_count if total_count else 0:.1f}%)")

        if last_import:
            print(f"\nLast import: {last_import}")

        if min_date or max_date:
            print(f"\nPublication date range:")
            if min_date:
                print(f"  Earliest: {min_date}")
            if max_date:
                print(f"  Latest: {max_date}")

        print("=" * 70)

        return 0

    except Exception as e:
        logging.error(f"Error getting status: {e}", exc_info=True)
        return 1


def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description='Import biomedical articles from PubMed into BMLibrarian',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )

    parser.add_argument(
        '--email',
        type=str,
        help='Email for NCBI (recommended but not required)'
    )

    parser.add_argument(
        '--api-key',
        type=str,
        help='NCBI API key for higher rate limits (optional)'
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to execute')

    # Search command
    search_parser = subparsers.add_parser(
        'search',
        help='Import articles by PubMed search query'
    )
    search_parser.add_argument(
        'query',
        type=str,
        help='PubMed search query (e.g., "COVID-19 vaccine")'
    )
    search_parser.add_argument(
        '--max-results',
        type=int,
        default=100,
        help='Maximum number of results to import (default: 100)'
    )
    search_parser.add_argument(
        '--min-date',
        type=str,
        help='Minimum publication date (YYYY/MM/DD format)'
    )
    search_parser.add_argument(
        '--max-date',
        type=str,
        help='Maximum publication date (YYYY/MM/DD format)'
    )

    # PMIDs command
    pmids_parser = subparsers.add_parser(
        'pmids',
        help='Import articles by PMID list'
    )
    pmids_parser.add_argument(
        'pmids',
        type=str,
        nargs='*',
        help='PubMed IDs to import'
    )
    pmids_parser.add_argument(
        '--from-file',
        type=str,
        help='Read PMIDs from file (one per line or comma-separated)'
    )

    # Status command
    status_parser = subparsers.add_parser(
        'status',
        help='Show PubMed import status and statistics'
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(args.verbose)

    # Execute command
    if args.command == 'search':
        return cmd_search(args)
    elif args.command == 'pmids':
        return cmd_pmids(args)
    elif args.command == 'status':
        return cmd_status(args)
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())
