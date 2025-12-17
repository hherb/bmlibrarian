"""
Workflow signal handlers for the Research Tab.

This module contains a mixin class that handles all workflow-related signals
from the workflow executor and workflow thread.
"""

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Slot
from PySide6.QtWidgets import QMessageBox

if TYPE_CHECKING:
    from .research_tab import ResearchTabWidget


class WorkflowHandlersMixin:
    """
    Mixin class providing workflow signal handlers.

    This mixin is designed to be used with ResearchTabWidget and provides
    all the signal handlers for workflow execution, including:
    - Workflow lifecycle (started, completed, error)
    - Step progress tracking
    - Query generation and document search
    - Document scoring
    - Citation extraction
    - Report generation
    - Counterfactual analysis
    """

    # Type hints for attributes expected from ResearchTabWidget
    logger: logging.Logger
    workflow_running: bool
    current_results: dict
    counterfactual_results: dict
    final_report_markdown: str
    workflow_executor: any
    workflow_thread: any

    # ========================================================================
    # Workflow Lifecycle Handlers
    # ========================================================================

    @Slot()
    def _on_workflow_started(self: 'ResearchTabWidget') -> None:
        """Handle workflow started signal."""
        self.logger.info("Workflow started")
        self.workflow_running = True

        # Hide Start button, show Cancel button
        self.start_button.setVisible(False)
        self.cancel_button.setVisible(True)
        self.cancel_button.setEnabled(True)

        # Update status bar
        self.status_label.setText("Running")
        self.progress_label.setText("Starting research workflow...")

        self.workflow_started.emit()

    @Slot(dict)
    def _on_workflow_completed(self: 'ResearchTabWidget', results: dict) -> None:
        """Handle workflow completed signal."""
        self.logger.info(f"Workflow completed: {results.get('status', 'unknown')}")
        self.workflow_running = False

        # Show Start button, hide Cancel button
        self.start_button.setVisible(True)
        self.start_button.setEnabled(True)
        self.cancel_button.setVisible(False)

        # Update status bar
        self.status_label.setText("Completed")
        self.progress_label.setText("Research workflow completed successfully")

        self.current_results = results
        self.workflow_completed.emit(results)

        # Check which phase/milestone completed and show appropriate message
        self._show_completion_message(results)

    @Slot(Exception)
    def _on_workflow_error(self: 'ResearchTabWidget', error: Exception) -> None:
        """Handle workflow error signal."""
        self.logger.error(f"Workflow error: {error}", exc_info=True)
        self.workflow_running = False

        # Show Start button, hide Cancel button
        self.start_button.setVisible(True)
        self.start_button.setEnabled(True)
        self.cancel_button.setVisible(False)

        # Update status bar
        self.status_label.setText("Error")
        self.progress_label.setText("Workflow failed - see error message")

        self.workflow_error.emit(error)

        QMessageBox.critical(
            self,
            "Workflow Error",
            f"An error occurred during workflow execution:\n\n{str(error)}"
        )

    @Slot(str)
    def _on_workflow_status(self: 'ResearchTabWidget', message: str) -> None:
        """Handle workflow status message signal."""
        self.logger.debug(f"Workflow status: {message}")
        # Update progress label with status messages
        self.progress_label.setText(message)
        self.status_message.emit(message)

    def _show_completion_message(self: 'ResearchTabWidget', results: dict) -> None:
        """Show appropriate completion message based on phase/milestone."""
        phase = results.get('phase', 'unknown')
        milestone = results.get('milestone', None)

        if phase == 2:
            # Phase 2: Agent connection test
            QMessageBox.information(
                self,
                "Phase 2 Complete - Agents Connected!",
                f"Research question: {results.get('question', 'N/A')}\n\n"
                "All agents are initialized and ready!\n\n"
                "Agent connection test successful:\n"
                "- QueryAgent\n"
                "- ScoringAgent\n"
                "- CitationAgent\n"
                "- ReportingAgent\n"
                "- EditorAgent\n"
                "- CounterfactualAgent (optional)\n\n"
                "Phase 3 will implement full workflow execution."
            )
        elif phase == 3 and milestone == 1:
            # Milestone 1: Query generation and search complete
            document_count = results.get('document_count', 0)
            query = results.get('query', 'N/A')

            QMessageBox.information(
                self,
                "Milestone 1 Complete - Search Successful!",
                f"Research question: {results.get('question', 'N/A')}\n\n"
                f"Search completed successfully!\n\n"
                f"Query: {query[:100]}{'...' if len(query) > 100 else ''}\n\n"
                f"Found {document_count} documents\n\n"
                "Check the 'Search' tab to see the query and results summary."
            )
        elif phase == 3 and milestone == 3:
            # Milestone 3: Citations and preliminary report complete
            document_count = results.get('document_count', 0)
            citation_count = results.get('citation_count', 0)
            word_count = len(results.get('preliminary_report', '').split())

            QMessageBox.information(
                self,
                "Milestone 3 Complete - Report Generated!",
                f"Research question: {results.get('question', 'N/A')}\n\n"
                f"Research workflow completed successfully!\n\n"
                f"Results:\n"
                f"- {document_count} documents found and scored\n"
                f"- {citation_count} citations extracted\n"
                f"- Preliminary report generated (~{word_count} words)\n\n"
                "Check the tabs:\n"
                "- 'Citations' tab - Extracted citations\n"
                "- 'Preliminary' tab - Generated report\n\n"
                "Next milestone will add counterfactual analysis."
            )

    # ========================================================================
    # Workflow Thread Signal Handlers
    # ========================================================================

    def _connect_workflow_thread_signals(self: 'ResearchTabWidget') -> None:
        """Connect workflow thread signals to UI handlers."""
        if not self.workflow_thread:
            return

        # Progress signals
        self.workflow_thread.step_started.connect(self._on_thread_step_started)
        self.workflow_thread.step_progress.connect(self._on_thread_step_progress)
        self.workflow_thread.step_completed.connect(self._on_thread_step_completed)
        self.workflow_thread.status_message.connect(self._on_workflow_status)

        # Result signals (reuse existing handlers)
        self.workflow_thread.query_generated.connect(self._on_query_generated)
        self.workflow_thread.documents_found.connect(self._on_documents_found)
        self.workflow_thread.documents_scored.connect(self._on_documents_scored)
        self.workflow_thread.citations_extracted.connect(self._on_citations_extracted)
        self.workflow_thread.preliminary_report_generated.connect(self._on_preliminary_report_generated)

        # Progressive display signals (per-item updates)
        self.workflow_thread.document_scored.connect(self._on_document_scored)
        self.workflow_thread.citation_progress.connect(self._on_citation_progress)
        self.workflow_thread.citation_extracted.connect(self._on_citation_extracted)

        # Counterfactual analysis signals
        self.workflow_thread.counterfactual_analysis_complete.connect(self._on_counterfactual_analysis_complete)
        self.workflow_thread.final_report_generated.connect(self._on_final_report_generated)

        # Completion signals
        self.workflow_thread.workflow_completed.connect(self._on_thread_workflow_completed)
        self.workflow_thread.workflow_error.connect(self._on_thread_workflow_error)
        self.workflow_thread.workflow_cancelled.connect(self._on_thread_workflow_cancelled)

        # Thread finished signal for cleanup
        self.workflow_thread.finished.connect(self._on_thread_finished)

        self.logger.info("Workflow thread signals connected")

    @Slot(str, str)
    def _on_thread_step_started(self: 'ResearchTabWidget', step_name: str, description: str) -> None:
        """Handle workflow step started signal."""
        self.logger.info(f"Step started: {step_name} - {description}")
        self.progress_label.setText(f"{description}")

        # Update status label based on major steps
        step_lower = step_name.lower()
        if 'query' in step_lower:
            self.status_label.setText("Generating query")
        elif 'search' in step_lower:
            self.status_label.setText("Searching documents")
        elif 'scor' in step_lower:
            self.status_label.setText("Scoring documents")
        elif 'citation' in step_lower:
            self.status_label.setText("Extracting citations")
        elif 'report' in step_lower:
            self.status_label.setText("Generating report")
        elif 'counterfactual' in step_lower:
            self.status_label.setText("Analyzing evidence")

    @Slot(str, int, int)
    def _on_thread_step_progress(self: 'ResearchTabWidget', step_name: str, current: int, total: int) -> None:
        """Handle workflow step progress signal."""
        if total > 0:
            percentage = int((current / total) * 100)
            self.progress_label.setText(f"Processing {current}/{total} documents... ({percentage}%)")

    @Slot(str)
    def _on_thread_step_completed(self: 'ResearchTabWidget', step_name: str) -> None:
        """Handle workflow step completed signal."""
        self.logger.info(f"Step completed: {step_name}")

    @Slot(dict)
    def _on_thread_workflow_completed(self: 'ResearchTabWidget', results: dict) -> None:
        """Handle workflow completed signal from thread."""
        self.logger.info(f"Thread workflow completed: {results.get('status', 'unknown')}")

        # Update UI state
        self.workflow_running = False

        # Show Start button, hide Cancel button
        self.start_button.setVisible(True)
        self.start_button.setEnabled(True)
        self.cancel_button.setVisible(False)

        # Update status bar
        doc_count = results.get('document_count', 0)
        citation_count = results.get('citation_count', 0)
        self.progress_label.setText(
            f"Found {doc_count} documents, extracted {citation_count} citations"
        )
        self.status_label.setText("Completed")

        # Store results
        self.current_results = results

        # Emit completion signal
        self.workflow_completed.emit(results)

    @Slot(Exception)
    def _on_thread_workflow_error(self: 'ResearchTabWidget', error: Exception) -> None:
        """Handle workflow error signal from thread."""
        self.logger.error(f"Thread workflow error: {error}", exc_info=True)

        # Update UI state
        self.workflow_running = False

        # Show Start button, hide Cancel button
        self.start_button.setVisible(True)
        self.start_button.setEnabled(True)
        self.cancel_button.setVisible(False)

        # Update status bar
        self.progress_label.setText("Workflow failed - see error message")
        self.status_label.setText("Error")

        # Emit error signal
        self.workflow_error.emit(error)

        # Show error dialog
        QMessageBox.critical(
            self,
            "Workflow Error",
            f"An error occurred during workflow execution:\n\n{str(error)}"
        )

    @Slot()
    def _on_thread_workflow_cancelled(self: 'ResearchTabWidget') -> None:
        """Handle workflow cancelled signal from thread."""
        self.logger.info("Workflow cancelled by user")

        # Update UI state
        self.workflow_running = False

        # Show Start button, hide Cancel button
        self.start_button.setVisible(True)
        self.start_button.setEnabled(True)
        self.cancel_button.setVisible(False)

        # Update status bar
        self.progress_label.setText("Workflow cancelled by user")
        self.status_label.setText("Cancelled")

        self.status_message.emit("Workflow cancelled by user")

    @Slot()
    def _on_thread_finished(self: 'ResearchTabWidget') -> None:
        """Handle thread finished signal for cleanup."""
        self.logger.info("Workflow thread finished")
        if self.workflow_thread:
            self.workflow_thread.deleteLater()
            self.workflow_thread = None

    # ========================================================================
    # Step-Specific Signal Handlers
    # ========================================================================

    @Slot(str)
    def _on_query_generated(self: 'ResearchTabWidget', query: str) -> None:
        """
        Handle query generated signal.

        Updates the Search tab to display the generated query.

        Args:
            query: The generated PostgreSQL tsquery string
        """
        self.logger.info(f"Query generated: {query}")

        # Update the query display in the Search tab
        if hasattr(self, 'search_refs') and 'query_text_display' in self.search_refs.widgets:
            self.search_refs.widgets['query_text_display'].setPlainText(query)

        self.status_message.emit(f"Query generated: {query[:50]}...")

    @Slot(list)
    def _on_documents_found(self: 'ResearchTabWidget', documents: list) -> None:
        """
        Handle documents found signal.

        Updates the Search tab to display the document count and populates
        the Literature tab with document cards (without scores).

        Args:
            documents: List of document dictionaries
        """
        from .tab_updaters import populate_unscored_documents

        doc_count = len(documents)
        self.logger.info(f"Documents found: {doc_count}")

        # Update the document count display in the Search tab
        if hasattr(self, 'search_refs') and 'document_count_label' in self.search_refs.widgets:
            label = self.search_refs.widgets['document_count_label']
            label.setText(f"Found {doc_count} documents matching your query")
            label.setStyleSheet(f"color: {self.ui.COLOR_PRIMARY_BLUE};")

        # Populate Literature tab with unscored documents
        if hasattr(self, 'literature_refs') and 'layout' in self.literature_refs.widgets:
            populate_unscored_documents(
                self.literature_refs.widgets['layout'],
                documents,
                self.document_card_factory,
                self.ui,
                self.logger
            )

        self.status_message.emit(f"Found {doc_count} documents")

    @Slot(int, int)
    def _on_scoring_progress(self: 'ResearchTabWidget', current: int, total: int) -> None:
        """
        Handle scoring progress signal.

        Updates the progress bar in the Scoring tab.

        Args:
            current: Current document number being scored
            total: Total number of documents to score
        """
        if hasattr(self, 'scoring_refs') and self.scoring_refs and 'progress_bar' in self.scoring_refs.widgets:
            progress_bar = self.scoring_refs.widgets['progress_bar']
            # Show progress bar if it's hidden
            if not progress_bar.isVisible():
                progress_bar.setVisible(True)

            # Update progress
            progress_bar.setMaximum(total)
            progress_bar.setValue(current)

            # Update summary label with live count
            if 'summary_label' in self.scoring_refs.widgets:
                self.scoring_refs.widgets['summary_label'].setText(
                    f"Scoring document {current}/{total}..."
                )

    @Slot(list)
    def _on_documents_scored(self: 'ResearchTabWidget', scored_documents: list) -> None:
        """
        Handle documents scored signal (scoring complete).

        Hides progress bar and updates final summary in the Scoring tab.
        Note: The Literature tab is left as-is (showing search results).
        Scoring results are displayed progressively in the Scoring tab via _on_document_scored.

        Args:
            scored_documents: List of (document, score_result) tuples
        """
        self.logger.info(f"Documents scored: {len(scored_documents)}")

        # Hide progress bar in Scoring tab
        if hasattr(self, 'scoring_refs') and self.scoring_refs and 'progress_bar' in self.scoring_refs.widgets:
            self.scoring_refs.widgets['progress_bar'].setVisible(False)

        # Update summary label in Scoring tab with final count
        total = len(scored_documents)
        # Type-safe score extraction with validation
        high_scoring = len([
            d for d, s in scored_documents
            if isinstance(s.get('score'), (int, float)) and s.get('score', 0) >= self.ui.SCORE_THRESHOLD_RELEVANT
        ])

        if hasattr(self, 'scoring_refs') and self.scoring_refs and 'summary_label' in self.scoring_refs.widgets:
            self.scoring_refs.widgets['summary_label'].setText(
                f"{total} documents scored | {high_scoring} highly relevant (score >= {self.ui.SCORE_THRESHOLD_RELEVANT})"
            )

        self.status_message.emit(f"Scored {total} documents ({high_scoring} highly relevant)")

    @Slot(list)
    def _on_citations_extracted(self: 'ResearchTabWidget', citations: list) -> None:
        """
        Handle citations extracted signal (extraction complete).

        Hides progress bar and updates final summary in the Citations tab.
        Note: Citation cards are added progressively via _on_citation_extracted.

        Args:
            citations: List of citation dictionaries
        """
        self.logger.info(f"Citations extracted: {len(citations)}")

        # Hide progress bar in Citations tab
        if hasattr(self, 'citations_refs') and self.citations_refs and 'progress_bar' in self.citations_refs.widgets:
            self.citations_refs.widgets['progress_bar'].setVisible(False)

        # Update summary label with final count
        if hasattr(self, 'citations_refs') and self.citations_refs and 'summary_label' in self.citations_refs.widgets:
            self.citations_refs.widgets['summary_label'].setText(
                f"{len(citations)} citations extracted from high-scoring documents"
            )

        self.status_message.emit(f"Extracted {len(citations)} citations")

    # ========================================================================
    # Progressive Display Signal Handlers
    # ========================================================================

    @Slot(object, object, int, int)
    def _on_document_scored(
        self: 'ResearchTabWidget',
        doc: dict,
        score_result: dict,
        current: int,
        total: int
    ) -> None:
        """
        Handle per-document scoring signal for progressive display.

        Adds a scored document card to the Scoring tab as each document is scored.

        Args:
            doc: Document dictionary
            score_result: Scoring result dictionary with 'score' and 'reasoning'
            current: Current document number (1-indexed)
            total: Total number of documents being scored
        """
        from .tab_updaters import add_single_scored_document

        if not hasattr(self, 'scoring_refs') or not self.scoring_refs:
            return

        if 'layout' not in self.scoring_refs.widgets:
            return

        try:
            add_single_scored_document(
                layout=self.scoring_refs.widgets['layout'],
                doc=doc,
                score_result=score_result,
                index=current,
                card_factory=self.document_card_factory,
                ui=self.ui,
                logger=self.logger,
                empty_label=self.scoring_refs.widgets.get('empty_label')
            )
        except Exception as e:
            self.logger.error(f"Error adding scored document card: {e}", exc_info=True)

    @Slot(int, int)
    def _on_citation_progress(self: 'ResearchTabWidget', current: int, total: int) -> None:
        """
        Handle citation extraction progress signal.

        Updates the progress bar in the Citations tab.

        Args:
            current: Current document number being processed
            total: Total number of documents to extract citations from
        """
        if not hasattr(self, 'citations_refs') or not self.citations_refs:
            return

        if 'progress_bar' not in self.citations_refs.widgets:
            return

        progress_bar = self.citations_refs.widgets['progress_bar']

        # Show progress bar if hidden
        if not progress_bar.isVisible():
            progress_bar.setVisible(True)

        # Update progress
        progress_bar.setMaximum(total)
        progress_bar.setValue(current)

        # Update summary label with live count
        if 'summary_label' in self.citations_refs.widgets:
            self.citations_refs.widgets['summary_label'].setText(
                f"Extracting citations from document {current}/{total}..."
            )

    @Slot(object, int, int)
    def _on_citation_extracted(
        self: 'ResearchTabWidget',
        citation: dict,
        current: int,
        total: int
    ) -> None:
        """
        Handle per-citation extraction signal for progressive display.

        Adds a citation card to the Citations tab as each citation is extracted.

        Args:
            citation: Citation dictionary
            current: Current citation number (1-indexed)
            total: Total number of documents being processed
        """
        from .tab_updaters import add_single_citation

        if not hasattr(self, 'citations_refs') or not self.citations_refs:
            return

        if 'layout' not in self.citations_refs.widgets:
            return

        try:
            add_single_citation(
                layout=self.citations_refs.widgets['layout'],
                citation=citation,
                index=current,
                ui=self.ui,
                logger=self.logger,
                card_factory=self.document_card_factory,
                empty_label=self.citations_refs.widgets.get('empty_label')
            )
        except Exception as e:
            self.logger.error(f"Error adding citation card: {e}", exc_info=True)

    @Slot(str)
    def _on_preliminary_report_generated(self: 'ResearchTabWidget', report: str) -> None:
        """
        Handle preliminary report generated signal.

        Updates the Preliminary Report tab to display the generated report.

        Args:
            report: Markdown-formatted preliminary report
        """
        self.logger.info(f"Preliminary report generated ({len(report)} characters)")

        # Update the Preliminary Report tab with markdown
        if hasattr(self, 'preliminary_refs') and 'report_viewer' in self.preliminary_refs.widgets:
            self.preliminary_refs.widgets['report_viewer'].set_markdown(report)

        # Update summary label (word count approximation)
        word_count = len(report.split())
        if hasattr(self, 'preliminary_refs') and 'summary_label' in self.preliminary_refs.widgets:
            self.preliminary_refs.widgets['summary_label'].setText(
                f"Report generated | ~{word_count} words | {len(report)} characters"
            )

        self.status_message.emit(f"Generated preliminary report ({word_count} words)")

    @Slot(dict)
    def _on_counterfactual_analysis_complete(self: 'ResearchTabWidget', results: dict) -> None:
        """
        Handle counterfactual analysis complete signal.

        Updates the Counterfactual tab with analysis results.

        Args:
            results: Dictionary with counterfactual analysis results
        """
        from .tab_updaters import update_counterfactual_tab

        self.logger.info(f"Counterfactual analysis complete: {results.get('question_count', 0)} questions")

        # Store results for later display
        self.counterfactual_results = results

        # Update status
        question_count = results.get('question_count', 0)
        doc_count = results.get('document_count', 0)
        self.status_message.emit(
            f"Counterfactual analysis: {question_count} questions, {doc_count} contradictory documents"
        )

        # Update Counterfactual tab
        if hasattr(self, 'counterfactual_refs'):
            update_counterfactual_tab(
                self.counterfactual_refs.widgets.get('content_layout'),
                self.counterfactual_refs.widgets.get('summary_label'),
                results,
                self.document_card_factory,
                self.ui,
                self.logger
            )

    @Slot(str)
    def _on_final_report_generated(self: 'ResearchTabWidget', report: str) -> None:
        """
        Handle final comprehensive report generated signal.

        Updates the Report tab with the comprehensive balanced report.

        Args:
            report: Markdown-formatted comprehensive report
        """
        self.logger.info(f"Final report generated ({len(report)} characters)")

        # Store the final report for export
        self.final_report_markdown = report

        # Update the Report tab with markdown
        if hasattr(self, 'report_refs') and 'report_viewer' in self.report_refs.widgets:
            self.report_refs.widgets['report_viewer'].set_markdown(report)

        # Update summary label (word count approximation)
        word_count = len(report.split())
        if hasattr(self, 'report_refs') and 'summary_label' in self.report_refs.widgets:
            self.report_refs.widgets['summary_label'].setText(
                f"Comprehensive report generated | ~{word_count} words | {len(report)} characters"
            )

        # Enable export buttons
        if hasattr(self, 'report_refs'):
            if 'save_markdown_button' in self.report_refs.widgets:
                self.report_refs.widgets['save_markdown_button'].setEnabled(True)
            if 'export_json_button' in self.report_refs.widgets:
                self.report_refs.widgets['export_json_button'].setEnabled(True)

        self.status_message.emit(f"Generated comprehensive final report ({word_count} words)")
