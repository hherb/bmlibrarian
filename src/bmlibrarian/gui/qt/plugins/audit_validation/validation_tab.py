"""
Main Validation Tab Widget for Audit Trail Validation GUI.

Provides a tabbed interface for browsing and validating audit trail items
organized by workflow step type (queries, scores, citations, reports, counterfactuals).
"""

import logging
from datetime import datetime
from typing import Optional, List, Callable

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QSplitter, QListWidget, QListWidgetItem, QLabel,
    QScrollArea, QFrame, QPushButton, QComboBox,
    QTextEdit, QGroupBox, QCheckBox, QSpinBox,
    QButtonGroup, QRadioButton, QMessageBox
)

from bmlibrarian.audit import (
    TargetType, ValidationStatus, Severity, ValidationCategory
)
from bmlibrarian.database import get_document_details
from bmlibrarian.gui.qt.resources.styles.stylesheet_generator import StylesheetGenerator
from bmlibrarian.gui.qt.resources.styles.dpi_scale import get_font_scale
from bmlibrarian.gui.qt.widgets.document_view_widget import DocumentViewWidget, DocumentViewData

from .data_manager import (
    AuditValidationDataManager,
    ResearchQuestionSummary,
    QueryAuditItem,
    ScoreAuditItem,
    CitationAuditItem,
    ReportAuditItem,
    CounterfactualAuditItem
)

logger = logging.getLogger(__name__)

# UI Constants - avoiding magic numbers
SPLITTER_LEFT_RATIO = 30  # Percentage for left panel
SPLITTER_RIGHT_RATIO = 70  # Percentage for right panel
REVIEW_TIMER_INTERVAL_MS = 1000  # Timer update interval in milliseconds
MAX_DISPLAY_TEXT_LENGTH = 50  # Max chars for list item text preview


