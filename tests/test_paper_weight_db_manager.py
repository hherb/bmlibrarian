"""
The paper-weight agent uses the database it was given (#366).

Inside a systematic review the agent's searches, fetches and results cache
use the review's ``db_manager`` (#285), but the paper-weight sub-agent read
documents, chunks and its ``paper_weights`` cache through the global
``get_db_manager()`` (the default ``.env``), so a review built for database B
assessed and stored papers in database A. These tests make the global manager
fail while the helpers run against an explicit one, and check that the agent
hands its own manager to every helper it calls.
"""

from contextlib import ExitStack
from pathlib import Path
from datetime import datetime
from typing import Any, Iterator
from unittest.mock import MagicMock, patch

import pytest

from bmlibrarian.agents.paper_weight import db as pw_db
from bmlibrarian.agents.paper_weight import llm_extractors, validators
from bmlibrarian.agents.paper_weight.agent import PaperWeightAssessmentAgent
from bmlibrarian.agents.paper_weight.models import DimensionScore, PaperWeightResult
from bmlibrarian.agents.systematic_review.config import SystematicReviewConfig
from bmlibrarian.agents.systematic_review.quality import QualityAssessor

AGENT_MODULE = "bmlibrarian.agents.paper_weight.agent"
# Where get_db_manager is looked up: its home module (read by the lazy
# ``from ...database import``) and the modules that bind it at import time.
GLOBAL_MANAGER_NAMES = (
    "bmlibrarian.database.get_db_manager",
    "bmlibrarian.agents.paper_weight.db.get_db_manager",
    "bmlibrarian.embeddings.chunk_embedder.get_db_manager",
    "bmlibrarian.importers.pdf_ingestor.get_db_manager",
)


@pytest.fixture
def no_global_manager() -> Iterator[None]:
    """Fail any use of the global manager."""
    with ExitStack() as stack:
        for name in GLOBAL_MANAGER_NAMES:
            stack.enter_context(
                patch(name, side_effect=AssertionError("global db_manager used"))
            )
        yield


def make_manager(fetchone: Any = None, fetchall: Any = ()) -> MagicMock:
    """A DatabaseManager whose cursors return the given rows."""
    manager = MagicMock()
    manager.get_cached_source_ids.return_value = {"pubmed": 7}
    cursor = manager.get_connection.return_value.__enter__.return_value \
        .cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = fetchone
    cursor.fetchall.return_value = list(fetchall)
    return manager


