#!/usr/bin/env python3
"""
Performance comparison between original and optimized adaptive chunkers.

Tests both implementations on the same 1000 documents to compare:
- Processing speed
- Chunk quality
- Output consistency
"""

import time
import statistics
from typing import List, Dict, Any
from pathlib import Path
import sys

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from bmlibrarian.database import DatabaseManager
from bmlibrarian.embeddings.adaptive_chunker import adaptive_chunker as adaptive_original
from bmlibrarian.embeddings.adaptive_chunker_optimized import adaptive_chunker as adaptive_optimized


def fetch_test_documents(db: DatabaseManager, limit: int = 1000) -> List[Dict[str, Any]]:
    """Fetch documents with non-empty full_text from the database."""
    print(f"[1/5] Fetching {limit} documents with full_text...")
    fetch_start = time.time()

    with db.get_connection() as conn:
        with conn.cursor() as cur:
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
    lengths = [d['text_length'] for d in documents]

    print(f"✓ Fetched {len(documents)} documents in {fetch_time:.2f}s")
    print(f"  Total characters: {sum(lengths):,}")
    print(f"  Average length: {statistics.mean(lengths):,.0f} chars")
    print()

    return documents


def test_chunker(
    name: str,
    chunker_func,
    documents: List[Dict[str, Any]],
    max_chars: int = 1800,
    overlap_chars: int = 320
) -> Dict[str, Any]:
    """Test a chunker implementation and return statistics."""
    print(f"Testing {name}...")
    print(f"  Configuration: max_chars={max_chars}, overlap_chars={overlap_chars}")
    print(f"  Progress updates every 100 documents")
    print("=" * 80)

    total_docs = len(documents)
    total_chunks = 0
    total_chars_processed = 0
    processing_times = []
    chunks_per_doc = []
    chunk_sizes = []
    all_chunks = []  # Store all chunks for comparison

    start_time = time.time()

    for idx, doc in enumerate(documents, 1):
        doc_start = time.time()

        # Chunk the document
        chunks = chunker_func(doc['full_text'], max_chars=max_chars, overlap_chars=overlap_chars)

        doc_time = time.time() - doc_start

        # Record statistics
        processing_times.append(doc_time)
        chunks_per_doc.append(len(chunks))
        total_chunks += len(chunks)
        total_chars_processed += doc['text_length']
        all_chunks.append(chunks)

        # Track chunk sizes
        for chunk in chunks:
            chunk_sizes.append(len(chunk))

        # Progress reporting every 100 documents
        if idx % 100 == 0 or idx == total_docs:
            elapsed = time.time() - start_time
            docs_per_sec = idx / elapsed if elapsed > 0 else 0
            chars_per_sec = total_chars_processed / elapsed if elapsed > 0 else 0

            print(f"  [{idx:4d}/{total_docs}] "
                  f"Speed: {docs_per_sec:6.1f} docs/s | "
                  f"{chars_per_sec/1000:7.1f}K chars/s | "
                  f"Chunks: {total_chunks:5d}")

    total_time = time.time() - start_time

    print("=" * 80)
    print(f"✓ {name} completed in {total_time:.2f}s")
    print()

    return {
        'name': name,
        'total_documents': total_docs,
        'total_chunks': total_chunks,
        'total_chars_processed': total_chars_processed,
        'total_time_seconds': total_time,
        'docs_per_second': total_docs / total_time,
        'chars_per_second': total_chars_processed / total_time,
        'chunks_per_second': total_chunks / total_time,
        'avg_time_per_doc': statistics.mean(processing_times),
        'median_time_per_doc': statistics.median(processing_times),
        'min_time_per_doc': min(processing_times),
        'max_time_per_doc': max(processing_times),
        'avg_chunks_per_doc': statistics.mean(chunks_per_doc),
        'median_chunks_per_doc': statistics.median(chunks_per_doc),
        'avg_chunk_size': statistics.mean(chunk_sizes) if chunk_sizes else 0,
        'median_chunk_size': statistics.median(chunk_sizes) if chunk_sizes else 0,
        'min_chunk_size': min(chunk_sizes) if chunk_sizes else 0,
        'max_chunk_size': max(chunk_sizes) if chunk_sizes else 0,
        'all_chunks': all_chunks,
    }


