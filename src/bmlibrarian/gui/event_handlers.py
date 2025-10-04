"""
Event Handlers Module for Research GUI

Contains short, focused event handling functions.
"""

import threading
import flet as ft
from typing import TYPE_CHECKING, Optional
from .components import StepCard
from ..cli.workflow_steps import WorkflowStep

if TYPE_CHECKING:
    from .research_app import ResearchGUI


class EventHandlers:
    """Handles UI events for the research GUI."""
    
    def __init__(self, app: 'ResearchGUI'):
        self.app = app
    
    def on_question_change(self, e):
        """Handle research question input change."""
        self.app.research_question = e.control.value.strip()
        self.app.start_button.disabled = not self.app.research_question or self.app.workflow_running
        self._update_status()
        self.app.page.update()
    
    def on_human_loop_toggle_change(self, e):
        """Handle human-in-the-loop toggle change."""
        self.app.human_in_loop = e.control.value
        self._update_status()
        self.app.page.update()
    
    def on_counterfactual_toggle_change(self, e):
        """Handle comprehensive counterfactual analysis toggle change."""
        self.app.comprehensive_counterfactual = e.control.value
        self._update_status()
        self.app.page.update()
    
    def on_max_results_change(self, e):
        """Handle max results input when field loses focus."""
        raw_value = e.control.value.strip()
        
        # If field is empty, set to default
        if not raw_value:
            value = 100
            e.control.value = str(value)
        else:
            try:
                value = int(raw_value)
                
                # Validate range and correct if needed
                if value < 1:
                    value = 1
                    e.control.value = str(value)
                elif value > 1000:
                    value = 1000
                    e.control.value = str(value)
                    
            except ValueError:
                # Reset to current valid value if invalid input
                value = self.app.max_results
                e.control.value = str(value)
        
        # Update internal values
        self.app.max_results = value
        self.app.config_overrides['max_results'] = value
        if hasattr(self.app, 'workflow_executor') and self.app.workflow_executor:
            self.app.workflow_executor.config_overrides['max_results'] = value
        
        # Update UI if field value was corrected
        if e.control.value != raw_value and self.app.page:
            self.app.page.update()
    
    def on_step_expand(self, card: StepCard, expanded: bool):
        """Handle step card expansion change."""
        if self.app.page:
            self.app.page.update()

    def on_add_more_documents(self, e):
        """Fetch additional documents with offset and score only the new ones."""
        if not self.app.workflow_executor or not self.app.documents:
            self.app.dialog_manager.show_error_dialog("No documents to extend")
            return

        # Disable the button during fetch
        if e.control:
            e.control.disabled = True
            e.control.text = "Fetching..."
            self.app.page.update()

        # Run fetch in separate thread to avoid blocking UI
        thread = threading.Thread(target=self._fetch_more_documents_thread, daemon=True)
        thread.start()

    def on_continue_workflow(self, e):
        """Continue workflow from scoring: extract citations (incremental) and regenerate report."""
        if not self.app.scored_documents:
            self.app.dialog_manager.show_error_dialog("No scored documents to process")
            return

        # Run in separate thread
        thread = threading.Thread(target=self._continue_workflow_thread, daemon=True)
        thread.start()

    def on_start_research(self, e):
        """Start the research workflow."""
        if not self.app.research_question or self.app.workflow_running:
            return
        
        if not self.app.agents_initialized:
            self.app.dialog_manager.show_error_dialog(
                "Research agents are not available. Please check your configuration and restart the application."
            )
            return
        
        self.app.workflow_running = True
        self.app.start_button.disabled = True
        self._update_status()
        self.app.page.update()
        
        # Run workflow in separate thread to avoid blocking UI
        thread = threading.Thread(target=self._run_workflow_thread, daemon=True)
        thread.start()
    
    def on_save_report(self, e):
        """Save the final report to a file."""
        print(f"Save button clicked. Report exists: {bool(self.app.final_report)}, Length: {len(self.app.final_report) if self.app.final_report else 0}")
        if self.app.final_report:
            self._show_save_path_dialog()
        else:
            self.app.dialog_manager.show_error_dialog("No report available to save")
    
    def on_copy_report(self, e):
        """Copy the report to clipboard."""
        if self.app.final_report:
            self.app.dialog_manager.copy_to_clipboard(self.app.final_report)
    
    def on_preview_report(self, e):
        """Show report in a preview dialog."""
        print(f"Preview button clicked. Report exists: {bool(self.app.final_report)}, Length: {len(self.app.final_report) if self.app.final_report else 0}")
        if self.app.final_report:
            self._show_preview_overlay()
        else:
            self.app.dialog_manager.show_error_dialog("No report available to preview")
    
    def on_report_link_tap(self, e):
        """Handle links in the report."""
        print(f"Report link tapped: {e.data}")
    
    def on_save_preliminary_report(self, e):
        """Save the preliminary report to a file."""
        print(f"Save preliminary report button clicked. Report exists: {bool(self.app.preliminary_report)}, Length: {len(self.app.preliminary_report) if self.app.preliminary_report else 0}")
        if self.app.preliminary_report:
            self._show_save_preliminary_path_dialog()
        else:
            self.app.dialog_manager.show_error_dialog("No preliminary report available to save")
    
    def on_copy_preliminary_report(self, e):
        """Copy the preliminary report to clipboard."""
        if self.app.preliminary_report:
            self.app.dialog_manager.copy_to_clipboard(self.app.preliminary_report)
    
    def on_preview_preliminary_report(self, e):
        """Show preliminary report in a preview dialog."""
        print(f"Preview preliminary report button clicked. Report exists: {bool(self.app.preliminary_report)}, Length: {len(self.app.preliminary_report) if self.app.preliminary_report else 0}")
        if self.app.preliminary_report:
            self._show_preliminary_preview_overlay()
        else:
            self.app.dialog_manager.show_error_dialog("No preliminary report available to preview")
    
    def _update_status(self):
        """Update the status text."""
        if not self.app.research_question:
            self.app.status_text.value = "Enter a research question to begin"
        elif self.app.workflow_running:
            mode = "Interactive" if self.app.human_in_loop else "Automated"
            cf_mode = " + Comprehensive Counterfactual" if self.app.comprehensive_counterfactual else ""
            self.app.status_text.value = f"Research in progress... ({mode}{cf_mode} mode)"
        else:
            mode = "Interactive" if self.app.human_in_loop else "Automated"
            cf_mode = " + Comprehensive Counterfactual" if self.app.comprehensive_counterfactual else ""
            self.app.status_text.value = f"Ready to start research in {mode}{cf_mode} mode"
    
    def _run_workflow_thread(self):
        """Run the research workflow in a separate thread."""
        try:
            print("Starting workflow execution...")
            
            # Read current values from GUI widgets at the time of execution
            try:
                current_max_results = int(self.app.max_results_field.value.strip()) if self.app.max_results_field.value.strip() else 100
                # Validate range
                if current_max_results < 1:
                    current_max_results = 1
                elif current_max_results > 1000:
                    current_max_results = 1000
            except ValueError:
                current_max_results = 100  # Default fallback
                
            current_human_in_loop = self.app.human_loop_toggle.value
            current_comprehensive_counterfactual = self.app.counterfactual_toggle.value
            
            # Update config overrides with current GUI widget values
            self.app.workflow_executor.config_overrides['comprehensive_counterfactual'] = current_comprehensive_counterfactual
            self.app.workflow_executor.config_overrides['max_results'] = current_max_results
            
            # Also update the app state for consistency
            self.app.max_results = current_max_results
            self.app.human_in_loop = current_human_in_loop
            self.app.comprehensive_counterfactual = current_comprehensive_counterfactual
            
            print(f"🔧 Reading GUI values at execution time:")
            print(f"  - Max results widget: {self.app.max_results_field.value} -> using: {current_max_results}")
            print(f"  - Interactive mode: {current_human_in_loop}")
            print(f"  - Comprehensive counterfactual: {current_comprehensive_counterfactual}")
            
            self.app.final_report = self.app.workflow_executor.run_workflow(
                self.app.research_question,
                current_human_in_loop,
                self._update_step_status,
                self.app.dialog_manager,  # Pass dialog manager for interactive mode
                self.app.step_cards,  # Pass step cards for inline editing
                self.app.tab_manager  # Pass tab manager for scoring interface
            )
            
            print(f"Workflow completed. Final report length: {len(self.app.final_report) if self.app.final_report else 0}")
            
            # Update tabs with final data
            self._update_tabs_after_workflow()
            
        except Exception as ex:
            self._handle_workflow_error(ex)
        finally:
            self.app.workflow_running = False
            self.app.start_button.disabled = not self.app.research_question
            self._update_status()
            if self.app.page:
                self.app.page.update()
    
    def _update_step_status(self, step: WorkflowStep, status: str, content: str = None):
        """Update a step's status and content."""
        if step in self.app.step_cards:
            self.app.step_cards[step].update_status(status, content)
            
            # Update tabs when specific steps complete
            if status in ["completed", "tab_update"]:
                self._handle_step_completion(step)
            
            if self.app.page:
                self.app.page.update()
    
    def _handle_step_completion(self, step: WorkflowStep):
        """Handle specific step completion events for tab updates."""
        from .data_updaters import DataUpdaters
        updaters = DataUpdaters(self.app)
        
        if step == WorkflowStep.SEARCH_DOCUMENTS:
            print(f"🔍 SEARCH_DOCUMENTS completed - checking for documents...")
            updaters.update_documents_if_available()
                    
        elif step == WorkflowStep.SCORE_DOCUMENTS:
            print(f"📊 SCORE_DOCUMENTS completed - checking for scored documents...")
            updaters.update_scored_documents_if_available()
                    
        elif step == WorkflowStep.EXTRACT_CITATIONS:
            print(f"📝 EXTRACT_CITATIONS completed - checking for citations...")
            updaters.update_citations_if_available()
                        
        elif step == WorkflowStep.GENERATE_REPORT:
            print(f"📄 GENERATE_REPORT completed - checking for preliminary report...")
            updaters.update_preliminary_report_if_available()
                        
        elif step == WorkflowStep.PERFORM_COUNTERFACTUAL_ANALYSIS:
            print(f"🧿 PERFORM_COUNTERFACTUAL_ANALYSIS completed - checking for counterfactual analysis...")
            updaters.update_counterfactual_if_available()
                    
        elif step == WorkflowStep.EXPORT_REPORT:
            print(f"📄 EXPORT_REPORT completed - checking for final report...")
            updaters.update_report_if_available()
    
    def _update_tabs_after_workflow(self):
        """Update all tabs with final workflow data."""
        from .data_updaters import DataUpdaters
        updaters = DataUpdaters(self.app)
        
        print("🔍 Final tab update check after workflow completion...")
        updaters.update_all_tabs_if_data_available()
    
    def _handle_workflow_error(self, error: Exception):
        """Handle workflow execution errors."""
        error_msg = f"Research workflow failed: {str(error)}"
        print(f"Workflow error: {error}")
        
        if self.app.page:
            self.app.dialog_manager.show_error_dialog(error_msg)
    
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
                import json
                
                # Expand user path and ensure .md extension
                expanded_path = os.path.expanduser(file_path.strip())
                if not expanded_path.endswith('.md'):
                    expanded_path += '.md'
                
                # Create directory if needed
                os.makedirs(os.path.dirname(expanded_path), exist_ok=True)
                
                # Save the markdown report
                with open(expanded_path, 'w', encoding='utf-8') as f:
                    f.write(self.app.final_report)
                
                # Generate JSON filename (replace .md with .json)
                json_path = expanded_path.replace('.md', '.json')
                
                # Get comprehensive workflow data
                try:
                    comprehensive_data = self.app.workflow_executor.export_comprehensive_data(
                        research_question=self.app.research_question,
                        query_text=getattr(self.app.workflow_executor, 'last_query_text', None)
                    )
                    
                    # Save the comprehensive JSON data
                    with open(json_path, 'w', encoding='utf-8') as f:
                        json.dump(comprehensive_data, f, indent=2, ensure_ascii=False)
                    
                    success_message = f"Files saved successfully:\n• Report: {expanded_path}\n• Data: {json_path}"
                    print(f"Report saved to: {expanded_path}")
                    print(f"Comprehensive data saved to: {json_path}")
                    
                except Exception as json_error:
                    print(f"JSON export error: {json_error}")
                    success_message = f"Report saved to: {expanded_path}\n\nWarning: Could not save comprehensive data file: {str(json_error)}"
                
                self.app.dialog_manager.show_success_dialog(success_message)
                
            except Exception as ex:
                self.app.dialog_manager.show_error_dialog(f"Failed to save report: {str(ex)}")
                print(f"Save error: {ex}")
        
        def close_save_dialog(e):
            self.app.page.overlay.clear()
            self.app.page.update()
        
        def handle_save(e):
            file_path = path_input.value.strip()
            if file_path:
                close_save_dialog(e)
                save_file(file_path)
            else:
                self.app.dialog_manager.show_error_dialog("Please enter a file path")
        
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
                ft.Text("📄 Two files will be saved:", size=12, weight=ft.FontWeight.W_500, color=ft.Colors.BLUE_700),
                ft.Text("• [filename].md - Formatted research report", size=11, color=ft.Colors.GREY_700),
                ft.Text("• [filename].json - Complete workflow data for reconstruction", size=11, color=ft.Colors.GREY_700),
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
        self.app.page.overlay.clear()
        self.app.page.overlay.append(
            ft.Container(
                content=save_dialog,
                alignment=ft.alignment.center,
                bgcolor=ft.Colors.with_opacity(0.5, ft.Colors.BLACK)
            )
        )
        
        self.app.page.update()
        print("Save path dialog created and displayed")
    
    def _show_preview_overlay(self):
        """Show report in a preview overlay."""
        try:
            def close_preview(e):
                self.app.page.overlay.clear()
                self.app.page.update()
            
            # Create preview content using overlay
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
                                value=self.app.final_report,
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
            self.app.page.overlay.clear()
            self.app.page.overlay.append(
                ft.Container(
                    content=preview_content,
                    alignment=ft.alignment.center,
                    bgcolor=ft.Colors.with_opacity(0.5, ft.Colors.BLACK)
                )
            )
            
            self.app.page.update()
            print("Preview overlay created and displayed")
            
        except Exception as ex:
            print(f"Preview error: {ex}")
            # Fallback to dialog
            self.app.dialog_manager.show_preview_dialog(self.app.final_report)
    
    def _show_save_preliminary_path_dialog(self):
        """Show custom save path dialog for preliminary report."""
        import os
        from datetime import datetime
        
        # Generate default path
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        default_filename = f"preliminary_report_{timestamp}.md"
        default_path = os.path.join(os.path.expanduser("~/Desktop"), default_filename)
        
        def save_file(file_path):
            try:
                # Expand user path and ensure .md extension
                expanded_path = os.path.expanduser(file_path.strip())
                if not expanded_path.endswith('.md'):
                    expanded_path += '.md'
                
                # Create directory if needed
                os.makedirs(os.path.dirname(expanded_path), exist_ok=True)
                
                # Save the markdown report
                with open(expanded_path, 'w', encoding='utf-8') as f:
                    f.write(self.app.preliminary_report)
                
                success_message = f"Preliminary report saved to: {expanded_path}"
                print(f"Preliminary report saved to: {expanded_path}")
                self.app.dialog_manager.show_success_dialog(success_message)
                
            except Exception as ex:
                self.app.dialog_manager.show_error_dialog(f"Failed to save preliminary report: {str(ex)}")
                print(f"Save error: {ex}")
        
        def close_save_dialog(e):
            self.app.page.overlay.clear()
            self.app.page.update()
        
        def handle_save(e):
            file_path = path_input.value.strip()
            if file_path:
                close_save_dialog(e)
                save_file(file_path)
            else:
                self.app.dialog_manager.show_error_dialog("Please enter a file path")
        
        # Create path input
        path_input = ft.TextField(
            label="Save preliminary report to:",
            value=default_path,
            width=500,
            hint_text="Enter full file path (e.g., ~/Desktop/my_preliminary_report.md)"
        )
        
        # Create save dialog overlay
        save_dialog = ft.Container(
            content=ft.Column([
                ft.Text("Save Preliminary Report", size=18, weight=ft.FontWeight.BOLD),
                ft.Text("Enter the path where you want to save the preliminary report:", size=12),
                ft.Text("📄 This is the report before counterfactual analysis.", size=11, color=ft.Colors.GREY_700),
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
        self.app.page.overlay.clear()
        self.app.page.overlay.append(
            ft.Container(
                content=save_dialog,
                alignment=ft.alignment.center,
                bgcolor=ft.Colors.with_opacity(0.5, ft.Colors.BLACK)
            )
        )
        
        self.app.page.update()
        print("Preliminary report save path dialog created and displayed")
    
    def _show_preliminary_preview_overlay(self):
        """Show preliminary report in a preview overlay."""
        try:
            def close_preview(e):
                self.app.page.overlay.clear()
                self.app.page.update()
            
            # Create preview content using overlay
            preview_content = ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Text("Preliminary Report Preview", size=18, weight=ft.FontWeight.BOLD),
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
                                value=self.app.preliminary_report,
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
            self.app.page.overlay.clear()
            self.app.page.overlay.append(
                ft.Container(
                    content=preview_content,
                    alignment=ft.alignment.center,
                    bgcolor=ft.Colors.with_opacity(0.5, ft.Colors.BLACK)
                )
            )
            
            self.app.page.update()
            print("Preliminary report preview overlay created and displayed")
            
        except Exception as ex:
            print(f"Preliminary report preview error: {ex}")
            # Fallback to dialog
            self.app.dialog_manager.show_preview_dialog(self.app.preliminary_report)

    def _fetch_more_documents_thread(self):
        """Fetch additional documents with offset and score only the new ones."""
        try:
            from ..config import get_search_config

            # Get current offset (number of documents already fetched)
            offset = len(self.app.documents)

            # Get max_results - use the same value that was used for the initial search
            # Priority: workflow_executor config > app config > search config
            max_results = None
            if hasattr(self.app.workflow_executor, 'config_overrides'):
                max_results = self.app.workflow_executor.config_overrides.get('max_results')
            if max_results is None and hasattr(self.app, 'config_overrides'):
                max_results = self.app.config_overrides.get('max_results')
            if max_results is None:
                search_config = get_search_config()
                max_results = search_config.get('max_results', 100)

            print(f"🔄 Fetching more documents: offset={offset}, max_results={max_results}")
            print(f"   Sources: workflow_executor.config_overrides={getattr(self.app.workflow_executor, 'config_overrides', {})}")
            print(f"   Sources: app.config_overrides={getattr(self.app, 'config_overrides', {})}")

            # Get the last query used (stored in workflow_executor)
            if not hasattr(self.app.workflow_executor, 'last_query_text') or not self.app.workflow_executor.last_query_text:
                self.app.dialog_manager.show_error_dialog("Cannot fetch more documents: no previous query found")
                # Refresh scoring tab to reset button
                self.app.data_updaters.update_scored_documents(self.app.scored_documents)
                return

            query_text = self.app.workflow_executor.last_query_text

            # Fetch additional documents using the QueryAgent with offset
            query_agent = self.app.agents['query_agent']

            documents_generator = query_agent.find_abstracts(
                question=self.app.research_question,
                max_rows=max_results,
                human_in_the_loop=False,  # No interaction for additional fetches
                human_query_modifier=None,
                offset=offset
            )

            # Convert generator to list
            new_documents = list(documents_generator)

            print(f"✅ Fetched {len(new_documents)} additional documents")

            if not new_documents:
                self.app.dialog_manager.show_info_dialog(
                    "No more documents found in the database.\n\n"
                    f"Total documents retrieved: {len(self.app.documents)}"
                )
                # Refresh scoring tab to remove the button since there are no more documents
                self.app.data_updaters.update_scored_documents(self.app.scored_documents)
                return

            # Deduplicate: Filter out documents that are already in our list
            existing_ids = {doc.get('id') for doc in self.app.documents if doc.get('id')}
            deduplicated_docs = [doc for doc in new_documents if doc.get('id') not in existing_ids]

            duplicates_found = len(new_documents) - len(deduplicated_docs)
            if duplicates_found > 0:
                print(f"⚠️ Filtered out {duplicates_found} duplicate document(s)")

            if not deduplicated_docs:
                self.app.dialog_manager.show_info_dialog(
                    "All fetched documents were duplicates.\n\n"
                    f"Total unique documents: {len(self.app.documents)}"
                )
                # Refresh scoring tab
                self.app.data_updaters.update_scored_documents(self.app.scored_documents)
                return

            # Store the original number of documents to identify which are new
            original_doc_count = len(self.app.documents)

            # Add only deduplicated documents to the existing list
            self.app.documents.extend(deduplicated_docs)
            self.app.workflow_executor.documents = self.app.documents

            # Update new_documents to only include deduplicated ones for scoring
            new_documents = deduplicated_docs

            # Update literature tab
            self.app.data_updaters.update_documents(self.app.documents)

            # Score ONLY the new documents
            print(f"📊 Scoring {len(new_documents)} new documents...")

            scoring_agent = self.app.agents['scoring_agent']
            new_scored_docs = []

            for idx, doc in enumerate(new_documents):
                print(f"  Scoring document {idx + 1}/{len(new_documents)}: {doc.get('title', 'Untitled')[:50]}...")
                score_data = scoring_agent.evaluate_document(
                    user_question=self.app.research_question,
                    document=doc
                )
                new_scored_docs.append((doc, score_data))

            # Merge new scored documents with existing ones
            self.app.scored_documents.extend(new_scored_docs)
            self.app.workflow_executor.scored_documents = self.app.scored_documents

            # Update scoring tab (which will show the button again if we hit the limit)
            self.app.data_updaters.update_scored_documents(self.app.scored_documents)

            print(f"✅ Successfully added and scored {len(new_documents)} new documents")

            # Show success message
            self.app.dialog_manager.show_info_dialog(
                f"Successfully fetched and scored {len(new_documents)} additional documents.\n\n"
                f"Total documents: {len(self.app.documents)}\n"
                f"Total scored: {len(self.app.scored_documents)}"
            )

        except Exception as ex:
            print(f"❌ Error fetching more documents: {ex}")
            import traceback
            traceback.print_exc()
            self.app.dialog_manager.show_error_dialog(f"Error fetching more documents: {str(ex)}")
        finally:
            # Re-enable UI
            if self.app.page:
                self.app.page.update()
    def _continue_workflow_thread(self):
        """Continue workflow: incremental citation extraction + full report regeneration."""
        try:
            from ..config import get_search_config

            print("🔄 Continuing workflow from scoring...")

            # Get configuration
            search_config = get_search_config()
            score_threshold = search_config.get('score_threshold', 2.5)

            # Determine which documents need citations extracted
            # Check if we have existing citations to know which docs were already processed
            existing_citation_doc_ids = set()
            if self.app.citations:
                for citation in self.app.citations:
                    if hasattr(citation, 'document_id'):
                        existing_citation_doc_ids.add(citation.document_id)
                    elif hasattr(citation, 'doc_id'):
                        existing_citation_doc_ids.add(citation.doc_id)

            # Find high-scoring documents that need citation extraction
            docs_needing_citations = []
            for doc, score_data in self.app.scored_documents:
                if score_data.get('score', 0) > score_threshold:
                    doc_id = doc.get('id')
                    if doc_id not in existing_citation_doc_ids:
                        docs_needing_citations.append((doc, score_data))

            print(f"📚 Documents needing citation extraction: {len(docs_needing_citations)}")
            print(f"📖 Existing citations: {len(self.app.citations)}")

            # Extract citations ONLY from new documents
            if docs_needing_citations:
                print(f"🔍 Extracting citations from {len(docs_needing_citations)} new high-scoring documents...")

                citation_agent = self.app.agents['citation_agent']
                new_citations = citation_agent.process_scored_documents_for_citations(
                    user_question=self.app.research_question,
                    scored_documents=docs_needing_citations,
                    score_threshold=score_threshold
                )

                # Merge with existing citations
                self.app.citations.extend(new_citations)
                self.app.workflow_executor.citations = self.app.citations

                print(f"✅ Extracted {len(new_citations)} new citations")
                print(f"📚 Total citations: {len(self.app.citations)}")

                # Update citations tab
                self.app.data_updaters.update_citations(self.app.citations)
            else:
                print("✅ No new documents need citation extraction")

            # Regenerate FULL report with all citations
            print(f"📝 Regenerating report with {len(self.app.citations)} total citations...")

            reporting_agent = self.app.agents['reporting_agent']

            # Get Report object (not formatted string) for EditorAgent
            report_object = reporting_agent.generate_citation_based_report(
                user_question=self.app.research_question,
                citations=self.app.citations,
                format_output=False  # Get Report object, not formatted string
            )

            # Also get formatted string for display
            new_report_formatted = reporting_agent.generate_citation_based_report(
                user_question=self.app.research_question,
                citations=self.app.citations,
                format_output=True  # Get formatted string for display
            )

            # Store formatted version as preliminary report for display
            self.app.preliminary_report = new_report_formatted
            self.app.workflow_executor.preliminary_report = new_report_formatted

            # Update preliminary report tab
            self.app.data_updaters.update_preliminary_report(new_report_formatted)

            print(f"✅ Report regenerated successfully")

            # Continue to counterfactual analysis if enabled
            if self.app.comprehensive_counterfactual:
                print(f"🧠 Performing comprehensive counterfactual analysis with literature search...")

                # Use the workflow executor's steps handler for comprehensive counterfactual
                from ..cli.workflow_steps import WorkflowStep

                # Use the steps_handler to perform comprehensive counterfactual analysis
                # This includes: analyzing report → generating questions → searching literature → finding contradictions
                def dummy_callback(step, status, message):
                    print(f"  [{step.name}] {status}: {message}")

                counterfactual_analysis = self.app.workflow_executor.steps_handler.execute_comprehensive_counterfactual_analysis(
                    new_report_formatted,
                    self.app.citations,
                    dummy_callback
                )

                # Store counterfactual analysis
                self.app.counterfactual_analysis = counterfactual_analysis
                self.app.workflow_executor.counterfactual_analysis = counterfactual_analysis

                # Update counterfactual tab
                self.app.data_updaters.update_counterfactual_if_available()

                print(f"🔬 Counterfactual analysis completed and displayed in tab")

                # Convert CounterfactualAnalysis object to dict for editor agent
                # The editor agent expects a dict with 'contradictory_citations' key
                if counterfactual_analysis:
                    if hasattr(counterfactual_analysis, 'to_dict'):
                        contradictory_dict = counterfactual_analysis.to_dict()
                    elif hasattr(counterfactual_analysis, '__dict__'):
                        contradictory_dict = counterfactual_analysis.__dict__
                    else:
                        contradictory_dict = {'analysis': str(counterfactual_analysis)}
                else:
                    contradictory_dict = None

                # Generate final comprehensive report with editor agent
                print(f"📝 Generating comprehensive final report...")

                editor_agent = self.app.agents['editor_agent']
                final_report = editor_agent.create_comprehensive_report(
                    original_report=report_object,  # Pass Report object, not formatted string
                    research_question=self.app.research_question,
                    supporting_citations=self.app.citations,
                    contradictory_evidence=contradictory_dict
                )

                # Check if editor agent succeeded, otherwise use preliminary report
                if final_report and (hasattr(final_report, 'content') or isinstance(final_report, str)):
                    # Extract content from EditedReport object if needed
                    if hasattr(final_report, 'content'):
                        final_report_content = final_report.content
                    else:
                        final_report_content = final_report

                    # Store and update final report
                    self.app.final_report = final_report_content
                    self.app.workflow_executor.final_report = final_report_content
                    self.app.data_updaters.update_report(final_report_content)
                    print(f"✅ Comprehensive final report generated ({len(final_report_content)} chars)")
                else:
                    # Fallback: use preliminary report as final report
                    print(f"⚠️ Editor agent failed, using preliminary report as final report")
                    self.app.final_report = new_report_formatted
                    self.app.workflow_executor.final_report = new_report_formatted
                    self.app.data_updaters.update_report(new_report_formatted)

                # Show success dialog
                self.app.dialog_manager.show_info_dialog(
                    f"Workflow completed successfully!\n\n"
                    f"New citations extracted: {len(new_citations) if docs_needing_citations else 0}\n"
                    f"Total citations: {len(self.app.citations)}\n"
                    f"Preliminary report regenerated\n"
                    f"Counterfactual analysis performed\n"
                    f"Final comprehensive report generated"
                )
            else:
                # No counterfactual - preliminary report is final
                self.app.final_report = new_report_formatted
                self.app.workflow_executor.final_report = new_report_formatted
                self.app.data_updaters.update_report(new_report_formatted)

                # Show success dialog
                self.app.dialog_manager.show_info_dialog(
                    f"Workflow continued successfully!\n\n"
                    f"New citations extracted: {len(new_citations) if docs_needing_citations else 0}\n"
                    f"Total citations: {len(self.app.citations)}\n"
                    f"Report regenerated with all evidence"
                )

        except Exception as ex:
            print(f"❌ Error continuing workflow: {ex}")
            import traceback
            traceback.print_exc()
            self.app.dialog_manager.show_error_dialog(f"Error continuing workflow: {str(ex)}")
        finally:
            if self.app.page:
                self.app.page.update()
