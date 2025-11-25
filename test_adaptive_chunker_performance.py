#!/usr/bin/env python3
"""Performance test for AdaptiveTextChunker.

Tests the performance of AdaptiveTextChunker on 1000 real documents,
with frequent console feedback and detailed statistics.
"""

import time
import statistics
from typing import List, Dict, Any
from pathlib import Path
import sys

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from bmlibrarian.database import DatabaseManager


class AdaptiveTextChunker:
    """
    Simplified AdaptiveTextChunker for performance testing.
    Adapted from localknowledge.textprocessing.chunking.AdaptiveTextChunker
    """

    def __init__(self, max_chunk_size: int = 1800, overlap: int = 320):
        """Initialize the chunker.

        Args:
            max_chunk_size: Maximum size of each chunk in characters
            overlap: Number of characters to overlap between chunks
        """
        self.max_chunk_size = max_chunk_size
        self.overlap = overlap

    def chunk(self, text: str) -> List[str]:
        """Split text into chunks adaptively based on length.

        Args:
            text: The text to chunk

        Returns:
            List of chunk strings
        """
        if not text or len(text.strip()) == 0:
            return []

        # For short texts, create a single chunk
        if len(text) <= self.max_chunk_size:
            return [text.strip()]

        # For longer texts, chunk with sentence boundaries
        return self._chunk_with_boundaries(text)

    def _chunk_with_boundaries(self, text: str) -> List[str]:
        """Split text into chunks with proper sentence boundaries.

        Args:
            text: The text to chunk

        Returns:
            List of chunk strings
        """
        # For very short texts, just return a single chunk
        if len(text) <= self.max_chunk_size:
            return [text.strip()]

        # Split text into sentences first
        sentences = []
        current_pos = 0

        # Simple sentence splitting
        while current_pos < len(text):
            # Find the next sentence end
            next_end = -1
            for marker in ['. ', '! ', '? ', '.\n', '!\n', '?\n']:
                pos = text.find(marker, current_pos)
                if pos != -1 and (next_end == -1 or pos < next_end):
                    next_end = pos + 1  # Include the period

            # If no sentence end found, take the rest of the text
            if next_end == -1:
                sentences.append(text[current_pos:])
                break
            else:
                # Add one more character to include the space after the period
                end_pos = min(next_end + 1, len(text))
                sentences.append(text[current_pos:end_pos])
                current_pos = end_pos

        # Now group sentences into chunks
        chunks = []
        current_chunk = ""
        chunk_start = 0

        for sentence in sentences:
            # If adding this sentence would exceed the max size, create a new chunk
            if len(current_chunk) + len(sentence) > self.max_chunk_size and current_chunk:
                # Add the current chunk
                chunks.append(current_chunk)

                # Start a new chunk with overlap
                chunk_end = chunk_start + len(current_chunk)
                overlap_start = max(0, chunk_end - self.overlap)

                # Start new chunk with this sentence
                current_chunk = sentence
                chunk_start = text.find(sentence, overlap_start)
            else:
                # Add the sentence to the current chunk
                current_chunk += sentence
                if not current_chunk.strip():
                    chunk_start = text.find(sentence)

        # Add the last chunk if there's anything left
        if current_chunk.strip():
            chunks.append(current_chunk)

        # Special case: if we couldn't split into sentences properly, fall back
        if not chunks:
            # Just split the text into chunks of max_chunk_size
            for i in range(0, len(text), self.max_chunk_size):
                chunk_end = min(i + self.max_chunk_size, len(text))
                chunk_content = text[i:chunk_end].strip()
                if chunk_content:
                    chunks.append(chunk_content)

        return chunks


def fetch_test_documents(db: DatabaseManager, limit: int = 1000) -> List[Dict[str, Any]]:
    """Fetch documents with non-empty full_text from the database.

    Args:
        db: DatabaseManager instance
        limit: Maximum number of documents to fetch

    Returns:
        List of document dictionaries containing id and full_text
    """
    print(f"[1/4] Fetching {limit} documents with full_text...")
    fetch_start = time.time()

    with db.get_connection() as conn:
        with conn.cursor() as cur:
            # Simplified query without LENGTH filter for speed
            cur.execute("""
                SELECT id, full_text
                FROM document
                WHERE full_text IS NOT NULL
                  AND full_text != ''
                ORDER BY id
                LIMIT %s
            """, (limit,))

            documents = []
            for row in cur.fetchall():
                text = row[1]
                documents.append({
                    'id': row[0],
                    'full_text': text,
                    'text_length': len(text) if text else 0
                })

    fetch_time = time.time() - fetch_start

    # Calculate text length stats
    lengths = [d['text_length'] for d in documents]
    total_chars = sum(lengths)

    print(f"✓ Fetched {len(documents)} documents in {fetch_time:.2f}s")
    print(f"  Total characters: {total_chars:,}")
    print(f"  Average length: {statistics.mean(lengths):,.0f} chars")
    print(f"  Median length: {statistics.median(lengths):,.0f} chars")
    print(f"  Min length: {min(lengths):,} chars")
    print(f"  Max length: {max(lengths):,} chars")
    print()

    return documents


