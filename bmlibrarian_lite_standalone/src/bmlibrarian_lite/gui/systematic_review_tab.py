"""
Systematic Review tab for BMLibrarian Lite.

Provides a complete workflow for literature review:
1. Enter research question
2. Search PubMed
3. Score documents for relevance
4. Extract citations
5. Generate report

Citations in the report are clickable and open the document
in the Document Interrogation tab for detailed Q&A.

Reports are automatically saved to ~/bmlibrarian_reports/ with audit trail data.
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Any, Dict

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QTextBrowser,
    QPushButton,
    QLabel,
    QProgressBar,
    QGroupBox,
    QSpinBox,
    QFileDialog,
    QMessageBox,
)
from PySide6.QtCore import Signal, QThread, QUrl

from bmlibrarian_lite.resources.styles.dpi_scale import scaled

from ..config import LiteConfig
from ..storage import LiteStorage
from ..data_models import LiteDocument, ScoredDocument, Citation
from ..agents import (
    LiteSearchAgent,
    LiteScoringAgent,
    LiteCitationAgent,
    LiteReportingAgent,
)
from ..quality import QualityManager, QualityFilter, QualityAssessment

from .quality_filter_panel import QualityFilterPanel
from .quality_summary import QualitySummaryWidget
from .workers import QualityFilterWorker

# Directory for auto-saved reports
REPORTS_DIR = Path.home() / "bmlibrarian_reports"

logger = logging.getLogger(__name__)


class WorkflowWorker(QThread):
    """
    Background worker for systematic review workflow.

    Executes the full workflow in a background thread:
    1. Search PubMed
    2. Quality filter (optional)
    3. Score documents
    4. Extract citations
    5. Generate report

    Signals:
        progress: Emitted during progress (step, current, total)
        step_complete: Emitted when a step completes (step name, result)
        error: Emitted on error (step, error message)
        finished: Emitted when workflow completes (final report)
    """

    progress = Signal(str, int, int)  # step, current, total
    step_complete = Signal(str, object)  # step name, result
    error = Signal(str, str)  # step, error message
    finished = Signal(str)  # final report

    def __init__(
        self,
        question: str,
        config: LiteConfig,
        storage: LiteStorage,
        max_results: int = 100,
        min_score: int = 3,
        quality_filter: Optional[QualityFilter] = None,
        quality_manager: Optional[QualityManager] = None,
    ) -> None:
        """
        Initialize the workflow worker.

        Args:
            question: Research question
            config: Lite configuration
            storage: Storage layer
            max_results: Maximum PubMed results to fetch
            min_score: Minimum relevance score (1-5)
            quality_filter: Optional quality filter settings
            quality_manager: Optional quality manager for filtering
        """
        super().__init__()
        self.question = question
        self.config = config
        self.storage = storage
        self.max_results = max_results
        self.min_score = min_score
        self.quality_filter = quality_filter
        self.quality_manager = quality_manager
        self._cancelled = False

    def run(self) -> None:
        """Execute the systematic review workflow."""
        try:
            # Step 1: Search PubMed
            self.progress.emit("search", 0, 1)
            search_agent = LiteSearchAgent(
                config=self.config,
                storage=self.storage,
            )
            session, documents = search_agent.search(
                self.question,
                max_results=self.max_results,
            )
            self.step_complete.emit("search", documents)

            if self._cancelled:
                self.finished.emit("Workflow cancelled.")
                return

            if not documents:
                self.finished.emit("No documents found for this query.")
                return

            # Step 2: Quality filtering (if enabled)
            if self.quality_filter and self.quality_manager:
                # Only apply quality filter if minimum tier is set
                if self.quality_filter.minimum_tier.value > 0:
                    self.progress.emit("quality_filter", 0, len(documents))

                    def quality_progress(
                        current: int,
                        total: int,
                        assessment: QualityAssessment,
                    ) -> None:
                        self.progress.emit("quality_filter", current, total)

                    filtered, assessments = self.quality_manager.filter_documents(
                        documents,
                        self.quality_filter,
                        progress_callback=quality_progress,
                    )
                    self.step_complete.emit("quality_filter", (filtered, assessments))

                    if self._cancelled:
                        self.finished.emit("Workflow cancelled.")
                        return

                    if not filtered:
                        self.finished.emit(
                            f"No documents passed quality filter. "
                            f"{len(documents)} documents were assessed but none met "
                            f"the minimum quality requirements."
                        )
                        return

                    # Use filtered documents for scoring
                    documents = filtered

            # Step 3: Score documents
            scoring_agent = LiteScoringAgent(config=self.config)
            scored_docs = scoring_agent.score_documents(
                self.question,
                documents,
                min_score=self.min_score,
                progress_callback=lambda c, t: self.progress.emit("scoring", c, t),
            )
            self.step_complete.emit("scoring", scored_docs)

            if self._cancelled:
                self.finished.emit("Workflow cancelled.")
                return

            if not scored_docs:
                self.finished.emit(
                    f"No documents scored {self.min_score} or higher. "
                    "Try lowering the minimum score threshold."
                )
                return

            # Step 3: Extract citations
            citation_agent = LiteCitationAgent(config=self.config)
            citations = citation_agent.extract_all_citations(
                self.question,
                scored_docs,
                min_score=self.min_score,
                progress_callback=lambda c, t: self.progress.emit("citations", c, t),
            )
            self.step_complete.emit("citations", citations)

            if self._cancelled:
                self.finished.emit("Workflow cancelled.")
                return

            # Step 4: Generate report
            self.progress.emit("report", 0, 1)
            reporting_agent = LiteReportingAgent(config=self.config)
            report = reporting_agent.generate_report(self.question, citations)
            self.step_complete.emit("report", report)

            self.finished.emit(report)

        except Exception as e:
            logger.exception("Workflow error")
            self.error.emit("workflow", str(e))

    def cancel(self) -> None:
        """Cancel the workflow."""
        self._cancelled = True


class SystematicReviewTab(QWidget):
    """
    Systematic Review tab widget.

    Provides interface for:
    - Entering research question
    - Configuring search parameters
    - Executing search and scoring workflow
    - Viewing generated report with clickable citations
    - Exporting report with full audit trail

    Attributes:
        config: Lite configuration
        storage: Storage layer

    Signals:
        document_requested: Emitted when user clicks a citation (document_id)
    """

    # Emitted when user clicks a citation link in the report
    document_requested = Signal(str)  # document_id

    def __init__(
        self,
        config: LiteConfig,
        storage: LiteStorage,
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Initialize the systematic review tab.

        Args:
            config: Lite configuration
            storage: Storage layer
            parent: Optional parent widget
        """
        super().__init__(parent)
        self.config = config
        self.storage = storage
        self._worker: Optional[WorkflowWorker] = None
        self._quality_worker: Optional[QualityFilterWorker] = None
        self._current_report: str = ""
        self._current_question: str = ""

        # Quality manager for document assessment
        self.quality_manager = QualityManager(config)

        # Store citations by document ID for later access
        self._citations_by_doc_id: Dict[str, Citation] = {}

        # Audit trail data - stored during workflow execution
        self._documents_found: List[LiteDocument] = []
        self._scored_documents: List[ScoredDocument] = []
        self._all_citations: List[Citation] = []
        self._quality_assessments: Dict[str, QualityAssessment] = {}
        self._current_report_path: Optional[Path] = None

        # Ensure reports directory exists
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        layout.setSpacing(scaled(8))

        # Question input section
        question_group = QGroupBox("Research Question")
        question_layout = QVBoxLayout(question_group)

        self.question_input = QTextEdit()
        self.question_input.setPlaceholderText(
            "Enter your research question...\n\n"
            "Example: What are the cardiovascular benefits of regular exercise "
            "in adults over 50?"
        )
        self.question_input.setMaximumHeight(scaled(100))
        question_layout.addWidget(self.question_input)

        # Options row
        options_layout = QHBoxLayout()

        options_layout.addWidget(QLabel("Max results:"))
        self.max_results_spin = QSpinBox()
        self.max_results_spin.setRange(10, 500)
        self.max_results_spin.setValue(100)
        self.max_results_spin.setToolTip("Maximum number of PubMed articles to retrieve")
        options_layout.addWidget(self.max_results_spin)

        options_layout.addSpacing(scaled(16))

        options_layout.addWidget(QLabel("Min score:"))
        self.min_score_spin = QSpinBox()
        self.min_score_spin.setRange(1, 5)
        self.min_score_spin.setValue(3)
        self.min_score_spin.setToolTip(
            "Minimum relevance score (1-5) to include in report"
        )
        options_layout.addWidget(self.min_score_spin)

        options_layout.addStretch()

        self.run_btn = QPushButton("Run Review")
        self.run_btn.clicked.connect(self._run_workflow)
        self.run_btn.setToolTip("Start the systematic review workflow")
        options_layout.addWidget(self.run_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self._cancel_workflow)
        self.cancel_btn.setEnabled(False)
        options_layout.addWidget(self.cancel_btn)

        question_layout.addLayout(options_layout)
        layout.addWidget(question_group)

        # Quality filter panel (collapsible)
        self.quality_filter_panel = QualityFilterPanel()
        self.quality_filter_panel.filterChanged.connect(self._on_quality_filter_changed)
        layout.addWidget(self.quality_filter_panel)

        # Quality summary widget (shows tier distribution after filtering)
        self.quality_summary = QualitySummaryWidget()
        self.quality_summary.setVisible(False)  # Hidden until filtering complete
        layout.addWidget(self.quality_summary)

        # Progress section
        progress_group = QGroupBox("Progress")
        progress_layout = QVBoxLayout(progress_group)

        self.progress_label = QLabel("Ready")
        progress_layout.addWidget(self.progress_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)

        layout.addWidget(progress_group)

        # Results section
        results_group = QGroupBox("Report")
        results_layout = QVBoxLayout(results_group)

        # Use QTextBrowser for clickable links
        self.report_view = QTextBrowser()
        self.report_view.setReadOnly(True)
        self.report_view.setOpenExternalLinks(False)  # Handle links ourselves
        self.report_view.setOpenLinks(False)  # Prevent navigation that clears content
        self.report_view.anchorClicked.connect(self._on_citation_clicked)
        self.report_view.setPlaceholderText(
            "Report will appear here after running the review...\n\n"
            "The workflow will:\n"
            "1. Search PubMed for relevant articles\n"
            "2. Score each document for relevance\n"
            "3. Extract key passages as citations\n"
            "4. Generate a comprehensive report\n\n"
            "Click on any citation to open the document for detailed Q&A."
        )
        results_layout.addWidget(self.report_view)

        # Button row
        button_layout = QHBoxLayout()

        # Load Report button
        self.load_btn = QPushButton("Load Report")
        self.load_btn.clicked.connect(self._load_report)
        self.load_btn.setToolTip("Load a previously saved report")
        button_layout.addWidget(self.load_btn)

        # Audit Trail button
        self.audit_btn = QPushButton("Audit Trail")
        self.audit_btn.setEnabled(False)
        self.audit_btn.clicked.connect(self._show_audit_trail)
        self.audit_btn.setToolTip(
            "View which documents were found, scored, and used for citations"
        )
        button_layout.addWidget(self.audit_btn)

        button_layout.addStretch()

        self.export_btn = QPushButton("Export Report")
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self._export_report)
        self.export_btn.setToolTip("Save report to file")
        button_layout.addWidget(self.export_btn)

        results_layout.addLayout(button_layout)
        layout.addWidget(results_group, stretch=1)

    def _run_workflow(self) -> None:
        """Start the systematic review workflow."""
        question = self.question_input.toPlainText().strip()
        if not question:
            self.progress_label.setText("Please enter a research question")
            return

        # Store question for audit trail
        self._current_question = question

        # Clear previous audit data
        self._documents_found = []
        self._scored_documents = []
        self._all_citations = []
        self._quality_assessments = {}
        self._current_report_path = None
        self.quality_summary.setVisible(False)

        # Update UI state
        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.export_btn.setEnabled(False)
        self.audit_btn.setEnabled(False)
        self.report_view.clear()
        self.progress_bar.setValue(0)
        self._current_report = ""

        # Get quality filter settings
        quality_filter = self.quality_filter_panel.get_filter()

        # Create and start worker
        self._worker = WorkflowWorker(
            question=question,
            config=self.config,
            storage=self.storage,
            max_results=self.max_results_spin.value(),
            min_score=self.min_score_spin.value(),
            quality_filter=quality_filter,
            quality_manager=self.quality_manager,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.step_complete.connect(self._on_step_complete)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _cancel_workflow(self) -> None:
        """Cancel the running workflow."""
        if self._worker:
            self._worker.cancel()
            self.progress_label.setText("Cancelling...")
        if self._quality_worker:
            self._quality_worker.cancel()

    def _on_quality_filter_changed(self, filter_settings: QualityFilter) -> None:
        """
        Handle quality filter settings change.

        This is called when user modifies filter settings in the panel.
        Settings are applied when the workflow runs.

        Args:
            filter_settings: New quality filter settings
        """
        logger.debug(f"Quality filter changed: {filter_settings}")
        # Settings will be used when workflow runs - no immediate action needed

    def _on_progress(self, step: str, current: int, total: int) -> None:
        """Handle progress updates from worker."""
        step_names = {
            "search": "Searching PubMed",
            "quality_filter": "Assessing quality",
            "scoring": "Scoring documents",
            "citations": "Extracting citations",
            "report": "Generating report",
        }
        name = step_names.get(step, step)
        self.progress_label.setText(f"{name}: {current}/{total}")

        if total > 0:
            self.progress_bar.setValue(int(current / total * 100))

    def _on_step_complete(self, step: str, result: Any) -> None:
        """Handle step completion from worker."""
        if step == "search":
            docs: List[LiteDocument] = result
            self._documents_found = docs
            self.progress_label.setText(f"Found {len(docs)} documents")
            # Quality filtering happens after search in the workflow worker
            # Results are stored for later display
        elif step == "quality_filter":
            # Handle quality filtering results
            filtered_docs, assessments = result
            self._store_quality_assessments(assessments)
            self.progress_label.setText(
                f"Quality filter: {len(filtered_docs)}/{len(assessments)} passed"
            )
            # Show quality summary
            self._show_quality_summary(assessments)
        elif step == "scoring":
            scored: List[ScoredDocument] = result
            self._scored_documents = scored
            self.progress_label.setText(f"Scored {len(scored)} relevant documents")
        elif step == "citations":
            citations: List[Citation] = result
            self._all_citations = citations
            self.progress_label.setText(f"Extracted {len(citations)} citations")
            # Store citations by document ID for later retrieval
            self._citations_by_doc_id.clear()
            for citation in citations:
                doc_id = citation.document.id
                self._citations_by_doc_id[doc_id] = citation

    def _on_error(self, step: str, message: str) -> None:
        """Handle workflow errors."""
        self.progress_label.setText(f"Error in {step}: {message}")
        self.report_view.setPlainText(f"Error during {step}:\n\n{message}")
        self._reset_ui()

    def _on_finished(self, report: str) -> None:
        """Handle workflow completion."""
        self._current_report = report

        # Convert markdown to HTML with clickable citations
        html_report = self._make_citations_clickable(report)
        self.report_view.setHtml(html_report)

        self.progress_label.setText("Complete - Click citations to view documents")
        self.progress_bar.setValue(100)
        self.export_btn.setEnabled(bool(report))
        self.audit_btn.setEnabled(bool(self._scored_documents))
        self._reset_ui()

        # Auto-save the report with audit trail
        if report and not report.startswith(("No documents", "Workflow cancelled")):
            self._auto_save_report()

    def _make_citations_clickable(self, markdown_report: str) -> str:
        """
        Convert markdown report to HTML with clickable citation links.

        Handles two citation formats:
        1. New format: [Author et al., 2023](docid:pmid-12345) - document ID in link
        2. Legacy format: [Author et al., 2023] - uses fuzzy matching (fallback)

        Args:
            markdown_report: Original markdown report

        Returns:
            HTML with clickable citation links
        """
        import markdown

        # Step 1: Convert docid: links to bmlibrarian:// links BEFORE markdown processing
        # Pattern matches: [Author et al., 2023](docid:pmid-12345)
        docid_pattern = r'\[([^\]]+)\]\(docid:([^)]+)\)'

        def replace_docid_link(match: re.Match) -> str:
            citation_text = match.group(1)
            doc_id = match.group(2)
            # Validate doc_id exists in our citations
            if doc_id in self._citations_by_doc_id:
                return f'[{citation_text}](bmlibrarian://doc/{doc_id})'
            # Fallback: keep as plain text if doc_id not found
            logger.warning(f"Document ID '{doc_id}' not found in citations")
            return f'[{citation_text}]'

        processed_markdown = re.sub(docid_pattern, replace_docid_link, markdown_report)

        # Step 2: Convert markdown to HTML
        md = markdown.Markdown(extensions=['extra', 'nl2br', 'sane_lists'])
        html = md.convert(processed_markdown)

        # Step 3: Handle legacy citations that don't have docid links (fallback)
        # Pattern matches: [Author et al., 2023] or [Smith J, 2022] that aren't already links
        # This regex looks for brackets NOT followed by ( which would indicate a link
        legacy_pattern = r'\[([A-Za-z][^,\[\]]+(?:,\s*\d{4})?)\](?!\()'

        def replace_legacy_citation(match: re.Match) -> str:
            citation_text = match.group(1)
            # Try to find matching document using fuzzy matching
            doc_id = self._find_document_by_citation(citation_text)
            if doc_id:
                return f'<a href="bmlibrarian://doc/{doc_id}" style="color: #2196F3; text-decoration: underline; cursor: pointer;">[{citation_text}]</a>'
            return match.group(0)

        html = re.sub(legacy_pattern, replace_legacy_citation, html)

        # Wrap in basic HTML structure with styling
        styled_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
                    font-size: 14px;
                    line-height: 1.6;
                    color: #333;
                    padding: 8px;
                }}
                h1, h2, h3 {{ color: #1a1a1a; }}
                h1 {{ font-size: 1.5em; border-bottom: 1px solid #eee; padding-bottom: 0.3em; }}
                h2 {{ font-size: 1.3em; }}
                h3 {{ font-size: 1.1em; }}
                blockquote {{
                    border-left: 3px solid #2196F3;
                    padding-left: 1em;
                    margin-left: 0;
                    color: #555;
                    background-color: #f8f9fa;
                }}
                a {{
                    color: #2196F3;
                    text-decoration: none;
                }}
                a:hover {{
                    text-decoration: underline;
                }}
                ul, ol {{ padding-left: 1.5em; }}
                code {{
                    background-color: #f0f0f0;
                    padding: 2px 4px;
                    border-radius: 3px;
                }}
            </style>
        </head>
        <body>
        {html}
        </body>
        </html>
        """
        return styled_html

    def _find_document_by_citation(self, citation_text: str) -> Optional[str]:
        """
        Find document ID from citation text using fuzzy matching.

        This is a LEGACY FALLBACK method for reports that don't use the new
        docid: link format. Prefer using document IDs directly via the
        [Author, Year](docid:ID) format for reliable citation tracking.

        Tries to match citation text like "Smith et al., 2023" against
        stored citations by comparing author names and years.

        Args:
            citation_text: Citation text to match (e.g., "Smith et al., 2023")

        Returns:
            Document ID if found, None otherwise
        """
        citation_lower = citation_text.lower()

        for doc_id, citation in self._citations_by_doc_id.items():
            doc = citation.document
            # Check if citation matches author and year
            formatted_authors = doc.formatted_authors.lower()

            # Extract year from citation text
            year_match = re.search(r'(\d{4})', citation_text)
            citation_year = year_match.group(1) if year_match else None

            # Check if first author name appears in citation
            if doc.authors:
                first_author_last = doc.authors[0].split()[-1].lower()
                if first_author_last in citation_lower:
                    # Check year if present
                    if citation_year:
                        if doc.year and str(doc.year) == citation_year:
                            return doc_id
                    else:
                        return doc_id

            # Also try matching formatted author string
            if formatted_authors.split(',')[0] in citation_lower:
                if citation_year:
                    if doc.year and str(doc.year) == citation_year:
                        return doc_id
                else:
                    return doc_id

        return None

    def _on_citation_clicked(self, url: QUrl) -> None:
        """
        Handle citation link click.

        Args:
            url: Clicked URL (bmlibrarian://doc/{doc_id})
        """
        if url.scheme() == "bmlibrarian" and url.host() == "doc":
            doc_id = url.path().lstrip('/')
            logger.info(f"Citation clicked: {doc_id}")
            self.document_requested.emit(doc_id)
        elif url.scheme() in ("http", "https"):
            # Open external links in browser
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(url)

    def get_citation(self, doc_id: str) -> Optional[Citation]:
        """
        Get citation by document ID.

        Args:
            doc_id: Document ID

        Returns:
            Citation if found, None otherwise
        """
        return self._citations_by_doc_id.get(doc_id)

    def _reset_ui(self) -> None:
        """Reset UI to ready state."""
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self._worker = None
        self._quality_worker = None

    def _store_quality_assessments(
        self,
        assessments: List[QualityAssessment],
    ) -> None:
        """
        Store quality assessments by document ID for later access.

        Args:
            assessments: List of quality assessments
        """
        for assessment in assessments:
            if hasattr(assessment, 'document_id') and assessment.document_id:
                self._quality_assessments[assessment.document_id] = assessment

    def _show_quality_summary(self, assessments: List[QualityAssessment]) -> None:
        """
        Display quality assessment summary.

        Args:
            assessments: List of quality assessments to summarize
        """
        if not assessments:
            self.quality_summary.setVisible(False)
            return

        summary = self.quality_manager.get_assessment_summary(assessments)
        self.quality_summary.update_summary(summary)
        self.quality_summary.setVisible(True)

    def get_quality_assessment(self, doc_id: str) -> Optional[QualityAssessment]:
        """
        Get quality assessment for a document.

        Args:
            doc_id: Document ID

        Returns:
            QualityAssessment if found, None otherwise
        """
        return self._quality_assessments.get(doc_id)

    def _export_report(self) -> None:
        """Export the report to a file."""
        if not self._current_report:
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Report",
            "research_report.md",
            "Markdown (*.md);;Text (*.txt);;All Files (*)",
        )

        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(self._current_report)
                self.progress_label.setText(f"Report exported to {file_path}")
            except Exception as e:
                self.progress_label.setText(f"Export failed: {e}")

    def _auto_save_report(self) -> None:
        """
        Auto-save report with audit trail to ~/bmlibrarian_reports/.

        Creates two files:
        - {timestamp}_report.md: The markdown report
        - {timestamp}_audit.json: Full audit trail with documents, scores, citations
        """
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_question = re.sub(r'[^\w\s-]', '', self._current_question)[:50].strip()
            safe_question = re.sub(r'\s+', '_', safe_question)

            report_path = REPORTS_DIR / f"{timestamp}_{safe_question}_report.md"
            audit_path = REPORTS_DIR / f"{timestamp}_{safe_question}_audit.json"

            # Save the markdown report
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(self._current_report)

            # Get quality filter settings for audit
            quality_filter_settings = self.quality_filter_panel.get_filter()

            # Build audit trail
            audit_data = {
                "metadata": {
                    "timestamp": datetime.now().isoformat(),
                    "research_question": self._current_question,
                    "report_file": str(report_path),
                },
                "workflow_summary": {
                    "documents_searched": len(self._documents_found),
                    "documents_scored_relevant": len(self._scored_documents),
                    "documents_rejected": len(self._documents_found) - len(self._scored_documents),
                    "citations_extracted": len(self._all_citations),
                    "quality_filter_applied": quality_filter_settings.minimum_tier.value > 0,
                    "quality_assessments_count": len(self._quality_assessments),
                },
                "quality_filter_settings": {
                    "minimum_tier": quality_filter_settings.minimum_tier.name,
                    "require_randomization": quality_filter_settings.require_randomization,
                    "require_blinding": quality_filter_settings.require_blinding,
                    "minimum_sample_size": quality_filter_settings.minimum_sample_size,
                    "use_metadata_only": quality_filter_settings.use_metadata_only,
                    "use_llm_classification": quality_filter_settings.use_llm_classification,
                    "use_detailed_assessment": quality_filter_settings.use_detailed_assessment,
                },
                "documents_found": [
                    {
                        "id": doc.id,
                        "title": doc.title,
                        "authors": doc.authors,
                        "year": doc.year,
                        "journal": doc.journal,
                        "pmid": doc.pmid,
                        "doi": doc.doi,
                        "quality_assessment": (
                            {
                                "study_design": self._quality_assessments[doc.id].study_design.value,
                                "quality_tier": self._quality_assessments[doc.id].quality_tier.name,
                                "quality_score": self._quality_assessments[doc.id].quality_score,
                                "confidence": self._quality_assessments[doc.id].confidence,
                                "assessment_tier": self._quality_assessments[doc.id].assessment_tier,
                            }
                            if doc.id in self._quality_assessments
                            else None
                        ),
                    }
                    for doc in self._documents_found
                ],
                "scored_documents": [
                    {
                        "id": sd.document.id,
                        "title": sd.document.title,
                        "score": sd.score,
                        "explanation": sd.explanation,
                        "is_relevant": sd.is_relevant,
                    }
                    for sd in self._scored_documents
                ],
                "rejected_documents": [
                    {
                        "id": doc.id,
                        "title": doc.title,
                        "reason": "Score below minimum threshold",
                    }
                    for doc in self._documents_found
                    if doc.id not in {sd.document.id for sd in self._scored_documents}
                ],
                "citations": [
                    {
                        "document_id": c.document.id,
                        "document_title": c.document.title,
                        "document_abstract": c.document.abstract,
                        "document_authors": c.document.authors,
                        "document_year": c.document.year,
                        "document_journal": c.document.journal,
                        "document_doi": c.document.doi,
                        "document_pmid": c.document.pmid,
                        "document_pmc_id": c.document.pmc_id,
                        "passage": c.passage,
                        "relevance_score": c.relevance_score,
                        "context": c.context,
                    }
                    for c in self._all_citations
                ],
            }

            with open(audit_path, "w", encoding="utf-8") as f:
                json.dump(audit_data, f, indent=2, ensure_ascii=False)

            self._current_report_path = report_path
            logger.info(f"Auto-saved report to {report_path}")

        except Exception as e:
            logger.warning(f"Failed to auto-save report: {e}")

    def _load_report(self) -> None:
        """Load a previously saved report with its audit trail."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Report",
            str(REPORTS_DIR),
            "Markdown (*.md);;All Files (*)",
        )

        if not file_path:
            return

        path = Path(file_path)
        if not path.exists():
            QMessageBox.warning(self, "File Not Found", f"File not found: {path}")
            return

        try:
            # Load the markdown report
            report = path.read_text(encoding="utf-8")
            self._current_report = report

            # Try to load the accompanying audit file
            audit_path = path.with_name(path.name.replace("_report.md", "_audit.json"))
            if audit_path.exists():
                with open(audit_path, "r", encoding="utf-8") as f:
                    audit_data = json.load(f)

                # Restore research question
                self._current_question = audit_data.get("metadata", {}).get(
                    "research_question", ""
                )
                self.question_input.setPlainText(self._current_question)

                # Restore citations for clickable links
                self._citations_by_doc_id.clear()
                for cit_data in audit_data.get("citations", []):
                    # Reconstruct LiteDocument with full metadata
                    doc = LiteDocument(
                        id=cit_data["document_id"],
                        title=cit_data["document_title"],
                        abstract=cit_data.get("document_abstract", ""),
                        authors=cit_data.get("document_authors", []),
                        year=cit_data.get("document_year"),
                        journal=cit_data.get("document_journal"),
                        doi=cit_data.get("document_doi"),
                        pmid=cit_data.get("document_pmid"),
                        pmc_id=cit_data.get("document_pmc_id"),
                    )
                    citation = Citation(
                        document=doc,
                        passage=cit_data["passage"],
                        relevance_score=cit_data["relevance_score"],
                        context=cit_data.get("context", ""),
                    )
                    self._citations_by_doc_id[doc.id] = citation

                # Enable audit button if we have audit data
                self.audit_btn.setEnabled(True)
                self._current_report_path = path

                # Store audit data for viewing
                self._loaded_audit_data = audit_data

                self.progress_label.setText(
                    f"Loaded report with {len(self._citations_by_doc_id)} citations"
                )
            else:
                self.progress_label.setText("Loaded report (no audit trail found)")

            # Display the report
            html_report = self._make_citations_clickable(report)
            self.report_view.setHtml(html_report)
            self.export_btn.setEnabled(True)

        except Exception as e:
            logger.exception("Failed to load report")
            QMessageBox.critical(self, "Load Error", f"Failed to load report:\n{e}")

    def _show_audit_trail(self) -> None:
        """Show the audit trail dialog with workflow details."""
        # Build audit content from current data or loaded data
        if hasattr(self, '_loaded_audit_data') and self._loaded_audit_data:
            audit_data = self._loaded_audit_data
        else:
            audit_data = {
                "metadata": {
                    "research_question": self._current_question,
                },
                "workflow_summary": {
                    "documents_searched": len(self._documents_found),
                    "documents_scored_relevant": len(self._scored_documents),
                    "documents_rejected": len(self._documents_found) - len(self._scored_documents),
                    "citations_extracted": len(self._all_citations),
                },
                "scored_documents": [
                    {
                        "id": sd.document.id,
                        "title": sd.document.title,
                        "score": sd.score,
                        "explanation": sd.explanation,
                    }
                    for sd in self._scored_documents
                ],
                "rejected_documents": [
                    {
                        "id": doc.id,
                        "title": doc.title,
                    }
                    for doc in self._documents_found
                    if doc.id not in {sd.document.id for sd in self._scored_documents}
                ],
                "citations": [
                    {
                        "document_title": c.document.title,
                        "passage": c.passage[:200] + "..." if len(c.passage) > 200 else c.passage,
                        "relevance_score": c.relevance_score,
                    }
                    for c in self._all_citations
                ],
            }

        # Create formatted markdown for the audit trail
        lines = [
            "# Audit Trail",
            "",
            f"**Research Question:** {audit_data['metadata']['research_question']}",
            "",
            "## Summary",
            "",
            f"- Documents searched: {audit_data['workflow_summary']['documents_searched']}",
            f"- Documents scored as relevant: {audit_data['workflow_summary']['documents_scored_relevant']}",
            f"- Documents rejected: {audit_data['workflow_summary']['documents_rejected']}",
            f"- Citations extracted: {audit_data['workflow_summary']['citations_extracted']}",
            "",
            "## Relevant Documents (with scores)",
            "",
        ]

        for sd in audit_data.get("scored_documents", []):
            lines.append(f"### {sd['title']}")
            lines.append(f"- **Score:** {sd['score']}/5")
            lines.append(f"- **ID:** {sd['id']}")
            if sd.get('explanation'):
                lines.append(f"- **Explanation:** {sd['explanation']}")
            lines.append("")

        lines.append("## Rejected Documents")
        lines.append("")

        rejected = audit_data.get("rejected_documents", [])
        if rejected:
            for rd in rejected[:20]:  # Limit to first 20
                lines.append(f"- {rd['title']}")
            if len(rejected) > 20:
                lines.append(f"- ... and {len(rejected) - 20} more")
        else:
            lines.append("*No documents were rejected*")

        lines.append("")
        lines.append("## Citations Extracted")
        lines.append("")

        for i, cit in enumerate(audit_data.get("citations", []), 1):
            lines.append(f"### Citation {i}: {cit['document_title']}")
            lines.append(f"> {cit['passage']}")
            lines.append("")

        audit_text = "\n".join(lines)

        # Show in a dialog
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QDialogButtonBox

        dialog = QDialog(self)
        dialog.setWindowTitle("Audit Trail")
        dialog.resize(scaled(600), scaled(500))

        layout = QVBoxLayout(dialog)

        audit_view = QTextBrowser()
        audit_view.setOpenExternalLinks(False)

        # Convert to HTML for nicer display
        import markdown as md
        html = md.markdown(audit_text, extensions=['extra', 'nl2br'])
        audit_view.setHtml(f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif;
                       font-size: 13px; line-height: 1.5; padding: 10px; }}
                h1 {{ color: #1a1a1a; font-size: 1.4em; border-bottom: 1px solid #eee; }}
                h2 {{ color: #333; font-size: 1.2em; }}
                h3 {{ color: #444; font-size: 1.05em; }}
                blockquote {{ border-left: 3px solid #2196F3; padding-left: 10px;
                             color: #555; background: #f9f9f9; margin: 5px 0; }}
                ul {{ padding-left: 20px; }}
            </style>
        </head>
        <body>{html}</body>
        </html>
        """)
        layout.addWidget(audit_view)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        dialog.exec()
