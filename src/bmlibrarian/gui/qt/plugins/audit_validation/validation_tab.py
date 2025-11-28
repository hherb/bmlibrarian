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
from bmlibrarian.gui.qt.resources.styles.stylesheet_generator import StylesheetGenerator
from bmlibrarian.gui.qt.resources.styles.dpi_scale import get_font_scale

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

        # Set initial splitter sizes (30% list, 70% detail)
        splitter.setSizes([300, 700])
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
        self.item_tabs.currentChanged.connect(self._on_tab_changed)

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

        # Item detail area (scrollable)
        detail_scroll = QScrollArea()
        detail_scroll.setWidgetResizable(True)
        detail_scroll.setFrameShape(QFrame.NoFrame)

        self.detail_widget = QWidget()
        self.detail_layout = QVBoxLayout(self.detail_widget)
        self.detail_layout.setContentsMargins(
            self.scale['padding_small'], 0, self.scale['padding_small'], 0
        )

        # Placeholder for item details
        self.detail_content = QLabel("Select an item to view details")
        self.detail_content.setAlignment(Qt.AlignCenter)
        self.detail_content.setStyleSheet(self.stylesheet_gen.label_stylesheet(
            font_size_key='font_medium', color="#999"
        ))
        self.detail_layout.addWidget(self.detail_content)
        self.detail_layout.addStretch()

        detail_scroll.setWidget(self.detail_widget)
        layout.addWidget(detail_scroll, 1)

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
            text = f"{status_icon} Query #{item.query_id}: {item.query_text[:50]}..."
            list_item = QListWidgetItem(text)
            list_item.setData(Qt.UserRole, item)
            self.query_list.addItem(list_item)

    def _populate_score_list(self, items: List[ScoreAuditItem]) -> None:
        """Populate the score list."""
        self.score_list.clear()
        for item in items:
            status_icon = self._get_validation_icon(item.validation)
            title = (item.document_title or 'Untitled')[:40]
            text = f"{status_icon} Score {item.relevance_score}/5: {title}..."
            list_item = QListWidgetItem(text)
            list_item.setData(Qt.UserRole, item)
            self.score_list.addItem(list_item)

    def _populate_citation_list(self, items: List[CitationAuditItem]) -> None:
        """Populate the citation list."""
        self.citation_list.clear()
        for item in items:
            status_icon = self._get_validation_icon(item.validation)
            text = f"{status_icon} {item.summary[:50]}..."
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
            text = f"{status_icon} {priority}{item.question_text[:50]}..."
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
        self.review_timer.start(1000)

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
        # Clear existing content
        while self.detail_layout.count() > 0:
            child = self.detail_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # Create detail content based on item type
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

        self.detail_layout.addStretch()

    def _display_query_details(self, item: QueryAuditItem) -> None:
        """Display query audit item details."""
        self._add_detail_header(f"Generated Query #{item.query_id}")

        if item.evaluator_name:
            self._add_detail_field("Evaluator", item.evaluator_name)

        self._add_detail_field("Human Edited", "Yes" if item.human_edited else "No")
        self._add_detail_field("Documents Found", str(item.documents_found_count or 0))
        self._add_detail_field("Created", item.created_at.strftime("%Y-%m-%d %H:%M"))

        self._add_detail_section("Generated Query")
        self._add_detail_text(item.query_text)

        if item.human_edited and item.original_ai_query:
            self._add_detail_section("Original AI Query")
            self._add_detail_text(item.original_ai_query)

    def _display_score_details(self, item: ScoreAuditItem) -> None:
        """Display score audit item details."""
        self._add_detail_header(f"Document Score #{item.scoring_id}")

        self._add_detail_field("Relevance Score", f"{item.relevance_score}/5")
        self._add_detail_field("Evaluator", item.evaluator_name)
        self._add_detail_field("Scored At", item.scored_at.strftime("%Y-%m-%d %H:%M"))

        if item.document_title:
            self._add_detail_section("Document")
            self._add_detail_field("Title", item.document_title)
            if item.document_authors:
                self._add_detail_field("Authors", item.document_authors[:100])
            if item.document_year:
                self._add_detail_field("Year", str(item.document_year))

        if item.reasoning:
            self._add_detail_section("AI Reasoning")
            self._add_detail_text(item.reasoning)

        if item.document_abstract:
            self._add_detail_section("Abstract")
            self._add_detail_text(item.document_abstract)

    def _display_citation_details(self, item: CitationAuditItem) -> None:
        """Display citation audit item details."""
        self._add_detail_header(f"Extracted Citation #{item.citation_id}")

        self._add_detail_field("Evaluator", item.evaluator_name)
        if item.relevance_confidence:
            self._add_detail_field("Confidence", f"{item.relevance_confidence:.2f}")
        if item.human_review_status:
            self._add_detail_field("Review Status", item.human_review_status)
        self._add_detail_field("Extracted At", item.extracted_at.strftime("%Y-%m-%d %H:%M"))

        if item.document_title:
            self._add_detail_section("Source Document")
            self._add_detail_field("Title", item.document_title)
            if item.document_authors:
                self._add_detail_field("Authors", item.document_authors[:100])

        self._add_detail_section("Extracted Passage")
        self._add_detail_text(item.passage)

        self._add_detail_section("AI Summary")
        self._add_detail_text(item.summary)

    def _display_report_details(self, item: ReportAuditItem) -> None:
        """Display report audit item details."""
        self._add_detail_header(f"Generated Report #{item.report_id}")

        self._add_detail_field("Report Type", item.report_type.title())
        if item.evaluator_name:
            self._add_detail_field("Evaluator", item.evaluator_name)
        self._add_detail_field("Citations", str(item.citation_count or 0))
        self._add_detail_field("Human Edited", "Yes" if item.human_edited else "No")
        self._add_detail_field("Final Version", "Yes" if item.is_final else "No")
        self._add_detail_field("Generated At", item.generated_at.strftime("%Y-%m-%d %H:%M"))

        self._add_detail_section("Report Content")
        self._add_detail_text(item.report_text[:2000] + "..." if len(item.report_text) > 2000 else item.report_text)

    def _display_counterfactual_details(self, item: CounterfactualAuditItem) -> None:
        """Display counterfactual question details."""
        self._add_detail_header(f"Counterfactual Question #{item.question_id}")

        if item.priority:
            self._add_detail_field("Priority", item.priority.upper())
        if item.documents_found_count is not None:
            self._add_detail_field("Documents Found", str(item.documents_found_count))

        self._add_detail_section("Question")
        self._add_detail_text(item.question_text)

        if item.target_claim:
            self._add_detail_section("Target Claim")
            self._add_detail_text(item.target_claim)

        if item.query_generated:
            self._add_detail_section("Generated Query")
            self._add_detail_text(item.query_generated)

    def _add_detail_header(self, text: str) -> None:
        """Add a header to the detail display."""
        label = QLabel(text)
        label.setStyleSheet(self.stylesheet_gen.label_stylesheet(
            font_size_key='font_large', bold=True
        ))
        self.detail_layout.addWidget(label)

    def _add_detail_section(self, text: str) -> None:
        """Add a section header to the detail display."""
        label = QLabel(text)
        label.setStyleSheet(self.stylesheet_gen.label_stylesheet(
            font_size_key='font_medium', bold=True, color="#444"
        ))
        label.setContentsMargins(0, self.scale['spacing_medium'], 0, 0)
        self.detail_layout.addWidget(label)

    def _add_detail_field(self, name: str, value: str) -> None:
        """Add a field-value pair to the detail display."""
        layout = QHBoxLayout()
        name_label = QLabel(f"{name}:")
        name_label.setStyleSheet(self.stylesheet_gen.label_stylesheet(
            font_size_key='font_normal', bold=True
        ))
        name_label.setFixedWidth(self.scale['control_width_small'])
        layout.addWidget(name_label)

        value_label = QLabel(value)
        value_label.setStyleSheet(self.stylesheet_gen.label_stylesheet(
            font_size_key='font_normal'
        ))
        value_label.setWordWrap(True)
        layout.addWidget(value_label, 1)

        self.detail_layout.addLayout(layout)

    def _add_detail_text(self, text: str) -> None:
        """Add a text block to the detail display."""
        text_edit = QTextEdit()
        text_edit.setPlainText(text)
        text_edit.setReadOnly(True)
        text_edit.setMaximumHeight(self.scale['control_height_xlarge'] * 4)
        text_edit.setStyleSheet(self.stylesheet_gen.text_edit_stylesheet(
            bg_color="#F5F5F5"
        ))
        self.detail_layout.addWidget(text_edit)

    def _clear_detail_display(self) -> None:
        """Clear the detail display area."""
        while self.detail_layout.count() > 0:
            child = self.detail_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        placeholder = QLabel("Select an item to view details")
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setStyleSheet(self.stylesheet_gen.label_stylesheet(
            font_size_key='font_medium', color="#999"
        ))
        self.detail_layout.addWidget(placeholder)
        self.detail_layout.addStretch()

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
