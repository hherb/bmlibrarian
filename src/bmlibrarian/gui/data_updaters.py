"""
Data Updaters Module for Research GUI

Contains functions for updating tab content with workflow data.
"""

import flet as ft
from typing import TYPE_CHECKING, List, Any
from .ui_builder import create_tab_header, create_action_button_row

if TYPE_CHECKING:
    from .research_app import ResearchGUI


class DataUpdaters:
    """Handles data updates for GUI tabs."""
    
    def __init__(self, app: 'ResearchGUI'):
        self.app = app
    
    def update_documents(self, documents: List[dict]):
        """Update the documents list and refresh the literature tab."""
        print(f"📖 update_documents called with {len(documents)} documents")
        self.app.documents = documents
        print(f"📚 Stored {len(self.app.documents)} documents in app.documents")
        print(f"📄 Calling _update_literature_tab...")
        self._update_literature_tab()
        print(f"📱 Updating page...")
        if self.app.page:
            self.app.page.update()
        print(f"✅ Literature tab update completed")
    
    def update_scored_documents(self, scored_documents: List[tuple]):
        """Update the scored documents and refresh the scoring tab."""
        self.app.scored_documents = scored_documents
        self._update_scoring_tab()
        if self.app.page:
            self.app.page.update()
    
    def update_citations(self, citations: List[Any]):
        """Update the citations and refresh the citations tab."""
        print(f"📝 update_citations called with {len(citations)} citations")
        self.app.citations = citations
        print(f"📚 Stored {len(self.app.citations)} citations in app.citations")
        print(f"📄 Calling _update_citations_tab...")
        self._update_citations_tab()
        print(f"📱 Updating page...")
        if self.app.page:
            self.app.page.update()
        print(f"✅ Citations tab update completed")
    
    def update_counterfactual_analysis(self, counterfactual_analysis: Any):
        """Update the counterfactual analysis and refresh the counterfactual tab."""
        print(f"🧿 update_counterfactual_analysis called with analysis: {bool(counterfactual_analysis)}")
        self.app.counterfactual_analysis = counterfactual_analysis
        print(f"🤖 Stored counterfactual analysis in app.counterfactual_analysis")
        print(f"📄 Calling _update_counterfactual_tab...")
        self._update_counterfactual_tab()
        print(f"📱 Updating page...")
        if self.app.page:
            self.app.page.update()
        print(f"✅ Counterfactual tab update completed")
    
    def update_report(self, report_content: str):
        """Update the report and refresh the report tab."""
        print(f"📄 update_report called with report length: {len(report_content) if report_content else 0}")
        self.app.final_report = report_content
        print(f"📝 Stored report content in app.final_report")
        print(f"📄 Calling _update_report_tab...")
        self._update_report_tab()
        print(f"📱 Updating page...")
        if self.app.page:
            self.app.page.update()
        print(f"✅ Report tab update completed")
    
    def update_documents_if_available(self):
        """Update documents tab if data is available in workflow executor."""
        if hasattr(self.app.workflow_executor, 'documents'):
            docs = self.app.workflow_executor.documents
            print(f"📚 Found {len(docs) if docs else 0} documents in workflow_executor")
            if docs:
                print(f"✅ Updating Literature tab with {len(docs)} documents")
                self.update_documents(docs)
            else:
                print(f"❌ No documents to update Literature tab")
        else:
            print(f"❌ workflow_executor has no 'documents' attribute")
    
    def update_scored_documents_if_available(self):
        """Update scored documents tab if data is available."""
        if hasattr(self.app.workflow_executor, 'scored_documents'):
            scored_docs = self.app.workflow_executor.scored_documents
            print(f"📈 Found {len(scored_docs) if scored_docs else 0} scored documents in workflow_executor")
            if scored_docs:
                print(f"✅ Updating Scoring tab with {len(scored_docs)} scored documents")
                self.update_scored_documents(scored_docs)
            else:
                print(f"❌ No scored documents to update Scoring tab")
        else:
            print(f"❌ workflow_executor has no 'scored_documents' attribute")
    
    def update_citations_if_available(self):
        """Update citations tab if data is available."""
        if hasattr(self.app.workflow_executor, 'citations'):
            citations = self.app.workflow_executor.citations
            print(f"📚 Found {len(citations) if citations else 0} citations in workflow_executor")
            if citations:
                print(f"✅ Updating Citations tab with {len(citations)} citations")
                self.update_citations(citations)
            else:
                print(f"❌ No citations to update Citations tab")
        else:
            print(f"❌ workflow_executor has no 'citations' attribute")
    
    def update_counterfactual_if_available(self):
        """Update counterfactual tab if data is available."""
        if hasattr(self.app.workflow_executor, 'counterfactual_analysis'):
            cf_analysis = self.app.workflow_executor.counterfactual_analysis
            print(f"🤖 Found counterfactual analysis: {bool(cf_analysis)}")
            print(f"🔍 Analysis type: {type(cf_analysis)}")
            
            # Debug the contents of the analysis
            if cf_analysis:
                if isinstance(cf_analysis, dict):
                    print(f"📋 Analysis keys: {list(cf_analysis.keys())}")
                    
                    # Check contents of key sections
                    if 'contradictory_evidence' in cf_analysis:
                        evidence = cf_analysis['contradictory_evidence']
                        print(f"🚫 Contradictory evidence count: {len(evidence) if evidence else 0}")
                    
                    if 'contradictory_citations' in cf_analysis:
                        citations = cf_analysis['contradictory_citations']
                        print(f"📖 Contradictory citations count: {len(citations) if citations else 0}")
                    
                    if 'summary' in cf_analysis:
                        summary = cf_analysis['summary']
                        print(f"📊 Summary keys: {list(summary.keys()) if isinstance(summary, dict) else 'Not a dict'}")
                        
                elif hasattr(cf_analysis, '__dict__'):
                    print(f"📋 Analysis attributes: {list(vars(cf_analysis).keys())}")
                else:
                    print(f"📋 Analysis string representation: {str(cf_analysis)[:200]}...")
                    
                print(f"✅ Updating Counterfactual tab with analysis")
                self.update_counterfactual_analysis(cf_analysis)
            else:
                print(f"⚠️ Counterfactual analysis is None/empty - will show debug info")
                # Still call update to show debug info
                self.update_counterfactual_analysis(cf_analysis)
        else:
            print(f"❌ workflow_executor has no 'counterfactual_analysis' attribute")
            # Still try to update to show debug info
            self.update_counterfactual_analysis(None)
    
    def update_report_if_available(self):
        """Update report tab if data is available."""
        if hasattr(self.app.workflow_executor, 'final_report') and self.app.workflow_executor.final_report:
            report = self.app.workflow_executor.final_report
            print(f"📝 Found report with length: {len(report)}")
            print(f"✅ Updating Report tab with final report")
            self.update_report(report)
        else:
            print(f"❌ No final report available in workflow_executor")
    
    def update_all_tabs_if_data_available(self):
        """Update all tabs with available data after workflow completion."""
        print("🔄 Final comprehensive tab update after workflow completion...")
        self.update_documents_if_available()
        self.update_scored_documents_if_available()
        self.update_citations_if_available()
        self.update_counterfactual_if_available()  # This will now always show something
        self.update_report_if_available()
        print("✅ All tab updates completed")
    
    def _update_literature_tab(self):
        """Update the literature tab with found documents."""
        from .display_utils import DocumentCardCreator
        
        print(f"📚 _update_literature_tab called")
        print(f"🔢 Documents count: {len(self.app.documents) if self.app.documents else 0}")
        
        if not self.app.documents:
            print(f"❌ No documents - exiting _update_literature_tab")
            return
        
        # Create document cards
        card_creator = DocumentCardCreator()
        doc_cards = card_creator.create_document_cards_list(self.app.documents, show_score=False)
        
        # Update header
        header_components = create_tab_header(
            "Literature Review",
            count=len(self.app.documents),
            subtitle="All documents found in the search, ordered by search relevance."
        )
        
        all_components = [*header_components, *doc_cards]
        
        # Update the literature tab content
        print(f"📋 Created {len(doc_cards)} document cards")
        if self.app.tab_manager and self.app.tab_manager.get_tab_content('literature'):
            print(f"✅ Updating literature_tab_content with {len(doc_cards)} cards")
            self.app.tab_manager.update_tab_content('literature', ft.Column(
                all_components,
                spacing=10,
                scroll=ft.ScrollMode.AUTO
            ))
            print(f"✅ Literature tab content updated successfully")
        else:
            print(f"❌ literature_tab_content is None - cannot update!")
    
    def _update_scoring_tab(self):
        """Update the scoring tab with scored documents ordered by score."""
        from .display_utils import DocumentCardCreator
        
        if not self.app.scored_documents:
            return
        
        # Sort documents by score (highest first)
        sorted_docs = sorted(self.app.scored_documents, 
                           key=lambda x: x[1].get('score', 0), reverse=True)
        
        # Create document cards
        card_creator = DocumentCardCreator()
        doc_cards = card_creator.create_scored_document_cards_list(sorted_docs)
        
        # Update header
        header_components = create_tab_header(
            "Document Scoring Results",
            count=len(sorted_docs),
            subtitle="Documents ordered by AI relevance score (highest to lowest)."
        )
        
        all_components = [*header_components, *doc_cards]
        
        # Update the scoring tab content
        if self.app.tab_manager and self.app.tab_manager.get_tab_content('scoring'):
            self.app.tab_manager.update_tab_content('scoring', ft.Column(
                all_components,
                spacing=10,
                scroll=ft.ScrollMode.AUTO
            ))
    
    def _update_citations_tab(self):
        """Update the citations tab with extracted citations."""
        from .display_utils import CitationCardCreator
        
        print(f"📝 _update_citations_tab called")
        print(f"🔢 Citations count: {len(self.app.citations) if self.app.citations else 0}")
        
        if not self.app.citations:
            print(f"❌ No citations - exiting _update_citations_tab")
            return
        
        # Sort citations by relevance score (highest first)
        sorted_citations = sorted(self.app.citations, 
                                key=lambda c: getattr(c, 'relevance_score', 0), reverse=True)
        
        # Create citation cards
        card_creator = CitationCardCreator()
        citation_cards = card_creator.create_citation_cards_list(sorted_citations)
        
        # Update header
        header_components = create_tab_header(
            "Extracted Citations",
            count=len(self.app.citations),
            subtitle="Relevant passages extracted from high-scoring documents, ordered by relevance."
        )
        
        all_components = [*header_components, *citation_cards]
        
        # Update the citations tab content
        print(f"📋 Created {len(citation_cards)} citation cards")
        if self.app.tab_manager and self.app.tab_manager.get_tab_content('citations'):
            print(f"✅ Updating citations_tab_content with {len(citation_cards)} cards")
            self.app.tab_manager.update_tab_content('citations', ft.Column(
                all_components,
                spacing=10,
                scroll=ft.ScrollMode.AUTO
            ))
            print(f"✅ Citations tab content updated successfully")
        else:
            print(f"❌ citations_tab_content is None - cannot update!")
    
    def _update_counterfactual_tab(self):
        """Update the counterfactual tab with analysis results."""
        from .display_utils import CounterfactualDisplayCreator
        from .ui_builder import create_tab_header
        
        print(f"🧿 _update_counterfactual_tab called")
        print(f"🤖 Analysis exists: {bool(self.app.counterfactual_analysis)}")
        
        # Always try to update the tab, even if analysis is None
        try:
            if not self.app.counterfactual_analysis:
                print(f"⚠️ No counterfactual analysis - showing debug message")
                
                # Create debug info components
                debug_components = [
                    *create_tab_header(
                        "Counterfactual Analysis Debug",
                        subtitle="Debugging why counterfactual analysis is not displaying"
                    ),
                    ft.Container(
                        content=ft.Column([
                            ft.Text("🔍 Debug Information:", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.ORANGE_700),
                            ft.Text(f"• Analysis data exists: {bool(self.app.counterfactual_analysis)}", size=12),
                            ft.Text(f"• Workflow executor exists: {hasattr(self.app, 'workflow_executor')}", size=12),
                            ft.Text(f"• Workflow executor has analysis attr: {hasattr(self.app.workflow_executor, 'counterfactual_analysis') if hasattr(self.app, 'workflow_executor') else 'N/A'}", size=12),
                            ft.Text(f"• Workflow executor analysis: {bool(getattr(self.app.workflow_executor, 'counterfactual_analysis', None)) if hasattr(self.app, 'workflow_executor') else 'N/A'}", size=12),
                            ft.Text("This debug info will be replaced with actual counterfactual analysis when available.", size=11, color=ft.Colors.GREY_600, italic=True)
                        ], spacing=8),
                        padding=ft.padding.all(15),
                        bgcolor=ft.Colors.ORANGE_50,
                        border_radius=8
                    )
                ]
                
                # Update with debug components
                if self.app.tab_manager and self.app.tab_manager.get_tab_content('counterfactual'):
                    print(f"✅ Updating counterfactual tab with debug info")
                    self.app.tab_manager.update_tab_content('counterfactual', ft.Column(
                        debug_components,
                        spacing=10,
                        scroll=ft.ScrollMode.AUTO
                    ))
                return
            
            # Debug the analysis data
            print(f"🔍 Analysis type in _update_counterfactual_tab: {type(self.app.counterfactual_analysis)}")
            if isinstance(self.app.counterfactual_analysis, dict):
                print(f"📋 Analysis keys in _update_counterfactual_tab: {list(self.app.counterfactual_analysis.keys())}")
            elif hasattr(self.app.counterfactual_analysis, '__dict__'):
                print(f"📋 Analysis attributes in _update_counterfactual_tab: {list(vars(self.app.counterfactual_analysis).keys())}")
            
            # Create counterfactual analysis display
            display_creator = CounterfactualDisplayCreator()
            cf_components = display_creator.create_counterfactual_display(self.app.counterfactual_analysis)
            
            print(f"📋 Created {len(cf_components)} counterfactual analysis display components")
            
            # Update the counterfactual tab content
            if self.app.tab_manager and self.app.tab_manager.get_tab_content('counterfactual'):
                print(f"✅ Updating counterfactual_tab_content with {len(cf_components)} components")
                self.app.tab_manager.update_tab_content('counterfactual', ft.Column(
                    cf_components,
                    spacing=10,
                    scroll=ft.ScrollMode.AUTO
                ))
                print(f"✅ Counterfactual tab content updated successfully")
            else:
                print(f"❌ counterfactual_tab_content is None - cannot update!")
                
        except Exception as e:
            print(f"❌ Error creating counterfactual display: {e}")
            import traceback
            traceback.print_exc()
    
    def _update_report_tab(self):
        """Update the report tab with the final report."""
        print(f"📄 _update_report_tab called")
        print(f"📝 Report exists: {bool(self.app.final_report)}")
        print(f"📊 Report length: {len(self.app.final_report) if self.app.final_report else 0}")
        
        if not self.app.final_report:
            print(f"❌ No report - exiting _update_report_tab")
            return
        
        # Create report components
        report_components = self._create_report_components()
        
        # Update the report tab content
        print(f"📋 Created report display components")
        if self.app.tab_manager and self.app.tab_manager.get_tab_content('report'):
            print(f"✅ Updating report_tab_content with final report")
            self.app.tab_manager.update_tab_content('report', ft.Column(
                report_components,
                spacing=10,
                expand=True
            ))
            print(f"✅ Report tab content updated successfully")
        else:
            print(f"❌ report_tab_content is None - cannot update!")
    
    def _create_report_components(self) -> List[ft.Control]:
        """Create components for the report tab."""
        # Get event handlers
        from .event_handlers import EventHandlers
        handlers = EventHandlers(self.app)
        
        # Create action buttons
        action_buttons = create_action_button_row([
            {
                'text': 'Preview',
                'icon': ft.Icons.PREVIEW,
                'on_click': handlers.on_preview_report
            },
            {
                'text': 'Copy to Clipboard',
                'icon': ft.Icons.COPY,
                'on_click': handlers.on_copy_report
            },
            {
                'text': 'Save Report',
                'icon': ft.Icons.SAVE,
                'on_click': handlers.on_save_report,
                'style': {'bgcolor': ft.Colors.GREEN_600, 'color': ft.Colors.WHITE}
            }
        ])
        
        # Header with title and buttons
        header_row = ft.Row([
            ft.Text(
                f"Research Report ({len(self.app.final_report):,} characters)",
                size=18,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.BLUE_700
            ),
            ft.Container(expand=True),
            action_buttons
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
        
        # Report content display
        report_display = ft.Container(
            content=ft.Column([
                ft.Markdown(
                    value=self.app.final_report,
                    selectable=True,
                    extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                    on_tap_link=handlers.on_report_link_tap,
                    auto_follow_links=False
                )
            ], scroll=ft.ScrollMode.ALWAYS, expand=True),
            bgcolor=ft.Colors.GREY_50,
            border_radius=5,
            padding=ft.padding.all(15),
            expand=True
        )
        
        return [header_row, report_display]