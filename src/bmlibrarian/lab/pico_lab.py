"""
PICO Lab - Interactive GUI for PICO component extraction from documents

Provides an interface for:
1. Entering a document ID
2. Displaying the document's title and abstract
3. Running PICO analysis and displaying results
"""

import flet as ft
import sys
from pathlib import Path
from typing import Optional, Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from bmlibrarian.agents import PICOAgent, AgentOrchestrator
from bmlibrarian.agents.pico_agent import PICOExtraction
from bmlibrarian.config import get_config
from bmlibrarian.database import fetch_documents_by_ids


class PICOLab:
    """Interactive lab for PICO component extraction."""

    def __init__(self):
        self.config = get_config()
        self.page: Optional[ft.Page] = None
        self.pico_agent: Optional[PICOAgent] = None
        self.orchestrator: Optional[AgentOrchestrator] = None
        self.controls = {}
        self.current_document: Optional[Dict[str, Any]] = None
        self.current_extraction: Optional[PICOExtraction] = None

    def main(self, page: ft.Page):
        """Main application entry point."""
        self.page = page
        page.title = "PICO Lab - BMLibrarian"
        page.window.width = 1200
        page.window.height = 900
        page.window.min_width = 1000
        page.window.min_height = 700
        page.window.resizable = True
        page.theme_mode = ft.ThemeMode.LIGHT

        # Initialize agent
        self._init_agent()

        # Create layout
        self._create_layout()

    def _init_agent(self):
        """Initialize PICOAgent with orchestrator."""
        try:
            # Initialize orchestrator
            self.orchestrator = AgentOrchestrator(max_workers=2)

            # Get model from config
            model = self.config.get_model('pico_agent') or "gpt-oss:20b"
            agent_config = self.config.get_agent_config('pico') or {}
            host = self.config.get_ollama_config()['host']

            print(f"🚀 Initializing PICOAgent with model: {model}")

            self.pico_agent = PICOAgent(
                model=model,
                host=host,
                temperature=agent_config.get('temperature', 0.1),
                top_p=agent_config.get('top_p', 0.9),
                max_tokens=agent_config.get('max_tokens', 2000),
                orchestrator=self.orchestrator,
                show_model_info=True
            )
        except Exception as e:
            print(f"Warning: Failed to initialize PICOAgent: {e}")
            self.pico_agent = None

    def _create_layout(self):
        """Create the main application layout."""

        # Header
        header = ft.Container(
            ft.Column([
                ft.Text(
                    "PICO Laboratory",
                    size=28,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.BLUE_700
                ),
                ft.Text(
                    "Extract Population, Intervention, Comparison, and Outcome components from research papers",
                    size=14,
                    color=ft.Colors.GREY_600
                )
            ]),
            margin=ft.margin.only(bottom=20)
        )

        # Document input panel
        input_panel = self._create_input_panel()

        # Document display panel
        document_panel = self._create_document_panel()

        # PICO results panel
        pico_panel = self._create_pico_panel()

        # Main layout
        main_content = ft.Column([
            header,
            ft.Divider(),
            input_panel,
            ft.Divider(),
            ft.Row([
                ft.Container(
                    document_panel,
                    width=500,
                    padding=ft.padding.all(15),
                    bgcolor=ft.Colors.GREY_50,
                    border_radius=10
                ),
                ft.VerticalDivider(width=20),
                ft.Container(
                    pico_panel,
                    expand=True,
                    padding=ft.padding.all(15),
                    bgcolor=ft.Colors.BLUE_50,
                    border_radius=10
                )
            ], expand=True, spacing=10)
        ],
        spacing=10,
        expand=True
        )

        self.page.add(
            ft.Container(
                main_content,
                padding=ft.padding.all(20),
                expand=True
            )
        )

    def _create_input_panel(self) -> ft.Container:
        """Create document input panel."""

        self.controls['doc_id_input'] = ft.TextField(
            label="Document ID",
            hint_text="Enter document ID (e.g., 12345)",
            width=200,
            input_filter=ft.NumbersOnlyInputFilter(),
            on_submit=lambda _: self._load_document(None)
        )

        self.controls['load_button'] = ft.ElevatedButton(
            "Load & Analyze",
            icon=ft.Icons.SEARCH,
            on_click=self._load_document,
            style=ft.ButtonStyle(
                bgcolor=ft.Colors.GREEN_600,
                color=ft.Colors.WHITE
            ),
            height=40,
            width=150
        )

        self.controls['clear_button'] = ft.ElevatedButton(
            "Clear",
            icon=ft.Icons.CLEAR,
            on_click=self._clear_all,
            height=40,
            width=100
        )

        self.controls['status_text'] = ft.Text(
            "Ready",
            size=12,
            color=ft.Colors.GREY_600
        )

        return ft.Container(
            ft.Row([
                self.controls['doc_id_input'],
                self.controls['load_button'],
                self.controls['clear_button'],
                ft.Container(width=20),
                self.controls['status_text']
            ],
            alignment=ft.MainAxisAlignment.START,
            vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.padding.all(10)
        )

    def _create_document_panel(self) -> ft.Column:
        """Create document display panel."""

        self.controls['doc_title'] = ft.Text(
            "No document loaded",
            size=16,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.GREY_700
        )

        self.controls['doc_metadata'] = ft.Text(
            "",
            size=12,
            color=ft.Colors.GREY_600
        )

        self.controls['doc_abstract'] = ft.TextField(
            label="Abstract",
            multiline=True,
            min_lines=15,
            max_lines=20,
            read_only=True,
            bgcolor=ft.Colors.WHITE,
            border_color=ft.Colors.GREY_300
        )

        return ft.Column([
            ft.Text("Document", size=18, weight=ft.FontWeight.BOLD),
            ft.Container(height=10),
            self.controls['doc_title'],
            ft.Container(height=5),
            self.controls['doc_metadata'],
            ft.Container(height=10),
            self.controls['doc_abstract']
        ],
        spacing=5
        )

    def _create_pico_panel(self) -> ft.Column:
        """Create PICO results display panel."""

        # Overall info
        self.controls['pico_confidence'] = ft.Text(
            "",
            size=14,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.GREEN_700
        )

        self.controls['study_info'] = ft.Text(
            "",
            size=12,
            color=ft.Colors.GREY_700
        )

        # Population
        self.controls['population'] = ft.TextField(
            label="Population (P)",
            hint_text="Population will appear here...",
            multiline=True,
            min_lines=3,
            max_lines=5,
            read_only=True,
            bgcolor=ft.Colors.WHITE,
            border_color=ft.Colors.BLUE_400
        )

        self.controls['population_conf'] = ft.Text(
            "",
            size=11,
            color=ft.Colors.GREY_600
        )

        # Intervention
        self.controls['intervention'] = ft.TextField(
            label="Intervention (I)",
            hint_text="Intervention will appear here...",
            multiline=True,
            min_lines=3,
            max_lines=5,
            read_only=True,
            bgcolor=ft.Colors.WHITE,
            border_color=ft.Colors.GREEN_400
        )

        self.controls['intervention_conf'] = ft.Text(
            "",
            size=11,
            color=ft.Colors.GREY_600
        )

        # Comparison
        self.controls['comparison'] = ft.TextField(
            label="Comparison (C)",
            hint_text="Comparison will appear here...",
            multiline=True,
            min_lines=3,
            max_lines=5,
            read_only=True,
            bgcolor=ft.Colors.WHITE,
            border_color=ft.Colors.ORANGE_400
        )

        self.controls['comparison_conf'] = ft.Text(
            "",
            size=11,
            color=ft.Colors.GREY_600
        )

        # Outcome
        self.controls['outcome'] = ft.TextField(
            label="Outcome (O)",
            hint_text="Outcome will appear here...",
            multiline=True,
            min_lines=3,
            max_lines=5,
            read_only=True,
            bgcolor=ft.Colors.WHITE,
            border_color=ft.Colors.PURPLE_400
        )

        self.controls['outcome_conf'] = ft.Text(
            "",
            size=11,
            color=ft.Colors.GREY_600
        )

        return ft.Column([
            ft.Text("PICO Analysis", size=18, weight=ft.FontWeight.BOLD),
            self.controls['pico_confidence'],
            self.controls['study_info'],
            ft.Divider(height=15),

            self.controls['population'],
            self.controls['population_conf'],
            ft.Container(height=10),

            self.controls['intervention'],
            self.controls['intervention_conf'],
            ft.Container(height=10),

            self.controls['comparison'],
            self.controls['comparison_conf'],
            ft.Container(height=10),

            self.controls['outcome'],
            self.controls['outcome_conf']
        ],
        spacing=5,
        scroll=ft.ScrollMode.AUTO
        )

    def _load_document(self, e):
        """Load document and perform PICO analysis."""
        doc_id_str = self.controls['doc_id_input'].value

        if not doc_id_str or not doc_id_str.strip():
            self._show_error_dialog("Please enter a document ID.")
            return

        try:
            doc_id = int(doc_id_str)
        except ValueError:
            self._show_error_dialog("Invalid document ID. Please enter a number.")
            return

        # Update status
        self.controls['status_text'].value = f"Loading document {doc_id}..."
        self.controls['status_text'].color = ft.Colors.BLUE_600
        self.page.update()

        try:
            # Fetch document from database
            documents = fetch_documents_by_ids({doc_id})

            if not documents:
                self._show_error_dialog(f"Document {doc_id} not found in database.")
                self.controls['status_text'].value = "Ready"
                self.controls['status_text'].color = ft.Colors.GREY_600
                self.page.update()
                return

            self.current_document = documents[0]

            # Display document
            self._display_document()

            # Update status
            self.controls['status_text'].value = "Running PICO extraction..."
            self.controls['status_text'].color = ft.Colors.BLUE_600
            self.page.update()

            # Perform PICO extraction
            if not self.pico_agent:
                self._show_error_dialog("PICO Agent not initialized. Cannot perform analysis.")
                self.controls['status_text'].value = "Agent unavailable"
                self.controls['status_text'].color = ft.Colors.RED_600
                self.page.update()
                return

            extraction = self.pico_agent.extract_pico_from_document(
                document=self.current_document,
                min_confidence=0.0  # Show all extractions
            )

            if extraction:
                self.current_extraction = extraction
                self._display_pico_results()
                self.controls['status_text'].value = f"✅ Analysis complete (confidence: {extraction.extraction_confidence:.1%})"
                self.controls['status_text'].color = ft.Colors.GREEN_600
            else:
                self._show_error_dialog("PICO extraction failed or returned no results.")
                self.controls['status_text'].value = "Extraction failed"
                self.controls['status_text'].color = ft.Colors.RED_600

        except Exception as ex:
            self._show_error_dialog(f"Error: {str(ex)}")
            self.controls['status_text'].value = f"Error: {str(ex)[:30]}..."
            self.controls['status_text'].color = ft.Colors.RED_600

        self.page.update()

    def _display_document(self):
        """Display the loaded document."""
        if not self.current_document:
            return

        # Title
        title = self.current_document.get('title', 'Untitled')
        self.controls['doc_title'].value = title

        # Metadata
        metadata_parts = []
        if self.current_document.get('pmid'):
            metadata_parts.append(f"PMID: {self.current_document['pmid']}")
        if self.current_document.get('doi'):
            metadata_parts.append(f"DOI: {self.current_document['doi']}")
        if self.current_document.get('publication_date'):
            metadata_parts.append(f"Date: {self.current_document['publication_date']}")
        if self.current_document.get('source_name'):
            metadata_parts.append(f"Source: {self.current_document['source_name']}")

        self.controls['doc_metadata'].value = " | ".join(metadata_parts)

        # Abstract
        abstract = self.current_document.get('abstract', 'No abstract available')
        self.controls['doc_abstract'].value = abstract

        self.page.update()

    def _display_pico_results(self):
        """Display PICO extraction results."""
        if not self.current_extraction:
            return

        ex = self.current_extraction

        # Overall confidence
        self.controls['pico_confidence'].value = f"Overall Confidence: {ex.extraction_confidence:.1%}"
        if ex.extraction_confidence >= 0.8:
            self.controls['pico_confidence'].color = ft.Colors.GREEN_700
        elif ex.extraction_confidence >= 0.6:
            self.controls['pico_confidence'].color = ft.Colors.ORANGE_700
        else:
            self.controls['pico_confidence'].color = ft.Colors.RED_700

        # Study info
        study_parts = []
        if ex.study_type:
            study_parts.append(f"Study Type: {ex.study_type}")
        if ex.sample_size:
            study_parts.append(f"Sample Size: {ex.sample_size}")
        self.controls['study_info'].value = " | ".join(study_parts) if study_parts else ""

        # Population
        self.controls['population'].value = ex.population
        if ex.population_confidence:
            self.controls['population_conf'].value = f"Confidence: {ex.population_confidence:.1%}"
        else:
            self.controls['population_conf'].value = ""

        # Intervention
        self.controls['intervention'].value = ex.intervention
        if ex.intervention_confidence:
            self.controls['intervention_conf'].value = f"Confidence: {ex.intervention_confidence:.1%}"
        else:
            self.controls['intervention_conf'].value = ""

        # Comparison
        self.controls['comparison'].value = ex.comparison
        if ex.comparison_confidence:
            self.controls['comparison_conf'].value = f"Confidence: {ex.comparison_confidence:.1%}"
        else:
            self.controls['comparison_conf'].value = ""

        # Outcome
        self.controls['outcome'].value = ex.outcome
        if ex.outcome_confidence:
            self.controls['outcome_conf'].value = f"Confidence: {ex.outcome_confidence:.1%}"
        else:
            self.controls['outcome_conf'].value = ""

        self.page.update()

    def _clear_all(self, e):
        """Clear all fields."""
        self.controls['doc_id_input'].value = ""
        self.controls['status_text'].value = "Ready"
        self.controls['status_text'].color = ft.Colors.GREY_600

        self.controls['doc_title'].value = "No document loaded"
        self.controls['doc_metadata'].value = ""
        self.controls['doc_abstract'].value = ""

        self.controls['pico_confidence'].value = ""
        self.controls['study_info'].value = ""
        self.controls['population'].value = ""
        self.controls['population_conf'].value = ""
        self.controls['intervention'].value = ""
        self.controls['intervention_conf'].value = ""
        self.controls['comparison'].value = ""
        self.controls['comparison_conf'].value = ""
        self.controls['outcome'].value = ""
        self.controls['outcome_conf'].value = ""

        self.current_document = None
        self.current_extraction = None

        self.page.update()

    def _show_error_dialog(self, message: str):
        """Show error dialog."""
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Error", color=ft.Colors.RED_700),
            content=ft.Text(message),
            actions=[
                ft.TextButton("OK", on_click=lambda _: self._close_dialog())
            ]
        )
        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()

    def _show_success_dialog(self, message: str):
        """Show success dialog."""
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Success", color=ft.Colors.GREEN_700),
            content=ft.Text(message),
            actions=[
                ft.TextButton("OK", on_click=lambda _: self._close_dialog())
            ]
        )
        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()

    def _close_dialog(self):
        """Close the current dialog."""
        if self.page.overlay:
            self.page.overlay.clear()
            self.page.update()


def run_pico_lab():
    """Run the PICO Lab application."""
    app = PICOLab()
    ft.app(target=app.main, view=ft.FLET_APP)


if __name__ == "__main__":
    run_pico_lab()
