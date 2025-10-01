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
                self.app.step_cards  # Pass step cards for inline editing
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