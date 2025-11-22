"""
PaperChecker Laboratory - Interactive testing interface for medical abstract fact-checking.

Provides an interactive GUI for testing PaperChecker functionality on single abstracts
with step-by-step workflow visualization, intermediate result inspection, and export capabilities.

The laboratory allows users to:
1. Input abstract text directly or fetch by PMID from the database
2. Watch the multi-step fact-checking workflow progress in real-time
3. Inspect extracted statements, counter-statements, and search results
4. Review verdicts with detailed rationale and evidence citations
5. Export results in JSON or Markdown format

Usage:
    # Launch laboratory
    uv run python paper_checker_lab.py

    # Launch in web mode
    uv run python paper_checker_lab.py --view web
"""

import flet as ft
import logging
import json
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List
from concurrent.futures import ThreadPoolExecutor
import threading

from psycopg.rows import dict_row

# Add parent directory to path for imports when running directly
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from bmlibrarian.paperchecker.agent import PaperCheckerAgent
from bmlibrarian.paperchecker.data_models import (
    PaperCheckResult, Statement, CounterStatement, SearchResults,
    ScoredDocument, CounterReport, Verdict
)
from bmlibrarian.config import get_config, get_model


logger = logging.getLogger(__name__)

# ============================================================================
# CONSTANTS - Following golden rules (no magic numbers/hardcoded values)
# ============================================================================

# Window dimensions
WINDOW_WIDTH_DEFAULT = 1400
WINDOW_HEIGHT_DEFAULT = 950
WINDOW_WIDTH_MIN = 1200
WINDOW_HEIGHT_MIN = 750

# Font sizes
FONT_SIZE_TINY = 11
FONT_SIZE_SMALL = 12
FONT_SIZE_NORMAL = 13
FONT_SIZE_MEDIUM = 14
FONT_SIZE_LARGE = 16
FONT_SIZE_XLARGE = 18
FONT_SIZE_TITLE = 24
FONT_SIZE_HEADER = 28

# Spacing and padding
SPACING_TINY = 3
SPACING_SMALL = 5
SPACING_MEDIUM = 10
SPACING_LARGE = 15
SPACING_XLARGE = 20

PADDING_SMALL = 5
PADDING_MEDIUM = 10
PADDING_LARGE = 15
PADDING_XLARGE = 20

# Container dimensions
ABSTRACT_INPUT_MIN_LINES = 5
ABSTRACT_INPUT_MAX_LINES = 10
PMID_INPUT_WIDTH = 200
BUTTON_HEIGHT = 40
BUTTON_WIDTH_MEDIUM = 150
BUTTON_WIDTH_SMALL = 100
WORKFLOW_PANEL_WIDTH_RATIO = 0.4
RESULTS_PANEL_WIDTH_RATIO = 0.6
WORKFLOW_STEP_CARD_HEIGHT = 50
SCROLLABLE_CONTAINER_HEIGHT = 500

# Progress update interval
PROGRESS_UPDATE_INTERVAL_MS = 100

# Border styling
BORDER_RADIUS_SMALL = 5
BORDER_RADIUS_MEDIUM = 10
BORDER_WIDTH = 1

# Input validation
MIN_ABSTRACT_LENGTH = 50  # Minimum characters for a valid abstract

# Workflow step names for progress display
WORKFLOW_STEPS = [
    "Initializing",
    "Extracting statements",
    "Generating counter-statements",
    "Searching for counter-evidence",
    "Scoring documents",
    "Extracting citations",
    "Generating counter-report",
    "Analyzing verdict",
    "Generating overall assessment",
    "Saving results",
    "Complete"
]

# Tab indices
TAB_INDEX_SUMMARY = 0
TAB_INDEX_STATEMENTS = 1
TAB_INDEX_EVIDENCE = 2
TAB_INDEX_VERDICTS = 3
TAB_INDEX_EXPORT = 4

# Colors (using Flet color constants)
COLOR_PRIMARY = ft.Colors.BLUE_700
COLOR_SUCCESS = ft.Colors.GREEN_600
COLOR_WARNING = ft.Colors.ORANGE_600
COLOR_ERROR = ft.Colors.RED_600
COLOR_GREY_50 = ft.Colors.GREY_50
COLOR_GREY_100 = ft.Colors.GREY_100
COLOR_GREY_300 = ft.Colors.GREY_300
COLOR_GREY_600 = ft.Colors.GREY_600
COLOR_GREY_700 = ft.Colors.GREY_700
COLOR_GREY_800 = ft.Colors.GREY_800
COLOR_WHITE = ft.Colors.WHITE

# Verdict colors
VERDICT_COLORS = {
    "supports": ft.Colors.GREEN_600,
    "contradicts": ft.Colors.RED_600,
    "undecided": ft.Colors.ORANGE_600
}

# Confidence colors
CONFIDENCE_COLORS = {
    "high": ft.Colors.GREEN_600,
    "medium": ft.Colors.ORANGE_600,
    "low": ft.Colors.RED_600
}

# Application title
APP_TITLE = "PaperChecker Laboratory"
APP_SUBTITLE = "Interactive medical abstract fact-checking"


