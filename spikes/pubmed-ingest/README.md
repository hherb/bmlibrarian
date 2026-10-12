# Phase 0a — PubMed ingest spike

Compares five ways of importing PubMed baseline files into a copy of
`public.document` and `transparency.document_metadata`. The copy has the same
indexes, generated `search_vector` and `update_all_keywords` trigger.

| Variant | Parse | Load |
|---|---|---|
| `p1` | production parser (`PubMedBulkImporter._parse_article`) | production write pattern: SELECT + INSERT/UPDATE per row, commit per 100, per-row metadata upsert |
| `p2` | production parser | COPY into TEMP staging + set-based merge (`sql/merge.sql`) |
| `p3` | production parser, process pool | as p2, one file per worker |
| `r1` | Rust port of the parser (`rust/src/parse.rs`), 1 thread | binary COPY + the same `sql/merge.sql` |
| `r2` | as r1, rayon pool | as r1, one file per worker |

The Rust parser reproduces ElementTree semantics, including the Python
importer's quirks, and is checked field by field against the Python output
(`compare_parity.py`). The COPY variants of both languages read the same SQL
files at runtime.

```bash
# parity on one file
uv run python spikes/pubmed-ingest/bench_python.py parse --first 1101 --files 1 --dump /tmp/py.jsonl
(cd spikes/pubmed-ingest/rust && cargo build --release)
spikes/pubmed-ingest/rust/target/release/pubmed-ingest-spike parse --first 1101 --files 1 --dump /tmp/rs.jsonl
python3 spikes/pubmed-ingest/compare_parity.py /tmp/py.jsonl /tmp/rs.jsonl

# every variant, cold + warm, with table checksums (FIRST/FILES/WORKERS env vars)
spikes/pubmed-ingest/run_all.sh
```

Input: `~/knowledgebase/pubmed_data/baseline/pubmed25n*.xml.gz`. Output:
`results/run_*.jsonl`. Results and conclusions: `FINDINGS.md`.
