"""
Tests for benchmarks/embedding_dimension (Matryoshka truncation benchmark).

Pure-function tests plus an end-to-end run with a stub encoder, so no model
download, GPU, database or network is needed.
"""

import argparse
import json
import math
import sys
import zipfile
from pathlib import Path

import numpy as np
import pytest

BENCH_DIR = Path(__file__).resolve().parents[2] / "benchmarks" / "embedding_dimension"
sys.path.insert(0, str(BENCH_DIR))

import beir_data  # noqa: E402
import retrieval_metrics as rm  # noqa: E402
import run_benchmark as rb  # noqa: E402


# --------------------------------------------------------------------------- metrics

class TestTruncateAndNormalize:
    """Matryoshka truncation behaviour."""

    def test_rows_are_unit_length_and_keep_direction(self) -> None:
        emb = np.array([[3.0, 4.0, 12.0, 0.0]], dtype=np.float32)
        out = rm.truncate_and_normalize(emb, 2)
        assert out.shape == (1, 2)
        assert np.allclose(np.linalg.norm(out, axis=1), 1.0)
        assert np.allclose(out[0], [0.6, 0.8])

    def test_zero_row_stays_finite(self) -> None:
        out = rm.truncate_and_normalize(np.zeros((1, 4), dtype=np.float32), 2)
        assert np.isfinite(out).all()

    def test_does_not_modify_input(self) -> None:
        emb = np.array([[1.0, 2.0, 3.0]], dtype=np.float32)
        rm.truncate_and_normalize(emb, 2)
        assert emb.tolist() == [[1.0, 2.0, 3.0]]

    @pytest.mark.parametrize("dim", [0, -1, 5])
    def test_invalid_dim(self, dim: int) -> None:
        with pytest.raises(ValueError):
            rm.truncate_and_normalize(np.ones((2, 4), dtype=np.float32), dim)

    def test_requires_2d(self) -> None:
        with pytest.raises(ValueError):
            rm.truncate_and_normalize(np.ones(4, dtype=np.float32), 2)


class TestRankCorpus:
    """Brute-force ranking."""

    def test_orders_by_similarity(self) -> None:
        docs = np.array([[1, 0], [0, 1], [0.7071, 0.7071]], dtype=np.float32)
        q = np.array([[1, 0], [0, 1]], dtype=np.float32)
        top = rm.rank_corpus(q, docs, 3)
        assert top[0].tolist() == [0, 2, 1]
        assert top[1].tolist() == [1, 2, 0]

    def test_k_larger_than_corpus_is_capped(self) -> None:
        top = rm.rank_corpus(np.ones((1, 2), np.float32), np.ones((3, 2), np.float32), 100)
        assert top.shape == (1, 3)

    def test_ties_break_by_index(self) -> None:
        top = rm.rank_corpus(np.ones((1, 2), np.float32), np.ones((4, 2), np.float32), 4)
        assert top[0].tolist() == [0, 1, 2, 3]

    def test_chunking_matches_unchunked(self) -> None:
        rng = np.random.default_rng(0)
        q = rng.normal(size=(10, 8)).astype(np.float32)
        d = rng.normal(size=(50, 8)).astype(np.float32)
        assert (rm.rank_corpus(q, d, 5, query_chunk_size=3) == rm.rank_corpus(q, d, 5)).all()

    def test_errors(self) -> None:
        with pytest.raises(ValueError):
            rm.rank_corpus(np.ones((1, 2), np.float32), np.ones((1, 3), np.float32), 1)
        with pytest.raises(ValueError):
            rm.rank_corpus(np.ones((1, 2), np.float32), np.ones((1, 2), np.float32), 0)


