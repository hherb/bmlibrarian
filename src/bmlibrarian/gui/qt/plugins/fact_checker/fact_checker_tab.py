"""
Main Fact-Checker Review Tab Widget.

Coordinates all components for reviewing and annotating fact-check results.
"""

import logging
from typing import Optional, Dict, Any, List, Tuple
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
from .....factchecker.db.postgresql_db import PostgreSQLFactCheckerDB

# Import DPI-aware styling
from ...resources.styles import get_font_scale, StylesheetGenerator
from ...resources.constants import ScoreColors



logger = logging.getLogger(__name__)


# Shown when an evaluation has no rationale text.
NO_RATIONALE_TEXT = 'No rationale provided'


def format_ai_rationale(reason: Optional[str], degradation_notes: Optional[List[str]]) -> str:
    """
    Text for the AI rationale panel, flagging a verdict based on partial evidence.

    Args:
        reason: The AI evaluation's rationale.
        degradation_notes: Evidence the fact-checker could not examine for
            this verdict (empty or None for a complete check).

    Returns:
        The rationale, followed by the notes when there are any.
    """
    text = reason if reason else NO_RATIONALE_TEXT
    if not degradation_notes:
        return text
    lines = "\n".join(f"- {note}" for note in degradation_notes)
    return (
        f"{text}\n\n⚠ Based on partial evidence; not examined:\n{lines}"
    )


def reviews_for_annotator(
    results: List[Dict[str, Any]],
    annotator_id: Optional[int],
) -> List[Dict[str, Any]]:
    """Build the per-statement review state for one annotator.

    Args:
        results: Statements in display format, each with 'human_annotations'
        annotator_id: The current annotator's id (None: no annotations)

    Returns:
        One dict per statement (a distinct object each): the annotator's
        existing annotation fields, or empty if they have none
    """
    reviews: List[Dict[str, Any]] = []
    for result in results:
        review: Dict[str, Any] = {}
        for annot in result.get('human_annotations', []):
            if annotator_id is not None and annot.get('annotator_id') == annotator_id:
                review = {
                    'human_annotation': annot.get('annotation'),
                    'human_explanation': annot.get('explanation', ''),
                    'confidence': annot.get('confidence', ''),
                    'review_duration_seconds': annot.get('review_duration_seconds'),
                }
                break
        reviews.append(review)
    return reviews


