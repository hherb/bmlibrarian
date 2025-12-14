"""
BMLibrarian Lite GUI module.

Provides a lightweight PySide6-based GUI with two main features:
- Systematic Review: Search, score, extract, and report
- Document Interrogation: Q&A with loaded documents

Usage:
    from bmlibrarian.lite.gui import run_lite_app

    # Run the application
    exit_code = run_lite_app()

    # Or create the window directly
    from bmlibrarian.lite.gui import LiteMainWindow
    from bmlibrarian.lite import LiteConfig

    config = LiteConfig.load()
    window = LiteMainWindow(config=config)
    window.show()
"""

from .app import LiteMainWindow, run_lite_app
from .systematic_review_tab import SystematicReviewTab, WorkflowWorker
from .document_interrogation_tab import (
    DocumentInterrogationTab,
    ChatBubble,
    LiteDocumentViewWidget,
    AnswerWorker,
)
from .settings_dialog import SettingsDialog

__all__ = [
    # Main application
    "LiteMainWindow",
    "run_lite_app",
    # Tabs
    "SystematicReviewTab",
    "DocumentInterrogationTab",
    # Workers
    "WorkflowWorker",
    "AnswerWorker",
    # Widgets
    "ChatBubble",
    "LiteDocumentViewWidget",
    # Dialogs
    "SettingsDialog",
]