def test_chunker_performance(
    documents: List[Dict[str, Any]],
    max_chars: int = 1800,
    overlap_chars: int = 320
) -> Dict[str, Any]:
    """Test the performance of AdaptiveTextChunker on documents.

    Args:
        documents: List of document dictionaries with 'id', 'full_text', 'text_length'
        max_chars: Maximum chunk size in characters
        overlap_chars: Overlap between chunks in characters

    Returns:
        Dictionary containing performance statistics
    """
    print(f"[2/4] Testing AdaptiveTextChunker")
    print(f"  Configuration: max_chars={max_chars}, overlap_chars={overlap_chars}")
    print(f"  Progress updates every 10 documents")
    print("=" * 80)

    # Initialize chunker
    chunker = AdaptiveTextChunker(max_chunk_size=max_chars, overlap=overlap_chars)

    # Statistics tracking
    total_docs = len(documents)
    total_chunks = 0
    total_chars_processed = 0
    processing_times = []
    chunks_per_doc = []
    chunk_sizes = []

    # Progress tracking
    start_time = time.time()
    last_report_idx = 0

    # Process each document
    for idx, doc in enumerate(documents, 1):
        doc_start = time.time()

        # Chunk the document
        chunks = chunker.chunk(doc['full_text'])

        doc_end = time.time()
        doc_time = doc_end - doc_start

        # Record statistics
        processing_times.append(doc_time)
        chunks_per_doc.append(len(chunks))
        total_chunks += len(chunks)
        total_chars_processed += doc['text_length']

        # Track chunk sizes
        for chunk in chunks:
            chunk_sizes.append(len(chunk))

        # Progress reporting every 10 documents
        if idx % 10 == 0 or idx == total_docs:
            elapsed = time.time() - start_time
            docs_per_sec = idx / elapsed if elapsed > 0 else 0
            chars_per_sec = total_chars_processed / elapsed if elapsed > 0 else 0
            eta_seconds = (total_docs - idx) / docs_per_sec if docs_per_sec > 0 else 0

            # Calculate stats for this batch
            batch_times = processing_times[last_report_idx:]
            avg_time = statistics.mean(batch_times) if batch_times else 0

            print(f"  [{idx:4d}/{total_docs}] "
                  f"Speed: {docs_per_sec:5.1f} docs/s | "
                  f"{chars_per_sec/1000:6.1f}K chars/s | "
                  f"Avg: {avg_time*1000:5.1f}ms | "
                  f"Chunks: {total_chunks:5d} | "
                  f"ETA: {eta_seconds:4.0f}s")

            last_report_idx = len(processing_times)

    total_time = time.time() - start_time

    print("=" * 80)
    print(f"✓ Processing complete in {total_time:.2f}s")
    print()

    # Calculate statistics
    stats = {
        # Overall performance
        'total_documents': total_docs,
        'total_chunks': total_chunks,
        'total_chars_processed': total_chars_processed,
        'total_time_seconds': total_time,
        'docs_per_second': total_docs / total_time,
        'chars_per_second': total_chars_processed / total_time,
        'chunks_per_second': total_chunks / total_time,

        # Per-document statistics
        'avg_time_per_doc': statistics.mean(processing_times),
        'median_time_per_doc': statistics.median(processing_times),
        'min_time_per_doc': min(processing_times),
        'max_time_per_doc': max(processing_times),
        'stdev_time_per_doc': statistics.stdev(processing_times) if len(processing_times) > 1 else 0,

        # Chunk statistics
        'avg_chunks_per_doc': statistics.mean(chunks_per_doc),
        'median_chunks_per_doc': statistics.median(chunks_per_doc),
        'min_chunks_per_doc': min(chunks_per_doc),
        'max_chunks_per_doc': max(chunks_per_doc),

        # Chunk size statistics
        'avg_chunk_size': statistics.mean(chunk_sizes) if chunk_sizes else 0,
        'median_chunk_size': statistics.median(chunk_sizes) if chunk_sizes else 0,
        'min_chunk_size': min(chunk_sizes) if chunk_sizes else 0,
        'max_chunk_size': max(chunk_sizes) if chunk_sizes else 0,

        # Configuration
        'max_chars': max_chars,
        'overlap_chars': overlap_chars,
    }

    return stats


