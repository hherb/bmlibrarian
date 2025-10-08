"""
Event Handlers Module for Research GUI

Contains short, focused event handling functions.
"""

import threading
import os
from datetime import datetime
import flet as ft
from typing import TYPE_CHECKING, Optional, Callable, Any
from .components import StepCard
from ..cli.workflow_steps import WorkflowStep

if TYPE_CHECKING:
    from .research_app import ResearchGUI


class EventHandlers:
    """Handles UI events for the research GUI."""

    def __init__(self, app: 'ResearchGUI'):
        self.app = app

    # ===== Simple Input Handlers =====

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
        value = self._validate_and_update_max_results(e.control.value.strip(), e.control)
        self._apply_max_results_config(value)

        if self.app.page:
            self.app.page.update()

    def on_step_expand(self, card: StepCard, expanded: bool):
        """Handle step card expansion change."""
        if self.app.page:
            self.app.page.update()

    # ===== Workflow Action Handlers =====

    def on_start_research(self, e):
        """Start the research workflow."""
        if not self.app.research_question or self.app.workflow_running:
            return

        if not self.app.agents_initialized:
            self.app.dialog_manager.show_error_dialog(
                "Research agents are not available. Please check your configuration and restart the application."
            )
            return

        self._start_workflow_execution()

    def on_add_more_documents(self, e):
        """Fetch additional documents with offset and score only the new ones."""
        if not self.app.workflow_executor or not self.app.documents:
            self.app.dialog_manager.show_error_dialog("No documents to extend")
            return

        self._disable_button_temporarily(e.control, "Fetching...")
        self._run_in_thread(self._fetch_more_documents_thread)

    def on_continue_workflow(self, e):
        """Continue workflow from scoring: extract citations (incremental) and regenerate report."""
        if not self.app.scored_documents:
            self.app.dialog_manager.show_error_dialog("No scored documents to process")
            return

        self._run_in_thread(self._continue_workflow_thread)

    # ===== Report Action Handlers =====

    def on_save_report(self, e):
        """Save the final report to a file."""
        self._handle_report_action(
            self.app.final_report,
            lambda: self._show_save_dialog(
                report=self.app.final_report,
                title="Save Research Report",
                default_prefix="research_report",
                description="Two files will be saved:",
                include_json_export=True
            ),
            "No report available to save"
        )

    def on_copy_report(self, e):
        """Copy the report to clipboard."""
        if self.app.final_report:
            self.app.dialog_manager.copy_to_clipboard(self.app.final_report)

    def on_preview_report(self, e):
        """Show report in a preview dialog."""
        self._handle_report_action(
            self.app.final_report,
            lambda: self._show_preview_overlay("Report Preview", self.app.final_report),
            "No report available to preview"
        )

    def on_save_preliminary_report(self, e):
        """Save the preliminary report to a file."""
        self._handle_report_action(
            self.app.preliminary_report,
            lambda: self._show_save_dialog(
                report=self.app.preliminary_report,
                title="Save Preliminary Report",
                default_prefix="preliminary_report",
                description="This is the report before counterfactual analysis.",
                include_json_export=False
            ),
            "No preliminary report available to save"
        )

    def on_copy_preliminary_report(self, e):
        """Copy the preliminary report to clipboard."""
        if self.app.preliminary_report:
            self.app.dialog_manager.copy_to_clipboard(self.app.preliminary_report)

    def on_preview_preliminary_report(self, e):
        """Show preliminary report in a preview dialog."""
        self._handle_report_action(
            self.app.preliminary_report,
            lambda: self._show_preview_overlay("Preliminary Report Preview", self.app.preliminary_report),
            "No preliminary report available to preview"
        )

    def on_report_link_tap(self, e):
        """Handle links in the report."""
        print(f"Report link tapped: {e.data}")

    # ===== Private Helper Methods =====

    def _update_status(self):
        """Update the status text."""
        if not self.app.research_question:
            self.app.status_text.value = "Enter a research question to begin"
        else:
            mode = "Interactive" if self.app.human_in_loop else "Automated"
            cf_mode = " + Comprehensive Counterfactual" if self.app.comprehensive_counterfactual else ""
            status_prefix = "Research in progress..." if self.app.workflow_running else "Ready to start research in"
            self.app.status_text.value = f"{status_prefix} {mode}{cf_mode} mode" if not self.app.workflow_running else f"{status_prefix} ({mode}{cf_mode} mode)"

    def _validate_and_update_max_results(self, raw_value: str, control) -> int:
        """Validate and return a valid max_results value."""
        if not raw_value:
            value = 100
            control.value = str(value)
        else:
            try:
                value = int(raw_value)
                # Clamp to valid range
                value = max(1, min(1000, value))
                control.value = str(value)
            except ValueError:
                # Reset to current valid value if invalid input
                value = self.app.max_results
                control.value = str(value)

        return value

    def _apply_max_results_config(self, value: int):
        """Apply max_results value to all relevant configuration locations."""
        self.app.max_results = value
        self.app.config_overrides['max_results'] = value
        if hasattr(self.app, 'workflow_executor') and self.app.workflow_executor:
            self.app.workflow_executor.config_overrides['max_results'] = value

    def _start_workflow_execution(self):
        """Prepare and start workflow execution in a thread."""
        self.app.workflow_running = True
        self.app.start_button.disabled = True
        self._update_status()
        self.app.page.update()

        self._run_in_thread(self._run_workflow_thread)

    def _run_workflow_thread(self):
        """Run the research workflow in a separate thread."""
        try:
            print("Starting workflow execution...")

            # Read and apply current GUI configuration
            config = self._read_workflow_config()
            self._apply_workflow_config(config)

            # Execute workflow
            self.app.final_report = self.app.workflow_executor.run_workflow(
                self.app.research_question,
                config['human_in_loop'],
                self._update_step_status,
                self.app.dialog_manager,
                self.app.step_cards,
                self.app.tab_manager
            )

            print(f"Workflow completed. Final report length: {len(self.app.final_report) if self.app.final_report else 0}")

            # Update tabs with final data
            self._update_tabs_after_workflow()

        except Exception as ex:
            self._handle_workflow_error(ex)
        finally:
            self._cleanup_workflow_state()

    def _read_workflow_config(self) -> dict:
        """Read current workflow configuration from GUI widgets."""
        try:
            max_results = int(self.app.max_results_field.value.strip()) if self.app.max_results_field.value.strip() else 100
            max_results = max(1, min(1000, max_results))
        except ValueError:
            max_results = 100

        config = {
            'max_results': max_results,
            'human_in_loop': self.app.human_loop_toggle.value,
            'comprehensive_counterfactual': self.app.counterfactual_toggle.value
        }

        print(f"🔧 Reading GUI values at execution time:")
        print(f"  - Max results widget: {self.app.max_results_field.value} -> using: {config['max_results']}")
        print(f"  - Interactive mode: {config['human_in_loop']}")
        print(f"  - Comprehensive counterfactual: {config['comprehensive_counterfactual']}")

        return config

    def _apply_workflow_config(self, config: dict):
        """Apply configuration to workflow executor and app state."""
        self.app.workflow_executor.config_overrides['comprehensive_counterfactual'] = config['comprehensive_counterfactual']
        self.app.workflow_executor.config_overrides['max_results'] = config['max_results']

        self.app.max_results = config['max_results']
        self.app.human_in_loop = config['human_in_loop']
        self.app.comprehensive_counterfactual = config['comprehensive_counterfactual']

    def _cleanup_workflow_state(self):
        """Reset workflow state after execution."""
        self.app.workflow_running = False
        self.app.start_button.disabled = not self.app.research_question
        self._update_status()
        if self.app.page:
            self.app.page.update()

    def _update_step_status(self, step: WorkflowStep, status: str, content: str = None):
        """Update a step's status and content."""
        if step in self.app.step_cards:
            self.app.step_cards[step].update_status(status, content)

            # Auto-switch to relevant tab when step starts or is running
            if status in ["running", "waiting"]:
                self._switch_to_relevant_tab(step)
                self._show_progress_bar_for_step(step, status)

            if status in ["completed", "tab_update"]:
                self._handle_step_completion(step)

            # Handle progressive counterfactual updates
            if step == WorkflowStep.PERFORM_COUNTERFACTUAL_ANALYSIS:
                self._handle_counterfactual_progressive_update(status, content)

            if self.app.page:
                self.app.page.update()

    def _show_progress_bar_for_step(self, step: WorkflowStep, status: str):
        """Show the appropriate progress bar when a step starts running."""
        from .data_updaters import DataUpdaters
        updaters = DataUpdaters(self.app)

        # Map steps to their progress bar show methods
        if step == WorkflowStep.GENERATE_AND_EDIT_QUERY:
            updaters.show_search_progress(visible=(status == "running"))
        elif step == WorkflowStep.SEARCH_DOCUMENTS:
            updaters.show_literature_progress(visible=(status == "running"))
        elif step == WorkflowStep.SCORE_DOCUMENTS:
            updaters.show_scoring_progress(visible=(status == "running"))
        elif step == WorkflowStep.EXTRACT_CITATIONS:
            updaters.show_citations_progress(visible=(status == "running"))
        elif step == WorkflowStep.GENERATE_REPORT:
            if self.app.tab_manager and hasattr(self.app.tab_manager, 'preliminary_progress_bar'):
                self.app.tab_manager.preliminary_progress_bar.visible = (status == "running")
        elif step == WorkflowStep.PERFORM_COUNTERFACTUAL_ANALYSIS:
            if self.app.tab_manager and hasattr(self.app.tab_manager, 'counterfactual_progress_bar'):
                self.app.tab_manager.counterfactual_progress_bar.visible = (status == "running")
        elif step == WorkflowStep.EXPORT_REPORT:
            if self.app.tab_manager and hasattr(self.app.tab_manager, 'report_progress_bar'):
                self.app.tab_manager.report_progress_bar.visible = (status == "running")

    def _switch_to_relevant_tab(self, step: WorkflowStep):
        """Switch to the tab relevant for the current workflow step."""
        if not self.app.tab_manager or not self.app.tab_manager.tabs_container:
            return

        # Map workflow steps to tab indices
        # Tab order: Search(0), Literature(1), Scoring(2), Citations(3), Preliminary(4), Counterfactual(5), Report(6)
        step_to_tab = {
            WorkflowStep.COLLECT_RESEARCH_QUESTION: 0,        # Search tab
            WorkflowStep.GENERATE_AND_EDIT_QUERY: 0,          # Search tab
            WorkflowStep.SEARCH_DOCUMENTS: 1,                  # Literature tab
            WorkflowStep.REVIEW_SEARCH_RESULTS: 1,             # Literature tab
            WorkflowStep.SCORE_DOCUMENTS: 2,                   # Scoring tab
            WorkflowStep.EXTRACT_CITATIONS: 3,                 # Citations tab
            WorkflowStep.GENERATE_REPORT: 4,                   # Preliminary tab
            WorkflowStep.PERFORM_COUNTERFACTUAL_ANALYSIS: 5,   # Counterfactual tab
            WorkflowStep.SEARCH_CONTRADICTORY_EVIDENCE: 5,     # Counterfactual tab
            WorkflowStep.EDIT_COMPREHENSIVE_REPORT: 6,         # Report tab
            WorkflowStep.EXPORT_REPORT: 6                      # Report tab
        }

        tab_index = step_to_tab.get(step)
        if tab_index is not None:
            print(f"🔄 Auto-switching to tab {tab_index} for step {step.name}")
            self.app.tab_manager.tabs_container.selected_index = tab_index
            if self.app.page:
                self.app.page.update()

    def _handle_step_completion(self, step: WorkflowStep):
        """Handle specific step completion events for tab updates."""
        from .data_updaters import DataUpdaters
        updaters = DataUpdaters(self.app)

        step_handlers = {
            WorkflowStep.COLLECT_RESEARCH_QUESTION: lambda: updaters.update_search_tab(
                self.app.research_question, show_edit_button=False
            ),
            WorkflowStep.GENERATE_AND_EDIT_QUERY: lambda: self._update_search_with_query(updaters),
            WorkflowStep.SEARCH_DOCUMENTS: updaters.update_documents_if_available,
            WorkflowStep.SCORE_DOCUMENTS: updaters.update_scored_documents_if_available,
            WorkflowStep.EXTRACT_CITATIONS: updaters.update_citations_if_available,
            WorkflowStep.GENERATE_REPORT: updaters.update_preliminary_report_if_available,
            WorkflowStep.PERFORM_COUNTERFACTUAL_ANALYSIS: updaters.update_counterfactual_if_available,
            WorkflowStep.EXPORT_REPORT: updaters.update_report_if_available
        }

        handler = step_handlers.get(step)
        if handler:
            print(f"📌 {step.name} completed - updating tab...")
            handler()

    def _update_search_with_query(self, updaters):
        """Update Search tab with generated query."""
        # Get the query from workflow executor if available
        query = None
        if hasattr(self.app.workflow_executor, 'last_query_text'):
            query = self.app.workflow_executor.last_query_text

        if query:
            updaters.update_search_tab(
                self.app.research_question,
                query=query,
                show_edit_button=False  # Button shown by interactive_handler if needed
            )

    def _handle_counterfactual_progressive_update(self, status: str, content: Any):
        """Handle progressive counterfactual analysis updates."""
        from .data_updaters import DataUpdaters
        updaters = DataUpdaters(self.app)

        # Handle different progressive update types
        if status == "cf_claims" and content:
            updaters.update_counterfactual_claims(content)
        elif status == "cf_questions" and content:
            updaters.update_counterfactual_questions(content)
        elif status == "cf_searches" and content:
            updaters.update_counterfactual_searches(content)
        elif status == "cf_results" and content:
            updaters.update_counterfactual_results(content)
        elif status == "cf_citations" and content:
            if isinstance(content, dict):
                updaters.update_counterfactual_citations(
                    content.get('contradictory_citations', []),
                    content.get('rejected_citations', []),
                    content.get('no_citation_extracted', [])
                )
        elif status == "cf_summary" and content:
            updaters.update_counterfactual_summary(content)
        elif status == "progress" and content:
            updaters.show_counterfactual_progress(content)

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

    def _handle_report_action(self, report_content: str, action: Callable, error_msg: str):
        """Generic handler for report actions (save/preview)."""
        print(f"Report action: exists={bool(report_content)}, length={len(report_content) if report_content else 0}")

        if report_content:
            action()
        else:
            self.app.dialog_manager.show_error_dialog(error_msg)

    def _show_save_dialog(self, report: str, title: str, default_prefix: str,
                         description: str, include_json_export: bool):
        """Show a save dialog for reports."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        default_filename = f"{default_prefix}_{timestamp}.md"
        default_path = os.path.join(os.path.expanduser("~/Desktop"), default_filename)

        def save_file(file_path: str):
            self._save_report_to_file(file_path, report, include_json_export)

        def close_dialog(e):
            self._clear_overlay()

        def handle_save(e):
            file_path = path_input.value.strip()
            if file_path:
                close_dialog(e)
                save_file(file_path)
            else:
                self.app.dialog_manager.show_error_dialog("Please enter a file path")

        path_input = ft.TextField(
            label=f"Save {default_prefix.replace('_', ' ')} to:",
            value=default_path,
            width=500,
            hint_text="Enter full file path (e.g., ~/Desktop/my_report.md)"
        )

        # Build description lines
        desc_lines = [ft.Text(description, size=12, weight=ft.FontWeight.W_500, color=ft.Colors.BLUE_700)]

        if include_json_export:
            desc_lines.extend([
                ft.Text("• [filename].md - Formatted research report", size=11, color=ft.Colors.GREY_700),
                ft.Text("• [filename].json - Complete workflow data for reconstruction", size=11, color=ft.Colors.GREY_700)
            ])
        else:
            desc_lines.append(
                ft.Text("• [filename].md - Markdown formatted report", size=11, color=ft.Colors.GREY_700)
            )

        dialog_content_column = ft.Column([
            ft.Text(title, size=18, weight=ft.FontWeight.BOLD),
            ft.Text("Enter the path where you want to save:", size=12),
            *desc_lines,
            path_input,
            ft.Row([
                ft.Container(expand=True),
                ft.TextButton("Cancel", on_click=close_dialog),
                ft.ElevatedButton("Save", on_click=handle_save)
            ], alignment=ft.MainAxisAlignment.END)
        ], spacing=15)

        # Wrap the dialog content in a styled container
        dialog_content = ft.Container(
            content=dialog_content_column,
            width=600,
            bgcolor=ft.Colors.WHITE,
            border_radius=10,
            padding=20,
            shadow=ft.BoxShadow(blur_radius=10, color=ft.Colors.GREY_400)
        )

        self._show_overlay_dialog(dialog_content)

    def _save_report_to_file(self, file_path: str, report: str, include_json_export: bool):
        """Save report to file with optional JSON export."""
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
                f.write(report)

            success_message = f"Report saved to: {expanded_path}"

            # Save comprehensive JSON data if requested
            if include_json_export:
                json_path = expanded_path.replace('.md', '.json')

                try:
                    comprehensive_data = self.app.workflow_executor.export_comprehensive_data(
                        research_question=self.app.research_question,
                        query_text=getattr(self.app.workflow_executor, 'last_query_text', None)
                    )

                    with open(json_path, 'w', encoding='utf-8') as f:
                        json.dump(comprehensive_data, f, indent=2, ensure_ascii=False)

                    success_message = f"Files saved successfully:\n• Report: {expanded_path}\n• Data: {json_path}"
                    print(f"Comprehensive data saved to: {json_path}")

                except Exception as json_error:
                    print(f"JSON export error: {json_error}")
                    success_message += f"\n\nWarning: Could not save comprehensive data file: {str(json_error)}"

            print(f"Report saved to: {expanded_path}")
            self.app.dialog_manager.show_success_dialog(success_message)

        except Exception as ex:
            self.app.dialog_manager.show_error_dialog(f"Failed to save report: {str(ex)}")
            print(f"Save error: {ex}")

    def _show_preview_overlay(self, title: str, content: str):
        """Show a preview overlay for report content."""
        try:
            def close_preview(e):
                self._clear_overlay()

            preview_content = ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Text(title, size=18, weight=ft.FontWeight.BOLD),
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
                                value=content,
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

            self._show_overlay_dialog(preview_content)
            print(f"Preview overlay created and displayed: {title}")

        except Exception as ex:
            print(f"Preview error: {ex}")
            # Fallback to dialog
            self.app.dialog_manager.show_preview_dialog(content)

    def _show_overlay_dialog(self, content):
        """Show a centered overlay dialog."""
        self.app.page.overlay.clear()
        self.app.page.overlay.append(
            ft.Container(
                content=content,
                alignment=ft.alignment.center,
                bgcolor=ft.Colors.with_opacity(0.5, ft.Colors.BLACK)
            )
        )
        self.app.page.update()

    def _clear_overlay(self):
        """Clear the page overlay."""
        self.app.page.overlay.clear()
        self.app.page.update()

    def _disable_button_temporarily(self, button, temp_text: str):
        """Temporarily disable a button and change its text."""
        if button:
            button.disabled = True
            button.text = temp_text
            self.app.page.update()

    def _run_in_thread(self, target: Callable):
        """Run a function in a separate daemon thread."""
        thread = threading.Thread(target=target, daemon=True)
        thread.start()

    # ===== Threaded Workflow Operations =====

    def _fetch_more_documents_thread(self):
        """Fetch additional documents with offset and score only the new ones."""
        try:
            from ..config import get_search_config

            offset = len(self.app.documents)
            max_results = self._get_effective_max_results()

            print(f"🔄 Fetching more documents: offset={offset}, max_results={max_results}")

            if not self._validate_previous_query():
                return

            # Fetch new documents
            query_text = self.app.workflow_executor.last_query_text
            new_documents = self._fetch_documents_with_offset(offset, max_results)

            if not new_documents:
                self._show_no_more_documents_message()
                return

            # Deduplicate
            deduplicated_docs = self._deduplicate_documents(new_documents)

            if not deduplicated_docs:
                self._show_all_duplicates_message()
                return

            # Add documents and score them
            self._add_and_score_new_documents(deduplicated_docs)

            # Show success
            self._show_fetch_success_message(len(deduplicated_docs))

        except Exception as ex:
            self._handle_fetch_error(ex)
        finally:
            if self.app.page:
                self.app.page.update()

    def _continue_workflow_thread(self):
        """Continue workflow: incremental citation extraction + full report regeneration."""
        try:
            from ..config import get_search_config

            print("🔄 Continuing workflow from scoring...")

            score_threshold = get_search_config().get('score_threshold', 2.5)

            # Determine which documents need citations
            docs_needing_citations = self._find_documents_needing_citations(score_threshold)

            # Extract new citations if needed
            new_citations = []
            if docs_needing_citations:
                new_citations = self._extract_citations_from_documents(docs_needing_citations, score_threshold)

            # Regenerate report with all citations
            report_object, report_formatted = self._regenerate_full_report()

            # Continue with counterfactual if enabled
            if self.app.comprehensive_counterfactual:
                self._perform_counterfactual_and_final_report(report_object, report_formatted)
                self._show_continue_success_with_counterfactual(len(new_citations))
            else:
                self._finalize_without_counterfactual(report_formatted)
                self._show_continue_success_without_counterfactual(len(new_citations))

        except Exception as ex:
            self._handle_continue_error(ex)
        finally:
            if self.app.page:
                self.app.page.update()

    # ===== Helper Methods for Document Fetching =====

    def _get_effective_max_results(self) -> int:
        """Get the effective max_results from configuration hierarchy."""
        from ..config import get_search_config

        max_results = None
        if hasattr(self.app.workflow_executor, 'config_overrides'):
            max_results = self.app.workflow_executor.config_overrides.get('max_results')
        if max_results is None and hasattr(self.app, 'config_overrides'):
            max_results = self.app.config_overrides.get('max_results')
        if max_results is None:
            search_config = get_search_config()
            max_results = search_config.get('max_results', 100)

        return max_results

    def _validate_previous_query(self) -> bool:
        """Validate that a previous query exists."""
        if not hasattr(self.app.workflow_executor, 'last_query_text') or not self.app.workflow_executor.last_query_text:
            self.app.dialog_manager.show_error_dialog("Cannot fetch more documents: no previous query found")
            self.app.data_updaters.update_scored_documents(self.app.scored_documents)
            return False
        return True

    def _fetch_documents_with_offset(self, offset: int, max_results: int) -> list:
        """Fetch documents using query agent with offset."""
        query_agent = self.app.agents['query_agent']
        documents_generator = query_agent.find_abstracts(
            question=self.app.research_question,
            max_rows=max_results,
            human_in_the_loop=False,
            human_query_modifier=None,
            offset=offset
        )

        new_documents = list(documents_generator)
        print(f"✅ Fetched {len(new_documents)} additional documents")
        return new_documents

    def _deduplicate_documents(self, new_documents: list) -> list:
        """Remove duplicates from new documents."""
        existing_ids = {doc.get('id') for doc in self.app.documents if doc.get('id')}
        deduplicated = [doc for doc in new_documents if doc.get('id') not in existing_ids]

        duplicates_found = len(new_documents) - len(deduplicated)
        if duplicates_found > 0:
            print(f"⚠️ Filtered out {duplicates_found} duplicate document(s)")

        return deduplicated

    def _add_and_score_new_documents(self, new_documents: list):
        """Add new documents to collection and score them."""
        # Add documents
        self.app.documents.extend(new_documents)
        self.app.workflow_executor.documents = self.app.documents
        self.app.data_updaters.update_documents(self.app.documents)

        # Score documents
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

        # Merge scored documents
        self.app.scored_documents.extend(new_scored_docs)
        self.app.workflow_executor.scored_documents = self.app.scored_documents
        self.app.data_updaters.update_scored_documents(self.app.scored_documents)

        print(f"✅ Successfully added and scored {len(new_documents)} new documents")

    def _show_no_more_documents_message(self):
        """Show message when no more documents are available."""
        self.app.dialog_manager.show_info_dialog(
            f"No more documents found in the database.\n\n"
            f"Total documents retrieved: {len(self.app.documents)}"
        )
        self.app.data_updaters.update_scored_documents(self.app.scored_documents)

    def _show_all_duplicates_message(self):
        """Show message when all fetched documents are duplicates."""
        self.app.dialog_manager.show_info_dialog(
            f"All fetched documents were duplicates.\n\n"
            f"Total unique documents: {len(self.app.documents)}"
        )
        self.app.data_updaters.update_scored_documents(self.app.scored_documents)

    def _show_fetch_success_message(self, count: int):
        """Show success message after fetching documents."""
        self.app.dialog_manager.show_info_dialog(
            f"Successfully fetched and scored {count} additional documents.\n\n"
            f"Total documents: {len(self.app.documents)}\n"
            f"Total scored: {len(self.app.scored_documents)}"
        )

    def _handle_fetch_error(self, error: Exception):
        """Handle errors during document fetching."""
        print(f"❌ Error fetching more documents: {error}")
        import traceback
        traceback.print_exc()
        self.app.dialog_manager.show_error_dialog(f"Error fetching more documents: {str(error)}")

    # ===== Helper Methods for Continue Workflow =====

    def _find_documents_needing_citations(self, score_threshold: float) -> list:
        """Find high-scoring documents that need citation extraction."""
        existing_citation_doc_ids = set()
        if self.app.citations:
            for citation in self.app.citations:
                if hasattr(citation, 'document_id'):
                    existing_citation_doc_ids.add(citation.document_id)
                elif hasattr(citation, 'doc_id'):
                    existing_citation_doc_ids.add(citation.doc_id)

        docs_needing_citations = []
        for doc, score_data in self.app.scored_documents:
            if score_data.get('score', 0) > score_threshold:
                doc_id = doc.get('id')
                if doc_id not in existing_citation_doc_ids:
                    docs_needing_citations.append((doc, score_data))

        print(f"📚 Documents needing citation extraction: {len(docs_needing_citations)}")
        print(f"📖 Existing citations: {len(self.app.citations)}")

        return docs_needing_citations

    def _extract_citations_from_documents(self, docs_needing_citations: list, score_threshold: float) -> list:
        """Extract citations from documents."""
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

        self.app.data_updaters.update_citations(self.app.citations)

        return new_citations

    def _regenerate_full_report(self) -> tuple:
        """Regenerate report with all citations. Returns (report_object, report_formatted)."""
        print(f"📝 Regenerating report with {len(self.app.citations)} total citations...")

        reporting_agent = self.app.agents['reporting_agent']

        # Get both object and formatted versions
        report_object = reporting_agent.generate_citation_based_report(
            user_question=self.app.research_question,
            citations=self.app.citations,
            format_output=False
        )

        report_formatted = reporting_agent.generate_citation_based_report(
            user_question=self.app.research_question,
            citations=self.app.citations,
            format_output=True
        )

        # Store as preliminary report
        self.app.preliminary_report = report_formatted
        self.app.workflow_executor.preliminary_report = report_formatted
        self.app.data_updaters.update_preliminary_report(report_formatted)

        print(f"✅ Report regenerated successfully")

        return report_object, report_formatted

    def _perform_counterfactual_and_final_report(self, report_object, report_formatted: str):
        """Perform counterfactual analysis and generate final report."""
        print(f"🧠 Performing comprehensive counterfactual analysis with literature search...")

        # Execute comprehensive counterfactual analysis
        def dummy_callback(step, status, message):
            print(f"  [{step.name}] {status}: {message}")

        counterfactual_analysis = self.app.workflow_executor.steps_handler.execute_comprehensive_counterfactual_analysis(
            report_formatted,
            self.app.citations,
            dummy_callback
        )

        # Store counterfactual analysis
        self.app.counterfactual_analysis = counterfactual_analysis
        self.app.workflow_executor.counterfactual_analysis = counterfactual_analysis
        self.app.data_updaters.update_counterfactual_if_available()

        print(f"🔬 Counterfactual analysis completed and displayed in tab")

        # Convert to dict for editor agent
        contradictory_dict = self._convert_counterfactual_to_dict(counterfactual_analysis)

        # Generate final comprehensive report
        print(f"📝 Generating comprehensive final report...")

        editor_agent = self.app.agents['editor_agent']
        final_report = editor_agent.create_comprehensive_report(
            original_report=report_object,
            research_question=self.app.research_question,
            supporting_citations=self.app.citations,
            contradictory_evidence=contradictory_dict
        )

        # Extract and store final report
        if final_report and (hasattr(final_report, 'content') or isinstance(final_report, str)):
            final_report_content = final_report.content if hasattr(final_report, 'content') else final_report

            # Build the full report with audit trail using report_builder
            print(f"📝 Building full final report with audit trail...")
            comprehensive_report = self.app.workflow_executor.report_builder.build_final_report(
                self.app.research_question,
                final_report_content,
                counterfactual_analysis,
                self.app.documents,
                self.app.scored_documents,
                self.app.citations,
                False,  # human_in_loop (we're in continue mode)
                self.app.workflow_executor.agent_model_info
            )

            self.app.final_report = comprehensive_report
            self.app.workflow_executor.final_report = comprehensive_report
            self.app.data_updaters.update_report(comprehensive_report)
            print(f"✅ Comprehensive final report with audit trail generated ({len(comprehensive_report)} chars)")
        else:
            # Fallback to preliminary report with audit trail
            print(f"⚠️ Editor agent failed, building final report from preliminary with audit trail")
            comprehensive_report = self.app.workflow_executor.report_builder.build_final_report(
                self.app.research_question,
                report_formatted,
                counterfactual_analysis,
                self.app.documents,
                self.app.scored_documents,
                self.app.citations,
                False,  # human_in_loop
                self.app.workflow_executor.agent_model_info
            )

            self.app.final_report = comprehensive_report
            self.app.workflow_executor.final_report = comprehensive_report
            self.app.data_updaters.update_report(comprehensive_report)

    def _finalize_without_counterfactual(self, report_formatted: str):
        """Finalize workflow without counterfactual analysis."""
        # Build the full report with audit trail using report_builder
        print(f"📝 Building final report without counterfactual (with audit trail)...")
        comprehensive_report = self.app.workflow_executor.report_builder.build_final_report(
            self.app.research_question,
            report_formatted,
            None,  # No counterfactual analysis
            self.app.documents,
            self.app.scored_documents,
            self.app.citations,
            False,  # human_in_loop (we're in continue mode)
            self.app.workflow_executor.agent_model_info
        )

        self.app.final_report = comprehensive_report
        self.app.workflow_executor.final_report = comprehensive_report
        self.app.data_updaters.update_report(comprehensive_report)
        print(f"✅ Final report with audit trail generated ({len(comprehensive_report)} chars)")

    def _convert_counterfactual_to_dict(self, counterfactual_analysis) -> Optional[dict]:
        """Convert CounterfactualAnalysis object to dict."""
        if not counterfactual_analysis:
            return None

        if hasattr(counterfactual_analysis, 'to_dict'):
            return counterfactual_analysis.to_dict()
        elif hasattr(counterfactual_analysis, '__dict__'):
            return counterfactual_analysis.__dict__
        else:
            return {'analysis': str(counterfactual_analysis)}

    def _show_continue_success_with_counterfactual(self, new_citations_count: int):
        """Show success message for workflow continuation with counterfactual."""
        self.app.dialog_manager.show_info_dialog(
            f"Workflow completed successfully!\n\n"
            f"New citations extracted: {new_citations_count}\n"
            f"Total citations: {len(self.app.citations)}\n"
            f"Preliminary report regenerated\n"
            f"Counterfactual analysis performed\n"
            f"Final comprehensive report generated"
        )

    def _show_continue_success_without_counterfactual(self, new_citations_count: int):
        """Show success message for workflow continuation without counterfactual."""
        self.app.dialog_manager.show_info_dialog(
            f"Workflow continued successfully!\n\n"
            f"New citations extracted: {new_citations_count}\n"
            f"Total citations: {len(self.app.citations)}\n"
            f"Report regenerated with all evidence"
        )

    def _handle_continue_error(self, error: Exception):
        """Handle errors during workflow continuation."""
        print(f"❌ Error continuing workflow: {error}")
        import traceback
        traceback.print_exc()
        self.app.dialog_manager.show_error_dialog(f"Error continuing workflow: {str(error)}")
