"""
Setup Wizard module for BMLibrarian initial configuration.

This module provides a PySide6 QWizard-based setup interface for:
1. PostgreSQL database configuration
2. Database schema initialization
3. Optional API key configuration (Anthropic, OpenAI)
4. Data source import (PubMed, medRxiv, MeSH)
5. Document browser for verifying imports

The pages are organized into individual modules for maintainability:
- welcome.py: WelcomePage, DatabaseInstructionsPage
- database_config.py: DatabaseConfigPage
- database_setup.py: DatabaseSetupWorker, DatabaseSetupPage
- api_keys.py: APIKeysPage
- import_options.py: ImportOptionsPage
- import_progress.py: ImportWorker, ImportProgressPage
- document_browser.py: DocumentBrowserPage
- complete.py: CompletePage
- utils.py: Shared utility functions
- constants.py: Configuration constants
"""

from .wizard import SetupWizard
from .pages import (
    WelcomePage,
    DatabaseInstructionsPage,
    DatabaseConfigPage,
    DatabaseSetupWorker,
    DatabaseSetupPage,
    APIKeysPage,
    ImportOptionsPage,
    ImportWorker,
    ImportProgressPage,
    DocumentBrowserPage,
    CompletePage,
)

__all__ = [
    "SetupWizard",
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
]