def print_statistics(stats: Dict[str, Any]) -> None:
    """Print performance statistics in a formatted manner.

    Args:
        stats: Dictionary containing performance statistics
    """
    print("[3/4] PERFORMANCE STATISTICS")
    print("=" * 80)

    print("\n📋 CONFIGURATION:")
    print(f"  Max chunk size:       {stats['max_chars']:,} characters")
    print(f"  Overlap size:         {stats['overlap_chars']:,} characters")

    print("\n⚡ THROUGHPUT:")
    print(f"  Documents processed:  {stats['total_documents']:,}")
    print(f"  Total chunks:         {stats['total_chunks']:,}")
    print(f"  Total characters:     {stats['total_chars_processed']:,}")
    print(f"  Total time:           {stats['total_time_seconds']:.2f} seconds")
    print(f"  Speed:                {stats['docs_per_second']:.2f} docs/second")
    print(f"  Speed:                {stats['chars_per_second']:,.0f} chars/second")
    print(f"  Speed:                {stats['chunks_per_second']:.2f} chunks/second")

    print("\n⏱️  PER-DOCUMENT TIMING:")
    print(f"  Average:              {stats['avg_time_per_doc']*1000:6.2f} ms")
    print(f"  Median:               {stats['median_time_per_doc']*1000:6.2f} ms")
    print(f"  Min:                  {stats['min_time_per_doc']*1000:6.2f} ms")
    print(f"  Max:                  {stats['max_time_per_doc']*1000:6.2f} ms")
    print(f"  Std deviation:        {stats['stdev_time_per_doc']*1000:6.2f} ms")

    print("\n📊 CHUNKS PER DOCUMENT:")
    print(f"  Average:              {stats['avg_chunks_per_doc']:.2f}")
    print(f"  Median:               {stats['median_chunks_per_doc']:.1f}")
    print(f"  Min:                  {stats['min_chunks_per_doc']}")
    print(f"  Max:                  {stats['max_chunks_per_doc']}")

    print("\n📏 CHUNK SIZES:")
    print(f"  Average:              {stats['avg_chunk_size']:.0f} characters")
    print(f"  Median:               {stats['median_chunk_size']:.0f} characters")
    print(f"  Min:                  {stats['min_chunk_size']:,} characters")
    print(f"  Max:                  {stats['max_chunk_size']:,} characters")

    print("\n" + "=" * 80)


def analyze_performance(stats: Dict[str, Any]) -> None:
    """Analyze performance and provide recommendations.

    Args:
        stats: Dictionary containing performance statistics
    """
    print("\n[4/4] PERFORMANCE ANALYSIS")
    print("=" * 80)

    # Throughput analysis
    docs_per_sec = stats['docs_per_second']
    if docs_per_sec > 100:
        print("✓ Excellent throughput (>100 docs/sec)")
    elif docs_per_sec > 50:
        print("✓ Good throughput (>50 docs/sec)")
    elif docs_per_sec > 20:
        print("⚠ Moderate throughput (>20 docs/sec)")
    else:
        print("⚠ Low throughput (<20 docs/sec)")

    # Calculate estimate for 1000 documents
    time_for_1000 = 1000 / docs_per_sec
    print(f"  Estimated time for 1000 docs: {time_for_1000:.1f} seconds ({time_for_1000/60:.1f} minutes)")

    # Calculate estimate for 1 million documents
    time_for_1m = 1_000_000 / docs_per_sec
    print(f"  Estimated time for 1M docs: {time_for_1m/3600:.1f} hours ({time_for_1m/86400:.1f} days)")

    # Chunk size analysis
    avg_chunk = stats['avg_chunk_size']
    max_chars = stats['max_chars']
    if avg_chunk > max_chars * 1.2:
        print(f"\n⚠ Average chunk size ({avg_chunk:.0f}) significantly exceeds target ({max_chars})")
        print("  Consider reviewing sentence segmentation or reducing max_chars")
    elif avg_chunk < max_chars * 0.3:
        print(f"\n⚠ Average chunk size ({avg_chunk:.0f}) is much smaller than target ({max_chars})")
        print("  Consider increasing max_chars for better context windows")
    else:
        print(f"\n✓ Chunk sizes are well-balanced (avg: {avg_chunk:.0f} vs target: {max_chars})")

    # Memory efficiency
    chunks_per_doc = stats['avg_chunks_per_doc']
    if chunks_per_doc > 10:
        print(f"\n⚠ High chunks per document ({chunks_per_doc:.1f})")
        print("  Consider increasing max_chars to reduce chunk count")
    else:
        print(f"\n✓ Reasonable chunks per document ({chunks_per_doc:.1f})")

    print("\n" + "=" * 80)


def main():
    """Main test execution function."""
    print("=" * 80)
    print("ADAPTIVE TEXT CHUNKER PERFORMANCE TEST")
    print("=" * 80)
    print()

    # Initialize database connection
    print("[0/4] Initializing database connection...")
    try:
        db = DatabaseManager()
        print("✓ Database connected")
        print()
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        return 1

    # Fetch test documents
    try:
        documents = fetch_test_documents(db, limit=1000)
    except Exception as e:
        print(f"✗ Failed to fetch documents: {e}")
        return 1

    if not documents:
        print("✗ No documents found with full_text!")
        return 1

    # Run performance test
    try:
        stats = test_chunker_performance(documents, max_chars=1800, overlap_chars=320)
    except Exception as e:
        print(f"✗ Performance test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # Print results
    print_statistics(stats)

    # Analyze performance
    analyze_performance(stats)

    print("\n✓ Performance test completed successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
