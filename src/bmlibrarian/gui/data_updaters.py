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
        
        # Debug current tab state before update
        if self.app.tab_manager:
            current_content = self.app.tab_manager.get_tab_content('counterfactual')
            if current_content:
                print(f"🔍 Current counterfactual tab content type: {type(current_content.content)}")
                if hasattr(current_content.content, 'controls'):
                    print(f"🔍 Current tab has {len(current_content.content.controls)} controls")
            else:
                print(f"❌ No counterfactual tab content found")
        
        print(f"📄 Calling _update_counterfactual_tab...")
        self._update_counterfactual_tab()
        print(f"📱 Updating page...")
        if self.app.page:
            self.app.page.update()
        print(f"✅ Counterfactual tab update completed")
    
    def update_preliminary_report(self, report_content: str):
        """Update the preliminary report and refresh the preliminary report tab."""
        print(f"📄 update_preliminary_report called with report length: {len(report_content) if report_content else 0}")
        self.app.preliminary_report = report_content
        print(f"📝 Stored preliminary report content in app.preliminary_report")
        print(f"📄 Calling _update_preliminary_report_tab...")
        self._update_preliminary_report_tab()
        print(f"📱 Updating page...")
        if self.app.page:
            self.app.page.update()
        print(f"✅ Preliminary report tab update completed")
    
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
    
    def update_preliminary_report_if_available(self):
        """Update preliminary report tab if data is available."""
        if hasattr(self.app.workflow_executor, 'preliminary_report') and self.app.workflow_executor.preliminary_report:
            report = self.app.workflow_executor.preliminary_report
            print(f"📝 Found preliminary report with length: {len(report)}")
            print(f"✅ Updating Preliminary Report tab with preliminary report")
            self.update_preliminary_report(report)
        else:
            print(f"❌ No preliminary report available in workflow_executor")
    
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
        self.update_preliminary_report_if_available()
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
        from ..config import get_search_config
        import flet as ft

        if not self.app.scored_documents:
            return

        # Get score threshold from configuration
        search_config = get_search_config()
        score_threshold = search_config.get('score_threshold', 2.5)

        # Sort documents by score (highest first)
        sorted_docs = sorted(self.app.scored_documents,
                           key=lambda x: x[1].get('score', 0), reverse=True)

        # Separate into high-scoring and low-scoring
        high_scoring_docs = [(doc, score) for doc, score in sorted_docs if score.get('score', 0) > score_threshold]
        low_scoring_docs = [(doc, score) for doc, score in sorted_docs if score.get('score', 0) <= score_threshold]

        # Create document cards with edit functionality
        card_creator = DocumentCardCreator()

        # Build components list
        all_components = []

        # Main header
        header_components = create_tab_header(
            "Document Scoring Results",
            count=len(sorted_docs),
            subtitle=f"All {len(sorted_docs)} documents with AI relevance scores. Threshold: {score_threshold}"
        )
        all_components.extend(header_components)

        # Add "Add More Documents" button if we hit the max_results limit
        print(f"🔍 Checking if 'Add More Documents' button should be shown...")
        print(f"  - workflow_executor exists: {self.app.workflow_executor is not None}")
        print(f"  - documents count: {len(self.app.documents) if self.app.documents else 0}")

        if self.app.workflow_executor and self.app.documents:
            # Check if the number of found documents equals max_results (indicating there may be more)
            from ..config import get_search_config
            search_config = get_search_config()

            # Get max_results from multiple sources (in priority order)
            max_results = None
            if hasattr(self.app, 'config_overrides') and self.app.config_overrides:
                max_results = self.app.config_overrides.get('max_results')
            if max_results is None and hasattr(self.app.workflow_executor, 'config_overrides'):
                max_results = self.app.workflow_executor.config_overrides.get('max_results')
            if max_results is None:
                max_results = search_config.get('max_results', 100)

            print(f"  - max_results: {max_results}")
            print(f"  - Should show button: {len(self.app.documents) >= max_results}")
            print(f"  - event_handlers exists: {hasattr(self.app, 'event_handlers')}")
            print(f"  - human_in_loop: {getattr(self.app, 'human_in_loop', 'N/A')}")

            # Only show button in interactive mode and if we hit the limit
            if len(self.app.documents) >= max_results:
                print(f"✅ Adding 'Add More Documents' button!")
                add_more_button = ft.ElevatedButton(
                    text=f"Add More Documents (fetch next {max_results})",
                    icon=ft.Icons.ADD_CIRCLE,
                    on_click=self.app.event_handlers.on_add_more_documents if hasattr(self.app, 'event_handlers') else None,
                    bgcolor=ft.Colors.BLUE_600,
                    color=ft.Colors.WHITE
                )
                all_components.append(ft.Container(
                    content=add_more_button,
                    padding=ft.padding.only(top=10, bottom=10)
                ))
            else:
                print(f"❌ Not adding button - document count ({len(self.app.documents)}) < max_results ({max_results})")

        # Add Continue Workflow button (for extracting citations and generating report)
        if self.app.scored_documents:
            continue_button = ft.ElevatedButton(
                text="Continue Workflow (Extract Citations & Generate Report)",
                icon=ft.Icons.ARROW_FORWARD,
                on_click=self.app.event_handlers.on_continue_workflow if hasattr(self.app, 'event_handlers') else None,
                bgcolor=ft.Colors.GREEN_600,
                color=ft.Colors.WHITE
            )
            all_components.append(ft.Container(
                content=continue_button,
                padding=ft.padding.only(top=10, bottom=15)
            ))

        # High-scoring documents section
        if high_scoring_docs:
            all_components.append(ft.Container(
                content=ft.Text(
                    f"🎯 HIGH-SCORING DOCUMENTS (Above threshold {score_threshold}): {len(high_scoring_docs)}",
                    size=16,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.GREEN_700
                ),
                padding=ft.padding.only(top=15, bottom=10)
            ))
            # Create editable scoring cards
            high_scoring_cards = self._create_editable_scoring_cards(high_scoring_docs, 0)
            all_components.extend(high_scoring_cards)

        # Low-scoring documents section
        if low_scoring_docs:
            all_components.append(ft.Container(
                content=ft.Text(
                    f"📉 LOW-SCORING DOCUMENTS (At or below threshold {score_threshold}): {len(low_scoring_docs)}",
                    size=16,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.ORANGE_700
                ),
                padding=ft.padding.only(top=20, bottom=10)
            ))
            # Create editable scoring cards
            low_scoring_cards = self._create_editable_scoring_cards(low_scoring_docs, len(high_scoring_docs))
            all_components.extend(low_scoring_cards)

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
                
                # Create new column with components
                new_content = ft.Column(
                    cf_components,
                    spacing=10,
                    scroll=ft.ScrollMode.AUTO
                )
                
                # Update the tab content
                self.app.tab_manager.update_tab_content('counterfactual', new_content)
                
                # Verify the update worked
                updated_content = self.app.tab_manager.get_tab_content('counterfactual')
                if updated_content and hasattr(updated_content.content, 'controls'):
                    print(f"🔍 After update: tab has {len(updated_content.content.controls)} controls")
                    if updated_content.content.controls:
                        first_control = updated_content.content.controls[0]
                        print(f"🔍 First control type: {type(first_control)}")
                else:
                    print(f"❌ Update verification failed - no controls found")
                
                # Force page update to ensure UI reflects changes
                if self.app.page:
                    print("🔄 Forcing page update after counterfactual tab update")
                    self.app.page.update()
                
                print(f"✅ Counterfactual tab content updated successfully with {len(cf_components)} components")
            else:
                print(f"❌ counterfactual_tab_content is None - cannot update!")
                # Try to check what's in tab_manager
                if self.app.tab_manager:
                    print(f"🔍 Tab manager exists, available tabs: {list(self.app.tab_manager.tab_contents.keys())}")
                else:
                    print(f"❌ No tab manager found!")
                
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
    
    def _update_preliminary_report_tab(self):
        """Update the preliminary report tab with the preliminary report."""
        print(f"📄 _update_preliminary_report_tab called")
        print(f"📝 Preliminary report exists: {bool(self.app.preliminary_report)}")
        print(f"📊 Preliminary report length: {len(self.app.preliminary_report) if self.app.preliminary_report else 0}")
        
        if not self.app.preliminary_report:
            print(f"❌ No preliminary report - exiting _update_preliminary_report_tab")
            return
        
        # Create preliminary report components
        preliminary_report_components = self._create_preliminary_report_components()
        
        # Update the preliminary report tab content
        print(f"📋 Created preliminary report display components")
        if self.app.tab_manager and self.app.tab_manager.get_tab_content('preliminary_report'):
            print(f"✅ Updating preliminary_report_tab_content with preliminary report")
            self.app.tab_manager.update_tab_content('preliminary_report', ft.Column(
                preliminary_report_components,
                spacing=10,
                expand=True
            ))
            print(f"✅ Preliminary report tab content updated successfully")
        else:
            print(f"❌ preliminary_report_tab_content is None - cannot update!")
    
    def _create_preliminary_report_components(self) -> List[ft.Control]:
        """Create components for the preliminary report tab."""
        # Get event handlers
        from .event_handlers import EventHandlers
        handlers = EventHandlers(self.app)
        
        # Create action buttons
        action_buttons = create_action_button_row([
            {
                'text': 'Preview',
                'icon': ft.Icons.PREVIEW,
                'on_click': lambda e: handlers.on_preview_preliminary_report(e)
            },
            {
                'text': 'Copy to Clipboard',
                'icon': ft.Icons.COPY,
                'on_click': lambda e: handlers.on_copy_preliminary_report(e)
            },
            {
                'text': 'Save Report',
                'icon': ft.Icons.SAVE,
                'on_click': lambda e: handlers.on_save_preliminary_report(e),
                'style': {'bgcolor': ft.Colors.BLUE_600, 'color': ft.Colors.WHITE}
            }
        ])
        
        # Header with title and buttons
        header_row = ft.Row([
            ft.Text(
                f"Preliminary Report ({len(self.app.preliminary_report):,} characters)",
                size=18,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.BLUE_700
            ),
            ft.Container(expand=True),
            action_buttons
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
        
        # Preliminary report content display
        report_display = ft.Container(
            content=ft.Column([
                ft.Markdown(
                    value=self.app.preliminary_report,
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
    def _create_editable_scoring_cards(self, scored_docs: List[tuple], start_index: int) -> List[ft.Control]:
        """Create editable scoring cards for documents."""
        cards = []

        for i, (doc, score_data) in enumerate(scored_docs):
            global_index = start_index + i
            card = self._create_single_editable_scoring_card(global_index, doc, score_data)
            cards.append(card)

        return cards

    def _create_single_editable_scoring_card(self, index: int, doc: dict, score_data: dict) -> ft.Container:
        """Create a single editable scoring card."""
        import flet as ft
        from .display_utils import truncate_text, extract_year_from_date

        doc_id = doc.get('id')
        title = doc.get('title', 'Untitled Document')
        abstract = doc.get('abstract', 'No abstract available')  # Show full abstract, no truncation
        ai_score = score_data.get('score', 0)
        reasoning = score_data.get('reasoning', 'No reasoning provided')
        is_human_edited = score_data.get('human_edited', False)
        human_score = score_data.get('human_score', None)

        # Display score (human or AI)
        display_score = human_score if human_score is not None else ai_score
        score_source = "👤 Human" if is_human_edited else "🤖 AI"

        # Year extraction
        publication_date = doc.get('publication_date', None)
        if publication_date and str(publication_date).strip():
            year = extract_year_from_date(str(publication_date).strip())
        else:
            year = doc.get('year', 'Unknown')

        # Score edit input
        score_input = ft.TextField(
            label="Edit score (1-5)",
            value=str(display_score),
            width=120,
            text_size=12,
            on_change=lambda e, idx=index, did=doc_id: self._on_score_edit(idx, did, e.control.value)
        )

        # Reset button (visible only if human edited)
        reset_button = ft.IconButton(
            icon=ft.Icons.REFRESH,
            tooltip="Reset to AI score",
            visible=is_human_edited,
            on_click=lambda e, idx=index, did=doc_id: self._on_score_reset(idx, did)
        )

        # Build card
        return ft.Container(
            content=ft.Column([
                # Header row
                ft.Row([
                    ft.Text(f"#{index + 1}: {title}",  # Full title, no truncation
                           size=13, weight=ft.FontWeight.BOLD, expand=True),
                    ft.Container(
                        content=ft.Text(f"{score_source}: {display_score}/5",
                                       size=12, weight=ft.FontWeight.BOLD,
                                       color=ft.Colors.GREEN_700 if is_human_edited else ft.Colors.BLUE_700),
                        bgcolor=ft.Colors.GREEN_50 if is_human_edited else ft.Colors.BLUE_50,
                        padding=ft.padding.all(5),
                        border_radius=5
                    )
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),

                # Metadata
                ft.Text(f"{doc.get('publication', 'Unknown')} • {year}",
                       size=11, color=ft.Colors.GREY_600),

                # Full Abstract (scrollable if long)
                ft.Container(
                    content=ft.Column([
                        ft.Text("Abstract:", size=11, weight=ft.FontWeight.BOLD),
                        ft.Text(abstract, size=11, color=ft.Colors.GREY_700, selectable=True)
                    ], spacing=3),
                    padding=ft.padding.all(8),
                    bgcolor=ft.Colors.GREY_100,
                    border_radius=5
                ),

                # Reasoning
                ft.Container(
                    content=ft.Column([
                        ft.Text("AI Reasoning:", size=11, weight=ft.FontWeight.BOLD),
                        ft.Text(reasoning, size=11, color=ft.Colors.GREY_600)
                    ], spacing=3),
                    padding=ft.padding.all(8),
                    bgcolor=ft.Colors.BLUE_50,
                    border_radius=5
                ),

                # Edit controls
                ft.Row([
                    score_input,
                    reset_button,
                    ft.Text(f"(AI: {ai_score})" if is_human_edited else "",
                           size=11, color=ft.Colors.GREY_500)
                ], spacing=10)
            ], spacing=8),
            padding=ft.padding.all(12),
            bgcolor=ft.Colors.GREY_50,
            border=ft.border.all(1, ft.Colors.GREY_300),
            border_radius=8
        )

    def _on_score_edit(self, index: int, doc_id: int, value: str):
        """Handle score edit."""
        try:
            score = float(value.strip())
            if 1 <= score <= 5:
                # Find the document in scored_documents and update it
                for i, (doc, score_data) in enumerate(self.app.scored_documents):
                    if doc.get('id') == doc_id:
                        # Store original AI score if not already stored
                        if 'original_ai_score' not in score_data:
                            score_data['original_ai_score'] = score_data.get('score', 0)

                        # Update with human edit
                        score_data['human_score'] = score
                        score_data['human_edited'] = True
                        score_data['score'] = score  # Update display score
                        print(f"✏️ Human edited score for doc {doc_id}: {score}")

                        # Update the scored_documents list
                        self.app.scored_documents[i] = (doc, score_data)

                        # Refresh the scoring tab to show changes
                        self._update_scoring_tab()
                        if self.app.page:
                            self.app.page.update()
                        break
        except ValueError:
            pass  # Invalid input, ignore

    def _on_score_reset(self, index: int, doc_id: int):
        """Reset score to AI original."""
        # Find the document and reset to AI score
        for i, (doc, score_data) in enumerate(self.app.scored_documents):
            if doc.get('id') == doc_id:
                # Get original AI score
                ai_score = score_data.get('original_ai_score', score_data.get('score', 0))

                # Reset to AI score
                score_data['score'] = ai_score
                score_data['human_edited'] = False
                if 'human_score' in score_data:
                    del score_data['human_score']

                print(f"🔄 Reset score for doc {doc_id} to AI score: {ai_score}")

                # Update the scored_documents list
                self.app.scored_documents[i] = (doc, score_data)

                # Refresh the scoring tab
                self._update_scoring_tab()
                if self.app.page:
                    self.app.page.update()
                break
