//! The index phase: every paper's title + abstract chunk and, when full text
//! is held, its canonical text cut by bmlib's chunker, embedded and stored in
//! `chunks` + `chunk_embeddings`, one transaction per paper.
//!
//! "Already indexed" is the paper's `publication_index` label: its model,
//! embedding recipe and chunker must be the running ones, and its converter
//! the one its full-text form implies. A new full text or version sets the
//! row `pending` (full-text phase), so its text hash need not be compared.

use std::path::Path;
use std::sync::atomic::{AtomicBool, Ordering};

use bml_db::{CHUNKS, CHUNK_EMBEDDINGS, PUBLICATION_FULLTEXT, PUBLICATION_INDEX};
use bmlib::db::{execute, fetch_one, Db, Row, Value};
use bmlib::embed::{verify_model, Embedder, ARCTIC_EMBED_L_V2_F16, EMBEDDING_RECIPE_VERSION};
use bmlib::fulltext::cache::FullTextCache;
use bmlib::fulltext::canonical::chunk::{
    chunk_canonical, CHUNKER_VERSION, DEFAULT_MAX_CHARS, DEFAULT_OVERLAP_CHARS,
};
use bmlib::fulltext::canonical::model::SourceFormat;
use bmlib::fulltext::canonical::{
    canonical_from_jats, canonical_from_segmented, CanonicalText, JATS_CANONICAL_VERSION,
    PDF_CANONICAL_VERSION,
};
use bmlib::fulltext::jats_reader;
use bmlib::fulltext::pdf_text::{PdfLimit, PdfTextExtractor};
use bmlib::fulltext::segmenter::SectionSegmenter;
use bmlib::fulltext::MupdfExtractor;
use sha2::{Digest, Sha256};

use crate::fulltext::LASTING_RETRY;
use crate::{Phase, PipelineError, Progress};

/// How many chunks are embedded per call.
pub const EMBED_BATCH_SIZE: usize = 16;
/// The converter label of a chunk set made from the title + abstract alone.
pub const ABSTRACT_CONVERTER: &str = "abstract";

/// Turns chunk texts into vectors (bmlib's [`Embedder`]; a stub in tests).
pub trait ChunkEmbedder {
    /// The sha256 of the model file, recorded in each chunk set's label.
    fn model_sha256(&self) -> &str;
    /// One normalised vector per text, in order.
    ///
    /// # Errors
    ///
    /// The model failed, in plain words.
    fn embed(&mut self, texts: &[&str]) -> Result<Vec<Vec<f32>>, String>;
}

/// bmlib's in-process [`Embedder`] over the setup's Arctic GGUF file.
pub struct ModelEmbedder {
    embedder: Embedder,
}

impl ChunkEmbedder for ModelEmbedder {
    fn model_sha256(&self) -> &str {
        self.embedder
            .model()
            .map_or(ARCTIC_EMBED_L_V2_F16.sha256, |m| m.sha256)
    }

    fn embed(&mut self, texts: &[&str]) -> Result<Vec<Vec<f32>>, String> {
        self.embedder
            .embed_documents(texts)
            .map_err(|e| e.to_string())
    }
}

/// Load the embedding model at `path`, checking it is the approved file.
///
/// # Errors
///
/// The file is missing, damaged or cannot be loaded, with the setup hint.
pub fn load_model_embedder(path: &Path) -> Result<Box<dyn ChunkEmbedder>, String> {
    let hint = "run `bml setup` to download it again";
    verify_model(path, &ARCTIC_EMBED_L_V2_F16).map_err(|e| {
        format!(
            "the embedding model {} is missing or damaged ({e}); {hint}",
            path.display()
        )
    })?;
    let embedder = Embedder::load_model(&ARCTIC_EMBED_L_V2_F16, path)
        .map_err(|e| format!("the embedding model could not be loaded ({e}); {hint}"))?;
    Ok(Box::new(ModelEmbedder { embedder }))
}

/// The converter label of a JATS chunk set.
#[must_use]
pub fn jats_converter() -> String {
    SourceFormat::Jats.converter_version(JATS_CANONICAL_VERSION)
}

