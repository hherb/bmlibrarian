#!/usr/bin/env bash
# Phase 0a: run every variant on the same files, cold (empty table) then warm
# (second pass = update path), and checksum the resulting tables after each run
# so the variants are shown to leave identical data. Results: results/*.jsonl
set -euo pipefail
cd "$(dirname "$0")/../.."
FIRST=${FIRST:-1101}
FILES=${FILES:-8}
WORKERS=${WORKERS:-8}
OUT=spikes/pubmed-ingest/results/run_$(date +%Y%m%d_%H%M%S).jsonl
mkdir -p spikes/pubmed-ingest/results
PY="uv run python spikes/pubmed-ingest/bench_python.py"
RS=spikes/pubmed-ingest/rust/target/release/pubmed-ingest-spike
(cd spikes/pubmed-ingest/rust && cargo build --release -q)

checksum() {
  uv run python - <<'EOF' 2>/dev/null
import sys; sys.path.insert(0, "spikes/pubmed-ingest")
import json, bench_python as b
with b.connect() as c:
    r = c.execute("""SELECT count(*), md5(string_agg(concat_ws('|', external_id, doi, title, abstract,
        authors::text, publication, publication_date::text, mesh_terms::text, keywords::text,
        -- all_keywords comes from SELECT DISTINCT without ORDER BY: compare it as a set
        (SELECT array_agg(k ORDER BY k) FROM unnest(all_keywords) k)::text), E'\n' ORDER BY external_id)) FROM spike_ingest.document""").fetchone()
    m = c.execute("""SELECT count(*), md5(string_agg(concat_ws('|', d.external_id, m.grants::text,
        m.publication_types::text, m.is_retracted::text, m.author_affiliations::text), E'\n'
        ORDER BY d.external_id)) FROM spike_ingest.document_metadata m
        JOIN spike_ingest.document d ON d.id = m.document_id""").fetchone()
    print(json.dumps({"docs": r[0], "doc_md5": r[1], "meta": m[0], "meta_md5": m[1]}))
EOF
}

run() {  # label, command...
  local label=$1; shift
  local t0 res
  res=$("$@" 2>/tmp/spike_err_$$ | tail -1) || { echo "FAILED $label"; cat /tmp/spike_err_$$; exit 1; }
  echo "{\"run\": \"$label\", \"result\": $res, \"checksum\": $(checksum)}" | tee -a "$OUT"
}

# parse-only scaling
#run parse-python-1   $PY parse --first $FIRST --files $FILES
#for t in 1 4 8 12; do run parse-rust-$t $RS parse --first $FIRST --files $FILES --threads $t; done

# load variants: cold then warm
run p1-cold $PY p1 --first $FIRST --files $FILES --reset
run p1-warm $PY p1 --first $FIRST --files $FILES
run p2-cold $PY p2 --first $FIRST --files $FILES --reset
run p2-warm $PY p2 --first $FIRST --files $FILES
run p3-cold $PY p3 --first $FIRST --files $FILES --workers $WORKERS --reset
run p3-warm $PY p3 --first $FIRST --files $FILES --workers $WORKERS
run r1-cold $RS load --first $FIRST --files $FILES --threads 1 --reset
run r1-warm $RS load --first $FIRST --files $FILES --threads 1
run r2-cold $RS load --first $FIRST --files $FILES --threads $WORKERS --reset
run r2-warm $RS load --first $FIRST --files $FILES --threads $WORKERS
echo "wrote $OUT"
