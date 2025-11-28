#!/usr/bin/env python3
"""
BMLibrarian Systematic Review GUI - Checkpoint-Based Literature Review

A PySide6-based desktop application for conducting systematic literature reviews
with checkpoint-based workflow management and the ability to resume from any point.

Features:
- Monitor systematic review progress in real-time
- Resume from checkpoints with modified parameters
- Prevent redundant computation by loading existing work
- Modify thresholds and weights when resuming
- Create new reviews with PICO-based criteria

Usage:
    python systematic_review_gui.py [--review-dir <path>]

Example:
    # Start with default directory
    python systematic_review_gui.py

    # Start with specific review directory
    python systematic_review_gui.py --review-dir ~/my_reviews
"""

import sys
import argparse
import logging
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout
from PySide6.QtGui import QCloseEvent
from PySide6.QtCore import Qt


class SystematicReviewMainWindow(QMainWindow):
    """Main window with proper cleanup handling for worker threads."""

    def __init__(self) -> None:
        """Initialize the main window."""
        super().__init__()
        self._tab_widget = None

    def set_tab_widget(self, tab_widget) -> None:
        """Set the tab widget reference for cleanup."""
        self._tab_widget = tab_widget

    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle window close event with proper cleanup."""
        if self._tab_widget is not None:
            self._tab_widget.cleanup()
        super().closeEvent(event)


def setup_logging(debug: bool = False) -> None:
    """Set up logging configuration."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def main() -> int:
    """Main entry point for the systematic review GUI."""
    parser = argparse.ArgumentParser(
        description='BMLibrarian Systematic Review GUI'
    )
    parser.add_argument(
        '--review-dir',
        type=str,
        default=str(Path.home() / "systematic_reviews"),
        help='Directory for storing review files and checkpoints'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )

    args = parser.parse_args()

    setup_logging(args.debug)
    logger = logging.getLogger(__name__)

    # Create the review directory if it doesn't exist
    review_dir = Path(args.review_dir)
    review_dir.mkdir(parents=True, exist_ok=True)

    # Create application
    app = QApplication(sys.argv)
    app.setApplicationName("BMLibrarian Systematic Review")
    app.setOrganizationName("BMLibrarian")

    # Import and create the tab widget
    try:
        from bmlibrarian.gui.qt.plugins.systematic_review.systematic_review_tab import (
            SystematicReviewTabWidget,
        )
    except ImportError as e:
        logger.error(f"Failed to import GUI components: {e}")
        return 1

    # Create main window with cleanup handling
    window = SystematicReviewMainWindow()
    window.setWindowTitle("BMLibrarian - Systematic Review")
    window.resize(1200, 800)

    # Create central widget with the systematic review tab
    central_widget = QWidget()
    layout = QVBoxLayout(central_widget)
    layout.setContentsMargins(0, 0, 0, 0)

    tab_widget = SystematicReviewTabWidget(parent=central_widget)
    window.set_tab_widget(tab_widget)

    # Set the review directory
    tab_widget.review_dir_edit.setText(str(review_dir))
    tab_widget.output_dir_edit.setText(str(review_dir))
    tab_widget._review_directory = review_dir

    # Connect status messages to status bar
    def show_status(message: str) -> None:
        window.statusBar().showMessage(message, 5000)

    tab_widget.status_message.connect(show_status)

    layout.addWidget(tab_widget)
    window.setCentralWidget(central_widget)

    # Load initial checkpoints
    tab_widget.refresh_checkpoints()

    # Show window
    window.show()

    logger.info("Systematic Review GUI started")

    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
