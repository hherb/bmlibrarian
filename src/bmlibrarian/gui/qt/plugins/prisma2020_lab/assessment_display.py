"""
Assessment display widgets and functions for PRISMA 2020 Lab.

Contains factory functions for creating assessment result display widgets
including suitability sections, overall compliance, and criteria tables.
"""

import logging
from typing import List, Tuple

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QSizePolicy
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor

from bmlibrarian.agents.prisma2020_agent import PRISMA2020Assessment
from ...resources.styles import StylesheetGenerator, scale_px, get_font_scale
from .constants import ITEM_LABELS, SEPARATOR_COLOR
from .score_utils import (
    get_score_color,
    get_score_text,
    get_compliance_color,
    get_compliance_bg_color,
    format_compliance_stats,
    format_document_type_display,
)

logger = logging.getLogger(__name__)


def extract_assessment_items(assessment: PRISMA2020Assessment) -> List[Tuple[int, str, float, str]]:
    """
    Extract all 27 PRISMA 2020 items from assessment as tuples.

    Args:
        assessment: PRISMA2020Assessment object

    Returns:
        List of tuples (item_num, item_name, score, explanation)
    """
    a = assessment
    return [
        (1, ITEM_LABELS[1], a.title_score, a.title_explanation),
        (2, ITEM_LABELS[2], a.abstract_score, a.abstract_explanation),
        (3, ITEM_LABELS[3], a.rationale_score, a.rationale_explanation),
        (4, ITEM_LABELS[4], a.objectives_score, a.objectives_explanation),
        (5, ITEM_LABELS[5], a.eligibility_criteria_score, a.eligibility_criteria_explanation),
        (6, ITEM_LABELS[6], a.information_sources_score, a.information_sources_explanation),
        (7, ITEM_LABELS[7], a.search_strategy_score, a.search_strategy_explanation),
        (8, ITEM_LABELS[8], a.selection_process_score, a.selection_process_explanation),
        (9, ITEM_LABELS[9], a.data_collection_score, a.data_collection_explanation),
        (10, ITEM_LABELS[10], a.data_items_score, a.data_items_explanation),
        (11, ITEM_LABELS[11], a.risk_of_bias_score, a.risk_of_bias_explanation),
        (12, ITEM_LABELS[12], a.effect_measures_score, a.effect_measures_explanation),
        (13, ITEM_LABELS[13], a.synthesis_methods_score, a.synthesis_methods_explanation),
        (14, ITEM_LABELS[14], a.reporting_bias_assessment_score, a.reporting_bias_assessment_explanation),
        (15, ITEM_LABELS[15], a.certainty_assessment_score, a.certainty_assessment_explanation),
        (16, ITEM_LABELS[16], a.study_selection_score, a.study_selection_explanation),
        (17, ITEM_LABELS[17], a.study_characteristics_score, a.study_characteristics_explanation),
        (18, ITEM_LABELS[18], a.risk_of_bias_results_score, a.risk_of_bias_results_explanation),
        (19, ITEM_LABELS[19], a.individual_studies_results_score, a.individual_studies_results_explanation),
        (20, ITEM_LABELS[20], a.synthesis_results_score, a.synthesis_results_explanation),
        (21, ITEM_LABELS[21], a.reporting_biases_results_score, a.reporting_biases_results_explanation),
        (22, ITEM_LABELS[22], a.certainty_of_evidence_score, a.certainty_of_evidence_explanation),
        (23, ITEM_LABELS[23], a.discussion_score, a.discussion_explanation),
        (24, ITEM_LABELS[24], a.limitations_score, a.limitations_explanation),
        (25, ITEM_LABELS[25], a.conclusions_score, a.conclusions_explanation),
        (26, ITEM_LABELS[26], a.registration_score, a.registration_explanation),
        (27, ITEM_LABELS[27], a.support_score, a.support_explanation),
    ]