class TestHelpersUseGivenManager:
    """The module-level helpers query the manager they are handed."""

    def test_get_cached_assessment(self, no_global_manager: None) -> None:
        """A cache miss is looked up in the given database."""
        manager = make_manager(fetchone=None)
        assert pw_db.get_cached_assessment(1, "1.0.0", db_manager=manager) is None
        manager.get_connection.assert_called_once()

    def test_get_document(self, no_global_manager: None) -> None:
        """The document comes from the given database."""
        manager = make_manager(fetchone=(1, "Title", "Abstract", None, 2020, None, None))
        assert pw_db.get_document(1, db_manager=manager)["title"] == "Title"

    def test_check_replication_status(self, no_global_manager: None) -> None:
        """Replications are read from the given database."""
        manager = make_manager(fetchall=[])
        assert pw_db.check_replication_status(1, db_manager=manager).score == 0.0
        manager.get_connection.assert_called_once()

    def test_store_assessment(self, no_global_manager: None) -> None:
        """The assessment is written to the given database."""
        manager = make_manager(fetchone=(5,))
        scores = {
            name: DimensionScore(name, 5.0)
            for name in ("study_design", "sample_size", "methodological_quality",
                         "risk_of_bias", "replication_status")
        }
        result = PaperWeightResult(
            document_id=1, assessor_version="1.0.0", assessed_at=datetime.now(),
            study_design=scores["study_design"], sample_size=scores["sample_size"],
            methodological_quality=scores["methodological_quality"],
            risk_of_bias=scores["risk_of_bias"],
            replication_status=scores["replication_status"],
            final_weight=5.0, dimension_weights={},
        )
        pw_db.store_assessment(result, db_manager=manager)
        manager.get_connection.assert_called_once()

    def test_chunk_helpers(self, no_global_manager: None) -> None:
        """Chunk search and listing read the given database's chunks."""
        manager = make_manager(fetchall=[(0, "chunk", 0.9)])
        assert validators.search_chunks_by_query(1, "study design", db_manager=manager)
        assert validators.get_all_document_chunks(1, db_manager=manager)

    def test_ensure_document_embeddings(self, no_global_manager: None) -> None:
        """Existing chunks are counted in the given database."""
        manager = make_manager(fetchone=(3,))
        assert llm_extractors.ensure_document_embeddings(1, db_manager=manager)

    def test_ensure_document_embeddings_creates_chunks(self, no_global_manager: None) -> None:
        """Missing chunks are embedded into the given database."""
        manager = make_manager(fetchone=(0,))
        with patch("bmlibrarian.embeddings.chunk_embedder.ChunkEmbedder") as embedder_cls:
            embedder_cls.return_value.chunk_and_embed.return_value = 2
            assert llm_extractors.ensure_document_embeddings(
                1, document={"full_text": "text"}, db_manager=manager
            )
        assert embedder_cls.call_args.kwargs["db_manager"] is manager

    @pytest.mark.parametrize("module, func, extra", [
        (llm_extractors, "extract_study_type_llm", {}),
        (llm_extractors, "extract_sample_size_llm", {}),
        (validators, "validate_study_type_extraction",
         {"dimension_score": DimensionScore("study_design", 5.0)}),
        (validators, "validate_sample_size_extraction",
         {"dimension_score": DimensionScore("sample_size", 5.0)}),
    ])
    def test_extractors_and_validators_pass_manager_on(
        self, no_global_manager: None, module: Any, func: str, extra: dict
    ) -> None:
        """The LLM extractors and validators read chunks from the given database."""
        manager = MagicMock()
        with patch.object(module, "search_chunks_by_query", return_value=[]) as search, \
             patch.object(module, "get_all_document_chunks", return_value=[]) as listing:
            try:
                getattr(module, func)(
                    document_id=1, llm_client=MagicMock(), model="m",
                    db_manager=manager, **extra,
                )
            except ValueError:
                pass  # no chunks and no document text: extractors refuse to score
        assert search.call_args.kwargs["db_manager"] is manager
        assert listing.call_args.kwargs["db_manager"] is manager

    def test_chunk_embedder_and_pdf_ingestor(self, no_global_manager: None) -> None:
        """Embedder and ingestor keep the manager they are given."""
        from bmlibrarian.embeddings.chunk_embedder import ChunkEmbedder
        from bmlibrarian.importers.pdf_ingestor import PDFIngestor

        manager = make_manager(fetchone=(4,))  # embedding_models row
        with patch("bmlibrarian.embeddings.chunk_embedder.LLMClient", create=True):
            embedder = ChunkEmbedder(backend="ollama", db_manager=manager)
            assert embedder.db_manager is manager
            assert embedder.model_id == 4  # model id looked up in the given database
            ingestor = PDFIngestor(db_manager=manager)
            assert ingestor.db_manager is manager
            assert ingestor.embedder.db_manager is manager

    def test_chunk_insert_failure_keeps_other_chunks(self) -> None:
        """Each chunk is inserted in its own savepoint, so one failure loses only that chunk."""
        from bmlibrarian.embeddings import chunk_embedder

        manager = make_manager(fetchone=(4,))
        with patch.object(chunk_embedder, "LLMClient", create=True):
            embedder = chunk_embedder.ChunkEmbedder(backend="ollama", db_manager=manager)
        conn = manager.get_connection.return_value.__enter__.return_value
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.execute.side_effect = [RuntimeError("insert failed"), None, None]
        positions = [MagicMock(chunk_no=n, text=f"chunk {n}") for n in range(3)]
        with patch.object(embedder, "get_document_full_text", return_value="text"), \
             patch.object(embedder, "delete_existing_chunks"), \
             patch.object(embedder, "create_embeddings_batch", return_value=[[0.1]] * 3), \
             patch.object(chunk_embedder, "adaptive_chunker_with_positions",
                          return_value=positions):
            assert embedder.chunk_and_embed(1) == 2
        assert conn.transaction.call_count == 3


