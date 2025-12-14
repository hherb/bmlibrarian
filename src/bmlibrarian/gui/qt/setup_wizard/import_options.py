"""
Import options page for the Setup Wizard.

Contains the page for selecting data import options.
"""

from typing import Optional, TYPE_CHECKING

from PySide6.QtWidgets import (
    QWizardPage,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QGroupBox,
    QCheckBox,
    QRadioButton,
    QButtonGroup,
    QSpinBox,
    QFrame,
    QScrollArea,
    QWidget,
)

from ..resources.styles.dpi_scale import get_font_scale
from .utils import create_frame_stylesheet, create_muted_label_stylesheet
from .constants import (
    MEDRXIV_DEFAULT_DAYS,
    MEDRXIV_MIN_DAYS,
    MEDRXIV_MAX_DAYS,
    PUBMED_DEFAULT_MAX_RESULTS,
    PUBMED_MIN_RESULTS,
    PUBMED_MAX_RESULTS,
    MESH_DEFAULT_YEAR,
    MESH_MIN_YEAR,
    MESH_MAX_YEAR,
    MESH_ESTIMATED_SIZE_MB,
    MESH_ESTIMATED_SIZE_NO_SCR_MB,
    COLOR_MUTED,
    FRAME_NOTE_BG,
    FRAME_NOTE_BORDER,
)

if TYPE_CHECKING:
    from .wizard import SetupWizard