def create_suitability_section(
    assessment: PRISMA2020Assessment,
    stylesheet_gen: StylesheetGenerator
) -> QGroupBox:
    """
    Create suitability assessment section widget.

    Args:
        assessment: PRISMA2020Assessment object
        stylesheet_gen: StylesheetGenerator for styling

    Returns:
        QGroupBox widget displaying suitability information
    """
    section = QGroupBox("📋 Document Suitability")
    section.setStyleSheet(
        stylesheet_gen.card_stylesheet(bg_color='#E3F2FD')
    )
    layout = QVBoxLayout(section)
    layout.setSpacing(scale_px(8))

    # Document type display
    doc_type_text = format_document_type_display(
        assessment.is_systematic_review,
        assessment.is_meta_analysis
    )
    has_valid_type = assessment.is_systematic_review or assessment.is_meta_analysis

    type_label = QLabel(doc_type_text)
    type_label.setFont(QFont("", 10, QFont.Bold))
    type_label.setStyleSheet(
        stylesheet_gen.label_stylesheet(
            font_size_key='font_medium',
            color='#1976D2' if has_valid_type else '#D32F2F',
            bold=True
        )
    )
    layout.addWidget(type_label)

    # Rationale
    rationale_label = QLabel(assessment.suitability_rationale)
    rationale_label.setWordWrap(True)
    rationale_label.setStyleSheet(
        stylesheet_gen.label_stylesheet(
            font_size_key='font_medium',
            color='#424242'
        )
    )
    layout.addWidget(rationale_label)

    return section


def create_overall_section(
    assessment: PRISMA2020Assessment,
    stylesheet_gen: StylesheetGenerator
) -> QGroupBox:
    """
    Create overall compliance section widget.

    Args:
        assessment: PRISMA2020Assessment object
        stylesheet_gen: StylesheetGenerator for styling

    Returns:
        QGroupBox widget displaying overall compliance summary
    """
    category = assessment.get_compliance_category()
    bg_color = get_compliance_bg_color(category)

    section = QGroupBox("⭐ Overall Compliance")
    section.setStyleSheet(
        stylesheet_gen.card_stylesheet(bg_color=bg_color)
    )
    layout = QVBoxLayout(section)
    layout.setSpacing(scale_px(8))

    # Compliance score row
    score_row = QHBoxLayout()
    score_label = QLabel("Compliance Score:")
    score_label.setFont(QFont("", 10, QFont.Bold))

    compliance_color = get_compliance_color(assessment.overall_compliance_percentage)
    score_value = QLabel(
        f"{assessment.overall_compliance_percentage:.1f}% "
        f"({assessment.overall_compliance_score:.2f}/2.0)"
    )
    score_value.setStyleSheet(
        stylesheet_gen.label_stylesheet(
            font_size_key='font_large',
            color=compliance_color,
            bold=True
        )
    )
    score_row.addWidget(score_label)
    score_row.addWidget(score_value)
    score_row.addStretch()
    layout.addLayout(score_row)

    # Category row
    category_row = QHBoxLayout()
    category_label = QLabel("Category:")
    category_label.setFont(QFont("", 10, QFont.Bold))
    category_value = QLabel(category)
    category_value.setStyleSheet(
        stylesheet_gen.label_stylesheet(
            font_size_key='font_medium',
            color=compliance_color,
            bold=True
        )
    )
    category_row.addWidget(category_label)
    category_row.addWidget(category_value)
    category_row.addStretch()
    layout.addLayout(category_row)

    # Statistics
    stats_text = format_compliance_stats(
        assessment.total_applicable_items,
        assessment.fully_reported_items,
        assessment.partially_reported_items,
        assessment.not_reported_items
    )
    stats_label = QLabel(stats_text)
    stats_label.setStyleSheet(
        stylesheet_gen.label_stylesheet(
            font_size_key='font_small',
            color='gray'
        )
    )
    layout.addWidget(stats_label)

    return section


def create_criteria_table(
    assessment: PRISMA2020Assessment,
    stylesheet_gen: StylesheetGenerator
) -> QGroupBox:
    """
    Create tabular display of all PRISMA 2020 criteria.

    Args:
        assessment: PRISMA2020Assessment object
        stylesheet_gen: StylesheetGenerator for styling

    Returns:
        QGroupBox widget containing criteria table
    """
    section = QGroupBox("📋 PRISMA 2020 Checklist")
    section.setStyleSheet(
        stylesheet_gen.card_stylesheet(bg_color='#FFFFFF')
    )
    section.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    layout = QVBoxLayout(section)
    layout.setSpacing(scale_px(10))
    layout.setContentsMargins(scale_px(10), scale_px(10), scale_px(10), scale_px(10))

    # Create table
    table = QTableWidget()
    table.setColumnCount(4)
    table.setHorizontalHeaderLabels(["#", "Criterion", "Status", "Explanation"])

    # Extract and populate items
    items = extract_assessment_items(assessment)
    table.setRowCount(len(items))

    for row, (item_num, item_name, score, explanation) in enumerate(items):
        _populate_table_row(table, row, item_num, item_name, score, explanation)

    # Configure table appearance
    _configure_table_appearance(table)

    layout.addWidget(table, stretch=1)

    return section


