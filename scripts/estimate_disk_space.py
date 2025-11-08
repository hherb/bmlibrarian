#!/usr/bin/env python3
"""
Estimate disk space impact of proposed optimizations.
"""

import os
import psycopg


def estimate_disk_space():
    """Estimate disk space requirements for optimizations."""
    db_params = {
        "dbname": os.getenv("POSTGRES_DB", "knowledgebase"),
        "user": os.getenv("POSTGRES_USER"),
        "password": os.getenv("POSTGRES_PASSWORD"),
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": os.getenv("POSTGRES_PORT", "5432")
    }

    with psycopg.connect(**db_params) as conn:
        with conn.cursor() as cur:
            print("=" * 80)
            print("DISK SPACE IMPACT ESTIMATION")
            print("=" * 80)

            # Get current sizes
            cur.execute("""
                SELECT
                    pg_size_pretty(pg_total_relation_size('emb_1024')) as emb_total,
                    pg_size_pretty(pg_relation_size('emb_1024')) as emb_table,
                    pg_size_pretty(pg_total_relation_size('chunks')) as chunks_total,
                    pg_size_pretty(pg_relation_size('chunks')) as chunks_table,
                    (SELECT count(*) FROM emb_1024) as emb_count,
                    (SELECT count(*) FROM chunks) as chunks_count
            """)
            emb_total, emb_table, chunks_total, chunks_table, emb_count, chunks_count = cur.fetchone()

            print(f"\n📊 Current Disk Usage:")
            print(f"  emb_1024 table:")
            print(f"    Table: {emb_table}")
            print(f"    Total (with indexes): {emb_total}")
            print(f"    Row count: {emb_count:,}")
            print(f"\n  chunks table:")
            print(f"    Table: {chunks_table}")
            print(f"    Total (with indexes): {chunks_total}")
            print(f"    Row count: {chunks_count:,}")

            # Get current HNSW index size
            cur.execute("""
                SELECT pg_size_pretty(pg_relation_size('arctic_hnsw_idx_v2'))
            """)
            current_hnsw_size = cur.fetchone()[0]
            print(f"\n  Current HNSW index: {current_hnsw_size}")

            # Get average text length from chunks
            cur.execute("""
                SELECT
                    AVG(LENGTH(text)) as avg_text_length,
                    AVG(chunklength) as avg_chunk_length,
                    pg_size_pretty(SUM(LENGTH(text))::bigint) as total_text_size
                FROM chunks
                LIMIT 10000  -- Sample for speed
            """)
            avg_text_len, avg_chunk_len, sample_text_size = cur.fetchone()

            print(f"\n📝 Text Content Statistics (sample):")
            print(f"  Average text length: {avg_text_len:.0f} characters")
            print(f"  Average chunk length: {avg_chunk_len:.0f}")

            print("\n" + "=" * 80)
            print("💾 ESTIMATED DISK SPACE IMPACT")
            print("=" * 80)

            # Estimation 1: text_search column
            print("\n1. Adding text_search tsvector column to chunks table:")
            print("   Formula: ~20-40% of original text size (typical for English)")

            # Get actual chunks table text size
            cur.execute("""
                SELECT pg_column_size(text) FROM chunks LIMIT 1000
            """)
            sample_sizes = [row[0] for row in cur.fetchall() if row[0]]
            avg_text_bytes = sum(sample_sizes) / len(sample_sizes) if sample_sizes else 1000

            estimated_tsvector_per_row = avg_text_bytes * 0.3  # 30% of text size
            estimated_tsvector_total = (estimated_tsvector_per_row * chunks_count) / (1024**3)

            print(f"   Average text size per row: ~{avg_text_bytes:.0f} bytes")
            print(f"   Estimated tsvector per row: ~{estimated_tsvector_per_row:.0f} bytes")
            print(f"   Total for {chunks_count:,} rows: ~{estimated_tsvector_total:.1f} GB")

            # Estimation 2: GIN index on text_search
            print("\n2. GIN index on text_search column:")
            print("   Formula: ~50-80% of tsvector column size")
            estimated_gin_size = estimated_tsvector_total * 0.65  # 65% typical
            print(f"   Estimated GIN index size: ~{estimated_gin_size:.1f} GB")

            # Estimation 3: Rebuilt HNSW index with m=24
            print("\n3. Rebuilt HNSW index (m=24, ef_construction=96):")
            print("   Current: m=6, ef_construction=48")
            print("   New: m=24, ef_construction=96")
            print("   Formula: Index size scales with 'm' parameter")

            # HNSW index size roughly proportional to m
            # Current: 206 GB with m=6
            # New: m=24 (4x increase) → roughly 4x size
            current_hnsw_gb = 206  # From analysis
            estimated_new_hnsw = current_hnsw_gb * (24 / 6)
            print(f"   Current index: {current_hnsw_gb} GB (m=6)")
            print(f"   Estimated new index: ~{estimated_new_hnsw:.0f} GB (m=24)")
            print(f"   Additional space needed: ~{estimated_new_hnsw - current_hnsw_gb:.0f} GB")
            print("   Note: During rebuild, both indexes exist briefly")

            # Total estimates
            print("\n" + "=" * 80)
            print("📈 TOTAL SPACE REQUIREMENTS")
            print("=" * 80)

            total_new_space = estimated_tsvector_total + estimated_gin_size
            total_with_hnsw = total_new_space + (estimated_new_hnsw - current_hnsw_gb)

            print("\nScenario A: Hybrid search only (text_search + GIN index)")
            print(f"  text_search column: ~{estimated_tsvector_total:.1f} GB")
            print(f"  GIN index: ~{estimated_gin_size:.1f} GB")
            print(f"  Total new space: ~{total_new_space:.1f} GB")

            print("\nScenario B: Hybrid search + rebuilt HNSW index")
            print(f"  text_search + GIN: ~{total_new_space:.1f} GB")
            print(f"  Additional HNSW space: ~{estimated_new_hnsw - current_hnsw_gb:.0f} GB")
            print(f"  Total new space: ~{total_with_hnsw:.0f} GB")
            print(f"  During rebuild: ~{total_with_hnsw + current_hnsw_gb:.0f} GB (both indexes)")

            # Check available disk space
            cur.execute("""
                SELECT
                    pg_tablespace_size('pg_default') as tablespace_size,
                    pg_database_size(current_database()) as db_size
            """)
            tablespace_size, db_size = cur.fetchone()
            tablespace_gb = tablespace_size / (1024**3)
            db_gb = db_size / (1024**3)

            print("\n" + "=" * 80)
            print("💿 CURRENT DISK USAGE")
            print("=" * 80)
            print(f"  Database size: {db_gb:.1f} GB")
            print(f"  Tablespace size: {tablespace_gb:.1f} GB")

            # Get filesystem info (this is approximate)
            import shutil
            try:
                # This gets the filesystem where PostgreSQL data directory is
                # Note: May not be accurate if using different tablespaces
                usage = shutil.disk_usage('/')
                total_disk_gb = usage.total / (1024**3)
                free_disk_gb = usage.free / (1024**3)
                print(f"\n  Root filesystem:")
                print(f"    Total: {total_disk_gb:.1f} GB")
                print(f"    Free: {free_disk_gb:.1f} GB")
                print(f"    Used: {(usage.used / (1024**3)):.1f} GB")
            except:
                print("\n  Could not determine filesystem space")

            print("\n" + "=" * 80)
            print("✅ RECOMMENDATIONS")
            print("=" * 80)

            print("\n1. Hybrid Search (text_search + GIN):")
            print(f"   Space needed: ~{total_new_space:.1f} GB")
            print("   Best for: Immediate 50-100x speedup")
            print("   Impact: Permanent addition to database")

            print("\n2. Rebuild HNSW Index:")
            print(f"   Space needed: ~{estimated_new_hnsw - current_hnsw_gb:.0f} GB permanent")
            print(f"   Temporary spike: ~{current_hnsw_gb:.0f} GB (during rebuild)")
            print("   Best for: Better vector search quality")
            print("   Note: Can be done after hybrid search")

            print("\n3. Both Optimizations:")
            print(f"   Total space: ~{total_with_hnsw:.0f} GB")
            print("   Best performance: Hybrid search + optimized HNSW")
            print("   Recommended approach: Start with hybrid, add HNSW rebuild later")


if __name__ == "__main__":
    try:
        estimate_disk_space()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
