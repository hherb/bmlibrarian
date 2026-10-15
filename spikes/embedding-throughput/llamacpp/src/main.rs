//! arctic-embed-l-v2.0 through llama.cpp in-process (llama-cpp-2, Metal).
//!
//! Same GGUF file Ollama serves (`snowflake-arctic-embed2`, F16), so the only
//! differences from the measured Ollama run are the HTTP/JSON layer and the
//! batching: texts are tokenized, sorted by length, and packed many sequences per
//! `LlamaBatch` (up to `--ubatch` tokens and `--seqs` sequences), decoded once,
//! CLS-pooled by llama.cpp, then truncated to 256 dims and L2-normalised here.
//! Writes `../results/<name>.npy` and a row in `../results/timings.jsonl`, the
//! format `bench_python.py compare` reads.

use std::fs::{File, OpenOptions};
use std::io::{BufRead, BufReader, Write};
use std::num::NonZeroU32;
use std::path::{Path, PathBuf};
use std::time::Instant;

use anyhow::{Context, Result, anyhow};
use clap::Parser;
use llama_cpp_2::context::params::{LlamaContextParams, LlamaPoolingType};
use llama_cpp_2::llama_backend::LlamaBackend;
use llama_cpp_2::llama_batch::LlamaBatch;
use llama_cpp_2::model::LlamaModel;
use llama_cpp_2::model::params::LlamaModelParams;
use llama_cpp_2::token::LlamaToken;

const PRODUCTION_DIM: usize = 256;
const ALL_LAYERS_ON_GPU: u32 = 999;
const WARMUP_TEXTS: usize = 64;

#[derive(Parser, Debug)]
#[command(about = "arctic-embed-l-v2.0 via llama.cpp (Metal)")]
struct Args {
    /// GGUF file (e.g. Ollama's blob for snowflake-arctic-embed2).
    #[arg(long)]
    gguf: PathBuf,
    #[arg(long, default_value = "../results/texts.jsonl")]
    texts: PathBuf,
    #[arg(long, default_value = "../results")]
    results: PathBuf,
    /// Tokens per batch (n_ctx = n_batch = n_ubatch).
    #[arg(long, default_value_t = 4096)]
    ubatch: u32,
    /// Max sequences per batch (n_seq_max).
    #[arg(long, default_value_t = 32)]
    seqs: u32,
    /// Per-text token cap (longer inputs are truncated, keeping the final </s>).
    #[arg(long, default_value_t = 2048)]
    max_tokens: usize,
}

fn load_texts(path: &Path) -> Result<Vec<String>> {
    BufReader::new(File::open(path).with_context(|| format!("opening {}", path.display()))?)
        .lines()
        .map(|l| {
            let v: serde_json::Value = serde_json::from_str(&l?)?;
            v["text"].as_str().map(str::to_string).ok_or_else(|| anyhow!("row without text"))
        })
        .collect()
}

/// Minimal `.npy` (v1.0, little-endian f32) writer.
fn write_npy(path: &Path, rows: &[Vec<f32>]) -> Result<()> {
    let cols = rows.first().map_or(0, Vec::len);
    let mut header = format!("{{'descr': '<f4', 'fortran_order': False, 'shape': ({}, {cols}), }}", rows.len());
    let pad = 64 - (10 + header.len() + 1) % 64;
    header.push_str(&" ".repeat(pad % 64));
    header.push('\n');
    let mut f = File::create(path)?;
    f.write_all(b"\x93NUMPY\x01\x00")?;
    f.write_all(&(header.len() as u16).to_le_bytes())?;
    f.write_all(header.as_bytes())?;
    for row in rows {
        for v in row {
            f.write_all(&v.to_le_bytes())?;
        }
    }
    Ok(())
}

/// Matryoshka truncation + L2 normalisation (the production vector).
fn truncate_normalise(v: &[f32]) -> Vec<f32> {
    let t = &v[..PRODUCTION_DIM.min(v.len())];
    let norm = t.iter().map(|x| x * x).sum::<f32>().sqrt().max(1e-12);
    t.iter().map(|x| x / norm).collect()
}