class ValidationTabWidget(QWidget):
    """
    Main widget for the audit trail validation interface.

    Provides:
    - Research question selector
    - Sub-tabs for each workflow step type
    - Validation controls with status, comment, and categories
    - Statistics summary
    """

    # Signals
    validation_saved = Signal(str, int, str)  # target_type, target_id, status
    status_message = Signal(str)

    def __init__(
        self,
        data_manager: AuditValidationDataManager,
        reviewer_id: Optional[int] = None,
        reviewer_name: str = "Anonymous",
        parent: Optional[QWidget] = None
    ):
        """
        Initialize the validation tab widget.

        Args:
            data_manager: Data manager for loading/saving audit data
            reviewer_id: ID of the current reviewer (optional)
            reviewer_name: Name of the current reviewer
            parent: Parent widget
        """
        super().__init__(parent)
        self.data_manager = data_manager
        self.reviewer_id = reviewer_id
        self.reviewer_name = reviewer_name
        self.current_question_id: Optional[int] = None
        self.current_item: Optional[object] = None
        self.review_start_time: Optional[datetime] = None

        # Styling
        self.scale = get_font_scale()
        self.stylesheet_gen = StylesheetGenerator(self.scale)

        self._setup_ui()
        self._load_research_questions()

    def _setup_ui(self) -> None:
        """Set up the main UI layout."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(
            self.scale['padding_medium'],
            self.scale['padding_medium'],
            self.scale['padding_medium'],
            self.scale['padding_medium']
        )

        # Top bar with question selector and filters
        top_bar = self._create_top_bar()
        main_layout.addWidget(top_bar)

        # Main content area with splitter
        splitter = QSplitter(Qt.Horizontal)

        # Left: Item list
        left_panel = self._create_item_list_panel()
        splitter.addWidget(left_panel)

        # Right: Item detail and validation controls
        right_panel = self._create_detail_panel()
        splitter.addWidget(right_panel)

        # Connect tab change signal AFTER detail panel is created
        # (detail panel creates category_combo which is accessed in _on_tab_changed)
        self.item_tabs.currentChanged.connect(self._on_tab_changed)

        # Set initial splitter sizes using ratios (30% list, 70% detail)
        total_width = self.scale.get('control_width_xlarge', 1000)
        left_size = (total_width * SPLITTER_LEFT_RATIO) // 100
        right_size = (total_width * SPLITTER_RIGHT_RATIO) // 100
        splitter.setSizes([left_size, right_size])
        main_layout.addWidget(splitter, 1)

    def _create_top_bar(self) -> QWidget:
        """Create the top bar with question selector and filters."""
        top_bar = QWidget()
        layout = QHBoxLayout(top_bar)
        layout.setContentsMargins(0, 0, 0, self.scale['spacing_medium'])

        # Research question selector
        layout.addWidget(QLabel("Research Question:"))
        self.question_combo = QComboBox()
        self.question_combo.setMinimumWidth(self.scale['control_width_xlarge'])
        self.question_combo.currentIndexChanged.connect(self._on_question_selected)
        layout.addWidget(self.question_combo, 1)

        # Include validated checkbox
        self.include_validated_checkbox = QCheckBox("Show validated items")
        self.include_validated_checkbox.setChecked(True)
        self.include_validated_checkbox.stateChanged.connect(self._refresh_current_tab)
        layout.addWidget(self.include_validated_checkbox)

        # Refresh button
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._load_research_questions)
        refresh_btn.setStyleSheet(self.stylesheet_gen.button_stylesheet(
            bg_color="#757575", hover_color="#616161"
        ))
        layout.addWidget(refresh_btn)

        return top_bar

    def _create_item_list_panel(self) -> QWidget:
        """Create the left panel with item list and type tabs."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        # Tab widget for different item types
        self.item_tabs = QTabWidget()
        # Note: currentChanged signal is connected later in _setup_ui()
        # after detail panel is created, to avoid accessing uninitialized widgets

        # Create tabs for each target type
        self.query_list = QListWidget()
        self.query_list.currentItemChanged.connect(self._on_item_selected)
        self.item_tabs.addTab(self.query_list, "Queries")

        self.score_list = QListWidget()
        self.score_list.currentItemChanged.connect(self._on_item_selected)
        self.item_tabs.addTab(self.score_list, "Scores")

        self.citation_list = QListWidget()
        self.citation_list.currentItemChanged.connect(self._on_item_selected)
        self.item_tabs.addTab(self.citation_list, "Citations")

        self.report_list = QListWidget()
        self.report_list.currentItemChanged.connect(self._on_item_selected)
        self.item_tabs.addTab(self.report_list, "Reports")

        self.counterfactual_list = QListWidget()
        self.counterfactual_list.currentItemChanged.connect(self._on_item_selected)
        self.item_tabs.addTab(self.counterfactual_list, "Counterfactuals")

        layout.addWidget(self.item_tabs)

        # Progress label
        self.progress_label = QLabel("Select a research question")
        self.progress_label.setStyleSheet(self.stylesheet_gen.label_stylesheet(
            font_size_key='font_small', color="#666"
        ))
        layout.addWidget(self.progress_label)

        return panel

    def _create_detail_panel(self) -> QWidget:
        """Create the right panel with item details and validation controls."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        # Placeholder shown when no item selected
        self.placeholder_label = QLabel("Select an item to view details")
        self.placeholder_label.setAlignment(Qt.AlignCenter)
        self.placeholder_label.setStyleSheet(self.stylesheet_gen.label_stylesheet(
            font_size_key='font_medium', color="#999"
        ))
        layout.addWidget(self.placeholder_label)

        # Main detail container (hidden until item selected)
        self.detail_container = QWidget()
        detail_container_layout = QVBoxLayout(self.detail_container)
        detail_container_layout.setContentsMargins(0, 0, 0, 0)
        detail_container_layout.setSpacing(self.scale['spacing_small'])

        # Audit item info section (collapsible header with key info)
        self.audit_info_group = QGroupBox("Audit Item Info")
        self.audit_info_group.setStyleSheet(self.stylesheet_gen.custom("""
            QGroupBox {{
                font-size: {font_small}pt;
                font-weight: bold;
                border: 1px solid #CCC;
                border-radius: {radius_small}px;
                margin-top: {spacing_small}px;
                padding: {padding_small}px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: {padding_small}px;
            }}
        """))
        audit_info_layout = QVBoxLayout(self.audit_info_group)
        audit_info_layout.setContentsMargins(
            self.scale['padding_small'], self.scale['padding_small'],
            self.scale['padding_small'], self.scale['padding_small']
        )

        # Labels for audit item fields (reused, not recreated)
        self.audit_header_label = QLabel()
        self.audit_header_label.setStyleSheet(self.stylesheet_gen.label_stylesheet(
            font_size_key='font_medium', bold=True
        ))
        audit_info_layout.addWidget(self.audit_header_label)

        self.audit_details_label = QLabel()
        self.audit_details_label.setWordWrap(True)
        self.audit_details_label.setStyleSheet(self.stylesheet_gen.label_stylesheet(
            font_size_key='font_small'
        ))
        audit_info_layout.addWidget(self.audit_details_label)

        # AI reasoning section (shown for scores/citations)
        self.reasoning_label = QLabel()
        self.reasoning_label.setWordWrap(True)
        self.reasoning_label.setStyleSheet(self.stylesheet_gen.label_stylesheet(
            font_size_key='font_small', color="#666"
        ))
        self.reasoning_label.hide()
        audit_info_layout.addWidget(self.reasoning_label)

        detail_container_layout.addWidget(self.audit_info_group)

        # Document viewer widget (with tabs for Metadata, PDF, Full Text)
        self.document_viewer = DocumentViewWidget()
        detail_container_layout.addWidget(self.document_viewer, 1)

        self.detail_container.hide()
        layout.addWidget(self.detail_container, 1)

        # Validation controls panel
        validation_panel = self._create_validation_controls()
        layout.addWidget(validation_panel)

        return panel

    def _create_validation_controls(self) -> QWidget:
        """Create the validation controls panel."""
        group = QGroupBox("Validation")
        group.setStyleSheet(self.stylesheet_gen.custom("""
            QGroupBox {{
                font-size: {font_medium}pt;
                font-weight: bold;
                border: 1px solid #CCC;
                border-radius: {radius_small}px;
                margin-top: {spacing_medium}px;
                padding-top: {padding_medium}px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: {padding_medium}px;
            }}
        """))

        layout = QVBoxLayout(group)

        # Validation status radio buttons
        status_layout = QHBoxLayout()
        status_layout.addWidget(QLabel("Status:"))

        self.status_group = QButtonGroup(self)
        self.status_buttons = {}

        for status in ValidationStatus:
            rb = QRadioButton(status.value.replace('_', ' ').title())
            self.status_group.addButton(rb)
            self.status_buttons[status] = rb
            status_layout.addWidget(rb)

        self.status_buttons[ValidationStatus.VALIDATED].setChecked(True)
        status_layout.addStretch()
        layout.addLayout(status_layout)

        # Severity (only for incorrect)
        severity_layout = QHBoxLayout()
        severity_layout.addWidget(QLabel("Severity:"))

        self.severity_combo = QComboBox()
        self.severity_combo.addItem("-- Select --", None)
        for sev in Severity:
            self.severity_combo.addItem(sev.value.title(), sev)
        self.severity_combo.setEnabled(False)
        severity_layout.addWidget(self.severity_combo)

        # Categories (only for incorrect)
        severity_layout.addWidget(QLabel("Category:"))
        self.category_combo = QComboBox()
        self.category_combo.addItem("-- Select --", None)
        self.category_combo.setEnabled(False)
        severity_layout.addWidget(self.category_combo, 1)

        layout.addLayout(severity_layout)

        # Connect status change to enable/disable severity/category
        self.status_group.buttonClicked.connect(self._on_status_changed)

        # Comment field
        comment_label = QLabel("Comment:")
        layout.addWidget(comment_label)

        self.comment_edit = QTextEdit()
        self.comment_edit.setMaximumHeight(self.scale['control_height_xlarge'] * 2)
        self.comment_edit.setPlaceholderText("Enter validation comment...")
        self.comment_edit.setStyleSheet(self.stylesheet_gen.text_edit_stylesheet())
        layout.addWidget(self.comment_edit)

        # Suggested correction (optional)
        correction_label = QLabel("Suggested Correction (optional):")
        layout.addWidget(correction_label)

        self.correction_edit = QTextEdit()
        self.correction_edit.setMaximumHeight(self.scale['control_height_xlarge'])
        self.correction_edit.setPlaceholderText("What should the correct value be?")
        self.correction_edit.setStyleSheet(self.stylesheet_gen.text_edit_stylesheet())
        layout.addWidget(self.correction_edit)

        # Action buttons
        button_layout = QHBoxLayout()

        self.save_btn = QPushButton("Save Validation")
        self.save_btn.setStyleSheet(self.stylesheet_gen.button_stylesheet(
            bg_color="#4CAF50", hover_color="#388E3C"
        ))
        self.save_btn.clicked.connect(self._save_validation)
        self.save_btn.setEnabled(False)
        button_layout.addWidget(self.save_btn)

        self.skip_btn = QPushButton("Skip")
        self.skip_btn.setStyleSheet(self.stylesheet_gen.button_stylesheet(
            bg_color="#757575", hover_color="#616161"
        ))
        self.skip_btn.clicked.connect(self._skip_to_next)
        self.skip_btn.setEnabled(False)
        button_layout.addWidget(self.skip_btn)

        button_layout.addStretch()

        # Timer display
        self.timer_label = QLabel("Time: 0:00")
        self.timer_label.setStyleSheet(self.stylesheet_gen.label_stylesheet(
            font_size_key='font_small', color="#666"
        ))
        button_layout.addWidget(self.timer_label)

        layout.addLayout(button_layout)

        # Timer for tracking review time
        self.review_timer = QTimer(self)
        self.review_timer.timeout.connect(self._update_timer_display)

        return group

    def _load_research_questions(self) -> None:
        """Load research questions into the combo box."""
        self.question_combo.clear()
        self.question_combo.addItem("-- Select Research Question --", None)

        try:
            questions = self.data_manager.get_research_questions()
            for q in questions:
                # Show progress info in display text
                total_items = sum(
                    p.get('total', 0) for p in q.validation_progress.values()
                )
                validated_items = sum(
                    p.get('validated', 0) for p in q.validation_progress.values()
                )
                progress_text = f"[{validated_items}/{total_items}]" if total_items > 0 else ""

                display_text = f"{q.question_text[:80]}... {progress_text}" if len(q.question_text) > 80 else f"{q.question_text} {progress_text}"
                self.question_combo.addItem(display_text, q.research_question_id)

            self.status_message.emit(f"Loaded {len(questions)} research questions")
        except Exception as e:
            logger.error(f"Error loading research questions: {e}")
            QMessageBox.critical(self, "Error", f"Failed to load research questions:\n{e}")

    def _on_question_selected(self, index: int) -> None:
        """Handle research question selection."""
        question_id = self.question_combo.currentData()
        self.current_question_id = question_id

        if question_id is None:
            self._clear_all_lists()
            return

        # Load categories for the current context
        self._load_categories()

        # Load items for all tabs
        self._load_all_items()

    def _load_categories(self) -> None:
        """Load validation categories into the category combo."""
        self.category_combo.clear()
        self.category_combo.addItem("-- Select --", None)

        # Get current tab's target type
        target_type = self._get_current_target_type()
        if target_type:
            categories = self.data_manager.get_categories(target_type)
            for cat in categories:
                self.category_combo.addItem(cat.category_name, cat.category_id)

    def _get_current_target_type(self) -> Optional[TargetType]:
        """Get the target type for the current tab."""
        tab_index = self.item_tabs.currentIndex()
        type_map = {
            0: TargetType.QUERY,
            1: TargetType.SCORE,
            2: TargetType.CITATION,
            3: TargetType.REPORT,
            4: TargetType.COUNTERFACTUAL
        }
        return type_map.get(tab_index)

    def _load_all_items(self) -> None:
        """Load items for all tabs."""
        if self.current_question_id is None:
            return

        include_validated = self.include_validated_checkbox.isChecked()

        try:
            # Load queries
            queries = self.data_manager.get_queries_for_question(
                self.current_question_id, include_validated
            )
            self._populate_query_list(queries)

            # Load scores
            scores = self.data_manager.get_scores_for_question(
                self.current_question_id, include_validated
            )
            self._populate_score_list(scores)

            # Load citations
            citations = self.data_manager.get_citations_for_question(
                self.current_question_id, include_validated
            )
            self._populate_citation_list(citations)

            # Load reports
            reports = self.data_manager.get_reports_for_question(
                self.current_question_id, include_validated
            )
            self._populate_report_list(reports)

            # Load counterfactuals
            counterfactuals = self.data_manager.get_counterfactuals_for_question(
                self.current_question_id, include_validated
            )
            self._populate_counterfactual_list(counterfactuals)

            self._update_progress_label()

        except Exception as e:
            logger.error(f"Error loading items: {e}")
            QMessageBox.warning(self, "Warning", f"Error loading some items:\n{e}")

    def _populate_query_list(self, items: List[QueryAuditItem]) -> None:
        """Populate the query list."""
        self.query_list.clear()
        for item in items:
            status_icon = self._get_validation_icon(item.validation)
            preview = item.query_text[:MAX_DISPLAY_TEXT_LENGTH]
            text = f"{status_icon} Query #{item.query_id}: {preview}..."
            list_item = QListWidgetItem(text)
            list_item.setData(Qt.UserRole, item)
            self.query_list.addItem(list_item)

    def _populate_score_list(self, items: List[ScoreAuditItem]) -> None:
        """Populate the score list."""
        self.score_list.clear()
        for item in items:
            status_icon = self._get_validation_icon(item.validation)
            title = (item.document_title or 'Untitled')[:MAX_DISPLAY_TEXT_LENGTH]
            text = f"{status_icon} Score {item.relevance_score}/5: {title}..."
            list_item = QListWidgetItem(text)
            list_item.setData(Qt.UserRole, item)
            self.score_list.addItem(list_item)

    def _populate_citation_list(self, items: List[CitationAuditItem]) -> None:
        """Populate the citation list."""
        self.citation_list.clear()
        for item in items:
            status_icon = self._get_validation_icon(item.validation)
            preview = item.summary[:MAX_DISPLAY_TEXT_LENGTH]
            text = f"{status_icon} {preview}..."
            list_item = QListWidgetItem(text)
            list_item.setData(Qt.UserRole, item)
            self.citation_list.addItem(list_item)

    def _populate_report_list(self, items: List[ReportAuditItem]) -> None:
        """Populate the report list."""
        self.report_list.clear()
        for item in items:
            status_icon = self._get_validation_icon(item.validation)
            final_mark = "[FINAL] " if item.is_final else ""
            text = f"{status_icon} {final_mark}{item.report_type.title()} ({item.citation_count or 0} citations)"
            list_item = QListWidgetItem(text)
            list_item.setData(Qt.UserRole, item)
            self.report_list.addItem(list_item)

    def _populate_counterfactual_list(self, items: List[CounterfactualAuditItem]) -> None:
        """Populate the counterfactual list."""
        self.counterfactual_list.clear()
        for item in items:
            status_icon = self._get_validation_icon(item.validation)
            priority = f"[{item.priority.upper()}] " if item.priority else ""
            preview = item.question_text[:MAX_DISPLAY_TEXT_LENGTH]
            text = f"{status_icon} {priority}{preview}..."
            list_item = QListWidgetItem(text)
            list_item.setData(Qt.UserRole, item)
            self.counterfactual_list.addItem(list_item)

    def _get_validation_icon(self, validation) -> str:
        """Get icon for validation status."""
        if validation is None:
            return "[ ]"
        status_icons = {
            ValidationStatus.VALIDATED: "[+]",
            ValidationStatus.INCORRECT: "[X]",
            ValidationStatus.UNCERTAIN: "[?]",
            ValidationStatus.NEEDS_REVIEW: "[!]"
        }
        return status_icons.get(validation.validation_status, "[ ]")

    def _clear_all_lists(self) -> None:
        """Clear all item lists."""
        self.query_list.clear()
        self.score_list.clear()
        self.citation_list.clear()
        self.report_list.clear()
        self.counterfactual_list.clear()
        self.progress_label.setText("Select a research question")

    def _on_tab_changed(self, index: int) -> None:
        """Handle tab change."""
        self._load_categories()
        self._clear_detail_display()

    def _refresh_current_tab(self) -> None:
        """Refresh the current tab's item list."""
        self._load_all_items()

    def _on_item_selected(self, current: QListWidgetItem, previous: QListWidgetItem) -> None:
        """Handle item selection in any list."""
        if current is None:
            self._clear_detail_display()
            return

        item = current.data(Qt.UserRole)
        self.current_item = item

        # Start review timer
        self.review_start_time = datetime.now()
        self.review_timer.start(REVIEW_TIMER_INTERVAL_MS)

        # Display item details
        self._display_item_details(item)

        # Enable validation controls
        self.save_btn.setEnabled(True)
        self.skip_btn.setEnabled(True)

        # Pre-fill validation if exists
        if hasattr(item, 'validation') and item.validation:
            self._prefill_validation(item.validation)
        else:
            self._reset_validation_controls()

    def _display_item_details(self, item: object) -> None:
        """Display details for the selected item."""
        # Show the detail container, hide placeholder
        self.placeholder_label.hide()
        self.detail_container.show()

        # Display audit item info based on type
        if isinstance(item, QueryAuditItem):
            self._display_query_details(item)
        elif isinstance(item, ScoreAuditItem):
            self._display_score_details(item)
        elif isinstance(item, CitationAuditItem):
            self._display_citation_details(item)
        elif isinstance(item, ReportAuditItem):
            self._display_report_details(item)
        elif isinstance(item, CounterfactualAuditItem):
            self._display_counterfactual_details(item)

    def _load_document_into_viewer(self, document_id: int) -> None:
        """Load a document into the document viewer widget."""
        try:
            doc_data = get_document_details(document_id)
            if doc_data:
                view_data = DocumentViewData(
                    document_id=doc_data.get('id'),
                    title=doc_data.get('title', ''),
                    authors=doc_data.get('authors'),
                    journal=doc_data.get('journal'),
                    year=doc_data.get('year'),
                    pmid=doc_data.get('pmid'),
                    doi=doc_data.get('doi'),
                    abstract=doc_data.get('abstract'),
                    full_text=doc_data.get('full_text'),
                    pdf_path=doc_data.get('pdf_filename'),
                    pdf_url=doc_data.get('pdf_url'),
                    publication_date=doc_data.get('publication_date')
                )
                self.document_viewer.set_document(view_data)
                self.document_viewer.show()
            else:
                self.document_viewer.hide()
                logger.warning(f"Document {document_id} not found")
        except Exception as e:
            logger.error(f"Error loading document {document_id}: {e}")
            self.document_viewer.hide()

    def _display_query_details(self, item: QueryAuditItem) -> None:
        """Display query audit item details."""
        self.audit_header_label.setText(f"Generated Query #{item.query_id}")

        details = []
        if item.evaluator_name:
            details.append(f"Evaluator: {item.evaluator_name}")
        details.append(f"Human Edited: {'Yes' if item.human_edited else 'No'}")
        details.append(f"Documents Found: {item.documents_found_count or 0}")
        details.append(f"Created: {item.created_at.strftime('%Y-%m-%d %H:%M')}")
        details.append(f"\nGenerated Query:\n{item.query_text}")

        if item.human_edited and item.original_ai_query:
            details.append(f"\nOriginal AI Query:\n{item.original_ai_query}")

        self.audit_details_label.setText("\n".join(details))
        self.reasoning_label.hide()

        # No document for queries
        self.document_viewer.hide()

    def _display_score_details(self, item: ScoreAuditItem) -> None:
        """Display score audit item details."""
        self.audit_header_label.setText(f"Document Score #{item.scoring_id}")

        details = [
            f"Relevance Score: {item.relevance_score}/5",
            f"Evaluator: {item.evaluator_name}",
            f"Scored At: {item.scored_at.strftime('%Y-%m-%d %H:%M')}"
        ]
        self.audit_details_label.setText("\n".join(details))

        # Show AI reasoning if available
        if item.reasoning:
            self.reasoning_label.setText(f"AI Reasoning: {item.reasoning}")
            self.reasoning_label.show()
        else:
            self.reasoning_label.hide()

        # Load document into viewer
        if item.document_id:
            self._load_document_into_viewer(item.document_id)
        else:
            self.document_viewer.hide()

    def _display_citation_details(self, item: CitationAuditItem) -> None:
        """Display citation audit item details."""
        self.audit_header_label.setText(f"Extracted Citation #{item.citation_id}")

        details = [f"Evaluator: {item.evaluator_name}"]
        if item.relevance_confidence:
            details.append(f"Confidence: {item.relevance_confidence:.2f}")
        if item.human_review_status:
            details.append(f"Review Status: {item.human_review_status}")
        details.append(f"Extracted At: {item.extracted_at.strftime('%Y-%m-%d %H:%M')}")
        details.append(f"\nExtracted Passage:\n{item.passage}")
        details.append(f"\nAI Summary:\n{item.summary}")

        self.audit_details_label.setText("\n".join(details))
        self.reasoning_label.hide()

        # Load source document into viewer
        if item.document_id:
            self._load_document_into_viewer(item.document_id)
        else:
            self.document_viewer.hide()

    def _display_report_details(self, item: ReportAuditItem) -> None:
        """Display report audit item details."""
        self.audit_header_label.setText(f"Generated Report #{item.report_id}")

        details = [
            f"Report Type: {item.report_type.title()}",
        ]
        if item.evaluator_name:
            details.append(f"Evaluator: {item.evaluator_name}")
        details.extend([
            f"Citations: {item.citation_count or 0}",
            f"Human Edited: {'Yes' if item.human_edited else 'No'}",
            f"Final Version: {'Yes' if item.is_final else 'No'}",
            f"Generated At: {item.generated_at.strftime('%Y-%m-%d %H:%M')}",
            f"\nReport Content:\n{item.report_text}"
        ])

        self.audit_details_label.setText("\n".join(details))
        self.reasoning_label.hide()

        # No document for reports
        self.document_viewer.hide()

    def _display_counterfactual_details(self, item: CounterfactualAuditItem) -> None:
        """Display counterfactual question details."""
        self.audit_header_label.setText(f"Counterfactual Question #{item.question_id}")

        details = []
        if item.priority:
            details.append(f"Priority: {item.priority.upper()}")
        if item.documents_found_count is not None:
            details.append(f"Documents Found: {item.documents_found_count}")
        details.append(f"\nQuestion:\n{item.question_text}")

        if item.target_claim:
            details.append(f"\nTarget Claim:\n{item.target_claim}")
        if item.query_generated:
            details.append(f"\nGenerated Query:\n{item.query_generated}")

        self.audit_details_label.setText("\n".join(details))
        self.reasoning_label.hide()

        # No document for counterfactuals
        self.document_viewer.hide()

    def _clear_detail_display(self) -> None:
        """Clear the detail display area."""
        # Hide detail container, show placeholder
        self.detail_container.hide()
        self.placeholder_label.show()

        # Clear the labels
        self.audit_header_label.setText("")
        self.audit_details_label.setText("")
        self.reasoning_label.setText("")
        self.reasoning_label.hide()

        self.current_item = None
        self.save_btn.setEnabled(False)
        self.skip_btn.setEnabled(False)
        self.review_timer.stop()

    def _prefill_validation(self, validation) -> None:
        """Pre-fill validation controls with existing validation."""
        # Set status
        if validation.validation_status in self.status_buttons:
            self.status_buttons[validation.validation_status].setChecked(True)
            self._on_status_changed()

        # Set severity
        if validation.severity:
            index = self.severity_combo.findData(validation.severity)
            if index >= 0:
                self.severity_combo.setCurrentIndex(index)

        # Set comment
        if validation.comment:
            self.comment_edit.setPlainText(validation.comment)

        # Set correction
        if validation.suggested_correction:
            self.correction_edit.setPlainText(validation.suggested_correction)

    def _reset_validation_controls(self) -> None:
        """Reset validation controls to defaults."""
        self.status_buttons[ValidationStatus.VALIDATED].setChecked(True)
        self.severity_combo.setCurrentIndex(0)
        self.category_combo.setCurrentIndex(0)
        self.comment_edit.clear()
        self.correction_edit.clear()
        self._on_status_changed()

    def _on_status_changed(self) -> None:
        """Handle validation status change."""
        # Find selected status
        is_incorrect = self.status_buttons[ValidationStatus.INCORRECT].isChecked()

        # Enable/disable severity and category for incorrect items
        self.severity_combo.setEnabled(is_incorrect)
        self.category_combo.setEnabled(is_incorrect)

    def _update_timer_display(self) -> None:
        """Update the review timer display."""
        if self.review_start_time:
            elapsed = datetime.now() - self.review_start_time
            minutes = int(elapsed.total_seconds() // 60)
            seconds = int(elapsed.total_seconds() % 60)
            self.timer_label.setText(f"Time: {minutes}:{seconds:02d}")

    def _update_progress_label(self) -> None:
        """Update the progress label with validation counts."""
        if self.current_question_id is None:
            return

        try:
            counts = self.data_manager.validation_tracker.get_unvalidated_counts(
                self.current_question_id
            )
            total = sum(c.total_count for c in counts)
            validated = sum(c.validated_count for c in counts)
            self.progress_label.setText(f"Progress: {validated}/{total} items validated")
        except Exception as e:
            logger.error(f"Error updating progress: {e}")

    def _save_validation(self) -> None:
        """Save the current validation."""
        if self.current_item is None or self.current_question_id is None:
            return

        # Get selected status
        selected_status = None
        for status, button in self.status_buttons.items():
            if button.isChecked():
                selected_status = status
                break

        if selected_status is None:
            QMessageBox.warning(self, "Warning", "Please select a validation status.")
            return

        # Get target type and ID
        target_type, target_id = self._get_item_target_info(self.current_item)
        if target_type is None:
            return

        # Get severity and category
        severity = self.severity_combo.currentData()
        category_id = self.category_combo.currentData()
        category_ids = [category_id] if category_id else None

        # Calculate time spent
        time_spent = None
        if self.review_start_time:
            time_spent = int((datetime.now() - self.review_start_time).total_seconds())

        try:
            self.data_manager.record_validation(
                research_question_id=self.current_question_id,
                target_type=target_type,
                target_id=target_id,
                validation_status=selected_status,
                reviewer_id=self.reviewer_id,
                reviewer_name=self.reviewer_name,
                comment=self.comment_edit.toPlainText() or None,
                suggested_correction=self.correction_edit.toPlainText() or None,
                severity=severity,
                time_spent_seconds=time_spent,
                category_ids=category_ids
            )

            self.status_message.emit(f"Validation saved for {target_type.value} #{target_id}")
            self.validation_saved.emit(target_type.value, target_id, selected_status.value)

            # Move to next item
            self._move_to_next_item()

        except Exception as e:
            logger.error(f"Error saving validation: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save validation:\n{e}")

    def _get_item_target_info(self, item: object) -> tuple:
        """Get target type and ID for an item."""
        if isinstance(item, QueryAuditItem):
            return TargetType.QUERY, item.query_id
        elif isinstance(item, ScoreAuditItem):
            return TargetType.SCORE, item.scoring_id
        elif isinstance(item, CitationAuditItem):
            return TargetType.CITATION, item.citation_id
        elif isinstance(item, ReportAuditItem):
            return TargetType.REPORT, item.report_id
        elif isinstance(item, CounterfactualAuditItem):
            return TargetType.COUNTERFACTUAL, item.question_id
        return None, None

    def _skip_to_next(self) -> None:
        """Skip to the next item without saving."""
        self._move_to_next_item()

    def _move_to_next_item(self) -> None:
        """Move to the next item in the current list."""
        # Get current list widget
        current_list = self._get_current_list_widget()
        if current_list is None:
            return

        # Get current row
        current_row = current_list.currentRow()
        if current_row < current_list.count() - 1:
            current_list.setCurrentRow(current_row + 1)
        else:
            # Refresh list to remove validated items (if filter is active)
            if not self.include_validated_checkbox.isChecked():
                self._refresh_current_tab()
                if current_list.count() > 0:
                    current_list.setCurrentRow(0)
                else:
                    self._clear_detail_display()

        # Reset timer
        self.review_start_time = datetime.now()
        self._reset_validation_controls()

        # Update progress
        self._update_progress_label()

    def _get_current_list_widget(self) -> Optional[QListWidget]:
        """Get the currently active list widget."""
        tab_index = self.item_tabs.currentIndex()
        list_map = {
            0: self.query_list,
            1: self.score_list,
            2: self.citation_list,
            3: self.report_list,
            4: self.counterfactual_list
        }
        return list_map.get(tab_index)
