"""
Main Research GUI Application for BMLibrarian

Contains the primary ResearchGUI class that orchestrates the entire research interface.
"""

import threading
import flet as ft
from typing import Dict, Any, Optional
from datetime import datetime

from .components import StepCard
from .dialogs import DialogManager
from .workflow import WorkflowExecutor
from ..cli.workflow_steps import WorkflowStep
from ..cli import CLIConfig, UserInterface, QueryProcessor, ReportFormatter, WorkflowOrchestrator


class ResearchGUI:
    """Main research GUI application."""
    
    def __init__(self, agents=None):
        self.page: Optional[ft.Page] = None
        self.research_question = ""
        self.human_in_loop = True
        self.workflow_running = False
        
        # Command-line configuration
        self.config_overrides = {}
        self.auto_question = None
        
        # GUI components
        self.question_field = None
        self.human_loop_toggle = None
        self.start_button = None
        self.step_cards: Dict[WorkflowStep, StepCard] = {}
        self.status_text = None
        self.workflow_expansion = None
        
        # Research components (pre-initialized agents can be passed in)
        self.config = None
        self.workflow_orchestrator = None
        self.final_report = ""
        self.agents_initialized = agents is not None
        self.agents = agents
        
        # Managers
        self.dialog_manager = None
        self.workflow_executor = None
        
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
        
        # Literature, scoring, citations, and report data for tabs
        self.documents = []
        self.scored_documents = []
        self.citations = []
        self.literature_tab_content = None
        self.scoring_tab_content = None
        self.citations_tab_content = None
        self.report_tab_content = None
    
    def main(self, page: ft.Page):
        """Main application entry point."""
        self.page = page
        page.title = "BMLibrarian Research Assistant"
        page.window.width = 1200
        page.window.height = 900
        page.window.min_width = 1000
        page.window.min_height = 700
        page.window.resizable = True
        page.theme_mode = ft.ThemeMode.LIGHT
        page.padding = 20
        page.scroll = ft.ScrollMode.AUTO
        
        # Initialize managers
        self.dialog_manager = DialogManager(page)
        self.workflow_executor = WorkflowExecutor(self.agents, self.config_overrides)
        
        # Initialize configuration
        try:
            self._initialize_config()
        except Exception as e:
            self.dialog_manager.show_error_dialog(f"Failed to initialize configuration: {str(e)}")
            return
        
        # Build UI
        self._build_ui()
        
        # Handle auto-start if question was provided via command line
        if self.auto_question:
            self.research_question = self.auto_question
            self.question_field.value = self.auto_question
            self.human_loop_toggle.value = self.human_in_loop
            self.start_button.disabled = False
            self._update_status()
            self.page.update()
            
            # Auto-start the research
            def auto_start():
                import time
                time.sleep(1)  # Give UI time to render
                self._start_research(None)
            
            thread = threading.Thread(target=auto_start, daemon=True)
            thread.start()
    
    def _initialize_config(self):
        """Initialize BMLibrarian configuration and components."""
        self.config = CLIConfig()
        
        # Apply command-line overrides
        if self.config_overrides:
            for key, value in self.config_overrides.items():
                setattr(self.config, key, value)
        
        # Set auto_mode in config if we have an auto question
        if self.auto_question:
            self.config.auto_mode = True
        
        # Initialize other components 
        self.ui = UserInterface(self.config)
        self.query_processor = QueryProcessor(self.config, self.ui)
        self.formatter = ReportFormatter(self.config, self.ui)
        self.workflow_orchestrator = WorkflowOrchestrator(
            self.config, self.ui, self.query_processor, self.formatter
        )
    
    def _build_ui(self):
        """Build the main user interface."""
        # Header
        header = ft.Container(
            content=ft.Column([
                ft.Text(
                    "BMLibrarian Research Assistant",
                    size=28,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.BLUE_700
                ),
                ft.Text(
                    "AI-Powered Evidence-Based Medical Literature Research",
                    size=14,
                    color=ft.Colors.GREY_600
                )
            ], spacing=5),
            margin=ft.margin.only(bottom=20)
        )
        
        # Research question input
        self.question_field = ft.TextField(
            label="Enter your medical research question",
            hint_text="e.g., What are the cardiovascular benefits of regular exercise in adults?",
            multiline=True,
            min_lines=3,
            max_lines=6,
            expand=True,
            on_change=self._on_question_change
        )
        
        # Controls section - right side
        self.human_loop_toggle = ft.Switch(
            label="Interactive mode",
            value=self.human_in_loop,
            on_change=self._on_toggle_change
        )
        
        self.start_button = ft.ElevatedButton(
            "Start Research",
            icon=ft.Icons.SEARCH,
            on_click=self._start_research,
            style=ft.ButtonStyle(
                bgcolor=ft.Colors.BLUE_600,
                color=ft.Colors.WHITE
            ),
            height=45,
            width=160,
            disabled=True
        )
        
        self.status_text = ft.Text(
            "Enter a research question to begin",
            size=12,
            color=ft.Colors.GREY_600,
            visible=False  # Hide the status text
        )
        
        # Right-side controls
        controls_column = ft.Column([
            self.human_loop_toggle,
            self.start_button
        ], spacing=8, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
        
        # Main input row with question field and controls
        controls_section = ft.Container(
            content=ft.Column([
                ft.Row([
                    self.question_field,
                    ft.Container(width=20),  # Spacer
                    ft.Container(
                        content=controls_column,
                        width=200,
                        alignment=ft.alignment.center
                    )
                ], alignment=ft.MainAxisAlignment.START, vertical_alignment=ft.CrossAxisAlignment.START)
            ], spacing=8),
            padding=ft.padding.all(15),
            bgcolor=ft.Colors.GREY_50,
            border_radius=10,
            margin=ft.margin.only(bottom=15)
        )
        
        # Create tabbed interface
        self._create_tabbed_interface()
        
        # Add all sections to page with proper expansion (no separate report section needed)
        main_content = ft.Column([
            header,
            controls_section,
            ft.Container(
                content=self.tabs_container,
                expand=True  # Tabs get all the remaining space
            )
        ], spacing=8, expand=True)
        
        self.page.add(main_content)
    
    def _create_tabbed_interface(self):
        """Create the tabbed interface with Workflow, Literature, and Scoring tabs."""
        # Create step cards first
        self._create_step_cards()
        
        # Create workflow tab content
        workflow_tab = self._create_workflow_tab()
        
        # Create literature tab content (initially empty)
        literature_tab = self._create_literature_tab()
        
        # Create scoring tab content (initially empty)
        scoring_tab = self._create_scoring_tab()
        
        # Create citations tab content (initially empty)
        citations_tab = self._create_citations_tab()
        
        # Create report tab content (initially empty)
        report_tab = self._create_report_tab()
        
        # Create tabs
        self.tabs_container = ft.Tabs(
            selected_index=0,
            animation_duration=300,
            tabs=[
                ft.Tab(
                    text="Workflow",
                    icon=ft.Icons.TIMELINE,
                    content=workflow_tab
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
                    text="Report",
                    icon=ft.Icons.DESCRIPTION,
                    content=report_tab
                )
            ],
            tab_alignment=ft.TabAlignment.START
        )
    
    def _create_workflow_tab(self):
        """Create the workflow progress tab content."""
        steps_column = ft.Column(
            [card.build() for card in self.step_cards.values()],
            spacing=8
        )
        
        workflow_content = ft.Container(
            content=ft.Column([steps_column], scroll=ft.ScrollMode.AUTO),
            expand=True
        )
        
        return workflow_content
    
    def _create_literature_tab(self):
        """Create the literature review tab content."""
        self.literature_tab_content = ft.Container(
            content=ft.Column([
                ft.Text(
                    "Literature Review",
                    size=18,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.BLUE_700
                ),
                ft.Text(
                    "Documents will appear here after search is completed.",
                    size=14,
                    color=ft.Colors.GREY_600
                ),
                ft.Container(
                    content=ft.Text("No documents found yet."),
                    padding=ft.padding.all(20),
                    bgcolor=ft.Colors.GREY_50,
                    border_radius=5
                )
            ], spacing=10, scroll=ft.ScrollMode.AUTO),
            padding=ft.padding.all(15),
            expand=True
        )
        return self.literature_tab_content
    
    def _create_scoring_tab(self):
        """Create the scoring results tab content."""
        self.scoring_tab_content = ft.Container(
            content=ft.Column([
                ft.Text(
                    "Document Scoring Results",
                    size=18,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.BLUE_700
                ),
                ft.Text(
                    "Scored documents will appear here ordered by relevance score.",
                    size=14,
                    color=ft.Colors.GREY_600
                ),
                ft.Container(
                    content=ft.Text("No scored documents yet."),
                    padding=ft.padding.all(20),
                    bgcolor=ft.Colors.GREY_50,
                    border_radius=5
                )
            ], spacing=10, scroll=ft.ScrollMode.AUTO),
            padding=ft.padding.all(15),
            expand=True
        )
        return self.scoring_tab_content
    
    def _create_citations_tab(self):
        """Create the citations tab content."""
        self.citations_tab_content = ft.Container(
            content=ft.Column([
                ft.Text(
                    "Extracted Citations",
                    size=18,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.BLUE_700
                ),
                ft.Text(
                    "Relevant passages extracted from high-scoring documents.",
                    size=14,
                    color=ft.Colors.GREY_600
                ),
                ft.Container(
                    content=ft.Text("No citations extracted yet."),
                    padding=ft.padding.all(20),
                    bgcolor=ft.Colors.GREY_50,
                    border_radius=5
                )
            ], spacing=10, scroll=ft.ScrollMode.AUTO),
            padding=ft.padding.all(15),
            expand=True
        )
        return self.citations_tab_content
    
    def _create_report_tab(self):
        """Create the report tab content."""
        self.report_tab_content = ft.Container(
            content=ft.Column([
                ft.Text(
                    "Research Report",
                    size=18,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.BLUE_700
                ),
                ft.Text(
                    "Final comprehensive research report with citations and analysis.",
                    size=14,
                    color=ft.Colors.GREY_600
                ),
                ft.Container(
                    content=ft.Text("Report will appear here once workflow is complete."),
                    padding=ft.padding.all(20),
                    bgcolor=ft.Colors.GREY_50,
                    border_radius=5
                )
            ], spacing=10, scroll=ft.ScrollMode.AUTO),
            padding=ft.padding.all(15),
            expand=True
        )
        return self.report_tab_content
    
    def _create_step_cards(self):
        """Create step cards for each workflow step."""
        self.step_cards = {}
        for step in self.workflow_steps:
            card = StepCard(step, on_expand_change=self._on_step_expand)
            self.step_cards[step] = card
    
    
    def _on_question_change(self, e):
        """Handle research question input change."""
        self.research_question = e.control.value.strip()
        self.start_button.disabled = not self.research_question or self.workflow_running
        self._update_status()
        self.page.update()
    
    def _on_toggle_change(self, e):
        """Handle human-in-the-loop toggle change."""
        self.human_in_loop = e.control.value
        self._update_status()
        self.page.update()
    
    def _update_status(self):
        """Update the status text."""
        if not self.research_question:
            self.status_text.value = "Enter a research question to begin"
        elif self.workflow_running:
            self.status_text.value = f"Research in progress... ({'Interactive' if self.human_in_loop else 'Automated'} mode)"
        else:
            mode = "Interactive" if self.human_in_loop else "Automated"
            self.status_text.value = f"Ready to start research in {mode} mode"
    
    def _on_step_expand(self, card: StepCard, expanded: bool):
        """Handle step card expansion change."""
        if self.page:
            self.page.update()
    
    def _start_research(self, e):
        """Start the research workflow."""
        if not self.research_question or self.workflow_running:
            return
        
        if not self.agents_initialized:
            self.dialog_manager.show_error_dialog("Research agents are not available. Please check your configuration and restart the application.")
            return
        
        self.workflow_running = True
        self.start_button.disabled = True
        self._update_status()
        self.page.update()
        
        # Run workflow in separate thread to avoid blocking UI
        def run_workflow():
            try:
                print("Starting workflow execution...")
                self.final_report = self.workflow_executor.run_workflow(
                    self.research_question,
                    self.human_in_loop,
                    self._update_step_status,
                    self.dialog_manager,  # Pass dialog manager for interactive mode
                    self.step_cards  # Pass step cards for inline editing
                )
                
                print(f"Workflow completed. Final report length: {len(self.final_report) if self.final_report else 0}")
                
                # Final report is now displayed in the Report tab automatically
                
                # Final check and update for tabs after workflow completion
                print("🔍 Final tab update check after workflow completion...")
                print(f"🗂️ Workflow executor has 'documents' attr: {hasattr(self.workflow_executor, 'documents')}")
                if hasattr(self.workflow_executor, 'documents'):
                    docs = self.workflow_executor.documents
                    print(f"📚 Workflow executor documents count: {len(docs) if docs else 0}")
                    if docs:
                        print(f"📖 Final update: Updating literature tab with {len(docs)} documents")
                        self.update_documents(docs)
                    else:
                        print(f"❌ Final update: No documents in workflow_executor.documents")
                
                print(f"📊 Workflow executor has 'scored_documents' attr: {hasattr(self.workflow_executor, 'scored_documents')}")
                if hasattr(self.workflow_executor, 'scored_documents'):
                    scored_docs = self.workflow_executor.scored_documents  
                    print(f"📈 Workflow executor scored documents count: {len(scored_docs) if scored_docs else 0}")
                    if scored_docs:
                        print(f"📊 Final update: Updating scoring tab with {len(scored_docs)} scored documents")
                        self.update_scored_documents(scored_docs)
                    else:
                        print(f"❌ Final update: No scored documents in workflow_executor.scored_documents")
                
                print(f"📝 Workflow executor has 'citations' attr: {hasattr(self.workflow_executor, 'citations')}")
                if hasattr(self.workflow_executor, 'citations'):
                    citations = self.workflow_executor.citations
                    print(f"📚 Workflow executor citations count: {len(citations) if citations else 0}")
                    if citations:
                        print(f"📝 Final update: Updating citations tab with {len(citations)} citations")
                        self.update_citations(citations)
                    else:
                        print(f"❌ Final update: No citations in workflow_executor.citations")
                
                # Check for final report
                if hasattr(self.workflow_executor, 'final_report') and self.workflow_executor.final_report:
                    report = self.workflow_executor.final_report
                    print(f"📄 Final update: Updating report tab with final report (length: {len(report)})")
                    self.update_report(report)
                else:
                    print(f"❌ Final update: No final report available")
                
            except Exception as ex:
                self._handle_workflow_error(ex)
            finally:
                self.workflow_running = False
                self.start_button.disabled = not self.research_question
                self._update_status()
                if self.page:
                    self.page.update()
        
        thread = threading.Thread(target=run_workflow, daemon=True)
        thread.start()
    
    def _update_step_status(self, step: WorkflowStep, status: str, content: str = None):
        """Update a step's status and content."""
        if step in self.step_cards:
            self.step_cards[step].update_status(status, content)
            
            # Debug logging
            # print(f"Step update: {step.name} -> {status}")
            
            # Update tabs when documents are found or scored
            if step == WorkflowStep.SEARCH_DOCUMENTS and (status == "completed" or status == "tab_update"):
                print(f"🔍 SEARCH_DOCUMENTS {status} - checking for documents...")
                if hasattr(self.workflow_executor, 'documents'):
                    docs = self.workflow_executor.documents
                    print(f"📚 Found {len(docs)} documents in workflow_executor")
                    if docs:
                        print(f"✅ Updating Literature tab with {len(docs)} documents")
                        self.update_documents(docs)
                    else:
                        print(f"❌ No documents to update Literature tab")
                else:
                    print(f"❌ workflow_executor has no 'documents' attribute")
                    
            elif step == WorkflowStep.SCORE_DOCUMENTS and (status == "completed" or status == "tab_update"):
                print(f"📊 SCORE_DOCUMENTS {status} - checking for scored documents...")
                if hasattr(self.workflow_executor, 'scored_documents'):
                    scored_docs = self.workflow_executor.scored_documents
                    print(f"📈 Found {len(scored_docs)} scored documents in workflow_executor")
                    if scored_docs:
                        print(f"✅ Updating Scoring tab with {len(scored_docs)} scored documents")
                        self.update_scored_documents(scored_docs)
                    else:
                        print(f"❌ No scored documents to update Scoring tab")
                else:
                    print(f"❌ workflow_executor has no 'scored_documents' attribute")
                    
            elif step == WorkflowStep.EXTRACT_CITATIONS and (status == "completed" or status == "tab_update"):
                print(f"📝 EXTRACT_CITATIONS {status} - checking for citations...")
                if hasattr(self.workflow_executor, 'citations'):
                    citations = self.workflow_executor.citations
                    print(f"📚 Found {len(citations)} citations in workflow_executor")
                    if citations:
                        print(f"✅ Updating Citations tab with {len(citations)} citations")
                        self.update_citations(citations)
                    else:
                        print(f"❌ No citations to update Citations tab")
                else:
                    print(f"❌ workflow_executor has no 'citations' attribute")
                    
            elif step == WorkflowStep.EXPORT_REPORT and (status == "completed" or status == "tab_update"):
                print(f"📄 EXPORT_REPORT {status} - checking for final report...")
                if hasattr(self.workflow_executor, 'final_report') and self.workflow_executor.final_report:
                    report = self.workflow_executor.final_report
                    print(f"📝 Found report with length: {len(report)}")
                    print(f"✅ Updating Report tab with final report")
                    self.update_report(report)
                else:
                    print(f"❌ No final report available in workflow_executor")
            
            if self.page:
                self.page.update()
    
    def update_documents(self, documents):
        """Update the documents list and refresh the literature tab."""
        print(f"📖 update_documents called with {len(documents)} documents")
        self.documents = documents
        print(f"📚 Stored {len(self.documents)} documents in app.documents")
        print(f"📄 Calling _update_literature_tab...")
        self._update_literature_tab()
        print(f"📱 Updating page...")
        if self.page:
            self.page.update()
        print(f"✅ Literature tab update completed")
    
    def update_scored_documents(self, scored_documents):
        """Update the scored documents and refresh the scoring tab."""
        self.scored_documents = scored_documents
        self._update_scoring_tab()
        if self.page:
            self.page.update()
    
    def update_citations(self, citations):
        """Update the citations and refresh the citations tab."""
        print(f"📝 update_citations called with {len(citations)} citations")
        self.citations = citations
        print(f"📚 Stored {len(self.citations)} citations in app.citations")
        print(f"📄 Calling _update_citations_tab...")
        self._update_citations_tab()
        print(f"📱 Updating page...")
        if self.page:
            self.page.update()
        print(f"✅ Citations tab update completed")
    
    def update_report(self, report_content: str):
        """Update the report and refresh the report tab."""
        print(f"📄 update_report called with report length: {len(report_content) if report_content else 0}")
        self.final_report = report_content
        print(f"📝 Stored report content in app.final_report")
        print(f"📄 Calling _update_report_tab...")
        self._update_report_tab()
        print(f"📱 Updating page...")
        if self.page:
            self.page.update()
        print(f"✅ Report tab update completed")
    
    def _update_literature_tab(self):
        """Update the literature tab with found documents."""
        print(f"📚 _update_literature_tab called")
        print(f"🔢 Documents count: {len(self.documents) if self.documents else 0}")
        print(f"📝 Literature tab content exists: {self.literature_tab_content is not None}")
        
        if not self.documents:
            print(f"❌ No documents - exiting _update_literature_tab")
            return
        
        # Create document cards for literature tab
        doc_cards = []
        
        # Header with count
        doc_cards.append(
            ft.Text(
                f"Literature Review ({len(self.documents)} documents found)",
                size=18,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.BLUE_700
            )
        )
        
        doc_cards.append(
            ft.Text(
                "All documents found in the search, ordered by search relevance.",
                size=14,
                color=ft.Colors.GREY_600
            )
        )
        
        # Create expandable cards for each document
        for i, doc in enumerate(self.documents):
            doc_card = self._create_document_card(i, doc, show_score=False)
            doc_cards.append(doc_card)
        
        # Update the literature tab content
        print(f"📋 Created {len(doc_cards)} document cards")
        if self.literature_tab_content:
            print(f"✅ Updating literature_tab_content with {len(doc_cards)} cards")
            self.literature_tab_content.content = ft.Column(
                doc_cards,
                spacing=10,
                scroll=ft.ScrollMode.AUTO
            )
            print(f"✅ Literature tab content updated successfully")
        else:
            print(f"❌ literature_tab_content is None - cannot update!")
    
    def _update_scoring_tab(self):
        """Update the scoring tab with scored documents ordered by score."""
        if not self.scored_documents:
            return
        
        # Sort documents by score (highest first)
        sorted_docs = sorted(self.scored_documents, 
                           key=lambda x: x[1].get('score', 0), reverse=True)
        
        # Create document cards for scoring tab
        doc_cards = []
        
        # Header with count
        doc_cards.append(
            ft.Text(
                f"Document Scoring Results ({len(sorted_docs)} documents scored)",
                size=18,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.BLUE_700
            )
        )
        
        doc_cards.append(
            ft.Text(
                "Documents ordered by AI relevance score (highest to lowest).",
                size=14,
                color=ft.Colors.GREY_600
            )
        )
        
        # Create expandable cards for each scored document
        for i, (doc, scoring_result) in enumerate(sorted_docs):
            doc_card = self._create_document_card(i, doc, show_score=True, scoring_result=scoring_result)
            doc_cards.append(doc_card)
        
        # Update the scoring tab content
        if self.scoring_tab_content:
            self.scoring_tab_content.content = ft.Column(
                doc_cards,
                spacing=10,
                scroll=ft.ScrollMode.AUTO
            )
    
    def _update_citations_tab(self):
        """Update the citations tab with extracted citations."""
        print(f"📝 _update_citations_tab called")
        print(f"🔢 Citations count: {len(self.citations) if self.citations else 0}")
        print(f"📄 Citations tab content exists: {self.citations_tab_content is not None}")
        
        if not self.citations:
            print(f"❌ No citations - exiting _update_citations_tab")
            return
        
        # Create citation cards for citations tab
        citation_cards = []
        
        # Header with count
        citation_cards.append(
            ft.Text(
                f"Extracted Citations ({len(self.citations)} citations found)",
                size=18,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.BLUE_700
            )
        )
        
        citation_cards.append(
            ft.Text(
                "Relevant passages extracted from high-scoring documents, ordered by relevance.",
                size=14,
                color=ft.Colors.GREY_600
            )
        )
        
        # Sort citations by relevance score (highest first)
        sorted_citations = sorted(self.citations, 
                                key=lambda c: getattr(c, 'relevance_score', 0), reverse=True)
        
        # Create expandable cards for each citation
        for i, citation in enumerate(sorted_citations):
            citation_card = self._create_citation_card(i, citation)
            citation_cards.append(citation_card)
        
        # Update the citations tab content
        print(f"📋 Created {len(citation_cards)} citation cards")
        if self.citations_tab_content:
            print(f"✅ Updating citations_tab_content with {len(citation_cards)} cards")
            self.citations_tab_content.content = ft.Column(
                citation_cards,
                spacing=10,
                scroll=ft.ScrollMode.AUTO
            )
            print(f"✅ Citations tab content updated successfully")
        else:
            print(f"❌ citations_tab_content is None - cannot update!")
    
    def _update_report_tab(self):
        """Update the report tab with the final report."""
        print(f"📄 _update_report_tab called")
        print(f"📝 Report exists: {bool(self.final_report)}")
        print(f"📊 Report length: {len(self.final_report) if self.final_report else 0}")
        print(f"📄 Report tab content exists: {self.report_tab_content is not None}")
        
        if not self.final_report:
            print(f"❌ No report - exiting _update_report_tab")
            return
        
        # Create report content for the tab
        report_components = []
        
        # Header with action buttons
        action_buttons = ft.Row([
            ft.ElevatedButton(
                "Preview",
                icon=ft.Icons.PREVIEW,
                on_click=self._preview_report,
                height=40
            ),
            ft.ElevatedButton(
                "Copy to Clipboard",
                icon=ft.Icons.COPY,
                on_click=self._copy_report,
                height=40
            ),
            ft.ElevatedButton(
                "Save Report",
                icon=ft.Icons.SAVE,
                on_click=self._save_report,
                style=ft.ButtonStyle(
                    bgcolor=ft.Colors.GREEN_600,
                    color=ft.Colors.WHITE
                ),
                height=40
            )
        ], spacing=10, alignment=ft.MainAxisAlignment.END)
        
        # Header with title and buttons
        report_components.append(
            ft.Row([
                ft.Text(
                    f"Research Report ({len(self.final_report):,} characters)",
                    size=18,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.BLUE_700
                ),
                ft.Container(expand=True),
                action_buttons
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
        )
        
        # Report content display
        report_display = ft.Container(
            content=ft.Column([
                ft.Markdown(
                    value=self.final_report,
                    selectable=True,
                    extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                    on_tap_link=self._on_report_link_tap,
                    auto_follow_links=False
                )
            ], scroll=ft.ScrollMode.ALWAYS, expand=True),
            bgcolor=ft.Colors.GREY_50,
            border_radius=5,
            padding=ft.padding.all(15),
            expand=True
        )
        
        report_components.append(report_display)
        
        # Update the report tab content
        print(f"📋 Created report display components")
        if self.report_tab_content:
            print(f"✅ Updating report_tab_content with final report")
            self.report_tab_content.content = ft.Column(
                report_components,
                spacing=10,
                expand=True
            )
            print(f"✅ Report tab content updated successfully")
        else:
            print(f"❌ report_tab_content is None - cannot update!")
    
    def _create_document_card(self, index: int, doc: dict, show_score: bool = False, scoring_result: dict = None):
        """Create an expandable card for a document.
        
        Args:
            index: Document index
            doc: Document dictionary
            show_score: Whether to show scoring information
            scoring_result: Scoring result dictionary (if show_score is True)
        """
        title = doc.get('title', 'Untitled Document')
        abstract = doc.get('abstract', 'No abstract available')
        year = doc.get('year', 'Unknown year')
        authors = doc.get('authors', 'Unknown authors')
        
        # Truncate title for display
        display_title = title[:80] + "..." if len(title) > 80 else title
        
        # Create title row with optional score
        title_row = [
            ft.Text(
                f"{index + 1}. {display_title}",
                size=12,
                weight=ft.FontWeight.W_500,
                color=ft.Colors.BLUE_800
            )
        ]
        
        if show_score and scoring_result:
            score = scoring_result.get('score', 0)
            score_color = self._get_score_color(score)
            title_row.append(
                ft.Container(
                    content=ft.Text(
                        f"{score:.1f}",
                        size=12,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.WHITE
                    ),
                    bgcolor=score_color,
                    padding=ft.padding.symmetric(horizontal=8, vertical=4),
                    border_radius=12,
                    margin=ft.margin.only(left=10)
                )
            )
        
        # Create subtitle with year
        subtitle_text = f"Year: {year}"
        if show_score and scoring_result:
            reasoning = scoring_result.get('reasoning', 'No reasoning provided')[:50] + "..."
            subtitle_text += f" | {reasoning}"
        
        # Create expansion tile
        return ft.ExpansionTile(
            title=ft.Row(title_row, alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            subtitle=ft.Text(
                subtitle_text,
                size=11,
                color=ft.Colors.GREY_600
            ),
            controls=[
                ft.Container(
                    content=ft.Column([
                        # Full title
                        ft.Container(
                            content=ft.Text(
                                f"Title: {title}",
                                size=11,
                                weight=ft.FontWeight.BOLD,
                                color=ft.Colors.BLUE_900
                            ),
                            padding=ft.padding.only(bottom=8)
                        ),
                        # Authors
                        ft.Container(
                            content=ft.Text(
                                f"Authors: {authors}",
                                size=10,
                                color=ft.Colors.GREY_700
                            ),
                            padding=ft.padding.only(bottom=8)
                        ),
                        # Scoring details (if available)
                        *([ft.Container(
                            content=ft.Column([
                                ft.Text(
                                    f"AI Score: {scoring_result.get('score', 0):.1f}/5.0",
                                    size=11,
                                    weight=ft.FontWeight.BOLD,
                                    color=self._get_score_color(scoring_result.get('score', 0))
                                ),
                                ft.Text(
                                    f"Reasoning: {scoring_result.get('reasoning', 'No reasoning provided')}",
                                    size=10,
                                    color=ft.Colors.GREY_700
                                )
                            ], spacing=4),
                            padding=ft.padding.only(bottom=8),
                            bgcolor=ft.Colors.BLUE_50,
                            border_radius=5
                        )] if show_score and scoring_result else []),
                        # Abstract
                        ft.Container(
                            content=ft.Column([
                                ft.Text(
                                    "Abstract:",
                                    size=11,
                                    weight=ft.FontWeight.BOLD,
                                    color=ft.Colors.BLACK
                                ),
                                ft.Text(
                                    abstract,
                                    size=10,
                                    color=ft.Colors.GREY_800,
                                    selectable=True
                                )
                            ], spacing=4),
                            padding=ft.padding.all(8),
                            bgcolor=ft.Colors.GREY_100,
                            border_radius=5
                        )
                    ], spacing=4),
                    padding=ft.padding.all(10)
                )
            ]
        )
    
    def _get_score_color(self, score: float) -> str:
        """Get color based on score value."""
        if score >= 4.5:
            return ft.Colors.GREEN_700
        elif score >= 3.5:
            return ft.Colors.BLUE_700
        elif score >= 2.5:
            return ft.Colors.ORANGE_700
        else:
            return ft.Colors.RED_700
    
    def _create_citation_card(self, index: int, citation):
        """Create an expandable card for a citation.
        
        Args:
            index: Citation index
            citation: Citation object or dictionary
        """
        # Handle both Citation objects and dictionaries
        if hasattr(citation, 'document_title'):
            title = citation.document_title
            summary = citation.summary
            passage = citation.passage
            authors = getattr(citation, 'authors', [])
            publication_date = getattr(citation, 'publication_date', 'Unknown')
            relevance_score = getattr(citation, 'relevance_score', 0)
            document_id = getattr(citation, 'document_id', 'Unknown')
            pmid = getattr(citation, 'pmid', None)
        elif isinstance(citation, dict):
            title = citation.get('document_title', 'Untitled Document')
            summary = citation.get('summary', 'No summary available')
            passage = citation.get('passage', 'No passage available')
            authors = citation.get('authors', [])
            publication_date = citation.get('publication_date', 'Unknown')
            relevance_score = citation.get('relevance_score', 0)
            document_id = citation.get('document_id', 'Unknown')
            pmid = citation.get('pmid', None)
        else:
            title = 'Unknown Citation'
            summary = str(citation)
            passage = str(citation)
            authors = []
            publication_date = 'Unknown'
            relevance_score = 0
            document_id = 'Unknown'
            pmid = None
        
        # Truncate title for display
        display_title = title[:80] + "..." if len(title) > 80 else title
        
        # Create title row with relevance score
        relevance_color = self._get_relevance_color(relevance_score)
        title_row = [
            ft.Text(
                f"{index + 1}. {display_title}",
                size=12,
                weight=ft.FontWeight.W_500,
                color=ft.Colors.BLUE_800
            ),
            ft.Container(
                content=ft.Text(
                    f"{relevance_score:.2f}",
                    size=12,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.WHITE
                ),
                bgcolor=relevance_color,
                padding=ft.padding.symmetric(horizontal=8, vertical=4),
                border_radius=12,
                margin=ft.margin.only(left=10)
            )
        ]
        
        # Create subtitle with authors and date
        authors_str = ', '.join(authors[:3]) if authors else 'Unknown authors'
        if len(authors) > 3:
            authors_str += '...'
        subtitle_text = f"{authors_str} ({publication_date})"
        
        # Create expansion tile
        return ft.ExpansionTile(
            title=ft.Row(title_row, alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            subtitle=ft.Text(
                subtitle_text,
                size=11,
                color=ft.Colors.GREY_600
            ),
            controls=[
                ft.Container(
                    content=ft.Column([
                        # Full title
                        ft.Container(
                            content=ft.Text(
                                f"Title: {title}",
                                size=11,
                                weight=ft.FontWeight.BOLD,
                                color=ft.Colors.BLUE_900
                            ),
                            padding=ft.padding.only(bottom=8)
                        ),
                        # Authors
                        ft.Container(
                            content=ft.Text(
                                f"Authors: {', '.join(authors) if authors else 'Unknown'}",
                                size=10,
                                color=ft.Colors.GREY_700
                            ),
                            padding=ft.padding.only(bottom=8)
                        ),
                        # Citation metadata
                        ft.Container(
                            content=ft.Column([
                                ft.Text(
                                    f"Relevance Score: {relevance_score:.3f}",
                                    size=11,
                                    weight=ft.FontWeight.BOLD,
                                    color=relevance_color
                                ),
                                ft.Text(
                                    f"Document ID: {document_id}",
                                    size=10,
                                    color=ft.Colors.GREY_600
                                ),
                                *([
                                    ft.Text(
                                        f"PMID: {pmid}",
                                        size=10,
                                        color=ft.Colors.GREY_600
                                    )
                                ] if pmid else [])
                            ], spacing=4),
                            padding=ft.padding.only(bottom=8),
                            bgcolor=ft.Colors.BLUE_50,
                            border_radius=5
                        ),
                        # Summary
                        ft.Container(
                            content=ft.Column([
                                ft.Text(
                                    "Summary:",
                                    size=11,
                                    weight=ft.FontWeight.BOLD,
                                    color=ft.Colors.BLACK
                                ),
                                ft.Text(
                                    summary,
                                    size=10,
                                    color=ft.Colors.GREY_800,
                                    selectable=True
                                )
                            ], spacing=4),
                            padding=ft.padding.all(8),
                            bgcolor=ft.Colors.GREEN_50,
                            border_radius=5
                        ),
                        # Passage
                        ft.Container(
                            content=ft.Column([
                                ft.Text(
                                    "Extracted Passage:",
                                    size=11,
                                    weight=ft.FontWeight.BOLD,
                                    color=ft.Colors.BLACK
                                ),
                                ft.Text(
                                    passage,
                                    size=10,
                                    color=ft.Colors.GREY_800,
                                    selectable=True,
                                    italic=True
                                )
                            ], spacing=4),
                            padding=ft.padding.all(8),
                            bgcolor=ft.Colors.GREY_100,
                            border_radius=5
                        )
                    ], spacing=4),
                    padding=ft.padding.all(10)
                )
            ]
        )
    
    def _get_relevance_color(self, relevance: float) -> str:
        """Get color based on relevance score (0-1 range)."""
        if relevance >= 0.8:
            return ft.Colors.GREEN_700
        elif relevance >= 0.6:
            return ft.Colors.BLUE_700
        elif relevance >= 0.4:
            return ft.Colors.ORANGE_700
        else:
            return ft.Colors.RED_700
    
    
    def _handle_workflow_error(self, error: Exception):
        """Handle workflow execution errors."""
        error_msg = f"Research workflow failed: {str(error)}"
        print(f"Workflow error: {error}")
        
        if self.page:
            self.dialog_manager.show_error_dialog(error_msg)
    
    def _save_report(self, e):
        """Save the final report to a file."""
        print(f"Save button clicked. Report exists: {bool(self.final_report)}, Length: {len(self.final_report) if self.final_report else 0}")
        if self.final_report:
            # Show file path input dialog (avoiding FilePicker bug on macOS)
            self._show_save_path_dialog()
        else:
            self.dialog_manager.show_error_dialog("No report available to save")
    
    def _show_save_path_dialog(self):
        """Show custom save path dialog."""
        import os
        from datetime import datetime
        
        # Generate default path
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        default_filename = f"research_report_{timestamp}.md"
        default_path = os.path.join(os.path.expanduser("~/Desktop"), default_filename)
        
        def save_file(file_path):
            try:
                # Expand user path and ensure .md extension
                expanded_path = os.path.expanduser(file_path.strip())
                if not expanded_path.endswith('.md'):
                    expanded_path += '.md'
                
                # Create directory if needed
                os.makedirs(os.path.dirname(expanded_path), exist_ok=True)
                
                # Save the file
                with open(expanded_path, 'w', encoding='utf-8') as f:
                    f.write(self.final_report)
                
                self.dialog_manager.show_success_dialog(f"Report saved successfully to:\n{expanded_path}")
                print(f"Report saved to: {expanded_path}")
                
            except Exception as ex:
                self.dialog_manager.show_error_dialog(f"Failed to save report: {str(ex)}")
                print(f"Save error: {ex}")
        
        def close_save_dialog(e):
            self.page.overlay.clear()
            self.page.update()
        
        def handle_save(e):
            file_path = path_input.value.strip()
            if file_path:
                close_save_dialog(e)
                save_file(file_path)
            else:
                self.dialog_manager.show_error_dialog("Please enter a file path")
        
        # Create path input
        path_input = ft.TextField(
            label="Save report to:",
            value=default_path,
            width=500,
            hint_text="Enter full file path (e.g., ~/Desktop/my_report.md)"
        )
        
        # Create save dialog overlay
        save_dialog = ft.Container(
            content=ft.Column([
                ft.Text("Save Research Report", size=18, weight=ft.FontWeight.BOLD),
                ft.Text("Enter the path where you want to save the report:", size=12),
                path_input,
                ft.Row([
                    ft.Container(expand=True),
                    ft.TextButton("Cancel", on_click=close_save_dialog),
                    ft.ElevatedButton("Save", on_click=handle_save)
                ], alignment=ft.MainAxisAlignment.END)
            ], spacing=15),
            width=600,
            bgcolor=ft.Colors.WHITE,
            border_radius=10,
            padding=30,
            shadow=ft.BoxShadow(blur_radius=10, color=ft.Colors.GREY_400)
        )
        
        # Add to overlay
        self.page.overlay.clear()
        self.page.overlay.append(
            ft.Container(
                content=save_dialog,
                alignment=ft.alignment.center,
                bgcolor=ft.Colors.with_opacity(0.5, ft.Colors.BLACK)
            )
        )
        
        self.page.update()
        print("Save path dialog created and displayed")
    
    def _copy_report(self, e):
        """Copy the report to clipboard."""
        if self.final_report:
            self.dialog_manager.copy_to_clipboard(self.final_report)
    
    def _preview_report(self, e):
        """Show report in a preview dialog."""
        print(f"Preview button clicked. Report exists: {bool(self.final_report)}, Length: {len(self.final_report) if self.final_report else 0}")
        if self.final_report:
            # Use a different approach for preview
            try:
                def close_preview(e):
                    self.page.overlay.clear()
                    self.page.update()
                
                # Create preview content using overlay instead of dialog
                preview_content = ft.Container(
                    content=ft.Column([
                        ft.Row([
                            ft.Text("Report Preview", size=18, weight=ft.FontWeight.BOLD),
                            ft.Container(expand=True),
                            ft.IconButton(
                                icon=ft.Icons.CLOSE,
                                on_click=close_preview,
                                tooltip="Close Preview"
                            )
                        ]),
                        ft.Container(
                            content=ft.Column([
                                ft.Markdown(
                                    value=self.final_report[:8000] + ("..." if len(self.final_report) > 8000 else ""),
                                    selectable=True,
                                    extension_set=ft.MarkdownExtensionSet.GITHUB_WEB
                                )
                            ], scroll=ft.ScrollMode.ALWAYS, expand=True),
                            expand=True,
                            bgcolor=ft.Colors.GREY_50,
                            border_radius=5,
                            padding=15
                        )
                    ], expand=True),
                    width=800,
                    height=600,
                    bgcolor=ft.Colors.WHITE,
                    border_radius=10,
                    padding=20,
                    shadow=ft.BoxShadow(blur_radius=10, color=ft.Colors.GREY_400)
                )
                
                # Add to overlay
                self.page.overlay.clear()
                self.page.overlay.append(
                    ft.Container(
                        content=preview_content,
                        alignment=ft.alignment.center,
                        bgcolor=ft.Colors.with_opacity(0.5, ft.Colors.BLACK)
                    )
                )
                
                self.page.update()
                print("Preview overlay created and displayed")
                
            except Exception as ex:
                print(f"Preview error: {ex}")
                # Fallback to dialog
                self.dialog_manager.show_preview_dialog(self.final_report)
        else:
            self.dialog_manager.show_error_dialog("No report available to preview")
    
    def _on_report_link_tap(self, e):
        """Handle links in the report."""
        print(f"Report link tapped: {e.data}")