class TestAgentPassesItsManager:
    """Every database step of an assessment gets the agent's manager."""

    HELPERS = (
        "get_cached_assessment", "get_document", "ensure_document_embeddings",
        "extract_study_type_llm", "extract_sample_size_llm",
        "check_replication_status", "store_assessment",
    )

    def test_assess_paper(self) -> None:
        """A fresh LLM-first assessment reads and stores via the agent's manager."""
        manager = MagicMock()
        agent = PaperWeightAssessmentAgent(show_model_info=False, db_manager=manager)
        with ExitStack() as stack:
            mocks = {
                name: stack.enter_context(patch(f"{AGENT_MODULE}.{name}"))
                for name in self.HELPERS
            }
            mocks["get_cached_assessment"].return_value = None
            mocks["get_document"].return_value = {"id": 1, "full_text": "text"}
            mocks["ensure_document_embeddings"].return_value = True
            for name, dim in (("extract_study_type_llm", "study_design"),
                              ("extract_sample_size_llm", "sample_size"),
                              ("check_replication_status", "replication_status")):
                mocks[name].return_value = DimensionScore(dim, 5.0)
            stack.enter_context(patch.object(
                agent, "_assess_methodological_quality",
                return_value=DimensionScore("methodological_quality", 5.0)))
            stack.enter_context(patch.object(
                agent, "_assess_risk_of_bias",
                return_value=DimensionScore("risk_of_bias", 5.0)))

            agent.assess_paper(1)

        for name, mock in mocks.items():
            assert mock.call_args.kwargs.get("db_manager") is manager, name

    def test_validate_extractions(self) -> None:
        """Legacy-mode validation reads chunks via the agent's manager."""
        manager = MagicMock()
        agent = PaperWeightAssessmentAgent(show_model_info=False, db_manager=manager)
        names = ("get_all_document_chunks", "validate_study_type_extraction",
                 "validate_sample_size_extraction")
        with ExitStack() as stack:
            mocks = {n: stack.enter_context(patch(f"{AGENT_MODULE}.{n}")) for n in names}
            stack.enter_context(patch(f"{AGENT_MODULE}.add_validation_to_dimension_score"))
            mocks["get_all_document_chunks"].return_value = [{"chunk_text": "t"}]
            for n in names[1:]:
                mocks[n].return_value.has_conflict = False
            agent._validate_extractions(
                1, DimensionScore("study_design", 5.0), DimensionScore("sample_size", 5.0)
            )
        for name, mock in mocks.items():
            assert mock.call_args.kwargs.get("db_manager") is manager, name

    def test_assess_full_paper(self, no_global_manager: None, tmp_path: Path) -> None:
        """PDF ingestion, document fetches and the chunk count use the agent's manager."""
        manager = make_manager(fetchall=[(0, 0, 5, "chunk")])
        agent = PaperWeightAssessmentAgent(show_model_info=False, db_manager=manager)
        with patch(f"{AGENT_MODULE}.get_document",
                   side_effect=[{"id": 1}, {"id": 1, "full_text": "text"}]) as get_doc, \
             patch("bmlibrarian.importers.pdf_ingestor.PDFIngestor") as ingestor_cls, \
             patch.object(agent, "assess_paper") as assess:
            ingestor_cls.return_value.ingest_pdf_immediate.return_value = MagicMock(
                success=True, full_text_stored=True
            )
            agent.assess_full_paper(1, pdf_path=tmp_path / "paper.pdf")
        assert ingestor_cls.call_args.kwargs["db_manager"] is manager
        assert all(c.kwargs["db_manager"] is manager for c in get_doc.call_args_list)
        manager.get_connection.assert_called_once()  # _search_document_chunks
        assess.assert_called_once()

    def test_assess_full_paper_without_stored_text_raises(self, tmp_path: Path) -> None:
        """An ingestion that stored no full text fails instead of scoring the abstract."""
        agent = PaperWeightAssessmentAgent(show_model_info=False, db_manager=MagicMock())
        with patch(f"{AGENT_MODULE}.get_document", return_value={"id": 1}), \
             patch("bmlibrarian.importers.pdf_ingestor.PDFIngestor") as ingestor_cls, \
             patch.object(agent, "assess_paper") as assess, \
             pytest.raises(RuntimeError, match="stored no full text: read-only"):
            ingestor_cls.return_value.ingest_pdf_immediate.return_value = MagicMock(
                success=True, full_text_stored=False, warnings=["read-only"]
            )
            agent.assess_full_paper(1, pdf_path=tmp_path / "paper.pdf")
        assess.assert_not_called()

    def test_quality_assessor_hands_on_its_manager(self) -> None:
        """The systematic review's paper-weight agent uses the review's database."""
        manager = MagicMock()
        assessor = QualityAssessor(
            config=SystematicReviewConfig(use_results_cache=False), db_manager=manager
        )
        assert assessor._get_weight_agent().db_manager is manager