/// Greedy packing of length-sorted sequences into batches within both limits.
fn pack(order: &[usize], lens: &[usize], max_tokens: usize, max_seqs: usize) -> Vec<Vec<usize>> {
    let mut batches = Vec::new();
    let mut cur = Vec::new();
    let mut used = 0;
    for &i in order {
        if !cur.is_empty() && (used + lens[i] > max_tokens || cur.len() == max_seqs) {
            batches.push(std::mem::take(&mut cur));
            used = 0;
        }
        cur.push(i);
        used += lens[i];
    }
    if !cur.is_empty() {
        batches.push(cur);
    }
    batches
}

fn main() -> Result<()> {
    let args = Args::parse();
    let texts = load_texts(&args.texts)?;
    let backend = LlamaBackend::init()?;
    let model = LlamaModel::load_from_file(
        &backend,
        &args.gguf,
        &LlamaModelParams::default().with_n_gpu_layers(ALL_LAYERS_ON_GPU),
    )?;
    let ctx_params = LlamaContextParams::default()
        .with_n_ctx(NonZeroU32::new(args.ubatch))
        .with_n_batch(args.ubatch)
        .with_n_ubatch(args.ubatch)
        .with_n_seq_max(args.seqs)
        .with_embeddings(true)
        .with_pooling_type(LlamaPoolingType::Cls);
    let mut ctx = model.new_context(&backend, ctx_params)?;
    let vocab = model.vocab();

    let mut run = |subset: &[String]| -> Result<(Vec<Vec<f32>>, usize)> {
        let mut ids: Vec<Vec<LlamaToken>> = subset.iter().map(|t| vocab.tokenize(t.as_bytes(), true, false)).collect();
        for t in &mut ids {
            if t.len() > args.max_tokens {
                let last = *t.last().expect("non-empty");
                t.truncate(args.max_tokens - 1);
                t.push(last);
            }
        }
        let lens: Vec<usize> = ids.iter().map(Vec::len).collect();
        let tokens = lens.iter().sum();
        let mut order: Vec<usize> = (0..ids.len()).collect();
        order.sort_by_key(|&i| std::cmp::Reverse(lens[i]));
        let mut out = vec![Vec::new(); ids.len()];
        let mut batch = LlamaBatch::new(args.ubatch as usize, args.seqs as i32);
        for group in pack(&order, &lens, args.ubatch as usize, args.seqs as usize) {
            batch.clear();
            for (seq, &i) in group.iter().enumerate() {
                batch.add_sequence(&ids[i], seq as i32, false)?;
            }
            ctx.clear_kv_cache();
            ctx.decode(&mut batch).map_err(|e| anyhow!("decode: {e}"))?;
            for (seq, &i) in group.iter().enumerate() {
                out[i] = truncate_normalise(ctx.embeddings_seq_ith(seq as i32)?);
            }
        }
        Ok((out, tokens))
    };

    run(&texts[..WARMUP_TEXTS.min(texts.len())])?; // warm-up: Metal pipeline compilation
    let started = Instant::now();
    let (out, tokens) = run(&texts)?;
    let seconds = started.elapsed().as_secs_f64();

    let quant = args.gguf.file_stem().and_then(|n| n.to_str()).and_then(|n| n.rsplit('-').next()).unwrap_or("gguf");
    let name = format!("llamacpp_{quant}_u{}_s{}", args.ubatch, args.seqs);
    write_npy(&args.results.join(format!("{name}.npy")), &out)?;
    let row = serde_json::json!({
        "backend": name, "docs": out.len(), "seconds": (seconds * 100.0).round() / 100.0,
        "docs_per_s": ((out.len() as f64 / seconds) * 10.0).round() / 10.0,
        "tokens": tokens, "tokens_per_s": (tokens as f64 / seconds).round(),
        "ubatch": args.ubatch, "seqs": args.seqs, "gguf": args.gguf.file_name().and_then(|n| n.to_str()),
    });
    println!("{row}");
    writeln!(OpenOptions::new().create(true).append(true).open(args.results.join("timings.jsonl"))?, "{row}")?;
    Ok(())
}
