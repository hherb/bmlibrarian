#!/bin/bash
# Monitor HNSW index build progress with time estimates

DB_NAME="${POSTGRES_DB:-knowledgebase}"

echo "Monitoring index build progress for database: $DB_NAME"
echo "Press Ctrl+C to stop monitoring"
echo ""

# Record start time
START_TIME=$(date +%s)
LAST_TUPLES=0
LAST_TIME=$START_TIME

while true; do
    # Get current progress
    RESULT=$(psql $DB_NAME -t -c "
        SELECT
            phase,
            tuples_done,
            tuples_total,
            round(100.0 * tuples_done / nullif(tuples_total, 0), 1) AS pct_complete
        FROM pg_stat_progress_create_index
    " 2>/dev/null)

    if [ -z "$RESULT" ]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') - No index build in progress or completed"
        break
    fi

    # Parse results
    PHASE=$(echo "$RESULT" | awk '{print $1}' | tr -d ' ')
    TUPLES_DONE=$(echo "$RESULT" | awk '{print $2}' | tr -d ' ')
    TUPLES_TOTAL=$(echo "$RESULT" | awk '{print $3}' | tr -d ' ')
    PCT=$(echo "$RESULT" | awk '{print $4}' | tr -d ' ')

    # Handle empty values
    TUPLES_DONE=${TUPLES_DONE:-0}
    TUPLES_TOTAL=${TUPLES_TOTAL:-1}
    PCT=${PCT:-0}

    # Calculate progress since last check
    CURRENT_TIME=$(date +%s)
    TIME_ELAPSED=$((CURRENT_TIME - START_TIME))
    TUPLES_SINCE_LAST=$((TUPLES_DONE - LAST_TUPLES))
    TIME_SINCE_LAST=$((CURRENT_TIME - LAST_TIME))

    # Calculate rate and ETA
    if [ $TUPLES_DONE -gt 0 ] && [ $TIME_ELAPSED -gt 0 ]; then
        TUPLES_PER_SEC=$(echo "scale=2; $TUPLES_DONE / $TIME_ELAPSED" | bc)
        TUPLES_REMAINING=$((TUPLES_TOTAL - TUPLES_DONE))
        SECONDS_REMAINING=$(echo "scale=0; $TUPLES_REMAINING / $TUPLES_PER_SEC" | bc)

        # Format time remaining
        HOURS=$((SECONDS_REMAINING / 3600))
        MINUTES=$(((SECONDS_REMAINING % 3600) / 60))
        SECS=$((SECONDS_REMAINING % 60))

        ETA=$(date -d "+${SECONDS_REMAINING} seconds" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date -v +${SECONDS_REMAINING}S '+%Y-%m-%d %H:%M:%S' 2>/dev/null)

        TIME_STR="${HOURS}h ${MINUTES}m ${SECS}s"
    else
        TUPLES_PER_SEC="calculating..."
        TIME_STR="calculating..."
        ETA="calculating..."
    fi

    # Display progress
    clear
    echo "=========================================="
    echo "HNSW Index Build Progress"
    echo "=========================================="
    echo ""
    echo "Phase:              $PHASE"
    echo "Progress:           $PCT%"
    echo "Tuples processed:   $(printf "%'d" $TUPLES_DONE) / $(printf "%'d" $TUPLES_TOTAL)"
    echo "Processing rate:    $TUPLES_PER_SEC tuples/sec"
    echo ""
    echo "Time elapsed:       $(printf '%02d:%02d:%02d' $((TIME_ELAPSED/3600)) $(((TIME_ELAPSED%3600)/60)) $((TIME_ELAPSED%60)))"
    echo "Time remaining:     ~$TIME_STR"
    echo "Estimated finish:   $ETA"
    echo ""
    echo "=========================================="
    echo "Last updated: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "Refreshing every 5 seconds..."
    echo "Press Ctrl+C to stop monitoring"

    # Update for next iteration
    LAST_TUPLES=$TUPLES_DONE
    LAST_TIME=$CURRENT_TIME

    # Wait before next check
    sleep 5
done

echo ""
echo "Monitoring stopped."
