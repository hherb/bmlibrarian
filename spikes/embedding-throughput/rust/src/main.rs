//! Phase 0b: snowflake-arctic-embed-l-v2.0 (XLM-RoBERTa large) on candle.
//!
//! Reproduces the sentence-transformers pipeline for *documents*: tokenize
//! (special tokens, truncation at `--max-len`), forward, CLS pooling, then the
//! production step — keep the first 256 dims and L2-renormalise. Texts are
//! sorted by token length before batching, as sentence-transformers does, and
//! restored to input order. Writes `results/<name>.npy` (256-d) and appends a
//! timing row to `results/timings.jsonl`, both read by `bench_python.py compare`.

use std::fs::{File, OpenOptions};
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::time::Instant;

use anyhow::{Context, Result, anyhow};
use candle_core::{DType, Device, IndexOp, Tensor};
use candle_nn::VarBuilder;
use candle_transformers::models::xlm_roberta::{Config, XLMRobertaModel};
use clap::Parser;
use tokenizers::{Tokenizer, TruncationParams};

const PRODUCTION_DIM: usize = 256;
const WARMUP_TEXTS: usize = 64;

#[derive(Parser, Debug)]
#[command(about = "arctic-embed-l-v2.0 on candle (Metal/CPU)")]
struct Args {
    /// HF snapshot directory (config.json, tokenizer.json, model.safetensors).
    #[arg(long)]
    model_dir: PathBuf,
    #[arg(long, default_value = "../results/texts.jsonl")]
    texts: PathBuf,
    #[arg(long, default_value = "../results")]
    results: PathBuf,
    #[arg(long, default_value_t = 32)]
    batch: usize,
    /// Token cap; sentence-transformers uses 8192 for this model.
    #[arg(long, default_value_t = 8192)]
    max_len: usize,
    #[arg(long)]
    cpu: bool,
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

/// Minimal `.npy` (v1.0, little-endian f32, C order) writer.
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

struct Embedder {
    model: XLMRobertaModel,
    tokenizer: Tokenizer,
    device: Device,
    pad_id: u32,
}

impl Embedder {
    fn load(dir: &Path, device: Device, max_len: usize) -> Result<Self> {
        let cfg: Config = serde_json::from_reader(File::open(dir.join("config.json"))?)?;
        let mut tokenizer = Tokenizer::from_file(dir.join("tokenizer.json")).map_err(|e| anyhow!("{e}"))?;
        tokenizer
            .with_truncation(Some(TruncationParams { max_length: max_len, ..Default::default() }))
            .map_err(|e| anyhow!("{e}"))?;
        tokenizer.with_padding(None);
        let vb = unsafe { VarBuilder::from_mmaped_safetensors(&[dir.join("model.safetensors")], DType::F32, &device)? };
        let model = XLMRobertaModel::new(&cfg, vb)?;
        Ok(Self { model, tokenizer, device, pad_id: cfg.pad_token_id })
    }

    fn token_ids(&self, texts: &[String]) -> Result<Vec<Vec<u32>>> {
        let enc = self.tokenizer.encode_batch(texts.to_vec(), true).map_err(|e| anyhow!("{e}"))?;
        Ok(enc.into_iter().map(|e| e.get_ids().to_vec()).collect())
    }

    /// CLS-pooled, 256-d truncated, L2-normalised embeddings for one padded batch.
    fn embed(&self, ids: &[&Vec<u32>]) -> Result<Vec<Vec<f32>>> {
        let max = ids.iter().map(|v| v.len()).max().unwrap_or(0);
        let mut flat = Vec::with_capacity(ids.len() * max);
        let mut mask = Vec::with_capacity(ids.len() * max);
        for v in ids {
            flat.extend_from_slice(v);
            flat.extend(std::iter::repeat_n(self.pad_id, max - v.len()));
            mask.extend(std::iter::repeat_n(1u32, v.len()));
            mask.extend(std::iter::repeat_n(0u32, max - v.len()));
        }
        let shape = (ids.len(), max);
        let input = Tensor::from_vec(flat, shape, &self.device)?;
        let attn = Tensor::from_vec(mask, shape, &self.device)?;
        let types = input.zeros_like()?;
        let hidden = self.model.forward(&input, &attn, &types, None, None, None)?;
        let cls = hidden.i((.., 0, ..PRODUCTION_DIM))?;
        let norm = cls.sqr()?.sum_keepdim(1)?.sqrt()?;
        let out = cls.broadcast_div(&norm)?;
        Ok(out.to_vec2::<f32>()?)
    }
}

fn main() -> Result<()> {
    let args = Args::parse();
    let device = if args.cpu { Device::Cpu } else { Device::new_metal(0)? };
    let texts = load_texts(&args.texts)?;
    let embedder = Embedder::load(&args.model_dir, device.clone(), args.max_len)?;

    // Warm-up: compiles Metal kernels for the shapes we hit first.
    let warm = embedder.token_ids(&texts[..WARMUP_TEXTS.min(texts.len())])?;
    embedder.embed(&warm.iter().take(args.batch).collect::<Vec<_>>())?;

    let started = Instant::now();
    let ids = embedder.token_ids(&texts)?;
    let tokens: usize = ids.iter().map(Vec::len).sum();
    let mut order: Vec<usize> = (0..ids.len()).collect();
    order.sort_by_key(|&i| std::cmp::Reverse(ids[i].len()));
    let mut out = vec![Vec::new(); ids.len()];
    for chunk in order.chunks(args.batch) {
        let batch: Vec<&Vec<u32>> = chunk.iter().map(|&i| &ids[i]).collect();
        for (&i, emb) in chunk.iter().zip(embedder.embed(&batch)?) {
            out[i] = emb;
        }
    }
    device.synchronize()?;
    let seconds = started.elapsed().as_secs_f64();

    let name = format!("candle_{}_bs{}", if args.cpu { "cpu" } else { "metal" }, args.batch);
    write_npy(&args.results.join(format!("{name}.npy")), &out)?;
    let row = serde_json::json!({
        "backend": name, "docs": out.len(), "seconds": (seconds * 100.0).round() / 100.0,
        "docs_per_s": ((out.len() as f64 / seconds) * 10.0).round() / 10.0,
        "batch": args.batch, "tokens": tokens, "tokens_per_s": (tokens as f64 / seconds).round(),
        "max_seq_length": args.max_len, "dtype": "f32",
    });
    println!("{row}");
    writeln!(OpenOptions::new().create(true).append(true).open(args.results.join("timings.jsonl"))?, "{row}")?;
    Ok(())
}
