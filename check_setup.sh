#!/bin/bash
# Quick diagnostic script to check vector search setup

echo "=========================================="
echo "Vector Search Setup Diagnostics"
echo "=========================================="

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

DB_NAME="${POSTGRES_DB:-knowledgebase}"
DB_USER="${POSTGRES_USER}"
DB_HOST="${POSTGRES_HOST:-localhost}"
DB_PORT="${POSTGRES_PORT:-5432}"

echo ""
echo "Database: $DB_NAME"
echo "Host: $DB_HOST:$DB_PORT"
echo ""

# Run analysis script
echo "Running Python analysis script..."
echo ""
uv run python analyze_index.py

echo ""
echo "=========================================="
echo "Next Steps"
echo "=========================================="
echo ""
echo "1. Review the analysis above"
echo ""
echo "2. If you DON'T have full-text search set up:"
echo "   - Run: psql $DB_NAME -f optimize_index.sql"
echo "   - This will take time (30-60 min for 60M chunks)"
echo "   - Expected improvement: 263s → 2-5s"
echo ""
echo "3. Test hybrid search:"
echo "   uv run python hybrid_search.py 'your query here'"
echo ""
echo "4. If hybrid search isn't enough, try:"
echo "   - Tune hnsw.ef_search (SET hnsw.ef_search = 100;)"
echo "   - Rebuild HNSW index with m=24, ef_construction=96"
echo ""
