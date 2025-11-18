"""
Background workflow execution thread for Qt GUI.

Provides threaded workflow execution with cancellation support and detailed progress updates.
"""

from typing import Dict, Any, Optional, List, Tuple
from PySide6.QtCore import QThread, Signal
import logging

# Import ReportBuilder for consistent final report generation (same as Flet GUI)
from bmlibrarian.gui.report_builder import ReportBuilder


class WorkflowThread(QThread):
    """
    Background thread for executing BMLibrarian research workflow.

    This thread runs the complete workflow (query generation, document search,
    scoring, citation extraction, reporting, and optional counterfactual analysis)
    in the background without blocking the Qt GUI.

    Features:
    - Cancellable execution (check _should_cancel flag periodically)
    - Detailed progress signals for each workflow step
    - Error handling with signal emission
    - Clean thread lifecycle management
    """

    # Progress signals
    step_started = Signal(str, str)  # (step_name, step_description)
    step_progress = Signal(str, int, int)  # (step_name, current, total)
    step_completed = Signal(str)  # step_name
    status_message = Signal(str)  # status text

    # Result signals
    query_generated = Signal(str)  # SQL query
    documents_found = Signal(list)  # List of documents
    documents_scored = Signal(list)  # List of (doc, score) tuples
    citations_extracted = Signal(list)  # List of citations
    preliminary_report_generated = Signal(str)  # Markdown report
    counterfactual_analysis_complete = Signal(dict)  # Analysis results
    final_report_generated = Signal(str)  # Markdown report

    # Completion signals
    workflow_completed = Signal(dict)  # Final results dictionary
    workflow_error = Signal(Exception)  # Error occurred
    workflow_cancelled = Signal()  # Workflow was cancelled

    def __init__(
        self,
        executor: 'QtWorkflowExecutor',
        question: str,
        max_results: int = 100,
        score_threshold: float = 3.0,
        enable_counterfactual: bool = False,
        parent: Optional[QThread] = None
    ):
        """
        Initialize workflow thread.

        Args:
            executor: The QtWorkflowExecutor with configured agents
            question: Research question to answer
            max_results: Maximum number of documents to retrieve
            score_threshold: Minimum relevance score for citation extraction
            enable_counterfactual: Whether to run counterfactual analysis
            parent: Optional parent QObject
        """
        super().__init__(parent)

        self.logger = logging.getLogger("bmlibrarian.gui.qt.WorkflowThread")

        # Store executor reference (contains all agents)
        self.executor = executor

        # Workflow parameters
        self.question = question
        self.max_results = max_results
        self.score_threshold = score_threshold
        self.enable_counterfactual = enable_counterfactual

        # Cancellation flag (checked periodically during execution)
        self._should_cancel = False

        # Workflow results (accumulated during execution)
        self.query: str = ""
        self.documents: List[Dict[str, Any]] = []
        self.scored_documents: List[Tuple[Dict, Dict]] = []
        self.citations: List[Dict[str, Any]] = []
        self.preliminary_report: str = ""
        self.counterfactual_results: Optional[Dict[str, Any]] = None
        self.final_report: str = ""

    def cancel(self) -> None:
        """
        Request workflow cancellation.

        Sets the cancellation flag. The workflow will check this flag
        between steps and exit gracefully.
        """
        self.logger.info("Workflow cancellation requested")
        self._should_cancel = True
        self.status_message.emit("🛑 Cancelling workflow...")

    def _check_cancellation(self, step_name: str) -> bool:
        """
        Check if workflow should be cancelled.

        Args:
            step_name: Current workflow step (for logging)

        Returns:
            True if should cancel, False otherwise
        """
        if self._should_cancel:
            self.logger.info(f"Workflow cancelled during step: {step_name}")
            self.workflow_cancelled.emit()
            return True
        return False

    def run(self) -> None:
        """
        Execute the complete workflow in background thread.

        This is the main thread execution method. It orchestrates all
        workflow steps and emits progress signals along the way.

        Workflow Steps:
        1. Generate database query from question
        2. Search for relevant documents
        3. Score documents for relevance
        4. Extract citations from high-scoring documents
        5. Generate preliminary report
        6. [Optional] Perform counterfactual analysis
        7. [Optional] Search for contradictory evidence
        8. [Optional] Generate comprehensive final report
        """
        try:
            self.logger.info(f"Workflow thread started: {self.question[:100]}")

            # Set the research question on the executor before starting workflow
            self.executor.current_question = self.question
            self.executor.max_results = self.max_results
            self.logger.debug(f"Executor configured: question='{self.question[:50]}...', max_results={self.max_results}")

            # ==================================================================
            # Step 1: Generate Query
            # ==================================================================
            step_name = "generate_query"
            self.step_started.emit(step_name, "Generating database query from your question")
            self.status_message.emit("🔍 Generating database query...")

            if self._check_cancellation(step_name):
                return

            self.query = self.executor.generate_query()
            self.query_generated.emit(self.query)
            self.step_completed.emit(step_name)

            if not self.query or not self.query.strip():
                raise ValueError("Query generation failed - no query returned")

            # ==================================================================
            # Step 2: Search Documents
            # ==================================================================
            step_name = "search_documents"
            self.step_started.emit(step_name, f"Searching database with query: {self.query[:50]}...")
            self.status_message.emit(f"📚 Searching database...")

            if self._check_cancellation(step_name):
                return

            self.documents = self.executor.search_documents(self.query)
            self.documents_found.emit(self.documents)
            self.step_completed.emit(step_name)

            if not self.documents:
                self.status_message.emit("⚠️ No documents found")
                self._emit_completion_no_documents()
                return

            self.status_message.emit(f"✓ Found {len(self.documents)} documents")

            # ==================================================================
            # Step 3: Score Documents
            # ==================================================================
            step_name = "score_documents"
            self.step_started.emit(step_name, f"Scoring {len(self.documents)} documents for relevance")
            self.status_message.emit(f"📊 Scoring {len(self.documents)} documents...")

            if self._check_cancellation(step_name):
                return

            self.scored_documents = []
            total = len(self.documents)

            for i, doc in enumerate(self.documents, 1):
                if self._check_cancellation(step_name):
                    return

                # Emit progress
                self.step_progress.emit(step_name, i, total)

                # Score document
                score_result = self.executor.scoring_agent.evaluate_document(
                    self.question, doc
                )

                if score_result:
                    self.scored_documents.append((doc, score_result))

            self.documents_scored.emit(self.scored_documents)
            self.step_completed.emit(step_name)

            if not self.scored_documents:
                self.status_message.emit("⚠️ No documents could be scored")
                self._emit_completion_no_scores()
                return

            high_scoring_count = len([
                (d, s) for d, s in self.scored_documents
                if isinstance(s.get('score'), (int, float)) and s.get('score', 0) >= self.score_threshold
            ])
            self.status_message.emit(
                f"✓ Scored {len(self.scored_documents)} documents "
                f"({high_scoring_count} above threshold {self.score_threshold})"
            )

            # ==================================================================
            # Step 4: Extract Citations
            # ==================================================================
            step_name = "extract_citations"
            self.step_started.emit(step_name, f"Extracting citations from {high_scoring_count} high-scoring documents")
            self.status_message.emit(f"💬 Extracting citations...")

            if self._check_cancellation(step_name):
                return

            self.citations = self.executor.extract_citations(
                self.scored_documents,
                score_threshold=self.score_threshold
            )
            self.citations_extracted.emit(self.citations)
            self.step_completed.emit(step_name)

            if not self.citations:
                self.status_message.emit("⚠️ No citations could be extracted")
                self._emit_completion_no_citations()
                return

            self.status_message.emit(f"✓ Extracted {len(self.citations)} citations")

            # ==================================================================
            # Step 5: Generate Preliminary Report
            # ==================================================================
            step_name = "generate_preliminary_report"
            self.step_started.emit(step_name, f"Generating preliminary report from {len(self.citations)} citations")
            self.status_message.emit(f"📄 Generating preliminary report...")

            if self._check_cancellation(step_name):
                return

            self.preliminary_report = self.executor.generate_preliminary_report(self.citations)
            self.preliminary_report_generated.emit(self.preliminary_report)
            self.step_completed.emit(step_name)

            report_word_count = len(self.preliminary_report.split())
            self.status_message.emit(f"✓ Generated preliminary report ({report_word_count} words)")

            # ==================================================================
            # Step 6-7: Comprehensive Counterfactual Analysis (WITH citation extraction)
            # ==================================================================
            if self.enable_counterfactual and self.executor.counterfactual_agent and self.executor.editor_agent:
                step_name = "counterfactual_analysis"
                self.step_started.emit(step_name, "Performing comprehensive counterfactual analysis")
                self.status_message.emit(f"🔬 Analyzing report and searching for contradictory evidence...")

                if self._check_cancellation(step_name):
                    return

                # Use the comprehensive find_contradictory_literature method (same as Flet GUI)
                # This does ALL the work:
                # 1. Analyzes report to generate counterfactual questions
                # 2. Searches for contradictory documents
                # 3. SCORES the contradictory documents (using ScoringAgent)
                # 4. EXTRACTS citations from contradictory documents (using CitationAgent)
                # 5. Assembles comprehensive analysis with evidence and citations
                try:
                    comprehensive_analysis = self.executor.counterfactual_agent.find_contradictory_literature(
                        document_content=self.preliminary_report,
                        document_title=f"Preliminary Report: {self.question[:100]}",
                        max_results_per_query=100,  # Same as main search
                        min_relevance_score=3.0,  # Configurable threshold for contradictory docs
                        query_agent=self.executor.query_agent,
                        scoring_agent=self.executor.scoring_agent,  # ← Scores contradictory docs!
                        citation_agent=self.executor.citation_agent  # ← Extracts citations!
                    )

                    if not comprehensive_analysis:
                        self.logger.warning("Counterfactual analysis failed - skipping")
                        self.step_completed.emit(step_name)
                        counterfactual_analysis = None
                    else:
                        # Extract components from comprehensive analysis
                        analysis_obj = comprehensive_analysis.get('analysis')
                        contradictory_evidence = comprehensive_analysis.get('contradictory_evidence', [])
                        contradictory_citations = comprehensive_analysis.get('contradictory_citations', [])
                        rejected_citations = comprehensive_analysis.get('rejected_citations', [])
                        no_citation_extracted = comprehensive_analysis.get('no_citation_extracted', [])
                        summary = comprehensive_analysis.get('summary', {})

                        # Get questions from analysis object
                        counterfactual_questions = []
                        if analysis_obj and hasattr(analysis_obj, 'counterfactual_questions'):
                            counterfactual_questions = analysis_obj.counterfactual_questions

                        # Extract documents from contradictory evidence (for backward-compatible UI display)
                        contradictory_docs = []
                        for evidence_item in contradictory_evidence:
                            if isinstance(evidence_item, dict) and 'document' in evidence_item:
                                doc = evidence_item['document']
                                # Tag with score and reasoning
                                doc['_counterfactual_score'] = evidence_item.get('score')
                                doc['_counterfactual_reasoning'] = evidence_item.get('reasoning')
                                contradictory_docs.append(doc)

                        self.status_message.emit(
                            f"✓ Found {len(contradictory_docs)} contradictory documents, "
                            f"extracted {len(contradictory_citations)} citations"
                        )
                        self.step_completed.emit(step_name)

                        # Store comprehensive counterfactual results (matching Flet structure)
                        self.counterfactual_results = {
                            'analysis': analysis_obj,
                            'questions': counterfactual_questions,
                            'contradictory_documents': contradictory_docs,
                            'contradictory_evidence': contradictory_evidence,  # Scored documents
                            'contradictory_citations': contradictory_citations,  # ← CITATIONS!
                            'rejected_citations': rejected_citations,
                            'no_citation_extracted': no_citation_extracted,
                            'summary': summary,
                            'question_count': len(counterfactual_questions),
                            'document_count': len(contradictory_docs),
                            'citation_count': len(contradictory_citations)
                        }
                        self.counterfactual_analysis_complete.emit(self.counterfactual_results)

                        # Also store for final report generation
                        counterfactual_analysis = comprehensive_analysis

                except Exception as e:
                    self.logger.error(f"Comprehensive counterfactual analysis failed: {e}", exc_info=True)
                    self.status_message.emit(f"⚠️ Counterfactual analysis failed: {str(e)}")
                    self.step_completed.emit(step_name)
                    counterfactual_analysis = None

                    # ==============================================================
                    # Step 8: Generate Comprehensive Final Report
                    # ==============================================================
                    step_name = "generate_final_report"
                    self.step_started.emit(step_name, "Creating comprehensive balanced report")
                    self.status_message.emit(f"📄 Synthesizing final report with all evidence...")

                    if self._check_cancellation(step_name):
                        return

                    # Use ReportBuilder to create final report (same approach as Flet GUI)
                    # This wraps the preliminary report (which contains all citations) with metadata sections
                    try:
                        # Create workflow steps list for metadata
                        workflow_steps = []  # Will be populated with actual steps if available

                        # Initialize ReportBuilder
                        report_builder = ReportBuilder(workflow_steps)

                        # Build comprehensive final report using same method as Flet GUI
                        # This preserves all citations from the preliminary report
                        self.final_report = report_builder.build_final_report(
                            research_question=self.question,
                            report_content=self.preliminary_report,  # Preliminary report with all citations
                            counterfactual_analysis=counterfactual_analysis,  # Counterfactual analysis results
                            documents=self.documents,  # All found documents
                            scored_documents=self.scored_documents,  # Scored documents above threshold
                            citations=self.citations,  # Extracted citations
                            human_in_loop=False,  # Qt GUI doesn't have interactive mode yet
                            agent_model_info=None,  # TODO: Pass model info if available
                            all_scored_documents=self.scored_documents  # All scored documents for accurate stats
                        )

                        if self.final_report:
                            self.final_report_generated.emit(self.final_report)
                            final_word_count = len(self.final_report.split())
                            self.status_message.emit(
                                f"✓ Generated comprehensive final report ({final_word_count} words)"
                            )
                            self.logger.info(f"Final report generated with {final_word_count} words, {len(self.final_report)} characters")
                        else:
                            self.logger.warning("ReportBuilder returned empty final report")
                            self.final_report = self.preliminary_report  # Fallback to preliminary

                    except Exception as e:
                        self.logger.error(f"Final report generation failed: {e}", exc_info=True)
                        self.final_report = self.preliminary_report  # Fallback to preliminary
                        self.status_message.emit(f"⚠️ Using preliminary report (final report generation failed)")

                    self.step_completed.emit(step_name)

            # ==================================================================
            # Final: Emit Completion
            # ==================================================================
            self.status_message.emit(
                f"✅ Workflow complete! {len(self.citations)} citations, "
                f"{report_word_count} word report"
            )

            results = {
                'milestone': 4,
                'status': 'completed',
                'question': self.question,
                'query': self.query,
                'documents': self.documents,
                'scored_documents': self.scored_documents,
                'citations': self.citations,
                'preliminary_report': self.preliminary_report,
                'counterfactual_results': self.counterfactual_results,
                'final_report': self.final_report,
                'document_count': len(self.documents),
                'high_scoring_count': high_scoring_count,
                'citation_count': len(self.citations),
                'report_length': len(self.preliminary_report)
            }

            self.workflow_completed.emit(results)

        except Exception as e:
            self.logger.error(f"Workflow execution failed: {e}", exc_info=True)
            self.status_message.emit(f"❌ Error: {str(e)}")
            self.workflow_error.emit(e)

    def _format_edited_report(self, edited_report: Any) -> str:
        """
        Format an EditedReport object as markdown.

        Args:
            edited_report: EditedReport object from EditorAgent

        Returns:
            Formatted markdown string
        """
        sections = []

        # Title
        if hasattr(edited_report, 'title') and edited_report.title:
            sections.append(f"# {edited_report.title}\n")

        # Executive Summary
        if hasattr(edited_report, 'executive_summary') and edited_report.executive_summary:
            sections.append("## Executive Summary\n")
            sections.append(f"{edited_report.executive_summary}\n")

        # Methodology
        if hasattr(edited_report, 'methodology_section') and edited_report.methodology_section:
            sections.append("## Methodology\n")
            sections.append(f"{edited_report.methodology_section}\n")

        # Findings
        if hasattr(edited_report, 'findings_section') and edited_report.findings_section:
            sections.append("## Findings\n")
            sections.append(f"{edited_report.findings_section}\n")

        # Contradictory Evidence (if present)
        if hasattr(edited_report, 'contradictory_evidence_section') and edited_report.contradictory_evidence_section:
            sections.append("## Contradictory Evidence\n")
            sections.append(f"{edited_report.contradictory_evidence_section}\n")

        # Evidence Quality Table (if present)
        if hasattr(edited_report, 'evidence_quality_table') and edited_report.evidence_quality_table:
            sections.append("## Evidence Quality Assessment\n")
            sections.append(f"{edited_report.evidence_quality_table}\n")

        # Limitations
        if hasattr(edited_report, 'limitations_section') and edited_report.limitations_section:
            sections.append("## Limitations\n")
            sections.append(f"{edited_report.limitations_section}\n")

        # Conclusions
        if hasattr(edited_report, 'conclusions_section') and edited_report.conclusions_section:
            sections.append("## Conclusions\n")
            sections.append(f"{edited_report.conclusions_section}\n")

        # Confidence Assessment
        if hasattr(edited_report, 'confidence_assessment') and edited_report.confidence_assessment:
            sections.append(f"**Overall Confidence:** {edited_report.confidence_assessment}\n")

        # References (if present)
        if hasattr(edited_report, 'references') and edited_report.references:
            sections.append("## References\n")
            for i, ref in enumerate(edited_report.references, 1):
                if isinstance(ref, dict):
                    ref_text = ref.get('text', str(ref))
                elif isinstance(ref, str):
                    ref_text = ref
                else:
                    ref_text = str(ref)
                sections.append(f"{i}. {ref_text}\n")

        # Word count and metadata
        if hasattr(edited_report, 'word_count') and edited_report.word_count:
            sections.append(f"\n---\n*Word count: {edited_report.word_count}*\n")

        return "\n".join(sections)

    def _emit_completion_no_documents(self) -> None:
        """Emit completion signal when no documents are found."""
        results = {
            'milestone': 4,
            'status': 'no_documents',
            'question': self.question,
            'query': self.query,
            'documents': [],
            'scored_documents': [],
            'citations': [],
            'preliminary_report': '',
            'counterfactual_results': None,
            'final_report': '',
            'document_count': 0
        }
        self.workflow_completed.emit(results)

    def _emit_completion_no_scores(self) -> None:
        """Emit completion signal when documents can't be scored."""
        results = {
            'milestone': 4,
            'status': 'no_scores',
            'question': self.question,
            'query': self.query,
            'documents': self.documents,
            'scored_documents': [],
            'citations': [],
            'preliminary_report': '',
            'counterfactual_results': None,
            'final_report': '',
            'document_count': len(self.documents)
        }
        self.workflow_completed.emit(results)

    def _emit_completion_no_citations(self) -> None:
        """Emit completion signal when no citations can be extracted."""
        high_scoring_count = len([
            (d, s) for d, s in self.scored_documents
            if isinstance(s.get('score'), (int, float)) and s.get('score', 0) >= self.score_threshold
        ])

        results = {
            'milestone': 4,
            'status': 'no_citations',
            'question': self.question,
            'query': self.query,
            'documents': self.documents,
            'scored_documents': self.scored_documents,
            'citations': [],
            'preliminary_report': '',
            'counterfactual_results': None,
            'final_report': '',
            'document_count': len(self.documents),
            'high_scoring_count': high_scoring_count
        }
        self.workflow_completed.emit(results)
