"""
Tab Manager Module for Research GUI

Handles creation and management of the tabbed interface with reusable functions.
"""

import flet as ft
from typing import Dict, List, Optional, Any
from .components import StepCard
from .ui_builder import create_tab_header, create_empty_state
from .scoring_interface import ScoringInterface
from ..cli.workflow_steps import WorkflowStep


class TabManager:
    """Manages the tabbed interface for the research GUI."""

    def __init__(self, page: ft.Page = None):
        self.tabs_container: Optional[ft.Tabs] = None
        self.tab_contents: Dict[str, ft.Container] = {}
        self.scoring_interface: Optional[ScoringInterface] = None
        self.page = page

        # Store references to event handlers (will be set after initialization)
        self.event_handlers = None

        # Create scoring interface if page is available
        if page:
            self.scoring_interface = ScoringInterface(page)
        
    def create_tabbed_interface(self, step_cards: Dict[WorkflowStep, StepCard]) -> ft.Tabs:
        """Create the complete tabbed interface following workflow progression."""
        search_tab = self._create_search_tab()
        literature_tab = self._create_literature_tab()
        scoring_tab = self._create_scoring_tab()
        citations_tab = self._create_citations_tab()
        preliminary_report_tab = self._create_preliminary_report_tab()
        counterfactual_tab = self._create_counterfactual_tab()
        report_tab = self._create_report_tab()
        settings_tab = self._create_settings_tab()

        self.tabs_container = ft.Tabs(
            selected_index=0,
            animation_duration=300,
            tabs=[
                ft.Tab(
                    text="Search",
                    icon=ft.Icons.SEARCH,
                    content=search_tab
                ),
                ft.Tab(
                    text="Literature",
                    icon=ft.Icons.LIBRARY_BOOKS,
                    content=literature_tab
                ),
                ft.Tab(
                    text="Scoring",
                    icon=ft.Icons.ANALYTICS,
                    content=scoring_tab
                ),
                ft.Tab(
                    text="Citations",
                    icon=ft.Icons.FORMAT_QUOTE,
                    content=citations_tab
                ),
                ft.Tab(
                    text="Preliminary",
                    icon=ft.Icons.ARTICLE,
                    content=preliminary_report_tab
                ),
                ft.Tab(
                    text="Counterfactual",
                    icon=ft.Icons.PSYCHOLOGY,
                    content=counterfactual_tab
                ),
                ft.Tab(
                    text="Report",
                    icon=ft.Icons.DESCRIPTION,
                    content=report_tab
                ),
                ft.Tab(
                    text="Settings",
                    icon=ft.Icons.SETTINGS,
                    content=settings_tab
                )
            ],
            tab_alignment=ft.TabAlignment.START
        )

        return self.tabs_container
    
    def _create_search_tab(self) -> ft.Container:
        """Create the search tab showing research question and generated query."""
        header_components = create_tab_header(
            "Search Query",
            subtitle="Research question and generated PostgreSQL query."
        )

        # Progress bar for query generation
        self.search_progress_bar = ft.ProgressBar(
            value=None,
            bar_height=4,
            color=ft.Colors.BLUE_400,
            bgcolor=ft.Colors.BLUE_50,
            visible=False
        )

        # Progress text for query generation
        self.search_progress_text = ft.Text(
            "",
            size=11,
            color=ft.Colors.GREY_600,
            visible=False
        )

        # Question display
        self.search_question_text = ft.Text(
            "No research question yet.",
            size=14,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.BLUE_800
        )

        # Query display (editable in interactive mode)
        self.search_query_text = ft.Text(
            "Query will appear here after generation...",
            size=12,
            selectable=True,
            color=ft.Colors.GREY_700
        )

        # Multi-model query details container (shows all queries with results)
        self.search_queries_detail = ft.Column(
            spacing=5,
            visible=False
        )

        # Query performance statistics container (shown after scoring completes)
        self.search_performance_stats = ft.Container(
            visible=False,
            border=ft.border.all(1, ft.Colors.BLUE_200),
            border_radius=8,
            padding=15,
            bgcolor=ft.Colors.BLUE_50
        )

        # Query edit field (hidden by default, shown in interactive mode)
        self.search_query_edit = ft.TextField(
            multiline=True,
            min_lines=5,
            max_lines=15,
            visible=False,
            hint_text="Edit the PostgreSQL query as needed"
        )

        # Callback for workflow integration
        self.search_edit_callback = None

        # Action buttons for interactive mode
        self.search_edit_button = ft.ElevatedButton(
            "Edit Query",
            icon=ft.Icons.EDIT,
            visible=False,
            on_click=self._on_search_edit_query
        )

        self.search_accept_button = ft.ElevatedButton(
            "Accept & Continue",
            icon=ft.Icons.CHECK,
            visible=False,
            bgcolor=ft.Colors.GREEN_600,
            color=ft.Colors.WHITE,
            on_click=self._on_search_accept_query
        )

        self.search_cancel_button = ft.TextButton(
            "Cancel",
            icon=ft.Icons.CLOSE,
            visible=False,
            on_click=self._on_search_cancel_edit
        )

        content = ft.Column(
            [
                *header_components,
                self.search_progress_bar,
                self.search_progress_text,
                ft.Container(height=10),
                ft.Text("Research Question:", size=12, weight=ft.FontWeight.BOLD),
                self.search_question_text,
                ft.Container(height=10),
                ft.Text("Generated Query:", size=12, weight=ft.FontWeight.BOLD),
                self.search_query_text,
                self.search_queries_detail,  # Add multi-model details container
                self.search_query_edit,
                ft.Row(
                    [self.search_edit_button, self.search_accept_button, self.search_cancel_button],
                    spacing=10
                ),
                ft.Container(height=10),
                self.search_performance_stats  # Add performance statistics container
            ],
            spacing=10,
            scroll=ft.ScrollMode.AUTO
        )

        self.tab_contents['search'] = ft.Container(
            content=content,
            padding=ft.padding.all(15),
            expand=True
        )

        return self.tab_contents['search']

    def update_search_progress(self, message: str, show_bar: bool = True):
        """Update search tab progress text.

        Args:
            message: Progress message to display
            show_bar: Whether to show the progress bar
        """
        self.search_progress_text.value = message
        self.search_progress_text.visible = bool(message)
        self.search_progress_bar.visible = show_bar
        if self.page:
            self.page.update()

    def enable_search_query_editing(self, query_text: str, callback):
        """Enable search query editing mode and set workflow callback.

        Args:
            query_text: The generated query to edit
            callback: Function to call with (approved: bool, edited_query: str)
        """
        # Store the callback
        self.search_edit_callback = callback

        # Set the query text
        self.search_query_text.value = query_text
        self.search_query_edit.value = query_text

        # Show edit mode immediately (auto-expand for user to see)
        self.search_query_text.visible = False
        self.search_query_edit.visible = True
        self.search_edit_button.visible = False
        self.search_accept_button.visible = True
        self.search_cancel_button.visible = True

        # Switch to Search tab
        if self.tabs_container:
            self.tabs_container.selected_index = 0  # Search tab

        if self.page:
            self.page.update()

    def disable_search_query_editing(self):
        """Disable search query editing mode."""
        self.search_edit_callback = None
        self.search_query_text.visible = True
        self.search_query_edit.visible = False
        self.search_edit_button.visible = False
        self.search_accept_button.visible = False
        self.search_cancel_button.visible = False

        if self.page:
            self.page.update()

    def _on_search_edit_query(self, e):
        """Handle edit query button click."""
        self.search_query_edit.value = self.search_query_text.value
        self.search_query_text.visible = False
        self.search_query_edit.visible = True
        self.search_edit_button.visible = False
        self.search_accept_button.visible = True
        self.search_cancel_button.visible = True
        if self.page:
            self.page.update()

    def _on_search_accept_query(self, e):
        """Handle accept query button click."""
        edited_query = self.search_query_edit.value

        # Update query text
        self.search_query_text.value = edited_query
        self.search_query_text.visible = True
        self.search_query_edit.visible = False
        self.search_edit_button.visible = False
        self.search_accept_button.visible = False
        self.search_cancel_button.visible = False

        # Call workflow callback if set
        if self.search_edit_callback:
            self.search_edit_callback(True, edited_query)

        if self.page:
            self.page.update()

    def _on_search_cancel_edit(self, e):
        """Handle cancel edit button click."""
        self.search_query_text.visible = True
        self.search_query_edit.visible = False
        self.search_edit_button.visible = False
        self.search_accept_button.visible = False
        self.search_cancel_button.visible = False

        # Call workflow callback if set
        if self.search_edit_callback:
            self.search_edit_callback(False, "")

        if self.page:
            self.page.update()
    
    def _create_literature_tab(self) -> ft.Container:
        """Create the literature review tab content with progress bar and action buttons."""
        header_components = create_tab_header(
            "Literature Review",
            subtitle="Documents retrieved from database search."
        )

        # Progress bar for document search
        self.literature_progress_bar = ft.ProgressBar(
            value=None,
            bar_height=4,
            color=ft.Colors.GREEN_400,
            bgcolor=ft.Colors.GREEN_50,
            visible=False
        )

        # Detailed progress (tqdm-style) for document retrieval
        self.literature_progress_text = ft.Text(
            "",
            size=11,
            color=ft.Colors.GREY_600,
            visible=False
        )

        # Empty state
        empty_state = create_empty_state("No documents found yet.")

        # Container for document list (will be populated dynamically)
        self.literature_document_list = ft.Column(
            [empty_state],
            spacing=8,
            scroll=ft.ScrollMode.AUTO
        )

        # Action buttons for interactive mode
        self.literature_continue_button = ft.ElevatedButton(
            "Continue to Scoring",
            icon=ft.Icons.ARROW_FORWARD,
            visible=False,
            bgcolor=ft.Colors.BLUE_600,
            color=ft.Colors.WHITE,
            on_click=self._on_literature_continue
        )

        self.literature_refine_button = ft.TextButton(
            "Refine Search Query",
            icon=ft.Icons.REFRESH,
            visible=False,
            on_click=self._on_literature_refine
        )

        content = ft.Column(
            [
                *header_components,
                self.literature_progress_bar,
                self.literature_progress_text,
                ft.Container(height=5),
                self.literature_document_list,
                ft.Container(height=10),
                ft.Row(
                    [self.literature_continue_button, self.literature_refine_button],
                    spacing=10
                )
            ],
            spacing=10,
            scroll=ft.ScrollMode.AUTO
        )

        self.tab_contents['literature'] = ft.Container(
            content=content,
            padding=ft.padding.all(15),
            expand=True
        )

        return self.tab_contents['literature']

    def _on_literature_continue(self, e):
        """Handle continue to scoring button click."""
        # Switch to scoring tab
        if self.tabs_container:
            self.tabs_container.selected_index = 2  # Scoring tab
            if self.page:
                self.page.update()

    def _on_literature_refine(self, e):
        """Handle refine search query button click."""
        # Switch back to search tab
        if self.tabs_container:
            self.tabs_container.selected_index = 0  # Search tab
            # Show edit mode in search tab
            self.search_edit_button.visible = False
            self.search_query_text.visible = False
            self.search_query_edit.visible = True
            self.search_query_edit.value = self.search_query_text.value
            self.search_accept_button.visible = True
            self.search_cancel_button.visible = True
            if self.page:
                self.page.update()
    
    def _create_scoring_tab(self) -> ft.Container:
        """Create the scoring results tab content with progress bar and action buttons."""
        header_components = create_tab_header(
            "Document Scoring",
            subtitle="AI-powered relevance scoring (1-5 scale) for retrieved documents."
        )

        # Progress bar for scoring
        self.scoring_progress_bar = ft.ProgressBar(
            value=0,
            bar_height=4,
            color=ft.Colors.ORANGE_400,
            bgcolor=ft.Colors.ORANGE_50,
            visible=False
        )

        # Detailed progress (tqdm-style) for document scoring
        self.scoring_progress_text = ft.Text(
            "",
            size=11,
            color=ft.Colors.GREY_600,
            visible=False
        )

        # Create scoring interface if not already created
        if not self.scoring_interface and self.page:
            self.scoring_interface = ScoringInterface(self.page)

        # Use scoring interface if available, otherwise create placeholder
        if self.scoring_interface:
            scoring_results_content = self.scoring_interface.create_interface()
        else:
            empty_state = create_empty_state("No scored documents yet.")
            scoring_results_content = ft.Column([empty_state], spacing=10)

        # Action buttons for interactive mode
        self.scoring_continue_button = ft.ElevatedButton(
            "Continue to Citations",
            icon=ft.Icons.ARROW_FORWARD,
            visible=False,
            bgcolor=ft.Colors.BLUE_600,
            color=ft.Colors.WHITE,
            on_click=self._on_scoring_continue
        )

        self.scoring_adjust_button = ft.TextButton(
            "Adjust Threshold",
            icon=ft.Icons.TUNE,
            visible=False,
            on_click=self._on_scoring_adjust
        )

        content = ft.Column(
            [
                *header_components,
                self.scoring_progress_bar,
                self.scoring_progress_text,
                ft.Container(height=5),
                scoring_results_content,
                ft.Container(height=10),
                ft.Row(
                    [self.scoring_continue_button, self.scoring_adjust_button],
                    spacing=10
                )
            ],
            spacing=10,
            scroll=ft.ScrollMode.AUTO
        )

        self.tab_contents['scoring'] = ft.Container(
            content=content,
            padding=ft.padding.all(15),
            expand=True
        )

        return self.tab_contents['scoring']

    def _on_scoring_continue(self, e):
        """Handle continue to citations button click."""
        if self.tabs_container:
            self.tabs_container.selected_index = 3  # Citations tab
            if self.page:
                self.page.update()

    def _on_scoring_adjust(self, e):
        """Handle adjust threshold button click."""
        # TODO: Show threshold adjustment dialog
        pass
    
    def _create_citations_tab(self) -> ft.Container:
        """Create the citations tab content with progress bar and action buttons."""
        header_components = create_tab_header(
            "Citation Extraction",
            subtitle="Relevant passages extracted from high-scoring documents."
        )

        # Progress spinner (animated ring)
        self.citations_progress_ring = ft.ProgressRing(
            width=20,
            height=20,
            stroke_width=2,
            color=ft.Colors.PURPLE_400,
            visible=False
        )

        # Progress bar for citation extraction
        self.citations_progress_bar = ft.ProgressBar(
            value=0,
            bar_height=6,
            color=ft.Colors.PURPLE_400,
            bgcolor=ft.Colors.PURPLE_50,
            visible=False
        )

        # Detailed progress (tqdm-style) for citation extraction
        self.citations_progress_text = ft.Text(
            "",
            size=12,
            weight=ft.FontWeight.W_500,
            color=ft.Colors.GREY_700,
            visible=False
        )

        # Current document being processed
        self.citations_current_doc = ft.Text(
            "",
            size=11,
            color=ft.Colors.GREY_600,
            italic=True,
            visible=False
        )

        # Estimated time remaining
        self.citations_eta = ft.Text(
            "",
            size=11,
            color=ft.Colors.BLUE_600,
            visible=False
        )

        # Empty state
        empty_state = create_empty_state("No citations extracted yet.")

        # Container for citation list (will be populated dynamically)
        self.citations_list = ft.Column(
            [empty_state],
            spacing=8,
            scroll=ft.ScrollMode.AUTO
        )

        # Action buttons for interactive mode
        self.citations_continue_button = ft.ElevatedButton(
            "Continue to Report",
            icon=ft.Icons.ARROW_FORWARD,
            visible=False,
            bgcolor=ft.Colors.BLUE_600,
            color=ft.Colors.WHITE,
            on_click=self._on_citations_continue
        )

        self.citations_request_more_button = ft.TextButton(
            "Request More Citations",
            icon=ft.Icons.ADD,
            visible=False,
            on_click=self._on_citations_request_more
        )

        # Progress container with spinner and status
        progress_row = ft.Row(
            [
                self.citations_progress_ring,
                ft.Container(width=10),
                ft.Column(
                    [
                        self.citations_progress_text,
                        self.citations_current_doc,
                        self.citations_eta
                    ],
                    spacing=3,
                    expand=True
                )
            ],
            visible=False
        )

        # Store reference for visibility control
        self.citations_progress_container = progress_row

        content = ft.Column(
            [
                *header_components,
                progress_row,
                self.citations_progress_bar,
                ft.Container(height=5),
                self.citations_list,
                ft.Container(height=10),
                ft.Row(
                    [self.citations_continue_button, self.citations_request_more_button],
                    spacing=10
                )
            ],
            spacing=10,
            scroll=ft.ScrollMode.AUTO
        )

        self.tab_contents['citations'] = ft.Container(
            content=content,
            padding=ft.padding.all(15),
            expand=True
        )

        return self.tab_contents['citations']

    def _on_citations_continue(self, e):
        """Handle continue to report button click."""
        if self.tabs_container:
            self.tabs_container.selected_index = 4  # Preliminary report tab
            if self.page:
                self.page.update()

    def _on_citations_request_more(self, e):
        """Handle request more citations button click."""
        # TODO: Implement request more citations functionality
        pass
    
    def _create_preliminary_report_tab(self) -> ft.Container:
        """Create the preliminary report tab content with progress bar and action buttons."""
        header_components = create_tab_header(
            "Preliminary Report",
            subtitle="Initial research report synthesized from citations."
        )

        # Progress bar for report generation
        self.preliminary_progress_bar = ft.ProgressBar(
            value=None,
            bar_height=4,
            color=ft.Colors.TEAL_400,
            bgcolor=ft.Colors.TEAL_50,
            visible=False
        )

        # Empty state
        empty_state = create_empty_state(
            "Preliminary report will appear here after report generation."
        )

        # Container for report content (will be populated dynamically)
        self.preliminary_report_content = ft.Column(
            [empty_state],
            spacing=8,
            scroll=ft.ScrollMode.AUTO
        )

        # Action buttons for interactive mode
        self.preliminary_continue_button = ft.ElevatedButton(
            "Continue to Counterfactual",
            icon=ft.Icons.ARROW_FORWARD,
            visible=False,
            bgcolor=ft.Colors.BLUE_600,
            color=ft.Colors.WHITE,
            on_click=self._on_preliminary_continue
        )

        self.preliminary_skip_button = ft.TextButton(
            "Skip Counterfactual Analysis",
            icon=ft.Icons.SKIP_NEXT,
            visible=False,
            on_click=self._on_preliminary_skip
        )

        content = ft.Column(
            [
                *header_components,
                self.preliminary_progress_bar,
                ft.Container(height=5),
                self.preliminary_report_content,
                ft.Container(height=10),
                ft.Row(
                    [self.preliminary_continue_button, self.preliminary_skip_button],
                    spacing=10
                )
            ],
            spacing=10,
            scroll=ft.ScrollMode.AUTO
        )

        self.tab_contents['preliminary_report'] = ft.Container(
            content=content,
            padding=ft.padding.all(15),
            expand=True
        )

        return self.tab_contents['preliminary_report']

    def _on_preliminary_continue(self, e):
        """Handle continue to counterfactual button click."""
        if self.tabs_container:
            self.tabs_container.selected_index = 5  # Counterfactual tab
            if self.page:
                self.page.update()

    def _on_preliminary_skip(self, e):
        """Handle skip counterfactual button click."""
        if self.tabs_container:
            self.tabs_container.selected_index = 6  # Final report tab
            if self.page:
                self.page.update()
    
    def _create_counterfactual_tab(self) -> ft.Container:
        """Create the counterfactual analysis tab content with progressive audit trail display."""
        header_components = create_tab_header(
            "Counterfactual Analysis",
            subtitle="Progressive workflow showing claims, queries, searches, and contradictory evidence."
        )

        # Progress bar for counterfactual analysis
        self.counterfactual_progress_bar = ft.ProgressBar(
            value=None,
            bar_height=4,
            color=ft.Colors.AMBER_400,
            bgcolor=ft.Colors.AMBER_50,
            visible=False
        )

        # Progress text for detailed status
        self.counterfactual_progress_text = ft.Text(
            "",
            size=11,
            color=ft.Colors.GREY_600,
            visible=False
        )

        # Empty state
        empty_state = create_empty_state(
            "Counterfactual analysis will appear here when enabled and completed."
        )

        # Progressive audit trail sections (initially empty, populated as workflow progresses)
        self.counterfactual_claims_section = ft.Container(visible=False)
        self.counterfactual_questions_section = ft.Container(visible=False)
        self.counterfactual_searches_section = ft.Container(visible=False)
        self.counterfactual_results_section = ft.Container(visible=False)
        self.counterfactual_scoring_section = ft.Container(visible=False)
        self.counterfactual_citations_section = ft.Container(visible=False)
        self.counterfactual_summary_section = ft.Container(visible=False)

        # Container for counterfactual content (will be populated progressively)
        self.counterfactual_content = ft.Column(
            [
                empty_state,
                self.counterfactual_claims_section,
                self.counterfactual_questions_section,
                self.counterfactual_searches_section,
                self.counterfactual_results_section,
                self.counterfactual_scoring_section,
                self.counterfactual_citations_section,
                self.counterfactual_summary_section
            ],
            spacing=12,
            scroll=ft.ScrollMode.AUTO
        )

        # Action buttons for interactive mode
        self.counterfactual_continue_button = ft.ElevatedButton(
            "Continue to Final Report",
            icon=ft.Icons.ARROW_FORWARD,
            visible=False,
            bgcolor=ft.Colors.BLUE_600,
            color=ft.Colors.WHITE,
            on_click=self._on_counterfactual_continue
        )

        content = ft.Column(
            [
                *header_components,
                self.counterfactual_progress_bar,
                self.counterfactual_progress_text,
                ft.Container(height=5),
                self.counterfactual_content,
                ft.Container(height=10),
                ft.Row(
                    [self.counterfactual_continue_button],
                    spacing=10
                )
            ],
            spacing=10,
            scroll=ft.ScrollMode.AUTO
        )

        self.tab_contents['counterfactual'] = ft.Container(
            content=content,
            padding=ft.padding.all(15),
            expand=True
        )

        return self.tab_contents['counterfactual']

    def _on_counterfactual_continue(self, e):
        """Handle continue to final report button click."""
        if self.tabs_container:
            self.tabs_container.selected_index = 6  # Final report tab
            if self.page:
                self.page.update()
    
    def _create_report_tab(self) -> ft.Container:
        """Create the final report tab content with action buttons."""
        header_components = create_tab_header(
            "Final Research Report",
            subtitle="Comprehensive research report with citations and counterfactual analysis."
        )

        # Progress bar for final report compilation
        self.report_progress_bar = ft.ProgressBar(
            value=None,
            bar_height=4,
            color=ft.Colors.GREEN_400,
            bgcolor=ft.Colors.GREEN_50,
            visible=False
        )

        # Empty state
        empty_state = create_empty_state(
            "Final report will appear here once workflow is complete."
        )

        # Container for report content (will be populated dynamically)
        self.report_content = ft.Column(
            [empty_state],
            spacing=8,
            scroll=ft.ScrollMode.AUTO
        )

        # Action buttons
        self.report_save_button = ft.ElevatedButton(
            "Save Report",
            icon=ft.Icons.SAVE,
            visible=False,
            bgcolor=ft.Colors.GREEN_600,
            color=ft.Colors.WHITE,
            on_click=self._on_report_save
        )

        self.report_export_json_button = ft.TextButton(
            "Export as JSON",
            icon=ft.Icons.DATA_OBJECT,
            visible=False,
            on_click=self._on_report_export_json
        )

        content = ft.Column(
            [
                *header_components,
                self.report_progress_bar,
                ft.Container(height=5),
                self.report_content,
                ft.Container(height=10),
                ft.Row(
                    [self.report_save_button, self.report_export_json_button],
                    spacing=10
                )
            ],
            spacing=10,
            scroll=ft.ScrollMode.AUTO
        )

        self.tab_contents['report'] = ft.Container(
            content=content,
            padding=ft.padding.all(15),
            expand=True
        )

        return self.tab_contents['report']

    def wire_event_handlers(self, event_handlers):
        """Wire up event handlers to tab manager buttons.

        Args:
            event_handlers: EventHandlers instance with handler methods
        """
        self.event_handlers = event_handlers

        # Update button click handlers to use the event_handlers
        if hasattr(self, 'report_save_button') and self.report_save_button:
            self.report_save_button.on_click = event_handlers.on_save_report

        if hasattr(self, 'report_export_json_button') and self.report_export_json_button:
            # Note: JSON export is included in save report, so we can reuse the same handler
            self.report_export_json_button.on_click = event_handlers.on_save_report

    def _on_report_save(self, e):
        """Handle save report button click."""
        # Delegate to event handlers if available
        if self.event_handlers and hasattr(self.event_handlers, 'on_save_report'):
            self.event_handlers.on_save_report(e)

    def _on_report_export_json(self, e):
        """Handle export JSON button click."""
        # Delegate to event handlers if available
        if self.event_handlers and hasattr(self.event_handlers, 'on_save_report'):
            # JSON export is included in the save report handler
            self.event_handlers.on_save_report(e)

    def update_search_performance_stats(self, stats: List[Any], score_threshold: float = 3.0):
        """Update the search tab with query performance statistics.

        Args:
            stats: List of QueryPerformanceStats from performance tracker
            score_threshold: Threshold used for high-scoring documents
        """
        if not stats:
            self.search_performance_stats.visible = False
            if self.page:
                self.page.update()
            return

        # Build performance statistics UI
        stats_content = []

        # Header
        stats_content.append(
            ft.Text(
                "📊 Multi-Model Query Performance",
                size=14,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.BLUE_900
            )
        )
        stats_content.append(ft.Divider(height=1, color=ft.Colors.BLUE_200))
        stats_content.append(ft.Container(height=5))

        # Summary metrics at top
        total_docs = sum(s.total_documents for s in stats)
        total_high_scoring = sum(s.high_scoring_documents for s in stats)
        total_unique = sum(s.unique_documents for s in stats)
        total_unique_high = sum(s.unique_high_scoring for s in stats)
        avg_time = sum(s.execution_time for s in stats) / len(stats) if stats else 0

        summary_metrics = ft.Row(
            [
                self._create_metric_card("Queries", str(len(stats)), ft.Colors.BLUE_700),
                self._create_metric_card("Total Docs", str(total_docs), ft.Colors.GREEN_700),
                self._create_metric_card("High-Scoring", str(total_high_scoring), ft.Colors.ORANGE_700),
                self._create_metric_card("Unique", str(total_unique), ft.Colors.PURPLE_700),
                self._create_metric_card("Avg Time", f"{avg_time:.1f}s", ft.Colors.TEAL_700),
            ],
            spacing=10,
            wrap=True
        )
        stats_content.append(summary_metrics)
        stats_content.append(ft.Container(height=10))

        # Per-query details
        stats_content.append(
            ft.Text(
                f"Per-Query Results (threshold ≥{score_threshold}):",
                size=12,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.GREY_800
            )
        )
        stats_content.append(ft.Container(height=5))

        for i, stat in enumerate(stats, 1):
            query_card = self._create_query_performance_card(i, stat, score_threshold)
            stats_content.append(query_card)

        # Set content and make visible
        self.search_performance_stats.content = ft.Column(
            stats_content,
            spacing=8,
            scroll=ft.ScrollMode.AUTO
        )
        self.search_performance_stats.visible = True

        if self.page:
            self.page.update()

    def _create_metric_card(self, label: str, value: str, color) -> ft.Container:
        """Create a small metric card for summary statistics."""
        return ft.Container(
            content=ft.Column(
                [
                    ft.Text(value, size=18, weight=ft.FontWeight.BOLD, color=color),
                    ft.Text(label, size=10, color=ft.Colors.GREY_600),
                ],
                spacing=2,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER
            ),
            padding=8,
            border=ft.border.all(1, ft.Colors.GREY_300),
            border_radius=6,
            bgcolor=ft.Colors.WHITE,
            alignment=ft.alignment.center,
        )

    def _create_query_performance_card(
        self, query_num: int, stat: Any, threshold: float
    ) -> ft.Container:
        """Create a card showing performance for a single query.

        Args:
            query_num: Query number (1-based)
            stat: QueryPerformanceStats object
            threshold: Score threshold used

        Returns:
            Container with formatted query performance info
        """
        # Model and temperature info
        model_short = stat.model.split(':')[0] if ':' in stat.model else stat.model
        if len(model_short) > 30:
            model_short = model_short[:27] + "..."

        header = ft.Row(
            [
                ft.Text(f"Query #{query_num}", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_800),
                ft.Container(expand=True),
                ft.Text(f"{model_short}", size=10, color=ft.Colors.GREY_700, italic=True),
                ft.Text(f"T={stat.temperature:.2f}", size=10, color=ft.Colors.GREY_600),
            ],
            spacing=8
        )

        # Metrics in a grid
        metrics = ft.Row(
            [
                ft.Column(
                    [
                        ft.Text(f"{stat.total_documents}", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_700),
                        ft.Text("Total", size=9, color=ft.Colors.GREY_600),
                    ],
                    spacing=2,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER
                ),
                ft.VerticalDivider(width=1, color=ft.Colors.GREY_300),
                ft.Column(
                    [
                        ft.Text(f"{stat.high_scoring_documents}", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.ORANGE_700),
                        ft.Text(f"≥{threshold}", size=9, color=ft.Colors.GREY_600),
                    ],
                    spacing=2,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER
                ),
                ft.VerticalDivider(width=1, color=ft.Colors.GREY_300),
                ft.Column(
                    [
                        ft.Text(f"{stat.unique_documents}", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.PURPLE_700),
                        ft.Text("Unique", size=9, color=ft.Colors.GREY_600),
                    ],
                    spacing=2,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER
                ),
                ft.VerticalDivider(width=1, color=ft.Colors.GREY_300),
                ft.Column(
                    [
                        ft.Text(f"{stat.unique_high_scoring}", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.PINK_700),
                        ft.Text("Unique High", size=9, color=ft.Colors.GREY_600),
                    ],
                    spacing=2,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER
                ),
                ft.VerticalDivider(width=1, color=ft.Colors.GREY_300),
                ft.Column(
                    [
                        ft.Text(f"{stat.execution_time:.2f}s", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.TEAL_700),
                        ft.Text("Time", size=9, color=ft.Colors.GREY_600),
                    ],
                    spacing=2,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER
                ),
            ],
            spacing=5,
            alignment=ft.MainAxisAlignment.SPACE_EVENLY
        )

        # Query text (truncated)
        query_display = stat.query if len(stat.query) <= 80 else stat.query[:77] + "..."
        query_text = ft.Text(
            f"Query: {query_display}",
            size=10,
            color=ft.Colors.GREY_700,
            italic=True,
            selectable=True
        )

        return ft.Container(
            content=ft.Column(
                [header, ft.Divider(height=1, color=ft.Colors.GREY_300), metrics, query_text],
                spacing=8
            ),
            padding=10,
            border=ft.border.all(1, ft.Colors.GREY_300),
            border_radius=6,
            bgcolor=ft.Colors.WHITE
        )

    def get_tab_content(self, tab_name: str) -> Optional[ft.Container]:
        """Get a specific tab's content container."""
        return self.tab_contents.get(tab_name)
    
    def update_tab_content(self, tab_name: str, new_content: ft.Column):
        """Update a tab's content."""
        if tab_name in self.tab_contents:
            self.tab_contents[tab_name].content = new_content
    
    def create_tab_with_content(self, header_components: List[ft.Control],
                               content_components: List[ft.Control]) -> ft.Container:
        """Create a tab container with header and content components."""
        all_components = [*header_components, *content_components]

        return ft.Container(
            content=ft.Column(
                all_components,
                spacing=10,
                scroll=ft.ScrollMode.AUTO
            ),
            padding=ft.padding.all(15),
            expand=True
        )

    def _create_settings_tab(self) -> ft.Container:
        """Create the settings tab content with nested configuration interface."""
        # Import here to avoid circular import
        from .settings_tab import SettingsTab

        # Get the app instance from page's data if available
        # This is a bit of a workaround since TabManager doesn't have direct access to ResearchGUI
        app = getattr(self.page, '_research_gui_app', None) if self.page else None

        if app:
            settings_tab = SettingsTab(app)
            content = settings_tab.build()
        else:
            # Fallback if app not available
            from .ui_builder import create_empty_state
            empty_state = create_empty_state(
                "Settings not available. Please restart the application."
            )
            content = ft.Container(
                content=ft.Column([empty_state], spacing=10),
                padding=ft.padding.all(15),
                expand=True
            )

        self.tab_contents['settings'] = content
        return content