class TestEvaluateRankings:
    """nDCG / recall / MRR against hand-computed values."""

    def test_perfect_ranking(self) -> None:
        m = rm.evaluate_rankings([["a", "b", "c"]], ["q"], {"q": {"a": 1}})
        assert m.ndcg[0] == pytest.approx(1.0)
        assert m.mrr[0] == pytest.approx(1.0)
        assert m.recall[10][0] == pytest.approx(1.0)

    def test_second_place(self) -> None:
        m = rm.evaluate_rankings([["x", "a"]], ["q"], {"q": {"a": 1}})
        assert m.ndcg[0] == pytest.approx(1 / math.log2(3))
        assert m.mrr[0] == pytest.approx(0.5)

    def test_graded_relevance(self) -> None:
        # ranking puts the grade-1 doc above the grade-2 doc
        m = rm.evaluate_rankings([["lo", "hi"]], ["q"], {"q": {"hi": 2, "lo": 1}})
        dcg = 1 / math.log2(2) + 2 / math.log2(3)
        ideal = 2 / math.log2(2) + 1 / math.log2(3)
        assert m.ndcg[0] == pytest.approx(dcg / ideal)

    def test_recall_cutoffs(self) -> None:
        ranking = [f"d{i}" for i in range(20)]
        qrels = {"q": {"d0": 1, "d15": 1}}
        m = rm.evaluate_rankings([ranking], ["q"], qrels)
        assert m.recall[10][0] == pytest.approx(0.5)
        assert m.recall[100][0] == pytest.approx(1.0)

    def test_miss_scores_zero(self) -> None:
        m = rm.evaluate_rankings([["x"]], ["q"], {"q": {"a": 1}})
        assert m.ndcg[0] == 0 and m.mrr[0] == 0

    def test_query_without_relevant_docs_rejected(self) -> None:
        with pytest.raises(ValueError):
            rm.evaluate_rankings([["a"]], ["q"], {"q": {"a": 0}})

    def test_length_mismatch(self) -> None:
        with pytest.raises(ValueError):
            rm.evaluate_rankings([["a"]], ["q1", "q2"], {})

    def test_means_keys(self) -> None:
        m = rm.evaluate_rankings([["a"]], ["q"], {"q": {"a": 1}})
        assert set(m.means()) == {"ndcg@10", "recall@10", "recall@100", "mrr@10"}


class TestBootstrap:
    """Paired bootstrap and verdicts."""

    def test_identical_has_zero_width_ci(self) -> None:
        a = np.array([0.2, 0.5, 0.9])
        r = rm.paired_bootstrap(a, a.copy(), n_resamples=200)
        assert (r.mean_diff, r.ci_low, r.ci_high) == (0.0, 0.0, 0.0)

    def test_constant_shift(self) -> None:
        a = np.linspace(0, 1, 40)
        r = rm.paired_bootstrap(a - 0.1, a, n_resamples=500)
        assert r.mean_diff == pytest.approx(-0.1)
        assert r.ci_low == pytest.approx(-0.1) and r.ci_high == pytest.approx(-0.1)

    def test_deterministic_for_seed(self) -> None:
        rng = np.random.default_rng(1)
        a, b = rng.random(30), rng.random(30)
        assert rm.paired_bootstrap(a, b, 300, seed=7) == rm.paired_bootstrap(a, b, 300, seed=7)

    def test_input_validation(self) -> None:
        with pytest.raises(ValueError):
            rm.paired_bootstrap(np.ones(3), np.ones(4))
        with pytest.raises(ValueError):
            rm.paired_bootstrap(np.array([]), np.array([]))

    @pytest.mark.parametrize(
        "low,high,expected",
        [(0.01, 0.05, "better"), (-0.01, 0.02, "non-inferior"),
         (-0.08, -0.04, "worse"), (-0.05, 0.01, "inconclusive")],
    )
    def test_verdicts(self, low: float, high: float, expected: str) -> None:
        res = rm.BootstrapResult((low + high) / 2, low, high, 100)
        assert rm.noninferiority_verdict(res, 0.02) == expected

    def test_negative_margin_rejected(self) -> None:
        with pytest.raises(ValueError):
            rm.noninferiority_verdict(rm.BootstrapResult(0, 0, 0, 1), -0.1)


def test_pgvector_size() -> None:
    assert rm.pgvector_bytes_per_vector(1024) == 4104
    assert rm.pgvector_bytes_per_vector(256) == 1032


# ------------------------------------------------------------------------ data loading

def write_dataset(root: Path, n_docs: int = 12, n_queries: int = 4) -> Path:
    """Create a tiny BEIR-format dataset: query i is relevant to doc i."""
    (root / "qrels").mkdir(parents=True)
    with open(root / "corpus.jsonl", "w") as fh:
        for i in range(n_docs):
            fh.write(json.dumps({"_id": f"d{i}", "title": f"title{i}", "text": f"alpha{i} beta{i} common"}) + "\n")
        fh.write("not json\n")
        fh.write(json.dumps({"_id": "bad"}) + "\n")
    with open(root / "queries.jsonl", "w") as fh:
        for i in range(n_queries):
            fh.write(json.dumps({"_id": f"q{i}", "text": f"alpha{i} beta{i}"}) + "\n")
        fh.write(json.dumps({"_id": "orphan", "text": "no qrels"}) + "\n")
    with open(root / "qrels" / "test.tsv", "w") as fh:
        fh.write("query-id\tcorpus-id\tscore\n")
        for i in range(n_queries):
            fh.write(f"q{i}\td{i}\t1\n")
        fh.write("q0\tmissing\t1\nq1\td1\t0\nshort\n")
    return root