def compare_chunk_quality(stats1: Dict[str, Any], stats2: Dict[str, Any]) -> Dict[str, Any]:
    """Compare chunk quality between two implementations."""
    print("[4/5] CHUNK QUALITY COMPARISON")
    print("=" * 80)

    # Compare number of chunks
    chunks1 = stats1['all_chunks']
    chunks2 = stats2['all_chunks']

    identical_count = 0
    different_count = 0
    total_docs = len(chunks1)

    for i, (c1, c2) in enumerate(zip(chunks1, chunks2)):
        if len(c1) == len(c2) and all(a == b for a, b in zip(c1, c2)):
            identical_count += 1
        else:
            different_count += 1

    print(f"\n📊 Output Consistency:")
    print(f"  Identical outputs:    {identical_count:4d} docs ({identical_count/total_docs*100:5.1f}%)")
    print(f"  Different outputs:    {different_count:4d} docs ({different_count/total_docs*100:5.1f}%)")

    # Sample some differences
    if different_count > 0:
        print(f"\n  Sample differences (first 3):")
        diff_count = 0
        for i, (c1, c2) in enumerate(zip(chunks1, chunks2)):
            if len(c1) != len(c2) or not all(a == b for a, b in zip(c1, c2)):
                print(f"    Doc {i}: {len(c1)} chunks vs {len(c2)} chunks")
                diff_count += 1
                if diff_count >= 3:
                    break

    print()
    return {
        'identical_count': identical_count,
        'different_count': different_count,
        'consistency_rate': identical_count / total_docs
    }


