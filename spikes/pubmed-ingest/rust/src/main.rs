//! Phase 0a ingest spike — Rust variants (R1 = 1 thread, R2 = N threads).
//!
//! `parse` decompresses and parses only (optionally dumping JSONL for the
//! parity check); `load` also binary-COPYs each file into `spike_ingest` in
//! `bmlibrarian_dev` and runs the shared merge. Files are distributed over a
//! rayon pool; each worker owns one database connection per file, which is the
//! same shape as the Python process-pool variant (P3).

mod load;
mod parse;

use std::fs::File;
use std::io::{BufWriter, Read, Write};
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::Instant;

use anyhow::{Context, Result, bail};
use clap::{Parser, ValueEnum};
use flate2::read::MultiGzDecoder;
use rayon::prelude::*;

#[derive(Copy, Clone, Debug, ValueEnum)]
enum Mode {
    Parse,
    Load,
}

#[derive(Parser, Debug)]
#[command(about = "Phase 0a PubMed ingest spike (Rust)")]
struct Args {
    mode: Mode,
    #[arg(long, default_value_os_t = default_baseline_dir())]
    baseline_dir: PathBuf,
    /// First file number (1-based).
    #[arg(long, default_value_t = 1)]
    first: usize,
    #[arg(long, default_value_t = 4)]
    files: usize,
    #[arg(long, default_value_t = 1)]
    threads: usize,
    /// Truncate the spike tables before loading.
    #[arg(long)]
    reset: bool,
    /// load: skip files already recorded in spike_ingest.ingest_ledger.
    #[arg(long)]
    resume: bool,
    /// parse: write parsed articles as JSONL.
    #[arg(long)]
    dump: Option<PathBuf>,
}

fn default_baseline_dir() -> PathBuf {
    PathBuf::from(std::env::var_os("HOME").unwrap_or_default()).join("knowledgebase/pubmed_data/baseline")
}

fn sql_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../sql")
}

fn pick_files(dir: &Path, first: usize, count: usize) -> Result<Vec<PathBuf>> {
    let mut files: Vec<PathBuf> = std::fs::read_dir(dir)
        .with_context(|| format!("reading {}", dir.display()))?
        .filter_map(|e| e.ok().map(|e| e.path()))
        .filter(|p| {
            let n = p.file_name().and_then(|n| n.to_str()).unwrap_or("");
            n.starts_with("pubmed") && n.ends_with(".xml.gz")
        })
        .collect();
    files.sort();
    let chosen: Vec<PathBuf> = files.into_iter().skip(first - 1).take(count).collect();
    if chosen.len() < count {
        bail!("only {} files available from #{first}", chosen.len());
    }
    Ok(chosen)
}

fn file_name(path: &Path) -> String {
    path.file_name().and_then(|n| n.to_str()).unwrap_or_default().to_string()
}

fn read_gz(path: &Path) -> Result<Vec<u8>> {
    let mut out = Vec::new();
    MultiGzDecoder::new(File::open(path)?).read_to_end(&mut out)?;
    Ok(out)
}

/// Parse every article in one file; parse errors are counted, not fatal.
fn parse_file(path: &Path) -> Result<(Vec<parse::Article>, usize)> {
    let xml = read_gz(path)?;
    let mut articles = Vec::new();
    let mut errors = 0;
    for slice in parse::article_slices(&xml) {
        match parse::parse_article(slice) {
            Ok(Some(a)) => articles.push(a),
            Ok(None) => {}
            Err(e) => {
                errors += 1;
                eprintln!("WARN {}: {e}", path.display());
            }
        }
    }
    Ok((articles, errors))
}

fn main() -> Result<()> {
    let args = Args::parse();
    let files = pick_files(&args.baseline_dir, args.first, args.files)?;
    rayon::ThreadPoolBuilder::new().num_threads(args.threads).build_global()?;
    let sql = sql_dir();

    // SPIKE_SKIP_SCHEMA=1 keeps a deliberately stripped table as it is (bare_load_experiment.py).
    if matches!(args.mode, Mode::Load) && std::env::var_os("SPIKE_SKIP_SCHEMA").is_none() {
        let mut c = load::connect()?;
        c.batch_execute(&std::fs::read_to_string(sql.join("schema.sql"))?)?;
        if args.reset {
            c.batch_execute("TRUNCATE spike_ingest.document, spike_ingest.document_metadata, spike_ingest.ingest_ledger RESTART IDENTITY")?;
        }
    }

    let files: Vec<PathBuf> = if args.resume && matches!(args.mode, Mode::Load) {
        let mut c = load::connect()?;
        let done: std::collections::HashSet<String> = c
            .query("SELECT file FROM spike_ingest.ingest_ledger", &[])?
            .iter()
            .map(|r| r.get(0))
            .collect();
        let todo: Vec<PathBuf> = files.into_iter().filter(|f| !done.contains(&file_name(f))).collect();
        eprintln!("INFO resume: {} files already committed, {} to do", done.len(), todo.len());
        todo
    } else {
        files
    };
    let dump = match &args.dump {
        Some(p) => Some(Mutex::new(BufWriter::new(File::create(p)?))),
        None => None,
    };
    let started = Instant::now();
    let results: Vec<Result<(usize, usize)>> = files
        .par_iter()
        .map(|path| {
            let file_started = Instant::now();
            let (articles, errors) = parse_file(path)?;
            if let Some(d) = &dump {
                let mut d = d.lock().expect("dump lock");
                for a in &articles {
                    writeln!(d, "{}", parse::to_json(a))?;
                }
            }
            if let Mode::Load = args.mode {
                let mut client = load::connect()?;
                load::load_articles(&mut client, &sql, &articles, &file_name(path), file_started)
                    .with_context(|| format!("loading {}", path.display()))?;
            }
            Ok((articles.len(), errors))
        })
        .collect();
    let seconds = started.elapsed().as_secs_f64();
    let (mut total, mut errors) = (0, 0);
    for r in results {
        let (n, e) = r?;
        total += n;
        errors += e;
    }
    println!(
        "{{\"variant\": \"rust-{}\", \"files\": {}, \"workers\": {}, \"articles\": {total}, \
         \"parse_errors\": {errors}, \"seconds\": {seconds:.2}, \"articles_per_s\": {:.1}}}",
        format!("{:?}", args.mode).to_lowercase(),
        files.len(),
        args.threads,
        total as f64 / seconds
    );
    Ok(())
}