class TestBeirData:
    """Loading, validation, sub-sampling and safe extraction."""

    def test_load_filters_bad_rows(self, tmp_path: Path) -> None:
        ds = beir_data.load_beir_dataset(write_dataset(tmp_path / "ds"), name="t")
        assert len(ds.corpus) == 12 and len(ds.queries) == 4
        assert ds.skipped_lines == 2
        assert "orphan" not in ds.queries
        assert ds.corpus["d0"] == "title0 alpha0 beta0 common"
        assert ds.qrels["q0"] == {"d0": 1}
        assert ds.notes

    def test_bad_header_rejected(self, tmp_path: Path) -> None:
        root = write_dataset(tmp_path / "ds")
        (root / "qrels" / "test.tsv").write_text("a\tb\tc\n")
        with pytest.raises(ValueError):
            beir_data.load_beir_dataset(root)

    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            beir_data.load_beir_dataset(tmp_path)

    def test_subsample_keeps_relevant_and_is_seeded(self, tmp_path: Path) -> None:
        ds = beir_data.load_beir_dataset(write_dataset(tmp_path / "ds", n_docs=40))
        a = beir_data.subsample_corpus(ds, 10, seed=1)
        b = beir_data.subsample_corpus(ds, 10, seed=1)
        assert len(a.corpus) == 10 and a.corpus == b.corpus
        assert {"d0", "d1", "d2", "d3"} <= set(a.corpus)

    def test_subsample_never_drops_relevant(self, tmp_path: Path) -> None:
        ds = beir_data.load_beir_dataset(write_dataset(tmp_path / "ds", n_docs=40))
        assert len(beir_data.subsample_corpus(ds, 2, seed=1).corpus) == 4

    def test_subsample_noop_when_small(self, tmp_path: Path) -> None:
        ds = beir_data.load_beir_dataset(write_dataset(tmp_path / "ds"))
        assert beir_data.subsample_corpus(ds, 1000, seed=1) is ds

    @pytest.mark.parametrize("name", ["scifact", "trec-covid", "nfcorpus"])
    def test_valid_names(self, name: str) -> None:
        assert beir_data.validate_dataset_name(name) == name

    @pytest.mark.parametrize("name", ["../x", "a/b", "Sci", "", "a b", "x" * 100])
    def test_invalid_names(self, name: str) -> None:
        with pytest.raises(ValueError):
            beir_data.validate_dataset_name(name)

    def test_zip_slip_rejected(self, tmp_path: Path) -> None:
        archive = tmp_path / "evil.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("../escape.txt", "x")
        with pytest.raises(ValueError):
            beir_data.extract_zip_safely(archive, tmp_path / "out")
        assert not (tmp_path / "escape.txt").exists()

    def test_safe_zip_extracts(self, tmp_path: Path) -> None:
        archive = tmp_path / "ok.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("ds/corpus.jsonl", "{}")
        (tmp_path / "out").mkdir()
        beir_data.extract_zip_safely(archive, tmp_path / "out")
        assert (tmp_path / "out" / "ds" / "corpus.jsonl").exists()


# ------------------------------------------------------------------------ CLI helpers

class TestParsers:
    """CLI option parsing."""

    def test_model_specs(self) -> None:
        specs = rb.parse_model_specs(["a=org/x", "b=org/y"])
        assert [s.label for s in specs] == ["a", "b"] and specs[1].model_id == "org/y"

    @pytest.mark.parametrize("bad", ["nolabel", "=x", "a=", "a@1=x"])
    def test_bad_model_spec(self, bad: str) -> None:
        with pytest.raises(ValueError):
            rb.parse_model_specs([bad])

    def test_duplicate_label(self) -> None:
        with pytest.raises(ValueError):
            rb.parse_model_specs(["a=x", "a=y"])

    def test_config_ref(self) -> None:
        assert rb.parse_config_ref("arctic@1024") == ("arctic", 1024)
        assert rb.parse_config_ref("arctic") == ("arctic", None)
        with pytest.raises(ValueError):
            rb.parse_config_ref("arctic@big")

    def test_label_map_keeps_equals_in_text(self) -> None:
        assert rb.parse_label_map(["m=task: x = y"]) == {"m": "task: x = y"}

    def test_resolve_prompt_priority(self) -> None:
        avail = {"query": "q: "}
        assert rb.resolve_prompt(avail, "query", None, False) == ("query", None)
        assert rb.resolve_prompt(avail, "document", None, False) == (None, None)
        assert rb.resolve_prompt(avail, "query", "X ", False) == (None, "X ")
        assert rb.resolve_prompt(avail, "query", "X ", True) == (None, None)

    def test_resolve_prompt_ignores_empty_model_prompt(self) -> None:
        assert rb.resolve_prompt({"document": ""}, "document", None, False) == (None, None)


# ---------------------------------------------------------------------------- end to end

