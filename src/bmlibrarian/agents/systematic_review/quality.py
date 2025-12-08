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

    # Class-level cache for agent versions to avoid repeated dynamic imports
    _agent_version_cache: Dict[str, str] = {}

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

            # Get agent version from the agent class
            agent_version = self._get_agent_version(assessment_type)

            # Register version
            version_id = self._cache_manager.register_version(
                assessment_type=assessment_type,
                model_name=model,
                agent_version=agent_version,
                parameters=parameters
            )

            # Cache it
            self._version_ids[cache_key] = version_id
            return version_id

        except Exception as e:
            logger.warning(f"Failed to register version for {assessment_type}: {e}")
            return None

    def _get_agent_version(self, assessment_type: str) -> str:
        """
        Get the version string from the corresponding agent class.

        Uses class-level caching to avoid repeated dynamic imports.
        The cache is shared across all instances for performance.

        Args:
            assessment_type: Type of assessment

        Returns:
            Version string from agent's VERSION class attribute, or "1.0.0" as fallback
        """
        # Check class-level cache first
        if assessment_type in QualityAssessor._agent_version_cache:
            return QualityAssessor._agent_version_cache[assessment_type]

        version_map = {
            "study_assessment": ("study_assessment_agent", "StudyAssessmentAgent"),
            "pico": ("pico_agent", "PICOAgent"),
            "prisma": ("prisma2020_agent", "PRISMA2020Agent"),
            "paper_weight": ("paper_weight.agent", "PaperWeightAssessmentAgent"),
        }

        if assessment_type not in version_map:
            return "1.0.0"

        version = "1.0.0"  # Default fallback

        try:
            # Dynamically import the agent class to get its VERSION
            if assessment_type == "paper_weight":
                from ..paper_weight.agent import PaperWeightAssessmentAgent
                version = getattr(PaperWeightAssessmentAgent, 'VERSION', '1.0.0')
            elif assessment_type == "study_assessment":
                from ..study_assessment_agent import StudyAssessmentAgent
                version = getattr(StudyAssessmentAgent, 'VERSION', '1.0.0')
            elif assessment_type == "pico":
                from ..pico_agent import PICOAgent
                version = getattr(PICOAgent, 'VERSION', '1.0.0')
            elif assessment_type == "prisma":
                from ..prisma2020_agent import PRISMA2020Agent
                version = getattr(PRISMA2020Agent, 'VERSION', '1.0.0')
        except ImportError as e:
            logger.warning(f"Could not import agent for {assessment_type}: {e}")

        # Cache the result at class level
        QualityAssessor._agent_version_cache[assessment_type] = version
        return version

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

            # Note: PaperWeightAssessmentAgent loads temperature/top_p from its own config
            # and does not accept them as constructor parameters
            self._weight_agent = PaperWeightAssessmentAgent(
                model=model,
                host=host,
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
        save_callback: Optional[Callable[["AssessedPaper"], None]] = None,
    ) -> QualityAssessmentResult:
        """
        Run quality assessments on all papers.

        Conditionally runs PICO/PRISMA based on study type.

        Args:
            papers: List of scored papers to assess
            progress_callback: Optional callback(current, total) for progress
            save_callback: Optional callback to save each assessed paper immediately.
                          Called with each AssessedPaper right after evaluation.
                          This ensures assessments are persisted even if the
                          process is interrupted.

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

                # Save immediately after evaluation to persist progress
                if save_callback:
                    try:
                        save_callback(assessed_paper)
                    except Exception as save_error:
                        logger.error(
                            f"Failed to save assessed paper {paper.paper.document_id}: {save_error}",
                            exc_info=True
                        )
                        # Re-raise so caller knows save failed - data integrity is critical
                        raise

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

            # Emit progress via callback system for GUI updates
            # Format: "X/Y | <title>" - X/Y is parsed for progress bar
            title_truncated = paper.paper.title[:60]
            if len(paper.paper.title) > 60:
                title_truncated += "..."
            if assessed_papers:
                last_assessed = assessed_papers[-1]
                quality_score = last_assessed.study_assessment.get("quality_score", "N/A")
                self._call_callback(
                    "quality_progress",
                    f"{i + 1}/{len(papers)} | Quality {quality_score}/10 for {title_truncated}"
                )
            else:
                self._call_callback(
                    "quality_progress",
                    f"{i + 1}/{len(papers)} | Failed: {title_truncated}"
                )

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
            AssessedPaper with all quality assessments (includes processing_time_ms)
        """
        start_time = time.time()

        self._call_callback(
            "assessing_paper",
            f"{paper.paper.title[:50]}..."
        )

        # Prepare document dict for agents
        document = self._paper_to_document(paper.paper)

        # 1. Study Assessment (conditional based on config flag)
        if self._config.run_study_assessment:
            study_assessment = self._run_study_assessment(document)
        else:
            logger.debug(f"Skipping study assessment for document {document['id']} (disabled in config)")
            # Return minimal assessment when disabled (AssessedPaper expects Dict, not None)
            study_assessment = {
                "study_type": "not_assessed",
                "study_design": "not_assessed",
                "quality_score": 5.0,
                "strengths": [],
                "limitations": ["Assessment disabled in configuration"],
                "overall_confidence": 0.0,
                "confidence_explanation": "Assessment skipped (disabled in config)",
                "evidence_level": "not_assessed",
                "document_id": str(document["id"]),
                "document_title": document.get("title", ""),
            }

        # 2. Paper Weight Assessment (conditional based on config flag)
        if self._config.run_paper_weight:
            paper_weight = self._run_paper_weight_assessment(document)
        else:
            logger.debug(f"Skipping paper weight assessment for document {document['id']} (disabled in config)")
            # Return minimal assessment when disabled (AssessedPaper expects Dict, not None)
            paper_weight = {
                "document_id": document["id"],
                "composite_score": 5.0,
                "dimensions": [],
                "note": "Assessment disabled in configuration",
            }

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

        # Calculate processing time in milliseconds
        processing_time_ms = int((time.time() - start_time) * 1000)

        return AssessedPaper(
            scored_paper=paper,
            study_assessment=study_assessment,
            paper_weight=paper_weight,
            pico_components=pico_components,
            prisma_assessment=prisma_assessment,
            processing_time_ms=processing_time_ms,
        )

    # =========================================================================
    # Individual Assessment Runners
    #
    # Error Handling Design:
    # - Required assessments (study_assessment, paper_weight): Return minimal dict
    #   with 'error' field on failure. These are always expected in AssessedPaper.
    # - Optional assessments (pico, prisma): Return None on failure or when not
    #   applicable. Downstream code handles None gracefully.
    # - Suitability checks: Return None on failure to signal "unknown suitability",
    #   which results in skipping the optional assessment.
    # =========================================================================

    def _run_study_assessment(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run study quality assessment with caching support.

        Args:
            document: Document dictionary with at minimum 'id', 'title', and 'abstract'

        Returns:
            Study assessment dictionary with the following guaranteed fields:
            - study_type (str): Type of study design (e.g., 'RCT', 'cohort', 'unknown')
            - study_design (str): Detailed study design description
            - quality_score (float): Quality score from 0.0 to 10.0
            - strengths (List[str]): List of study strengths
            - limitations (List[str]): List of study limitations
            - overall_confidence (float): Confidence in assessment (0.0 to 1.0)
            - confidence_explanation (str): Explanation of confidence level
            - evidence_level (str): Evidence level classification
            - document_id (str): ID of the assessed document
            - document_title (str): Title of the assessed document

            On error, the dict will also contain:
            - error (str): Error message describing the failure

            The presence of the 'error' field indicates assessment failure.
            Downstream code should check for this field to detect errors.

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

            # assess_study expects a document dict with 'abstract' key
            result = agent.assess_study(document=document)

            if result is None:
                logger.warning(f"Study assessment returned None for document {document_id}")
                return None

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
            # Return minimal assessment on error (with 'error' field for detection)
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
                "error": str(e),
            }

    def _run_paper_weight_assessment(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run paper weight assessment with caching support.

        The paper weight agent has its own internal caching (via paper_weights.assessments),
        but we also integrate with ResultsCacheManager for:
        - Unified cache statistics
        - Consistent version tracking
        - Cross-assessment performance analysis

        Args:
            document: Document dictionary with at minimum 'id'

        Returns:
            Paper weight assessment dictionary with the following guaranteed fields:
            - document_id (int): ID of the assessed document
            - composite_score (float): Overall evidence weight score (0.0 to 10.0)
            - dimensions (List[Dict]): Individual dimension assessments

            On error, the dict will also contain:
            - error (str): Error message describing the failure

            The presence of the 'error' field indicates assessment failure.
            Downstream code should check for this field to detect errors.
        """
        document_id = document["id"]

        # Check ResultsCacheManager first (unless force_recompute is set)
        version_id = self._get_version_id("paper_weight", "paper_weight")
        if version_id and self._cache_manager:
            cached_result = self._cache_manager.get_paper_weight(document_id, version_id)
            if cached_result:
                logger.info(f"Using cached paper weight assessment for document {document_id}")
                return cached_result

        # Not in cache or force recompute - run assessment
        try:
            start_time = time.time()
            agent = self._get_weight_agent()

            # Use agent's internal caching for performance (force_reassess=False)
            result = agent.assess_paper(
                document_id=document_id,
                force_reassess=False,
            )

            if result is None:
                logger.warning(f"Paper weight assessment returned None for document {document_id}")
                return None

            result_dict = result.to_dict()
            execution_time_ms = int((time.time() - start_time) * 1000)

            # Store in ResultsCacheManager for unified tracking
            if version_id and self._cache_manager:
                # Get assessment_id from result if available
                assessment_id = result_dict.get('assessment_id')
                self._cache_manager.store_paper_weight(
                    document_id, version_id, result_dict,
                    paper_weight_assessment_id=assessment_id,
                    execution_time_ms=execution_time_ms
                )

            return result_dict

        except Exception as e:
            logger.error(f"Paper weight assessment failed for {document_id}: {e}")
            # Return minimal assessment on error
            return {
                "document_id": document_id,
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
        Run PRISMA 2020 compliance assessment with caching support.

        Args:
            document: Document dictionary

        Returns:
            PRISMA assessment dictionary, or None on error
        """
        document_id = document["id"]

        # Check cache first (unless force_recompute is set)
        version_id = self._get_version_id("prisma", "prisma2020")
        if version_id and self._cache_manager:
            cached_result = self._cache_manager.get_prisma_assessment(document_id, version_id)
            if cached_result:
                logger.info(f"Using cached PRISMA assessment for document {document_id}")
                return cached_result

        # Not in cache or force recompute - run assessment
        try:
            start_time = time.time()
            agent = self._get_prisma_agent()

            # Use assess_prisma_compliance with full document dict
            # skip_suitability_check=True since we already checked suitability
            result = agent.assess_prisma_compliance(
                document=document,
                skip_suitability_check=True,
            )

            if result is None:
                logger.warning(f"PRISMA assessment returned None for document {document_id}")
                return None

            result_dict = result.to_dict()
            execution_time_ms = int((time.time() - start_time) * 1000)

            # Store in cache
            if version_id and self._cache_manager:
                self._cache_manager.store_prisma_assessment(
                    document_id, version_id, result_dict, execution_time_ms
                )

            return result_dict

        except Exception as e:
            logger.error(f"PRISMA assessment failed for {document_id}: {e}")
            return None

    # =========================================================================
    # Conditional Logic (LLM-Based Suitability Checks)
    # =========================================================================

    def _check_pico_suitability(self, document: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Check if PICO extraction is applicable using LLM-based assessment with caching.

        Uses PICOAgent's check_suitability method to determine if the document
        is an intervention study suitable for PICO component extraction.

        Args:
            document: Document dictionary

        Returns:
            Suitability assessment dictionary, or None on error
        """
        document_id = document["id"]

        # Check cache first (unless force_recompute is set)
        version_id = self._get_version_id("pico", "pico")
        if version_id and self._cache_manager:
            cached_result = self._cache_manager.get_suitability_check(
                document_id, "pico", version_id
            )
            if cached_result:
                logger.info(f"Using cached PICO suitability check for document {document_id}")
                return cached_result

        # Not in cache or force recompute - run check
        try:
            start_time = time.time()
            agent = self._get_pico_agent()
            suitability = agent.check_suitability(document)

            if suitability is None:
                logger.warning(f"PICO suitability check returned None for document {document_id}")
                return None

            result_dict = suitability.to_dict()
            execution_time_ms = int((time.time() - start_time) * 1000)

            # Store in cache
            if version_id and self._cache_manager:
                self._cache_manager.store_suitability_check(
                    document_id, "pico", version_id, result_dict, execution_time_ms
                )

            return result_dict

        except Exception as e:
            logger.error(f"PICO suitability check failed for {document_id}: {e}")
            return None

    def _check_prisma_suitability(self, document: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Check if PRISMA assessment is applicable using LLM-based assessment with caching.

        Uses PRISMA2020Agent's check_suitability method to determine if the document
        is a systematic review or meta-analysis suitable for PRISMA assessment.

        Args:
            document: Document dictionary

        Returns:
            Suitability assessment dictionary, or None on error
        """
        document_id = document["id"]

        # Check cache first (unless force_recompute is set)
        version_id = self._get_version_id("prisma", "prisma2020")
        if version_id and self._cache_manager:
            cached_result = self._cache_manager.get_suitability_check(
                document_id, "prisma", version_id
            )
            if cached_result:
                logger.info(f"Using cached PRISMA suitability check for document {document_id}")
                return cached_result

        # Not in cache or force recompute - run check
        try:
            start_time = time.time()
            agent = self._get_prisma_agent()
            suitability = agent.check_suitability(document)

            if suitability is None:
                logger.warning(f"PRISMA suitability check returned None for document {document_id}")
                return None

            result_dict = suitability.to_dict()
            execution_time_ms = int((time.time() - start_time) * 1000)

            # Store in cache
            if version_id and self._cache_manager:
                self._cache_manager.store_suitability_check(
                    document_id, "prisma", version_id, result_dict, execution_time_ms
                )

            return result_dict

        except Exception as e:
            logger.error(f"PRISMA suitability check failed for {document_id}: {e}")
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
