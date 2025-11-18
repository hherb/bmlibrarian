"""
Main Fact-Checker Review Tab Widget.

Coordinates all components for reviewing and annotating fact-check results.
"""

from typing import Optional, Dict, Any, List
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QMessageBox,
    QInputDialog,
    QFileDialog,
)
from PySide6.QtCore import Qt, Signal, Slot

from .statement_widget import StatementWidget
from .annotation_widget import AnnotationWidget
from .citation_widget import CitationListWidget
from .timer_widget import TimerWidget
from .navigation_widget import NavigationWidget

# Import fact-checker database components
from .....factchecker.db import get_fact_checker_db, Annotator, HumanAnnotation

# Import DPI-aware styling
from ...resources.styles import get_font_scale


class FactCheckerTabWidget(QWidget):
    """Main fact-checker review tab widget."""

    # Signals
    status_changed = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        """
        Initialize fact-checker tab.

        Args:
            parent: Optional parent widget
        """
        super().__init__(parent)

        # DPI-aware scaling
        self.scale = get_font_scale()

        # Configuration
        self.incremental = False
        self.blind_mode = False
        self.db_file: Optional[str] = None

        # Data
        self.results: List[Dict[str, Any]] = []
        self.reviews: List[Dict[str, Any]] = []
        self.current_index = 0

        # Database
        self.fact_checker_db = None
        self.db_type = "postgresql"
        self.annotator_id: Optional[int] = None
        self.annotator_username: Optional[str] = None

        # Components
        self.statement_widget: Optional[StatementWidget] = None
        self.annotation_widget: Optional[AnnotationWidget] = None
        self.citation_widget: Optional[CitationListWidget] = None
        self.timer_widget: Optional[TimerWidget] = None
        self.navigation_widget: Optional[NavigationWidget] = None

        # UI elements
        self.status_label: Optional[QLabel] = None
        self.review_container: Optional[QWidget] = None
        self.load_data_button: Optional[QPushButton] = None
        self.statistics_button: Optional[QPushButton] = None

        self._setup_ui()

    def _setup_ui(self):
        """Setup the user interface."""
        s = self.scale

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(s['padding_xlarge'], s['padding_xlarge'], s['padding_xlarge'], s['padding_xlarge'])
        main_layout.setSpacing(s['spacing_xlarge'])

        # Header
        header_layout = QHBoxLayout()

        title_layout = QVBoxLayout()
        title = QLabel("Fact-Checker Review Interface")
        title.setStyleSheet(f"font-size: {s['font_xlarge']}pt; font-weight: bold; color: #0d47a1;")
        title_layout.addWidget(title)

        subtitle = QLabel("Review and annotate AI-generated fact-checking results")
        subtitle.setStyleSheet(f"font-size: {s['font_normal']}pt; color: #666;")
        title_layout.addWidget(subtitle)

        header_layout.addLayout(title_layout)
        header_layout.addStretch()

        # Statistics button
        self.statistics_button = QPushButton("📊 Statistics")
        self.statistics_button.setFixedWidth(int(s['control_height_medium'] * 3.3))
        self.statistics_button.clicked.connect(self._on_show_statistics)
        self.statistics_button.setStyleSheet(f"""
            QPushButton {{
                background-color: #1565c0;
                color: white;
                padding: {s['padding_small']}px {s['padding_large']}px;
                border: none;
                border-radius: {s['radius_small']}px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #0d47a1;
            }}
        """)
        header_layout.addWidget(self.statistics_button)

        main_layout.addLayout(header_layout)

        # Status section
        status_container = QWidget()
        status_layout = QHBoxLayout(status_container)
        status_layout.setContentsMargins(s['spacing_xlarge'], s['spacing_medium'], s['spacing_xlarge'], s['spacing_medium'])

        self.status_label = QLabel("Click 'Load Data' to begin reviewing")
        self.status_label.setStyleSheet("color: #666; font-style: italic;")
        status_layout.addWidget(self.status_label)

        status_container.setStyleSheet(f"""
            QWidget {{
                background-color: #bbdefb;
                border-radius: {s['radius_medium']}px;
            }}
        """)
        main_layout.addWidget(status_container)

        # Load data button (initially visible)
        self.load_data_button = QPushButton("Load Data from Database")
        self.load_data_button.clicked.connect(self._on_load_data)
        self.load_data_button.setStyleSheet(f"""
            QPushButton {{
                background-color: #43a047;
                color: white;
                padding: {s['padding_large']}px {s['padding_xlarge'] * 2}px;
                border: none;
                border-radius: {s['radius_small']}px;
                font-size: {s['font_medium']}pt;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #388e3c;
            }}
        """)
        main_layout.addWidget(self.load_data_button, alignment=Qt.AlignCenter)

        # Review content (initially hidden)
        self.review_container = self._build_review_container()
        self.review_container.setVisible(False)
        main_layout.addWidget(self.review_container)

    def _build_review_container(self) -> QWidget:
        """Build the review interface container."""
        s = self.scale

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(s['spacing_xlarge'])

        # Progress and timer row
        progress_layout = QHBoxLayout()

        # Statement widget
        self.statement_widget = StatementWidget(blind_mode=self.blind_mode)
        progress_layout.addWidget(self.statement_widget, stretch=1)

        # Timer widget
        self.timer_widget = TimerWidget()
        progress_layout.addWidget(self.timer_widget)

        layout.addLayout(progress_layout)

        # Annotation widget
        self.annotation_widget = AnnotationWidget()
        self.annotation_widget.annotation_changed.connect(self._on_annotation_change)
        layout.addWidget(self.annotation_widget)

        # Citations section
        citations_title = QLabel("Supporting Citations")
        citations_title.setStyleSheet(f"font-weight: bold; color: #263238; font-size: {s['font_normal']}pt;")
        layout.addWidget(citations_title)

        # Scrollable citation list
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMinimumHeight(int(s['control_height_large'] * 7.5))
        scroll_area.setMaximumHeight(int(s['control_height_large'] * 10))

        self.citation_widget = CitationListWidget()
        scroll_area.setWidget(self.citation_widget)

        scroll_area.setStyleSheet(f"""
            QScrollArea {{
                background-color: #fff8e1;
                border: 1px solid #ffb74d;
                border-radius: {s['radius_medium']}px;
            }}
        """)
        layout.addWidget(scroll_area)

        # Navigation
        self.navigation_widget = NavigationWidget()
        self.navigation_widget.previous_clicked.connect(self._on_previous)
        self.navigation_widget.next_clicked.connect(self._on_next)
        layout.addWidget(self.navigation_widget)

        return container

    @Slot()
    def _on_load_data(self):
        """Handle load data button click."""
        # Show annotator login dialog
        username, ok = QInputDialog.getText(
            self,
            "Annotator Login",
            "Enter your username:",
        )

        if ok and username:
            self.annotator_username = username

            # Ask for database type
            options = ["PostgreSQL (default)", "SQLite file"]
            choice, ok = QInputDialog.getItem(
                self,
                "Database Source",
                "Select data source:",
                options,
                0,
                False,
            )

            if ok:
                if "SQLite" in choice:
                    # Ask for SQLite file
                    file_path, _ = QFileDialog.getOpenFileName(
                        self,
                        "Select SQLite Database File",
                        str(Path.home()),
                        "Database Files (*.db *.sqlite);;All Files (*)",
                    )
                    if file_path:
                        self.db_file = file_path
                        self.db_type = "sqlite"
                        self._load_from_database()
                else:
                    # Use PostgreSQL
                    self.db_file = None
                    self.db_type = "postgresql"
                    self._load_from_database()

    def _load_from_database(self):
        """Load fact-check results from database."""
        try:
            self.status_label.setText("Loading from database...")
            self.status_label.setStyleSheet("color: #666; font-style: italic;")

            # Get database instance
            self.fact_checker_db = get_fact_checker_db(self.db_file)

            # Register annotator
            annotator = Annotator(
                username=self.annotator_username,
                full_name=self.annotator_username,
                email=None,
                expertise_level=None,
            )
            self.annotator_id = self.fact_checker_db.insert_or_get_annotator(annotator)

            # Load all statements with evaluations
            all_data = self.fact_checker_db.get_all_statements_with_evaluations()

            if not all_data:
                raise ValueError("No statements found in database")

            # Convert to display format
            self.results = []
            for row in all_data:
                result = {
                    'statement_id': row['id'],
                    'statement': row['statement_text'],
                    'expected_answer': row['expected_answer'],
                    'evaluation': row.get('evaluation'),
                    'reason': row.get('reason'),
                    'confidence': row.get('confidence'),
                    'evidence_list': [],
                    'human_annotations': row.get('human_annotations', []),
                }

                # Convert evidence
                for ev in row.get('evidence', []):
                    result['evidence_list'].append({
                        'pmid': ev.get('pmid', 'N/A'),
                        'doi': ev.get('doi', ''),
                        'title': ev.get('title', 'No title'),
                        'abstract': ev.get('abstract', 'No abstract'),
                        'authors': ev.get('authors', 'Unknown'),
                        'journal': ev.get('journal', 'Unknown'),
                        'pub_year': ev.get('pub_year', 'N/A'),
                        'passage': ev.get('citation_text', ''),
                    })

                self.results.append(result)

            # Initialize reviews
            self.reviews = [{}] * len(self.results)
            for i, result in enumerate(self.results):
                for annot in result.get('human_annotations', []):
                    if annot.get('annotator_id') == self.annotator_id:
                        self.reviews[i] = {
                            'human_annotation': annot.get('annotation'),
                            'human_explanation': annot.get('explanation', ''),
                            'confidence': annot.get('confidence', ''),
                            'review_duration_seconds': annot.get('review_duration_seconds'),
                        }
                        break

            # Update UI
            mode_indicator = " [INCREMENTAL]" if self.incremental else ""
            db_source = self.db_type.upper()

            self.status_label.setText(
                f"✓ Loaded {len(self.results)} statements from {db_source}{mode_indicator}"
            )
            self.status_label.setStyleSheet("color: #2e7d32; font-weight: bold;")

            # Hide load button, show review interface
            self.load_data_button.setVisible(False)
            self.review_container.setVisible(True)

            # Display first statement
            self.current_index = 0
            self._display_current_statement()

            self.status_changed.emit(f"Loaded {len(self.results)} statements")

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"ERROR loading database:\n{error_details}")

            QMessageBox.critical(
                self,
                "Error Loading Data",
                f"Failed to load from database:\n\n{str(e)}",
            )
            self.status_label.setText("Error loading data")
            self.status_label.setStyleSheet("color: #c62828; font-weight: bold;")

    def _display_current_statement(self):
        """Display the current statement and its annotations."""
        if not self.results or self.current_index >= len(self.results):
            return

        result = self.results[self.current_index]

        # Update statement widget
        self.statement_widget.update_progress(self.current_index, len(self.results))
        self.statement_widget.update_statement(result.get('statement', 'N/A'))
        self.statement_widget.update_annotations(
            result.get('expected_answer', 'N/A'),
            result.get('evaluation', 'N/A'),
            result.get('reason', 'No rationale provided'),
        )

        # Update annotation widget
        saved_review = self.reviews[self.current_index]
        self.annotation_widget.set_annotation(
            saved_review.get('human_annotation', ''),
            saved_review.get('human_explanation', ''),
            saved_review.get('confidence', ''),
        )

        # Update citations
        self.citation_widget.set_citations(result.get('evidence_list', []))

        # Update navigation
        self.navigation_widget.set_button_states(
            can_go_previous=self.current_index > 0,
            can_go_next=self.current_index < len(self.results) - 1,
        )

        # Start timer
        previous_time = saved_review.get('review_duration_seconds', 0) or 0
        self.timer_widget.start(previous_seconds=previous_time)

    @Slot(str, str, str)
    def _on_annotation_change(self, annotation: str, explanation: str, confidence: str):
        """Handle annotation change event."""
        # Only record time if an evaluation has been selected
        review_duration = None
        if annotation and annotation != "n/a":
            review_duration = self.timer_widget.get_elapsed_seconds()

        # Save to database
        self._save_annotation(annotation, explanation, confidence, review_duration)

    def _save_annotation(
        self,
        annotation: str,
        explanation: str,
        confidence: str,
        review_duration: Optional[int],
    ):
        """Save annotation to database."""
        if not self.fact_checker_db or self.current_index >= len(self.results):
            return

        try:
            result = self.results[self.current_index]
            statement_id = result['statement_id']

            # Convert 'n/a' to empty string for database
            db_annotation = "" if annotation == "n/a" else annotation
            db_confidence = "" if confidence == "n/a" else confidence

            # Create annotation object
            human_annotation = HumanAnnotation(
                statement_id=statement_id,
                annotator_id=self.annotator_id,
                annotation=db_annotation,
                explanation=explanation,
                confidence=db_confidence,
                review_duration_seconds=review_duration,
            )

            # Insert or update
            self.fact_checker_db.insert_or_update_human_annotation(human_annotation)

            # Update local review
            self.reviews[self.current_index] = {
                'human_annotation': db_annotation,
                'human_explanation': explanation,
                'confidence': db_confidence,
                'review_duration_seconds': review_duration,
            }

        except Exception as e:
            print(f"ERROR saving annotation: {e}")
            import traceback
            traceback.print_exc()

    @Slot()
    def _on_previous(self):
        """Navigate to previous statement."""
        if self.current_index > 0:
            # Reset timer if no annotation
            current_review = self.reviews[self.current_index]
            if not current_review.get('human_annotation'):
                self.timer_widget.reset()

            self.current_index -= 1
            self._display_current_statement()

    @Slot()
    def _on_next(self):
        """Navigate to next statement."""
        if self.current_index < len(self.results) - 1:
            # Reset timer if no annotation
            current_review = self.reviews[self.current_index]
            if not current_review.get('human_annotation'):
                self.timer_widget.reset()

            self.current_index += 1
            self._display_current_statement()

    @Slot()
    def _on_show_statistics(self):
        """Display statistics dialog."""
        if not self.results:
            QMessageBox.information(
                self,
                "No Data",
                "No data loaded. Please load data first.",
            )
            return

        # Calculate statistics
        total = len(self.results)
        annotated = sum(1 for r in self.reviews if r.get('human_annotation'))

        stats_text = f"""
Statistics:

Total Statements: {total}
Annotated: {annotated}
Remaining: {total - annotated}

Progress: {(annotated / total * 100):.1f}%
        """

        QMessageBox.information(
            self,
            "Review Statistics",
            stats_text,
        )

    def on_activated(self):
        """Called when tab is activated."""
        pass

    def on_deactivated(self):
        """Called when tab is deactivated."""
        pass

    def cleanup(self):
        """Cleanup resources."""
        if self.timer_widget:
            self.timer_widget.stop()
        if self.fact_checker_db:
            # Close database connection if needed
            pass
