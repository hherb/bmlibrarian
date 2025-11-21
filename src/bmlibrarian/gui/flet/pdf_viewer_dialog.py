"""PDF Viewer and Downloader Dialog

Provides dialogs for viewing existing PDFs or downloading PDFs from URLs.
"""

import flet as ft
import logging
import subprocess
import platform
import os
from pathlib import Path
from typing import Optional, Dict, Any, Callable

logger = logging.getLogger(__name__)


class PDFViewerDialog:
    """Dialog for viewing or downloading PDFs."""

    def __init__(self, page: ft.Page):
        """Initialize PDF viewer dialog.

        Args:
            page: Flet page instance
        """
        self.page = page
        self.dialog = None
        self.progress_bar = None
        self.status_text = None

    def show_pdf(self, pdf_path: Path, document: Dict[str, Any]):
        """Show an existing PDF using the system's default PDF viewer.

        Args:
            pdf_path: Path to the PDF file
            document: Document dictionary for title/metadata
        """
        if not pdf_path.exists():
            self._show_error(f"PDF file not found: {pdf_path}")
            return

        title = document.get('title', 'Unknown Document')

        try:
            # Open PDF with system default application
            if platform.system() == 'Darwin':  # macOS
                subprocess.run(['open', str(pdf_path)], check=True)
            elif platform.system() == 'Windows':
                os.startfile(str(pdf_path))
            elif platform.system() == 'Linux':
                subprocess.run(['xdg-open', str(pdf_path)], check=True)
            else:
                self._show_error(f"Unsupported platform: {platform.system()}")
                return

            # PDF opened successfully - just log it, no dialog needed
            logger.info(f"Opened PDF in system viewer: {title} at {pdf_path}")

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to open PDF: {e}")
            self._show_error(f"Failed to open PDF with system viewer: {e}")
        except Exception as e:
            logger.error(f"Unexpected error opening PDF: {e}")
            self._show_error(f"Unexpected error: {e}")

    def download_and_show_pdf(
        self,
        document: Dict[str, Any],
        on_success: Optional[Callable[[Path], None]] = None,
        on_error: Optional[Callable[[str], None]] = None
    ):
        """Download PDF from URL and show it.

        Args:
            document: Document dictionary with pdf_url
            on_success: Optional callback when download succeeds (receives pdf_path)
            on_error: Optional callback when download fails (receives error message)
        """
        from ..utils.pdf_manager import PDFManager

        pdf_url = document.get('pdf_url')
        if not pdf_url:
            error_msg = "No PDF URL available for this document"
            logger.warning(error_msg)
            if on_error:
                on_error(error_msg)
            else:
                self._show_error(error_msg)
            return

        title = document.get('title', 'Unknown Document')

        # Show download dialog
        self._show_download_dialog(title)

        # Download in background (simulate async with thread)
        import threading

        def download_task():
            try:
                # Get database connection for updates
                from ..app import get_database_connection
                db_conn = get_database_connection()
                pdf_manager = PDFManager(db_conn=db_conn)

                # Download PDF
                pdf_path = pdf_manager.download_pdf(document)

                if pdf_path and pdf_path.exists():
                    # Update database with relative path
                    doc_id = document.get('id')
                    if doc_id and db_conn:
                        try:
                            relative_path = pdf_manager.get_relative_pdf_path(document)
                            if relative_path:
                                pdf_manager.update_database_pdf_path(doc_id, relative_path)
                                logger.info(f"Updated database with PDF path: {relative_path}")
                                # Update document dict for UI
                                document['pdf_filename'] = relative_path
                        except Exception as e:
                            logger.error(f"Failed to update database: {e}")

                    # Close database connection
                    if db_conn:
                        db_conn.close()

                    # Success - call handler on UI thread
                    def update_ui():
                        self._on_download_success(pdf_path, document, on_success)
                    self.page.run_thread(update_ui)
                else:
                    if db_conn:
                        db_conn.close()
                    error_msg = "Download failed - check logs for details"
                    def update_ui():
                        self._on_download_error(error_msg, on_error)
                    self.page.run_thread(update_ui)

            except Exception as e:
                error_msg = f"Download error: {str(e)}"
                logger.error(error_msg, exc_info=True)
                def update_ui():
                    self._on_download_error(error_msg, on_error)
                self.page.run_thread(update_ui)

        thread = threading.Thread(target=download_task, daemon=True)
        thread.start()

    def _show_download_dialog(self, title: str):
        """Show download progress dialog.

        Args:
            title: Document title
        """
        self.progress_bar = ft.ProgressBar(width=400)
        self.status_text = ft.Text("Downloading PDF...", size=14)

        self.dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Downloading PDF", size=18, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                content=ft.Column([
                    ft.Text(f"Document: {title[:100]}...", size=12, color=ft.Colors.GREY_700),
                    ft.Container(height=10),
                    self.progress_bar,
                    self.status_text
                ], tight=True, spacing=10),
                padding=ft.padding.all(10),
                width=450
            )
        )

        self.page.overlay.append(self.dialog)
        self.dialog.open = True
        self.page.update()

    def _on_download_success(self, pdf_path: Path, document: Dict[str, Any], callback: Optional[Callable]):
        """Handle successful download.

        Args:
            pdf_path: Path to downloaded PDF
            document: Document dictionary
            callback: Optional success callback
        """
        # Close download dialog
        if self.dialog:
            self.dialog.open = False
            self.page.update()

        # Call user callback if provided
        if callback:
            callback(pdf_path)

        # Open the PDF
        self.show_pdf(pdf_path, document)

    def _on_download_error(self, error_msg: str, callback: Optional[Callable]):
        """Handle download error.

        Args:
            error_msg: Error message
            callback: Optional error callback
        """
        # Close download dialog
        if self.dialog:
            self.dialog.open = False
            self.page.update()

        # Call user callback if provided
        if callback:
            callback(error_msg)
        else:
            self._show_error(error_msg)

    def _show_error(self, message: str):
        """Show error dialog.

        Args:
            message: Error message to display
        """
        error_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Error", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.RED_700),
            content=ft.Text(message, size=14),
            actions=[
                ft.TextButton("OK", on_click=lambda e: self._close_dialog(error_dialog))
            ]
        )

        self.page.overlay.append(error_dialog)
        error_dialog.open = True
        self.page.update()

    def _show_info(self, title: str, message: str):
        """Show info dialog.

        Args:
            title: Dialog title
            message: Info message to display
        """
        info_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(title, size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_700),
            content=ft.Text(message, size=14),
            actions=[
                ft.TextButton("OK", on_click=lambda e: self._close_dialog(info_dialog))
            ]
        )

        self.page.overlay.append(info_dialog)
        info_dialog.open = True
        self.page.update()

    def _close_dialog(self, dialog: ft.AlertDialog):
        """Close a dialog.

        Args:
            dialog: Dialog to close
        """
        dialog.open = False
        self.page.update()

    def import_pdf(
        self,
        document: Dict[str, Any],
        on_success: Optional[Callable[[Path], None]] = None,
        on_error: Optional[Callable[[str], None]] = None
    ):
        """Show file picker to import a PDF manually.

        Args:
            document: Document dictionary
            on_success: Optional callback when import succeeds (receives pdf_path)
            on_error: Optional callback when import fails (receives error message)
        """
        from ..utils.pdf_manager import PDFManager

        title = document.get('title', 'Unknown Document')

        # Create file picker dialog
        def on_file_result(e: ft.FilePickerResultEvent):
            if e.files and len(e.files) > 0:
                selected_file = e.files[0]
                source_path = Path(selected_file.path)

                # Validate it's a PDF
                if not source_path.name.lower().endswith('.pdf'):
                    error_msg = "Please select a PDF file (.pdf extension)"
                    if on_error:
                        on_error(error_msg)
                    else:
                        self._show_error(error_msg)
                    return

                # Import the PDF
                self._import_pdf_file(source_path, document, on_success, on_error)
            else:
                # User cancelled
                pass

        # Create and show file picker
        file_picker = ft.FilePicker(on_result=on_file_result)
        self.page.overlay.append(file_picker)
        self.page.update()

        # Open file picker dialog
        file_picker.pick_files(
            dialog_title=f"Select PDF for: {title[:50]}...",
            allowed_extensions=["pdf"],
            allow_multiple=False
        )

    def _import_pdf_file(
        self,
        source_path: Path,
        document: Dict[str, Any],
        on_success: Optional[Callable[[Path], None]],
        on_error: Optional[Callable[[str], None]]
    ):
        """Copy selected PDF file to organized storage.

        Args:
            source_path: Path to source PDF file
            document: Document dictionary
            on_success: Success callback
            on_error: Error callback
        """
        from ..utils.pdf_manager import PDFManager
        from ..app import get_database_connection
        import shutil

        try:
            # Get database connection for updates
            db_conn = get_database_connection()
            pdf_manager = PDFManager(db_conn=db_conn)

            # Generate filename if needed
            if not document.get('pdf_filename'):
                document['pdf_filename'] = source_path.name

            # Get destination path (creates year directory)
            dest_path = pdf_manager.get_pdf_path(document, create_dirs=True)
            if dest_path is None:
                raise ValueError("Could not determine destination path")

            # Copy file to organized storage
            logger.info(f"Importing PDF from {source_path} to {dest_path}")
            shutil.copy2(source_path, dest_path)

            # Update database with relative path
            doc_id = document.get('id')
            if doc_id and db_conn:
                try:
                    relative_path = pdf_manager.get_relative_pdf_path(document)
                    if relative_path:
                        pdf_manager.update_database_pdf_path(doc_id, relative_path)
                        logger.info(f"Updated database with PDF path: {relative_path}")
                        # Update document dict for UI
                        document['pdf_filename'] = relative_path
                except Exception as e:
                    logger.error(f"Failed to update database: {e}")

            # Close database connection
            if db_conn:
                db_conn.close()

            # Success
            logger.info(f"PDF imported successfully to {dest_path}")

            if on_success:
                on_success(dest_path)

            # Show success message and open PDF
            self._show_info(
                "PDF Imported Successfully",
                f"File saved to:\n{dest_path}\n\nOpening PDF..."
            )

            # Open the imported PDF
            self.show_pdf(dest_path, document)

        except Exception as e:
            error_msg = f"Failed to import PDF: {str(e)}"
            logger.error(error_msg, exc_info=True)
            if on_error:
                on_error(error_msg)
            else:
                self._show_error(error_msg)
