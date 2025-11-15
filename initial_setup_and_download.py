#!/usr/bin/env python3
"""
Initial Setup and Download Script for BMLibrarian

This script battle-tests the PostgreSQL database setup and import scripts by:
1. Loading connection parameters from a .env file
2. Creating the database schema including all migrations
3. Running MedRxiv import
4. Running PubMed import

Usage:
    python initial_setup_and_download.py test_database.env
    python initial_setup_and_download.py test_database.env --skip-medrxiv
    python initial_setup_and_download.py test_database.env --skip-pubmed
    python initial_setup_and_download.py test_database.env --medrxiv-days 7 --pubmed-max-results 50
"""

import argparse
import logging
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def load_env_file(env_file_path: Path) -> dict:
    """
    Load environment variables from a .env style file.

    Args:
        env_file_path: Path to the .env file

    Returns:
        Dictionary of environment variables

    Raises:
        FileNotFoundError: If env file doesn't exist
        ValueError: If required variables are missing
    """
    if not env_file_path.exists():
        raise FileNotFoundError(f"Environment file not found: {env_file_path}")

    env_vars = {}

    print(f"\n{'='*70}")
    print(f"Loading environment from: {env_file_path}")
    print(f"{'='*70}")

    with open(env_file_path, 'r') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue

            # Parse KEY=VALUE format
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()

                # Remove quotes if present
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]

                env_vars[key] = value
                os.environ[key] = value

                # Print loaded variable (mask password)
                if 'PASSWORD' in key.upper():
                    print(f"  {key}=***MASKED***")
                else:
                    print(f"  {key}={value}")
            else:
                logger.warning(f"Skipping invalid line {line_num}: {line}")

    # Validate required variables
    required_vars = ['POSTGRES_HOST', 'POSTGRES_USER', 'POSTGRES_PASSWORD', 'POSTGRES_DB']
    missing_vars = [var for var in required_vars if var not in env_vars]

    if missing_vars:
        raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

    # Set defaults for optional variables
    env_vars.setdefault('POSTGRES_PORT', '5432')
    env_vars.setdefault('PDF_BASE_DIR', '~/knowledgebase/pdf')

    print(f"\nLoaded {len(env_vars)} environment variables")
    print(f"{'='*70}\n")

    return env_vars


def setup_database_schema(env_vars: dict) -> bool:
    """
    Set up the database schema including baseline and migrations.

    Args:
        env_vars: Environment variables dictionary

    Returns:
        True if successful, False otherwise
    """
    print(f"\n{'='*70}")
    print("DATABASE SCHEMA SETUP")
    print(f"{'='*70}\n")

    try:
        from src.bmlibrarian.migrations import MigrationManager

        # Create migration manager
        manager = MigrationManager(
            host=env_vars['POSTGRES_HOST'],
            port=env_vars['POSTGRES_PORT'],
            user=env_vars['POSTGRES_USER'],
            password=env_vars['POSTGRES_PASSWORD'],
            database=env_vars['POSTGRES_DB']
        )

        # Initialize database with baseline schema
        baseline_path = Path(__file__).parent / 'baseline_schema.sql'

        if not baseline_path.exists():
            logger.error(f"Baseline schema not found: {baseline_path}")
            return False

        print("Step 1: Initialize database with baseline schema")
        print("-" * 70)
        manager.initialize_database(baseline_path)

        # Apply migrations
        migrations_dir = Path(__file__).parent / 'migrations'

        print(f"\nStep 2: Apply migrations from {migrations_dir}")
        print("-" * 70)

        if not migrations_dir.exists():
            logger.warning(f"Migrations directory not found: {migrations_dir}")
            print("No migrations to apply.")
        else:
            applied_count = manager.apply_pending_migrations(migrations_dir, silent=False)
            print(f"\nTotal migrations applied: {applied_count}")

        print(f"\n{'='*70}")
        print("✓ DATABASE SCHEMA SETUP COMPLETE")
        print(f"{'='*70}\n")

        return True

    except Exception as e:
        logger.error(f"Database schema setup failed: {e}", exc_info=True)
        print(f"\n{'='*70}")
        print("✗ DATABASE SCHEMA SETUP FAILED")
        print(f"{'='*70}\n")
        return False


def run_medrxiv_import(env_vars: dict, days_to_fetch: int = 7, download_pdfs: bool = False) -> bool:
    """
    Run MedRxiv import test.

    Args:
        env_vars: Environment variables dictionary
        days_to_fetch: Number of days back to fetch
        download_pdfs: Whether to download PDFs

    Returns:
        True if successful, False otherwise
    """
    print(f"\n{'='*70}")
    print("MEDRXIV IMPORT TEST")
    print(f"{'='*70}")
    print(f"Days to fetch: {days_to_fetch}")
    print(f"Download PDFs: {download_pdfs}")
    print(f"{'='*70}\n")

    try:
        from src.bmlibrarian.importers import MedRxivImporter

        # Create importer
        pdf_dir = env_vars.get('PDF_BASE_DIR', '~/knowledgebase/pdf')
        importer = MedRxivImporter(pdf_base_dir=pdf_dir)

        # Run update
        print("Starting MedRxiv import...")
        stats = importer.update_database(
            download_pdfs=download_pdfs,
            days_to_fetch=days_to_fetch,
            max_retries=3
        )

        print(f"\n{'='*70}")
        print("✓ MEDRXIV IMPORT COMPLETE")
        print(f"{'='*70}")
        print(f"Total papers processed: {stats.get('total_processed', 0)}")
        print(f"Dates processed: {stats.get('dates_processed', 0)}")
        print(f"{'='*70}\n")

        return True

    except Exception as e:
        logger.error(f"MedRxiv import failed: {e}", exc_info=True)
        print(f"\n{'='*70}")
        print("✗ MEDRXIV IMPORT FAILED")
        print(f"{'='*70}\n")
        return False


