"""
Paper Weight Assessment Laboratory - Main Window

The main application window for the Paper Weight Assessment Laboratory.
Uses a tabbed interface with search, PDF upload, and results tabs.
"""

import logging
import sys

from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QTabWidget
from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent

from bmlibrarian.agents.paper_weight import PaperWeightAssessmentAgent
from bmlibrarian.gui.qt.resources.styles.dpi_scale import get_font_scale
from bmlibrarian.gui.qt.resources.styles.stylesheet_generator import get_stylesheet_generator

from .constants import (
    WINDOW_MIN_WIDTH,
    WINDOW_MIN_HEIGHT,
    WINDOW_DEFAULT_WIDTH,
    WINDOW_DEFAULT_HEIGHT,
    TAB_INDEX_SEARCH,
    TAB_INDEX_PDF_UPLOAD,
    TAB_INDEX_RESULTS,
)
from .tabs import SearchTab, PDFUploadTab, ResultsTab


logger = logging.getLogger(__name__)


class PaperWeightLab(QMainWindow):
    """
    Main laboratory GUI window for paper weight assessment.

    Provides a tabbed interface with:
    - Search tab: Find documents by keyword or semantic search
    - PDF Upload tab: Upload PDFs and match/create documents
    - Results tab: Assessment, visualization, and export

    Workflow:
    - App starts on Search tab
    - After document selection, switches to Results tab
    """

    def __init__(self):
        """Initialize the Paper Weight Laboratory."""
        super().__init__()

        # Get scaling values
        self.scale = get_font_scale()
        self.styles = get_stylesheet_generator()

        # Initialize agent
        try:
            self.agent = PaperWeightAssessmentAgent(show_model_info=False)
        except Exception as e:
            logger.error(f"Failed to initialize agent: {e}")
            self.agent = None

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Initialize user interface."""
        self.setWindowTitle("Paper Weight Assessment Laboratory")
        self.setMinimumSize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        self.resize(WINDOW_DEFAULT_WIDTH, WINDOW_DEFAULT_HEIGHT)

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(self.scale['spacing_medium'])
        main_layout.setContentsMargins(
            self.scale['padding_medium'],
            self.scale['padding_medium'],
            self.scale['padding_medium'],
            self.scale['padding_medium']
        )

        # Tab widget
        self.tab_widget = QTabWidget()

        # Create tabs
        self.search_tab = SearchTab()
        self.pdf_upload_tab = PDFUploadTab()
        self.results_tab = ResultsTab(agent=self.agent)

        # Add tabs
        self.tab_widget.addTab(self.search_tab, "Document Search")
        self.tab_widget.addTab(self.pdf_upload_tab, "PDF Upload")
        self.tab_widget.addTab(self.results_tab, "Assessment Results")

        main_layout.addWidget(self.tab_widget)

    def _connect_signals(self) -> None:
        """Connect tab signals."""
        # Connect document selection signals to switch to results tab
        self.search_tab.document_selected.connect(self._on_document_selected)
        self.pdf_upload_tab.document_selected.connect(self._on_document_selected)

    def _on_document_selected(self, document_id: int) -> None:
        """
        Handle document selection from search or PDF upload tabs.

        Args:
            document_id: Selected document ID
        """
        # Load document in results tab
        self.results_tab.load_document(document_id)

        # Switch to results tab
        self.tab_widget.setCurrentIndex(TAB_INDEX_RESULTS)

        # Refresh recent assessments in search tab
        self.search_tab.load_recent_assessments()

    def closeEvent(self, event: QCloseEvent) -> None:
        """
        Handle window close event.

        Ensures all child tab worker threads are properly terminated
        before closing the application.

        Args:
            event: The close event
        """
        logger.info("Closing Paper Weight Laboratory...")

        # Terminate workers in child tabs
        # The tabs' closeEvent will be called automatically, but we ensure
        # cleanup happens even if closeEvent propagation fails
        if hasattr(self.pdf_upload_tab, '_terminate_workers'):
            self.pdf_upload_tab._terminate_workers()
        if hasattr(self.results_tab, '_terminate_workers'):
            self.results_tab._terminate_workers()

        super().closeEvent(event)


def main() -> None:
    """Main entry point for the Paper Weight Laboratory."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    lab = PaperWeightLab()
    lab.show()

    sys.exit(app.exec())


__all__ = ['PaperWeightLab', 'main']
