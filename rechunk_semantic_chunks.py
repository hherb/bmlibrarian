#!/usr/bin/env python3
"""
Re-chunk Semantic Chunks CLI

This script re-chunks all documents in the semantic.chunks table using the
optimized adaptive chunker with sentence boundary awareness.

Workflow:
1. Saves unique document IDs from semantic.chunks to a temporary table
2. Truncates semantic.chunks (preserves HNSW index structure, clears data)
3. Re-chunks each document using adaptive_chunker_with_positions
4. Displays progress with tqdm and reports statistics

Usage:
    uv run python rechunk_semantic_chunks.py
    uv run python rechunk_semantic_chunks.py --chunk-size 1800 --overlap 320
    uv run python rechunk_semantic_chunks.py --model snowflake-arctic-embed2:latest
    uv run python rechunk_semantic_chunks.py --dry-run  # Show what would be done

Example:
    $ uv run python rechunk_semantic_chunks.py

    Re-chunk Semantic Chunks
    ========================
    Model: snowflake-arctic-embed2:latest
    Chunk size: 1800 chars
    Overlap: 320 chars

    Step 1: Collecting document IDs...
    Found 1,234 documents to rechunk

    Step 2: Truncating semantic.chunks...
    Table truncated (HNSW index preserved)

    Step 3: Re-chunking documents...
    Processing: 100%|████████████████| 1234/1234 [15:23<00:00, 1.34doc/s]

    Statistics
    ==========
    Documents processed: 1,234
    Documents failed: 0
    Total chunks created: 5,678
    Time elapsed: 923.45s
    Processing rate: 6.15 chunks/s
    Average chunks/doc: 4.60
"""

import argparse
import logging
import sys
import time
from datetime import timedelta

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Suppress noisy HTTP request logging from httpx (used by ollama)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

try:
    from tqdm import tqdm
except ImportError:
    logger.error("tqdm is required. Install with: uv add tqdm")
    sys.exit(1)

from bmlibrarian.embeddings.chunk_embedder import (
    ChunkEmbedder,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_EMBEDDING_MODEL_NAME,
)
from bmlibrarian.database import get_db_manager


def format_duration(seconds: float) -> str:
    """Format seconds into a human-readable duration string."""
    td = timedelta(seconds=int(seconds))
    hours, remainder = divmod(td.seconds, 3600)
    minutes, secs = divmod(remainder, 60)

    if td.days > 0:
        return f"{td.days}d {hours}h {minutes}m {secs}s"
    elif hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    else:
        return f"{secs}s"


def get_current_stats() -> dict:
    """Get current statistics from semantic.chunks table."""
    db_manager = get_db_manager()

    with db_manager.get_connection() as conn:
        with conn.cursor() as cur:
            # Get document count and chunk count
            cur.execute("""
                SELECT
                    COUNT(DISTINCT document_id) as doc_count,
                    COUNT(*) as chunk_count
                FROM semantic.chunks
            """)
            result = cur.fetchone()
            doc_count = result[0] if result else 0
            chunk_count = result[1] if result else 0

            # Get chunking parameters in use
            cur.execute("""
                SELECT DISTINCT chunk_size, chunk_overlap
                FROM semantic.chunks
                LIMIT 5
            """)
            params = cur.fetchall()

            return {
                "document_count": doc_count,
                "chunk_count": chunk_count,
                "chunking_params": params,
            }


def dry_run(chunk_size: int, overlap: int, model_name: str) -> None:
    """Show what would be done without making changes."""
    print("\n" + "=" * 60)
    print("DRY RUN - No changes will be made")
    print("=" * 60)

    stats = get_current_stats()

    print(f"\nCurrent state:")
    print(f"  Documents in semantic.chunks: {stats['document_count']:,}")
    print(f"  Total chunks: {stats['chunk_count']:,}")

    if stats['chunking_params']:
        print(f"  Current chunking parameters:")
        for size, olap in stats['chunking_params']:
            print(f"    - chunk_size={size}, overlap={olap}")

    print(f"\nProposed changes:")
    print(f"  Model: {model_name}")
    print(f"  New chunk_size: {chunk_size}")
    print(f"  New overlap: {overlap}")

    print(f"\nActions that would be performed:")
    print(f"  1. Save {stats['document_count']:,} document IDs to temp table")
    print(f"  2. TRUNCATE semantic.chunks (delete {stats['chunk_count']:,} chunks)")
    print(f"  3. Re-chunk all {stats['document_count']:,} documents")
    print(f"  4. Generate new embeddings with {model_name}")

    # Estimate time based on typical processing rate
    estimated_rate = 1.5  # documents per second (conservative)
    estimated_time = stats['document_count'] / estimated_rate
    print(f"\nEstimated time: {format_duration(estimated_time)} (at ~{estimated_rate} docs/s)")

    print("\nTo proceed, run without --dry-run flag")
    print("=" * 60 + "\n")


