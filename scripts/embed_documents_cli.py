#!/usr/bin/env python3
"""
Document Embedding CLI for BMLibrarian

Command-line interface for generating vector embeddings for documents in the
BMLibrarian knowledge base.

Usage:
    # Embed medRxiv abstracts (100 documents)
    python embed_documents_cli.py embed --source medrxiv --limit 100

    # Embed all documents without embeddings
    python embed_documents_cli.py embed

    # Count documents needing embeddings
    python embed_documents_cli.py count --source medrxiv

    # Use a specific model
    python embed_documents_cli.py embed --model nomic-embed-text:latest --limit 50
"""

import argparse
import logging
import sys
from datetime import datetime

from src.bmlibrarian.embeddings import DocumentEmbedder


def setup_logging(verbose: bool = False):
    """Configure logging for the CLI."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def cmd_embed(args):
    """Execute the embed command."""
    print("=" * 70)
    print("Document Embedding")
    print("=" * 70)

    try:
        embedder = DocumentEmbedder(model_name=args.model)

        stats = embedder.embed_documents(
            source_name=args.source,
            limit=args.limit,
            batch_size=args.batch_size
        )

        print("\n" + "=" * 70)
        print("Embedding Complete!")
        print("=" * 70)
        print(f"Total processed: {stats['total_processed']}")
        print(f"Successfully embedded: {stats['embedded_count']}")
        print(f"Failed: {stats['failed_count']}")
        if stats['total_processed'] > 0:
            success_rate = 100 * stats['embedded_count'] / stats['total_processed']
            print(f"Success rate: {success_rate:.1f}%")
        print("=" * 70)

        return 0

    except Exception as e:
        logging.error(f"Error during embedding: {e}", exc_info=True)
        return 1


def cmd_count(args):
    """Execute the count command."""
    print("=" * 70)
    print("Documents Without Embeddings")
    print("=" * 70)

    try:
        embedder = DocumentEmbedder(model_name=args.model)

        count = embedder.count_documents_without_embeddings(source_name=args.source)

        source_str = f" from source '{args.source}'" if args.source else ""
        print(f"\nFound {count} documents{source_str} without embeddings")
        print(f"Model: {args.model}")
        print("=" * 70)

        return 0

    except Exception as e:
        logging.error(f"Error counting documents: {e}", exc_info=True)
        return 1


def cmd_status(args):
    """Show embedding status and statistics."""
    print("=" * 70)
    print("Embedding Status")
    print("=" * 70)

    try:
        from bmlibrarian.database import get_db_manager

        embedder = DocumentEmbedder(model_name=args.model)
        db_manager = get_db_manager()

        print(f"\nModel: {args.model}")
        print(f"Model ID: {embedder.model_id}")
        print(f"Embedding dimension: {embedder.embedding_dimension or 'Not yet determined'}")

        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                # Count total documents with abstracts
                cur.execute("""
                    SELECT COUNT(*) FROM document
                    WHERE abstract IS NOT NULL AND abstract != ''
                """)
                total_docs = cur.fetchone()[0]

                # Count documents with embeddings for this model
                cur.execute("""
                    SELECT COUNT(DISTINCT c.document_id)
                    FROM chunks c
                    JOIN embedding_base eb ON c.id = eb.chunk_id
                    WHERE eb.model_id = %s
                """, (embedder.model_id,))
                with_embeddings = cur.fetchone()[0]

                # Count by source
                cur.execute("""
                    SELECT s.name, COUNT(DISTINCT d.id) as total
                    FROM document d
                    JOIN sources s ON d.source_id = s.id
                    WHERE d.abstract IS NOT NULL AND d.abstract != ''
                    GROUP BY s.name
                    ORDER BY total DESC
                """)
                sources = cur.fetchall()

        print(f"\nTotal documents with abstracts: {total_docs}")
        print(f"Documents with embeddings: {with_embeddings} ({100*with_embeddings/total_docs if total_docs else 0:.1f}%)")
        print(f"Documents without embeddings: {total_docs - with_embeddings}")

        print("\nBy source:")
        for source_name, count in sources:
            # Count with embeddings for this source
            with db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT COUNT(DISTINCT c.document_id)
                        FROM chunks c
                        JOIN embedding_base eb ON c.id = eb.chunk_id
                        JOIN document d ON c.document_id = d.id
                        JOIN sources s ON d.source_id = s.id
                        WHERE eb.model_id = %s AND s.name = %s
                    """, (embedder.model_id, source_name))
                    embedded = cur.fetchone()[0]

            print(f"  {source_name}: {embedded}/{count} embedded ({100*embedded/count if count else 0:.1f}%)")

        print("=" * 70)

        return 0

    except Exception as e:
        logging.error(f"Error getting status: {e}", exc_info=True)
        return 1


def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description='Generate vector embeddings for documents in BMLibrarian',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )

    parser.add_argument(
        '--model',
        type=str,
        default='snowflake-arctic-embed2:latest',
        help='Ollama model to use for embeddings (default: snowflake-arctic-embed2:latest)'
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to execute')

    # Embed command
    embed_parser = subparsers.add_parser(
        'embed',
        help='Generate embeddings for documents without embeddings'
    )
    embed_parser.add_argument(
        '--source',
        type=str,
        help='Filter by source name (e.g., medrxiv, pubmed)'
    )
    embed_parser.add_argument(
        '--limit',
        type=int,
        help='Maximum number of documents to embed'
    )
    embed_parser.add_argument(
        '--batch-size',
        type=int,
        default=100,
        help='Number of documents to process in each batch (default: 100)'
    )

    # Count command
    count_parser = subparsers.add_parser(
        'count',
        help='Count documents without embeddings'
    )
    count_parser.add_argument(
        '--source',
        type=str,
        help='Filter by source name (e.g., medrxiv, pubmed)'
    )

    # Status command
    status_parser = subparsers.add_parser(
        'status',
        help='Show embedding status and statistics'
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(args.verbose)

    # Execute command
    if args.command == 'embed':
        return cmd_embed(args)
    elif args.command == 'count':
        return cmd_count(args)
    elif args.command == 'status':
        return cmd_status(args)
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())
