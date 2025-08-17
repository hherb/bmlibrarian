"""Biomedical Literature Librarian - A Python library for accessing biomedical literature databases."""

__version__ = "0.1.0"
__author__ = "Your Name"
__email__ = "your.email@example.com"

from .app import initialize_app, get_database_connection
from .migrations import MigrationManager

__all__ = ["initialize_app", "get_database_connection", "MigrationManager"]