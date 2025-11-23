#!/usr/bin/env python3
"""
Chunk Worker CLI for BMLibrarian

Background worker for processing the semantic chunk queue. Processes documents
that have full_text but haven't been chunked and embedded yet.

Usage:
    # Process up to 100 documents from queue
    uv run python chunk_worker.py process --batch-size 100

    # Continuous processing mode (runs until interrupted)
    uv run python chunk_worker.py process --continuous

    # Show queue status
    uv run python chunk_worker.py status

    # Custom chunk parameters
    uv run python chunk_worker.py process --chunk-size 500 --overlap 75

    # Queue a specific document for processing
    uv run python chunk_worker.py queue 12345

    # Clear failed items from queue
    uv run python chunk_worker.py clear-failed
"""

import argparse
import logging
import signal
import sys
import time
from datetime import datetime
from typing import Optional

# Configure logging
logger = logging.getLogger(__name__)

# Constants
DEFAULT_BATCH_SIZE = 100
DEFAULT_CHUNK_SIZE = 350
DEFAULT_CHUNK_OVERLAP = 50
CONTINUOUS_POLL_INTERVAL_SECONDS = 30
MAX_RETRY_ATTEMPTS = 3


def setup_logging(verbose: bool = False) -> None:
    """
    Configure logging for the CLI.

    Args:
        verbose: If True, enable DEBUG level logging.
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def cmd_process(args: argparse.Namespace) -> int:
    """
    Execute the process command - process documents from chunk queue.

    Args:
        args: Parsed command line arguments.

    Returns:
        Exit code (0 for success, non-zero for error).
    """
    from bmlibrarian.embeddings.chunk_embedder import ChunkEmbedder

    print("=" * 70)
    print("Chunk Worker - Processing Queue")
    print("=" * 70)
    print(f"Batch size: {args.batch_size}")
    print(f"Chunk size: {args.chunk_size}")
    print(f"Chunk overlap: {args.overlap}")
    print(f"Continuous mode: {args.continuous}")
    print("=" * 70)

    # Setup graceful shutdown for continuous mode
    shutdown_requested = False

    def signal_handler(signum, frame):
        nonlocal shutdown_requested
        print("\nShutdown requested, finishing current batch...")
        shutdown_requested = True

    if args.continuous:
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    try:
        embedder = ChunkEmbedder()

        total_processed = 0
        total_failed = 0
        batches = 0

        while True:
            batches += 1
            print(f"\n--- Batch {batches} ---")

            # Process a batch
            processed, failed = embedder.process_queue(
                batch_size=args.batch_size,
                chunk_size=args.chunk_size,
                overlap=args.overlap,
            )

            total_processed += processed
            total_failed += failed

            print(f"Batch {batches}: {processed} processed, {failed} failed")
            print(f"Total: {total_processed} processed, {total_failed} failed")

            # Check exit conditions
            if shutdown_requested:
                print("\nShutdown requested, exiting...")
                break

            if not args.continuous:
                break

            if processed == 0 and failed == 0:
                # Queue is empty, wait before polling again
                print(f"Queue empty, waiting {CONTINUOUS_POLL_INTERVAL_SECONDS}s...")
                time.sleep(CONTINUOUS_POLL_INTERVAL_SECONDS)

        print("\n" + "=" * 70)
        print("Processing Complete!")
        print("=" * 70)
        print(f"Total batches: {batches}")
        print(f"Total processed: {total_processed}")
        print(f"Total failed: {total_failed}")
        if total_processed + total_failed > 0:
            success_rate = 100 * total_processed / (total_processed + total_failed)
            print(f"Success rate: {success_rate:.1f}%")
        print("=" * 70)

        return 0

    except Exception as e:
        logger.error(f"Error during processing: {e}", exc_info=True)
        return 1


def cmd_status(args: argparse.Namespace) -> int:
    """
    Show chunk queue status and statistics.

    Args:
        args: Parsed command line arguments.

    Returns:
        Exit code (0 for success, non-zero for error).
    """
    from bmlibrarian.database import get_db_manager

    print("=" * 70)
    print("Chunk Queue Status")
    print("=" * 70)

    try:
        db_manager = get_db_manager()

        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                # Count queued documents
                cur.execute("SELECT COUNT(*) FROM semantic.chunk_queue")
                queue_count = cur.fetchone()[0]

                # Count by attempts
                cur.execute("""
                    SELECT attempts, COUNT(*)
                    FROM semantic.chunk_queue
                    GROUP BY attempts
                    ORDER BY attempts
                """)
                attempts_breakdown = cur.fetchall()

                # Count documents with chunks
                cur.execute("SELECT COUNT(DISTINCT document_id) FROM semantic.chunks")
                docs_with_chunks = cur.fetchone()[0]

                # Total chunks
                cur.execute("SELECT COUNT(*) FROM semantic.chunks")
                total_chunks = cur.fetchone()[0]

                # Documents with full_text but no chunks
                cur.execute("""
                    SELECT COUNT(*)
                    FROM public.document d
                    WHERE d.full_text IS NOT NULL AND d.full_text != ''
                    AND NOT EXISTS (
                        SELECT 1 FROM semantic.chunks c WHERE c.document_id = d.id
                    )
                """)
                needs_chunking = cur.fetchone()[0]

                # Most recent queue activity
                cur.execute("""
                    SELECT MAX(queued_at), MIN(queued_at)
                    FROM semantic.chunk_queue
                """)
                newest, oldest = cur.fetchone()

                # Failed items (max attempts reached)
                cur.execute(f"""
                    SELECT COUNT(*)
                    FROM semantic.chunk_queue
                    WHERE attempts >= {MAX_RETRY_ATTEMPTS}
                """)
                failed_count = cur.fetchone()[0]

        print(f"\nQueue Statistics:")
        print(f"  Documents in queue: {queue_count}")
        print(f"  Failed (max retries): {failed_count}")

        if attempts_breakdown:
            print(f"\n  By retry attempts:")
            for attempts, count in attempts_breakdown:
                status = " (will be skipped)" if attempts >= MAX_RETRY_ATTEMPTS else ""
                print(f"    {attempts} attempts: {count}{status}")

        if oldest and newest:
            print(f"\n  Queue time range:")
            print(f"    Oldest: {oldest}")
            print(f"    Newest: {newest}")

        print(f"\nChunk Statistics:")
        print(f"  Documents with chunks: {docs_with_chunks}")
        print(f"  Total chunks: {total_chunks}")
        if docs_with_chunks > 0:
            avg_chunks = total_chunks / docs_with_chunks
            print(f"  Average chunks per document: {avg_chunks:.1f}")

        print(f"\nDocuments needing chunking: {needs_chunking}")
        print("=" * 70)

        return 0

    except Exception as e:
        logger.error(f"Error getting status: {e}", exc_info=True)
        return 1


def cmd_queue(args: argparse.Namespace) -> int:
    """
    Add a specific document to the chunk queue.

    Args:
        args: Parsed command line arguments.

    Returns:
        Exit code (0 for success, non-zero for error).
    """
    from bmlibrarian.database import get_db_manager

    document_id = args.document_id
    priority = args.priority

    print(f"Queueing document {document_id} with priority {priority}...")

    try:
        db_manager = get_db_manager()

        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                # Verify document exists and has full_text
                cur.execute("""
                    SELECT id, title, LENGTH(full_text) as text_len
                    FROM public.document
                    WHERE id = %s
                """, (document_id,))
                result = cur.fetchone()

                if not result:
                    print(f"Error: Document {document_id} not found")
                    return 1

                doc_id, title, text_len = result
                if not text_len:
                    print(f"Error: Document {document_id} has no full_text")
                    return 1

                # Add to queue
                cur.execute("""
                    INSERT INTO semantic.chunk_queue (document_id, priority)
                    VALUES (%s, %s)
                    ON CONFLICT (document_id)
                    DO UPDATE SET
                        queued_at = NOW(),
                        priority = EXCLUDED.priority,
                        attempts = 0,
                        last_error = NULL
                """, (document_id, priority))

        print(f"Document {document_id} queued successfully")
        print(f"  Title: {title[:60]}..." if len(title or "") > 60 else f"  Title: {title}")
        print(f"  Text length: {text_len:,} characters")
        print(f"  Priority: {priority}")

        return 0

    except Exception as e:
        logger.error(f"Error queueing document: {e}", exc_info=True)
        return 1


def cmd_clear_failed(args: argparse.Namespace) -> int:
    """
    Clear failed items from the chunk queue.

    Args:
        args: Parsed command line arguments.

    Returns:
        Exit code (0 for success, non-zero for error).
    """
    from bmlibrarian.database import get_db_manager

    print("Clearing failed items from chunk queue...")

    try:
        db_manager = get_db_manager()

        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                if args.reset:
                    # Reset attempts counter instead of deleting
                    cur.execute(f"""
                        UPDATE semantic.chunk_queue
                        SET attempts = 0, last_error = NULL
                        WHERE attempts >= {MAX_RETRY_ATTEMPTS}
                    """)
                    count = cur.rowcount
                    print(f"Reset {count} failed items for retry")
                else:
                    # Delete failed items
                    cur.execute(f"""
                        DELETE FROM semantic.chunk_queue
                        WHERE attempts >= {MAX_RETRY_ATTEMPTS}
                    """)
                    count = cur.rowcount
                    print(f"Deleted {count} failed items from queue")

        return 0

    except Exception as e:
        logger.error(f"Error clearing failed items: {e}", exc_info=True)
        return 1


def main() -> int:
    """
    Main entry point for the CLI.

    Returns:
        Exit code.
    """
    parser = argparse.ArgumentParser(
        description="Background worker for processing semantic chunk queue",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Process command
    process_parser = subparsers.add_parser(
        "process",
        help="Process documents from the chunk queue",
    )
    process_parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Number of documents to process per batch (default: {DEFAULT_BATCH_SIZE})",
    )
    process_parser.add_argument(
        "--chunk-size",
        type=int,
        default=DEFAULT_CHUNK_SIZE,
        help=f"Target chunk size in characters (default: {DEFAULT_CHUNK_SIZE})",
    )
    process_parser.add_argument(
        "--overlap",
        type=int,
        default=DEFAULT_CHUNK_OVERLAP,
        help=f"Chunk overlap in characters (default: {DEFAULT_CHUNK_OVERLAP})",
    )
    process_parser.add_argument(
        "--continuous",
        action="store_true",
        help="Run continuously, polling for new work",
    )

    # Status command
    status_parser = subparsers.add_parser(
        "status",
        help="Show chunk queue status and statistics",
    )

    # Queue command
    queue_parser = subparsers.add_parser(
        "queue",
        help="Add a document to the chunk queue",
    )
    queue_parser.add_argument(
        "document_id",
        type=int,
        help="Document ID to queue",
    )
    queue_parser.add_argument(
        "--priority",
        type=int,
        default=0,
        help="Queue priority (higher = processed sooner, default: 0)",
    )

    # Clear failed command
    clear_parser = subparsers.add_parser(
        "clear-failed",
        help="Clear or reset failed items from queue",
    )
    clear_parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset attempts counter instead of deleting",
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(args.verbose)

    # Execute command
    if args.command == "process":
        return cmd_process(args)
    elif args.command == "status":
        return cmd_status(args)
    elif args.command == "queue":
        return cmd_queue(args)
    elif args.command == "clear-failed":
        return cmd_clear_failed(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
