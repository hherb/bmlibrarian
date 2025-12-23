"""
Constants for the Setup Wizard module.

Defines all magic numbers and configuration values used throughout the wizard.
Following golden rule #2: No magic numbers.
"""

# Database connection defaults
DEFAULT_POSTGRES_HOST = "localhost"
DEFAULT_POSTGRES_PORT = "5432"
DEFAULT_OLLAMA_HOST = "http://localhost:11434"

# Connection timeout in seconds
DB_CONNECTION_TIMEOUT_SECONDS = 10

# Import settings
# Note: medRxiv launched June 6, 2019 - the importer will clamp dates before this
MEDRXIV_DEFAULT_DAYS = 7
MEDRXIV_MIN_DAYS = 1
MEDRXIV_MAX_DAYS = 365
MEDRXIV_FULL_IMPORT_DAYS = 2500  # Full historical import (importer clamps to launch date)

PUBMED_DEFAULT_MAX_RESULTS = 100
PUBMED_MIN_RESULTS = 10
PUBMED_MAX_RESULTS = 10000
PUBMED_TEST_QUERY = "COVID-19 vaccine"

# UI display limits
TABLE_DISPLAY_LIMIT = 10  # Max tables to show in warning message

# UI size multipliers (relative to scale values)
SQL_TEXT_HEIGHT_MULTIPLIER = 3  # For SQL command text area
LOG_TEXT_HEIGHT_MULTIPLIER = 2  # For import log text area
WIZARD_WIDTH_MULTIPLIER = 2  # Wizard width relative to control_width_xlarge
WIZARD_HEIGHT_RATIO = 0.8  # Wizard height as ratio of width

# Progress percentages for quick test import
PROGRESS_MEDRXIV_START = 10
PROGRESS_PUBMED_START = 40
PROGRESS_MESH_START = 70
PROGRESS_COMPLETE = 100

# Required PostgreSQL extensions
REQUIRED_EXTENSIONS = ["vector", "plpython3u", "pg_trgm"]

# MeSH import settings
MESH_DEFAULT_YEAR = 2025
MESH_MIN_YEAR = 2020
MESH_MAX_YEAR = 2030
MESH_ESTIMATED_SIZE_MB = 400  # Approximate download size with SCRs
MESH_ESTIMATED_SIZE_NO_SCR_MB = 180  # Without supplementary concepts

# Color constants for status messages (HTML colors)
COLOR_ERROR = "#D32F2F"
COLOR_WARNING = "#FF9800"
COLOR_SUCCESS = "#4CAF50"
COLOR_MUTED = "#666666"

# Frame background colors
FRAME_NOTE_BG = "#FFF3E0"
FRAME_NOTE_BORDER = "#FFB74D"
FRAME_WARNING_BG = "#FFEBEE"
FRAME_WARNING_BORDER = "#EF5350"
FRAME_SUCCESS_BG = "#E8F5E9"
FRAME_SUCCESS_BORDER = "#66BB6A"
FRAME_METADATA_BG = "#F5F5F5"
FRAME_METADATA_BORDER = "#E0E0E0"

# Splitter size ratios (as percentages)
SPLITTER_LIST_RATIO = 40  # Document list takes 40% of width
SPLITTER_PREVIEW_RATIO = 60  # Preview takes 60% of width
