"""
Import progress page and worker for the Setup Wizard.

Contains the worker thread and page for data import operations.
"""

import logging
from typing import Optional, TYPE_CHECKING

from PySide6.QtWidgets import (
    QWizardPage,
    QVBoxLayout,
    QLabel,
    QTextEdit,
    QGroupBox,
    QProgressBar,
    QPushButton,
    QMessageBox,
)
from PySide6.QtCore import Signal, QThread

from ..resources.styles.dpi_scale import get_font_scale
from .constants import (
    MEDRXIV_DEFAULT_DAYS,
    MEDRXIV_FULL_IMPORT_DAYS,
    PUBMED_DEFAULT_MAX_RESULTS,
    PUBMED_TEST_QUERY,
    MESH_DEFAULT_YEAR,
    LOG_TEXT_HEIGHT_MULTIPLIER,
    PROGRESS_MEDRXIV_START,
    PROGRESS_PUBMED_START,
    PROGRESS_MESH_START,
    PROGRESS_COMPLETE,
)

if TYPE_CHECKING:
    from .wizard import SetupWizard
    from .import_options import ImportOptionsPage

logger = logging.getLogger(__name__)


class ImportWorker(QThread):
    """Worker thread for data import operations."""

    progress = Signal(str)  # Progress message
    progress_percent = Signal(int)  # Progress percentage
    finished = Signal(bool, str, dict)  # Success, message, stats

    def __init__(
        self,
        import_mode: int,
        settings: dict,
        parent: Optional[object] = None,
    ):
        """Initialize the import worker."""
        super().__init__(parent)
        self.import_mode = import_mode
        self.settings = settings
        self._cancelled = False

    def cancel(self) -> None:
        """Cancel the import operation."""
        self._cancelled = True
        logger.info("Import cancellation requested")

    def is_cancelled(self) -> bool:
        """Check if import has been cancelled."""
        return self._cancelled

    def _progress_callback(self, message: str) -> None:
        """Callback for importer progress messages. Emits signal to GUI."""
        self.progress.emit(message)

    def run(self) -> None:
        """Execute the import operation."""
        try:
            stats = {}

            if self.import_mode == 1:  # Quick test
                self._run_quick_test(stats)
            elif self.import_mode == 2:  # Full medRxiv
                self._run_medrxiv_full(stats)
            elif self.import_mode == 3:  # Full PubMed
                self._run_pubmed_full(stats)
            elif self.import_mode == 4:  # MeSH only
                self._run_mesh_only(stats)

            if self._cancelled:
                self.finished.emit(False, "Import cancelled", stats)
            else:
                self.finished.emit(True, "Import completed successfully!", stats)

        except Exception as e:
            logger.error(f"Import failed: {e}", exc_info=True)
            self.finished.emit(False, f"Import failed: {str(e)}", {})

    def _run_quick_test(self, stats: dict) -> None:
        """Run quick test import."""
        # MedRxiv
        self.progress.emit("Importing medRxiv preprints...")
        self.progress_percent.emit(PROGRESS_MEDRXIV_START)

        try:
            from bmlibrarian.importers import MedRxivImporter

            importer = MedRxivImporter()
            medrxiv_stats = importer.update_database(
                download_pdfs=self.settings.get("download_pdfs", False),
                days_to_fetch=self.settings.get("medrxiv_days", MEDRXIV_DEFAULT_DAYS),
                progress_callback=self._progress_callback,
                cancel_check=self.is_cancelled,
            )
            stats["medrxiv"] = medrxiv_stats
            self.progress.emit(
                f"medRxiv: {medrxiv_stats.get('total_processed', 0)} papers imported"
            )
        except Exception as e:
            logger.error(f"medRxiv import failed: {e}", exc_info=True)
            stats["medrxiv_error"] = str(e)

        if self._cancelled:
            return

        # PubMed
        self.progress.emit("Importing PubMed articles...")
        self.progress_percent.emit(PROGRESS_PUBMED_START)

        try:
            from bmlibrarian.importers import PubMedImporter

            importer = PubMedImporter()
            pubmed_stats = importer.import_by_search(
                query=PUBMED_TEST_QUERY,
                max_results=self.settings.get("pubmed_max_results", PUBMED_DEFAULT_MAX_RESULTS),
                progress_callback=self._progress_callback,
                cancel_check=self.is_cancelled,
            )
            stats["pubmed"] = pubmed_stats
            self.progress.emit(
                f"PubMed: {pubmed_stats.get('imported', 0)} articles imported"
            )
        except Exception as e:
            logger.error(f"PubMed import failed: {e}", exc_info=True)
            stats["pubmed_error"] = str(e)

        if self._cancelled:
            return

        # MeSH (if enabled)
        if self.settings.get("include_mesh", False):
            self._import_mesh(stats)

        self.progress_percent.emit(PROGRESS_COMPLETE)

    def _run_medrxiv_full(self, stats: dict) -> None:
        """Run full medRxiv import."""
        self.progress.emit("Starting full medRxiv import (this may take hours)...")
        self.progress_percent.emit(0)

        try:
            from bmlibrarian.importers import MedRxivImporter

            importer = MedRxivImporter()
            # Use a large days_to_fetch for full historical import
            medrxiv_stats = importer.update_database(
                download_pdfs=self.settings.get("download_pdfs", False),
                days_to_fetch=MEDRXIV_FULL_IMPORT_DAYS,
                progress_callback=self._progress_callback,
                cancel_check=self.is_cancelled,
            )
            stats["medrxiv"] = medrxiv_stats
        except Exception as e:
            logger.error(f"medRxiv full import failed: {e}", exc_info=True)
            stats["medrxiv_error"] = str(e)

        self.progress_percent.emit(PROGRESS_COMPLETE)

    def _run_pubmed_full(self, stats: dict) -> None:
        """Run full PubMed baseline import."""
        self.progress.emit("Starting full PubMed baseline import (this will take many hours)...")
        self.progress_percent.emit(0)

        try:
            from bmlibrarian.importers import PubMedBulkImporter

            importer = PubMedBulkImporter()

            # Download baseline
            self._progress_callback("Downloading PubMed baseline files...")
            importer.download_baseline()

            if self._cancelled:
                self._progress_callback("Import cancelled by user")
                return

            # Import baseline
            self._progress_callback("Importing PubMed baseline files...")
            pubmed_stats = importer.import_files(file_type="baseline")
            stats["pubmed"] = pubmed_stats
            self._progress_callback(f"PubMed baseline import complete: {pubmed_stats}")
        except Exception as e:
            logger.error(f"PubMed full import failed: {e}", exc_info=True)
            stats["pubmed_error"] = str(e)
            self._progress_callback(f"PubMed full import failed: {e}")

        self.progress_percent.emit(PROGRESS_COMPLETE)

    def _run_mesh_only(self, stats: dict) -> None:
        """Run MeSH vocabulary import only."""
        self.progress.emit("Starting MeSH vocabulary import...")
        self.progress_percent.emit(0)

        self._import_mesh(stats)

        self.progress_percent.emit(PROGRESS_COMPLETE)

    def _import_mesh(self, stats: dict) -> None:
        """
        Import MeSH vocabulary.

        Args:
            stats: Dictionary to store import statistics
        """
        self.progress.emit("Importing MeSH vocabulary...")
        self.progress_percent.emit(PROGRESS_MESH_START)

        try:
            from bmlibrarian.importers import MeSHImporter

            mesh_year = self.settings.get("mesh_year", MESH_DEFAULT_YEAR)
            include_supplementary = self.settings.get("mesh_supplementary", True)

            importer = MeSHImporter()

            def mesh_progress_callback(phase: str, processed: int, total: int) -> None:
                """Handle MeSH import progress updates."""
                if total > 0:
                    percent = int((processed / total) * 100)
                    self._progress_callback(f"MeSH {phase}: {processed:,}/{total:,} ({percent}%)")
                else:
                    self._progress_callback(f"MeSH {phase}: {processed:,} processed")

            mesh_stats = importer.import_mesh(
                year=mesh_year,
                include_supplementary=include_supplementary,
                progress_callback=mesh_progress_callback,
            )

            stats["mesh"] = {
                "year": mesh_year,
                "descriptors": mesh_stats.descriptors,
                "concepts": mesh_stats.concepts,
                "terms": mesh_stats.terms,
                "qualifiers": mesh_stats.qualifiers,
                "supplementary_concepts": mesh_stats.supplementary_concepts,
                "status": mesh_stats.status,
            }
            self.progress.emit(
                f"MeSH: {mesh_stats.descriptors:,} descriptors, "
                f"{mesh_stats.terms:,} terms imported"
            )
        except Exception as e:
            logger.error(f"MeSH import failed: {e}", exc_info=True)
            stats["mesh_error"] = str(e)
            self._progress_callback(f"MeSH import failed: {e}")