def _populate_table_row(
    table: QTableWidget,
    row: int,
    item_num: int,
    item_name: str,
    score: float,
    explanation: str
) -> None:
    """
    Populate a single row in the criteria table.

    Args:
        table: QTableWidget to populate
        row: Row index
        item_num: PRISMA item number
        item_name: PRISMA item name
        score: Score value
        explanation: Explanation text
    """
    # Column 0: Item number
    num_item = QTableWidgetItem(str(item_num))
    num_item.setTextAlignment(Qt.AlignCenter)
    num_item.setFlags(num_item.flags() & ~Qt.ItemIsEditable)
    table.setItem(row, 0, num_item)

    # Column 1: Criterion name
    name_item = QTableWidgetItem(item_name)
    name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
    name_item.setFont(QFont("", 10, QFont.Bold))
    table.setItem(row, 1, name_item)

    # Column 2: Status with color coding
    status_text = get_score_text(score)
    status_item = QTableWidgetItem(status_text)
    status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)
    status_item.setTextAlignment(Qt.AlignCenter)

    # Set background color based on score
    color = get_score_color(score)
    status_item.setBackground(QColor(color))
    status_item.setForeground(QColor('white'))
    status_item.setFont(QFont("", 10, QFont.Bold))
    table.setItem(row, 2, status_item)

    # Column 3: Explanation
    explanation_item = QTableWidgetItem(explanation)
    explanation_item.setFlags(explanation_item.flags() & ~Qt.ItemIsEditable)
    table.setItem(row, 3, explanation_item)


def _configure_table_appearance(table: QTableWidget) -> None:
    """
    Configure table appearance and column sizing.

    Args:
        table: QTableWidget to configure
    """
    table.setAlternatingRowColors(True)
    table.setShowGrid(True)
    table.verticalHeader().setVisible(False)

    # Set column widths
    table.setColumnWidth(0, scale_px(40))   # Item number - narrow
    table.setColumnWidth(1, scale_px(200))  # Criterion name - medium
    table.setColumnWidth(2, scale_px(150))  # Status - medium

    # Explanation column stretches to fill remaining space
    header = table.horizontalHeader()
    header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
    header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
    header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
    header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

    # Set row heights to accommodate text
    table.verticalHeader().setDefaultSectionSize(scale_px(60))

    # Enable text wrapping for explanation column
    table.setWordWrap(True)

    # Set size policy to expand and fill all available space
    table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)


def create_item_row(
    item_num: int,
    label: str,
    score: float,
    explanation: str,
    stylesheet_gen: StylesheetGenerator
) -> QWidget:
    """
    Create a checklist item row with score badge and explanation.

    This is used for the legacy non-tabular display format.

    Args:
        item_num: PRISMA item number (1-27)
        label: Item label text
        score: Score value (0.0, 1.0, or 2.0)
        explanation: Explanation text
        stylesheet_gen: StylesheetGenerator for styling

    Returns:
        QWidget containing the formatted item row
    """
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(scale_px(10), scale_px(5), scale_px(10), scale_px(5))
    layout.setSpacing(scale_px(3))

    # Header row with item number, label, and score
    header_row = QHBoxLayout()

    item_label = QLabel(f"Item {item_num}: {label}")
    item_label.setFont(QFont("", 10, QFont.Bold))

    score_badge = QLabel(get_score_text(score))
    score_badge.setAlignment(Qt.AlignCenter)
    score_badge.setFixedWidth(scale_px(120))
    s = get_font_scale()
    score_badge.setStyleSheet(
        f"""
            QLabel {{
                background-color: {get_score_color(score)};
                color: white;
                font-weight: bold;
                font-size: {s['font_small']}pt;
                padding: {s['padding_tiny']}px;
                border-radius: {s['radius_small']}px;
            }}
        """
    )

    header_row.addWidget(item_label)
    header_row.addStretch()
    header_row.addWidget(score_badge)

    # Explanation
    explanation_label = QLabel(explanation)
    explanation_label.setWordWrap(True)
    explanation_label.setStyleSheet(
        stylesheet_gen.label_stylesheet(
            font_size_key='font_small',
            color='#424242'
        )
    )

    layout.addLayout(header_row)
    layout.addWidget(explanation_label)

    # Add separator line
    separator = QWidget()
    separator.setFixedHeight(1)
    separator.setStyleSheet(f"background-color: {SEPARATOR_COLOR};")
    layout.addWidget(separator)

    return widget
