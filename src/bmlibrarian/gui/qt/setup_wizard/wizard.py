"""
Main Setup Wizard class for BMLibrarian.

Provides a step-by-step wizard for initial setup and configuration.
"""

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import QWizard, QApplication, QMessageBox
from PySide6.QtCore import Qt

from ..resources.styles.dpi_scale import get_font_scale
from ..resources.styles.stylesheet_generator import StylesheetGenerator


logger = logging.getLogger(__name__)


class SetupWizard(QWizard):
    """
    Main setup wizard for BMLibrarian initial configuration.

    Guides users through:
    1. Welcome and overview
    2. PostgreSQL database setup instructions
    3. Database credentials configuration
    4. Database schema initialization
    5. Data import options (PubMed, medRxiv)
    6. Import progress
    7. Completion

    Example:
        app = QApplication(sys.argv)
        wizard = SetupWizard()
        wizard.show()
        sys.exit(app.exec())
    """

    # Page IDs as class constants for readability
    PAGE_WELCOME = 0
    PAGE_DB_INSTRUCTIONS = 1
    PAGE_DB_CONFIG = 2
    PAGE_DB_SETUP = 3
    PAGE_IMPORT_OPTIONS = 4
    PAGE_IMPORT_PROGRESS = 5
    PAGE_COMPLETE = 6

    def __init__(self, parent: Optional[object] = None):
        """
        Initialize the setup wizard.

        Args:
            parent: Optional parent widget
        """
        super().__init__(parent)

        # Store collected configuration
        self._config = {
            "postgres_host": "localhost",
            "postgres_port": "5432",
            "postgres_user": "",
            "postgres_password": "",
            "postgres_db": "",
            "pdf_base_dir": str(Path.home() / "knowledgebase" / "pdf"),
            "ncbi_email": "",
            "ncbi_api_key": "",
            "ollama_host": "http://localhost:11434",
        }

        # Import results tracking
        self._import_results = {
            "medrxiv_success": False,
            "pubmed_success": False,
            "medrxiv_stats": {},
            "pubmed_stats": {},
        }

        self._setup_ui()
        self._setup_pages()
        self._apply_styles()

        logger.info("Setup wizard initialized")

    def _setup_ui(self) -> None:
        """Configure wizard UI properties."""
        scale = get_font_scale()

        self.setWindowTitle("BMLibrarian Setup Wizard")
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)

        # Set minimum size based on font scaling
        min_width = scale["control_width_xlarge"] * 2
        min_height = int(min_width * 0.8)
        self.setMinimumSize(min_width, min_height)

        # Configure wizard options
        self.setOption(QWizard.WizardOption.IndependentPages, False)
        self.setOption(QWizard.WizardOption.HaveHelpButton, False)
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage, True)

        # Set button text
        self.setButtonText(QWizard.WizardButton.NextButton, "Next >")
        self.setButtonText(QWizard.WizardButton.BackButton, "< Back")
        self.setButtonText(QWizard.WizardButton.FinishButton, "Finish")
        self.setButtonText(QWizard.WizardButton.CancelButton, "Cancel")

    def _setup_pages(self) -> None:
        """Create and add all wizard pages."""
        # Import pages here to avoid circular imports
        from .pages import (
            WelcomePage,
            DatabaseInstructionsPage,
            DatabaseConfigPage,
            DatabaseSetupPage,
            ImportOptionsPage,
            ImportProgressPage,
            CompletePage,
        )

        # Create and add pages in order
        self.setPage(self.PAGE_WELCOME, WelcomePage(self))
        self.setPage(self.PAGE_DB_INSTRUCTIONS, DatabaseInstructionsPage(self))
        self.setPage(self.PAGE_DB_CONFIG, DatabaseConfigPage(self))
        self.setPage(self.PAGE_DB_SETUP, DatabaseSetupPage(self))
        self.setPage(self.PAGE_IMPORT_OPTIONS, ImportOptionsPage(self))
        self.setPage(self.PAGE_IMPORT_PROGRESS, ImportProgressPage(self))
        self.setPage(self.PAGE_COMPLETE, CompletePage(self))

    def _apply_styles(self) -> None:
        """Apply DPI-aware styling to the wizard."""
        scale = get_font_scale()
        gen = StylesheetGenerator(scale)

        # Build wizard-specific stylesheet
        stylesheet = gen.custom("""
            QWizard {{
                background-color: #FAFAFA;
            }}
            QWizardPage {{
                background-color: #FFFFFF;
                padding: {padding_large}px;
            }}
            QLabel {{
                font-size: {font_normal}pt;
                color: #333333;
            }}
            QLabel[heading="true"] {{
                font-size: {font_xlarge}pt;
                font-weight: bold;
                color: #1976D2;
            }}
            QLabel[subheading="true"] {{
                font-size: {font_medium}pt;
                color: #666666;
            }}
            QLineEdit {{
                font-size: {font_normal}pt;
                padding: {padding_small}px;
                border: 1px solid #CCCCCC;
                border-radius: {radius_small}px;
            }}
            QLineEdit:focus {{
                border-color: #1976D2;
            }}
            QTextEdit {{
                font-size: {font_normal}pt;
                padding: {padding_small}px;
                border: 1px solid #CCCCCC;
                border-radius: {radius_small}px;
            }}
            QTextEdit:focus {{
                border-color: #1976D2;
            }}
            QCheckBox {{
                font-size: {font_normal}pt;
                spacing: {spacing_small}px;
            }}
            QRadioButton {{
                font-size: {font_normal}pt;
                spacing: {spacing_small}px;
            }}
            QGroupBox {{
                font-size: {font_medium}pt;
                font-weight: bold;
                border: 1px solid #DDDDDD;
                border-radius: {radius_small}px;
                margin-top: {spacing_large}px;
                padding-top: {spacing_large}px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: {padding_medium}px;
                padding: 0 {padding_small}px;
            }}
            QProgressBar {{
                border: 1px solid #CCCCCC;
                border-radius: {radius_small}px;
                text-align: center;
                height: {control_height_small}px;
            }}
            QProgressBar::chunk {{
                background-color: #4CAF50;
                border-radius: {radius_tiny}px;
            }}
            QPushButton {{
                font-size: {font_normal}pt;
                padding: {padding_small}px {padding_medium}px;
                border-radius: {radius_small}px;
                background-color: #2196F3;
                color: white;
                border: none;
            }}
            QPushButton:hover {{
                background-color: #1976D2;
            }}
            QPushButton:disabled {{
                background-color: #CCCCCC;
                color: #666666;
            }}
        """)

        self.setStyleSheet(stylesheet)

    def get_config(self) -> dict:
        """
        Get the current configuration values.

        Returns:
            dict: Configuration dictionary
        """
        return self._config.copy()

    def set_config_value(self, key: str, value: str) -> None:
        """
        Set a configuration value.

        Args:
            key: Configuration key
            value: Configuration value
        """
        self._config[key] = value

    def get_config_value(self, key: str, default: str = "") -> str:
        """
        Get a configuration value.

        Args:
            key: Configuration key
            default: Default value if key not found

        Returns:
            str: Configuration value or default
        """
        return self._config.get(key, default)

    def set_import_result(
        self, source: str, success: bool, stats: Optional[dict] = None
    ) -> None:
        """
        Record import result for a data source.

        Args:
            source: Data source name ('medrxiv' or 'pubmed')
            success: Whether import was successful
            stats: Optional statistics dictionary
        """
        self._import_results[f"{source}_success"] = success
        if stats:
            self._import_results[f"{source}_stats"] = stats

    def get_import_results(self) -> dict:
        """
        Get import results.

        Returns:
            dict: Import results dictionary
        """
        return self._import_results.copy()

    def reject(self) -> None:
        """Handle wizard cancellation."""
        reply = QMessageBox.question(
            self,
            "Cancel Setup",
            "Are you sure you want to cancel the setup wizard?\n\n"
            "You can run it again later to complete the setup.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            logger.info("Setup wizard cancelled by user")
            super().reject()

    def done(self, result: int) -> None:
        """
        Handle wizard completion.

        Args:
            result: Dialog result code
        """
        if result == QWizard.DialogCode.Accepted:
            logger.info("Setup wizard completed successfully")
        else:
            logger.info("Setup wizard cancelled")

        super().done(result)
