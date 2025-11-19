"""Constants for PRISMA 2020 Lab plugin."""

# UI Layout Constants
DEFAULT_SPLITTER_SIZES = [400, 600]  # 40% document panel, 60% assessment panel
DOC_ID_INPUT_WIDTH = 200  # Pixels (before scaling)
LOAD_BUTTON_WIDTH = 150
LOAD_BUTTON_HEIGHT = 35
CLEAR_BUTTON_WIDTH = 80
CLEAR_BUTTON_HEIGHT = 35
REFRESH_BUTTON_WIDTH = 80
MODEL_COMBO_MIN_WIDTH = 300
SCORE_BADGE_WIDTH = 120

# Database Constants
DOC_ID_MIN_VALUE = 1
DOC_ID_MAX_VALUE = 2147483647  # PostgreSQL INTEGER type maximum (INT_MAX)

# Color Schemes
SCORE_COLORS = {
    0.0: '#D32F2F',    # Red - Not reported
    1.0: '#F57C00',    # Orange - Partially reported
    2.0: '#388E3C',    # Green - Fully reported
}

COMPLIANCE_COLORS = {
    'excellent': '#1B5E20',     # Dark green (≥90%)
    'good': '#388E3C',          # Green (75-89%)
    'adequate': '#F57C00',      # Orange (60-74%)
    'poor': '#E65100',          # Dark orange (40-59%)
    'very_poor': '#B71C1C',     # Dark red (<40%)
}

SECTION_COLORS = {
    'title': '#1976D2',
    'info': '#1976D2',
    'success': '#2E7D32',
    'error': '#C62828',
}

# Section Background Colors (for compliance display)
COMPLIANCE_BG_COLORS = {
    'excellent': '#E8F5E9',     # Light green
    'good': '#F1F8E9',          # Light lime
    'adequate': '#FFF3E0',      # Light orange
    'poor': '#FFE0B2',          # Darker light orange
    'very_poor': '#FFEBEE',     # Light red
}

# Assessment Settings
MIN_CONFIDENCE_LAB_MODE = 0.0  # Lab mode shows all assessments regardless of confidence

# Score Thresholds
SCORE_FULLY_REPORTED_THRESHOLD = 1.9
SCORE_PARTIALLY_REPORTED_THRESHOLD = 0.9

# Compliance Percentage Thresholds
COMPLIANCE_EXCELLENT_THRESHOLD = 90.0
COMPLIANCE_GOOD_THRESHOLD = 75.0
COMPLIANCE_ADEQUATE_THRESHOLD = 60.0
COMPLIANCE_POOR_THRESHOLD = 40.0

# Agent Configuration
DEFAULT_PRISMA_MODEL = "gpt-oss:20b"
DEFAULT_TEMPERATURE = 0.1
DEFAULT_TOP_P = 0.9
DEFAULT_MAX_TOKENS = 4000
DEFAULT_MAX_WORKERS = 2

# UI Text Constants
WINDOW_TITLE = "PRISMA 2020 Laboratory"
WINDOW_SUBTITLE = "Assess systematic reviews and meta-analyses against PRISMA 2020 reporting guidelines"
NO_DOCUMENT_LOADED = "No document loaded"
NO_ABSTRACT_AVAILABLE = "No abstract available"
ASSESSMENT_PLACEHOLDER = "Assessment results will appear here after loading a document."
DOC_ID_PLACEHOLDER = "Enter document ID (e.g., 12345)"

# Status Messages
STATUS_READY = "Ready"
STATUS_LOADING_DOCUMENT = "Loading document {}..."
STATUS_RUNNING_ASSESSMENT = "Running PRISMA 2020 assessment..."
STATUS_ASSESSMENT_COMPLETE = "✓ Assessment complete ({:.1f}% compliance)"
STATUS_ASSESSMENT_FAILED = "Assessment failed"
STATUS_AGENT_UNAVAILABLE = "Agent unavailable"
STATUS_DB_CONNECTION_FAILED = "Database connection failed"
STATUS_CLEARED = "Cleared all fields"

# Error Messages
ERROR_NO_DOC_ID = "Please enter a document ID."
ERROR_INVALID_DOC_ID = "Invalid document ID. Please enter a number."
ERROR_DOC_NOT_FOUND = "Document {} not found in database."
ERROR_AGENT_NOT_INITIALIZED = "PRISMA Agent not initialized. Cannot perform assessment."
ERROR_ASSESSMENT_FAILED = "PRISMA 2020 assessment failed: {}"
ERROR_DB_CONNECTION = "Failed to connect to database: {}"
ERROR_UNEXPECTED = "Unexpected error: {}"
ERROR_NO_OLLAMA_CONNECTION = "Failed to connect to Ollama: {}\n\nPlease ensure Ollama is running."
ERROR_MODEL_REFRESH = "Unexpected error while refreshing models: {}"
ERROR_MODEL_SWITCH = "Failed to switch model: {}"
ERROR_MISSING_CONFIG = "Missing required configuration: {}"

# Success Messages
SUCCESS_MODEL_REFRESH = "Refreshed models - {} available"
SUCCESS_MODEL_SWITCH = "Switched to model: {}"
SUCCESS_ASSESSMENT = "PRISMA 2020 assessment complete - {:.1f}% compliance"

# PRISMA 2020 Section Names
SECTION_TITLE_ABSTRACT = "1. TITLE AND ABSTRACT"
SECTION_INTRODUCTION = "2. INTRODUCTION"
SECTION_METHODS = "3. METHODS"
SECTION_RESULTS = "4. RESULTS"
SECTION_DISCUSSION = "5. DISCUSSION"
SECTION_OTHER_INFO = "6. OTHER INFORMATION"

# PRISMA 2020 Item Labels
ITEM_LABELS = {
    1: "Title",
    2: "Abstract",
    3: "Rationale",
    4: "Objectives",
    5: "Eligibility Criteria",
    6: "Information Sources",
    7: "Search Strategy",
    8: "Selection Process",
    9: "Data Collection",
    10: "Data Items",
    11: "Risk of Bias Assessment",
    12: "Effect Measures",
    13: "Synthesis Methods",
    14: "Reporting Bias Assessment",
    15: "Certainty Assessment",
    16: "Study Selection",
    17: "Study Characteristics",
    18: "Risk of Bias Results",
    19: "Individual Studies Results",
    20: "Synthesis Results",
    21: "Reporting Biases Results",
    22: "Certainty of Evidence",
    23: "Discussion",
    24: "Limitations",
    25: "Conclusions",
    26: "Registration & Protocol",
    27: "Support & Funding",
}

# Score Display Symbols
SYMBOL_FULLY_REPORTED = "✓"
SYMBOL_PARTIALLY_REPORTED = "◐"
SYMBOL_NOT_REPORTED = "✗"
SYMBOL_SYSTEMATIC_REVIEW = "✓"
SYMBOL_META_ANALYSIS = "✓"
