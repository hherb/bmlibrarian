"""
Background workflow execution thread for Qt GUI.

Provides threaded workflow execution with cancellation support and detailed progress updates.
"""

from typing import Dict, Any, Optional, List, Tuple
from PySide6.QtCore import QThread, Signal
import logging


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
            # Step 6: Counterfactual Analysis (Optional)
            # ==================================================================
            # Initialize variables for later use in Step 8
            counterfactual_analysis = None
            unique_contradictory_docs = []
            counterfactual_questions = []

            if self.enable_counterfactual and self.executor.counterfactual_agent and self.executor.editor_agent:
                # Step 6a: Analyze preliminary report for counterfactual questions
                step_name = "counterfactual_analysis"
                self.step_started.emit(step_name, "Analyzing report for potential contradictions")
                self.status_message.emit(f"🔄 Generating counterfactual research questions...")

                if self._check_cancellation(step_name):
                    return

                # Analyze preliminary report to generate counterfactual questions
                counterfactual_analysis = self.executor.counterfactual_agent.analyze_document(
                    document_content=self.preliminary_report,
                    document_title=f"Preliminary Report: {self.question[:100]}"
                )

                if not counterfactual_analysis:
                    self.logger.warning("Counterfactual analysis failed - skipping")
                    self.step_completed.emit(step_name)
                else:
                    # Store counterfactual questions
                    counterfactual_questions = counterfactual_analysis.counterfactual_questions
                    self.status_message.emit(
                        f"✓ Generated {len(counterfactual_questions)} counterfactual questions"
                    )
                    self.step_completed.emit(step_name)

                    # ==============================================================
                    # Step 7: Search for Contradictory Evidence
                    # ==============================================================
                    step_name = "search_contradictory_evidence"
                    self.step_started.emit(step_name, "Searching for contradictory evidence")
                    self.status_message.emit(f"📚 Searching for contradictory studies...")

                    if self._check_cancellation(step_name):
                        return

                    # Search for contradictory documents using counterfactual statements
                    contradictory_docs = []
                    for i, cf_question in enumerate(counterfactual_questions, 1):
                        if self._check_cancellation(step_name):
                            return

                        # Emit progress for each counterfactual search
                        self.step_progress.emit(step_name, i, len(counterfactual_questions))

                        # Use the counterfactual_statement for search (it's a declarative statement)
                        cf_statement = cf_question.counterfactual_statement

                        # Convert natural language statement to PostgreSQL tsquery
                        # Use QueryAgent if available, otherwise try direct search
                        if self.executor.query_agent:
                            try:
                                cf_query = self.executor.query_agent.convert_question(cf_statement)
                                if cf_query:
                                    cf_docs = self.executor.query_agent.search_documents(cf_query)
                                    if cf_docs:
                                        # Tag documents with the counterfactual question they relate to
                                        for doc in cf_docs:
                                            doc['_counterfactual_question'] = cf_question.question
                                            doc['_counterfactual_priority'] = cf_question.priority
                                        contradictory_docs.extend(cf_docs[:self.max_results])
                            except Exception as e:
                                self.logger.error(f"Counterfactual search failed for: {cf_statement[:100]}: {e}")
                                continue

                    # Remove duplicates based on doc_id
                    seen_ids = set()
                    unique_contradictory_docs = []
                    for doc in contradictory_docs:
                        doc_id = doc.get('doc_id')
                        if doc_id and doc_id not in seen_ids:
                            seen_ids.add(doc_id)
                            unique_contradictory_docs.append(doc)

                    self.status_message.emit(
                        f"✓ Found {len(unique_contradictory_docs)} potentially contradictory documents"
                    )
                    self.step_completed.emit(step_name)

                    # Store counterfactual results
                    self.counterfactual_results = {
                        'analysis': counterfactual_analysis,
                        'questions': counterfactual_questions,
                        'contradictory_documents': unique_contradictory_docs,
                        'question_count': len(counterfactual_questions),
                        'document_count': len(unique_contradictory_docs)
                    }
                    self.counterfactual_analysis_complete.emit(self.counterfactual_results)

            # ==============================================================
            # Step 8: Generate Comprehensive Final Report
            # ==============================================================
            # This step runs ALWAYS - either with or without counterfactual analysis
            step_name = "generate_final_report"
            self.step_started.emit(step_name, "Creating comprehensive balanced report")

            if counterfactual_analysis and unique_contradictory_docs and self.executor.editor_agent:
                # Case 1: Counterfactual analysis succeeded - use EditorAgent for comprehensive report
                self.status_message.emit(f"📄 Synthesizing final report with all evidence...")

                if self._check_cancellation(step_name):
                    return

                # Prepare contradictory evidence dict for EditorAgent
                contradictory_evidence = {
                    'counterfactual_analysis': counterfactual_analysis,
                    'contradictory_documents': unique_contradictory_docs,
                    'counterfactual_questions': counterfactual_questions
                }

                # Generate comprehensive report using EditorAgent
                # EditorAgent needs: original_report, research_question, supporting_citations,
                #                    contradictory_evidence, confidence_analysis
                try:
                    # Convert preliminary report text to a simple report-like object
                    # EditorAgent expects an object with content/text attribute
                    class PreliminaryReportWrapper:
                        def __init__(self, content):
                            self.content = content
                            self.text = content
                            self.markdown = content

                    preliminary_report_obj = PreliminaryReportWrapper(self.preliminary_report)

                    edited_report = self.executor.editor_agent.create_comprehensive_report(
                        original_report=preliminary_report_obj,
                        research_question=self.question,
                        supporting_citations=self.citations,
                        contradictory_evidence=contradictory_evidence,
                        confidence_analysis=counterfactual_analysis
                    )

                    if edited_report:
                        # Format the edited report as markdown
                        self.final_report = self._format_edited_report(edited_report)
                        self.final_report_generated.emit(self.final_report)

                        final_word_count = len(self.final_report.split())
                        self.status_message.emit(
                            f"✓ Generated comprehensive final report ({final_word_count} words)"
                        )
                    else:
                        self.logger.warning("EditorAgent failed to create final report")
                        self.final_report = self.preliminary_report  # Fallback to preliminary

                except Exception as e:
                    self.logger.error(f"Final report generation failed: {e}", exc_info=True)
                    self.final_report = self.preliminary_report  # Fallback to preliminary
            else:
                # Case 2: No counterfactual analysis or it failed - use preliminary report as final
                self.status_message.emit(f"📄 Using preliminary report as final report...")
                self.final_report = self.preliminary_report
                self.final_report_generated.emit(self.final_report)

                final_word_count = len(self.final_report.split())
                self.status_message.emit(
                    f"✓ Final report ready ({final_word_count} words)"
                )

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