/// The converter label of a PDF chunk set.
#[must_use]
pub fn pdf_converter() -> String {
    SourceFormat::Pdf.converter_version(PDF_CANONICAL_VERSION)
}

/// What the index phase did.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct IndexReport {
    /// Papers indexed.
    pub indexed: u64,
    /// Of those, with full-text chunks.
    pub fulltext: u64,
    /// Full texts that could not be read, so the paper became abstract-only.
    pub unreadable: u64,
    /// Chunks stored.
    pub chunks: u64,
    /// `stop` was set before every paper was indexed.
    pub stopped: bool,
}

/// One paper due for indexing.
#[derive(Debug, Clone, PartialEq, Eq)]
struct Due {
    id: i64,
    title: String,
    abstract_text: String,
    form: Option<String>,
    cache_key: Option<String>,
}

fn opt_text(row: &Row, name: &str) -> Result<Option<String>, PipelineError> {
    Ok(row.get(name)?.as_str().map(str::to_string))
}

fn next_due(db: &mut dyn Db, model_sha256: &str) -> Result<Option<Due>, PipelineError> {
    let sql = format!(
        "SELECT p.id AS id, p.title AS title, p.abstract AS abstract, f.form AS form, \
                f.cache_key AS cache_key \
         FROM publications p \
         LEFT JOIN {PUBLICATION_FULLTEXT} f ON f.publication_id = p.id \
         LEFT JOIN {PUBLICATION_INDEX} i ON i.publication_id = p.id \
         WHERE i.publication_id IS NULL OR i.status = 'pending' \
            OR i.model_sha256 IS DISTINCT FROM ? OR i.recipe_version IS DISTINCT FROM ? \
            OR i.chunker_version IS DISTINCT FROM ? \
            OR i.converter_version IS DISTINCT FROM \
               (CASE f.form WHEN 'jats' THEN ? WHEN 'pdf' THEN ? ELSE ? END) \
         ORDER BY p.id LIMIT 1"
    );
    let row = fetch_one(
        db,
        &sql,
        &[
            Value::Text(model_sha256.into()),
            Value::Int(EMBEDDING_RECIPE_VERSION.into()),
            Value::Int(CHUNKER_VERSION.into()),
            Value::Text(jats_converter()),
            Value::Text(pdf_converter()),
            Value::Text(ABSTRACT_CONVERTER.into()),
        ],
    )?;
    let Some(row) = row else { return Ok(None) };
    Ok(Some(Due {
        id: row.get_i64("id")?,
        title: row.get_str("title")?.to_string(),
        abstract_text: opt_text(&row, "abstract")?.unwrap_or_default(),
        form: opt_text(&row, "form")?,
        cache_key: opt_text(&row, "cache_key")?,
    }))
}

/// The paper's canonical full text from the cache, or why it cannot be read.
fn canonical(
    cache: &FullTextCache,
    form: &str,
    key: &str,
    title: &str,
) -> Result<CanonicalText, String> {
    match form {
        "jats" => {
            let bytes = cache
                .get_jats(key)
                .map_err(|e| format!("the JATS XML could not be read ({e})"))?
                .ok_or("the JATS XML is missing from the library folder")?;
            let xml = std::str::from_utf8(&bytes)
                .map_err(|e| format!("the JATS XML is not UTF-8 ({e})"))?;
            let article = jats_reader::parse(xml)
                .map_err(|e| format!("the JATS XML does not parse ({e})"))?;
            Ok(canonical_from_jats(&article))
        }
        "pdf" => {
            let path = cache
                .get_pdf(key)
                .ok_or("the PDF is missing from the library folder")?;
            let blocks = MupdfExtractor::new()
                .extract_blocks_with_warnings(&path, &PdfLimit::default())
                .map_err(|e| format!("the PDF could not be read ({e})"))?;
            let document = SectionSegmenter::default().segment_document(
                &blocks.blocks,
                &path.display().to_string(),
                blocks.metadata_title.as_deref().or(Some(title)),
                serde_json::Value::Object(serde_json::Map::new()),
            );
            Ok(canonical_from_segmented(&document))
        }
        other => Err(format!("unknown full-text form {other}")),
    }
}

/// One chunk to store: `None` span for the abstract chunk.
struct Piece {
    text: String,
    span: Option<(usize, usize)>,
}