class FakeEncoder:
    """Bag-of-hashed-tokens encoder: shared tokens => similar vectors."""

    native_dim = 64

    def __init__(self) -> None:
        self.calls = 0

    def _token_vec(self, token: str) -> np.ndarray:
        seed = int.from_bytes(token.encode()[:8].ljust(8, b"\0"), "little") % (2**32)
        return np.random.default_rng(seed).normal(size=self.native_dim)

    def encode(self, texts, role: str) -> np.ndarray:
        self.calls += 1
        return np.stack([sum(self._token_vec(t) for t in text.split()) for text in texts]).astype(np.float32)

    def describe_prompt(self, role: str) -> str:
        return f"fake-{role}"


def make_args(tmp_path: Path, dataset: Path, **overrides) -> argparse.Namespace:
    """Build CLI args for run() without going through argv."""
    argv = ["--datasets", "--custom-dataset", str(dataset), "--cache-dir", str(tmp_path / "cache"),
            "--dims", "64", "32", "16", "--bootstrap-resamples", "200",
            "--model", "big=fake/big", "--model", "small=fake/small"]
    args = rb.build_arg_parser().parse_args(argv + [x for kv in overrides.items() for x in kv])
    return args


class TestEndToEnd:
    """Full pipeline with a stub encoder."""

    def test_run_structure_and_cache(self, tmp_path: Path, capsys) -> None:
        ds = write_dataset(tmp_path / "ds", n_docs=30, n_queries=6)
        args = make_args(tmp_path, ds)
        encoders = {}

        def factory(spec: rb.ModelSpec, _: argparse.Namespace) -> FakeEncoder:
            encoders[spec.label] = FakeEncoder()
            return encoders[spec.label]

        doc = rb.run(args, factory)
        rows = doc["results"]
        assert {(r["model"], r["dim"]) for r in rows} == {
            (m, d) for m in ("big", "small") for d in (64, 32, 16)}
        base = [r for r in rows if r["verdict"] == "baseline"]
        assert len(base) == 1 and base[0]["model"] == "big" and base[0]["dim"] == 64
        same = [r for r in rows if r["model"] == "small" and r["dim"] == 64][0]
        assert same["delta_ndcg10"]["mean"] == pytest.approx(0.0)  # identical encoder
        assert all(0.0 <= r["metrics"]["ndcg@10"] <= 1.0 for r in rows)
        assert "Macro-average" in capsys.readouterr().out
        json.dumps(doc)  # serialisable

        first_calls = {k: v.calls for k, v in encoders.items()}
        assert all(c == 2 for c in first_calls.values())  # docs + queries
        rb.run(make_args(tmp_path, ds), factory)  # second run: all cached
        assert all(v.calls == 0 for v in encoders.values())

    def test_dimension_above_native_is_skipped_native_always_included(self, tmp_path: Path) -> None:
        ds = write_dataset(tmp_path / "ds", n_docs=20, n_queries=4)
        args = make_args(tmp_path, ds)
        args.dims = [4096, 16]
        doc = rb.run(args, lambda s, a: FakeEncoder())
        assert {r["dim"] for r in doc["results"]} == {64, 16}

    def test_failed_model_is_reported_not_fatal(self, tmp_path: Path) -> None:
        ds = write_dataset(tmp_path / "ds", n_docs=20, n_queries=4)

        def factory(spec: rb.ModelSpec, _: argparse.Namespace) -> FakeEncoder:
            if spec.label == "small":
                raise RuntimeError("no weights")
            return FakeEncoder()

        doc = rb.run(make_args(tmp_path, ds), factory)
        assert doc["failures"] == ["small"]
        assert {r["model"] for r in doc["results"]} == {"big"}

    def test_encoder_returning_nan_is_rejected(self, tmp_path: Path) -> None:
        class NanEncoder(FakeEncoder):
            def encode(self, texts, role):
                return np.full((len(texts), self.native_dim), np.nan, dtype=np.float32)

        ds = write_dataset(tmp_path / "ds", n_docs=20, n_queries=4)
        with pytest.raises(ValueError):
            rb.run(make_args(tmp_path, ds), lambda s, a: NanEncoder())

    def test_main_returns_nonzero_on_load_failure(self, tmp_path: Path, monkeypatch) -> None:
        ds = write_dataset(tmp_path / "ds", n_docs=20, n_queries=4)

        def boom(spec, args):
            raise RuntimeError("x")

        monkeypatch.setattr(rb, "make_sentence_transformer_encoder", boom)
        out = tmp_path / "out.json"
        code = rb.main(["--datasets", "--custom-dataset", str(ds), "--cache-dir", str(tmp_path / "c"),
                        "--model", "a=x/y", "-o", str(out)])
        assert code == 1 and json.loads(out.read_text())["failures"] == ["a"]