def print_comparison(stats1: Dict[str, Any], stats2: Dict[str, Any]):
    """Print side-by-side performance comparison."""
    print("[5/5] PERFORMANCE COMPARISON")
    print("=" * 80)

    name1 = stats1['name']
    name2 = stats2['name']

    print(f"\n⚡ THROUGHPUT COMPARISON:")
    print(f"{'Metric':<30} {name1:>25} {name2:>25} {'Improvement':>12}")
    print("-" * 95)

    # Speed comparison
    speed1 = stats1['docs_per_second']
    speed2 = stats2['docs_per_second']
    speedup = speed2 / speed1 if speed1 > 0 else 0
    print(f"{'Documents/second':<30} {speed1:>25.2f} {speed2:>25.2f} {speedup:>11.2f}x")

    # Character throughput
    chars1 = stats1['chars_per_second']
    chars2 = stats2['chars_per_second']
    chars_speedup = chars2 / chars1 if chars1 > 0 else 0
    print(f"{'Characters/second':<30} {chars1:>25,.0f} {chars2:>25,.0f} {chars_speedup:>11.2f}x")

    # Total time
    time1 = stats1['total_time_seconds']
    time2 = stats2['total_time_seconds']
    time_reduction = (time1 - time2) / time1 * 100 if time1 > 0 else 0
    print(f"{'Total time (seconds)':<30} {time1:>25.2f} {time2:>25.2f} {time_reduction:>10.1f}%")

    print(f"\n⏱️  PER-DOCUMENT TIMING:")
    print(f"{'Metric':<30} {name1:>25} {name2:>25} {'Improvement':>12}")
    print("-" * 95)

    # Average time
    avg1 = stats1['avg_time_per_doc'] * 1000
    avg2 = stats2['avg_time_per_doc'] * 1000
    avg_speedup = avg1 / avg2 if avg2 > 0 else 0
    print(f"{'Average (ms)':<30} {avg1:>25.2f} {avg2:>25.2f} {avg_speedup:>11.2f}x")

    # Median time
    med1 = stats1['median_time_per_doc'] * 1000
    med2 = stats2['median_time_per_doc'] * 1000
    med_speedup = med1 / med2 if med2 > 0 else 0
    print(f"{'Median (ms)':<30} {med1:>25.2f} {med2:>25.2f} {med_speedup:>11.2f}x")

    print(f"\n📊 CHUNK STATISTICS:")
    print(f"{'Metric':<30} {name1:>25} {name2:>25} {'Difference':>12}")
    print("-" * 95)

    # Chunks per doc
    chunks1 = stats1['avg_chunks_per_doc']
    chunks2 = stats2['avg_chunks_per_doc']
    chunk_diff = ((chunks2 - chunks1) / chunks1 * 100) if chunks1 > 0 else 0
    print(f"{'Avg chunks/doc':<30} {chunks1:>25.2f} {chunks2:>25.2f} {chunk_diff:>10.1f}%")

    # Avg chunk size
    size1 = stats1['avg_chunk_size']
    size2 = stats2['avg_chunk_size']
    size_diff = ((size2 - size1) / size1 * 100) if size1 > 0 else 0
    print(f"{'Avg chunk size (chars)':<30} {size1:>25.0f} {size2:>25.0f} {size_diff:>10.1f}%")

    # Median chunk size
    med_size1 = stats1['median_chunk_size']
    med_size2 = stats2['median_chunk_size']
    med_size_diff = ((med_size2 - med_size1) / med_size1 * 100) if med_size1 > 0 else 0
    print(f"{'Median chunk size (chars)':<30} {med_size1:>25.0f} {med_size2:>25.0f} {med_size_diff:>10.1f}%")

    print(f"\n💡 SCALABILITY ESTIMATES:")
    print(f"{'Dataset Size':<30} {name1:>25} {name2:>25} {'Time Saved':>12}")
    print("-" * 95)

    for size, label in [(10_000, '10K docs'), (100_000, '100K docs'), (1_000_000, '1M docs')]:
        time1_est = size / speed1 / 60  # minutes
        time2_est = size / speed2 / 60  # minutes
        time_saved = time1_est - time2_est

        if time1_est > 60:
            time1_str = f"{time1_est/60:.1f}h"
            time2_str = f"{time2_est/60:.1f}h"
            saved_str = f"{time_saved/60:.1f}h"
        else:
            time1_str = f"{time1_est:.1f}m"
            time2_str = f"{time2_est:.1f}m"
            saved_str = f"{time_saved:.1f}m"

        print(f"{label:<30} {time1_str:>25} {time2_str:>25} {saved_str:>12}")

    print("\n" + "=" * 80)


def main():
    """Main test execution function."""
    print("=" * 80)
    print("ADAPTIVE CHUNKER: ORIGINAL vs OPTIMIZED COMPARISON")
    print("=" * 80)
    print()

    # Initialize database connection
    print("[0/5] Initializing database connection...")
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

    # Test original implementation
    print("[2/5] ORIGINAL ADAPTIVE CHUNKER")
    print("=" * 80)
    stats_original = test_chunker("Original", adaptive_original, documents)

    # Test optimized implementation
    print("[3/5] OPTIMIZED ADAPTIVE CHUNKER")
    print("=" * 80)
    stats_optimized = test_chunker("Optimized", adaptive_optimized, documents)

    # Compare chunk quality
    quality_comparison = compare_chunk_quality(stats_original, stats_optimized)

    # Print comparison
    print_comparison(stats_original, stats_optimized)

    # Print recommendation
    if stats_optimized['docs_per_second'] > stats_original['docs_per_second']:
        speedup = stats_optimized['docs_per_second'] / stats_original['docs_per_second']
        print(f"\n✓ RECOMMENDATION: Use OPTIMIZED implementation")
        print(f"  - {speedup:.2f}x faster processing speed")
        print(f"  - {quality_comparison['consistency_rate']*100:.1f}% output consistency")
        if quality_comparison['consistency_rate'] < 0.95:
            print(f"  - Note: Some output differences detected ({quality_comparison['different_count']} docs)")
    else:
        print(f"\n⚠ UNEXPECTED: Original appears faster")
        print(f"  - This may be due to system variability")
        print(f"  - Re-run the test to confirm")

    print("\n✓ Comparison completed successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
