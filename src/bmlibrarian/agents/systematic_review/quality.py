"""
Quality Assessment Orchestrator for SystematicReviewAgent

This module coordinates quality assessment tools to evaluate papers
that have passed relevance scoring. It orchestrates:
- Study design and quality assessment (StudyAssessmentAgent)
- Evidential weight assessment (PaperWeightAssessmentAgent)
- PICO component extraction (PICOAgent) for applicable studies
- PRISMA 2020 compliance (PRISMA2020Agent) for systematic reviews

The QualityAssessor applies conditional logic to run only relevant
assessments based on study type.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, TYPE_CHECKING

from .data_models import (
    ScoredPaper,
    AssessedPaper,
    StudyTypeFilter,
)
from .config import (
    SystematicReviewConfig,
    get_systematic_review_config,
    DEFAULT_BATCH_SIZE,
)
from .cache_manager import ResultsCacheManager

if TYPE_CHECKING:
    from ..study_assessment_agent import StudyAssessmentAgent
    from ..paper_weight.agent import PaperWeightAssessmentAgent
    from ..pico_agent import PICOAgent
    from ..prisma2020_agent import PRISMA2020Agent
    from ..orchestrator import AgentOrchestrator

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# NOTE: Study type determination is now delegated to LLM-based suitability checks
# in PICOAgent.check_suitability() and PRISMA2020Agent.check_suitability().
# This follows BMLibrarian's AI-first approach and avoids unreliable keyword matching.


# =============================================================================
# Data Types
# =============================================================================

@dataclass
class QualityAssessmentResult:
    """
    Result of quality assessment for a batch of papers.

    Attributes:
        assessed_papers: Papers with quality assessments
        failed_papers: Papers that failed assessment
        total_processed: Total papers attempted
        execution_time_seconds: Total time taken
        assessment_statistics: Breakdown by assessment type
    """

    assessed_papers: List[AssessedPaper] = field(default_factory=list)
    failed_papers: List[Tuple[ScoredPaper, str]] = field(default_factory=list)
    total_processed: int = 0
    execution_time_seconds: float = 0.0
    assessment_statistics: Dict[str, Any] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        """Percentage of papers successfully assessed."""
        if self.total_processed == 0:
            return 0.0
        return len(self.assessed_papers) / self.total_processed

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "assessed_count": len(self.assessed_papers),
            "failed_count": len(self.failed_papers),
            "total_processed": self.total_processed,
            "success_rate_percent": round(self.success_rate * 100, 2),
            "execution_time_seconds": round(self.execution_time_seconds, 2),
            "assessment_statistics": self.assessment_statistics,
        }


# =============================================================================
# QualityAssessor Class
# =============================================================================

class QualityAssessor:
    """
    Orchestrates quality assessment tools for systematic reviews.

    This class coordinates multiple specialized agents to perform
    comprehensive quality assessment of papers. It applies conditional
    logic to run only relevant assessments based on study type.

    Attributes:
        config: Full systematic review configuration
        callback: Optional progress callback
        orchestrator: Optional orchestrator for queue-based processing

    Example:
        >>> assessor = QualityAssessor()
        >>> result = assessor.assess_batch(scored_papers)
        >>> print(f"Assessed {len(result.assessed_papers)} papers")
    """

    def __init__(
        self,
        config: Optional[SystematicReviewConfig] = None,
        callback: Optional[Callable[[str, str], None]] = None,
        orchestrator: Optional["AgentOrchestrator"] = None,
    ) -> None:
        """
        Initialize the QualityAssessor.

        Args:
            config: Optional configuration
            callback: Optional progress callback
            orchestrator: Optional orchestrator for queue-based processing
        """
        self.callback = callback
        self.orchestrator = orchestrator

        # Load config
        self._config = config or get_systematic_review_config()

        # Initialize cache manager (lazy-loaded if cache is enabled)
        self._cache_manager: Optional[ResultsCacheManager] = None
        if self._config.use_results_cache:
            try:
                self._cache_manager = ResultsCacheManager()
                logger.info("Results cache manager initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize cache manager: {e}. Proceeding without cache.")
                self._cache_manager = None

        # Lazy-loaded agents
        self._study_agent: Optional["StudyAssessmentAgent"] = None
        self._weight_agent: Optional["PaperWeightAssessmentAgent"] = None
        self._pico_agent: Optional["PICOAgent"] = None
        self._prisma_agent: Optional["PRISMA2020Agent"] = None

        # Track version IDs for caching
        self._version_ids: Dict[str, int] = {}

        logger.info("QualityAssessor initialized")

    def _call_callback(self, event: str, data: str) -> None:
        """Call progress callback if registered."""
        if self.callback:
            try:
                self.callback(event, data)
            except Exception as e:
                logger.warning(f"Callback error: {e}")

    # =========================================================================
    # Cache Management
    # =========================================================================

    def _get_version_id(self, assessment_type: str, agent_name: str) -> Optional[int]:
        """
        Get or register version ID for an assessment type.

        Args:
            assessment_type: Type of assessment ('study_assessment', 'pico', 'prisma', 'paper_weight')
            agent_name: Name of the agent (for getting config)

        Returns:
            Version ID for caching, or None if cache is disabled
        """
        if not self._cache_manager or self._config.force_recompute:
            return None

        # Check if already cached
        cache_key = f"{assessment_type}:{agent_name}"
        if cache_key in self._version_ids:
            return self._version_ids[cache_key]

        # Get agent configuration
        from ...config import get_model, get_agent_config

        try:
            model = get_model(agent_name)
            agent_config = get_agent_config(agent_name)

            # Build parameters dict for versioning
            parameters = {
                "temperature": agent_config.get("temperature", 0.1),
                "top_p": agent_config.get("top_p", 0.9),
            }

            # Register version
            version_id = self._cache_manager.register_version(
                assessment_type=assessment_type,
                model_name=model,
                agent_version="1.0.0",  # TODO: Get from agent class
                parameters=parameters
            )

            # Cache it
            self._version_ids[cache_key] = version_id
            return version_id

        except Exception as e:
            logger.warning(f"Failed to register version for {assessment_type}: {e}")
            return None

    # =========================================================================
    # Agent Initialization (Lazy Loading)
    # =========================================================================

    def _get_study_agent(self) -> "StudyAssessmentAgent":
        """
        Get or create StudyAssessmentAgent.

        Returns:
            StudyAssessmentAgent instance
        """
        if self._study_agent is None:
            from ..study_assessment_agent import StudyAssessmentAgent
            from ...config import get_model, get_ollama_host, get_agent_config

            model = get_model("study_assessment")
            host = get_ollama_host()
            agent_config = get_agent_config("study_assessment")

            self._study_agent = StudyAssessmentAgent(
                model=model,
                host=host,
                temperature=agent_config.get("temperature", 0.1),
                top_p=agent_config.get("top_p", 0.9),
                callback=self.callback,
                orchestrator=self.orchestrator,
                show_model_info=False,
            )

        return self._study_agent

    def _get_weight_agent(self) -> "PaperWeightAssessmentAgent":
        """
        Get or create PaperWeightAssessmentAgent.

        Returns:
            PaperWeightAssessmentAgent instance
        """
        if self._weight_agent is None:
            from ..paper_weight.agent import PaperWeightAssessmentAgent
            from ...config import get_model, get_ollama_host, get_agent_config

            model = get_model("paper_weight")
            host = get_ollama_host()
            agent_config = get_agent_config("paper_weight")

            self._weight_agent = PaperWeightAssessmentAgent(
                model=model,
                host=host,
                temperature=agent_config.get("temperature", 0.3),
                top_p=agent_config.get("top_p", 0.9),
                callback=self.callback,
                orchestrator=self.orchestrator,
                show_model_info=False,
            )

        return self._weight_agent

    def _get_pico_agent(self) -> "PICOAgent":
        """
        Get or create PICOAgent.

        Returns:
            PICOAgent instance
        """
        if self._pico_agent is None:
            from ..pico_agent import PICOAgent
            from ...config import get_model, get_ollama_host, get_agent_config

            model = get_model("pico")
            host = get_ollama_host()
            agent_config = get_agent_config("pico")

            self._pico_agent = PICOAgent(
                model=model,
                host=host,
                temperature=agent_config.get("temperature", 0.1),
                top_p=agent_config.get("top_p", 0.9),
                callback=self.callback,
                orchestrator=self.orchestrator,
                show_model_info=False,
            )

        return self._pico_agent

    def _get_prisma_agent(self) -> "PRISMA2020Agent":
        """
        Get or create PRISMA2020Agent.

        Returns:
            PRISMA2020Agent instance
        """
        if self._prisma_agent is None:
            from ..prisma2020_agent import PRISMA2020Agent
            from ...config import get_model, get_ollama_host, get_agent_config

            model = get_model("prisma2020")
            host = get_ollama_host()
            agent_config = get_agent_config("prisma2020")

            self._prisma_agent = PRISMA2020Agent(
                model=model,
                host=host,
                temperature=agent_config.get("temperature", 0.1),
                top_p=agent_config.get("top_p", 0.9),
                callback=self.callback,
                orchestrator=self.orchestrator,
                show_model_info=False,
            )

        return self._prisma_agent

    # =========================================================================
    # Main Assessment Methods
    # =========================================================================

    def assess_batch(
        self,
        papers: List[ScoredPaper],
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> QualityAssessmentResult:
        """
        Run quality assessments on all papers.

        Conditionally runs PICO/PRISMA based on study type.

        Args:
            papers: List of scored papers to assess
            progress_callback: Optional callback(current, total) for progress

        Returns:
            QualityAssessmentResult with all assessed papers
        """
        self._call_callback(
            "quality_assessment_started",
            f"Assessing {len(papers)} papers"
        )

        start_time = time.time()
        assessed_papers: List[AssessedPaper] = []
        failed_papers: List[Tuple[ScoredPaper, str]] = []

        # Track assessment statistics
        stats = {
            "study_assessments": 0,
            "weight_assessments": 0,
            "pico_assessments": 0,
            "prisma_assessments": 0,
        }

        for i, paper in enumerate(papers):
            try:
                assessed_paper = self._assess_single(paper)
                assessed_papers.append(assessed_paper)

                # Update statistics
                stats["study_assessments"] += 1
                stats["weight_assessments"] += 1
                if assessed_paper.pico_components is not None:
                    stats["pico_assessments"] += 1
                if assessed_paper.prisma_assessment is not None:
                    stats["prisma_assessments"] += 1

            except Exception as e:
                logger.error(f"Failed to assess paper {paper.paper.document_id}: {e}")
                failed_papers.append((paper, str(e)))

            if progress_callback:
                progress_callback(i + 1, len(papers))

        execution_time = time.time() - start_time

        self._call_callback(
            "quality_assessment_completed",
            f"Assessed {len(assessed_papers)}, failed {len(failed_papers)}"
        )

        logger.info(
            f"Quality assessment complete: {len(assessed_papers)} assessed, "
            f"{len(failed_papers)} failed ({execution_time:.2f}s)"
        )

        return QualityAssessmentResult(
            assessed_papers=assessed_papers,
            failed_papers=failed_papers,
            total_processed=len(papers),
            execution_time_seconds=execution_time,
            assessment_statistics=stats,
        )

    def _assess_single(
        self,
        paper: ScoredPaper,
    ) -> AssessedPaper:
        """
        Assess a single paper.

        Runs all applicable quality assessments based on LLM-determined study suitability
        and configuration flags. Uses cached results when available unless force_recompute is set.

        Args:
            paper: Scored paper to assess

        Returns:
            AssessedPaper with all quality assessments
        """
        self._call_callback(
            "assessing_paper",
            f"{paper.paper.title[:50]}..."
        )

        # Prepare document dict for agents
        document = self._paper_to_document(paper.paper)

        # 1. Study Assessment (conditional based on config flag)
        study_assessment = None
        if self._config.run_study_assessment:
            study_assessment = self._run_study_assessment(document)
        else:
            logger.debug(f"Skipping study assessment for document {document['id']} (disabled in config)")

        # 2. Paper Weight Assessment (conditional based on config flag)
        paper_weight = None
        if self._config.run_paper_weight:
            paper_weight = self._run_paper_weight_assessment(document)
        else:
            logger.debug(f"Skipping paper weight assessment for document {document['id']} (disabled in config)")

        # 3. PICO extraction (conditional - config flag + LLM-based suitability check)
        pico_components = None
        if self._config.run_pico_extraction:
            pico_suitability = self._check_pico_suitability(document)
            if pico_suitability and pico_suitability.get("is_suitable", False):
                logger.info(
                    f"Document {document['id']} suitable for PICO: "
                    f"{pico_suitability.get('rationale', 'N/A')}"
                )
                pico_components = self._run_pico_extraction(document)
            elif pico_suitability:
                logger.info(
                    f"Document {document['id']} NOT suitable for PICO: "
                    f"{pico_suitability.get('rationale', 'N/A')}"
                )
        else:
            logger.debug(f"Skipping PICO extraction for document {document['id']} (disabled in config)")

        # 4. PRISMA assessment (conditional - config flag + LLM-based suitability check)
        prisma_assessment = None
        if self._config.run_prisma_assessment:
            prisma_suitability = self._check_prisma_suitability(document)
            if prisma_suitability and prisma_suitability.get("is_suitable", False):
                logger.info(
                    f"Document {document['id']} suitable for PRISMA: "
                    f"{prisma_suitability.get('rationale', 'N/A')}"
                )
                prisma_assessment = self._run_prisma_assessment(document)
            elif prisma_suitability:
                logger.info(
                    f"Document {document['id']} NOT suitable for PRISMA: "
                    f"{prisma_suitability.get('rationale', 'N/A')}"
                )
        else:
            logger.debug(f"Skipping PRISMA assessment for document {document['id']} (disabled in config)")

        return AssessedPaper(
            scored_paper=paper,
            study_assessment=study_assessment,
            paper_weight=paper_weight,
            pico_components=pico_components,
            prisma_assessment=prisma_assessment,
        )

    # =========================================================================
    # Individual Assessment Runners
    # =========================================================================

    def _run_study_assessment(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run study quality assessment with caching support.

        Args:
            document: Document dictionary

        Returns:
            Study assessment dictionary

        Note:
            No text truncation is performed as per Golden Rule #14.
            Truncation causes information loss which is unacceptable in medical domain.
        """
        document_id = document["id"]

        # Check cache first (unless force_recompute is set)
        version_id = self._get_version_id("study_assessment", "study_assessment")
        if version_id and self._cache_manager:
            cached_result = self._cache_manager.get_study_assessment(document_id, version_id)
            if cached_result:
                logger.info(f"Using cached study assessment for document {document_id}")
                return cached_result

        # Not in cache or force recompute - run assessment
        try:
            start_time = time.time()
            agent = self._get_study_agent()

            # Use full text without truncation (Golden Rule #14)
            text = document.get("abstract", "")

            result = agent.assess_study(
                abstract=text,
                title=document.get("title", ""),
                document_id=str(document_id),
                pmid=document.get("pmid"),
                doi=document.get("doi"),
            )

            result_dict = result.to_dict()
            execution_time_ms = int((time.time() - start_time) * 1000)

            # Store in cache
            if version_id and self._cache_manager:
                self._cache_manager.store_study_assessment(
                    document_id, version_id, result_dict, execution_time_ms
                )

            return result_dict

        except Exception as e:
            logger.error(f"Study assessment failed for {document_id}: {e}")
            # Return minimal assessment on error
            return {
                "study_type": "unknown",
                "study_design": "unknown",
                "quality_score": 5.0,
                "strengths": [],
                "limitations": [f"Assessment failed: {e}"],
                "overall_confidence": 0.0,
                "confidence_explanation": "Assessment failed",
                "evidence_level": "unknown",
                "document_id": str(document_id),
                "document_title": document.get("title", ""),
            }

    def _run_paper_weight_assessment(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run paper weight assessment.

        Args:
            document: Document dictionary

        Returns:
            Paper weight assessment dictionary
        """
        try:
            agent = self._get_weight_agent()

            result = agent.assess_paper(
                document_id=document["id"],
                use_cache=True,
            )

            return result.to_dict()

        except Exception as e:
            logger.error(f"Paper weight assessment failed for {document['id']}: {e}")
            # Return minimal assessment on error
            return {
                "document_id": document["id"],
                "composite_score": 5.0,
                "dimensions": [],
                "error": str(e),
            }

    def _run_pico_extraction(self, document: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Run PICO component extraction with caching support.

        Args:
            document: Document dictionary

        Returns:
            PICO extraction dictionary, or None on error

        Note:
            No text truncation is performed as per Golden Rule #14.
            Truncation causes information loss which is unacceptable in medical domain.
            The PICOAgent will handle large texts appropriately.
        """
        document_id = document["id"]

        # Check cache first (unless force_recompute is set)
        version_id = self._get_version_id("pico", "pico")
        if version_id and self._cache_manager:
            cached_result = self._cache_manager.get_pico_extraction(document_id, version_id)
            if cached_result:
                logger.info(f"Using cached PICO extraction for document {document_id}")
                return cached_result

        # Not in cache or force recompute - run extraction
        try:
            start_time = time.time()
            agent = self._get_pico_agent()

            # Use the extract_pico_from_document method which expects a full document dict
            result = agent.extract_pico_from_document(
                document=document,
                min_confidence=0.5
            )

            if result is None:
                return None

            result_dict = result.to_dict()
            execution_time_ms = int((time.time() - start_time) * 1000)

            # Store in cache
            if version_id and self._cache_manager:
                self._cache_manager.store_pico_extraction(
                    document_id, version_id, result_dict, execution_time_ms
                )

            return result_dict

        except Exception as e:
            logger.error(f"PICO extraction failed for {document_id}: {e}")
            return None

    def _run_prisma_assessment(self, document: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Run PRISMA 2020 compliance assessment.

        Args:
            document: Document dictionary

        Returns:
            PRISMA assessment dictionary, or None on error
        """
        try:
            agent = self._get_prisma_agent()

            result = agent.assess_document(
                document_id=document["id"],
            )

            return result.to_dict()

        except Exception as e:
            logger.error(f"PRISMA assessment failed for {document['id']}: {e}")
            return None

    # =========================================================================
    # Conditional Logic (LLM-Based Suitability Checks)
    # =========================================================================

    def _check_pico_suitability(self, document: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Check if PICO extraction is applicable using LLM-based assessment.

        Uses PICOAgent's check_suitability method to determine if the document
        is an intervention study suitable for PICO component extraction.

        Args:
            document: Document dictionary

        Returns:
            Suitability assessment dictionary, or None on error
        """
        try:
            agent = self._get_pico_agent()
            suitability = agent.check_suitability(document)

            if suitability is None:
                logger.warning(f"PICO suitability check returned None for document {document['id']}")
                return None

            return suitability.to_dict()

        except Exception as e:
            logger.error(f"PICO suitability check failed for {document['id']}: {e}")
            return None

    def _check_prisma_suitability(self, document: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Check if PRISMA assessment is applicable using LLM-based assessment.

        Uses PRISMA2020Agent's check_suitability method to determine if the document
        is a systematic review or meta-analysis suitable for PRISMA assessment.

        Args:
            document: Document dictionary

        Returns:
            Suitability assessment dictionary, or None on error
        """
        try:
            agent = self._get_prisma_agent()
            suitability = agent.check_suitability(document)

            if suitability is None:
                logger.warning(f"PRISMA suitability check returned None for document {document['id']}")
                return None

            return suitability.to_dict()

        except Exception as e:
            logger.error(f"PRISMA suitability check failed for {document['id']}: {e}")
            return None

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _paper_to_document(self, paper) -> Dict[str, Any]:
        """
        Convert PaperData to document dict for agents.

        Args:
            paper: PaperData instance

        Returns:
            Document dictionary compatible with quality agents
        """
        return {
            "id": paper.document_id,
            "title": paper.title,
            "abstract": paper.abstract or "",
            "authors": paper.authors,
            "publication": paper.journal,
            "publication_date": str(paper.year),
            "doi": paper.doi,
            "pmid": paper.pmid,
            "pmc_id": paper.pmc_id,
            "full_text": paper.full_text,
        }

    # =========================================================================
    # Statistics
    # =========================================================================

    def get_assessment_statistics(
        self,
        result: QualityAssessmentResult,
    ) -> Dict[str, Any]:
        """
        Get detailed statistics about assessment results.

        Args:
            result: QualityAssessmentResult to analyze

        Returns:
            Dictionary with detailed statistics
        """
        if not result.assessed_papers:
            return {
                "total": result.total_processed,
                "assessed": 0,
                "failed": len(result.failed_papers),
            }

        # Study type distribution
        study_types: Dict[str, int] = {}
        for paper in result.assessed_papers:
            study_type = paper.study_assessment.get("study_type", "unknown")
            study_types[study_type] = study_types.get(study_type, 0) + 1

        # Quality score distribution
        quality_scores = [
            p.study_assessment.get("quality_score", 0.0)
            for p in result.assessed_papers
        ]

        avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0.0

        return {
            "total_papers": result.total_processed,
            "successfully_assessed": len(result.assessed_papers),
            "failed": len(result.failed_papers),
            "success_rate_percent": round(result.success_rate * 100, 2),
            "assessment_types": result.assessment_statistics,
            "study_type_distribution": study_types,
            "average_quality_score": round(avg_quality, 2),
            "execution_time_seconds": round(result.execution_time_seconds, 2),
            "papers_per_second": round(
                len(result.assessed_papers) / result.execution_time_seconds, 2
            ) if result.execution_time_seconds > 0 else 0,
        }
