"""
Setup Wizard module for BMLibrarian initial configuration.

This module provides a PySide6 QWizard-based setup interface for:
1. PostgreSQL database configuration
2. Database schema initialization
3. Data source import (PubMed, medRxiv)
"""

from .wizard import SetupWizard
from .pages import (
    WelcomePage,
    DatabaseInstructionsPage,
    DatabaseConfigPage,
    DatabaseSetupPage,
    ImportOptionsPage,
    ImportProgressPage,
    CompletePage,
)

__all__ = [
    "SetupWizard",
    "WelcomePage",
    "DatabaseInstructionsPage",
    "DatabaseConfigPage",
    "DatabaseSetupPage",
    "ImportOptionsPage",
    "ImportProgressPage",
    "CompletePage",
]
