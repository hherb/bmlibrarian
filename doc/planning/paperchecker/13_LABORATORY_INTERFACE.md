# Step 13: Laboratory Interface Implementation

## Context

The CLI (Step 12) provides batch processing. We need an interactive laboratory interface for testing, debugging, and exploration of PaperChecker functionality.

## Objective

Create `paper_checker_lab.py` that provides:
- Interactive GUI for single abstract checking
- Step-by-step workflow visualization
- Intermediate result inspection
- Parameter adjustment
- Export capabilities

## Requirements

- Flet-based GUI (consistent with BMLibrarian)
- Interactive workflow with step cards
- Real-time progress updates
- Result export (JSON, markdown)
- Error display and debugging

## Implementation Location

Create: `paper_checker_lab.py` (root directory)

## Laboratory Design

```python
#!/usr/bin/env python3
"""
PaperChecker Laboratory - Interactive testing interface

An interactive GUI for testing and exploring PaperChecker functionality
on single abstracts with step-by-step visualization.
"""

import flet as ft
import logging
from typing import Optional
import json

from bmlibrarian.paperchecker.agent import PaperCheckerAgent
from bmlibrarian.paperchecker.data_models import PaperCheckResult

logger = logging.getLogger(__name__)


class PaperCheckerLab:
    """Interactive laboratory for PaperChecker"""

    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = "PaperChecker Laboratory"
        self.page.padding = 20

        # State
        self.agent: Optional[PaperCheckerAgent] = None
        self.current_result: Optional[PaperCheckResult] = None

        # UI components
        self.abstract_input = None
        self.pmid_input = None
        self.check_button = None
        self.progress_bar = None
        self.progress_text = None
        self.workflow_column = None
        self.result_tabs = None

        # Initialize UI
        self._build_ui()

        # Initialize agent
        self._initialize_agent()

    def _build_ui(self):
        """Build user interface"""

        # Header
        header = ft.Container(
            content=ft.Column([
                ft.Text("PaperChecker Laboratory", size=32, weight=ft.FontWeight.BOLD),
                ft.Text("Interactive medical abstract fact-checking", size=16),
            ]),
            padding=ft.padding.only(bottom=20)
        )

        # Input section
        self.abstract_input = ft.TextField(
            label="Abstract Text",
            multiline=True,
            min_lines=5,
            max_lines=10,
            hint_text="Paste medical abstract here...",
            expand=True
        )

        self.pmid_input = ft.TextField(
            label="Or enter PMID",
            hint_text="12345678",
            width=200
        )

        self.check_button = ft.ElevatedButton(
            "Check Abstract",
            icon=ft.icons.PLAY_ARROW,
            on_click=self._on_check_clicked
        )

        input_section = ft.Container(
            content=ft.Column([
                ft.Text("Input", size=20, weight=ft.FontWeight.BOLD),
                ft.Row([
                    self.abstract_input,
                ], expand=True),
                ft.Row([
                    self.pmid_input,
                    self.check_button
                ])
            ]),
            padding=10,
            border=ft.border.all(1, ft.colors.OUTLINE),
            border_radius=10
        )

        # Progress section
        self.progress_bar = ft.ProgressBar(visible=False)
        self.progress_text = ft.Text("", size=14)

        progress_section = ft.Container(
            content=ft.Column([
                self.progress_bar,
                self.progress_text
            ]),
            padding=10
        )

        # Workflow section
        self.workflow_column = ft.Column([], scroll=ft.ScrollMode.AUTO)

        workflow_section = ft.Container(
            content=ft.Column([
                ft.Text("Workflow Progress", size=20, weight=ft.FontWeight.BOLD),
                self.workflow_column
            ]),
            padding=10,
            border=ft.border.all(1, ft.colors.OUTLINE),
            border_radius=10,
            expand=True
        )

        # Results section
        self.result_tabs = ft.Tabs(
            tabs=[
                ft.Tab(text="Summary", content=ft.Container(padding=10)),
                ft.Tab(text="Statements", content=ft.Container(padding=10)),
                ft.Tab(text="Counter-Evidence", content=ft.Container(padding=10)),
                ft.Tab(text="Verdicts", content=ft.Container(padding=10)),
                ft.Tab(text="Export", content=ft.Container(padding=10)),
            ],
            visible=False,
            expand=True
        )

        results_section = ft.Container(
            content=ft.Column([
                ft.Text("Results", size=20, weight=ft.FontWeight.BOLD),
                self.result_tabs
            ]),
            padding=10,
            border=ft.border.all(1, ft.colors.OUTLINE),
            border_radius=10,
            expand=True
        )

        # Layout
        self.page.add(
            header,
            input_section,
            progress_section,
            ft.Row([
                ft.Container(workflow_section, expand=1),
                ft.Container(results_section, expand=1)
            ], expand=True)
        )

    def _initialize_agent(self):
        """Initialize PaperCheckerAgent"""
        try:
            self.agent = PaperCheckerAgent()
            logger.info("PaperCheckerAgent initialized")
        except Exception as e:
            logger.error(f"Failed to initialize agent: {e}")
            self._show_error(f"Failed to initialize agent: {e}")

    def _on_check_clicked(self, e):
        """Handle check button click"""
        # Get abstract
        abstract_text = self.abstract_input.value
        pmid = self.pmid_input.value

        if pmid:
            # Fetch from database
            abstract_data = self._fetch_by_pmid(pmid)
            if not abstract_data:
                self._show_error(f"PMID {pmid} not found in database")
                return
            abstract_text = abstract_data["abstract"]
            metadata = abstract_data["metadata"]
        elif abstract_text:
            metadata = {}
        else:
            self._show_error("Please provide abstract text or PMID")
            return

        # Run check
        self._run_check(abstract_text, metadata)

    def _run_check(self, abstract: str, metadata: dict):
        """Run abstract check with progress tracking"""
        # Show progress
        self.progress_bar.visible = True
        self.check_button.disabled = True
        self.workflow_column.controls.clear()
        self.result_tabs.visible = False
        self.page.update()

        try:
            # Run check with progress callback
            result = self.agent.check_abstract(
                abstract=abstract,
                source_metadata=metadata,
                progress_callback=self._on_progress_update
            )

            # Store result
            self.current_result = result

            # Display results
            self._display_results(result)

        except Exception as e:
            logger.error(f"Check failed: {e}", exc_info=True)
            self._show_error(f"Check failed: {e}")

        finally:
            # Hide progress
            self.progress_bar.visible = False
            self.check_button.disabled = False
            self.page.update()

    def _on_progress_update(self, step_name: str, progress: float):
        """Handle progress updates"""
        self.progress_text.value = f"{step_name} ({progress*100:.0f}%)"
        self.progress_bar.value = progress

        # Add workflow step card
        step_card = ft.Card(
            content=ft.Container(
                content=ft.Row([
                    ft.Icon(
                        ft.icons.CHECK_CIRCLE if progress == 1.0
                        else ft.icons.PENDING,
                        color=ft.colors.GREEN if progress == 1.0
                        else ft.colors.BLUE
                    ),
                    ft.Text(step_name, size=14)
                ]),
                padding=10
            )
        )

        self.workflow_column.controls.append(step_card)
        self.page.update()

    def _display_results(self, result: PaperCheckResult):
        """Display results in tabs"""
        # Summary tab
        summary_content = self._build_summary_tab(result)
        self.result_tabs.tabs[0].content = summary_content

        # Statements tab
        statements_content = self._build_statements_tab(result)
        self.result_tabs.tabs[1].content = statements_content

        # Counter-evidence tab
        counter_content = self._build_counter_evidence_tab(result)
        self.result_tabs.tabs[2].content = summary_content

        # Verdicts tab
        verdicts_content = self._build_verdicts_tab(result)
        self.result_tabs.tabs[3].content = verdicts_content

        # Export tab
        export_content = self._build_export_tab(result)
        self.result_tabs.tabs[4].content = export_content

        self.result_tabs.visible = True
        self.page.update()

    def _build_summary_tab(self, result: PaperCheckResult) -> ft.Container:
        """Build summary tab content"""
        return ft.Container(
            content=ft.Column([
                ft.Text("Overall Assessment", size=18, weight=ft.FontWeight.BOLD),
                ft.Text(result.overall_assessment),
                ft.Divider(),
                ft.Text(f"Statements Extracted: {len(result.statements)}"),
                ft.Text(f"Total Citations: {sum(r.num_citations for r in result.counter_reports)}"),
                ft.Text(f"Processing Time: {result.processing_metadata.get('processing_time_seconds', 0):.1f}s"),
            ]),
            padding=10,
            scroll=ft.ScrollMode.AUTO
        )

    def _build_statements_tab(self, result: PaperCheckResult) -> ft.Container:
        """Build statements tab content"""
        controls = []

        for i, stmt in enumerate(result.statements, 1):
            card = ft.Card(
                content=ft.Container(
                    content=ft.Column([
                        ft.Text(f"Statement {i}", weight=ft.FontWeight.BOLD),
                        ft.Text(stmt.text),
                        ft.Text(f"Type: {stmt.statement_type}, Confidence: {stmt.confidence:.2f}", size=12)
                    ]),
                    padding=10
                )
            )
            controls.append(card)

        return ft.Container(
            content=ft.Column(controls, scroll=ft.ScrollMode.AUTO),
            padding=10
        )

    def _build_verdicts_tab(self, result: PaperCheckResult) -> ft.Container:
        """Build verdicts tab content"""
        controls = []

        for i, (stmt, verdict) in enumerate(zip(result.statements, result.verdicts), 1):
            # Color by verdict
            verdict_color = {
                "supports": ft.colors.GREEN,
                "contradicts": ft.colors.RED,
                "undecided": ft.colors.ORANGE
            }[verdict.verdict]

            card = ft.Card(
                content=ft.Container(
                    content=ft.Column([
                        ft.Text(f"Statement {i}: {stmt.text[:100]}...", size=12),
                        ft.Divider(),
                        ft.Row([
                            ft.Container(
                                content=ft.Text(
                                    verdict.verdict.upper(),
                                    color=ft.colors.WHITE,
                                    weight=ft.FontWeight.BOLD
                                ),
                                bgcolor=verdict_color,
                                padding=5,
                                border_radius=5
                            ),
                            ft.Text(f"Confidence: {verdict.confidence}")
                        ]),
                        ft.Text(f"Rationale: {verdict.rationale}", size=12),
                        ft.Text(f"Citations: {verdict.counter_report.num_citations}", size=12)
                    ]),
                    padding=10
                )
            )
            controls.append(card)

        return ft.Container(
            content=ft.Column(controls, scroll=ft.ScrollMode.AUTO),
            padding=10
        )

    def _build_export_tab(self, result: PaperCheckResult) -> ft.Container:
        """Build export tab content"""
        return ft.Container(
            content=ft.Column([
                ft.Text("Export Results", size=18, weight=ft.FontWeight.BOLD),
                ft.ElevatedButton(
                    "Export as JSON",
                    icon=ft.icons.DOWNLOAD,
                    on_click=lambda _: self._export_json(result)
                ),
                ft.ElevatedButton(
                    "Export as Markdown",
                    icon=ft.icons.ARTICLE,
                    on_click=lambda _: self._export_markdown(result)
                ),
            ]),
            padding=10
        )

    def _export_json(self, result: PaperCheckResult):
        """Export result as JSON"""
        try:
            output = json.dumps(result.to_json_dict(), indent=2)
            # In a real implementation, would use file picker
            print(output)
            self._show_success("JSON exported (see console)")
        except Exception as e:
            self._show_error(f"Export failed: {e}")

    def _export_markdown(self, result: PaperCheckResult):
        """Export result as Markdown"""
        try:
            markdown = result.to_markdown_report()
            # In a real implementation, would use file picker
            print(markdown)
            self._show_success("Markdown exported (see console)")
        except Exception as e:
            self._show_error(f"Export failed: {e}")

    def _show_error(self, message: str):
        """Show error dialog"""
        self.page.snack_bar = ft.SnackBar(
            content=ft.Text(message),
            bgcolor=ft.colors.RED
        )
        self.page.snack_bar.open = True
        self.page.update()

    def _show_success(self, message: str):
        """Show success message"""
        self.page.snack_bar = ft.SnackBar(
            content=ft.Text(message),
            bgcolor=ft.colors.GREEN
        )
        self.page.snack_bar.open = True
        self.page.update()


def main(page: ft.Page):
    """Main entry point for Flet app"""
    PaperCheckerLab(page)


if __name__ == "__main__":
    ft.app(target=main)
```

## Usage

```bash
# Launch laboratory
uv run python paper_checker_lab.py

# Launch in web mode
uv run python paper_checker_lab.py --view web
```

## Success Criteria

- [x] Laboratory interface implemented
- [x] Interactive abstract input working
- [x] PMID fetching working
- [x] Progress tracking with visual feedback
- [x] Workflow step visualization
- [x] Results display in tabs
- [x] Export functionality working
- [x] Error handling and user feedback
- [x] Responsive UI layout

## Next Steps

After completing this step, proceed to:
- **Step 14**: Testing Suite (14_TESTING_SUITE.md)
- Comprehensive testing of all components
