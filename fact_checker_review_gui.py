#!/usr/bin/env python3
"""
Fact-Checker Review GUI for BMLibrarian

A graphical interface for human reviewers to annotate and review fact-checking results.
Built using the Flet framework, this application allows reviewers to:
- Load fact-check results from JSON files
- Review each statement with original and AI-generated annotations
- Provide human annotations with explanations
- View supporting citations for each statement
- Export reviewed annotations to a new JSON file
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
import flet as ft


class FactCheckerReviewGUI:
    """Main application for reviewing fact-check results."""

    def __init__(self):
        self.page: Optional[ft.Page] = None
        self.results: List[Dict[str, Any]] = []
        self.current_index: int = 0
        self.reviews: List[Dict[str, Any]] = []
        self.input_file_path: str = ""

        # UI components
        self.file_path_text = None
        self.statement_counter = None
        self.statement_text = None
        self.original_annotation = None
        self.ai_annotation = None
        self.ai_rationale = None
        self.human_annotation_dropdown = None
        self.human_explanation = None
        self.citations_list = None
        self.prev_button = None
        self.next_button = None
        self.save_button = None
        self.progress_bar = None

    def main(self, page: ft.Page):
        """Main application entry point."""
        self.page = page
        self._setup_page()
        self._build_ui()

    def _setup_page(self):
        """Configure the main page settings."""
        self.page.title = "BMLibrarian Fact-Checker Review"
        self.page.window.width = 1400
        self.page.window.height = 900
        self.page.window.min_width = 1200
        self.page.window.min_height = 700
        self.page.window.resizable = True
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.padding = 20
        self.page.scroll = ft.ScrollMode.AUTO

    def _build_ui(self):
        """Build the main user interface."""
        # Header
        header = ft.Container(
            content=ft.Column([
                ft.Text(
                    "Fact-Checker Review Interface",
                    size=28,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.BLUE_900
                ),
                ft.Text(
                    "Review and annotate AI-generated fact-checking results",
                    size=14,
                    color=ft.Colors.GREY_700
                )
            ], spacing=5),
            padding=ft.padding.only(bottom=20)
        )

        # File selection section
        self.file_path_text = ft.Text(
            "No file loaded",
            size=12,
            color=ft.Colors.GREY_600,
            italic=True
        )

        file_section = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.ElevatedButton(
                        "Load Fact-Check Results",
                        icon=ft.Icons.FOLDER_OPEN,
                        on_click=self._on_load_file,
                        bgcolor=ft.Colors.BLUE_600,
                        color=ft.Colors.WHITE
                    ),
                    self.file_path_text
                ], spacing=15, alignment=ft.MainAxisAlignment.START)
            ]),
            padding=ft.padding.all(15),
            bgcolor=ft.Colors.BLUE_50,
            border_radius=10
        )

        # Review content (initially hidden)
        self.review_content = self._build_review_content()
        self.review_content.visible = False

        # Main layout
        main_content = ft.Column([
            header,
            file_section,
            ft.Container(height=20),
            self.review_content
        ], spacing=0, expand=True, scroll=ft.ScrollMode.AUTO)

        self.page.add(main_content)

    def _build_review_content(self) -> ft.Container:
        """Build the statement review interface."""
        # Progress section
        self.statement_counter = ft.Text(
            "Statement 0 of 0",
            size=14,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.BLUE_900
        )

        self.progress_bar = ft.ProgressBar(
            value=0,
            width=400,
            color=ft.Colors.BLUE_600,
            bgcolor=ft.Colors.BLUE_100
        )

        progress_section = ft.Row([
            self.statement_counter,
            self.progress_bar
        ], spacing=20, alignment=ft.MainAxisAlignment.START)

        # Statement section
        self.statement_text = ft.Text(
            "",
            size=16,
            weight=ft.FontWeight.W_500,
            selectable=True
        )

        statement_section = ft.Container(
            content=ft.Column([
                ft.Text("Statement:", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.GREY_700),
                self.statement_text
            ], spacing=8),
            padding=ft.padding.all(15),
            bgcolor=ft.Colors.GREY_50,
            border_radius=8,
            border=ft.border.all(1, ft.Colors.GREY_300)
        )

        # Annotations section (3 columns)
        self.original_annotation = self._create_annotation_display(
            "Original Annotation",
            ft.Colors.PURPLE_100,
            ft.Colors.PURPLE_700
        )

        self.ai_annotation = self._create_annotation_display(
            "AI Fact-Checker",
            ft.Colors.BLUE_100,
            ft.Colors.BLUE_700
        )

        self.ai_rationale = ft.Text(
            "",
            size=12,
            color=ft.Colors.GREY_800,
            selectable=True
        )

        # Human annotation section
        self.human_annotation_dropdown = ft.Dropdown(
            label="Your Annotation",
            options=[
                ft.dropdown.Option("yes", "Yes"),
                ft.dropdown.Option("no", "No"),
                ft.dropdown.Option("maybe", "Maybe"),
                ft.dropdown.Option("", "-- Select --")
            ],
            value="",
            width=200,
            on_change=self._on_annotation_change
        )

        self.human_explanation = ft.TextField(
            label="Explanation for your annotation (optional)",
            multiline=True,
            min_lines=2,
            max_lines=4,
            on_change=self._on_explanation_change
        )

        human_annotation_section = ft.Container(
            content=ft.Column([
                ft.Text("Human Review", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_700),
                self.human_annotation_dropdown,
                self.human_explanation
            ], spacing=10),
            padding=ft.padding.all(15),
            bgcolor=ft.Colors.GREEN_50,
            border_radius=8,
            border=ft.border.all(2, ft.Colors.GREEN_300)
        )

        # Annotations row
        annotations_row = ft.Row([
            ft.Container(
                content=self.original_annotation,
                expand=1
            ),
            ft.Container(
                content=ft.Column([
                    self.ai_annotation,
                    ft.Container(height=10),
                    ft.Container(
                        content=ft.Column([
                            ft.Text("AI Rationale:", size=11, weight=ft.FontWeight.BOLD, color=ft.Colors.GREY_700),
                            self.ai_rationale
                        ], spacing=5),
                        padding=ft.padding.all(10),
                        bgcolor=ft.Colors.GREY_50,
                        border_radius=5
                    )
                ], spacing=0),
                expand=1
            ),
            ft.Container(
                content=human_annotation_section,
                expand=1
            )
        ], spacing=15)

        # Citations section
        self.citations_list = ft.Column(
            controls=[],
            spacing=10,
            scroll=ft.ScrollMode.AUTO
        )

        citations_section = ft.Container(
            content=ft.Column([
                ft.Text(
                    "Supporting Citations",
                    size=14,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.GREY_900
                ),
                ft.Container(
                    content=self.citations_list,
                    height=300,
                    bgcolor=ft.Colors.GREY_50,
                    border_radius=8,
                    padding=ft.padding.all(10)
                )
            ], spacing=10),
            padding=ft.padding.all(15),
            bgcolor=ft.Colors.ORANGE_50,
            border_radius=8,
            border=ft.border.all(1, ft.Colors.ORANGE_200)
        )

        # Navigation buttons
        self.prev_button = ft.ElevatedButton(
            "Previous",
            icon=ft.Icons.ARROW_BACK,
            on_click=self._on_previous,
            disabled=True
        )

        self.next_button = ft.ElevatedButton(
            "Next",
            icon=ft.Icons.ARROW_FORWARD,
            on_click=self._on_next,
            disabled=True
        )

        self.save_button = ft.ElevatedButton(
            "Save Reviews",
            icon=ft.Icons.SAVE,
            on_click=self._on_save_reviews,
            bgcolor=ft.Colors.GREEN_700,
            color=ft.Colors.WHITE
        )

        navigation_section = ft.Row([
            self.prev_button,
            self.next_button,
            ft.Container(expand=True),
            self.save_button
        ], spacing=10, alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        # Combine all sections
        return ft.Container(
            content=ft.Column([
                progress_section,
                ft.Container(height=10),
                statement_section,
                ft.Container(height=15),
                annotations_row,
                ft.Container(height=15),
                citations_section,
                ft.Container(height=20),
                navigation_section
            ], spacing=0),
            padding=ft.padding.all(20),
            bgcolor=ft.Colors.WHITE,
            border_radius=10,
            border=ft.border.all(1, ft.Colors.GREY_300)
        )

    def _create_annotation_display(self, title: str, bg_color: str, text_color: str) -> ft.Column:
        """Create a standardized annotation display component."""
        annotation_badge = ft.Container(
            content=ft.Text(
                "--",
                size=14,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.WHITE
            ),
            padding=ft.padding.symmetric(horizontal=20, vertical=8),
            bgcolor=text_color,
            border_radius=20,
            alignment=ft.alignment.center
        )

        return ft.Column([
            ft.Text(title, size=12, weight=ft.FontWeight.BOLD, color=text_color),
            annotation_badge
        ], spacing=10, horizontal_alignment=ft.CrossAxisAlignment.CENTER)

    def _on_load_file(self, e):
        """Handle load file button click."""
        def on_file_result(file_picker_result: ft.FilePickerResultEvent):
            if file_picker_result.files and len(file_picker_result.files) > 0:
                file_path = file_picker_result.files[0].path
                self._load_fact_check_results(file_path)

        # Create file picker
        file_picker = ft.FilePicker(on_result=on_file_result)
        self.page.overlay.append(file_picker)
        self.page.update()

        # Open file picker dialog
        file_picker.pick_files(
            dialog_title="Select Fact-Check Results JSON",
            allowed_extensions=["json"],
            allow_multiple=False
        )

    def _load_fact_check_results(self, file_path: str):
        """Load fact-check results from JSON file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Extract results array
            if isinstance(data, dict) and 'results' in data:
                self.results = data['results']
            elif isinstance(data, list):
                self.results = data
            else:
                raise ValueError("Invalid JSON format: expected 'results' array or direct array")

            if not self.results:
                raise ValueError("No results found in file")

            # Initialize reviews list
            self.reviews = [{}] * len(self.results)

            # Store file path
            self.input_file_path = file_path
            self.file_path_text.value = f"Loaded: {Path(file_path).name} ({len(self.results)} statements)"
            self.file_path_text.italic = False
            self.file_path_text.color = ft.Colors.GREEN_700

            # Show review interface
            self.current_index = 0
            self.review_content.visible = True
            self._display_current_statement()

            self.page.update()

        except Exception as ex:
            self._show_error_dialog(f"Error loading file: {str(ex)}")

    def _display_current_statement(self):
        """Display the current statement and its annotations."""
        if not self.results or self.current_index >= len(self.results):
            return

        result = self.results[self.current_index]

        # Update progress
        self.statement_counter.value = f"Statement {self.current_index + 1} of {len(self.results)}"
        self.progress_bar.value = (self.current_index + 1) / len(self.results)

        # Update statement
        self.statement_text.value = result.get('statement', 'N/A')

        # Update original annotation
        expected_answer = result.get('expected_answer', 'N/A')
        self._update_annotation_badge(self.original_annotation, expected_answer)

        # Update AI annotation
        ai_evaluation = result.get('evaluation', 'N/A')
        self._update_annotation_badge(self.ai_annotation, ai_evaluation)

        # Update AI rationale
        self.ai_rationale.value = result.get('reason', 'No rationale provided')

        # Update human annotation from saved review (if exists)
        saved_review = self.reviews[self.current_index]
        self.human_annotation_dropdown.value = saved_review.get('human_annotation', '')
        self.human_explanation.value = saved_review.get('human_explanation', '')

        # Update citations
        self._display_citations(result.get('evidence_list', []))

        # Update navigation buttons
        self.prev_button.disabled = (self.current_index == 0)
        self.next_button.disabled = (self.current_index == len(self.results) - 1)

        self.page.update()

    def _update_annotation_badge(self, annotation_column: ft.Column, value: str):
        """Update an annotation badge with the given value."""
        # annotation_column has: [Text(title), Container(badge)]
        badge_container = annotation_column.controls[1]
        badge_text = badge_container.content

        # Update text and color based on value
        value_lower = str(value).lower()

        if value_lower == 'yes':
            badge_text.value = "YES ✓"
            badge_container.bgcolor = ft.Colors.GREEN_700
        elif value_lower == 'no':
            badge_text.value = "NO ✗"
            badge_container.bgcolor = ft.Colors.RED_700
        elif value_lower == 'maybe':
            badge_text.value = "MAYBE ?"
            badge_container.bgcolor = ft.Colors.ORANGE_700
        else:
            badge_text.value = str(value).upper()
            badge_container.bgcolor = ft.Colors.GREY_600

    def _display_citations(self, evidence_list: List[Dict[str, Any]]):
        """Display citations in the scrollable list."""
        self.citations_list.controls.clear()

        if not evidence_list:
            self.citations_list.controls.append(
                ft.Text("No citations available", size=12, color=ft.Colors.GREY_500, italic=True)
            )
            return

        for i, evidence in enumerate(evidence_list, 1):
            citation_card = self._create_citation_card(i, evidence)
            self.citations_list.controls.append(citation_card)

    def _create_citation_card(self, index: int, evidence: Dict[str, Any]) -> ft.Container:
        """Create a card for displaying a single citation."""
        # Get stance color
        stance = evidence.get('stance', 'neutral')
        if stance == 'supports':
            stance_color = ft.Colors.GREEN_100
            stance_border = ft.Colors.GREEN_500
            stance_icon = ft.Icons.CHECK_CIRCLE
            stance_icon_color = ft.Colors.GREEN_700
        elif stance == 'contradicts':
            stance_color = ft.Colors.RED_100
            stance_border = ft.Colors.RED_500
            stance_icon = ft.Icons.CANCEL
            stance_icon_color = ft.Colors.RED_700
        else:
            stance_color = ft.Colors.GREY_100
            stance_border = ft.Colors.GREY_400
            stance_icon = ft.Icons.HELP_OUTLINE
            stance_icon_color = ft.Colors.GREY_700

        # Get identifiers
        pmid = evidence.get('pmid', '')
        doi = evidence.get('doi', '')
        relevance_score = evidence.get('relevance_score')

        identifier_text = []
        if pmid:
            identifier_text.append(pmid)
        if doi:
            identifier_text.append(doi)
        if relevance_score is not None:
            identifier_text.append(f"Score: {relevance_score:.1f}/5.0")

        identifier_str = " | ".join(identifier_text) if identifier_text else "No identifier"

        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(stance_icon, color=stance_icon_color, size=20),
                    ft.Text(
                        f"Citation {index}",
                        size=13,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.GREY_900
                    ),
                    ft.Container(
                        content=ft.Text(
                            stance.upper(),
                            size=10,
                            weight=ft.FontWeight.BOLD,
                            color=ft.Colors.WHITE
                        ),
                        bgcolor=stance_border,
                        padding=ft.padding.symmetric(horizontal=8, vertical=2),
                        border_radius=10
                    )
                ], spacing=10),
                ft.Text(
                    identifier_str,
                    size=10,
                    color=ft.Colors.GREY_600,
                    italic=True
                ),
                ft.Container(height=5),
                ft.Text(
                    evidence.get('citation', 'No citation text available'),
                    size=12,
                    color=ft.Colors.GREY_800,
                    selectable=True
                )
            ], spacing=5),
            padding=ft.padding.all(12),
            bgcolor=stance_color,
            border_radius=8,
            border=ft.border.all(1, stance_border)
        )

    def _on_annotation_change(self, e):
        """Handle human annotation selection change."""
        if not self.reviews:
            return

        if 'human_annotation' not in self.reviews[self.current_index]:
            self.reviews[self.current_index] = {}

        self.reviews[self.current_index]['human_annotation'] = self.human_annotation_dropdown.value

    def _on_explanation_change(self, e):
        """Handle human explanation text change."""
        if not self.reviews:
            return

        if 'human_explanation' not in self.reviews[self.current_index]:
            self.reviews[self.current_index] = {}

        self.reviews[self.current_index]['human_explanation'] = self.human_explanation.value

    def _on_previous(self, e):
        """Navigate to previous statement."""
        if self.current_index > 0:
            self.current_index -= 1
            self._display_current_statement()

    def _on_next(self, e):
        """Navigate to next statement."""
        if self.current_index < len(self.results) - 1:
            self.current_index += 1
            self._display_current_statement()

    def _on_save_reviews(self, e):
        """Save human reviews to a new JSON file."""
        if not self.results:
            self._show_error_dialog("No results to save")
            return

        # Create dialog for file save
        save_path_field = ft.TextField(
            label="Output file path",
            value=self._get_default_output_path(),
            width=500
        )

        def on_save_confirm(e):
            output_path = save_path_field.value
            if output_path:
                self._save_reviews_to_file(output_path)
                dialog.open = False
                self.page.update()

        def on_cancel(e):
            dialog.open = False
            self.page.update()

        dialog = ft.AlertDialog(
            title=ft.Text("Save Reviewed Annotations"),
            content=ft.Container(
                content=save_path_field,
                padding=ft.padding.all(10)
            ),
            actions=[
                ft.TextButton("Cancel", on_click=on_cancel),
                ft.ElevatedButton(
                    "Save",
                    on_click=on_save_confirm,
                    bgcolor=ft.Colors.GREEN_700,
                    color=ft.Colors.WHITE
                )
            ]
        )

        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()

    def _get_default_output_path(self) -> str:
        """Generate default output file path."""
        if self.input_file_path:
            input_path = Path(self.input_file_path)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            return str(input_path.parent / f"{input_path.stem}_reviewed_{timestamp}.json")
        else:
            return f"fact_check_reviewed_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    def _save_reviews_to_file(self, output_path: str):
        """Save reviews to JSON file."""
        try:
            # Combine results with reviews
            output_data = {
                "reviewed_statements": [],
                "metadata": {
                    "source_file": self.input_file_path,
                    "review_date": datetime.now().isoformat(),
                    "total_statements": len(self.results),
                    "reviewed_count": sum(1 for r in self.reviews if r.get('human_annotation'))
                }
            }

            for i, result in enumerate(self.results):
                review = self.reviews[i] if i < len(self.reviews) else {}

                reviewed_item = {
                    "statement": result.get('statement'),
                    "original_annotation": result.get('expected_answer'),
                    "ai_annotation": result.get('evaluation'),
                    "ai_rationale": result.get('reason'),
                    "human_annotation": review.get('human_annotation', ''),
                    "human_explanation": review.get('human_explanation', ''),
                    "evidence_count": len(result.get('evidence_list', [])),
                    "matches_expected": result.get('matches_expected')
                }

                # Include input statement ID if present
                if 'input_statement_id' in result:
                    reviewed_item['input_statement_id'] = result['input_statement_id']

                output_data["reviewed_statements"].append(reviewed_item)

            # Write to file
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)

            self._show_success_dialog(f"Reviews saved successfully to:\n{output_path}")

        except Exception as ex:
            self._show_error_dialog(f"Error saving reviews: {str(ex)}")

    def _show_error_dialog(self, message: str):
        """Show error dialog."""
        dialog = ft.AlertDialog(
            title=ft.Text("Error", color=ft.Colors.RED_700),
            content=ft.Text(message),
            actions=[
                ft.TextButton("OK", on_click=lambda e: self._close_dialog(dialog))
            ]
        )
        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()

    def _show_success_dialog(self, message: str):
        """Show success dialog."""
        dialog = ft.AlertDialog(
            title=ft.Text("Success", color=ft.Colors.GREEN_700),
            content=ft.Text(message),
            actions=[
                ft.TextButton("OK", on_click=lambda e: self._close_dialog(dialog))
            ]
        )
        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()

    def _close_dialog(self, dialog):
        """Close a dialog."""
        dialog.open = False
        self.page.update()


def main():
    """Main entry point for the application."""
    app = FactCheckerReviewGUI()
    ft.app(target=app.main)


if __name__ == "__main__":
    main()
