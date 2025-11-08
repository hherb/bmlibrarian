#!/usr/bin/env python3
"""
Analyze and optimize HNSW index configuration for emb_1024 table.
"""

import os
import psycopg


def analyze_index():
    """Analyze current index configuration and suggest optimizations."""
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
            print("HNSW INDEX ANALYSIS FOR emb_1024")
            print("=" * 80)

            # Get table size
            cur.execute("""
                SELECT
                    pg_size_pretty(pg_total_relation_size('emb_1024')) as total_size,
                    pg_size_pretty(pg_relation_size('emb_1024')) as table_size,
                    (SELECT count(*) FROM emb_1024) as row_count
            """)
            total_size, table_size, row_count = cur.fetchone()
            print(f"\nTable Statistics:")
            print(f"  Total size: {total_size}")
            print(f"  Table size: {table_size}")
            print(f"  Row count: {row_count:,}")

            # Get index information
            cur.execute("""
                SELECT
                    indexrelname,
                    pg_size_pretty(pg_relation_size(indexrelid)) as index_size,
                    idx_scan,
                    idx_tup_read,
                    idx_tup_fetch
                FROM pg_stat_user_indexes
                WHERE relname = 'emb_1024'
                ORDER BY indexrelname
            """)
            print(f"\nIndex Statistics:")
            for row in cur.fetchall():
                indexname, size, scans, reads, fetches = row
                print(f"  {indexname}:")
                print(f"    Size: {size}")
                print(f"    Scans: {scans}")
                print(f"    Tuples read: {reads}")
                print(f"    Tuples fetched: {fetches}")

            # Get index definition
            cur.execute("""
                SELECT indexdef
                FROM pg_indexes
                WHERE tablename = 'emb_1024' AND indexname LIKE '%hnsw%'
            """)
            result = cur.fetchone()
            if result:
                print(f"\nCurrent HNSW Index Definition:")
                print(f"  {result[0]}")

            # Check current HNSW parameters
            cur.execute("SHOW hnsw.ef_search")
            ef_search = cur.fetchone()[0]
            print(f"\nCurrent Query Parameters:")
            print(f"  hnsw.ef_search: {ef_search}")

            # Check if chunks table has text_search column
            cur.execute("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'chunks' AND table_schema = 'public'
                ORDER BY ordinal_position
            """)
            print(f"\nChunks Table Columns:")
            has_text_search = False
            for col, dtype in cur.fetchall():
                print(f"  {col}: {dtype}")
                if col == 'text_search':
                    has_text_search = True

            if has_text_search:
                print("\n✅ Full-text search column exists!")
                # Check if there's a GIN index
                cur.execute("""
                    SELECT indexname, indexdef
                    FROM pg_indexes
                    WHERE tablename = 'chunks' AND indexdef LIKE '%GIN%'
                """)
                gin_indexes = cur.fetchall()
                if gin_indexes:
                    print("✅ GIN index exists for full-text search:")
                    for name, defn in gin_indexes:
                        print(f"  {name}")
                else:
                    print("❌ No GIN index found for full-text search")
            else:
                print("\n❌ No text_search column found - hybrid search not available")

            # Recommendations
            print("\n" + "=" * 80)
            print("RECOMMENDATIONS")
            print("=" * 80)

            print("\n1. HNSW Index Optimization:")
            print("   Your index uses default parameters. For 60M chunks, consider:")
            print("""
   -- Drop existing index
   DROP INDEX IF EXISTS arctic_hnsw_idx_v2;

   -- Recreate with optimized parameters
   CREATE INDEX arctic_hnsw_idx_v3 ON emb_1024
   USING hnsw (embedding vector_cosine_ops)
   WITH (
       m = 24,              -- Increase from default 16 for better recall
       ef_construction = 96 -- Increase from default 64 for better quality
   );
   """)

            print("\n2. Query-time Parameter Tuning:")
            print("   Try increasing ef_search for better recall:")
            print("""
   -- In your session or postgresql.conf
   SET hnsw.ef_search = 100;  -- Default is 40
   -- Try: 80, 100, 200 and measure speed vs recall
   """)

            if not has_text_search:
                print("\n3. Enable Hybrid Search (HIGHEST IMPACT):")
                print("   Add full-text search capability to chunks table:")
                print("""
   -- Add tsvector column
   ALTER TABLE chunks ADD COLUMN text_search tsvector;

   -- Populate it (this may take a while for 37M rows)
   UPDATE chunks SET text_search = to_tsvector('english', text);

   -- Create GIN index for fast full-text search
   CREATE INDEX idx_chunks_text_search ON chunks USING GIN(text_search);

   -- Keep it updated with a trigger
   CREATE TRIGGER chunks_text_search_update
   BEFORE INSERT OR UPDATE ON chunks
   FOR EACH ROW
   EXECUTE FUNCTION tsvector_update_trigger(text_search, 'pg_catalog.english', text);
   """)
                print("\n   Expected impact: 263s → 2-5s (50-100x speedup!)")

            else:
                print("\n3. Use Hybrid Search:")
                print("   You have full-text search capability!")
                print("   Run: uv run python hybrid_search.py \"your query\"")

            print("\n4. PostgreSQL Configuration:")
            print("   Add to postgresql.conf:")
            print("""
   work_mem = 256MB              # For sorting operations
   shared_buffers = 8GB          # Increase for better caching
   effective_cache_size = 24GB   # Hint for query planner
   hnsw.ef_search = 100          # Better recall at query time
   """)

            print("\n5. Consider Table Partitioning:")
            print("   If queries target specific document types/domains")
            print("   See: VECTOR_SEARCH_OPTIMIZATION.md")


if __name__ == "__main__":
    try:
        analyze_index()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
