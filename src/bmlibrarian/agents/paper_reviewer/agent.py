"""
Paper Reviewer Agent - Main Orchestrator

Comprehensive paper review agent that coordinates multiple sub-agents
to provide thorough analysis of research papers.

Components:
- DocumentResolver: Resolves DOI/PMID/PDF/text to document dicts
- SummaryGenerator: Creates brief summaries and extracts hypotheses
- StudyTypeDetector: Detects study type for PICO/PRISMA applicability
- PICOAgent: PICO extraction (when applicable)
- PRISMA2020Agent: PRISMA assessment (when applicable)
- PaperWeightAssessmentAgent: Multi-dimensional weight assessment
- StudyAssessmentAgent: Study quality assessment
- ContradictoryEvidenceFinder: Finds contradicting literature
"""

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Callable, Dict, Any, List

from ..base import BaseAgent
from ...config import get_model, get_agent_config, get_ollama_host

from .models import (
    PaperReviewResult,
    StudyTypeResult,
    ContradictoryPaper,
    ReviewStep,
    ReviewStepStatus,
    SourceType,
    create_review_steps,
    VERSION,
)
from .constants import (
    MAX_STRENGTHS_TO_EXTRACT,
    MAX_WEAKNESSES_TO_EXTRACT,
    MAX_STRENGTHS_IN_SUMMARY,
    MAX_WEAKNESSES_IN_SUMMARY,
    STRONG_SCORE_THRESHOLD,
    WEAK_SCORE_THRESHOLD,
    HIGH_CONFIDENCE_THRESHOLD,
    LOW_CONFIDENCE_THRESHOLD,
)
from .resolver import DocumentResolver
from .summarizer import SummaryGenerator
from .study_detector import StudyTypeDetector
from .contradictory_finder import ContradictoryEvidenceFinder

logger = logging.getLogger(__name__)


