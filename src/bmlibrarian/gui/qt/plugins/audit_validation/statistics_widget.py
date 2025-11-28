"""
Statistics Widget for Audit Validation GUI.

Displays validation statistics for benchmarking and analysis of
human reviewer agreement with automated evaluations.
"""

import logging
from typing import Optional, Dict, Any, List

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QTableWidget, QTableWidgetItem, QLabel, QGroupBox,
    QPushButton, QHeaderView, QFrame, QScrollArea
)

from bmlibrarian.audit import TargetType, ValidationStatus
from bmlibrarian.gui.qt.resources.styles.stylesheet_generator import StylesheetGenerator
from bmlibrarian.gui.qt.resources.styles.dpi_scale import get_font_scale

from .data_manager import AuditValidationDataManager

logger = logging.getLogger(__name__)


class StatisticsWidget(QWidget):
    """
    Widget displaying validation statistics for benchmarking.

    Shows:
    - Overall validation rates by target type
    - Validation status distribution
    - Error category breakdown
    - Reviewer activity summary
    """

    refresh_requested = Signal()

    def __init__(
        self,
        data_manager: AuditValidationDataManager,
        parent: Optional[QWidget] = None
    ):
        """
        Initialize the statistics widget.

        Args:
            data_manager: Data manager for loading statistics
            parent: Parent widget
        """
        super().__init__(parent)
        self.data_manager = data_manager

        # Styling
        self.scale = get_font_scale()
        self.stylesheet_gen = StylesheetGenerator(self.scale)

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the statistics UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            self.scale['padding_medium'],
            self.scale['padding_medium'],
            self.scale['padding_medium'],
            self.scale['padding_medium']
        )

        # Header with refresh button
        header_layout = QHBoxLayout()

        title = QLabel("Validation Statistics")
        title.setStyleSheet(self.stylesheet_gen.label_stylesheet(
            font_size_key='font_xlarge', bold=True
        ))
        header_layout.addWidget(title)

        header_layout.addStretch()

        refresh_btn = QPushButton("Refresh Statistics")
        refresh_btn.setStyleSheet(self.stylesheet_gen.button_stylesheet(
            bg_color="#2196F3", hover_color="#1976D2"
        ))
        refresh_btn.clicked.connect(self._load_statistics)
        header_layout.addWidget(refresh_btn)

        layout.addLayout(header_layout)

        # Scroll area for statistics content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        content_layout = QVBoxLayout(content)

        # Summary cards
        self.summary_layout = QHBoxLayout()
        content_layout.addLayout(self.summary_layout)

        # Detailed statistics table
        self.stats_group = QGroupBox("Validation by Target Type")
        self.stats_group.setStyleSheet(self.stylesheet_gen.custom("""
            QGroupBox {{
                font-size: {font_medium}pt;
                font-weight: bold;
                border: 1px solid #CCC;
                border-radius: {radius_small}px;
                margin-top: {spacing_medium}px;
                padding: {padding_medium}px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: {padding_medium}px;
            }}
        """))
        stats_layout = QVBoxLayout(self.stats_group)

        self.stats_table = QTableWidget()
        self.stats_table.setColumnCount(8)
        self.stats_table.setHorizontalHeaderLabels([
            "Type", "Total", "Validated", "Incorrect", "Uncertain",
            "Needs Review", "Rate %", "Avg Time (s)"
        ])
        self.stats_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.stats_table.setAlternatingRowColors(True)
        self.stats_table.setStyleSheet(self.stylesheet_gen.custom("""
            QTableWidget {{
                gridline-color: #DDD;
            }}
            QTableWidget::item {{
                padding: {padding_small}px;
            }}
        """))
        stats_layout.addWidget(self.stats_table)

        content_layout.addWidget(self.stats_group)

        # Error category breakdown
        self.categories_group = QGroupBox("Error Categories (for Incorrect Validations)")
        self.categories_group.setStyleSheet(self.stats_group.styleSheet())
        categories_layout = QVBoxLayout(self.categories_group)

        self.categories_table = QTableWidget()
        self.categories_table.setColumnCount(4)
        self.categories_table.setHorizontalHeaderLabels([
            "Type", "Category", "Count", "Percentage"
        ])
        self.categories_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.categories_table.setAlternatingRowColors(True)
        self.categories_table.setStyleSheet(self.stats_table.styleSheet())
        categories_layout.addWidget(self.categories_table)

        content_layout.addWidget(self.categories_group)

        content_layout.addStretch()

        scroll.setWidget(content)
        layout.addWidget(scroll)

    def _load_statistics(self) -> None:
        """Load and display validation statistics."""
        try:
            stats = self.data_manager.get_validation_statistics()
            self._display_summary_cards(stats)
            self._display_stats_table(stats)
            self._load_error_categories()
        except Exception as e:
            logger.error(f"Error loading statistics: {e}")

    def _display_summary_cards(self, stats: Dict[str, Any]) -> None:
        """Display summary cards at the top."""
        # Clear existing cards
        while self.summary_layout.count() > 0:
            child = self.summary_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # Calculate totals
        total_validations = sum(s.get('total_validations', 0) for s in stats.values())
        total_validated = sum(s.get('validated_count', 0) for s in stats.values())
        total_incorrect = sum(s.get('incorrect_count', 0) for s in stats.values())

        overall_rate = 0
        if total_validations > 0:
            overall_rate = 100.0 * total_validated / total_validations

        # Create summary cards
        cards = [
            ("Total Reviewed", str(total_validations), "#2196F3"),
            ("Validated", str(total_validated), "#4CAF50"),
            ("Incorrect", str(total_incorrect), "#F44336"),
            ("Validation Rate", f"{overall_rate:.1f}%", "#9C27B0"),
        ]

        for title, value, color in cards:
            card = self._create_summary_card(title, value, color)
            self.summary_layout.addWidget(card)

        self.summary_layout.addStretch()

    def _create_summary_card(self, title: str, value: str, color: str) -> QFrame:
        """
        Create a summary card widget.

        Args:
            title: Card title text
            value: Card value text
            color: Background color for the card

        Returns:
            QFrame widget with styled content
        """
        card = QFrame()
        card.setStyleSheet(self.stylesheet_gen.custom("""
            QFrame {{
                background-color: {bg_color};
                border-radius: {radius_medium}px;
                padding: {padding_medium}px;
            }}
        """.replace("{bg_color}", color)))
        card.setMinimumWidth(self.scale['control_width_small'])
        card.setMaximumWidth(self.scale['control_width_medium'])

        layout = QVBoxLayout(card)

        value_label = QLabel(value)
        value_label.setStyleSheet(self.stylesheet_gen.label_stylesheet(
            font_size_key='font_xlarge', bold=True, color="white"
        ))
        value_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(value_label)

        title_label = QLabel(title)
        title_label.setStyleSheet(self.stylesheet_gen.label_stylesheet(
            font_size_key='font_small', color="rgba(255, 255, 255, 0.9)"
        ))
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        return card

    def _display_stats_table(self, stats: Dict[str, Any]) -> None:
        """Display statistics in the table."""
        self.stats_table.setRowCount(len(stats))

        for row, (target_type, data) in enumerate(stats.items()):
            self.stats_table.setItem(row, 0, QTableWidgetItem(target_type.title()))
            self.stats_table.setItem(row, 1, QTableWidgetItem(str(data.get('total_validations', 0))))
            self.stats_table.setItem(row, 2, QTableWidgetItem(str(data.get('validated_count', 0))))
            self.stats_table.setItem(row, 3, QTableWidgetItem(str(data.get('incorrect_count', 0))))
            self.stats_table.setItem(row, 4, QTableWidgetItem(str(data.get('uncertain_count', 0))))
            self.stats_table.setItem(row, 5, QTableWidgetItem(str(data.get('needs_review_count', 0))))
            self.stats_table.setItem(row, 6, QTableWidgetItem(f"{data.get('validation_rate_percent', 0):.1f}"))

            avg_time = data.get('avg_review_time_seconds')
            time_str = f"{avg_time:.1f}" if avg_time else "-"
            self.stats_table.setItem(row, 7, QTableWidgetItem(time_str))

            # Color code the validation rate
            rate = data.get('validation_rate_percent', 0)
            if rate >= 90:
                self.stats_table.item(row, 6).setBackground(Qt.green)
            elif rate >= 70:
                self.stats_table.item(row, 6).setBackground(Qt.yellow)
            elif rate < 70 and data.get('total_validations', 0) > 0:
                self.stats_table.item(row, 6).setBackground(Qt.red)

    def _load_error_categories(self) -> None:
        """Load error category statistics."""
        try:
            # Query the error categories view
            with self.data_manager.conn.cursor() as cur:
                cur.execute("""
                    SELECT target_type, category_name, error_count, percentage_of_errors
                    FROM audit.v_validation_error_categories
                    WHERE error_count > 0
                    ORDER BY target_type, error_count DESC
                """)
                rows = cur.fetchall()

                self.categories_table.setRowCount(len(rows))
                for row_idx, (target_type, category, count, pct) in enumerate(rows):
                    self.categories_table.setItem(row_idx, 0, QTableWidgetItem(target_type.title()))
                    self.categories_table.setItem(row_idx, 1, QTableWidgetItem(category))
                    self.categories_table.setItem(row_idx, 2, QTableWidgetItem(str(count)))
                    pct_str = f"{pct:.1f}%" if pct else "-"
                    self.categories_table.setItem(row_idx, 3, QTableWidgetItem(pct_str))

        except Exception as e:
            logger.error(f"Error loading error categories: {e}")
            self.categories_table.setRowCount(1)
            self.categories_table.setItem(0, 0, QTableWidgetItem("Error loading data"))

    def refresh(self) -> None:
        """Public method to refresh statistics."""
        self._load_statistics()