def main() -> int:
    """Main entry point for the rechunk CLI."""
    parser = argparse.ArgumentParser(
        description="Re-chunk all documents in semantic.chunks using adaptive chunking",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Use defaults (1800 chars, 320 overlap)
  %(prog)s --chunk-size 2000        # Custom chunk size
  %(prog)s --dry-run                # Preview without making changes
  %(prog)s --model my-model:latest  # Use different embedding model
        """,
    )

    parser.add_argument(
        "--chunk-size",
        type=int,
        default=DEFAULT_CHUNK_SIZE,
        help=f"Target chunk size in characters (default: {DEFAULT_CHUNK_SIZE})",
    )

    parser.add_argument(
        "--overlap",
        type=int,
        default=DEFAULT_CHUNK_OVERLAP,
        help=f"Overlap between chunks in characters (default: {DEFAULT_CHUNK_OVERLAP})",
    )

    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_EMBEDDING_MODEL_NAME,
        help=f"Embedding model name (default: {DEFAULT_EMBEDDING_MODEL_NAME})",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Validate parameters
    if args.chunk_size <= 0:
        print(f"Error: chunk-size must be positive, got {args.chunk_size}")
        return 1

    if args.overlap < 0:
        print(f"Error: overlap cannot be negative, got {args.overlap}")
        return 1

    if args.overlap >= args.chunk_size:
        print(f"Error: overlap ({args.overlap}) must be less than chunk-size ({args.chunk_size})")
        return 1

    # Handle dry run
    if args.dry_run:
        dry_run(args.chunk_size, args.overlap, args.model)
        return 0

    # Print header
    print("\n" + "=" * 60)
    print("Re-chunk Semantic Chunks")
    print("=" * 60)
    print(f"Model: {args.model}")
    print(f"Chunk size: {args.chunk_size} chars")
    print(f"Overlap: {args.overlap} chars")
    print("=" * 60 + "\n")

    # Confirm before proceeding (this is a destructive operation)
    current_stats = get_current_stats()
    print(f"WARNING: This will truncate semantic.chunks and re-process")
    print(f"         {current_stats['document_count']:,} documents ({current_stats['chunk_count']:,} chunks)")
    print()

    try:
        response = input("Continue? [y/N] ").strip().lower()
        if response != "y":
            print("Aborted.")
            return 0
    except KeyboardInterrupt:
        print("\nAborted.")
        return 0

    print()

    # Initialize embedder
    try:
        embedder = ChunkEmbedder(model_name=args.model)
    except Exception as e:
        print(f"Error initializing embedder: {e}")
        return 1

    # Create progress bar
    pbar = None
    current_stage = ""

    def progress_callback(stage: str, current: int, total: int) -> None:
        """Update progress bar based on stage."""
        nonlocal pbar, current_stage

        if stage != current_stage:
            # Close previous progress bar
            if pbar is not None:
                pbar.close()

            current_stage = stage

            if stage == "collecting_ids":
                print("Step 1: Collecting document IDs...")
            elif stage == "truncating":
                print(f"\nFound {total:,} documents to rechunk")
                print("\nStep 2: Truncating semantic.chunks...")
                print("Table truncated (HNSW index preserved)\n")
                print("Step 3: Re-chunking documents...")
                pbar = tqdm(
                    total=total,
                    desc="Processing",
                    unit="doc",
                    ncols=80,
                )
            elif stage == "chunking":
                if pbar is None:
                    pbar = tqdm(
                        total=total,
                        desc="Processing",
                        unit="doc",
                        ncols=80,
                    )

        if stage == "chunking" and pbar is not None:
            pbar.n = current
            pbar.refresh()

    # Run rechunking
    start_time = time.perf_counter()

    try:
        stats = embedder.rechunk_all(
            chunk_size=args.chunk_size,
            overlap=args.overlap,
            progress_callback=progress_callback,
        )
    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
        if pbar is not None:
            pbar.close()
        return 1
    except Exception as e:
        print(f"\n\nError during rechunking: {e}")
        if pbar is not None:
            pbar.close()
        return 1

    # Close progress bar
    if pbar is not None:
        pbar.close()

    # Calculate total time (including collection and truncation)
    total_elapsed = time.perf_counter() - start_time

    # Print statistics
    print("\n" + "=" * 60)
    print("Statistics")
    print("=" * 60)
    print(f"Documents processed: {stats['processed']:,}")
    print(f"Documents failed: {stats['failed']:,}")
    print(f"Total chunks created: {stats['total_chunks_created']:,}")
    print(f"Time elapsed: {format_duration(total_elapsed)}")

    if total_elapsed > 0:
        print(f"Processing rate: {stats['total_chunks_created'] / total_elapsed:.2f} chunks/s")
        print(f"Document rate: {stats['processed'] / total_elapsed:.2f} docs/s")

    if stats['processed'] > 0:
        print(f"Average chunks/doc: {stats['avg_chunks_per_doc']:.2f}")

    print("=" * 60 + "\n")

    return 0 if stats['failed'] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
