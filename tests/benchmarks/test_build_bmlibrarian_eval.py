"""
Tests for benchmarks/embedding_dimension/build_bmlibrarian_eval.py.

Only the pure qrels/corpus logic is tested; database access is not exercised.
"""

import sys
from pathlib import Path

BENCH_DIR = Path(__file__).resolve().parents[2] / "benchmarks" / "embedding_dimension"
sys.path.insert(0, str(BENCH_DIR))

import beir_data  # noqa: E402
import build_bmlibrarian_eval as bbe  # noqa: E402


class TestCleanAbstract:
    """Abstract normalisation."""

    def test_strips_markdown_emphasis_and_whitespace(self) -> None:
        assert bbe.clean_abstract("**BACKGROUND:**  Aspirin\n\nworks `x`") == "BACKGROUND: Aspirin works x"

    def test_none_and_empty(self) -> None:
        assert bbe.clean_abstract(None) == ""
        assert bbe.clean_abstract("   ") == ""


class TestGrades:
    """Score-to-grade mapping and qrels accumulation."""

    def test_grade_mapping(self) -> None:
        assert bbe.grade_from_score(5.0, bbe.EVIDENCE_GRADES) == 2
        assert bbe.grade_from_score(4, bbe.EVIDENCE_GRADES) == 1
        assert bbe.grade_from_score(3, bbe.EVIDENCE_GRADES) == 0
        assert bbe.grade_from_score(None, bbe.EVIDENCE_GRADES) == 0
        assert bbe.grade_from_score("junk", bbe.EVIDENCE_GRADES) == 0  # type: ignore[arg-type]

    def test_add_qrel_keeps_highest_and_ignores_zero(self) -> None:
        qrels: bbe.Qrels = {}
        bbe.add_qrel(qrels, "q", "d", 1)
        bbe.add_qrel(qrels, "q", "d", 2)
        bbe.add_qrel(qrels, "q", "d", 1)
        bbe.add_qrel(qrels, "q", "e", 0)
        assert qrels == {"q": {"d": 2}}


class TestPubmedqaSets:
    """Source-only and graded PubMedQA sets."""

    def test_source_and_evidence(self) -> None:
        statements = [("1", " Does X help? ", "10"), ("2", "Is Y bad?", None)]
        evidence = [("1", "11", 5.0), ("1", "12", 4.0), ("1", "13", 3.0),
                    ("1", "10", 4.0), ("2", "14", 5.0)]
        source, graded = bbe.build_pubmedqa_sets(statements, evidence)
        assert source.queries == {"1": "Does X help?"}
        assert source.qrels == {"1": {"10": 1}}
        # source paper keeps grade 2 even though its evidence score maps to 1
        assert graded.qrels == {"1": {"10": 2, "11": 2, "12": 1}}
        assert graded.queries == source.queries
        assert any("1 statements skipped" in n for n in source.notes)


class TestResearchSet:
    """Research-question set and duplicate merging."""

    def test_merges_typo_duplicates_into_earliest_id(self) -> None:
        questions = {"5": "Is prophylactic methylprednisolone effective for AMS?",
                     "8": "What is Achenbach syndrome?",
                     "10": "s prophylactic methylprednisolone effective for AMS?"}
        assert bbe.merge_near_duplicates(questions) == {"5": "5", "8": "8", "10": "5"}

    def test_grades_and_drops_queries_without_relevant_docs(self) -> None:
        questions = {"1": "aspirin benefits", "2": "coffee and AF", "3": "aspirin benefits?"}
        scores = [("1", "a", 5), ("1", "b", 3), ("1", "c", 1), ("3", "d", 4), ("2", "e", 2)]
        result = bbe.build_research_set(questions, scores)
        assert result.qrels == {"1": {"a": 3, "b": 1, "d": 2}}
        assert result.queries == {"1": "aspirin benefits"}
        assert "1 questions dropped (no document scored >= 3)" in result.notes


class TestWriteAndDrop:
    """Output is loadable by the benchmark and missing documents are handled."""

    def test_drop_missing_docs(self) -> None:
        eval_set = bbe.EvalSet("s", {"q1": "a", "q2": "b"}, {"q1": {"d1": 1, "dx": 1}, "q2": {"dx": 1}})
        out = bbe.drop_missing_docs(eval_set, {"d1": "text"})
        assert out.qrels == {"q1": {"d1": 1}}
        assert out.queries == {"q1": "a"}
        assert "2 judgements dropped (document has no abstract)" in out.notes

    def test_written_dir_round_trips_through_loader(self, tmp_path: Path) -> None:
        corpus = {"d1": "aspirin reduces infarction", "d2": "photosynthesis in leaves"}
        eval_set = bbe.EvalSet("s", {"q1": "does aspirin help?"}, {"q1": {"d1": 2}})
        bbe.write_beir_dir(tmp_path, corpus, eval_set)
        ds = beir_data.load_beir_dataset(tmp_path, name="t")
        assert ds.corpus == corpus  # empty title adds no prefix
        assert ds.queries == {"q1": "does aspirin help?"}
        assert ds.qrels == {"q1": {"d1": 2}}

    def test_qrel_stats(self) -> None:
        eval_set = bbe.EvalSet("s", {"q1": "a", "q2": "b"}, {"q1": {"d": 1}, "q2": {"d": 1, "e": 2}})
        assert bbe.qrel_stats(eval_set) == {"queries": 2, "judgements": 3, "mean_relevant_per_query": 1.5}