/// The full-text chunks of `canonical`, or why there are none.
fn fulltext_pieces(canonical: &CanonicalText) -> Result<Vec<Piece>, String> {
    let chunks = chunk_canonical(canonical, DEFAULT_MAX_CHARS, DEFAULT_OVERLAP_CHARS)
        .map_err(|e| format!("the full text could not be chunked ({e})"))?;
    if chunks.is_empty() {
        return Err("the full text holds no text to index".into());
    }
    let chars: Vec<char> = canonical.text.chars().collect();
    Ok(chunks
        .iter()
        .map(|c| Piece {
            text: chars[c.span.start..c.span.end].iter().collect(),
            span: Some((c.span.start, c.span.end)),
        })
        .collect())
}

fn sha256_hex(text: &str) -> String {
    Sha256::digest(text.as_bytes())
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}

fn halfvec_literal(vector: &[f32]) -> String {
    let parts: Vec<String> = vector.iter().map(f32::to_string).collect();
    format!("[{}]", parts.join(","))
}

fn int(n: usize) -> Value {
    Value::Int(i64::try_from(n).unwrap_or(i64::MAX))
}

/// Index one paper; returns (chunks stored, had full text, full text unreadable).
fn index_paper(
    db: &mut dyn Db,
    cache: &FullTextCache,
    embedder: &mut dyn ChunkEmbedder,
    due: &Due,
) -> Result<(usize, bool, bool), PipelineError> {
    let abstract_chunk = [due.title.trim(), due.abstract_text.trim()]
        .iter()
        .filter(|s| !s.is_empty())
        .copied()
        .collect::<Vec<_>>()
        .join("\n\n");
    let fulltext = match (due.form.as_deref(), due.cache_key.as_deref()) {
        (Some(form @ ("jats" | "pdf")), Some(key)) => Some(
            canonical(cache, form, key, &due.title)
                .and_then(|c| fulltext_pieces(&c).map(|pieces| (c, pieces))),
        ),
        _ => None,
    };
    let (converter, text_sha256, mut pieces, unreadable) = match fulltext {
        Some(Ok((canonical, pieces))) => (
            canonical.converter_version.clone(),
            sha256_hex(&canonical.text),
            pieces,
            None,
        ),
        Some(Err(reason)) => (
            ABSTRACT_CONVERTER.to_string(),
            sha256_hex(&abstract_chunk),
            Vec::new(),
            Some(reason),
        ),
        None => (
            ABSTRACT_CONVERTER.to_string(),
            sha256_hex(&abstract_chunk),
            Vec::new(),
            None,
        ),
    };
    let has_fulltext = !pieces.is_empty();
    if !abstract_chunk.is_empty() {
        pieces.insert(
            0,
            Piece {
                text: abstract_chunk,
                span: None,
            },
        );
    }
    let mut vectors = Vec::with_capacity(pieces.len());
    for batch in pieces.chunks(EMBED_BATCH_SIZE) {
        let texts: Vec<&str> = batch.iter().map(|p| p.text.as_str()).collect();
        vectors.extend(embedder.embed(&texts).map_err(PipelineError::Embed)?);
    }
    if vectors.len() != pieces.len() {
        return Err(PipelineError::Embed(format!(
            "the model returned {} vectors for {} chunks",
            vectors.len(),
            pieces.len()
        )));
    }

    let mut tx = db.begin()?;
    if let Some(reason) = &unreadable {
        execute(
            &mut *tx,
            &format!(
                "UPDATE {PUBLICATION_FULLTEXT} SET form = 'abstract', version_held = NULL, \
                 cache_key = NULL, cache_path = NULL, attempts = attempts + 1, last_error = ?, \
                 last_error_kind = 'lasting', retry_after = now() + make_interval(secs => ?), \
                 updated_at = now() WHERE publication_id = ?"
            ),
            &[
                Value::Text(reason.clone()),
                Value::Int(i64::try_from(LASTING_RETRY.as_secs()).unwrap_or(i64::MAX)),
                Value::Int(due.id),
            ],
        )?;
    }
    execute(
        &mut *tx,
        &format!("DELETE FROM {CHUNKS} WHERE publication_id = ?"),
        &[Value::Int(due.id)],
    )?;
    for (ordinal, (piece, vector)) in pieces.iter().zip(&vectors).enumerate() {
        let (kind, start, end) = match piece.span {
            Some((s, e)) => ("fulltext", int(s), int(e)),
            None => ("abstract", Value::Null, Value::Null),
        };
        let row = fetch_one(
            &mut *tx,
            &format!(
                "INSERT INTO {CHUNKS} (publication_id, ordinal, kind, text, span_start, span_end) \
                 VALUES (?, ?, ?, ?, CAST(? AS INTEGER), CAST(? AS INTEGER)) RETURNING id"
            ),
            &[
                Value::Int(due.id),
                int(ordinal),
                Value::Text(kind.into()),
                Value::Text(piece.text.clone()),
                start,
                end,
            ],
        )?
        .ok_or_else(|| PipelineError::Other("a chunk insert returned no id".into()))?;
        execute(
            &mut *tx,
            &format!(
                "INSERT INTO {CHUNK_EMBEDDINGS} (chunk_id, embedding) \
                 VALUES (?, CAST(CAST(? AS TEXT) AS halfvec))"
            ),
            &[
                Value::Int(row.get_i64("id")?),
                Value::Text(halfvec_literal(vector)),
            ],
        )?;
    }
    execute(
        &mut *tx,
        &format!(
            "INSERT INTO {PUBLICATION_INDEX} (publication_id, status, model_sha256, recipe_version, \
             chunker_version, converter_version, text_sha256, chunk_count) \
             VALUES (?, 'complete', ?, ?, ?, ?, ?, ?) \
             ON CONFLICT (publication_id) DO UPDATE SET status = 'complete', \
             model_sha256 = excluded.model_sha256, recipe_version = excluded.recipe_version, \
             chunker_version = excluded.chunker_version, \
             converter_version = excluded.converter_version, text_sha256 = excluded.text_sha256, \
             chunk_count = excluded.chunk_count, updated_at = now()"
        ),
        &[
            Value::Int(due.id),
            Value::Text(embedder.model_sha256().into()),
            Value::Int(EMBEDDING_RECIPE_VERSION.into()),
            Value::Int(CHUNKER_VERSION.into()),
            Value::Text(converter),
            Value::Text(text_sha256),
            int(pieces.len()),
        ],
    )?;
    tx.commit()?;
    if unreadable.is_some() {
        if let Some(key) = &due.cache_key {
            cache.delete(key);
        }
    }
    Ok((pieces.len(), has_fulltext, unreadable.is_some()))
}

