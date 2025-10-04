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

        # Create scoring interface if page is available
        if page:
            self.scoring_interface = ScoringInterface(page)
        
    def create_tabbed_interface(self, step_cards: Dict[WorkflowStep, StepCard]) -> ft.Tabs:
        """Create the complete tabbed interface."""
        workflow_tab = self._create_workflow_tab(step_cards)
        literature_tab = self._create_literature_tab()
        scoring_tab = self._create_scoring_tab()
        citations_tab = self._create_citations_tab()
        preliminary_report_tab = self._create_preliminary_report_tab()
        counterfactual_tab = self._create_counterfactual_tab()
        report_tab = self._create_report_tab()
        
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
                )
            ],
            tab_alignment=ft.TabAlignment.START
        )
        
        return self.tabs_container
    
    def _create_workflow_tab(self, step_cards: Dict[WorkflowStep, StepCard]) -> ft.Container:
        """Create the workflow progress tab content."""
        steps_column = ft.Column(
            [card.build() for card in step_cards.values()],
            spacing=8
        )
        
        return ft.Container(
            content=ft.Column([steps_column], scroll=ft.ScrollMode.AUTO),
            expand=True
        )
    
    def _create_literature_tab(self) -> ft.Container:
        """Create the literature review tab content."""
        header_components = create_tab_header(
            "Literature Review",
            subtitle="Documents will appear here after search is completed."
        )
        
        empty_state = create_empty_state("No documents found yet.")
        
        self.tab_contents['literature'] = ft.Container(
            content=ft.Column(
                [*header_components, empty_state],
                spacing=10,
                scroll=ft.ScrollMode.AUTO
            ),
            padding=ft.padding.all(15),
            expand=True
        )
        
        return self.tab_contents['literature']
    
    def _create_scoring_tab(self) -> ft.Container:
        """Create the scoring results tab content with integrated scoring interface."""
        # Create scoring interface if not already created
        if not self.scoring_interface and self.page:
            self.scoring_interface = ScoringInterface(self.page)

        # Use scoring interface if available, otherwise create placeholder
        if self.scoring_interface:
            scoring_content = self.scoring_interface.create_interface()
        else:
            header_components = create_tab_header(
                "Document Scoring Results",
                subtitle="Scored documents will appear here ordered by relevance score."
            )
            empty_state = create_empty_state("No scored documents yet.")
            scoring_content = ft.Column(
                [*header_components, empty_state],
                spacing=10,
                scroll=ft.ScrollMode.AUTO
            )

        self.tab_contents['scoring'] = ft.Container(
            content=scoring_content,
            padding=ft.padding.all(15),
            expand=True
        )

        return self.tab_contents['scoring']
    
    def _create_citations_tab(self) -> ft.Container:
        """Create the citations tab content."""
        header_components = create_tab_header(
            "Extracted Citations",
            subtitle="Relevant passages extracted from high-scoring documents."
        )
        
        empty_state = create_empty_state("No citations extracted yet.")
        
        self.tab_contents['citations'] = ft.Container(
            content=ft.Column(
                [*header_components, empty_state],
                spacing=10,
                scroll=ft.ScrollMode.AUTO
            ),
            padding=ft.padding.all(15),
            expand=True
        )
        
        return self.tab_contents['citations']
    
    def _create_preliminary_report_tab(self) -> ft.Container:
        """Create the preliminary report tab content."""
        header_components = create_tab_header(
            "Preliminary Report",
            subtitle="Initial research report before counterfactual analysis."
        )
        
        empty_state = create_empty_state(
            "Preliminary report will appear here after report generation."
        )
        
        self.tab_contents['preliminary_report'] = ft.Container(
            content=ft.Column(
                [*header_components, empty_state],
                spacing=10,
                scroll=ft.ScrollMode.AUTO
            ),
            padding=ft.padding.all(15),
            expand=True
        )
        
        return self.tab_contents['preliminary_report']
    
    def _create_counterfactual_tab(self) -> ft.Container:
        """Create the counterfactual analysis tab content."""
        header_components = create_tab_header(
            "Counterfactual Analysis",
            subtitle="Analysis of potential contradictory evidence and research questions."
        )
        
        empty_state = create_empty_state(
            "Counterfactual analysis will appear here when enabled and completed."
        )
        
        self.tab_contents['counterfactual'] = ft.Container(
            content=ft.Column(
                [*header_components, empty_state],
                spacing=10,
                scroll=ft.ScrollMode.AUTO
            ),
            padding=ft.padding.all(15),
            expand=True
        )
        
        return self.tab_contents['counterfactual']
    
    def _create_report_tab(self) -> ft.Container:
        """Create the report tab content."""
        header_components = create_tab_header(
            "Research Report",
            subtitle="Final comprehensive research report with citations and analysis."
        )
        
        empty_state = create_empty_state(
            "Report will appear here once workflow is complete."
        )
        
        self.tab_contents['report'] = ft.Container(
            content=ft.Column(
                [*header_components, empty_state],
                spacing=10,
                scroll=ft.ScrollMode.AUTO
            ),
            padding=ft.padding.all(15),
            expand=True
        )
        
        return self.tab_contents['report']
    
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