# Spikes

Throwaway measurement code for the Rust port's Phase 0
(`doc/planning/rust/rust_port_planning.md`). Spikes are not part of the
package, the test suite or the coding standards that apply to `src/`. Each one
answers one question and records the answer in its `FINDINGS.md`.

| Spike | Question |
|---|---|
| `pubmed-ingest/` | How much faster is PubMed baseline ingest in Rust, and how much of the gain comes from design (COPY, set-based merge, parallelism) rather than language? |
| `vector-partitions/` | Can 256-d HNSW indexing be split into bounded, restartable per-partition builds, and what do partitions cost in recall and latency? |
| `embedding-throughput/` | Which backend embeds arctic-embed-l-v2.0 fastest on this machine at the production 256 dimensions, and do they agree? |

**Database safety:**
- The spikes write only to schemas `spike_ingest` and `spike_vec` in
  `bmlibrarian_dev`.
- `vector-partitions` additionally *reads* production vectors from
  `knowledgebase`, in READ ONLY transactions. No other database is touched.
- They connect with psycopg/`postgres` directly, because `DatabaseManager`
  runs the BMLibrarian migrations on whatever database it opens.
- `pubmed-ingest/pg_import_profile.py` changes **server-wide** settings
  (approved by the owner for imports): it saves the originals first and
  restores them afterwards.