class ImportProgressPage(QWizardPage):
    """
    Page showing import progress.

    Displays real-time progress of data import operations.
    """

    def __init__(self, parent: Optional["SetupWizard"] = None):
        """Initialize import progress page."""
        super().__init__(parent)
        self._wizard = parent
        self._worker: Optional[ImportWorker] = None
        self._import_complete = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the progress page UI."""
        scale = get_font_scale()

        self.setTitle("Importing Data")
        self.setSubTitle("Please wait while data is being imported...")

        layout = QVBoxLayout(self)
        layout.setSpacing(scale["spacing_large"])

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        # Status label
        self.status_label = QLabel("Preparing import...")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        # Log area
        log_group = QGroupBox("Import Log")
        log_layout = QVBoxLayout(log_group)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(scale["control_height_xlarge"] * LOG_TEXT_HEIGHT_MULTIPLIER)
        log_layout.addWidget(self.log_text)

        layout.addWidget(log_group)

        # Cancel button
        self.cancel_btn = QPushButton("Cancel Import")
        self.cancel_btn.clicked.connect(self._cancel_import)
        layout.addWidget(self.cancel_btn)

        layout.addStretch()

    def initializePage(self) -> None:
        """Initialize the page when it becomes visible."""
        from .import_options import ImportOptionsPage

        self._import_complete = False
        self.progress_bar.setValue(0)
        self.log_text.clear()
        self.cancel_btn.setEnabled(True)

        # Get import settings from previous page
        options_page = self.wizard().page(self.wizard().PAGE_IMPORT_OPTIONS)
        if isinstance(options_page, ImportOptionsPage):
            settings = options_page.get_import_settings()
            import_mode = settings["mode"]

            # Start import worker
            self._worker = ImportWorker(import_mode, settings, self)
            self._worker.progress.connect(self._on_progress)
            self._worker.progress_percent.connect(self._on_progress_percent)
            self._worker.finished.connect(self._on_finished)
            self._worker.start()

    def _on_progress(self, message: str) -> None:
        """Handle progress updates."""
        self.status_label.setText(message)
        self.log_text.append(message)

    def _on_progress_percent(self, percent: int) -> None:
        """Handle progress percentage updates."""
        self.progress_bar.setValue(percent)

    def _on_finished(self, success: bool, message: str, stats: dict) -> None:
        """Handle import completion."""
        self._import_complete = True
        self.cancel_btn.setEnabled(False)

        self.status_label.setText(message)
        self.log_text.append(f"\n{message}")

        # Log stats
        if stats:
            self.log_text.append("\n--- Import Statistics ---")
            for key, value in stats.items():
                self.log_text.append(f"{key}: {value}")

        # Store results in wizard
        if self._wizard:
            self._wizard.set_import_result(
                "medrxiv",
                "medrxiv" in stats and "medrxiv_error" not in stats,
                stats.get("medrxiv", {}),
            )
            self._wizard.set_import_result(
                "pubmed",
                "pubmed" in stats and "pubmed_error" not in stats,
                stats.get("pubmed", {}),
            )
            self._wizard.set_import_result(
                "mesh",
                "mesh" in stats and "mesh_error" not in stats,
                stats.get("mesh", {}),
            )

        self.completeChanged.emit()

    def _cancel_import(self) -> None:
        """Cancel the import operation."""
        if self._worker and self._worker.isRunning():
            reply = QMessageBox.question(
                self,
                "Cancel Import",
                "Are you sure you want to cancel the import?\n\n"
                "Data imported so far will be kept.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )

            if reply == QMessageBox.StandardButton.Yes:
                self._worker.cancel()
                self.status_label.setText("Cancelling import...")

    def isComplete(self) -> bool:
        """Check if page is complete."""
        return self._import_complete

    def cleanup(self) -> None:
        """
        Clean up resources when wizard is closed.

        Cancels any running import and waits for the thread to finish.
        """
        if self._worker and self._worker.isRunning():
            logger.info("Cleaning up import worker...")
            self._worker.cancel()
            # Wait for thread to finish with a timeout
            if not self._worker.wait(5000):  # 5 second timeout
                logger.warning("Import worker did not finish in time, terminating...")
                self._worker.terminate()
                self._worker.wait()
            logger.info("Import worker cleaned up")
