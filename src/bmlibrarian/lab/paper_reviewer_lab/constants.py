"""
Paper Reviewer Lab Constants

UI constants, step definitions, and dimensions for the Paper Reviewer Lab.
All dimensions are relative or DPI-scaled following BMLibrarian guidelines.
"""

from typing import Dict, List, Tuple

# Version
VERSION = "1.0.0"

# Window dimension multipliers (relative to DPI scale)
# Actual pixel values are calculated at runtime using dpi_scale
WINDOW_MIN_WIDTH_MULTIPLIER = 60  # ~1000px at 100% DPI
WINDOW_MIN_HEIGHT_MULTIPLIER = 42  # ~700px at 100% DPI
WINDOW_DEFAULT_WIDTH_MULTIPLIER = 72  # ~1200px at 100% DPI
WINDOW_DEFAULT_HEIGHT_MULTIPLIER = 48  # ~800px at 100% DPI

# Panel width ratios
INPUT_PANEL_RATIO = 0.35
WORKFLOW_PANEL_RATIO = 0.35
RESULTS_PANEL_RATIO = 0.30

# Tab indices (for single-window tabbed interface)
TAB_INPUT = 0
TAB_PDF = 1
TAB_WORKFLOW = 2
TAB_RESULTS = 3

# Step definitions with internal name and display name
WORKFLOW_STEPS: List[Tuple[str, str]] = [
    ("resolve_input", "Resolving Input"),
    ("generate_summary", "Generating Summary"),
    ("extract_hypothesis", "Extracting Hypothesis"),
    ("detect_study_type", "Detecting Study Type"),
    ("pico_assessment", "PICO Analysis"),
    ("prisma_assessment", "PRISMA Assessment"),
    ("paper_weight", "Paper Weight Assessment"),
    ("study_assessment", "Study Quality Assessment"),
    ("synthesize_strengths", "Synthesizing Strengths/Weaknesses"),
    ("search_contradictory", "Searching for Contradictory Evidence"),
    ("compile_report", "Compiling Final Report"),
]

# Step weights for progress estimation (sum should be 1.0)
STEP_WEIGHTS: Dict[str, float] = {
    "resolve_input": 0.05,
    "generate_summary": 0.10,
    "extract_hypothesis": 0.08,
    "detect_study_type": 0.05,
    "pico_assessment": 0.12,
    "prisma_assessment": 0.12,
    "paper_weight": 0.15,
    "study_assessment": 0.12,
    "synthesize_strengths": 0.05,
    "search_contradictory": 0.12,
    "compile_report": 0.04,
}

# Step status values
STATUS_PENDING = "pending"
STATUS_IN_PROGRESS = "in_progress"
STATUS_COMPLETED = "completed"
STATUS_SKIPPED = "skipped"
STATUS_FAILED = "failed"

# Status colors (CSS/Qt compatible hex colors)
STATUS_COLORS: Dict[str, str] = {
    STATUS_PENDING: "#808080",      # Gray
    STATUS_IN_PROGRESS: "#1E90FF",  # Dodger Blue
    STATUS_COMPLETED: "#32CD32",    # Lime Green
    STATUS_SKIPPED: "#FFA500",      # Orange
    STATUS_FAILED: "#DC143C",       # Crimson
}

# Input type identifiers
INPUT_TYPE_DOI = "doi"
INPUT_TYPE_PMID = "pmid"
INPUT_TYPE_PDF = "pdf"
INPUT_TYPE_TEXT = "text"
INPUT_TYPE_FILE = "file"

# File filter for PDF selection
PDF_FILE_FILTER = "PDF Files (*.pdf);;All Files (*)"
TEXT_FILE_FILTER = "Text Files (*.txt *.md *.markdown);;All Files (*)"

# Export formats
EXPORT_FORMAT_MARKDOWN = "markdown"
EXPORT_FORMAT_PDF = "pdf"
EXPORT_FORMAT_JSON = "json"

EXPORT_FILE_FILTERS = {
    EXPORT_FORMAT_MARKDOWN: "Markdown Files (*.md);;All Files (*)",
    EXPORT_FORMAT_PDF: "PDF Files (*.pdf);;All Files (*)",
    EXPORT_FORMAT_JSON: "JSON Files (*.json);;All Files (*)",
}

# Animation durations (milliseconds)
PROGRESS_UPDATE_INTERVAL_MS = 100
STEP_EXPAND_ANIMATION_MS = 200

# Validation patterns
DOI_PATTERN = r'^10\.\d{4,}/\S+$'
PMID_PATTERN = r'^\d{1,9}$'


__all__ = [
    'VERSION',
    'WINDOW_MIN_WIDTH_MULTIPLIER',
    'WINDOW_MIN_HEIGHT_MULTIPLIER',
    'WINDOW_DEFAULT_WIDTH_MULTIPLIER',
    'WINDOW_DEFAULT_HEIGHT_MULTIPLIER',
    'INPUT_PANEL_RATIO',
    'WORKFLOW_PANEL_RATIO',
    'RESULTS_PANEL_RATIO',
    'TAB_INPUT',
    'TAB_PDF',
    'TAB_WORKFLOW',
    'TAB_RESULTS',
    'WORKFLOW_STEPS',
    'STEP_WEIGHTS',
    'STATUS_PENDING',
    'STATUS_IN_PROGRESS',
    'STATUS_COMPLETED',
    'STATUS_SKIPPED',
    'STATUS_FAILED',
    'STATUS_COLORS',
    'INPUT_TYPE_DOI',
    'INPUT_TYPE_PMID',
    'INPUT_TYPE_PDF',
    'INPUT_TYPE_TEXT',
    'INPUT_TYPE_FILE',
    'PDF_FILE_FILTER',
    'TEXT_FILE_FILTER',
    'EXPORT_FORMAT_MARKDOWN',
    'EXPORT_FORMAT_PDF',
    'EXPORT_FORMAT_JSON',
    'EXPORT_FILE_FILTERS',
    'PROGRESS_UPDATE_INTERVAL_MS',
    'STEP_EXPAND_ANIMATION_MS',
    'DOI_PATTERN',
    'PMID_PATTERN',
]