class ImportOptionsPage(QWizardPage):
    """
    Page for selecting data import options.

    Allows user to choose between:
    - Full PubMed mirror
    - Full medRxiv mirror
    - MeSH vocabulary import
    - Quick test import (latest updates only)
    - Skip import
    """

    def __init__(self, parent: Optional["SetupWizard"] = None):
        """Initialize import options page."""
        super().__init__(parent)
        self._wizard = parent
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the import options page UI."""
        scale = get_font_scale()

        self.setTitle("Data Import Options")
        self.setSubTitle("Choose which data sources to import into your database.")

        # Create scroll area to accommodate all options
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        scroll_widget = QWidget()
        layout = QVBoxLayout(scroll_widget)
        layout.setSpacing(scale["spacing_large"])

        # Import mode selection
        mode_group = QGroupBox("Import Mode")
        mode_layout = QVBoxLayout(mode_group)

        self.mode_button_group = QButtonGroup(self)

        # Skip import option
        self.skip_radio = QRadioButton("Skip Import (configure manually later)")
        self.skip_radio.setChecked(True)
        self.mode_button_group.addButton(self.skip_radio, 0)
        mode_layout.addWidget(self.skip_radio)

        # Quick test option
        self.quick_radio = QRadioButton(
            "Quick Test Import (medRxiv + PubMed samples)"
        )
        self.mode_button_group.addButton(self.quick_radio, 1)
        mode_layout.addWidget(self.quick_radio)

        quick_note = QLabel(
            f"    Downloads ~{MEDRXIV_DEFAULT_DAYS} days of medRxiv preprints and "
            f"~{PUBMED_DEFAULT_MAX_RESULTS} PubMed articles"
        )
        quick_note.setStyleSheet(create_muted_label_stylesheet(COLOR_MUTED))
        mode_layout.addWidget(quick_note)

        # Full medRxiv option
        self.medrxiv_radio = QRadioButton("Full medRxiv Mirror")
        self.mode_button_group.addButton(self.medrxiv_radio, 2)
        mode_layout.addWidget(self.medrxiv_radio)

        medrxiv_note = QLabel("    Downloads all available medRxiv preprints (~500K+)")
        medrxiv_note.setStyleSheet(create_muted_label_stylesheet(COLOR_MUTED))
        mode_layout.addWidget(medrxiv_note)

        # Full PubMed option
        self.pubmed_radio = QRadioButton("Full PubMed Baseline Mirror")
        self.mode_button_group.addButton(self.pubmed_radio, 3)
        mode_layout.addWidget(self.pubmed_radio)

        pubmed_note = QLabel(
            "    Downloads complete PubMed baseline (~38M articles, ~400GB)"
        )
        pubmed_note.setStyleSheet(create_muted_label_stylesheet(COLOR_MUTED))
        mode_layout.addWidget(pubmed_note)

        # MeSH only option
        self.mesh_radio = QRadioButton("MeSH Vocabulary Only")
        self.mode_button_group.addButton(self.mesh_radio, 4)
        mode_layout.addWidget(self.mesh_radio)

        mesh_note = QLabel(
            f"    Downloads MeSH medical vocabulary (~{MESH_ESTIMATED_SIZE_MB}MB with supplementary concepts)"
        )
        mesh_note.setStyleSheet(create_muted_label_stylesheet(COLOR_MUTED))
        mode_layout.addWidget(mesh_note)

        layout.addWidget(mode_group)

        # MeSH settings group
        mesh_group = QGroupBox("MeSH Vocabulary Settings")
        mesh_layout = QVBoxLayout(mesh_group)

        # Include MeSH checkbox (for quick test mode)
        self.include_mesh_check = QCheckBox("Include MeSH vocabulary import (recommended)")
        self.include_mesh_check.setChecked(True)
        self.include_mesh_check.setToolTip(
            "MeSH (Medical Subject Headings) provides standardized medical vocabulary "
            "used for query expansion and term matching."
        )
        mesh_layout.addWidget(self.include_mesh_check)

        # MeSH year selection
        mesh_year_layout = QHBoxLayout()
        mesh_year_label = QLabel("MeSH year:")
        mesh_year_label.setMinimumWidth(scale["control_width_small"])
        self.mesh_year_spin = QSpinBox()
        self.mesh_year_spin.setRange(MESH_MIN_YEAR, MESH_MAX_YEAR)
        self.mesh_year_spin.setValue(MESH_DEFAULT_YEAR)
        mesh_year_layout.addWidget(mesh_year_label)
        mesh_year_layout.addWidget(self.mesh_year_spin)
        mesh_year_layout.addStretch()
        mesh_layout.addLayout(mesh_year_layout)

        # Include supplementary concepts checkbox
        self.mesh_supplementary_check = QCheckBox(
            f"Include supplementary concepts (~{MESH_ESTIMATED_SIZE_MB}MB vs ~{MESH_ESTIMATED_SIZE_NO_SCR_MB}MB)"
        )
        self.mesh_supplementary_check.setChecked(True)
        self.mesh_supplementary_check.setToolTip(
            "Supplementary Concept Records (SCRs) include additional terms like "
            "drug names, chemicals, and rare diseases."
        )
        mesh_layout.addWidget(self.mesh_supplementary_check)

        layout.addWidget(mesh_group)

        # Literature import settings group
        settings_group = QGroupBox("Literature Import Settings")
        settings_layout = QVBoxLayout(settings_group)

        # MedRxiv days
        medrxiv_days_layout = QHBoxLayout()
        medrxiv_days_label = QLabel("medRxiv days to fetch (for quick test):")
        self.medrxiv_days_spin = QSpinBox()
        self.medrxiv_days_spin.setRange(MEDRXIV_MIN_DAYS, MEDRXIV_MAX_DAYS)
        self.medrxiv_days_spin.setValue(MEDRXIV_DEFAULT_DAYS)
        medrxiv_days_layout.addWidget(medrxiv_days_label)
        medrxiv_days_layout.addWidget(self.medrxiv_days_spin)
        medrxiv_days_layout.addStretch()
        settings_layout.addLayout(medrxiv_days_layout)

        # PubMed max results
        pubmed_max_layout = QHBoxLayout()
        pubmed_max_label = QLabel("PubMed max results (for quick test):")
        self.pubmed_max_spin = QSpinBox()
        self.pubmed_max_spin.setRange(PUBMED_MIN_RESULTS, PUBMED_MAX_RESULTS)
        self.pubmed_max_spin.setValue(PUBMED_DEFAULT_MAX_RESULTS)
        pubmed_max_layout.addWidget(pubmed_max_label)
        pubmed_max_layout.addWidget(self.pubmed_max_spin)
        pubmed_max_layout.addStretch()
        settings_layout.addLayout(pubmed_max_layout)

        # Download PDFs checkbox
        self.download_pdfs_check = QCheckBox("Download PDFs (medRxiv only)")
        self.download_pdfs_check.setChecked(False)
        settings_layout.addWidget(self.download_pdfs_check)

        layout.addWidget(settings_group)

        # Warning for large imports
        warning_frame = QFrame()
        warning_frame.setObjectName("importWarningFrame")
        warning_frame.setStyleSheet(
            create_frame_stylesheet(scale, FRAME_NOTE_BG, FRAME_NOTE_BORDER, "importWarningFrame")
        )

        warning_layout = QVBoxLayout(warning_frame)
        warning_label = QLabel(
            "Note: Full mirror imports can take many hours to complete "
            "and require significant disk space. For testing purposes, "
            "the 'Quick Test Import' option is recommended.\n\n"
            "MeSH vocabulary import is relatively fast (~5-10 minutes) and "
            "highly recommended for optimal search functionality."
        )
        warning_label.setWordWrap(True)
        warning_layout.addWidget(warning_label)

        layout.addWidget(warning_frame)

        layout.addStretch()

        scroll.setWidget(scroll_widget)

        # Main page layout
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(scroll)

    def get_import_mode(self) -> int:
        """Get the selected import mode."""
        return self.mode_button_group.checkedId()

    def get_import_settings(self) -> dict:
        """Get the import settings."""
        return {
            "mode": self.get_import_mode(),
            "medrxiv_days": self.medrxiv_days_spin.value(),
            "pubmed_max_results": self.pubmed_max_spin.value(),
            "download_pdfs": self.download_pdfs_check.isChecked(),
            "include_mesh": self.include_mesh_check.isChecked(),
            "mesh_year": self.mesh_year_spin.value(),
            "mesh_supplementary": self.mesh_supplementary_check.isChecked(),
        }

    def nextId(self) -> int:
        """Determine next page based on import selection."""
        from .wizard import SetupWizard

        mode = self.get_import_mode()
        if mode == 0:  # Skip import
            return SetupWizard.PAGE_COMPLETE
        return SetupWizard.PAGE_IMPORT_PROGRESS
