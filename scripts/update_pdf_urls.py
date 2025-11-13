#!/usr/bin/env python3
"""
Update document.pdf_url from unpaywall.doi_urls table.

This script updates the pdf_url column in the public.document table
with PDF URLs from the unpaywall.doi_urls table where the document's
pdf_url is currently NULL or empty.
"""

import sys
from pathlib import Path

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from bmlibrarian.database import get_db_manager

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False


def update_pdf_urls(dry_run=False, batch_size=10000):
    """
    Update document.pdf_url from unpaywall.doi_urls where pdf_url is empty.

    Args:
        dry_run: If True, only report what would be updated without making changes
        batch_size: Number of records to update per batch (default: 10000)

    Returns:
        Tuple of (total_empty, total_matched, updated_count)
    """
    import time

    db_manager = get_db_manager()

    with db_manager.get_connection() as conn:
        with conn.cursor() as cur:
            print("Analyzing database...")

            # First, check how many documents have empty pdf_url
            print("Counting documents with empty pdf_url...", flush=True)
            start = time.time()
            cur.execute("""
                SELECT COUNT(*)
                FROM public.document
                WHERE pdf_url IS NULL OR pdf_url = ''
            """)
            total_empty = cur.fetchone()[0]
            elapsed = time.time() - start
            print(f"✓ Found {total_empty:,} documents with empty pdf_url ({elapsed:.1f}s)")

            # Create a temporary table with best URLs for efficient operations
            print("\nCreating temporary table with best quality URLs...", flush=True)
            print("(This will speed up counting and all subsequent updates)")
            start = time.time()

            cur.execute("""
                CREATE TEMPORARY TABLE temp_best_urls AS
                SELECT DISTINCT ON (doi) doi, pdf_url, url_quality_score
                FROM unpaywall.doi_urls
                WHERE pdf_url IS NOT NULL AND pdf_url != ''
                ORDER BY doi, url_quality_score DESC NULLS LAST
            """)

            elapsed = time.time() - start
            print(f"✓ Temporary table created in {elapsed:.1f}s")

            # Create index on temporary table for faster joins
            print("Creating index on temporary table...", flush=True)
            start = time.time()
            cur.execute("CREATE INDEX idx_temp_best_urls_doi ON temp_best_urls(doi)")
            elapsed = time.time() - start
            print(f"✓ Index created in {elapsed:.1f}s")

            # Now count matches using the indexed temporary table
            print("Counting potential matches...", flush=True)
            start = time.time()
            cur.execute("""
                SELECT COUNT(*)
                FROM public.document d
                INNER JOIN temp_best_urls u ON d.doi = u.doi
                WHERE (d.pdf_url IS NULL OR d.pdf_url = '')
            """)
            total_matched = cur.fetchone()[0]
            elapsed = time.time() - start
            print(f"✓ Found {total_matched:,} documents that can be updated ({elapsed:.1f}s)")

            if total_matched == 0:
                print("No updates to perform.")
                return total_empty, 0, 0

            if dry_run:
                # Show sample of what would be updated
                print("\nFetching sample records...", flush=True)
                cur.execute("""
                    SELECT d.id, d.doi, d.title, u.pdf_url, u.url_quality_score
                    FROM public.document d
                    INNER JOIN temp_best_urls u ON d.doi = u.doi
                    WHERE (d.pdf_url IS NULL OR d.pdf_url = '')
                    LIMIT 10
                """)

                print("\nSample of documents that would be updated:")
                print("-" * 80)
                for row in cur.fetchall():
                    doc_id, doi, title, pdf_url, quality_score = row
                    title_short = title[:60] + "..." if len(title) > 60 else title
                    print(f"ID: {doc_id}")
                    print(f"DOI: {doi}")
                    print(f"Title: {title_short}")
                    print(f"New PDF URL: {pdf_url}")
                    print(f"Quality Score: {quality_score}")
                    print("-" * 80)

                return total_empty, total_matched, 0

            # Perform the update in batches with progress reporting
            print(f"\nUpdating {total_matched:,} records in batches of {batch_size:,}...")
            if not HAS_TQDM:
                print("(Install tqdm for enhanced progress bar: pip install tqdm)")
            print()

            updated_total = 0
            batch_num = 0
            overall_start = time.time()

            # Create progress bar if tqdm is available
            if HAS_TQDM:
                pbar = tqdm(
                    total=total_matched,
                    desc="Updating PDFs",
                    unit="docs",
                    unit_scale=True,
                    bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]'
                )

            while True:
                batch_num += 1
                batch_start = time.time()

                # Update one batch using the pre-computed best URLs
                cur.execute("""
                    UPDATE public.document d
                    SET pdf_url = u.pdf_url
                    FROM (
                        SELECT d2.id, bu.pdf_url
                        FROM public.document d2
                        INNER JOIN temp_best_urls bu ON d2.doi = bu.doi
                        WHERE (d2.pdf_url IS NULL OR d2.pdf_url = '')
                        LIMIT %s
                    ) AS u
                    WHERE d.id = u.id
                """, (batch_size,))

                batch_updated = cur.rowcount

                # Commit this batch
                conn.commit()

                batch_elapsed = time.time() - batch_start
                overall_elapsed = time.time() - overall_start
                updated_total += batch_updated

                # Update progress bar or print status
                if HAS_TQDM:
                    pbar.update(batch_updated)
                    pbar.set_postfix({
                        'batch': batch_num,
                        'batch_time': f'{batch_elapsed:.1f}s'
                    })
                else:
                    # Calculate progress and ETA for fallback display
                    progress_pct = (updated_total / total_matched) * 100
                    avg_time_per_batch = overall_elapsed / batch_num
                    remaining_batches = max(0, (total_matched - updated_total) / batch_size)
                    eta_seconds = remaining_batches * avg_time_per_batch

                    print(f"Batch {batch_num}: Updated {batch_updated:,} records in {batch_elapsed:.1f}s | "
                          f"Total: {updated_total:,}/{total_matched:,} ({progress_pct:.1f}%) | "
                          f"ETA: {eta_seconds/60:.1f}m", flush=True)

                # Stop if no more records to update
                if batch_updated == 0:
                    break

            # Close progress bar if used
            if HAS_TQDM:
                pbar.close()

            total_elapsed = time.time() - overall_start
            print(f"\n✓ Successfully updated {updated_total:,} document records in {total_elapsed/60:.1f} minutes")

            return total_empty, total_matched, updated_total


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Update document.pdf_url from unpaywall.doi_urls table'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be updated without making changes'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=10000,
        help='Number of records to update per batch (default: 10000)'
    )

    args = parser.parse_args()

    try:
        total_empty, total_matched, updated = update_pdf_urls(
            dry_run=args.dry_run,
            batch_size=args.batch_size
        )

        if args.dry_run:
            print(f"\n{'='*80}")
            print("DRY RUN - No changes were made")
            print(f"{'='*80}")
            print(f"Total documents with empty pdf_url: {total_empty}")
            print(f"Total that would be updated: {total_matched}")
            print("\nRun without --dry-run to perform the actual update")
        else:
            print(f"\n{'='*80}")
            print("UPDATE COMPLETE")
            print(f"{'='*80}")
            print(f"Total documents with empty pdf_url: {total_empty}")
            print(f"Total updated: {updated}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
