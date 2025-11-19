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
    QLineEdit,
    QTextEdit,
    QComboBox,
)
from PySide6.QtCore import Qt, Signal, Slot

from .citation_widget import CitationListWidget
from .timer_widget import TimerWidget

# Import fact-checker database components
from .....factchecker.db import get_fact_checker_db, Annotator, HumanAnnotation

# Import DPI-aware styling
from ...resources.styles import get_font_scale, StylesheetGenerator
from ...resources.constants import ScoreColors


class FactCheckerTabWidget(QWidget):
    """Main fact-checker review tab widget."""

    # Signals
    status_changed = Signal(str)

    # Color constants (DPI-independent)
    COLOR_PRIMARY_BLUE = "#1976d2"
    COLOR_DARK_BLUE = "#0d47a1"
    COLOR_LIGHT_BLUE = "#1565c0"
    COLOR_INFO_BG = "#bbdefb"
    COLOR_TEXT_GREY = "#666"
    COLOR_SUCCESS_GREEN = "#43a047"
    COLOR_SUCCESS_GREEN_HOVER = "#388e3c"
    COLOR_SUCCESS_TEXT = "#2e7d32"
    COLOR_NAV_GREY = "#757575"
    COLOR_NAV_GREY_HOVER = "#616161"
    COLOR_DISABLED_BG = "#e0e0e0"
    COLOR_DISABLED_TEXT = "#9e9e9e"

    # Tag colors (evaluation states)
    COLOR_TAG_YES = "#4caf50"  # Green
    COLOR_TAG_NO = "#f44336"   # Red
    COLOR_TAG_MAYBE = "#ff9800"  # Orange
    COLOR_TAG_NA = "#9e9e9e"   # Grey

    # Column background colors
    COLOR_ORIGINAL_BG = "#e8eaf6"
    COLOR_ORIGINAL_BORDER = "#c5cae9"
    COLOR_AI_BG = "#ede7f6"
    COLOR_AI_BORDER = "#d1c4e9"
    COLOR_HUMAN_BG = "#e8f5e9"
    COLOR_HUMAN_BORDER = "#66bb6a"
    COLOR_BLIND_BG = "#e0e0e0"
    COLOR_BLIND_BORDER = "#bdbdbd"

    # Content area colors
    COLOR_INPUT_BG = "#f5f5f5"
    COLOR_INPUT_BORDER = "#ddd"
    COLOR_ARTICLE_BG = "#fffde7"
    COLOR_ARTICLE_BORDER = "#fdd835"
    COLOR_CITATION_BG = "#fff8e1"
    COLOR_CITATION_BORDER = "#ffb74d"

    def __init__(self, parent: Optional[QWidget] = None):
        """
        Initialize fact-checker tab.

        Args:
            parent: Optional parent widget
        """
        super().__init__(parent)

        # DPI-aware scaling
        self.scale = get_font_scale()
        self.style_gen = StylesheetGenerator(self.scale)

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
        self.citation_widget: Optional[CitationListWidget] = None
        self.timer_widget: Optional[TimerWidget] = None

        # UI elements - new layout
        self.status_label: Optional[QLabel] = None
        self.review_container: Optional[QWidget] = None
        self.load_data_button: Optional[QPushButton] = None
        self.statistics_button: Optional[QPushButton] = None
        self.statement_label: Optional[QLabel] = None
        self.statement_text: Optional[QLineEdit] = None
        self.original_tag: Optional[QLabel] = None
        self.original_text: Optional[QTextEdit] = None
        self.ai_tag: Optional[QLabel] = None
        self.ai_text: Optional[QTextEdit] = None
        self.human_dropdown: Optional[QComboBox] = None
        self.human_text: Optional[QTextEdit] = None
        self.article_text: Optional[QTextEdit] = None
        self.prev_button: Optional[QPushButton] = None
        self.next_button: Optional[QPushButton] = None
        self.original_col: Optional[QWidget] = None
        self.ai_col: Optional[QWidget] = None

        self._setup_ui()

    def _get_statement_input_stylesheet(self) -> str:
        """Generate stylesheet for statement input field."""
        s = self.scale
        return f"""
            QLineEdit {{
                background-color: {self.COLOR_INPUT_BG};
                padding: {s['padding_medium']}px;
                border: 1px solid {self.COLOR_INPUT_BORDER};
                border-radius: {s['radius_small']}px;
                font-size: {s['font_medium']}pt;
                color: #263238;
            }}
        """

    def _get_nav_button_stylesheet(self, is_next: bool = False) -> str:
        """Generate stylesheet for navigation buttons."""
        s = self.scale
        bg_color = self.COLOR_PRIMARY_BLUE if is_next else self.COLOR_NAV_GREY
        hover_color = self.COLOR_LIGHT_BLUE if is_next else self.COLOR_NAV_GREY_HOVER
        return f"""
            QPushButton {{
                background-color: {bg_color};
                color: white;
                border: none;
                border-radius: {s['radius_small']}px;
                font-size: {s['font_large']}pt;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {hover_color};
            }}
            QPushButton:disabled {{
                background-color: {self.COLOR_DISABLED_BG};
                color: {self.COLOR_DISABLED_TEXT};
            }}
        """

    def _get_column_stylesheet(self, col_type: str) -> str:
        """Generate stylesheet for evaluation columns."""
        s = self.scale
        color_map = {
            'original': (self.COLOR_ORIGINAL_BG, self.COLOR_ORIGINAL_BORDER),
            'ai': (self.COLOR_AI_BG, self.COLOR_AI_BORDER),
            'human': (self.COLOR_HUMAN_BG, self.COLOR_HUMAN_BORDER),
        }
        bg, border = color_map.get(col_type, ('#fff', '#ccc'))
        border_width = '2px' if col_type == 'human' else '1px'
        return f"""
            QWidget {{
                background-color: {bg};
                border: {border_width} solid {border};
                border-radius: {s['radius_medium']}px;
            }}
        """

    def _get_text_edit_stylesheet(self) -> str:
        """Generate stylesheet for text edit fields."""
        s = self.scale
        return f"""
            QTextEdit {{
                background-color: {self.COLOR_INPUT_BG};
                border: 1px solid {self.COLOR_INPUT_BORDER};
                padding: {s['padding_small']}px;
                border-radius: {s['radius_small']}px;
                font-size: {s['font_small']}pt;
            }}
        """

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
        """Build the review interface container with redesigned layout."""
        s = self.scale

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(s['spacing_large'])

        # ==============================================================================
        # ROW 1: Statement text + Navigation buttons (fixed height, expandable width)
        # ==============================================================================
        statement_row = QHBoxLayout()
        statement_row.setSpacing(s['spacing_medium'])

        # Statement label and text
        self.statement_label = QLabel("Statement #1:")
        self.statement_label.setStyleSheet(f"font-weight: bold; color: #1976d2; font-size: {s['font_normal']}pt;")
        self.statement_label.setFixedWidth(int(s['control_height_medium'] * 3.3))
        statement_row.addWidget(self.statement_label)

        # Statement text (read-only, expandable)
        self.statement_text = QLineEdit()
        self.statement_text.setReadOnly(True)
        self.statement_text.setStyleSheet(f"""
            QLineEdit {{
                background-color: #f5f5f5;
                padding: {s['padding_medium']}px;
                border: 1px solid #ddd;
                border-radius: {s['radius_small']}px;
                font-size: {s['font_medium']}pt;
                color: #263238;
            }}
        """)
        statement_row.addWidget(self.statement_text, stretch=1)

        # Navigation buttons (back/forward arrows)
        self.prev_button = QPushButton("←")
        self.prev_button.setFixedSize(int(s['control_height_medium'] * 1.1), int(s['control_height_medium'] * 1.1))
        self.prev_button.clicked.connect(self._on_previous)
        self.prev_button.setStyleSheet(f"""
            QPushButton {{
                background-color: #757575;
                color: white;
                border: none;
                border-radius: {s['radius_small']}px;
                font-size: {s['font_large']}pt;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #616161;
            }}
            QPushButton:disabled {{
                background-color: #e0e0e0;
                color: #9e9e9e;
            }}
        """)
        statement_row.addWidget(self.prev_button)

        self.next_button = QPushButton("→")
        self.next_button.setFixedSize(int(s['control_height_medium'] * 1.1), int(s['control_height_medium'] * 1.1))
        self.next_button.clicked.connect(self._on_next)
        self.next_button.setStyleSheet(f"""
            QPushButton {{
                background-color: #1976d2;
                color: white;
                border: none;
                border-radius: {s['radius_small']}px;
                font-size: {s['font_large']}pt;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #1565c0;
            }}
            QPushButton:disabled {{
                background-color: #e0e0e0;
                color: #9e9e9e;
            }}
        """)
        statement_row.addWidget(self.next_button)

        layout.addLayout(statement_row)

        # ==============================================================================
        # ROW 2: 3-column evaluation row (Original | AI | Human)
        # Horizontal stretch, NO vertical stretch, equal width columns
        # ==============================================================================
        evaluation_row = QHBoxLayout()
        evaluation_row.setSpacing(s['spacing_medium'])

        # Column 1: Original Answer
        original_col = QWidget()
        original_layout = QVBoxLayout(original_col)
        original_layout.setContentsMargins(s['spacing_medium'], s['spacing_medium'], s['spacing_medium'], s['spacing_medium'])
        original_layout.setSpacing(s['spacing_small'])

        original_title = QLabel("Original Answer")
        original_title.setStyleSheet(f"font-weight: bold; color: #3949ab; font-size: {s['font_small']}pt;")
        original_layout.addWidget(original_title)

        self.original_tag = QLabel("N/A")
        self.original_tag.setAlignment(Qt.AlignCenter)
        self.original_tag.setFixedHeight(int(s['control_height_small'] * 0.83))
        self.original_tag.setStyleSheet(f"""
            QLabel {{
                background-color: #9e9e9e;
                color: white;
                padding: {s['padding_tiny']}px {s['padding_small']}px;
                border-radius: {s['radius_small']}px;
                font-weight: bold;
            }}
        """)
        original_layout.addWidget(self.original_tag)

        self.original_text = QTextEdit()
        self.original_text.setReadOnly(True)
        self.original_text.setPlaceholderText("Original long answer (to be added)")
        self.original_text.setMinimumHeight(int(s['control_height_medium'] * 2.2))
        self.original_text.setMaximumHeight(int(s['control_height_medium'] * 2.2))
        self.original_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: #f5f5f5;
                border: 1px solid #ddd;
                padding: {s['padding_small']}px;
                border-radius: {s['radius_small']}px;
                font-size: {s['font_small']}pt;
            }}
        """)
        original_layout.addWidget(self.original_text)

        original_col.setStyleSheet(f"""
            QWidget {{
                background-color: #e8eaf6;
                border: 1px solid #c5cae9;
                border-radius: {s['radius_medium']}px;
            }}
        """)
        evaluation_row.addWidget(original_col, stretch=1)

        # Column 2: AI Evaluation
        ai_col = QWidget()
        ai_layout = QVBoxLayout(ai_col)
        ai_layout.setContentsMargins(s['spacing_medium'], s['spacing_medium'], s['spacing_medium'], s['spacing_medium'])
        ai_layout.setSpacing(s['spacing_small'])

        ai_title = QLabel("AI Evaluation")
        ai_title.setStyleSheet(f"font-weight: bold; color: #5e35b1; font-size: {s['font_small']}pt;")
        ai_layout.addWidget(ai_title)

        self.ai_tag = QLabel("N/A")
        self.ai_tag.setAlignment(Qt.AlignCenter)
        self.ai_tag.setFixedHeight(int(s['control_height_small'] * 0.83))
        self.ai_tag.setStyleSheet(f"""
            QLabel {{
                background-color: #9e9e9e;
                color: white;
                padding: {s['padding_tiny']}px {s['padding_small']}px;
                border-radius: {s['radius_small']}px;
                font-weight: bold;
            }}
        """)
        ai_layout.addWidget(self.ai_tag)

        self.ai_text = QTextEdit()
        self.ai_text.setReadOnly(True)
        self.ai_text.setPlaceholderText("AI rationale")
        self.ai_text.setMinimumHeight(int(s['control_height_medium'] * 2.2))
        self.ai_text.setMaximumHeight(int(s['control_height_medium'] * 2.2))
        self.ai_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: #f5f5f5;
                border: 1px solid #ddd;
                padding: {s['padding_small']}px;
                border-radius: {s['radius_small']}px;
                font-size: {s['font_small']}pt;
            }}
        """)
        ai_layout.addWidget(self.ai_text)

        ai_col.setStyleSheet(f"""
            QWidget {{
                background-color: #ede7f6;
                border: 1px solid #d1c4e9;
                border-radius: {s['radius_medium']}px;
            }}
        """)
        evaluation_row.addWidget(ai_col, stretch=1)

        # Column 3: Human Evaluation
        human_col = QWidget()
        human_layout = QVBoxLayout(human_col)
        human_layout.setContentsMargins(s['spacing_medium'], s['spacing_medium'], s['spacing_medium'], s['spacing_medium'])
        human_layout.setSpacing(s['spacing_small'])

        human_title = QLabel("Human Review")
        human_title.setStyleSheet(f"font-weight: bold; color: #2e7d32; font-size: {s['font_small']}pt;")
        human_layout.addWidget(human_title)

        self.human_dropdown = QComboBox()
        self.human_dropdown.addItem("N/A (Not Yet Annotated)", "n/a")
        self.human_dropdown.addItem("Yes", "yes")
        self.human_dropdown.addItem("No", "no")
        self.human_dropdown.addItem("Maybe", "maybe")
        self.human_dropdown.setCurrentIndex(0)
        self.human_dropdown.currentIndexChanged.connect(self._on_annotation_change)
        self.human_dropdown.setFixedHeight(int(s['control_height_small'] * 0.83))
        self.human_dropdown.setStyleSheet(f"""
            QComboBox {{
                background-color: white;
                border: 1px solid #ccc;
                padding: {s['padding_tiny']}px;
                border-radius: {s['radius_small']}px;
            }}
        """)
        human_layout.addWidget(self.human_dropdown)

        self.human_text = QTextEdit()
        self.human_text.setPlaceholderText("Enter your explanation...")
        self.human_text.textChanged.connect(self._on_annotation_change)
        self.human_text.setMinimumHeight(int(s['control_height_medium'] * 2.2))
        self.human_text.setMaximumHeight(int(s['control_height_medium'] * 2.2))
        self.human_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: white;
                border: 1px solid #ccc;
                padding: {s['padding_small']}px;
                border-radius: {s['radius_small']}px;
                font-size: {s['font_small']}pt;
            }}
        """)
        human_layout.addWidget(self.human_text)

        human_col.setStyleSheet(f"""
            QWidget {{
                background-color: #e8f5e9;
                border: 2px solid #66bb6a;
                border-radius: {s['radius_medium']}px;
            }}
        """)
        evaluation_row.addWidget(human_col, stretch=1)

        # Store column widgets for blind mode
        self.original_col = original_col
        self.ai_col = ai_col

        layout.addLayout(evaluation_row)

        # ==============================================================================
        # ROW 3: Original article (fixed height ~12 lines, horizontally expandable)
        # ==============================================================================
        article_label = QLabel("Original Article Context:")
        article_label.setStyleSheet(f"font-weight: bold; color: #263238; font-size: {s['font_normal']}pt;")
        layout.addWidget(article_label)

        self.article_text = QTextEdit()
        self.article_text.setReadOnly(True)
        self.article_text.setPlaceholderText("Original article information will be shown here")
        self.article_text.setMinimumHeight(int(s['control_height_medium'] * 4.4))
        self.article_text.setMaximumHeight(int(s['control_height_medium'] * 4.4))
        self.article_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: #fffde7;
                border: 1px solid #fdd835;
                padding: {s['padding_medium']}px;
                border-radius: {s['radius_medium']}px;
                font-size: {s['font_small']}pt;
            }}
        """)
        layout.addWidget(self.article_text)

        # ==============================================================================
        # ROW 4: Citations (both ways expandable)
        # ==============================================================================
        citations_label = QLabel("Supporting Citations:")
        citations_label.setStyleSheet(f"font-weight: bold; color: #263238; font-size: {s['font_normal']}pt;")
        layout.addWidget(citations_label)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMinimumHeight(int(s['control_height_large'] * 3.75))

        self.citation_widget = CitationListWidget()
        scroll_area.setWidget(self.citation_widget)

        scroll_area.setStyleSheet(f"""
            QScrollArea {{
                background-color: #fff8e1;
                border: 1px solid #ffb74d;
                border-radius: {s['radius_medium']}px;
            }}
        """)
        layout.addWidget(scroll_area, stretch=1)

        # ==============================================================================
        # Timer and auto-save indicator
        # ==============================================================================
        footer_layout = QHBoxLayout()
        footer_layout.setSpacing(s['spacing_medium'])

        # Timer widget
        self.timer_widget = TimerWidget()
        footer_layout.addWidget(self.timer_widget)

        footer_layout.addStretch()

        # Auto-save indicator
        auto_save_label = QLabel("✓ Annotations saved automatically")
        auto_save_label.setStyleSheet(f"color: #2e7d32; font-size: {s['font_small']}pt; font-style: italic;")
        footer_layout.addWidget(auto_save_label)

        layout.addLayout(footer_layout)

        # Apply blind mode if enabled
        if self.blind_mode:
            self._apply_blind_mode()

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
                        'document_id': ev.get('document_id'),  # Include for database enrichment
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

        # Update statement label and text
        self.statement_label.setText(f"Statement #{self.current_index + 1}:")
        self.statement_text.setText(result.get('statement', 'N/A'))

        # Update original answer column
        original_answer = result.get('expected_answer', 'N/A')
        self._update_tag(self.original_tag, original_answer)
        self.original_text.setPlainText(result.get('original_explanation', ''))  # Will be added to DB

        # Update AI evaluation column
        ai_evaluation = result.get('evaluation', 'N/A')
        self._update_tag(self.ai_tag, ai_evaluation)
        self.ai_text.setPlainText(result.get('reason', 'No rationale provided'))

        # Update human evaluation column
        saved_review = self.reviews[self.current_index]
        self.human_dropdown.blockSignals(True)
        self.human_text.blockSignals(True)

        human_annotation = saved_review.get('human_annotation', '')
        if not human_annotation or human_annotation == "":
            human_annotation = "n/a"
        idx = self.human_dropdown.findData(human_annotation.lower())
        if idx >= 0:
            self.human_dropdown.setCurrentIndex(idx)

        self.human_text.setPlainText(saved_review.get('human_explanation', ''))

        self.human_dropdown.blockSignals(False)
        self.human_text.blockSignals(False)

        # Update original article context
        # TODO: Fetch from database if not present
        article_context = result.get('article_context', '')
        if not article_context:
            # Get from input_statement_id if it's a PMID
            input_id = result.get('input_statement_id', '')
            if input_id:
                article_context = f"Original article ID: {input_id}\n\n(Full article text to be fetched from database)"
        self.article_text.setPlainText(article_context)

        # Update citations (with database enrichment if needed)
        citations = result.get('evidence_list', [])
        self.citation_widget.set_citations(citations, self.fact_checker_db)

        # Update navigation buttons
        self.prev_button.setEnabled(self.current_index > 0)
        self.next_button.setEnabled(self.current_index < len(self.results) - 1)

        # Start timer
        previous_time = saved_review.get('review_duration_seconds', 0) or 0
        self.timer_widget.start(previous_seconds=previous_time)

    def _update_tag(self, tag_label: QLabel, value: str):
        """
        Update a tag label with appropriate styling.

        Args:
            tag_label: The QLabel to update
            value: The value ('yes', 'no', 'maybe', 'N/A')
        """
        s = self.scale
        value_lower = value.lower() if value else 'n/a'

        # Color mapping
        color_map = {
            'yes': '#4caf50',    # Green
            'no': '#f44336',     # Red
            'maybe': '#ff9800',  # Orange
            'n/a': '#9e9e9e',    # Gray
        }

        bg_color = color_map.get(value_lower, '#9e9e9e')
        tag_label.setText(value.upper() if value else 'N/A')
        tag_label.setStyleSheet(f"""
            QLabel {{
                background-color: {bg_color};
                color: white;
                padding: {s['padding_tiny']}px {s['padding_small']}px;
                border-radius: {s['radius_small']}px;
                font-weight: bold;
            }}
        """)

    def _on_annotation_change(self):
        """Handle annotation change event."""
        # Get current values from widgets
        annotation = self.human_dropdown.currentData()
        explanation = self.human_text.toPlainText()

        # Only record time if an evaluation has been selected
        review_duration = None
        if annotation and annotation != "n/a":
            review_duration = self.timer_widget.get_elapsed_seconds()

        # Save to database (using empty string for confidence for now)
        self._save_annotation(annotation, explanation, "", review_duration)

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

    def _apply_blind_mode(self):
        """Apply visual graying to original and AI columns in blind mode."""
        if not self.original_col or not self.ai_col:
            return

        s = self.scale

        # Gray out original column
        self.original_col.setEnabled(False)
        self.original_col.setStyleSheet(f"""
            QWidget {{
                background-color: #e0e0e0;
                border: 1px solid #bdbdbd;
                border-radius: {s['radius_medium']}px;
                opacity: 0.5;
            }}
        """)

        # Gray out AI column
        self.ai_col.setEnabled(False)
        self.ai_col.setStyleSheet(f"""
            QWidget {{
                background-color: #e0e0e0;
                border: 1px solid #bdbdbd;
                border-radius: {s['radius_medium']}px;
                opacity: 0.5;
            }}
        """)

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