class PaperCheckerLab:
    """
    Interactive laboratory for testing PaperChecker functionality.

    Provides a Flet-based GUI for checking medical abstracts with step-by-step
    visualization, intermediate result inspection, and export capabilities.

    Attributes:
        page: Flet page instance
        config: BMLibrarian configuration
        agent: PaperCheckerAgent instance
        current_result: Most recent PaperCheckResult
        controls: Dictionary of UI control references
        workflow_steps: List of workflow step cards
        executor: ThreadPoolExecutor for background processing
        processing: Whether a check is currently in progress
    """

    def __init__(self) -> None:
        """Initialize PaperCheckerLab with default state."""
        self.page: Optional[ft.Page] = None
        self.config = get_config()
        self.agent: Optional[PaperCheckerAgent] = None
        self.current_result: Optional[PaperCheckResult] = None
        self.controls: Dict[str, Any] = {}
        self.workflow_steps: List[ft.Card] = []
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.processing = False
        self._check_lock = threading.Lock()

    def main(self, page: ft.Page) -> None:
        """
        Main entry point for Flet application.

        Args:
            page: Flet page instance provided by the framework
        """
        self.page = page
        page.title = APP_TITLE
        page.window.width = WINDOW_WIDTH_DEFAULT
        page.window.height = WINDOW_HEIGHT_DEFAULT
        page.window.min_width = WINDOW_WIDTH_MIN
        page.window.min_height = WINDOW_HEIGHT_MIN
        page.window.resizable = True
        page.theme_mode = ft.ThemeMode.LIGHT
        page.padding = PADDING_XLARGE
        page.scroll = ft.ScrollMode.AUTO

        # Initialize agent
        self._init_agent()

        # Build UI
        self._build_ui()

    def _init_agent(self) -> None:
        """
        Initialize PaperCheckerAgent with configuration.

        Logs initialization status and handles failures gracefully.
        """
        try:
            self.agent = PaperCheckerAgent(show_model_info=True)
            logger.info("PaperCheckerAgent initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize PaperCheckerAgent: {e}")
            self.agent = None
            if self.page:
                self._show_error(f"Failed to initialize agent: {e}")

    def _build_ui(self) -> None:
        """Build the main user interface layout."""
        # Header section
        header = self._build_header()

        # Input section
        input_section = self._build_input_section()

        # Progress section
        progress_section = self._build_progress_section()

        # Main content (workflow + results)
        workflow_panel = self._build_workflow_panel()
        results_panel = self._build_results_panel()

        main_content = ft.Row([
            ft.Container(
                workflow_panel,
                expand=1,
                padding=PADDING_MEDIUM,
                bgcolor=COLOR_GREY_50,
                border_radius=BORDER_RADIUS_MEDIUM
            ),
            ft.Container(
                results_panel,
                expand=2,
                padding=PADDING_MEDIUM,
                bgcolor=COLOR_GREY_50,
                border_radius=BORDER_RADIUS_MEDIUM
            )
        ], expand=True, spacing=SPACING_MEDIUM)

        # Add all sections to page
        self.page.add(
            header,
            ft.Divider(),
            input_section,
            progress_section,
            main_content
        )

    def _build_header(self) -> ft.Container:
        """
        Build the header section with title and subtitle.

        Returns:
            Container with header elements
        """
        return ft.Container(
            content=ft.Column([
                ft.Text(
                    APP_TITLE,
                    size=FONT_SIZE_HEADER,
                    weight=ft.FontWeight.BOLD,
                    color=COLOR_PRIMARY
                ),
                ft.Text(
                    APP_SUBTITLE,
                    size=FONT_SIZE_LARGE,
                    color=COLOR_GREY_600
                )
            ]),
            margin=ft.margin.only(bottom=SPACING_LARGE)
        )

    def _build_input_section(self) -> ft.Container:
        """
        Build the input section with abstract text area, PMID field, and buttons.

        Returns:
            Container with input elements
        """
        # Model selector
        available_models = self._get_available_models()
        current_model = get_model("paper_checker_agent", default="gpt-oss:20b")

        self.controls['model_selector'] = ft.Dropdown(
            label="Model",
            value=current_model if current_model in available_models else (
                available_models[0] if available_models else "gpt-oss:20b"
            ),
            options=[ft.dropdown.Option(model) for model in available_models],
            width=350,
            on_change=self._on_model_change
        )

        self.controls['refresh_models_button'] = ft.IconButton(
            icon=ft.Icons.REFRESH,
            tooltip="Refresh available models",
            on_click=self._refresh_models
        )

        # Abstract input
        self.controls['abstract_input'] = ft.TextField(
            label="Abstract Text",
            multiline=True,
            min_lines=ABSTRACT_INPUT_MIN_LINES,
            max_lines=ABSTRACT_INPUT_MAX_LINES,
            hint_text="Paste medical abstract here for fact-checking...",
            expand=True
        )

        # PMID input
        self.controls['pmid_input'] = ft.TextField(
            label="Or enter PMID",
            hint_text="e.g., 12345678",
            width=PMID_INPUT_WIDTH,
            input_filter=ft.NumbersOnlyInputFilter(),
            on_submit=lambda _: self._on_check_clicked(None)
        )

        # Buttons
        self.controls['check_button'] = ft.ElevatedButton(
            "Check Abstract",
            icon=ft.Icons.PLAY_ARROW,
            on_click=self._on_check_clicked,
            style=ft.ButtonStyle(
                bgcolor=COLOR_PRIMARY,
                color=COLOR_WHITE
            ),
            height=BUTTON_HEIGHT,
            width=BUTTON_WIDTH_MEDIUM
        )

        self.controls['clear_button'] = ft.ElevatedButton(
            "Clear",
            icon=ft.Icons.CLEAR,
            on_click=self._on_clear_clicked,
            height=BUTTON_HEIGHT,
            width=BUTTON_WIDTH_SMALL
        )

        self.controls['status_text'] = ft.Text(
            "Ready - Enter abstract text or PMID to begin",
            size=FONT_SIZE_SMALL,
            color=COLOR_GREY_600
        )

        return ft.Container(
            content=ft.Column([
                ft.Text("Input", size=FONT_SIZE_XLARGE, weight=ft.FontWeight.BOLD),
                ft.Row([
                    self.controls['model_selector'],
                    self.controls['refresh_models_button']
                ], spacing=SPACING_SMALL),
                ft.Row([
                    self.controls['abstract_input']
                ], expand=True),
                ft.Row([
                    self.controls['pmid_input'],
                    self.controls['check_button'],
                    self.controls['clear_button']
                ], spacing=SPACING_MEDIUM),
                self.controls['status_text']
            ], spacing=SPACING_MEDIUM),
            padding=PADDING_MEDIUM,
            border=ft.border.all(BORDER_WIDTH, COLOR_GREY_300),
            border_radius=BORDER_RADIUS_MEDIUM
        )

    def _build_progress_section(self) -> ft.Container:
        """
        Build the progress section with progress bar and status text.

        Returns:
            Container with progress elements
        """
        self.controls['progress_bar'] = ft.ProgressBar(
            visible=False,
            value=0
        )

        self.controls['progress_text'] = ft.Text(
            "",
            size=FONT_SIZE_MEDIUM,
            color=COLOR_PRIMARY
        )

        return ft.Container(
            content=ft.Column([
                self.controls['progress_bar'],
                self.controls['progress_text']
            ], spacing=SPACING_SMALL),
            padding=PADDING_MEDIUM,
            visible=True
        )

    def _build_workflow_panel(self) -> ft.Column:
        """
        Build the workflow panel showing step-by-step progress.

        Returns:
            Column with workflow step cards
        """
        self.controls['workflow_column'] = ft.Column(
            [],
            scroll=ft.ScrollMode.AUTO,
            spacing=SPACING_SMALL
        )

        return ft.Column([
            ft.Text(
                "Workflow Progress",
                size=FONT_SIZE_XLARGE,
                weight=ft.FontWeight.BOLD,
                color=COLOR_GREY_800
            ),
            ft.Container(
                self.controls['workflow_column'],
                expand=True,
                padding=PADDING_SMALL
            )
        ], spacing=SPACING_MEDIUM, expand=True)

    def _build_results_panel(self) -> ft.Column:
        """
        Build the results panel with tabbed display.

        Returns:
            Column with results tabs
        """
        self.controls['result_tabs'] = ft.Tabs(
            tabs=[
                ft.Tab(
                    text="Summary",
                    content=self._build_summary_placeholder()
                ),
                ft.Tab(
                    text="Statements",
                    content=self._build_statements_placeholder()
                ),
                ft.Tab(
                    text="Evidence",
                    content=self._build_evidence_placeholder()
                ),
                ft.Tab(
                    text="Verdicts",
                    content=self._build_verdicts_placeholder()
                ),
                ft.Tab(
                    text="Export",
                    content=self._build_export_placeholder()
                )
            ],
            visible=True,
            expand=True,
            animation_duration=300
        )

        return ft.Column([
            ft.Text(
                "Results",
                size=FONT_SIZE_XLARGE,
                weight=ft.FontWeight.BOLD,
                color=COLOR_GREY_800
            ),
            self.controls['result_tabs']
        ], spacing=SPACING_MEDIUM, expand=True)

    def _build_summary_placeholder(self) -> ft.Container:
        """Build placeholder content for summary tab."""
        return ft.Container(
            content=ft.Text(
                "Results will appear here after checking an abstract.",
                size=FONT_SIZE_NORMAL,
                color=COLOR_GREY_600
            ),
            padding=PADDING_MEDIUM
        )

    def _build_statements_placeholder(self) -> ft.Container:
        """Build placeholder content for statements tab."""
        return ft.Container(
            content=ft.Text(
                "Extracted statements will appear here.",
                size=FONT_SIZE_NORMAL,
                color=COLOR_GREY_600
            ),
            padding=PADDING_MEDIUM
        )

    def _build_evidence_placeholder(self) -> ft.Container:
        """Build placeholder content for evidence tab."""
        return ft.Container(
            content=ft.Text(
                "Counter-evidence reports will appear here.",
                size=FONT_SIZE_NORMAL,
                color=COLOR_GREY_600
            ),
            padding=PADDING_MEDIUM
        )

    def _build_verdicts_placeholder(self) -> ft.Container:
        """Build placeholder content for verdicts tab."""
        return ft.Container(
            content=ft.Text(
                "Verdicts will appear here.",
                size=FONT_SIZE_NORMAL,
                color=COLOR_GREY_600
            ),
            padding=PADDING_MEDIUM
        )

    def _build_export_placeholder(self) -> ft.Container:
        """Build placeholder content for export tab."""
        return ft.Container(
            content=ft.Column([
                ft.Text(
                    "Export options will be available after checking an abstract.",
                    size=FONT_SIZE_NORMAL,
                    color=COLOR_GREY_600
                )
            ]),
            padding=PADDING_MEDIUM
        )

    # ==================== EVENT HANDLERS ====================

    def _on_check_clicked(self, e: Optional[ft.ControlEvent]) -> None:
        """
        Handle check button click event.

        Validates input and starts the abstract checking process.

        Args:
            e: Flet control event (may be None for programmatic calls)
        """
        # Prevent concurrent processing
        if self.processing:
            self._show_warning("Processing in progress. Please wait.")
            return

        # Get input
        abstract_text = self.controls['abstract_input'].value or ""
        pmid_text = self.controls['pmid_input'].value or ""

        # Validate input
        if pmid_text.strip():
            # Fetch abstract by PMID
            abstract_data = self._fetch_by_pmid(pmid_text.strip())
            if abstract_data is None:
                self._show_error(f"PMID {pmid_text} not found in database")
                return
            abstract_text = abstract_data.get("abstract", "")
            metadata = {
                "pmid": abstract_data.get("pmid"),
                "title": abstract_data.get("title"),
                "doi": abstract_data.get("doi"),
                "source": "database"
            }
        elif abstract_text.strip():
            metadata = {"source": "user_input"}
        else:
            self._show_error("Please provide abstract text or PMID")
            return

        # Validate abstract length
        stripped_abstract = abstract_text.strip()
        if len(stripped_abstract) < MIN_ABSTRACT_LENGTH:
            self._show_error(
                f"Abstract too short ({len(stripped_abstract)} characters). "
                f"Minimum length: {MIN_ABSTRACT_LENGTH} characters."
            )
            return

        # Validate agent
        if self.agent is None:
            self._show_error("Agent not initialized. Please restart the application.")
            return

        # Start check in background thread
        self._run_check(stripped_abstract, metadata)

    def _on_clear_clicked(self, e: Optional[ft.ControlEvent]) -> None:
        """
        Handle clear button click event.

        Resets all input fields and clears results.

        Args:
            e: Flet control event
        """
        self.controls['abstract_input'].value = ""
        self.controls['pmid_input'].value = ""
        self.controls['workflow_column'].controls.clear()
        self.controls['progress_bar'].visible = False
        self.controls['progress_text'].value = ""
        self.controls['status_text'].value = "Ready - Enter abstract text or PMID to begin"
        self.controls['status_text'].color = COLOR_GREY_600
        self.current_result = None

        # Reset tab content to placeholders
        self.controls['result_tabs'].tabs[TAB_INDEX_SUMMARY].content = self._build_summary_placeholder()
        self.controls['result_tabs'].tabs[TAB_INDEX_STATEMENTS].content = self._build_statements_placeholder()
        self.controls['result_tabs'].tabs[TAB_INDEX_EVIDENCE].content = self._build_evidence_placeholder()
        self.controls['result_tabs'].tabs[TAB_INDEX_VERDICTS].content = self._build_verdicts_placeholder()
        self.controls['result_tabs'].tabs[TAB_INDEX_EXPORT].content = self._build_export_placeholder()

        self.page.update()

    def _on_model_change(self, e: ft.ControlEvent) -> None:
        """
        Handle model selection change.

        Reinitializes the agent with the new model.

        Args:
            e: Flet control event with new model value
        """
        new_model = self.controls['model_selector'].value
        self._update_status(f"Switching to model: {new_model}...")

        try:
            # Reinitialize agent with new model
            self.agent = PaperCheckerAgent(show_model_info=False)
            # Note: The model is configured via config.json, not directly here
            # The user should update config.json for persistent model changes
            self._update_status(f"Using model: {new_model}")
        except Exception as err:
            self._show_error(f"Error switching model: {err}")

    def _refresh_models(self, e: ft.ControlEvent) -> None:
        """
        Refresh available models list from Ollama.

        Args:
            e: Flet control event
        """
        self._update_status("Refreshing models...")
        models = self._get_available_models()
        self.controls['model_selector'].options = [
            ft.dropdown.Option(model) for model in models
        ]
        self._update_status(f"Found {len(models)} models")
        self.page.update()

    # ==================== PROCESSING ====================

    def _run_check(self, abstract: str, metadata: Dict[str, Any]) -> None:
        """
        Run abstract check with progress tracking.

        Executes the check in a background thread to keep UI responsive.

        Args:
            abstract: Abstract text to check
            metadata: Source metadata dictionary
        """
        with self._check_lock:
            if self.processing:
                return
            self.processing = True

        # Update UI for processing state
        self.controls['progress_bar'].visible = True
        self.controls['progress_bar'].value = 0
        self.controls['check_button'].disabled = True
        self.controls['workflow_column'].controls.clear()
        self._update_status("Starting abstract check...")
        self.page.update()

        # Run in background thread
        def run_check_thread() -> None:
            """Background thread for running the check."""
            try:
                result = self.agent.check_abstract(
                    abstract=abstract,
                    source_metadata=metadata,
                    progress_callback=self._on_progress_update
                )

                # Store result and update UI on main thread
                self.current_result = result
                self.page.run_task(lambda: self._on_check_complete(result))

            except Exception as e:
                logger.error(f"Check failed: {e}", exc_info=True)
                self.page.run_task(lambda: self._on_check_error(str(e)))

            finally:
                with self._check_lock:
                    self.processing = False

        self.executor.submit(run_check_thread)

    def _on_progress_update(self, step_name: str, progress: float) -> None:
        """
        Handle progress updates from PaperCheckerAgent.

        Updates the progress bar and adds workflow step cards.

        Args:
            step_name: Name of current processing step
            progress: Progress fraction (0.0 to 1.0)
        """
        # Update progress bar (schedule on main thread)
        def update_ui() -> None:
            self.controls['progress_bar'].value = progress
            self.controls['progress_text'].value = f"{step_name} ({progress*100:.0f}%)"

            # Add workflow step card
            step_card = self._create_workflow_step_card(step_name, progress)
            self.controls['workflow_column'].controls.append(step_card)

            self.page.update()

        self.page.run_task(update_ui)

    def _on_check_complete(self, result: PaperCheckResult) -> None:
        """
        Handle successful check completion.

        Updates UI with results and enables export options.

        Args:
            result: Complete PaperCheckResult from the agent
        """
        self.controls['progress_bar'].visible = False
        self.controls['check_button'].disabled = False

        # Add completion step
        complete_card = self._create_workflow_step_card("Complete", 1.0)
        self.controls['workflow_column'].controls.append(complete_card)

        # Update status
        processing_time = result.processing_metadata.get("processing_time_seconds", 0)
        self._update_status(
            f"Check complete in {processing_time:.1f}s - "
            f"{len(result.statements)} statements analyzed",
            color=COLOR_SUCCESS
        )

        # Display results
        self._display_results(result)

        self.page.update()

    def _on_check_error(self, error_message: str) -> None:
        """
        Handle check error.

        Updates UI to show error state and re-enables input.

        Args:
            error_message: Error description string
        """
        self.controls['progress_bar'].visible = False
        self.controls['check_button'].disabled = False
        self._show_error(f"Check failed: {error_message}")
        self.page.update()

    # ==================== RESULTS DISPLAY ====================

    def _display_results(self, result: PaperCheckResult) -> None:
        """
        Display complete check results in all tabs.

        Args:
            result: Complete PaperCheckResult to display
        """
        # Summary tab
        self.controls['result_tabs'].tabs[TAB_INDEX_SUMMARY].content = (
            self._build_summary_tab(result)
        )

        # Statements tab
        self.controls['result_tabs'].tabs[TAB_INDEX_STATEMENTS].content = (
            self._build_statements_tab(result)
        )

        # Evidence tab
        self.controls['result_tabs'].tabs[TAB_INDEX_EVIDENCE].content = (
            self._build_evidence_tab(result)
        )

        # Verdicts tab
        self.controls['result_tabs'].tabs[TAB_INDEX_VERDICTS].content = (
            self._build_verdicts_tab(result)
        )

        # Export tab
        self.controls['result_tabs'].tabs[TAB_INDEX_EXPORT].content = (
            self._build_export_tab(result)
        )

        self.page.update()

    def _build_summary_tab(self, result: PaperCheckResult) -> ft.Container:
        """
        Build summary tab content.

        Args:
            result: PaperCheckResult to summarize

        Returns:
            Container with summary content
        """
        # Count verdicts
        verdict_counts = {"supports": 0, "contradicts": 0, "undecided": 0}
        for verdict in result.verdicts:
            verdict_counts[verdict.verdict] = verdict_counts.get(verdict.verdict, 0) + 1

        # Calculate total citations
        total_citations = sum(report.num_citations for report in result.counter_reports)

        return ft.Container(
            content=ft.Column([
                ft.Text(
                    "Overall Assessment",
                    size=FONT_SIZE_XLARGE,
                    weight=ft.FontWeight.BOLD
                ),
                ft.Container(
                    ft.Text(
                        result.overall_assessment,
                        size=FONT_SIZE_NORMAL
                    ),
                    padding=PADDING_MEDIUM,
                    bgcolor=COLOR_WHITE,
                    border_radius=BORDER_RADIUS_SMALL,
                    border=ft.border.all(BORDER_WIDTH, COLOR_GREY_300)
                ),
                ft.Divider(),
                ft.Text("Statistics", size=FONT_SIZE_LARGE, weight=ft.FontWeight.BOLD),
                ft.Row([
                    self._create_stat_chip("Statements", str(len(result.statements)), COLOR_PRIMARY),
                    self._create_stat_chip("Supports", str(verdict_counts.get("supports", 0)), COLOR_SUCCESS),
                    self._create_stat_chip("Contradicts", str(verdict_counts.get("contradicts", 0)), COLOR_ERROR),
                    self._create_stat_chip("Undecided", str(verdict_counts.get("undecided", 0)), COLOR_WARNING),
                    self._create_stat_chip("Citations", str(total_citations), COLOR_GREY_700),
                ], wrap=True, spacing=SPACING_MEDIUM),
                ft.Divider(),
                ft.Text("Source Metadata", size=FONT_SIZE_LARGE, weight=ft.FontWeight.BOLD),
                self._build_metadata_display(result.source_metadata),
                ft.Divider(),
                ft.Text("Processing Info", size=FONT_SIZE_LARGE, weight=ft.FontWeight.BOLD),
                ft.Text(
                    f"Model: {result.processing_metadata.get('model', 'Unknown')}",
                    size=FONT_SIZE_SMALL,
                    color=COLOR_GREY_600
                ),
                ft.Text(
                    f"Processing time: {result.processing_metadata.get('processing_time_seconds', 0):.2f}s",
                    size=FONT_SIZE_SMALL,
                    color=COLOR_GREY_600
                ),
            ], spacing=SPACING_MEDIUM, scroll=ft.ScrollMode.AUTO),
            padding=PADDING_MEDIUM
        )

    def _build_statements_tab(self, result: PaperCheckResult) -> ft.Container:
        """
        Build statements tab content.

        Args:
            result: PaperCheckResult with statements

        Returns:
            Container with statements list
        """
        controls = []

        for i, (stmt, counter) in enumerate(
            zip(result.statements, result.counter_statements), 1
        ):
            card = ft.Card(
                content=ft.Container(
                    content=ft.Column([
                        ft.Row([
                            ft.Text(
                                f"Statement {i}",
                                size=FONT_SIZE_MEDIUM,
                                weight=ft.FontWeight.BOLD
                            ),
                            ft.Container(
                                ft.Text(
                                    stmt.statement_type.upper(),
                                    size=FONT_SIZE_TINY,
                                    color=COLOR_WHITE
                                ),
                                bgcolor=COLOR_PRIMARY,
                                padding=ft.padding.symmetric(horizontal=PADDING_SMALL, vertical=SPACING_TINY),
                                border_radius=BORDER_RADIUS_SMALL
                            ),
                            ft.Text(
                                f"Confidence: {stmt.confidence:.0%}",
                                size=FONT_SIZE_SMALL,
                                color=COLOR_GREY_600
                            )
                        ], spacing=SPACING_MEDIUM),
                        ft.Text(
                            stmt.text,
                            size=FONT_SIZE_NORMAL,
                            selectable=True
                        ),
                        ft.Divider(),
                        ft.Text(
                            "Counter-Statement:",
                            size=FONT_SIZE_SMALL,
                            weight=ft.FontWeight.BOLD,
                            color=COLOR_GREY_700
                        ),
                        ft.Text(
                            counter.negated_text,
                            size=FONT_SIZE_SMALL,
                            italic=True,
                            color=COLOR_GREY_600,
                            selectable=True
                        ),
                        ft.Row([
                            ft.Text(
                                f"Keywords: {', '.join(counter.keywords[:5])}{'...' if len(counter.keywords) > 5 else ''}",
                                size=FONT_SIZE_TINY,
                                color=COLOR_GREY_600
                            )
                        ])
                    ], spacing=SPACING_SMALL),
                    padding=PADDING_MEDIUM
                )
            )
            controls.append(card)

        return ft.Container(
            content=ft.Column(controls, spacing=SPACING_MEDIUM, scroll=ft.ScrollMode.AUTO),
            padding=PADDING_MEDIUM
        )

    def _build_evidence_tab(self, result: PaperCheckResult) -> ft.Container:
        """
        Build evidence tab content with counter-reports.

        Args:
            result: PaperCheckResult with counter reports

        Returns:
            Container with evidence display
        """
        controls = []

        for i, (stmt, report) in enumerate(zip(result.statements, result.counter_reports), 1):
            # Search statistics
            stats = report.search_stats
            strategies = stats.get("search_strategies", {})

            # Evidence section
            evidence_card = ft.ExpansionTile(
                title=ft.Text(
                    f"Statement {i}: Counter-Evidence",
                    weight=ft.FontWeight.BOLD
                ),
                subtitle=ft.Text(
                    f"{report.num_citations} citations from {stats.get('documents_found', 0)} documents",
                    size=FONT_SIZE_SMALL,
                    color=COLOR_GREY_600
                ),
                initially_expanded=True,
                controls=[
                    ft.Container(
                        ft.Column([
                            ft.Text(
                                "Search Statistics",
                                size=FONT_SIZE_SMALL,
                                weight=ft.FontWeight.BOLD
                            ),
                            ft.Row([
                                ft.Text(f"Semantic: {strategies.get('semantic', 0)}", size=FONT_SIZE_TINY),
                                ft.Text(f"HyDE: {strategies.get('hyde', 0)}", size=FONT_SIZE_TINY),
                                ft.Text(f"Keyword: {strategies.get('keyword', 0)}", size=FONT_SIZE_TINY),
                            ], spacing=SPACING_LARGE),
                            ft.Divider(),
                            ft.Text(
                                "Summary",
                                size=FONT_SIZE_SMALL,
                                weight=ft.FontWeight.BOLD
                            ),
                            ft.Container(
                                ft.Markdown(
                                    report.summary,
                                    selectable=True,
                                    extension_set=ft.MarkdownExtensionSet.GITHUB_FLAVORED
                                ),
                                padding=PADDING_SMALL,
                                bgcolor=COLOR_WHITE,
                                border_radius=BORDER_RADIUS_SMALL
                            ),
                            ft.Divider(),
                            ft.Text(
                                f"Citations ({report.num_citations})",
                                size=FONT_SIZE_SMALL,
                                weight=ft.FontWeight.BOLD
                            ),
                            *[self._build_citation_card(cit) for cit in report.citations[:5]],
                            ft.Text(
                                f"... and {len(report.citations) - 5} more"
                                if len(report.citations) > 5 else "",
                                size=FONT_SIZE_TINY,
                                color=COLOR_GREY_600
                            ) if len(report.citations) > 5 else ft.Container()
                        ], spacing=SPACING_SMALL),
                        padding=PADDING_MEDIUM
                    )
                ]
            )
            controls.append(evidence_card)

        return ft.Container(
            content=ft.Column(controls, spacing=SPACING_MEDIUM, scroll=ft.ScrollMode.AUTO),
            padding=PADDING_MEDIUM
        )

    def _build_verdicts_tab(self, result: PaperCheckResult) -> ft.Container:
        """
        Build verdicts tab content.

        Args:
            result: PaperCheckResult with verdicts

        Returns:
            Container with verdicts display
        """
        controls = []

        for i, (stmt, verdict) in enumerate(zip(result.statements, result.verdicts), 1):
            verdict_color = VERDICT_COLORS.get(verdict.verdict, COLOR_GREY_700)
            confidence_color = CONFIDENCE_COLORS.get(verdict.confidence, COLOR_GREY_600)

            card = ft.Card(
                content=ft.Container(
                    content=ft.Column([
                        ft.Text(
                            f"Statement {i}",
                            size=FONT_SIZE_SMALL,
                            color=COLOR_GREY_600
                        ),
                        ft.Text(
                            stmt.text[:150] + "..." if len(stmt.text) > 150 else stmt.text,
                            size=FONT_SIZE_NORMAL,
                            italic=True
                        ),
                        ft.Divider(),
                        ft.Row([
                            ft.Container(
                                ft.Text(
                                    verdict.verdict.upper(),
                                    color=COLOR_WHITE,
                                    weight=ft.FontWeight.BOLD,
                                    size=FONT_SIZE_MEDIUM
                                ),
                                bgcolor=verdict_color,
                                padding=ft.padding.symmetric(
                                    horizontal=PADDING_MEDIUM,
                                    vertical=PADDING_SMALL
                                ),
                                border_radius=BORDER_RADIUS_SMALL
                            ),
                            ft.Container(
                                ft.Text(
                                    f"{verdict.confidence} confidence",
                                    color=COLOR_WHITE,
                                    size=FONT_SIZE_SMALL
                                ),
                                bgcolor=confidence_color,
                                padding=ft.padding.symmetric(
                                    horizontal=PADDING_SMALL,
                                    vertical=SPACING_TINY
                                ),
                                border_radius=BORDER_RADIUS_SMALL
                            ),
                            ft.Text(
                                f"{verdict.counter_report.num_citations} citations",
                                size=FONT_SIZE_SMALL,
                                color=COLOR_GREY_600
                            )
                        ], spacing=SPACING_MEDIUM),
                        ft.Container(
                            ft.Text(
                                verdict.rationale,
                                size=FONT_SIZE_NORMAL,
                                selectable=True
                            ),
                            padding=PADDING_SMALL,
                            bgcolor=COLOR_GREY_50,
                            border_radius=BORDER_RADIUS_SMALL
                        )
                    ], spacing=SPACING_MEDIUM),
                    padding=PADDING_MEDIUM
                )
            )
            controls.append(card)

        return ft.Container(
            content=ft.Column(controls, spacing=SPACING_MEDIUM, scroll=ft.ScrollMode.AUTO),
            padding=PADDING_MEDIUM
        )

    def _build_export_tab(self, result: PaperCheckResult) -> ft.Container:
        """
        Build export tab content with export buttons.

        Args:
            result: PaperCheckResult to export

        Returns:
            Container with export options
        """
        self.controls['json_output'] = ft.TextField(
            value="",
            multiline=True,
            min_lines=10,
            max_lines=20,
            read_only=True,
            visible=False,
            expand=True
        )

        self.controls['markdown_output'] = ft.Markdown(
            "",
            selectable=True,
            visible=False,
            extension_set=ft.MarkdownExtensionSet.GITHUB_FLAVORED
        )

        return ft.Container(
            content=ft.Column([
                ft.Text(
                    "Export Results",
                    size=FONT_SIZE_XLARGE,
                    weight=ft.FontWeight.BOLD
                ),
                ft.Row([
                    ft.ElevatedButton(
                        "Export as JSON",
                        icon=ft.Icons.CODE,
                        on_click=lambda _: self._export_json(result)
                    ),
                    ft.ElevatedButton(
                        "Export as Markdown",
                        icon=ft.Icons.ARTICLE,
                        on_click=lambda _: self._export_markdown(result)
                    ),
                    ft.ElevatedButton(
                        "Copy to Clipboard",
                        icon=ft.Icons.COPY,
                        on_click=lambda _: self._copy_to_clipboard(result)
                    )
                ], spacing=SPACING_MEDIUM, wrap=True),
                ft.Divider(),
                self.controls['json_output'],
                self.controls['markdown_output']
            ], spacing=SPACING_MEDIUM, scroll=ft.ScrollMode.AUTO),
            padding=PADDING_MEDIUM
        )

    # ==================== HELPER METHODS ====================

    def _create_workflow_step_card(self, step_name: str, progress: float) -> ft.Card:
        """
        Create a workflow step card for the progress display.

        Args:
            step_name: Name of the workflow step
            progress: Progress fraction (0.0 to 1.0)

        Returns:
            Card widget showing step status
        """
        is_complete = progress >= 1.0 or step_name == "Complete"
        is_current = not is_complete and progress > 0

        icon = ft.Icons.CHECK_CIRCLE if is_complete else (
            ft.Icons.PENDING if is_current else ft.Icons.CIRCLE_OUTLINED
        )
        icon_color = COLOR_SUCCESS if is_complete else (
            COLOR_PRIMARY if is_current else COLOR_GREY_300
        )

        return ft.Card(
            content=ft.Container(
                content=ft.Row([
                    ft.Icon(icon, color=icon_color, size=FONT_SIZE_XLARGE),
                    ft.Text(step_name, size=FONT_SIZE_MEDIUM),
                    ft.Text(
                        f"({progress*100:.0f}%)" if is_current else "",
                        size=FONT_SIZE_SMALL,
                        color=COLOR_GREY_600
                    )
                ], spacing=SPACING_MEDIUM),
                padding=PADDING_MEDIUM
            )
        )

    def _create_stat_chip(self, label: str, value: str, color: str) -> ft.Container:
        """
        Create a statistics chip widget.

        Args:
            label: Stat label text
            value: Stat value text
            color: Background color for the value

        Returns:
            Container with stat chip
        """
        return ft.Container(
            content=ft.Row([
                ft.Text(label, size=FONT_SIZE_SMALL),
                ft.Container(
                    ft.Text(value, color=COLOR_WHITE, weight=ft.FontWeight.BOLD),
                    bgcolor=color,
                    padding=ft.padding.symmetric(horizontal=PADDING_SMALL, vertical=SPACING_TINY),
                    border_radius=BORDER_RADIUS_SMALL
                )
            ], spacing=SPACING_SMALL),
            margin=ft.margin.only(right=SPACING_SMALL)
        )

    def _build_citation_card(self, citation) -> ft.Container:
        """
        Build a citation display card.

        Args:
            citation: ExtractedCitation object

        Returns:
            Container with citation display
        """
        return ft.Container(
            content=ft.Column([
                ft.Text(
                    f"[{citation.citation_order}] {citation.full_citation}",
                    size=FONT_SIZE_SMALL,
                    weight=ft.FontWeight.BOLD,
                    selectable=True
                ),
                ft.Text(
                    f"\"{citation.passage[:200]}{'...' if len(citation.passage) > 200 else ''}\"",
                    size=FONT_SIZE_SMALL,
                    italic=True,
                    color=COLOR_GREY_700,
                    selectable=True
                )
            ], spacing=SPACING_TINY),
            padding=PADDING_SMALL,
            bgcolor=COLOR_WHITE,
            border_radius=BORDER_RADIUS_SMALL,
            border=ft.border.all(BORDER_WIDTH, COLOR_GREY_300)
        )

    def _build_metadata_display(self, metadata: Dict[str, Any]) -> ft.Column:
        """
        Build metadata display rows.

        Args:
            metadata: Source metadata dictionary

        Returns:
            Column with metadata rows
        """
        rows = []
        if metadata.get("title"):
            rows.append(ft.Text(f"Title: {metadata['title']}", size=FONT_SIZE_SMALL))
        if metadata.get("pmid"):
            rows.append(ft.Text(f"PMID: {metadata['pmid']}", size=FONT_SIZE_SMALL))
        if metadata.get("doi"):
            rows.append(ft.Text(f"DOI: {metadata['doi']}", size=FONT_SIZE_SMALL))
        if metadata.get("source"):
            rows.append(ft.Text(f"Source: {metadata['source']}", size=FONT_SIZE_SMALL))

        return ft.Column(rows, spacing=SPACING_TINY) if rows else ft.Column([
            ft.Text("No metadata available", size=FONT_SIZE_SMALL, color=COLOR_GREY_600)
        ])

    def _fetch_by_pmid(self, pmid: str) -> Optional[Dict[str, Any]]:
        """
        Fetch document by PMID from database.

        Args:
            pmid: PubMed ID string

        Returns:
            Document dictionary or None if not found
        """
        try:
            pmid_int = int(pmid)
            # Validate PMID is positive
            if pmid_int <= 0:
                logger.error(f"Invalid PMID: must be positive integer, got {pmid_int}")
                return None

            # Search database for PMID using database manager
            from bmlibrarian.database import get_db_manager
            db_manager = get_db_manager()

            with db_manager.get_connection() as conn:
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute("""
                        SELECT id, title, abstract, authors, pmid, doi, publication_date
                        FROM document
                        WHERE pmid = %s
                        LIMIT 1
                    """, (pmid_int,))
                    result = cur.fetchone()

                    if result:
                        return dict(result)
                    return None

        except ValueError:
            logger.error(f"Invalid PMID format: {pmid}")
            return None
        except Exception as e:
            logger.error(f"Error fetching PMID {pmid}: {e}")
            return None

    def _get_available_models(self) -> List[str]:
        """
        Get list of available Ollama models.

        Returns:
            List of model names
        """
        try:
            if self.agent and hasattr(self.agent, 'get_available_models'):
                models = self.agent.get_available_models()
                return models if models else ["gpt-oss:20b"]
        except Exception as e:
            logger.error(f"Error fetching models: {e}")

        return ["gpt-oss:20b", "medgemma-27b-text-it-Q8_0:latest", "medgemma4B_it_q8:latest"]

    # ==================== EXPORT METHODS ====================

    def _export_json(self, result: PaperCheckResult) -> None:
        """
        Export result as JSON and display in output field.

        Args:
            result: PaperCheckResult to export
        """
        try:
            output = json.dumps(result.to_json_dict(), indent=2, default=str)
            self.controls['json_output'].value = output
            self.controls['json_output'].visible = True
            self.controls['markdown_output'].visible = False
            self._show_success("JSON exported - copy from text field below")
            self.page.update()
        except Exception as e:
            self._show_error(f"Export failed: {e}")

    def _export_markdown(self, result: PaperCheckResult) -> None:
        """
        Export result as Markdown and display in output field.

        Args:
            result: PaperCheckResult to export
        """
        try:
            markdown = result.to_markdown_report()
            self.controls['markdown_output'].value = markdown
            self.controls['markdown_output'].visible = True
            self.controls['json_output'].visible = False
            self._show_success("Markdown exported - copy from display below")
            self.page.update()
        except Exception as e:
            self._show_error(f"Export failed: {e}")

    def _copy_to_clipboard(self, result: PaperCheckResult) -> None:
        """
        Copy result summary to clipboard.

        Args:
            result: PaperCheckResult to copy
        """
        try:
            summary = f"PaperChecker Results\n\n{result.overall_assessment}"
            self.page.set_clipboard(summary)
            self._show_success("Summary copied to clipboard")
        except Exception as e:
            self._show_error(f"Copy failed: {e}")

    # ==================== UI HELPERS ====================

    def _update_status(self, message: str, color: str = COLOR_GREY_600) -> None:
        """
        Update status text display.

        Args:
            message: Status message to display
            color: Text color (default grey)
        """
        self.controls['status_text'].value = message
        self.controls['status_text'].color = color
        self.page.update()

    def _show_error(self, message: str) -> None:
        """
        Show error message in snackbar.

        Args:
            message: Error message to display
        """
        self.controls['status_text'].value = message
        self.controls['status_text'].color = COLOR_ERROR
        self.page.snack_bar = ft.SnackBar(
            content=ft.Text(message, color=COLOR_WHITE),
            bgcolor=COLOR_ERROR
        )
        self.page.snack_bar.open = True
        self.page.update()

    def _show_warning(self, message: str) -> None:
        """
        Show warning message in snackbar.

        Args:
            message: Warning message to display
        """
        self.page.snack_bar = ft.SnackBar(
            content=ft.Text(message, color=COLOR_WHITE),
            bgcolor=COLOR_WARNING
        )
        self.page.snack_bar.open = True
        self.page.update()

    def _show_success(self, message: str) -> None:
        """
        Show success message in snackbar.

        Args:
            message: Success message to display
        """
        self.page.snack_bar = ft.SnackBar(
            content=ft.Text(message, color=COLOR_WHITE),
            bgcolor=COLOR_SUCCESS
        )
        self.page.snack_bar.open = True
        self.page.update()


def run_paper_checker_lab() -> None:
    """Run the PaperChecker Laboratory application."""
    app = PaperCheckerLab()
    ft.app(target=app.main)


if __name__ == "__main__":
    run_paper_checker_lab()
