"""
Main application window for BMLibrarian Lite.

A lightweight version of BMLibrarian with two tabs:
- Systematic Review: Search PubMed, score, extract, and generate reports
- Document Interrogation: Q&A with loaded documents
"""

import logging
import sys
from typing import Optional

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QStatusBar,
    QPushButton,
)
from PySide6.QtCore import Qt

from bmlibrarian.gui.qt.resources.dpi_scale import scaled
from bmlibrarian.gui.qt.resources.stylesheet_generator import StylesheetGenerator

from ..config import LiteConfig
from ..storage import LiteStorage
from .systematic_review_tab import SystematicReviewTab
from .document_interrogation_tab import DocumentInterrogationTab
from .settings_dialog import SettingsDialog

logger = logging.getLogger(__name__)


class LiteMainWindow(QMainWindow):
    """
    Main window for BMLibrarian Lite.

    Provides a two-tab interface for systematic review and document
    interrogation workflows.

    Attributes:
        config: Lite configuration instance
        storage: Storage layer instance
    """

    # Window dimensions relative to font metrics
    DEFAULT_WIDTH_CHARS = 120
    DEFAULT_HEIGHT_CHARS = 40

    def __init__(
        self,
        config: Optional[LiteConfig] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Initialize the main window.

        Args:
            config: Lite configuration (uses defaults if not provided)
            parent: Optional parent widget
        """
        super().__init__(parent)

        self.config = config or LiteConfig.load()
        self.config.ensure_directories()
        self.config.load_env()

        self.storage = LiteStorage(self.config)

        self._setup_ui()
        self._apply_styles()

        logger.info("BMLibrarian Lite initialized")

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        self.setWindowTitle("BMLibrarian Lite")

        # Calculate window size from font metrics
        fm = self.fontMetrics()
        width = fm.horizontalAdvance('x') * self.DEFAULT_WIDTH_CHARS
        height = fm.height() * self.DEFAULT_HEIGHT_CHARS
        self.resize(width, height)

        # Central widget and layout
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(scaled(8), scaled(8), scaled(8), scaled(8))

        # Tab widget
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # Create tabs
        self.systematic_review_tab = SystematicReviewTab(
            config=self.config,
            storage=self.storage,
            parent=self,
        )
        self.tab_widget.addTab(self.systematic_review_tab, "Systematic Review")

        self.interrogation_tab = DocumentInterrogationTab(
            config=self.config,
            storage=self.storage,
            parent=self,
        )
        self.tab_widget.addTab(self.interrogation_tab, "Document Interrogation")

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

        # Settings button in status bar
        settings_btn = QPushButton("Settings")
        settings_btn.clicked.connect(self._show_settings)
        self.status_bar.addPermanentWidget(settings_btn)

    def _apply_styles(self) -> None:
        """Apply stylesheet to the application."""
        generator = StylesheetGenerator()
        stylesheet = generator.generate()
        self.setStyleSheet(stylesheet)

    def _show_settings(self) -> None:
        """Show the settings dialog."""
        dialog = SettingsDialog(self.config, parent=self)
        if dialog.exec():
            # Reload configuration
            self.config = LiteConfig.load()
            self.status_bar.showMessage("Settings saved", 3000)

    def set_status(self, message: str, timeout: int = 0) -> None:
        """
        Set status bar message.

        Args:
            message: Status message
            timeout: Timeout in milliseconds (0 = permanent)
        """
        self.status_bar.showMessage(message, timeout)


def run_lite_app() -> int:
    """
    Run the BMLibrarian Lite application.

    Returns:
        Application exit code
    """
    app = QApplication(sys.argv)
    app.setApplicationName("BMLibrarian Lite")
    app.setOrganizationName("BMLibrarian")

    window = LiteMainWindow()
    window.show()

    return app.exec()
