"""
Wizard pages for BMLibrarian Setup Wizard.

This module serves as a compatibility layer, re-exporting all page classes
from their individual module files. This maintains backward compatibility
with existing code that imports from pages.py.

For new code, prefer importing directly from the specific modules:
    from .welcome import WelcomePage, DatabaseInstructionsPage
    from .database_config import DatabaseConfigPage
    from .database_setup import DatabaseSetupWorker, DatabaseSetupPage
    from .api_keys import APIKeysPage
    from .import_options import ImportOptionsPage
    from .import_progress import ImportWorker, ImportProgressPage
    from .document_browser import DocumentBrowserPage
    from .complete import CompletePage
"""

# Re-export all page classes for backward compatibility
from .welcome import WelcomePage, DatabaseInstructionsPage
from .database_config import DatabaseConfigPage
from .database_setup import DatabaseSetupWorker, DatabaseSetupPage
from .api_keys import APIKeysPage
from .import_options import ImportOptionsPage
from .import_progress import ImportWorker, ImportProgressPage
from .document_browser import DocumentBrowserPage
from .complete import CompletePage

# Re-export utility functions and constants for backward compatibility
from .utils import (
    find_project_root,
    create_frame_stylesheet,
    create_muted_label_stylesheet,
    create_metadata_label_stylesheet,
    calculate_splitter_sizes,
    format_authors_short,
    format_date_short,
    ENV_FILE_PERMISSIONS,
    DEFAULT_DATABASE_NAME,
    DEFAULT_APP_USER,
)

# Make _create_frame_stylesheet available as an alias for backward compatibility
_create_frame_stylesheet = create_frame_stylesheet

__all__ = [
    # Page classes
    "WelcomePage",
    "DatabaseInstructionsPage",
    "DatabaseConfigPage",
    "DatabaseSetupWorker",
    "DatabaseSetupPage",
    "APIKeysPage",
    "ImportOptionsPage",
    "ImportWorker",
    "ImportProgressPage",
    "DocumentBrowserPage",
    "CompletePage",
    # Utility functions
    "find_project_root",
    "create_frame_stylesheet",
    "_create_frame_stylesheet",
    "create_muted_label_stylesheet",
    "create_metadata_label_stylesheet",
    "calculate_splitter_sizes",
    "format_authors_short",
    "format_date_short",
    # Constants
    "ENV_FILE_PERMISSIONS",
    "DEFAULT_DATABASE_NAME",
    "DEFAULT_APP_USER",
]
