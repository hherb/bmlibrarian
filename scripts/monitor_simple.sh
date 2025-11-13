#!/bin/bash
# Simple index build monitor

DB_NAME="${POSTGRES_DB:-knowledgebase}"

echo "Monitoring index build for: $DB_NAME"
echo "Press Ctrl+C to stop"
echo ""

while true; do
    clear
    echo "=========================================="
    echo "HNSW Index Build Progress"
    echo "=========================================="
    echo ""
    echo "$(date '+%Y-%m-%d %H:%M:%S')"
    echo ""

    psql $DB_NAME -c "
        SELECT
            phase,
            round(100.0 * tuples_done / nullif(tuples_total, 0), 1) AS \"Progress %\",
            tuples_done AS \"Tuples Done\",
            tuples_total AS \"Tuples Total\",
            pg_size_pretty(tuples_done * 8192::bigint) AS \"Size Processed\"
        FROM pg_stat_progress_create_index;
    " 2>/dev/null

    if [ $? -ne 0 ]; then
        echo "No index build in progress or completed"
        break
    fi

    echo ""
    echo "Refreshing every 10 seconds..."
    sleep 10
done

echo ""
echo "Monitoring stopped."
