"""
Refactored Research GUI Application for BMLibrarian

This is a much smaller, focused version of the main ResearchGUI class that delegates
responsibilities to specialized modules, emphasizing short reusable functions.
"""

import flet as ft
from typing import Dict, Optional, List, Any
from datetime import datetime

from .components import StepCard
from .dialogs import DialogManager
from .workflow import WorkflowExecutor
from .tab_manager import TabManager
from .event_handlers import EventHandlers
from .data_updaters import DataUpdaters
from .ui_builder import (
    create_header, create_question_field, create_toggle_switch,
    create_start_button, create_max_results_field, create_min_relevant_field,
    create_controls_section, create_search_strategy_checkboxes
)
from ...cli.workflow_steps import WorkflowStep
from ...cli import CLIConfig, UserInterface, QueryProcessor, ReportFormatter, WorkflowOrchestrator


class ResearchGUI:
    """Refactored research GUI application with modular architecture."""
    
    def __init__(self, agents=None):
        self.page: Optional[ft.Page] = None
        self.research_question = ""
        self.human_in_loop = False  # Changed default to OFF
        self.comprehensive_counterfactual = True  # Changed default to ON
        self.workflow_running = False
        self.workflow_continuing = False  # Prevents concurrent workflow continuations
        
        # Command-line configuration
        self.config_overrides = {}
        self.auto_question = None
        
        # GUI components (will be initialized in _build_ui)
        self.question_field = None
        self.max_results_field = None
        self.min_relevant_field = None
        self.human_loop_toggle = None
        self.counterfactual_toggle = None
        self.start_button = None
        self.step_cards: Dict[WorkflowStep, StepCard] = {}
        self.status_text = None

        # Default max results and min relevant values
        self.max_results = 100
        self.min_relevant = 10

        # Search strategy settings (will be loaded from config)
        self.search_strategy_keyword = True  # Default enabled
        self.search_strategy_bm25 = False
        self.search_strategy_semantic = False
        self.search_strategy_hyde = False
        self.reranking_method = "sum_scores"  # Default re-ranking method

        # Managers and handlers (initialized in main())
        self.tab_manager = None
        self.event_handlers = None
        self.data_updaters = None
        self.dialog_manager = None
        self.workflow_executor = None
        
        # Research components
        self.config = None
        self.workflow_orchestrator = None
        self.preliminary_report = ""
        self.final_report = ""
        self.agents_initialized = agents is not None
        self.agents = agents
        
        # Data storage for tabs
        self.documents: List[dict] = []
        self.scored_documents: List[tuple] = []
        self.citations: List[Any] = []
        self.counterfactual_analysis = None
        
        # Default workflow steps
        self.workflow_steps = [
            WorkflowStep.COLLECT_RESEARCH_QUESTION,
            WorkflowStep.GENERATE_AND_EDIT_QUERY,
            WorkflowStep.SEARCH_DOCUMENTS,
            WorkflowStep.REVIEW_SEARCH_RESULTS,
            WorkflowStep.SCORE_DOCUMENTS,
            WorkflowStep.EXTRACT_CITATIONS,
            WorkflowStep.GENERATE_REPORT,
            WorkflowStep.PERFORM_COUNTERFACTUAL_ANALYSIS,
            WorkflowStep.SEARCH_CONTRADICTORY_EVIDENCE,
            WorkflowStep.EDIT_COMPREHENSIVE_REPORT,
            WorkflowStep.EXPORT_REPORT
        ]
    
    def main(self, page: ft.Page):
        """Main application entry point."""
        self.page = page
        self._setup_page()
        self._initialize_managers()
        self._initialize_config()
        self._build_ui()
        self._handle_auto_start()
    
    def _setup_page(self):
        """Configure the main page settings."""
        self.page.title = "BMLibrarian Research Assistant"
        self.page.window.width = 1200
        self.page.window.height = 900
        self.page.window.min_width = 1000
        self.page.window.min_height = 700
        self.page.window.resizable = True
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.padding = 20
        self.page.scroll = ft.ScrollMode.AUTO
        # Store reference to app for Settings tab access
        self.page._research_gui_app = self
    
    def _initialize_managers(self):
        """Initialize all managers and handlers."""
        self.dialog_manager = DialogManager(self.page)
        self.tab_manager = TabManager(self.page)  # Pass page for scoring interface
        self.workflow_executor = WorkflowExecutor(self.agents, self.config_overrides, self.tab_manager)  # Pass tab_manager
        self.event_handlers = EventHandlers(self)
        self.data_updaters = DataUpdaters(self)

        # Pass data_updaters reference to workflow components that need it
        if self.workflow_executor and hasattr(self.workflow_executor, 'steps_handler'):
            self.workflow_executor.steps_handler.data_updaters = self.data_updaters
    
    def _initialize_config(self):
        """Initialize BMLibrarian configuration and components."""
        try:
            self.config = CLIConfig()
            self._load_config_defaults()
            self._apply_config_overrides()
            self._initialize_workflow_components()
        except Exception as e:
            if self.dialog_manager:
                self.dialog_manager.show_error_dialog(f"Failed to initialize configuration: {str(e)}")
            return
    
    def _load_config_defaults(self):
        """Load default values from config file."""
        try:
            from ..config import get_config
            config = get_config()
            search_config = config.get('search_strategy', {})

            # Load max_results and min_relevant from config if not already set by command line
            if 'max_results' not in self.config_overrides:
                self.max_results = config.get('max_results', 100)

            if 'min_relevant' not in self.config_overrides:
                self.min_relevant = config.get('min_relevant', 10)

            # Load search strategy settings from config
            self.search_strategy_keyword = search_config.get('keyword', {}).get('enabled', True)
            self.search_strategy_bm25 = search_config.get('bm25', {}).get('enabled', False)
            self.search_strategy_semantic = search_config.get('semantic', {}).get('enabled', False)
            self.search_strategy_hyde = search_config.get('hyde', {}).get('enabled', False)
            self.reranking_method = search_config.get('reranking', {}).get('method', 'sum_scores')

        except Exception as e:
            print(f"Warning: Could not load config defaults: {e}")
            # Use fallback defaults
            if 'max_results' not in self.config_overrides:
                self.max_results = 100
            if 'min_relevant' not in self.config_overrides:
                self.min_relevant = 10
            # Search strategy defaults already set in __init__
    
    def _apply_config_overrides(self):
        """Apply command-line overrides to configuration."""
        if self.config_overrides:
            for key, value in self.config_overrides.items():
                setattr(self.config, key, value)
                # Update max_results in GUI if specified
                if key == 'max_results':
                    self.max_results = value
        
        if self.auto_question:
            self.config.auto_mode = True
    
    def _initialize_workflow_components(self):
        """Initialize workflow orchestration components."""
        self.ui = UserInterface(self.config)
        self.query_processor = QueryProcessor(self.config, self.ui)
        self.formatter = ReportFormatter(self.config, self.ui)
        self.workflow_orchestrator = WorkflowOrchestrator(
            self.config, self.ui, self.query_processor, self.formatter
        )
    
    def _build_ui(self):
        """Build the main user interface using modular components."""
        # Create header
        header = create_header()

        # Create input components
        self.question_field = create_question_field(self.event_handlers.on_question_change)
        self.max_results_field = create_max_results_field(
            self.max_results,
            self.event_handlers.on_max_results_change
        )
        self.min_relevant_field = create_min_relevant_field(
            self.min_relevant,
            self.event_handlers.on_min_relevant_change
        )
        self.human_loop_toggle = create_toggle_switch(
            "Interactive mode",
            self.human_in_loop,
            self.event_handlers.on_human_loop_toggle_change
        )
        self.counterfactual_toggle = create_toggle_switch(
            "Comprehensive counterfactual analysis",
            self.comprehensive_counterfactual,
            self.event_handlers.on_counterfactual_toggle_change
        )
        self.start_button = create_start_button(self.event_handlers.on_start_research)

        # Create search strategy checkboxes
        search_strategy_checkboxes = create_search_strategy_checkboxes(
            self.search_strategy_keyword,
            self.search_strategy_bm25,
            self.search_strategy_semantic,
            self.search_strategy_hyde,
            self.event_handlers.on_keyword_search_change,
            self.event_handlers.on_bm25_search_change,
            self.event_handlers.on_semantic_search_change,
            self.event_handlers.on_hyde_search_change,
            self.reranking_method,
            self.event_handlers.on_reranking_change
        )

        # Create status text (hidden by default)
        self.status_text = ft.Text(
            "Enter a research question to begin",
            size=12,
            color=ft.Colors.GREY_600,
            visible=False
        )

        # Create controls section with new layout
        controls_section = create_controls_section(
            self.question_field,
            self.max_results_field,
            self.min_relevant_field,
            self.human_loop_toggle,
            self.counterfactual_toggle,
            self.start_button,
            search_strategy_checkboxes
        )
        
        # Create step cards and tabbed interface
        self._create_step_cards()
        tabs_container = self.tab_manager.create_tabbed_interface(self.step_cards)

        # Wire event handlers to tab manager buttons (must be done after tabs are created)
        self.tab_manager.wire_event_handlers(self.event_handlers)

        # Build main layout
        main_content = ft.Column([
            header,
            controls_section,
            ft.Container(
                content=tabs_container,
                expand=True
            )
        ], spacing=8, expand=True)
        
        self.page.add(main_content)
    
    def _create_step_cards(self):
        """Create step cards for each workflow step."""
        self.step_cards = {}
        for step in self.workflow_steps:
            card = StepCard(step, on_expand_change=self.event_handlers.on_step_expand)
            self.step_cards[step] = card
    
    def _handle_auto_start(self):
        """Handle auto-start if question was provided via command line."""
        if not self.auto_question:
            return
        
        self.research_question = self.auto_question
        self.question_field.value = self.auto_question
        self.human_loop_toggle.value = self.human_in_loop
        self.counterfactual_toggle.value = self.comprehensive_counterfactual
        self.start_button.disabled = False
        self.event_handlers._update_status()
        self.page.update()
        
        # Auto-start the research
        import threading
        import time
        
        def auto_start():
            time.sleep(1)  # Give UI time to render
            self.event_handlers.on_start_research(None)
        
        thread = threading.Thread(target=auto_start, daemon=True)
        thread.start()


# Backwards compatibility - keep the same class name for imports
ResearchGUI_Original = ResearchGUI