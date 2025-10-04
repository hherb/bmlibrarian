"""
GUI Components for BMLibrarian Research Interface

Contains the StepCard class for workflow progress tracking.
Uses modular components from:
- status_icons.py: Status icon/color utilities
- progress_widgets.py: Progress bar components
- document_cards.py: Document display cards
- citation_review.py: Citation review components
- text_highlighting.py: Text highlighting utilities
"""

import flet as ft
from typing import Optional, Callable, List, Dict
from ..cli.workflow_steps import WorkflowStep

# Import modular utilities
from .status_icons import get_status_icon, get_status_color, get_score_color
from .progress_widgets import create_simple_progress_bar, create_detailed_progress_container, get_progress_components
from .document_cards import create_document_result_card, create_document_scoring_card
from .citation_review import create_citation_review_card, toggle_citation_status


class StepCard:
    """A collapsible card representing a workflow step."""

    def __init__(self, step: WorkflowStep, on_expand_change: Optional[Callable] = None):
        self.step = step
        self.expanded = False
        self.status = "pending"  # pending, running, completed, error, waiting
        self.content = ""
        self.error_message = ""
        self.on_expand_change = on_expand_change

        # UI components
        self.expansion_tile = None
        self.content_text = None
        self.status_icon = None
        self.progress_bar = None
        self.detailed_progress_container = None
        self.detailed_progress_text = None
        self.detailed_progress_bar = None
        self.detailed_progress_item = None

        # Inline editing components
        self.editing_mode = False
        self.edit_field = None
        self.accept_button = None
        self.cancel_button = None
        self.edit_container = None
        self.edit_callback = None

        # Document scoring components
        self.scoring_mode = False
        self.document_scoring_data = None
        self.score_overrides = {}
        self.score_approvals = {}
        self.scoring_callback = None
        self.scoring_container = None

        # Document search results components
        self.search_results_mode = False
        self.document_search_data = None
        self.search_results_container = None

        # Citation review components
        self.citation_review_mode = False
        self.citation_data = None
        self.citation_reviews = {}
        self.citation_callback = None
        self.citation_container = None

    def build(self) -> ft.ExpansionTile:
        """Build the expansion tile UI component."""
        # Status icon based on current status
        self.status_icon = ft.Icon(
            name=get_status_icon(self.status),
            color=get_status_color(self.status),
            size=20
        )

        # Progress bars
        self.progress_bar = create_simple_progress_bar(visible=False)
        self.detailed_progress_container = create_detailed_progress_container(visible=False)

        # Store references to detailed progress components
        self.detailed_progress_text, self.detailed_progress_bar, self.detailed_progress_item = \
            get_progress_components(self.detailed_progress_container)

        # Content text area
        self.content_text = ft.Text(
            value=self.content or "Waiting to start...",
            size=12,
            color=ft.Colors.GREY_700,
            selectable=True
        )

        # Content container
        content_container = ft.Container(
            content=ft.Column([
                self.progress_bar,
                self.detailed_progress_container,
                ft.Container(
                    content=self.content_text,
                    padding=ft.padding.all(10),
                    bgcolor=ft.Colors.GREY_50,
                    border_radius=5
                )
            ], spacing=5),
            padding=ft.padding.only(left=10, right=10, bottom=10)
        )

        # Build expansion tile with minimal parameters
        self.expansion_tile = ft.ExpansionTile(
            title=ft.Row([
                self.status_icon,
                ft.Text(self.step.display_name, size=14, weight=ft.FontWeight.W_500),
            ], spacing=8),
            subtitle=ft.Text(self.step.description, size=12, color=ft.Colors.GREY_600),
            controls=[content_container]
        )

        return self.expansion_tile

    def update_status(self, status: str, content: Optional[str] = None, error: Optional[str] = None):
        """Update the step status and content."""
        self.status = status
        if content is not None:
            self.content = content
        if error is not None:
            self.error_message = error

        # Update UI components if they exist
        if self.status_icon:
            self.status_icon.name = get_status_icon(self.status)
            self.status_icon.color = get_status_color(self.status)

        if self.progress_bar:
            self.progress_bar.visible = (status == "running")

        if self.content_text:
            display_content = self.content
            if self.error_message:
                display_content += f"\n\nError: {self.error_message}"
            self.content_text.value = display_content or "Waiting to start..."

    def update_progress(self, current: int, total: int, item_name: str = ""):
        """Update the detailed progress bar with tqdm-style display.

        Args:
            current: Current progress count
            total: Total items to process
            item_name: Name/description of current item being processed
        """
        if total <= 0:
            return

        # Calculate progress percentage
        progress_value = current / total

        # Update progress components
        if self.detailed_progress_text:
            self.detailed_progress_text.value = f"{current}/{total} ({progress_value*100:.1f}%)"

        if self.detailed_progress_bar:
            self.detailed_progress_bar.value = progress_value

        if self.detailed_progress_item and item_name:
            self.detailed_progress_item.value = item_name

        # Show/hide detailed progress container based on status
        if self.detailed_progress_container:
            self.detailed_progress_container.visible = (self.status == "running" and total > 1)

    def show_detailed_progress(self, visible: bool = True):
        """Show or hide the detailed progress bar."""
        if self.detailed_progress_container:
            self.detailed_progress_container.visible = visible

    def enable_inline_editing(self, initial_text: str, callback: Callable[[bool, str], None]):
        """Enable inline editing mode with text field and accept/cancel buttons."""
        self.editing_mode = True
        self.edit_callback = callback

        # Create edit field
        self.edit_field = ft.TextField(
            value=initial_text,
            multiline=True,
            min_lines=3,
            max_lines=8,
            expand=True,
            hint_text="Edit the query as needed (no markdown formatting)"
        )

        # Create buttons
        self.accept_button = ft.ElevatedButton(
            "Accept",
            icon=ft.Icons.CHECK,
            on_click=self._on_accept_edit,
            bgcolor=ft.Colors.GREEN_600,
            color=ft.Colors.WHITE,
            height=36
        )

        self.cancel_button = ft.TextButton(
            "Cancel",
            icon=ft.Icons.CLOSE,
            on_click=self._on_cancel_edit,
            height=36
        )

        # Create edit container
        self.edit_container = ft.Container(
            content=ft.Column([
                ft.Text("Edit Query:", size=12, weight=ft.FontWeight.BOLD),
                ft.Text("Use & for AND, | for OR, () for grouping. No backticks or markdown.",
                        size=10, color=ft.Colors.GREY_600),
                self.edit_field,
                ft.Row([
                    self.accept_button,
                    self.cancel_button
                ], spacing=10, alignment=ft.MainAxisAlignment.END)
            ], spacing=10),
            padding=ft.padding.all(10),
            bgcolor=ft.Colors.YELLOW_50,
            border=ft.border.all(2, ft.Colors.ORANGE_300),
            border_radius=5
        )

        # Replace content container with edit container
        self._update_expansion_content([
            self.progress_bar,
            self.detailed_progress_container,
            self.edit_container,
            self._create_content_container()
        ])

        # Auto-expand the tile to show editing interface
        if self.expansion_tile:
            self.expansion_tile.initially_expanded = True

    def disable_inline_editing(self):
        """Disable inline editing mode and return to normal view."""
        self.editing_mode = False
        self.edit_callback = None
        self._restore_normal_view()

    def _on_accept_edit(self, _):
        """Handle accept button click."""
        if self.edit_callback and self.edit_field:
            edited_text = self.edit_field.value or ""
            self.edit_callback(True, edited_text)

    def _on_cancel_edit(self, _):
        """Handle cancel button click."""
        if self.edit_callback:
            self.edit_callback(False, "")

    def enable_document_scoring(self, documents, scored_documents, callback: Callable[[dict], None]):
        """Enable document scoring mode with editable score fields for human override."""
        self.scoring_mode = True
        self.document_scoring_data = {
            'documents': documents,
            'scored_documents': scored_documents
        }
        self.scoring_callback = callback
        self.score_overrides = {}
        self.score_approvals = {}

        # Create scoring interface
        scoring_controls = []

        # Header
        scoring_controls.append(
            ft.Text(
                f"Document Scoring Results ({len(scored_documents)} documents above threshold)",
                size=14,
                weight=ft.FontWeight.BOLD
            )
        )

        scoring_controls.append(
            ft.Text(
                "Review AI scores and reasoning. Check 'Approve' to confirm AI score, or enter a different score to override.",
                size=12,
                color=ft.Colors.GREY_600
            )
        )

        # Document scoring cards using modular function
        for i, (doc, scoring_result) in enumerate(scored_documents):
            doc_card = create_document_scoring_card(
                i, doc, scoring_result,
                on_score_override=self._on_score_override_change,
                on_score_approval=self._on_score_approval_change
            )
            scoring_controls.append(doc_card)

        # Action buttons
        button_row = ft.Row([
            ft.ElevatedButton(
                "Apply Overrides",
                icon=ft.Icons.CHECK,
                on_click=self._on_apply_score_overrides,
                bgcolor=ft.Colors.GREEN_600,
                color=ft.Colors.WHITE
            ),
            ft.TextButton(
                "Continue with AI Scores",
                icon=ft.Icons.ARROW_FORWARD,
                on_click=self._on_continue_ai_scores
            )
        ], spacing=10, alignment=ft.MainAxisAlignment.END)

        scoring_controls.append(button_row)

        # Create scoring container
        self.scoring_container = ft.Container(
            content=ft.Column(scoring_controls, spacing=10, scroll=ft.ScrollMode.AUTO),
            padding=ft.padding.all(10),
            bgcolor=ft.Colors.BLUE_50,
            border=ft.border.all(2, ft.Colors.BLUE_300),
            border_radius=5,
            height=600
        )

        # Replace content container with scoring container
        self._update_expansion_content([
            self.progress_bar,
            self.detailed_progress_container,
            self.scoring_container,
            self._create_content_container()
        ])

        # Auto-expand the tile to show scoring interface
        if self.expansion_tile:
            self.expansion_tile.initially_expanded = True

    def _on_score_override_change(self, index: int, value: str):
        """Handle changes to human score override fields."""
        try:
            if value and value.strip():
                score = float(value)
                if 1 <= score <= 5:
                    self.score_overrides[index] = score
                    self.score_approvals.pop(index, None)
                else:
                    self.score_overrides.pop(index, None)
            else:
                self.score_overrides.pop(index, None)
        except ValueError:
            self.score_overrides.pop(index, None)

    def _on_score_approval_change(self, index: int, approved: bool):
        """Handle changes to approval checkboxes."""
        if approved:
            self.score_approvals[index] = True
            self.score_overrides.pop(index, None)
        else:
            self.score_approvals.pop(index, None)

    def _on_apply_score_overrides(self, _):
        """Handle apply overrides button click."""
        if self.scoring_callback:
            self.scoring_callback({
                'overrides': self.score_overrides,
                'approvals': self.score_approvals
            })
        self.disable_document_scoring()

    def _on_continue_ai_scores(self, _):
        """Handle continue with AI scores button click."""
        if self.scoring_callback:
            self.scoring_callback({})
        self.disable_document_scoring()

    def disable_document_scoring(self):
        """Disable document scoring mode and return to normal view."""
        self.scoring_mode = False
        self.scoring_callback = None
        self.score_overrides = {}
        self._restore_normal_view()

    def enable_document_search_results(self, documents: List[Dict]):
        """Enable document search results mode with expandable document listings."""
        self.search_results_mode = True
        self.document_search_data = {'documents': documents}

        print(f"Creating search results interface for {len(documents)} documents")

        # Update the content text to show search results summary first
        summary_text = f"📋 Found {len(documents)} documents - click below to expand and browse all results"
        if self.content_text:
            self.content_text.value = summary_text

        # Create search results interface
        results_controls = []

        # Header
        results_controls.append(
            ft.Text(
                f"Search Results ({len(documents)} documents found)",
                size=14,
                weight=ft.FontWeight.BOLD
            )
        )

        results_controls.append(
            ft.Text(
                "Click on any document to expand and view the full abstract.",
                size=12,
                color=ft.Colors.GREY_600
            )
        )

        # Document result cards using modular function
        for i, doc in enumerate(documents):
            doc_card = create_document_result_card(i, doc)
            results_controls.append(doc_card)

        # Create search results container
        self.search_results_container = ft.Container(
            content=ft.Column(results_controls, spacing=8, scroll=ft.ScrollMode.AUTO),
            padding=ft.padding.all(10),
            bgcolor=ft.Colors.GREEN_50,
            border=ft.border.all(2, ft.Colors.GREEN_300),
            border_radius=5,
            height=600
        )

        # Replace content container with search results container
        self._update_expansion_content([
            self.progress_bar,
            self.detailed_progress_container,
            self.search_results_container,
            self._create_content_container()
        ])

        # Auto-expand the tile to show search results
        if self.expansion_tile:
            self.expansion_tile.initially_expanded = True
            print("Expansion tile set to initially expanded")

    def disable_document_search_results(self):
        """Disable document search results mode and return to normal view."""
        self.search_results_mode = False
        self.document_search_data = None
        self._restore_normal_view()

    def enable_citation_review(self, citations: List, callback: Callable[[Dict[int, str]], None]):
        """Enable citation review mode with accept/refuse/unrated toggle for each citation."""
        self.citation_review_mode = True
        self.citation_data = {'citations': citations}
        self.citation_callback = callback
        self.citation_reviews = {}

        # Create citation review interface
        review_controls = []

        # Header
        review_controls.append(
            ft.Text(
                f"Citation Review ({len(citations)} citations extracted)",
                size=14,
                weight=ft.FontWeight.BOLD
            )
        )

        review_controls.append(
            ft.Text(
                "Review each citation. The passage is highlighted in the abstract. Toggle: Refuse ❌ → Unrated ⚪ → Accept ✅",
                size=12,
                color=ft.Colors.GREY_600
            )
        )

        # Citation review cards using modular function
        for i, citation in enumerate(citations):
            citation_card = create_citation_review_card(i, citation, on_toggle=self._toggle_citation_status)
            review_controls.append(citation_card)

        # Action buttons
        button_row = ft.Row([
            ft.ElevatedButton(
                "Continue with Reviewed Citations",
                icon=ft.Icons.CHECK_CIRCLE,
                on_click=self._on_apply_citation_reviews,
                bgcolor=ft.Colors.GREEN_700,
                color=ft.Colors.WHITE
            ),
            ft.TextButton(
                "Continue with All Citations",
                icon=ft.Icons.SKIP_NEXT,
                on_click=self._on_continue_all_citations
            )
        ], spacing=10)

        review_controls.append(ft.Container(height=10))
        review_controls.append(button_row)

        # Create scrollable container for citations
        self.citation_container = ft.Container(
            content=ft.Column(
                controls=review_controls,
                spacing=10,
                scroll=ft.ScrollMode.AUTO
            ),
            padding=ft.padding.all(15),
            bgcolor=ft.Colors.BLUE_50,
            border=ft.border.all(2, ft.Colors.BLUE_300),
            border_radius=5,
            height=600
        )

        # Replace content container with citation review container
        self._update_expansion_content([
            self.progress_bar,
            self.detailed_progress_container,
            self.citation_container,
            self._create_content_container()
        ])

        # Auto-expand the tile to show citation review interface
        if self.expansion_tile:
            self.expansion_tile.initially_expanded = True

    def _toggle_citation_status(self, index: int, button):
        """Toggle citation status using modular function."""
        new_status = toggle_citation_status(button)
        self.citation_reviews[index] = new_status
        button.update()

    def _on_apply_citation_reviews(self, _):
        """Handle apply citation reviews button click."""
        if self.citation_callback:
            self.citation_callback(self.citation_reviews)
        self.disable_citation_review()

    def _on_continue_all_citations(self, _):
        """Handle continue with all citations button click."""
        if self.citation_callback:
            self.citation_callback({})
        self.disable_citation_review()

    def disable_citation_review(self):
        """Disable citation review mode and return to normal view."""
        self.citation_review_mode = False
        self.citation_data = None
        self.citation_reviews = {}
        self._restore_normal_view()

    # Helper methods

    def _create_content_container(self) -> ft.Container:
        """Create the standard content container."""
        return ft.Container(
            content=self.content_text,
            padding=ft.padding.all(10),
            bgcolor=ft.Colors.GREY_50,
            border_radius=5
        )

    def _update_expansion_content(self, controls: List[ft.Control]):
        """Update the expansion tile content with new controls."""
        if self.expansion_tile and len(self.expansion_tile.controls) > 0:
            content_container = self.expansion_tile.controls[0]
            if hasattr(content_container, 'content') and hasattr(content_container.content, 'controls'):
                content_container.content.controls = controls

    def _restore_normal_view(self):
        """Restore the normal content view."""
        self._update_expansion_content([
            self.progress_bar,
            self.detailed_progress_container,
            self._create_content_container()
        ])
