"""
Welcome and instructions pages for the Setup Wizard.

Contains the initial pages that introduce users to the setup process.
"""

from typing import Optional, TYPE_CHECKING

from PySide6.QtWidgets import QWizardPage, QVBoxLayout, QLabel, QFrame

from ..resources.styles.dpi_scale import get_font_scale
from .utils import create_frame_stylesheet
from .constants import FRAME_NOTE_BG, FRAME_NOTE_BORDER

if TYPE_CHECKING:
    from .wizard import SetupWizard


class WelcomePage(QWizardPage):
    """
    Welcome page introducing the setup wizard.

    Displays overview of what the wizard will configure.
    """

    def __init__(self, parent: Optional["SetupWizard"] = None):
        """Initialize welcome page."""
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the welcome page UI."""
        scale = get_font_scale()

        self.setTitle("Welcome to BMLibrarian Setup")
        self.setSubTitle(
            "This wizard will help you configure BMLibrarian for first use."
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(scale["spacing_large"])

        # Welcome message
        welcome_text = QLabel(
            "BMLibrarian is a comprehensive Python library for AI-powered "
            "access to biomedical literature databases.\n\n"
            "This setup wizard will guide you through:\n\n"
            "  1. PostgreSQL database configuration\n"
            "  2. Database schema initialization\n"
            "  3. Optional data import from PubMed and medRxiv\n\n"
            "Before proceeding, please ensure you have:\n\n"
            "  - PostgreSQL server installed and running\n"
            "  - pgvector extension available\n"
            "  - plpython3u extension available\n"
            "  - Database administrator credentials"
        )
        welcome_text.setWordWrap(True)
        layout.addWidget(welcome_text)

        # Requirements note
        note_frame = QFrame()
        note_frame.setObjectName("noteFrame")
        note_frame.setStyleSheet(
            create_frame_stylesheet(scale, FRAME_NOTE_BG, FRAME_NOTE_BORDER, "noteFrame")
        )

        note_layout = QVBoxLayout(note_frame)
        note_label = QLabel(
            "Note: The wizard will check if the database already contains "
            "tables. If it does, you will need to specify a different "
            "(empty) database name to avoid data loss."
        )
        note_label.setWordWrap(True)
        note_layout.addWidget(note_label)

        layout.addWidget(note_frame)
        layout.addStretch()


class DatabaseInstructionsPage(QWizardPage):
    """
    Page explaining the automated database setup process.

    Informs the user what will be created automatically.
    """

    def __init__(self, parent: Optional["SetupWizard"] = None):
        """Initialize database instructions page."""
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the instructions page UI."""
        scale = get_font_scale()

        self.setTitle("PostgreSQL Database Setup")
        self.setSubTitle(
            "The wizard will automatically set up your database."
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(scale["spacing_large"])

        # What will be created
        overview = QLabel(
            "BMLibrarian requires PostgreSQL with specific extensions for "
            "semantic search and text processing.\n\n"
            "On the next page, you'll provide PostgreSQL superuser credentials, "
            "and the wizard will automatically:"
        )
        overview.setWordWrap(True)
        layout.addWidget(overview)

        # Steps that will be performed
        steps_frame = QFrame()
        steps_frame.setObjectName("stepsFrame")
        steps_frame.setStyleSheet(
            create_frame_stylesheet(scale, FRAME_NOTE_BG, FRAME_NOTE_BORDER, "stepsFrame")
        )
        steps_layout = QVBoxLayout(steps_frame)

        steps = [
            "1. Create the 'bmlibrarian' database",
            "2. Install required extensions:",
            "      • pgvector (semantic similarity search)",
            "      • plpython3u (embedding generation)",
            "      • pg_trgm (trigram text search)",
            "3. Create a 'bmlibrarian' database user",
            "4. Grant appropriate permissions",
            "5. Apply the database schema",
        ]
        for step in steps:
            step_label = QLabel(step)
            steps_layout.addWidget(step_label)

        layout.addWidget(steps_frame)

        # Prerequisites note
        prereq_label = QLabel(
            "\nPrerequisites:\n\n"
            "  • PostgreSQL must be installed and running\n"
            "  • You need superuser credentials (e.g., 'postgres' user)\n"
            "  • pgvector extension must be available on your system:\n"
            "      - macOS (Homebrew): brew install pgvector\n"
            "      - Ubuntu/Debian: sudo apt install postgresql-16-pgvector\n"
            "      - Or compile from source: github.com/pgvector/pgvector"
        )
        prereq_label.setWordWrap(True)
        layout.addWidget(prereq_label)

        layout.addStretch()
