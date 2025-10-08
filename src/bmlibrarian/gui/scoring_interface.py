"""
Interactive Scoring Interface for the Scoring Tab

Provides a dedicated interface for document scoring with progress tracking,
human editing, and the "Add More Documents" feature.
"""

import flet as ft
import logging
from typing import Callable, Dict, List, Tuple, Any

logger = logging.getLogger(__name__)


class ScoringInterface:
    """Manages the interactive scoring interface in the Scoring tab."""

    def __init__(self, page: ft.Page):
        self.page = page
        self.scoring_mode = False
        self.score_overrides = {}
        self.score_approvals = {}
        self.scoring_callback = None
        self.documents = []
        self.scored_documents = []

        # UI components
        self.progress_bar = None
        self.progress_text = None
        self.scoring_container = None
        self.main_container = None

        # PDF viewer
        from .pdf_viewer_dialog import PDFViewerDialog
        self.pdf_viewer = PDFViewerDialog(page)

    def create_interface(self) -> ft.Container:
        """Create the main scoring interface container."""
        self.progress_bar = ft.ProgressBar(visible=False, width=400)
        self.progress_text = ft.Text("", size=12, color=ft.Colors.GREY_600, visible=False)

        self.main_container = ft.Container(
            content=ft.Column([
                ft.Text("Scoring interface will appear here when scoring begins",
                       size=14, color=ft.Colors.GREY_500, italic=True)
            ], spacing=10, scroll=ft.ScrollMode.AUTO),
            padding=ft.padding.all(15),
            expand=True
        )

        return self.main_container

    def start_scoring(self, documents: List[Dict], scored_documents: List[Tuple],
                     callback: Callable[[dict], None], progress_callback: Callable[[int, int], None] = None):
        """Start the interactive scoring process.

        Args:
            documents: List of all documents
            scored_documents: List of (document, scoring_result) tuples
            callback: Callback to receive final score overrides
            progress_callback: Optional callback for progress updates (current, total)
        """
        self.scoring_mode = True
        self.documents = documents
        self.scored_documents = scored_documents
        self.scoring_callback = callback
        self.score_overrides = {}
        self.score_approvals = {}

        # Build the scoring interface
        self._build_scoring_ui()

        if self.page:
            self.page.update()

    def update_progress(self, current: int, total: int, message: str = ""):
        """Update the progress bar during scoring."""
        if self.progress_bar:
            self.progress_bar.visible = True
            self.progress_bar.value = current / total if total > 0 else 0

        if self.progress_text:
            self.progress_text.visible = True
            self.progress_text.value = f"{message} ({current}/{total})"

        if self.page:
            self.page.update()

    def hide_progress(self):
        """Hide the progress bar."""
        if self.progress_bar:
            self.progress_bar.visible = False
        if self.progress_text:
            self.progress_text.visible = False
        if self.page:
            self.page.update()

    def _build_scoring_ui(self):
        """Build the interactive scoring UI."""
        from ..config import get_search_config

        # Get score threshold
        search_config = get_search_config()
        score_threshold = search_config.get('score_threshold', 2.5)

        # Separate into high-scoring and low-scoring
        high_scoring = [(doc, score) for doc, score in self.scored_documents
                       if score.get('score', 0) > score_threshold]
        low_scoring = [(doc, score) for doc, score in self.scored_documents
                      if score.get('score', 0) <= score_threshold]

        controls = []

        # Header
        controls.append(ft.Text(
            f"Interactive Document Scoring ({len(self.scored_documents)} documents)",
            size=18,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.BLUE_700
        ))

        controls.append(ft.Text(
            "Review AI scores and reasoning. Check 'Approve' to confirm, or enter a different score to override.",
            size=12,
            color=ft.Colors.GREY_600
        ))

        # Progress bar
        controls.append(ft.Container(
            content=ft.Column([
                self.progress_bar,
                self.progress_text
            ], spacing=5),
            padding=ft.padding.only(top=10, bottom=10)
        ))

        # High-scoring documents
        if high_scoring:
            controls.append(ft.Container(
                content=ft.Text(
                    f"🎯 HIGH-SCORING DOCUMENTS (Above threshold {score_threshold}): {len(high_scoring)}",
                    size=16,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.GREEN_700
                ),
                padding=ft.padding.only(top=15, bottom=10)
            ))

            for i, (doc, score_data) in enumerate(high_scoring):
                card = self._create_scoring_card(i, doc, score_data)
                controls.append(card)

        # Low-scoring documents
        if low_scoring:
            controls.append(ft.Container(
                content=ft.Text(
                    f"📉 LOW-SCORING DOCUMENTS (At or below threshold {score_threshold}): {len(low_scoring)}",
                    size=16,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.ORANGE_700
                ),
                padding=ft.padding.only(top=20, bottom=10)
            ))

            for i, (doc, score_data) in enumerate(low_scoring, start=len(high_scoring)):
                card = self._create_scoring_card(i, doc, score_data)
                controls.append(card)

        # Action buttons
        button_row = ft.Row([
            ft.ElevatedButton(
                "Apply Changes and Continue",
                icon=ft.Icons.CHECK,
                on_click=self._on_apply_overrides,
                bgcolor=ft.Colors.GREEN_600,
                color=ft.Colors.WHITE
            ),
            ft.TextButton(
                "Continue Without Changes",
                icon=ft.Icons.ARROW_FORWARD,
                on_click=self._on_continue_no_changes
            )
        ], spacing=10, alignment=ft.MainAxisAlignment.END)

        controls.append(ft.Container(
            content=button_row,
            padding=ft.padding.only(top=20, bottom=10)
        ))

        # Update main container
        self.main_container.content = ft.Column(
            controls,
            spacing=10,
            scroll=ft.ScrollMode.AUTO
        )

        if self.page:
            self.page.update()

    def _create_scoring_card(self, index: int, doc: dict, scoring_result: dict) -> ft.Container:
        """Create an interactive scoring card for a document."""
        title = doc.get('title', 'Untitled Document')
        abstract = doc.get('abstract', 'No abstract available')[:300]
        ai_score = scoring_result.get('score', 0)
        reasoning = scoring_result.get('reasoning', 'No reasoning provided')

        # Approval checkbox
        approval_checkbox = ft.Checkbox(
            label="Approve AI score",
            value=False,
            on_change=lambda e: self._on_approval_change(index, e.control.value)
        )

        # Score override input
        score_input = ft.TextField(
            label="Override score (1-5)",
            hint_text=f"AI: {ai_score}",
            width=150,
            on_change=lambda e: self._on_score_override(index, e.control.value)
        )

        # PDF button (show full text or fetch full text)
        pdf_button = self._create_pdf_button(doc)

        # Build controls row
        controls_row = ft.Row([
            approval_checkbox,
            score_input
        ], spacing=20)

        # Add PDF button if available
        if pdf_button:
            controls_row.controls.append(pdf_button)

        # Build card
        return ft.Container(
            content=ft.Column([
                ft.Text(f"Document {index + 1}: {title}",
                       size=14, weight=ft.FontWeight.BOLD),
                ft.Text(f"Abstract: {abstract}...",
                       size=12, color=ft.Colors.GREY_700),
                ft.Container(
                    content=ft.Column([
                        ft.Text(f"AI Score: {ai_score}/5",
                               size=13, weight=ft.FontWeight.BOLD,
                               color=ft.Colors.BLUE_700),
                        ft.Text(f"Reasoning: {reasoning}",
                               size=12, color=ft.Colors.GREY_600)
                    ], spacing=5),
                    padding=ft.padding.all(10),
                    bgcolor=ft.Colors.BLUE_50,
                    border_radius=5
                ),
                controls_row
            ], spacing=8),
            padding=ft.padding.all(15),
            bgcolor=ft.Colors.GREY_50,
            border=ft.border.all(1, ft.Colors.GREY_300),
            border_radius=8
        )

    def _on_approval_change(self, index: int, approved: bool):
        """Handle approval checkbox change."""
        if approved:
            self.score_approvals[index] = True
            # Remove any override if approving
            if index in self.score_overrides:
                del self.score_overrides[index]
        else:
            if index in self.score_approvals:
                del self.score_approvals[index]

    def _on_score_override(self, index: int, value: str):
        """Handle score override input."""
        if value.strip():
            try:
                score = float(value.strip())
                if 1 <= score <= 5:
                    self.score_overrides[index] = score
                    # Remove approval if overriding
                    if index in self.score_approvals:
                        del self.score_approvals[index]
            except ValueError:
                pass
        else:
            if index in self.score_overrides:
                del self.score_overrides[index]

    def _on_apply_overrides(self, e):
        """Apply score overrides and continue workflow."""
        if self.scoring_callback:
            result = {
                'overrides': self.score_overrides,
                'approvals': self.score_approvals
            }
            self.scoring_callback(result)
        self.scoring_mode = False

    def _on_continue_no_changes(self, e):
        """Continue workflow without any changes."""
        if self.scoring_callback:
            self.scoring_callback({
                'overrides': {},
                'approvals': {}
            })
        self.scoring_mode = False

    def disable_scoring(self):
        """Disable scoring mode and show results."""
        self.scoring_mode = False
        # The scoring tab will be updated by the normal update flow

    def _create_pdf_button(self, doc: dict) -> ft.Control:
        """Create PDF button(s) for a document.

        Args:
            doc: Document dictionary

        Returns:
            Button control or Row of buttons, or None if nothing available
        """
        from ..utils.pdf_manager import PDFManager

        pdf_manager = PDFManager()

        # Primary button (main action)
        primary_button = None

        # Check if PDF already exists locally
        if pdf_manager.pdf_exists(doc):
            primary_button = ft.ElevatedButton(
                "Show Full Text",
                icon=ft.Icons.PICTURE_AS_PDF,
                on_click=lambda e: self._on_show_pdf(doc),
                bgcolor=ft.Colors.GREEN_600,
                color=ft.Colors.WHITE,
                tooltip="Open PDF with system viewer"
            )
        # Check if PDF URL is available for download
        elif doc.get('pdf_url'):
            primary_button = ft.ElevatedButton(
                "Fetch Full Text",
                icon=ft.Icons.DOWNLOAD,
                on_click=lambda e: self._on_fetch_pdf(doc),
                bgcolor=ft.Colors.ORANGE_600,
                color=ft.Colors.WHITE,
                tooltip="Download and open PDF"
            )
        # Check if document URL is available
        elif doc.get('url'):
            primary_button = ft.ElevatedButton(
                "Browse Online",
                icon=ft.Icons.OPEN_IN_BROWSER,
                on_click=lambda e: self._on_browse_url(doc, doc['url']),
                bgcolor=ft.Colors.BLUE_600,
                color=ft.Colors.WHITE,
                tooltip="Open document page in browser"
            )
        # Check if DOI is available (can construct URL)
        elif doc.get('doi'):
            doi_url = f"https://doi.org/{doc['doi']}"
            primary_button = ft.ElevatedButton(
                "Browse DOI",
                icon=ft.Icons.OPEN_IN_BROWSER,
                on_click=lambda e: self._on_browse_url(doc, doi_url),
                bgcolor=ft.Colors.BLUE_400,
                color=ft.Colors.WHITE,
                tooltip=f"Open DOI: {doc['doi']}"
            )

        # Always provide "Import PDF" option if no local PDF exists
        if not pdf_manager.pdf_exists(doc):
            import_button = ft.ElevatedButton(
                "Import PDF",
                icon=ft.Icons.UPLOAD_FILE,
                on_click=lambda e: self._on_import_pdf(doc),
                bgcolor=ft.Colors.PURPLE_600,
                color=ft.Colors.WHITE,
                tooltip="Import PDF file from your computer"
            )

            # If we have a primary button, show both
            if primary_button:
                return ft.Row([primary_button, import_button], spacing=10)
            else:
                # Only import button available
                return import_button
        else:
            # PDF exists, just return primary button
            return primary_button

    def _on_show_pdf(self, doc: dict):
        """Handle 'Show Full Text' button click.

        Args:
            doc: Document dictionary
        """
        from ..utils.pdf_manager import PDFManager

        pdf_manager = PDFManager()
        pdf_path = pdf_manager.get_pdf_path(doc)

        if pdf_path and pdf_path.exists():
            self.pdf_viewer.show_pdf(pdf_path, doc)
        else:
            # Shouldn't happen, but handle gracefully
            self._show_error("PDF file not found")

    def _on_fetch_pdf(self, doc: dict):
        """Handle 'Fetch Full Text' button click.

        Args:
            doc: Document dictionary
        """
        def on_success(pdf_path):
            # Update button state (would need to rebuild card, but for now just notify)
            pass

        def on_error(error_msg):
            pass

        self.pdf_viewer.download_and_show_pdf(doc, on_success, on_error)

    def _on_browse_url(self, doc: dict, url: str):
        """Handle 'Browse Online' or 'Browse DOI' button click.

        Args:
            doc: Document dictionary
            url: URL to open in browser
        """
        import webbrowser

        try:
            webbrowser.open(url)
            # Show confirmation
            title = doc.get('title', 'Document')
            if self.page:
                self.page.show_snack_bar(
                    ft.SnackBar(
                        content=ft.Text(f"Opening in browser: {title[:50]}..."),
                        bgcolor=ft.Colors.BLUE_700
                    )
                )
        except Exception as e:
            logger.error(f"Failed to open URL in browser: {e}")
            self._show_error(f"Failed to open browser: {str(e)}")

    def _on_import_pdf(self, doc: dict):
        """Handle 'Import PDF' button click.

        Args:
            doc: Document dictionary
        """
        def on_success(pdf_path):
            # Rebuild the scoring UI to update button from "Import" to "Show"
            # For now, just show success message
            if self.page:
                self.page.show_snack_bar(
                    ft.SnackBar(
                        content=ft.Text(f"PDF imported successfully!"),
                        bgcolor=ft.Colors.GREEN_700
                    )
                )

        def on_error(error_msg):
            # Error already shown by pdf_viewer
            pass

        self.pdf_viewer.import_pdf(doc, on_success, on_error)

    def _show_error(self, message: str):
        """Show error snackbar.

        Args:
            message: Error message
        """
        if self.page:
            self.page.show_snack_bar(
                ft.SnackBar(
                    content=ft.Text(message),
                    bgcolor=ft.Colors.RED_700
                )
            )