def run_pubmed_import(env_vars: dict, max_results: int = 100) -> bool:
    """
    Run PubMed import test.

    Args:
        env_vars: Environment variables dictionary
        max_results: Maximum number of results to import

    Returns:
        True if successful, False otherwise
    """
    print(f"\n{'='*70}")
    print("PUBMED IMPORT TEST")
    print(f"{'='*70}")
    print(f"Search query: COVID-19 vaccine")
    print(f"Max results: {max_results}")
    print(f"{'='*70}\n")

    try:
        from src.bmlibrarian.importers import PubMedImporter

        # Create importer
        email = env_vars.get('NCBI_EMAIL', '')
        api_key = env_vars.get('NCBI_API_KEY', '')

        importer = PubMedImporter(email=email, api_key=api_key)

        # Run search import
        print("Starting PubMed import...")
        stats = importer.import_by_search(
            query="COVID-19 vaccine",
            max_results=max_results
        )

        print(f"\n{'='*70}")
        print("✓ PUBMED IMPORT COMPLETE")
        print(f"{'='*70}")
        print(f"Total found: {stats.get('total_found', 0)}")
        print(f"Parsed: {stats.get('parsed', stats.get('total_found', 0))}")
        print(f"Imported: {stats.get('imported', 0)}")
        if stats.get('total_found', 0) > 0:
            import_rate = 100 * stats.get('imported', 0) / stats['total_found']
            print(f"Import rate: {import_rate:.1f}%")
        print(f"{'='*70}\n")

        return True

    except Exception as e:
        logger.error(f"PubMed import failed: {e}", exc_info=True)
        print(f"\n{'='*70}")
        print("✗ PUBMED IMPORT FAILED")
        print(f"{'='*70}\n")
        return False


def print_final_summary(results: dict):
    """Print final summary of all operations."""
    print(f"\n{'='*70}")
    print("BATTLE TEST SUMMARY")
    print(f"{'='*70}")

    for operation, success in results.items():
        status = "✓ PASSED" if success else "✗ FAILED"
        print(f"{operation:.<50} {status}")

    print(f"{'='*70}")

    total = len(results)
    passed = sum(1 for v in results.values() if v)
    failed = total - passed

    print(f"\nTotal operations: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"{'='*70}\n")

    return failed == 0


def main():
    """Main entry point for the setup script."""
    parser = argparse.ArgumentParser(
        description='Initialize BMLibrarian database and test import scripts',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        'env_file',
        type=str,
        help='Path to .env file with database connection parameters'
    )

    parser.add_argument(
        '--skip-medrxiv',
        action='store_true',
        help='Skip MedRxiv import test'
    )

    parser.add_argument(
        '--skip-pubmed',
        action='store_true',
        help='Skip PubMed import test'
    )

    parser.add_argument(
        '--medrxiv-days',
        type=int,
        default=7,
        help='Number of days to fetch for MedRxiv (default: 7)'
    )

    parser.add_argument(
        '--medrxiv-download-pdfs',
        action='store_true',
        help='Download PDFs during MedRxiv import'
    )

    parser.add_argument(
        '--pubmed-max-results',
        type=int,
        default=100,
        help='Maximum PubMed results to import (default: 100)'
    )

    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )

    args = parser.parse_args()

    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Print banner
    print("\n" + "="*70)
    print("BMLibrarian - Database Setup and Import Battle Test")
    print("="*70)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)

    results = {}

    try:
        # Step 1: Load environment file
        env_file_path = Path(args.env_file)
        env_vars = load_env_file(env_file_path)

        # Step 2: Setup database schema
        results['Database Schema Setup'] = setup_database_schema(env_vars)

        if not results['Database Schema Setup']:
            print("\n⚠️  Database setup failed. Skipping import tests.")
            print_final_summary(results)
            return 1

        # Step 3: Run MedRxiv import (if not skipped)
        if not args.skip_medrxiv:
            results['MedRxiv Import'] = run_medrxiv_import(
                env_vars,
                days_to_fetch=args.medrxiv_days,
                download_pdfs=args.medrxiv_download_pdfs
            )
        else:
            print("\n⚠️  Skipping MedRxiv import (--skip-medrxiv)")

        # Step 4: Run PubMed import (if not skipped)
        if not args.skip_pubmed:
            results['PubMed Import'] = run_pubmed_import(
                env_vars,
                max_results=args.pubmed_max_results
            )
        else:
            print("\n⚠️  Skipping PubMed import (--skip-pubmed)")

        # Print final summary
        success = print_final_summary(results)

        print(f"Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*70 + "\n")

        return 0 if success else 1

    except KeyboardInterrupt:
        print("\n\n⚠️  Operation cancelled by user")
        return 130

    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        print(f"\n{'='*70}")
        print("✗ FATAL ERROR")
        print(f"{'='*70}")
        print(f"{e}")
        print(f"{'='*70}\n")
        return 1


if __name__ == '__main__':
    sys.exit(main())