/// Run the index phase (see the module docs).
///
/// # Errors
///
/// A database or model failure; papers already indexed stay indexed.
pub fn run(
    db: &mut dyn Db,
    cache: &FullTextCache,
    embedder: &mut dyn ChunkEmbedder,
    stop: &AtomicBool,
    progress: &mut dyn FnMut(Progress),
) -> Result<IndexReport, PipelineError> {
    let mut report = IndexReport::default();
    let model = embedder.model_sha256().to_string();
    while let Some(due) = next_due(db, &model)? {
        if stop.load(Ordering::Relaxed) {
            report.stopped = true;
            break;
        }
        let (chunks, fulltext, unreadable) = index_paper(db, cache, embedder, &due)?;
        report.indexed += 1;
        report.chunks += chunks as u64;
        if fulltext {
            report.fulltext += 1;
        }
        if unreadable {
            report.unreadable += 1;
            progress(Progress {
                phase: Phase::Index,
                message: format!(
                    "paper {}: its full text could not be read; indexed its abstract",
                    due.id
                ),
            });
        }
    }
    Ok(report)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn halfvec_literals_are_bracketed_lists() {
        assert_eq!(halfvec_literal(&[0.5, -1.0, 0.0]), "[0.5,-1,0]");
    }

    #[test]
    fn converter_labels_name_their_format() {
        assert!(
            jats_converter().starts_with("jats-"),
            "{}",
            jats_converter()
        );
        assert!(pdf_converter().starts_with("pdf-"), "{}", pdf_converter());
        assert_ne!(jats_converter(), ABSTRACT_CONVERTER);
    }
}
