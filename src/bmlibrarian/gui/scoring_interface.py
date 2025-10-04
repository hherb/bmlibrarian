"""
Interactive Scoring Interface for the Scoring Tab

Provides a dedicated interface for document scoring with progress tracking,
human editing, and the "Add More Documents" feature.
"""

import flet as ft
from typing import Callable, Dict, List, Tuple, Any


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
                ft.Row([
                    approval_checkbox,
                    score_input
                ], spacing=20)
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
