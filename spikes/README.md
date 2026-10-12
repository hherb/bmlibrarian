# Spikes

Throwaway measurement code for the Rust port's Phase 0
(`doc/planning/rust/rust_port_planning.md`). Spikes are not part of the
package, the test suite or the coding standards that apply to `src/`. Each one
answers one question and records the answer in its `FINDINGS.md`.

| Spike | Question |
|---|---|
| `pubmed-ingest/` | How much faster is PubMed baseline ingest in Rust, and how much of the gain comes from design (COPY, set-based merge, parallelism) rather than language? |
| `embedding-throughput/` | Which backend embeds arctic-embed-l-v2.0 fastest on this machine at the production 256 dimensions, and do they agree? |

**Database safety:** the spikes write only to schema `spike_ingest` in
`bmlibrarian_dev`, and refuse to connect to any other database. They connect
with psycopg/`postgres` directly, because `DatabaseManager` runs the
BMLibrarian migrations on whatever database it opens.
