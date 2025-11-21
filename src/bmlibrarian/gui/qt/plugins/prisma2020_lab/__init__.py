"""
PRISMA 2020 Lab Plugin for BMLibrarian Qt GUI.

This plugin provides an interactive interface for assessing systematic reviews
and meta-analyses against PRISMA 2020 reporting guidelines.

Module Structure:
    - prisma2020_lab_tab: Main tab widget (PRISMA2020LabTabWidget)
    - worker: Background assessment worker thread
    - assessment_display: Assessment result display widgets
    - ui_builders: UI panel builder functions
    - score_utils: Pure functions for score/color calculations
    - constants: Configuration constants and color schemes
    - plugin: Plugin registration for Qt GUI
"""

from .prisma2020_lab_tab import PRISMA2020LabTabWidget
from .worker import PRISMA2020AssessmentWorker
from .score_utils import (
    get_score_color,
    get_score_text,
    get_compliance_color,
    get_compliance_bg_color,
    format_compliance_stats,
    format_document_type_display,
)
from .assessment_display import (
    create_suitability_section,
    create_overall_section,
    create_criteria_table,
    create_item_row,
    extract_assessment_items,
)
from .ui_builders import (
    UIComponents,
    create_header,
    create_input_panel,
    create_document_panel,
    create_assessment_panel,
    create_status_label,
    clear_layout,
)

__all__ = [
    # Main widget
    "PRISMA2020LabTabWidget",
    # Worker
    "PRISMA2020AssessmentWorker",
    # Score utilities
    "get_score_color",
    "get_score_text",
    "get_compliance_color",
    "get_compliance_bg_color",
    "format_compliance_stats",
    "format_document_type_display",
    # Assessment display
    "create_suitability_section",
    "create_overall_section",
    "create_criteria_table",
    "create_item_row",
    "extract_assessment_items",
    # UI builders
    "UIComponents",
    "create_header",
    "create_input_panel",
    "create_document_panel",
    "create_assessment_panel",
    "create_status_label",
    "clear_layout",
]