def filter_unannotated(
    results: List[Dict[str, Any]],
    reviews: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Keep only statements the annotator has not annotated (incremental mode).

    Args:
        results: Statements in display format
        reviews: Matching per-statement review state (same order)

    Returns:
        The filtered (results, reviews) pair, still aligned
    """
    kept = [
        (result, review)
        for result, review in zip(results, reviews)
        if not review.get('human_annotation')
    ]
    return [r for r, _ in kept], [v for _, v in kept]


class FactCheckerTabWidget(QWidget):
    """Main fact-checker review tab widget."""

    # Signals
    status_changed = Signal(str)

    AUTO_SAVE_OK_TEXT = "✓ Annotations saved automatically"
    AUTO_SAVE_FAILED_TEXT = "⚠ Last annotation was NOT saved (see status above)"

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

    # Content area colors
    COLOR_INPUT_BG = "#f5f5f5"
    COLOR_INPUT_BORDER = "#ddd"
    COLOR_ARTICLE_BG = "#fffde7"
    COLOR_ARTICLE_BORDER = "#fdd835"
    COLOR_CITATION_BG = "#fff8e1"
    COLOR_CITATION_BORDER = "#ffb74d"
    # Text and border colors
    COLOR_DARK_TEXT = "#263238"
    COLOR_WHITE = "#fff"
    COLOR_LIGHT_BORDER = "#ccc"
    COLOR_COLUMN_TITLE_ORIGINAL = "#3949ab"  # Indigo
    COLOR_COLUMN_TITLE_AI = "#5e35b1"  # Purple
    COLOR_ERROR_RED = "#c62828"


    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        db_file: Optional[str] = None,
        default_username: Optional[str] = None,
        blind_mode: bool = False,
        incremental: bool = False,
    ):
        """
        Initialize fact-checker tab.

        Args:
            parent: Optional parent widget
            db_file: SQLite review-package file; None uses PostgreSQL
            default_username: Annotator username to start with (skips the
                PostgreSQL single-annotator auto-detection)
            blind_mode: Hide the original and AI annotations from the reviewer
                (the columns are hidden and never filled; the review toggle
                is removed so they cannot be shown)
            incremental: Only show statements this annotator has not yet
                annotated (requires an annotator; without one all statements
                are shown)
        """
        super().__init__(parent)

        # DPI-aware scaling
        self.scale = get_font_scale()
        self.style_gen = StylesheetGenerator(self.scale)

        # Configuration
        self.incremental = incremental
        self.blind_mode = blind_mode
        self.db_file: Optional[str] = db_file
        self.show_review_enabled = True  # Show original/AI columns by default
        self.show_citations_enabled = True  # Show citations by default

        # Data
        self.results: List[Dict[str, Any]] = []
        self.reviews: List[Dict[str, Any]] = []
        self.current_index = 0
        self._load_failed = False

        # Database
        self.fact_checker_db = None
        self.db_type = "sqlite" if db_file else "postgresql"
        self.annotator_id: Optional[int] = None
        self.annotator_username: Optional[str] = None

        # Components
        self.citation_widget: Optional[CitationListWidget] = None
        self.timer_widget: Optional[TimerWidget] = None

        # UI elements - new layout
        self.status_label: Optional[QLabel] = None
        self.review_container: Optional[QWidget] = None
        self.statistics_button: Optional[QPushButton] = None
        self.username_field: Optional[QLineEdit] = None
        self.show_review_toggle: Optional[QPushButton] = None
        self.show_citations_toggle: Optional[QPushButton] = None
        self.citations_section: Optional[QWidget] = None
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
        self.auto_save_label: Optional[QLabel] = None

        self._setup_ui()
        if default_username and self.username_field is not None:
            self.username_field.setText(default_username)

        # Connect username field changes (only when focus leaves field)
        self.username_field.editingFinished.connect(self._on_username_changed)

        # Auto-load data from database on startup
        self._auto_load_data()

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
                color: {self.COLOR_DARK_TEXT};
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
        bg, border = color_map.get(col_type, ('{self.COLOR_WHITE}', '{self.COLOR_LIGHT_BORDER}'))
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


    def _get_article_text_stylesheet(self) -> str:
        """Generate stylesheet for article context text area."""
        s = self.scale
        return f"""
            QTextEdit {{
                background-color: {self.COLOR_ARTICLE_BG};
                border: 1px solid {self.COLOR_ARTICLE_BORDER};
                padding: {s['padding_medium']}px;
                border-radius: {s['radius_medium']}px;
                font-size: {s['font_small']}pt;
            }}
        """

    def _get_citation_scroll_stylesheet(self) -> str:
        """Generate stylesheet for citation scroll area."""
        s = self.scale
        return f"""
            QScrollArea {{
                background-color: {self.COLOR_CITATION_BG};
                border: 1px solid {self.COLOR_CITATION_BORDER};
                border-radius: {s['radius_medium']}px;
            }}
        """

    def _get_column_title_stylesheet(self, col_type: str) -> str:
        """Generate stylesheet for column title labels."""
        s = self.scale
        color_map = {
            'original': self.COLOR_COLUMN_TITLE_ORIGINAL,  # Indigo
            'ai': self.COLOR_COLUMN_TITLE_AI,        # Purple
            'human': self.COLOR_SUCCESS_TEXT,  # Green
        }
        color = color_map.get(col_type, self.COLOR_DARK_TEXT)
        return f"font-weight: bold; color: {color}; font-size: {s['font_small']}pt;"

    def _get_tag_initial_stylesheet(self) -> str:
        """Generate initial stylesheet for tag labels (before value is set)."""
        s = self.scale
        return f"""
            QLabel {{
                background-color: {self.COLOR_TAG_NA};
                color: white;
                padding: {s['padding_tiny']}px {s['padding_small']}px;
                border-radius: {s['radius_small']}px;
                font-weight: bold;
            }}
        """

    def _get_human_text_edit_stylesheet(self) -> str:
        """Generate stylesheet for human evaluation text edit (white background)."""
        s = self.scale
        return f"""
            QTextEdit {{
                background-color: white;
                border: 1px solid {self.COLOR_LIGHT_BORDER};
                padding: {s['padding_small']}px;
                border-radius: {s['radius_small']}px;
                font-size: {s['font_small']}pt;
            }}
        """

    def _get_human_dropdown_stylesheet(self) -> str:
        """Generate stylesheet for human evaluation dropdown."""
        s = self.scale
        return f"""
            QComboBox {{
                background-color: white;
                border: 1px solid {self.COLOR_LIGHT_BORDER};
                padding: {s['padding_tiny']}px;
                border-radius: {s['radius_small']}px;
            }}
        """

    def _get_section_label_stylesheet(self) -> str:
        """Generate stylesheet for section labels."""
        s = self.scale
        return f"font-weight: bold; color: {self.COLOR_DARK_TEXT}; font-size: {s['font_normal']}pt;"

    def _get_auto_save_label_stylesheet(self) -> str:
        """Generate stylesheet for auto-save indicator label."""
        s = self.scale
        return f"color: {self.COLOR_SUCCESS_TEXT}; font-size: {s['font_small']}pt; font-style: italic;"

    def _get_username_label_stylesheet(self) -> str:
        """Generate stylesheet for username label."""
        s = self.scale
        return f"font-weight: bold; font-size: {s['font_normal']}pt;"

    def _get_username_field_stylesheet(self) -> str:
        """Generate stylesheet for username input field."""
        s = self.scale
        return f"""
            QLineEdit {{
                background-color: white;
                border: 1px solid {self.COLOR_LIGHT_BORDER};
                padding: {s['padding_tiny']}px;
                border-radius: {s['radius_small']}px;
                font-size: {s['font_normal']}pt;
            }}
        """

    def _get_title_stylesheet(self) -> str:
        """Generate stylesheet for main title label."""
        s = self.scale
        return f"font-size: {s['font_xlarge']}pt; font-weight: bold; color: {self.COLOR_DARK_BLUE};"

    def _get_subtitle_stylesheet(self) -> str:
        """Generate stylesheet for subtitle label."""
        s = self.scale
        return f"font-size: {s['font_normal']}pt; color: {self.COLOR_TEXT_GREY};"

    def _get_statistics_button_stylesheet(self) -> str:
        """Generate stylesheet for statistics button."""
        s = self.scale
        return f"""
            QPushButton {{
                background-color: {self.COLOR_LIGHT_BLUE};
                color: white;
                padding: {s['padding_small']}px {s['padding_large']}px;
                border: none;
                border-radius: {s['radius_small']}px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {self.COLOR_DARK_BLUE};
            }}
        """

    def _get_status_label_stylesheet(self, state: str = 'info') -> str:
        """Generate stylesheet for status label.
        
        Args:
            state: One of 'info', 'success', 'error'
        """
        color_map = {
            'info': self.COLOR_TEXT_GREY,
            'success': self.COLOR_SUCCESS_TEXT,
            'error': self.COLOR_ERROR_RED,
        }
        color = color_map.get(state, self.COLOR_TEXT_GREY)
        style = "color: " + color + ";"
        if state == 'info':
            style += " font-style: italic;"
        else:
            style += " font-weight: bold;"
        return style

    def _get_status_container_stylesheet(self) -> str:
        """Generate stylesheet for status container."""
        s = self.scale
        return f"""
            QWidget {{
                background-color: {self.COLOR_INFO_BG};
                border-radius: {s['radius_medium']}px;
            }}
        """

    def _get_tag_stylesheet(self, value: str) -> str:
        """Generate stylesheet for tag label based on value.
        
        Args:
            value: Tag value ('yes', 'no', 'maybe', 'n/a')
        """
        s = self.scale
        value_lower = value.lower() if value else 'n/a'
        
        color_map = {
            'yes': self.COLOR_TAG_YES,
            'no': self.COLOR_TAG_NO,
            'maybe': self.COLOR_TAG_MAYBE,
            'n/a': self.COLOR_TAG_NA,
        }
        
        bg_color = color_map.get(value_lower, self.COLOR_TAG_NA)
        return f"""
            QLabel {{
                background-color: {bg_color};
                color: white;
                padding: {s['padding_tiny']}px {s['padding_small']}px;
                border-radius: {s['radius_small']}px;
                font-weight: bold;
            }}
        """

    def _get_statement_label_stylesheet(self) -> str:
        """Generate stylesheet for statement number label."""
        s = self.scale
        return f"font-weight: bold; color: {self.COLOR_PRIMARY_BLUE}; font-size: {s['font_normal']}pt;"

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
        title.setStyleSheet(self._get_title_stylesheet())
        title_layout.addWidget(title)

        subtitle = QLabel("Review and annotate AI-generated fact-checking results")
        subtitle.setStyleSheet(self._get_subtitle_stylesheet())
        title_layout.addWidget(subtitle)

        header_layout.addLayout(title_layout)
        header_layout.addStretch()

        # Username field
        username_label = QLabel("Username:")
        username_label.setStyleSheet(self._get_username_label_stylesheet())
        header_layout.addWidget(username_label)

        self.username_field = QLineEdit()
        self.username_field.setPlaceholderText("Enter your username...")
        self.username_field.setFixedWidth(int(s['control_height_medium'] * 4.4))
        self.username_field.setStyleSheet(self._get_username_field_stylesheet())
        header_layout.addWidget(self.username_field)

        # Show Review toggle
        self.show_review_toggle = QPushButton("👁 Hide Review")
        self.show_review_toggle.setCheckable(True)
        self.show_review_toggle.setChecked(False)  # Not checked = showing
        self.show_review_toggle.setFixedWidth(int(s['control_height_medium'] * 3.3))
        self.show_review_toggle.clicked.connect(self._on_toggle_review)
        self.show_review_toggle.setStyleSheet(self._get_statistics_button_stylesheet())
        header_layout.addWidget(self.show_review_toggle)

        # Show Citations toggle
        self.show_citations_toggle = QPushButton("📚 Hide Citations")
        self.show_citations_toggle.setCheckable(True)
        self.show_citations_toggle.setChecked(False)  # Not checked = showing
        self.show_citations_toggle.setFixedWidth(int(s['control_height_medium'] * 3.8))
        self.show_citations_toggle.clicked.connect(self._on_toggle_citations)
        self.show_citations_toggle.setStyleSheet(self._get_statistics_button_stylesheet())
        header_layout.addWidget(self.show_citations_toggle)

        # Statistics button
        self.statistics_button = QPushButton("📊 Statistics")
        self.statistics_button.setFixedWidth(int(s['control_height_medium'] * 3.3))
        self.statistics_button.clicked.connect(self._on_show_statistics)
        self.statistics_button.setStyleSheet(self._get_statistics_button_stylesheet())
        header_layout.addWidget(self.statistics_button)

        main_layout.addLayout(header_layout)

        # Status section
        status_container = QWidget()
        status_layout = QHBoxLayout(status_container)
        status_layout.setContentsMargins(s['spacing_xlarge'], s['spacing_medium'], s['spacing_xlarge'], s['spacing_medium'])

        self.status_label = QLabel("Initializing fact-checker review interface...")
        self.status_label.setStyleSheet(self._get_status_label_stylesheet('info'))
        status_layout.addWidget(self.status_label)

        status_container.setStyleSheet(self._get_status_container_stylesheet())
        main_layout.addWidget(status_container)

        # Review content (always visible)
        self.review_container = self._build_review_container()
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
        self.statement_label.setStyleSheet(self._get_statement_label_stylesheet())
        self.statement_label.setFixedWidth(int(s['control_height_medium'] * 3.3))
        statement_row.addWidget(self.statement_label)

        # Statement text (read-only, expandable)
        self.statement_text = QLineEdit()
        self.statement_text.setReadOnly(True)
        self.statement_text.setStyleSheet(self._get_statement_input_stylesheet())
        statement_row.addWidget(self.statement_text, stretch=1)

        # Navigation buttons (back/forward arrows)
        self.prev_button = QPushButton("←")
        self.prev_button.setFixedSize(int(s['control_height_medium'] * 1.1), int(s['control_height_medium'] * 1.1))
        self.prev_button.clicked.connect(self._on_previous)
        self.prev_button.setStyleSheet(self._get_nav_button_stylesheet(is_next=False))
        statement_row.addWidget(self.prev_button)

        self.next_button = QPushButton("→")
        self.next_button.setFixedSize(int(s['control_height_medium'] * 1.1), int(s['control_height_medium'] * 1.1))
        self.next_button.clicked.connect(self._on_next)
        self.next_button.setStyleSheet(self._get_nav_button_stylesheet(is_next=True))
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
        original_title.setStyleSheet(self._get_column_title_stylesheet('original'))
        original_layout.addWidget(original_title)

        self.original_tag = QLabel("N/A")
        self.original_tag.setAlignment(Qt.AlignCenter)
        self.original_tag.setFixedHeight(int(s['control_height_small'] * 0.83))
        self.original_tag.setStyleSheet(self._get_tag_initial_stylesheet())
        original_layout.addWidget(self.original_tag)

        self.original_text = QTextEdit()
        self.original_text.setReadOnly(True)
        self.original_text.setPlaceholderText("Original explanation/reasoning from dataset")
        self.original_text.setMinimumHeight(int(s['control_height_medium'] * 2.2))
        self.original_text.setMaximumHeight(int(s['control_height_medium'] * 2.2))
        self.original_text.setStyleSheet(self._get_text_edit_stylesheet())
        original_layout.addWidget(self.original_text)

        original_col.setStyleSheet(self._get_column_stylesheet('original'))
        evaluation_row.addWidget(original_col, stretch=1)

        # Column 2: AI Evaluation
        ai_col = QWidget()
        ai_layout = QVBoxLayout(ai_col)
        ai_layout.setContentsMargins(s['spacing_medium'], s['spacing_medium'], s['spacing_medium'], s['spacing_medium'])
        ai_layout.setSpacing(s['spacing_small'])

        ai_title = QLabel("AI Evaluation")
        ai_title.setStyleSheet(self._get_column_title_stylesheet('ai'))
        ai_layout.addWidget(ai_title)

        self.ai_tag = QLabel("N/A")
        self.ai_tag.setAlignment(Qt.AlignCenter)
        self.ai_tag.setFixedHeight(int(s['control_height_small'] * 0.83))
        self.ai_tag.setStyleSheet(self._get_tag_initial_stylesheet())
        ai_layout.addWidget(self.ai_tag)

        self.ai_text = QTextEdit()
        self.ai_text.setReadOnly(True)
        self.ai_text.setPlaceholderText("AI rationale")
        self.ai_text.setMinimumHeight(int(s['control_height_medium'] * 2.2))
        self.ai_text.setMaximumHeight(int(s['control_height_medium'] * 2.2))
        self.ai_text.setStyleSheet(self._get_text_edit_stylesheet())
        ai_layout.addWidget(self.ai_text)

        ai_col.setStyleSheet(self._get_column_stylesheet('ai'))
        evaluation_row.addWidget(ai_col, stretch=1)

        # Column 3: Human Evaluation
        human_col = QWidget()
        human_layout = QVBoxLayout(human_col)
        human_layout.setContentsMargins(s['spacing_medium'], s['spacing_medium'], s['spacing_medium'], s['spacing_medium'])
        human_layout.setSpacing(s['spacing_small'])

        human_title = QLabel("Human Review")
        human_title.setStyleSheet(self._get_column_title_stylesheet('human'))
        human_layout.addWidget(human_title)

        self.human_dropdown = QComboBox()
        self.human_dropdown.addItem("N/A (Not Yet Annotated)", "n/a")
        self.human_dropdown.addItem("Yes", "yes")
        self.human_dropdown.addItem("No", "no")
        self.human_dropdown.addItem("Maybe", "maybe")
        self.human_dropdown.addItem("Unclear", "unclear")
        self.human_dropdown.setCurrentIndex(0)
        self.human_dropdown.currentIndexChanged.connect(self._on_annotation_change)
        self.human_dropdown.setFixedHeight(int(s['control_height_small'] * 0.83))
        self.human_dropdown.setStyleSheet(self._get_human_dropdown_stylesheet())
        human_layout.addWidget(self.human_dropdown)

        self.human_text = QTextEdit()
        self.human_text.setPlaceholderText("Enter your explanation...")
        self.human_text.textChanged.connect(self._on_annotation_change)
        self.human_text.setMinimumHeight(int(s['control_height_medium'] * 2.2))
        self.human_text.setMaximumHeight(int(s['control_height_medium'] * 2.2))
        self.human_text.setStyleSheet(self._get_human_text_edit_stylesheet())
        human_layout.addWidget(self.human_text)

        human_col.setStyleSheet(self._get_column_stylesheet('human'))
        evaluation_row.addWidget(human_col, stretch=1)

        # Store column widgets for blind mode
        self.original_col = original_col
        self.ai_col = ai_col

        layout.addLayout(evaluation_row)

        # ==============================================================================
        # ROW 3: Original article (fixed height ~12 lines, horizontally expandable)
        # ==============================================================================
        article_label = QLabel("Original Article Context:")
        article_label.setStyleSheet(self._get_section_label_stylesheet())
        layout.addWidget(article_label)

        self.article_text = QTextEdit()
        self.article_text.setReadOnly(True)
        self.article_text.setPlaceholderText("Original article information will be shown here")
        self.article_text.setMinimumHeight(int(s['control_height_medium'] * 4.4))
        self.article_text.setMaximumHeight(int(s['control_height_medium'] * 4.4))
        self.article_text.setStyleSheet(self._get_article_text_stylesheet())
        layout.addWidget(self.article_text)

        # ==============================================================================
        # ROW 4: Citations (both ways expandable) - wrapped in container for toggle
        # ==============================================================================
        self.citations_section = QWidget()
        citations_section_layout = QVBoxLayout(self.citations_section)
        citations_section_layout.setContentsMargins(0, 0, 0, 0)
        citations_section_layout.setSpacing(s['spacing_small'])

        citations_label = QLabel("Supporting Citations:")
        citations_label.setStyleSheet(self._get_section_label_stylesheet())
        citations_section_layout.addWidget(citations_label)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMinimumHeight(int(s['control_height_large'] * 3.75))

        self.citation_widget = CitationListWidget()
        scroll_area.setWidget(self.citation_widget)

        scroll_area.setStyleSheet(self._get_citation_scroll_stylesheet())
        citations_section_layout.addWidget(scroll_area, stretch=1)

        layout.addWidget(self.citations_section, stretch=1)

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
        self.auto_save_label = QLabel(self.AUTO_SAVE_OK_TEXT)
        self.auto_save_label.setStyleSheet(self._get_auto_save_label_stylesheet())
        footer_layout.addWidget(self.auto_save_label)

        layout.addLayout(footer_layout)

        # Apply blind mode if enabled
        if self.blind_mode:
            self._apply_blind_mode()

        return container

    @Slot()
    def _on_username_changed(self):
        """Handle username field changes - switch to that user's annotations."""
        username = self.username_field.text().strip()
        if not username:
            return

        if self._load_failed:
            # Nothing usable is loaded: confirming a username retries the load
            self.annotator_username = username
            self._load_from_database()
            return

        # Don't trigger if nothing is loaded or the username hasn't changed
        if not self.fact_checker_db or username == self.annotator_username:
            return

        # Save current annotation before switching users
        if self.annotator_id and self.current_index < len(self.results):
            self._save_current_annotation()

        # Switch to new user
        try:
            # Check if user already exists
            existing_annotator = self.fact_checker_db.get_annotator(username)

            if not existing_annotator:
                # User doesn't exist - confirm creation
                reply = QMessageBox.question(
                    self,
                    "Create New User?",
                    f"The username '{username}' does not exist in the database.\n\n"
                    f"Do you want to create a new user with this name?\n\n"
                    f"(Click 'No' if this was a typing error)",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No  # Default to No for safety
                )

                if reply == QMessageBox.No:
                    # User cancelled - restore previous username
                    if self.annotator_username:
                        self.username_field.blockSignals(True)
                        self.username_field.setText(self.annotator_username)
                        self.username_field.blockSignals(False)
                    else:
                        self.username_field.clear()
                    return

            self.annotator_username = username

            # Get or create annotator
            annotator = Annotator(
                username=username,
                full_name=username,
                email=None,
                expertise_level=None,
            )
            self.annotator_id = self.fact_checker_db.insert_or_get_annotator(annotator)

            if self.incremental or not self.results:
                # The incremental subset depends on the annotator: reload it
                # rather than re-mapping rows onto the filtered list by index
                self._load_from_database()
                return

            # Reload reviews for this user
            self.reviews = reviews_for_annotator(self.results, self.annotator_id)

            # Reload the database to get fresh annotations
            all_data = self.fact_checker_db.get_all_statements_with_evaluations()
            for i, row in enumerate(all_data):
                if i < len(self.results):
                    self.results[i]['human_annotations'] = row.get('human_annotations', [])

            # Update reviews with fresh data
            self.reviews = reviews_for_annotator(self.results, self.annotator_id)

            # Refresh the current display
            self._display_current_statement()

            self.status_label.setText(f"✓ Switched to user: {username}")
            self.status_label.setStyleSheet(self._get_status_label_stylesheet('success'))

        except Exception as e:
            logger.exception(f"Failed to switch to user '{username}'")
            self._show_status(f"✗ Failed to switch to user '{username}': {e}", 'error')

    def _auto_load_data(self):
        """Auto-load data on startup from the SQLite package or PostgreSQL."""
        # With PostgreSQL and no username given, pick the annotator
        # automatically when there is exactly one
        if self.db_file is None and not self.username_field.text().strip():
            self._autodetect_single_annotator()

        # Get username from text field if set
        username = self.username_field.text().strip()
        if username:
            self.annotator_username = username

        self._load_from_database()

    def _autodetect_single_annotator(self) -> None:
        """Fill the username field if PostgreSQL has exactly one annotator."""
        try:
            temp_db = get_fact_checker_db(self.db_file)
            if not isinstance(temp_db, PostgreSQLFactCheckerDB):
                return
            with temp_db.db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT username FROM factcheck.annotators ORDER BY created_at DESC")
                    annotators = cur.fetchall()

            # If there's exactly one annotator, use it automatically
            if len(annotators) == 1 and self.username_field is not None:
                username = annotators[0][0]
                self.username_field.setText(username)
                self.annotator_username = username
        except Exception as e:
            # Optional convenience: the user can still type a username
            logger.warning(f"Could not check for existing annotators: {e}", exc_info=True)

    def _load_from_database(self):
        """Load fact-check results from database."""
        try:
            self.status_label.setText("Loading from database...")
            self.status_label.setStyleSheet(self._get_status_label_stylesheet('info'))

            # Get database instance
            self.fact_checker_db = get_fact_checker_db(self.db_file)

            # Use the annotator only if it already exists: an unknown name
            # (e.g. a --user typo) must be confirmed before it is created
            unknown_username: Optional[str] = None
            self.annotator_id = None
            if self.annotator_username:
                existing = self.fact_checker_db.get_annotator(self.annotator_username)
                if existing:
                    self.annotator_id = existing.annotator_id
                else:
                    unknown_username = self.annotator_username
                    self.annotator_username = None

            # Load all statements with evaluations
            all_data = self.fact_checker_db.get_all_statements_with_evaluations()

            if not all_data:
                if self.db_type == "sqlite":
                    raise ValueError(
                        "The review package contains no statements; ask for a "
                        "new package (scripts/export_review_package.py)"
                    )
                raise ValueError(
                    "No statements found in database. Import fact-checker data "
                    "first: uv run python fact_checker_cli.py statements.json"
                )

            # Convert to display format
            self.results = []
            for row in all_data:
                result = {
                    'statement_id': row['id'],
                    'statement': row['statement_text'],
                    'expected_answer': row['expected_answer'],
                    'long_answer': row.get('long_answer'),
                    'context': row.get('context'),
                    'input_statement_id': row.get('input_statement_id'),
                    'evaluation': row.get('evaluation'),
                    'reason': row.get('reason'),
                    'degradation_notes': row.get('degradation_notes') or [],
                    'confidence': row.get('confidence'),
                    'evidence_list': [],
                    'human_annotations': row.get('human_annotations', []),
                }

                # Convert evidence
                # Note: Evidence table only has document_id, pmid, doi, citation_text
                # The citation widget will enrich from the main document table using document_id
                for ev in row.get('evidence', []):
                    result['evidence_list'].append({
                        'document_id': ev.get('document_id'),
                        'pmid': ev.get('pmid'),
                        'doi': ev.get('doi'),
                        'passage': ev.get('citation_text', ''),
                        # Leave these empty/None to trigger enrichment
                        'title': None,
                        'abstract': None,
                        'authors': None,
                        'journal': None,
                        'pub_year': None,
                    })

                self.results.append(result)

            # Initialize reviews for the current annotator
            reviews = reviews_for_annotator(self.results, self.annotator_id)
            results = self.results
            total = len(results)
            if self.incremental and self.annotator_id is not None:
                results, reviews = filter_unannotated(results, reviews)
                logger.info(
                    f"Incremental mode: {len(results)} of {total} statements "
                    f"not yet annotated by {self.annotator_username}"
                )
            self.results, self.reviews = results, reviews
            self.current_index = 0
            self._load_failed = False

            if not self.results:
                # Incremental mode with everything annotated: a finished state
                self._show_nothing_to_review(total)
                return

            # Update UI
            mode_indicator = " [INCREMENTAL]" if self.incremental else ""
            db_source = self.db_type.upper()
            if unknown_username:
                self._show_status(
                    f"⚠ Unknown annotator '{unknown_username}': press Enter in the "
                    f"username field to create it (annotations are not recorded "
                    f"until then). Loaded {len(self.results)} statements from "
                    f"{db_source}{mode_indicator}",
                    'error'
                )
            else:
                self._show_status(
                    f"✓ Loaded {len(self.results)} statements from {db_source}{mode_indicator}",
                    'success'
                )

            self._set_review_enabled(True)
            self._display_current_statement()

            self.status_changed.emit(f"Loaded {len(self.results)} statements")

        except Exception as e:
            logger.exception("Failed to load fact-check data")
            self._load_failed = True
            self.results, self.reviews, self.current_index = [], [], 0
            self._set_review_enabled(False)
            self._show_status(
                f"✗ Error loading data: {e} — fix the problem, then press Enter "
                f"in the username field to retry",
                'error'
            )
            self.status_changed.emit(f"Error loading fact-check data: {e}")

    def _show_status(self, text: str, kind: str) -> None:
        """Show a message in the status line.

        Args:
            text: Message text
            kind: 'info', 'success' or 'error' (selects the style)
        """
        if self.status_label is None:
            return
        self.status_label.setText(text)
        self.status_label.setStyleSheet(self._get_status_label_stylesheet(kind))

    def _set_review_enabled(self, enabled: bool) -> None:
        """Enable or disable annotation input and navigation."""
        for widget in (self.human_dropdown, self.human_text, self.prev_button, self.next_button):
            if widget is not None:
                widget.setEnabled(enabled)

    def _show_nothing_to_review(self, total: int) -> None:
        """Show the incremental-mode "all statements annotated" state.

        Args:
            total: Number of statements in the database
        """
        self._set_review_enabled(False)
        if self.statement_label is not None:
            self.statement_label.setText("Nothing left to review")
        if self.statement_text is not None:
            self.statement_text.setText("")
        for text_widget in (self.original_text, self.ai_text, self.human_text, self.article_text):
            if text_widget is not None:
                text_widget.clear()
        if self.citation_widget is not None:
            self.citation_widget.clear()
        if self.timer_widget is not None:
            self.timer_widget.stop()
        self._show_status(
            f"✓ {self.annotator_username} has annotated all {total} statements "
            f"— nothing left to review",
            'success'
        )
        self.status_changed.emit("All statements annotated")

    def _display_current_statement(self):
        """Display the current statement and its annotations."""
        if not self.results or self.current_index >= len(self.results):
            return

        result = self.results[self.current_index]

        # Update statement label and text
        self.statement_label.setText(f"Statement #{self.current_index + 1}:")
        self.statement_text.setText(result.get('statement', 'N/A'))

        # Original answer and AI evaluation columns; never filled in blind
        # mode, so the reviewer cannot see them even if the columns were shown
        if not self.blind_mode:
            original_answer = result.get('expected_answer', 'N/A')
            self._update_tag(self.original_tag, original_answer)
            long_answer = result.get('long_answer', '')
            self.original_text.setPlainText(long_answer if long_answer else 'No explanation available')

            ai_evaluation = result.get('evaluation', 'N/A')
            self._update_tag(self.ai_tag, ai_evaluation)
            self.ai_text.setPlainText(format_ai_rationale(
                result.get('reason'), result.get('degradation_notes')
            ))

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

        # Update original article context (from context field in database)
        article_context = result.get('context', '')
        if not article_context:
            # Fallback: Show input_statement_id if no context available
            input_id = result.get('input_statement_id', '')
            if input_id:
                article_context = f"Original article ID: {input_id}\n\nNo abstract/context available"
            else:
                article_context = "No abstract/context available"
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
        tag_label.setText(value.upper() if value else 'N/A')
        tag_label.setStyleSheet(self._get_tag_stylesheet(value))

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

        if annotation and annotation != "n/a" and not self.annotator_id:
            # Annotators are created only through the username field, which
            # confirms unknown names (a typo must not become a new annotator)
            self._show_status(
                "⚠ Annotation not recorded: enter your username and press Enter first",
                'error'
            )
            return

        if not annotation or annotation == "n/a" or not self.annotator_id:
            # Nothing chosen (or no annotator yet): the schema only accepts
            # yes/no/maybe/unclear, so there is nothing to record
            return

        try:
            result = self.results[self.current_index]
            statement_id = result['statement_id']
            db_annotation = annotation
            # Convert empty string or 'n/a' to None for confidence (database constraint requires NULL not empty string)
            db_confidence = None if (not confidence or confidence == "n/a" or confidence == "") else confidence

            # Create annotation object
            human_annotation = HumanAnnotation(
                statement_id=statement_id,
                annotator_id=self.annotator_id,
                annotation=db_annotation,
                explanation=explanation,
                confidence=db_confidence,
                review_duration_seconds=review_duration,
            )

            # Insert or update (method handles both via ON CONFLICT)
            self.fact_checker_db.insert_human_annotation(human_annotation)

            # Update local review
            self.reviews[self.current_index] = {
                'human_annotation': db_annotation,
                'human_explanation': explanation,
                'confidence': db_confidence,
                'review_duration_seconds': review_duration,
            }
            if self.auto_save_label is not None:
                self.auto_save_label.setText(self.AUTO_SAVE_OK_TEXT)

        except Exception as e:
            logger.exception(f"Failed to save annotation for statement index {self.current_index}")
            self._show_status(f"✗ Annotation NOT saved: {e}", 'error')
            if self.auto_save_label is not None:
                self.auto_save_label.setText(self.AUTO_SAVE_FAILED_TEXT)

    @Slot()
    def _on_previous(self):
        """Navigate to previous statement."""
        if self.current_index > 0:
            # Save current annotation before navigating
            self._save_current_annotation()

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
            # Save current annotation before navigating
            self._save_current_annotation()

            # Reset timer if no annotation
            current_review = self.reviews[self.current_index]
            if not current_review.get('human_annotation'):
                self.timer_widget.reset()

            self.current_index += 1
            self._display_current_statement()

    def _save_current_annotation(self):
        """Save the current annotation from UI widgets to database."""
        # Get current values from widgets
        annotation = self.human_dropdown.currentData()
        explanation = self.human_text.toPlainText()

        # Only record time if an evaluation has been selected
        review_duration = None
        if annotation and annotation != "n/a":
            review_duration = self.timer_widget.get_elapsed_seconds()

        # Save to database
        self._save_annotation(annotation, explanation, "", review_duration)

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

    def _apply_blind_mode(self) -> None:
        """Hide the original and AI columns for unbiased (blind) review.

        The columns are hidden and ``_display_current_statement`` never fills
        them; the review toggle is removed so they cannot be brought back.
        """
        self.show_review_enabled = False
        for column in (self.original_col, self.ai_col):
            if column is not None:
                column.setVisible(False)
        if self.show_review_toggle is not None:
            self.show_review_toggle.setVisible(False)
            self.show_review_toggle.setEnabled(False)

    @Slot()
    def _on_toggle_review(self):
        """Toggle visibility of original and AI review columns."""
        if self.blind_mode:
            return
        # Toggle state
        self.show_review_enabled = not self.show_review_toggle.isChecked()

        # Update button text
        if self.show_review_enabled:
            self.show_review_toggle.setText("👁 Hide Review")
        else:
            self.show_review_toggle.setText("🔒 Show Review")

        # Show/hide the columns
        if self.original_col and self.ai_col:
            self.original_col.setVisible(self.show_review_enabled)
            self.ai_col.setVisible(self.show_review_enabled)

    @Slot()
    def _on_toggle_citations(self):
        """Toggle visibility of citations section."""
        # Toggle state
        self.show_citations_enabled = not self.show_citations_toggle.isChecked()

        # Update button text
        if self.show_citations_enabled:
            self.show_citations_toggle.setText("📚 Hide Citations")
        else:
            self.show_citations_toggle.setText("🔒 Show Citations")

        # Show/hide citations section
        if self.citations_section:
            self.citations_section.setVisible(self.show_citations_enabled)

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