class PaperReviewerAgent(BaseAgent):
    """
    Main orchestrator for comprehensive paper review.

    Coordinates multiple sub-agents to perform:
    1. Document resolution (DOI, PMID, PDF, text)
    2. Summary generation
    3. Hypothesis extraction
    4. Study type detection
    5. PICO analysis (if applicable)
    6. PRISMA assessment (if applicable)
    7. Paper weight assessment
    8. Study quality assessment
    9. Strengths/weaknesses synthesis
    10. Contradictory evidence search
    """

    VERSION = VERSION

    def __init__(
        self,
        model: Optional[str] = None,
        host: Optional[str] = None,
        callback: Optional[Callable[[str, str], None]] = None,
        data_callback: Optional[Callable[[str, Dict], None]] = None,
        orchestrator: Optional[Any] = None,
        show_model_info: bool = True,
        ncbi_email: Optional[str] = None,
        ncbi_api_key: Optional[str] = None,
    ):
        """
        Initialize the PaperReviewerAgent.

        Args:
            model: LLM model name (default: from config)
            host: Ollama server host URL (default: from config)
            callback: Optional callback for progress updates (step_name, message)
            data_callback: Optional callback for intermediate data (step_name, data_dict)
            orchestrator: Optional orchestrator for queue-based processing
            show_model_info: Whether to display model information
            ncbi_email: Email for NCBI API (for external search)
            ncbi_api_key: NCBI API key for higher rate limits
        """
        # Get defaults from config if not provided
        if model is None:
            model = get_model('paper_reviewer')
        if host is None:
            host = get_ollama_host()

        super().__init__(
            model=model,
            host=host,
            callback=callback,
            orchestrator=orchestrator,
            show_model_info=show_model_info,
        )

        self.data_callback = data_callback
        self.ncbi_email = ncbi_email
        self.ncbi_api_key = ncbi_api_key

        # Initialize sub-components (lazy loading for sub-agents)
        self._resolver: Optional[DocumentResolver] = None
        self._summarizer: Optional[SummaryGenerator] = None
        self._study_detector: Optional[StudyTypeDetector] = None
        self._contradictory_finder: Optional[ContradictoryEvidenceFinder] = None

    def get_agent_type(self) -> str:
        """Get the agent type identifier."""
        return "paper_reviewer_agent"

    @property
    def resolver(self) -> DocumentResolver:
        """Get or create DocumentResolver."""
        if self._resolver is None:
            self._resolver = DocumentResolver(
                ncbi_email=self.ncbi_email,
                ncbi_api_key=self.ncbi_api_key,
            )
        return self._resolver

    @property
    def summarizer(self) -> SummaryGenerator:
        """Get or create SummaryGenerator."""
        if self._summarizer is None:
            self._summarizer = SummaryGenerator(
                model=self.model,
                host=self.host,
                callback=self.callback,
                show_model_info=False,
            )
        return self._summarizer

    @property
    def study_detector(self) -> StudyTypeDetector:
        """Get or create StudyTypeDetector."""
        if self._study_detector is None:
            self._study_detector = StudyTypeDetector(
                model=self.model,
                host=self.host,
                callback=self.callback,
                show_model_info=False,
            )
        return self._study_detector

    @property
    def contradictory_finder(self) -> ContradictoryEvidenceFinder:
        """Get or create ContradictoryEvidenceFinder."""
        if self._contradictory_finder is None:
            self._contradictory_finder = ContradictoryEvidenceFinder(
                model=self.model,
                host=self.host,
                callback=self.callback,
                show_model_info=False,
                ncbi_email=self.ncbi_email,
                ncbi_api_key=self.ncbi_api_key,
            )
        return self._contradictory_finder

    def _call_data_callback(self, step_name: str, data: Dict[str, Any]) -> None:
        """Call the data callback if provided."""
        if self.data_callback:
            try:
                self.data_callback(step_name, data)
            except Exception as e:
                logger.warning(f"Data callback failed for step '{step_name}': {e}")

    def review_paper(
        self,
        doi: Optional[str] = None,
        pmid: Optional[str] = None,
        pdf_path: Optional[Path] = None,
        text: Optional[str] = None,
        text_file: Optional[Path] = None,
        search_external: bool = True,
        skip_pico: bool = False,
        skip_prisma: bool = False,
        skip_paper_weight: bool = False,
        skip_study_assessment: bool = False,
        skip_contradictory: bool = False,
    ) -> PaperReviewResult:
        """
        Perform comprehensive paper review.

        Exactly one of doi, pmid, pdf_path, text, or text_file must be provided.

        Args:
            doi: DOI to look up
            pmid: PubMed ID to look up
            pdf_path: Path to PDF file
            text: Raw text content (abstract or full text)
            text_file: Path to text/markdown file
            search_external: Whether to search PubMed for contradictory evidence
            skip_pico: Skip PICO analysis even if applicable
            skip_prisma: Skip PRISMA assessment even if applicable
            skip_paper_weight: Skip paper weight assessment
            skip_study_assessment: Skip study quality assessment
            skip_contradictory: Skip contradictory evidence search

        Returns:
            Complete PaperReviewResult with all assessments
        """
        start_time = time.time()
        steps = create_review_steps()
        step_index = 0

        # Helper to get and update current step
        def get_step(name: str) -> ReviewStep:
            for s in steps:
                if s.name == name:
                    return s
            return steps[0]

        def update_step(name: str, status: ReviewStepStatus, summary: str = "", data: Dict = None):
            step = get_step(name)
            if status == ReviewStepStatus.IN_PROGRESS:
                step.start()
            elif status == ReviewStepStatus.COMPLETED:
                step.complete(summary, data)
            elif status == ReviewStepStatus.SKIPPED:
                step.skip(summary)
            elif status == ReviewStepStatus.FAILED:
                step.fail(summary)
            self._call_callback(name, summary)
            if data:
                self._call_data_callback(name, data)

        # Initialize result with defaults
        result = PaperReviewResult(
            document_id=None,
            doi=None,
            pmid=None,
            title="Unknown",
            authors=[],
            year=None,
            journal=None,
            source_type=SourceType.TEXT,
            brief_summary="",
            summary_confidence=0.0,
            core_hypothesis="",
            hypothesis_confidence=0.0,
            study_type_result=StudyTypeResult(
                study_type="unknown",
                study_type_detailed="Unknown",
                is_clinical_study=False,
                is_systematic_review=False,
                is_meta_analysis=False,
                is_observational=False,
                is_case_report=False,
                is_laboratory=False,
                confidence=0.0,
                rationale="Not yet analyzed",
            ),
            steps=steps,
        )

        try:
            # --- Step 1: Resolve Input ---
            update_step("resolve_input", ReviewStepStatus.IN_PROGRESS, "Resolving input")
            try:
                doc, source_type = self.resolver.resolve(
                    doi=doi,
                    pmid=pmid,
                    pdf_path=Path(pdf_path) if pdf_path else None,
                    text=text,
                    text_file=Path(text_file) if text_file else None,
                )
                result.document_id = doc.get('id')
                result.doi = doc.get('doi')
                result.pmid = doc.get('pmid')
                result.title = doc.get('title', 'Unknown')
                result.authors = doc.get('authors', [])
                result.year = doc.get('year')
                result.journal = doc.get('journal')
                result.source_type = source_type

                update_step("resolve_input", ReviewStepStatus.COMPLETED,
                           f"Resolved from {source_type.value}", {'document': doc})
            except Exception as e:
                update_step("resolve_input", ReviewStepStatus.FAILED, str(e))
                raise

            # --- Step 2: Generate Summary ---
            update_step("generate_summary", ReviewStepStatus.IN_PROGRESS, "Generating summary")
            try:
                summary, summary_conf = self.summarizer.generate_summary(doc)
                result.brief_summary = summary
                result.summary_confidence = summary_conf
                update_step("generate_summary", ReviewStepStatus.COMPLETED,
                           f"Generated ({summary_conf:.0%} confidence)",
                           {'summary': summary, 'confidence': summary_conf})
            except Exception as e:
                update_step("generate_summary", ReviewStepStatus.FAILED, str(e))
                logger.error(f"Summary generation failed: {e}")

            # --- Step 3: Extract Hypothesis ---
            update_step("extract_hypothesis", ReviewStepStatus.IN_PROGRESS, "Extracting hypothesis")
            try:
                hypothesis, hyp_conf = self.summarizer.extract_hypothesis(doc)
                result.core_hypothesis = hypothesis
                result.hypothesis_confidence = hyp_conf
                update_step("extract_hypothesis", ReviewStepStatus.COMPLETED,
                           f"Extracted ({hyp_conf:.0%} confidence)",
                           {'hypothesis': hypothesis, 'confidence': hyp_conf})
            except Exception as e:
                update_step("extract_hypothesis", ReviewStepStatus.FAILED, str(e))
                logger.error(f"Hypothesis extraction failed: {e}")

            # --- Step 4: Detect Study Type ---
            update_step("detect_study_type", ReviewStepStatus.IN_PROGRESS, "Detecting study type")
            try:
                study_type_result = self.study_detector.detect_study_type(doc)
                result.study_type_result = study_type_result
                result.pico_applicable = study_type_result.pico_applicable
                result.prisma_applicable = study_type_result.prisma_applicable
                update_step("detect_study_type", ReviewStepStatus.COMPLETED,
                           f"{study_type_result.study_type} ({study_type_result.confidence:.0%})",
                           study_type_result.to_dict())
            except Exception as e:
                update_step("detect_study_type", ReviewStepStatus.FAILED, str(e))
                logger.error(f"Study type detection failed: {e}")

            # --- Step 5: PICO Assessment (if applicable) ---
            if result.pico_applicable and not skip_pico:
                update_step("pico_assessment", ReviewStepStatus.IN_PROGRESS, "Running PICO analysis")
                try:
                    from ..pico_agent import PICOAgent
                    pico_agent = PICOAgent(
                        model=self.model,
                        host=self.host,
                        show_model_info=False,
                    )
                    pico_extraction = pico_agent.extract_pico(doc)
                    result.pico_extraction = pico_extraction
                    if pico_extraction:
                        update_step("pico_assessment", ReviewStepStatus.COMPLETED,
                                   f"Extracted PICO ({pico_extraction.extraction_confidence:.0%})",
                                   pico_extraction.to_dict())
                    else:
                        update_step("pico_assessment", ReviewStepStatus.COMPLETED,
                                   "PICO extraction returned no results", {})
                except Exception as e:
                    update_step("pico_assessment", ReviewStepStatus.FAILED, str(e))
                    logger.error(f"PICO analysis failed: {e}")
            else:
                reason = "Skipped by user" if skip_pico else "Not applicable for this study type"
                update_step("pico_assessment", ReviewStepStatus.SKIPPED, reason)

            # --- Step 6: PRISMA Assessment (if applicable) ---
            if result.prisma_applicable and not skip_prisma:
                update_step("prisma_assessment", ReviewStepStatus.IN_PROGRESS, "Running PRISMA assessment")
                try:
                    from ..prisma2020_agent import PRISMA2020Agent
                    prisma_agent = PRISMA2020Agent(
                        model=self.model,
                        host=self.host,
                        show_model_info=False,
                    )
                    prisma_assessment = prisma_agent.assess_document(doc)
                    result.prisma_assessment = prisma_assessment
                    if prisma_assessment:
                        update_step("prisma_assessment", ReviewStepStatus.COMPLETED,
                                   "PRISMA assessment completed",
                                   prisma_assessment.to_dict())
                    else:
                        update_step("prisma_assessment", ReviewStepStatus.COMPLETED,
                                   "PRISMA assessment returned no results", {})
                except Exception as e:
                    update_step("prisma_assessment", ReviewStepStatus.FAILED, str(e))
                    logger.error(f"PRISMA assessment failed: {e}")
            else:
                reason = "Skipped by user" if skip_prisma else "Not applicable for this study type"
                update_step("prisma_assessment", ReviewStepStatus.SKIPPED, reason)

            # --- Step 7: Paper Weight Assessment ---
            if not skip_paper_weight:
                update_step("paper_weight", ReviewStepStatus.IN_PROGRESS, "Running paper weight assessment")
                try:
                    from ..paper_weight import PaperWeightAssessmentAgent
                    pw_agent = PaperWeightAssessmentAgent(
                        model=self.model,
                        host=self.host,
                        show_model_info=False,
                    )
                    paper_weight = pw_agent.assess_paper(doc)
                    result.paper_weight = paper_weight
                    if paper_weight:
                        update_step("paper_weight", ReviewStepStatus.COMPLETED,
                                   f"Weight: {paper_weight.final_weight:.1f}/10",
                                   paper_weight.to_dict())
                    else:
                        update_step("paper_weight", ReviewStepStatus.COMPLETED,
                                   "Paper weight assessment returned no results", {})
                except Exception as e:
                    update_step("paper_weight", ReviewStepStatus.FAILED, str(e))
                    logger.error(f"Paper weight assessment failed: {e}")
            else:
                update_step("paper_weight", ReviewStepStatus.SKIPPED, "Skipped by user")

            # --- Step 8: Study Quality Assessment ---
            if not skip_study_assessment:
                update_step("study_assessment", ReviewStepStatus.IN_PROGRESS, "Running study quality assessment")
                try:
                    from ..study_assessment_agent import StudyAssessmentAgent
                    sa_agent = StudyAssessmentAgent(
                        model=self.model,
                        host=self.host,
                        show_model_info=False,
                    )
                    study_assessment = sa_agent.assess_study(doc)
                    result.study_assessment = study_assessment
                    if study_assessment:
                        update_step("study_assessment", ReviewStepStatus.COMPLETED,
                                   f"Quality: {study_assessment.quality_score:.1f}/10",
                                   study_assessment.to_dict())
                    else:
                        update_step("study_assessment", ReviewStepStatus.COMPLETED,
                                   "Study assessment returned no results", {})
                except Exception as e:
                    update_step("study_assessment", ReviewStepStatus.FAILED, str(e))
                    logger.error(f"Study assessment failed: {e}")
            else:
                update_step("study_assessment", ReviewStepStatus.SKIPPED, "Skipped by user")

            # --- Step 9: Synthesize Strengths/Weaknesses ---
            update_step("synthesize_strengths", ReviewStepStatus.IN_PROGRESS, "Synthesizing strengths/weaknesses")
            try:
                strengths, weaknesses = self._synthesize_strengths_weaknesses(result)
                result.strengths_summary = strengths
                result.weaknesses_summary = weaknesses
                update_step("synthesize_strengths", ReviewStepStatus.COMPLETED,
                           f"{len(strengths)} strengths, {len(weaknesses)} weaknesses",
                           {'strengths': strengths, 'weaknesses': weaknesses})
            except Exception as e:
                update_step("synthesize_strengths", ReviewStepStatus.FAILED, str(e))
                logger.error(f"Strength/weakness synthesis failed: {e}")

            # --- Step 10: Search Contradictory Evidence ---
            if not skip_contradictory and result.core_hypothesis:
                update_step("search_contradictory", ReviewStepStatus.IN_PROGRESS,
                           "Searching for contradictory evidence")
                try:
                    counter_stmt, papers, sources = self.contradictory_finder.find_contradictory_evidence(
                        hypothesis=result.core_hypothesis,
                        document=doc,
                        search_external=search_external,
                    )
                    result.counter_statement = counter_stmt
                    result.contradictory_papers = papers
                    result.search_sources_used = sources
                    update_step("search_contradictory", ReviewStepStatus.COMPLETED,
                               f"Found {len(papers)} potentially contradicting papers",
                               {'counter_statement': counter_stmt,
                                'papers_count': len(papers),
                                'sources_used': sources})
                except Exception as e:
                    update_step("search_contradictory", ReviewStepStatus.FAILED, str(e))
                    logger.error(f"Contradictory evidence search failed: {e}")
            else:
                reason = "Skipped by user" if skip_contradictory else "No hypothesis to search against"
                update_step("search_contradictory", ReviewStepStatus.SKIPPED, reason)

            # --- Step 11: Compile Report ---
            update_step("compile_report", ReviewStepStatus.IN_PROGRESS, "Compiling final report")
            result.reviewed_at = datetime.now(timezone.utc)
            result.total_processing_time_seconds = time.time() - start_time
            update_step("compile_report", ReviewStepStatus.COMPLETED,
                       f"Completed in {result.total_processing_time_seconds:.1f}s",
                       {'processing_time': result.total_processing_time_seconds})

        except Exception as e:
            logger.error(f"Paper review failed: {e}")
            result.total_processing_time_seconds = time.time() - start_time
            raise

        return result

    def _synthesize_strengths_weaknesses(
        self,
        result: PaperReviewResult,
    ) -> tuple:
        """
        Synthesize strengths and weaknesses from all assessments.

        Args:
            result: Partial PaperReviewResult with completed assessments

        Returns:
            Tuple of (strengths_list, weaknesses_list)
        """
        strengths = []
        weaknesses = []

        # From Study Assessment
        if result.study_assessment:
            sa = result.study_assessment
            strengths.extend(sa.strengths[:MAX_STRENGTHS_TO_EXTRACT])
            weaknesses.extend(sa.limitations[:MAX_WEAKNESSES_TO_EXTRACT])

        # From Paper Weight Assessment
        if result.paper_weight:
            pw = result.paper_weight

            # Add study design strength/weakness based on score
            if pw.study_design.score >= STRONG_SCORE_THRESHOLD:
                strengths.append(f"Strong study design ({pw.study_type or 'well-designed'})")
            elif pw.study_design.score < WEAK_SCORE_THRESHOLD:
                weaknesses.append(f"Weak study design (score: {pw.study_design.score:.1f}/10)")

            # Add sample size strength/weakness
            if pw.sample_size.score >= STRONG_SCORE_THRESHOLD:
                if pw.sample_size_n:
                    strengths.append(f"Adequate sample size (N={pw.sample_size_n})")
                else:
                    strengths.append("Adequate sample size")
            elif pw.sample_size.score < WEAK_SCORE_THRESHOLD:
                weaknesses.append("Small sample size limits generalizability")

            # Add methodological quality
            if pw.methodological_quality.score >= STRONG_SCORE_THRESHOLD:
                strengths.append("High methodological quality")
            elif pw.methodological_quality.score < WEAK_SCORE_THRESHOLD:
                weaknesses.append("Methodological concerns")

            # Add risk of bias (inverted - high score = low risk)
            if pw.risk_of_bias.score >= STRONG_SCORE_THRESHOLD:
                strengths.append("Low risk of bias")
            elif pw.risk_of_bias.score < WEAK_SCORE_THRESHOLD:
                weaknesses.append("High risk of bias")

        # From PICO (if applicable)
        if result.pico_extraction:
            pico = result.pico_extraction
            if pico.extraction_confidence >= HIGH_CONFIDENCE_THRESHOLD:
                strengths.append("Clear PICO framework")
            if pico.comparison and pico.comparison.lower() not in ['none', 'n/a', 'not specified']:
                strengths.append("Has comparison/control group")
            else:
                weaknesses.append("No clear comparison group")

        # From PRISMA (if applicable)
        if result.prisma_assessment:
            prisma = result.prisma_assessment
            # Check if overall compliance is good
            if hasattr(prisma, 'overall_score') and prisma.overall_score:
                if prisma.overall_score >= HIGH_CONFIDENCE_THRESHOLD:
                    strengths.append("High PRISMA compliance")
                elif prisma.overall_score < LOW_CONFIDENCE_THRESHOLD:
                    weaknesses.append("Poor PRISMA compliance")

        # Deduplicate while preserving order
        seen_strengths = set()
        unique_strengths = []
        for s in strengths:
            s_lower = s.lower()
            if s_lower not in seen_strengths:
                seen_strengths.add(s_lower)
                unique_strengths.append(s)

        seen_weaknesses = set()
        unique_weaknesses = []
        for w in weaknesses:
            w_lower = w.lower()
            if w_lower not in seen_weaknesses:
                seen_weaknesses.add(w_lower)
                unique_weaknesses.append(w)

        return unique_strengths[:MAX_STRENGTHS_IN_SUMMARY], unique_weaknesses[:MAX_WEAKNESSES_IN_SUMMARY]


__all__ = ['PaperReviewerAgent']
