"""
PRISMA 2020 Lab - Interactive GUI for systematic review reporting quality assessment

Provides an interface for:
1. Entering a document ID
2. Checking if the document is suitable for PRISMA assessment (systematic review check)
3. Displaying the document's title and abstract
4. Running PRISMA 2020 compliance assessment and displaying results for all 27 items
"""

import flet as ft
import sys
from pathlib import Path
from typing import Optional, Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from bmlibrarian.agents import PRISMA2020Agent, AgentOrchestrator
from bmlibrarian.agents.prisma2020_agent import PRISMA2020Assessment, SuitabilityAssessment
from bmlibrarian.config import get_config
from bmlibrarian.database import fetch_documents_by_ids


class PRISMA2020Lab:
    """Interactive lab for PRISMA 2020 compliance assessment."""

    def __init__(self):
        self.config = get_config()
        self.page: Optional[ft.Page] = None
        self.assessment_agent: Optional[PRISMA2020Agent] = None
        self.orchestrator: Optional[AgentOrchestrator] = None
        self.controls = {}
        self.current_document: Optional[Dict[str, Any]] = None
        self.current_suitability: Optional[SuitabilityAssessment] = None
        self.current_assessment: Optional[PRISMA2020Assessment] = None

    def main(self, page: ft.Page):
        """Main application entry point."""
        self.page = page
        page.title = "PRISMA 2020 Lab - BMLibrarian"
        page.window.width = 1600
        page.window.height = 1000
        page.window.min_width = 1400
        page.window.min_height = 800
        page.window.resizable = True
        page.theme_mode = ft.ThemeMode.LIGHT

        # Initialize agent
        self._init_agent()

        # Create layout
        self._create_layout()

    def _init_agent(self):
        """Initialize PRISMA2020Agent with orchestrator."""
        try:
            # Initialize orchestrator
            self.orchestrator = AgentOrchestrator(max_workers=2)

            # Get model from config (use general model if no specific PRISMA config)
            model = self.config.get_model('prisma2020_agent') or self.config.get_model('study_assessment_agent') or "gpt-oss:20b"
            agent_config = self.config.get_agent_config('prisma2020') or self.config.get_agent_config('study_assessment') or {}
            host = self.config.get_ollama_config()['host']

            print(f"🚀 Initializing PRISMA2020Agent with model: {model}")

            self.assessment_agent = PRISMA2020Agent(
                model=model,
                host=host,
                temperature=agent_config.get('temperature', 0.1),
                top_p=agent_config.get('top_p', 0.9),
                max_tokens=agent_config.get('max_tokens', 4000),
                orchestrator=self.orchestrator,
                show_model_info=True
            )
        except Exception as e:
            print(f"Warning: Failed to initialize PRISMA2020Agent: {e}")
            self.assessment_agent = None

    def _create_layout(self):
        """Create the main application layout."""

        # Header
        header = ft.Container(
            ft.Column([
                ft.Text(
                    "PRISMA 2020 Compliance Laboratory",
                    size=28,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.PURPLE_700
                ),
                ft.Text(
                    "Assess systematic reviews and meta-analyses against PRISMA 2020 reporting guidelines (27-item checklist)",
                    size=14,
                    color=ft.Colors.GREY_600
                )
            ]),
            margin=ft.margin.only(bottom=20)
        )

        # Document input panel
        input_panel = self._create_input_panel()

        # Document display panel (left side)
        document_panel = self._create_document_panel()

        # Assessment results panel (right side)
        assessment_panel = self._create_assessment_panel()

        # Main layout with scrollable content
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
                    assessment_panel,
                    expand=True,
                    padding=ft.padding.all(15),
                    bgcolor=ft.Colors.PURPLE_50,
                    border_radius=10
                )
            ], expand=True, spacing=10)
        ],
        spacing=10,
        expand=True,
        scroll=ft.ScrollMode.AUTO
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

        # Model selection
        available_models = self._get_available_models()
        current_model = self.config.get_model('prisma2020_agent') or self.config.get_model('study_assessment_agent') or "gpt-oss:20b"

        self.controls['model_selector'] = ft.Dropdown(
            label="Assessment Model",
            value=current_model if current_model in available_models else (available_models[0] if available_models else ""),
            options=[ft.dropdown.Option(model) for model in available_models],
            width=350,
            on_change=self._on_model_change
        )

        self.controls['refresh_models_button'] = ft.IconButton(
            icon=ft.Icons.REFRESH,
            tooltip="Refresh available models",
            on_click=self._refresh_models
        )

        self.controls['doc_id_input'] = ft.TextField(
            label="Document ID",
            hint_text="Enter document ID (e.g., 12345)",
            width=200,
            input_filter=ft.NumbersOnlyInputFilter(),
            on_submit=lambda _: self._load_and_assess(None)
        )

        self.controls['load_button'] = ft.ElevatedButton(
            "Load & Assess",
            icon=ft.Icons.SEARCH,
            on_click=self._load_and_assess,
            style=ft.ButtonStyle(
                bgcolor=ft.Colors.PURPLE_600,
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
            "Ready - Enter a document ID to begin PRISMA 2020 assessment",
            size=12,
            color=ft.Colors.GREY_600
        )

        return ft.Container(
            ft.Column([
                ft.Row([
                    self.controls['model_selector'],
                    self.controls['refresh_models_button']
                ], spacing=10),
                ft.Row([
                    self.controls['doc_id_input'],
                    self.controls['load_button'],
                    self.controls['clear_button']
                ], spacing=10),
                self.controls['status_text']
            ], spacing=10),
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

        self.controls['suitability_card'] = ft.Container(
            ft.Column([
                ft.Text(
                    "Suitability Check",
                    size=14,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.GREY_700
                ),
                ft.Text(
                    "Document suitability assessment will appear here.",
                    size=12,
                    color=ft.Colors.GREY_600
                )
            ], spacing=5),
            padding=ft.padding.all(10),
            bgcolor=ft.Colors.GREY_100,
            border_radius=5,
            border=ft.border.all(1, ft.Colors.GREY_300)
        )

        self.controls['doc_abstract'] = ft.Text(
            "Load a document to check if it's a systematic review and assess PRISMA 2020 compliance.",
            size=13,
            color=ft.Colors.GREY_700
        )

        return ft.Column([
            ft.Text("Document", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.GREY_800),
            ft.Divider(),
            self.controls['doc_title'],
            self.controls['doc_metadata'],
            ft.Divider(),
            self.controls['suitability_card'],
            ft.Divider(),
            ft.Text("Abstract", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.GREY_700),
            ft.Container(
                self.controls['doc_abstract'],
                height=300,
                padding=ft.padding.all(10),
                bgcolor=ft.Colors.WHITE,
                border_radius=5,
                border=ft.border.all(1, ft.Colors.GREY_300)
            )
        ], spacing=10, scroll=ft.ScrollMode.AUTO)

    def _create_assessment_panel(self) -> ft.Column:
        """Create PRISMA assessment results panel."""

        self.controls['assessment_header'] = ft.Text(
            "PRISMA 2020 Compliance Assessment",
            size=18,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.GREY_800
        )

        self.controls['assessment_results'] = ft.Column(
            [
                ft.Text(
                    "Assessment results will appear here after loading a suitable systematic review.",
                    size=13,
                    color=ft.Colors.GREY_600
                )
            ],
            spacing=10,
            scroll=ft.ScrollMode.AUTO
        )

        return ft.Column([
            self.controls['assessment_header'],
            ft.Divider(),
            ft.Container(
                self.controls['assessment_results'],
                expand=True,
                padding=ft.padding.all(10),
                bgcolor=ft.Colors.WHITE,
                border_radius=5,
                border=ft.border.all(1, ft.Colors.GREY_300)
            )
        ], spacing=10, expand=True)

    def _get_available_models(self) -> list[str]:
        """Get list of available Ollama models."""
        if not self.assessment_agent:
            return ["gpt-oss:20b"]

        try:
            models = self.assessment_agent.get_available_models()
            return models if models else ["gpt-oss:20b"]
        except Exception as e:
            print(f"Error fetching models: {e}")
            return ["gpt-oss:20b"]

    def _refresh_models(self, e):
        """Refresh available models list."""
        self.controls['status_text'].value = "Refreshing models..."
        self.page.update()

        models = self._get_available_models()
        self.controls['model_selector'].options = [
            ft.dropdown.Option(model) for model in models
        ]

        self.controls['status_text'].value = f"Found {len(models)} models"
        self.page.update()

    def _on_model_change(self, e):
        """Handle model selection change."""
        new_model = self.controls['model_selector'].value
        print(f"Switching to model: {new_model}")

        # Reinitialize agent with new model
        try:
            agent_config = self.config.get_agent_config('prisma2020') or self.config.get_agent_config('study_assessment') or {}
            host = self.config.get_ollama_config()['host']

            self.assessment_agent = PRISMA2020Agent(
                model=new_model,
                host=host,
                temperature=agent_config.get('temperature', 0.1),
                top_p=agent_config.get('top_p', 0.9),
                max_tokens=agent_config.get('max_tokens', 4000),
                orchestrator=self.orchestrator,
                show_model_info=False
            )

            self.controls['status_text'].value = f"Switched to {new_model}"
        except Exception as err:
            self.controls['status_text'].value = f"Error switching model: {err}"

        self.page.update()

    def _load_and_assess(self, e):
        """Load document, check suitability, and run PRISMA assessment."""
        doc_id = self.controls['doc_id_input'].value

        if not doc_id:
            self.controls['status_text'].value = "Please enter a document ID"
            self.controls['status_text'].color = ft.Colors.RED_600
            self.page.update()
            return

        if not self.assessment_agent:
            self.controls['status_text'].value = "Assessment agent not initialized"
            self.controls['status_text'].color = ft.Colors.RED_600
            self.page.update()
            return

        # Update status
        self.controls['status_text'].value = f"Loading document {doc_id}..."
        self.controls['status_text'].color = ft.Colors.BLUE_600
        self.controls['load_button'].disabled = True
        self.page.update()

        try:
            # Fetch document from database
            documents = fetch_documents_by_ids([int(doc_id)])

            if not documents:
                self.controls['status_text'].value = f"Document {doc_id} not found"
                self.controls['status_text'].color = ft.Colors.RED_600
                self.controls['load_button'].disabled = False
                self.page.update()
                return

            self.current_document = documents[0]

            # Display document
            self._display_document()

            # Check suitability first
            self.controls['status_text'].value = "Checking if document is a systematic review..."
            self.page.update()

            self.current_suitability = self.assessment_agent.check_suitability(self.current_document)

            if not self.current_suitability:
                self.controls['status_text'].value = "Suitability check failed"
                self.controls['status_text'].color = ft.Colors.RED_600
                self.controls['load_button'].disabled = False
                self.page.update()
                return

            # Display suitability results
            self._display_suitability()

            # If suitable, run full PRISMA assessment
            if self.current_suitability.is_suitable:
                self.controls['status_text'].value = "Running PRISMA 2020 compliance assessment..."
                self.page.update()

                self._run_assessment()
            else:
                self.controls['status_text'].value = "Document not suitable for PRISMA assessment"
                self.controls['status_text'].color = ft.Colors.ORANGE_600
                self.controls['load_button'].disabled = False

                # Clear assessment results
                self.controls['assessment_results'].controls = [
                    ft.Text(
                        "This document is not a systematic review or meta-analysis. "
                        "PRISMA 2020 assessment cannot be performed.",
                        size=13,
                        color=ft.Colors.ORANGE_700,
                        weight=ft.FontWeight.BOLD
                    )
                ]

                self.page.update()

        except Exception as err:
            self.controls['status_text'].value = f"Error: {err}"
            self.controls['status_text'].color = ft.Colors.RED_600
            self.controls['load_button'].disabled = False
            self.page.update()

    def _display_document(self):
        """Display loaded document."""
        if not self.current_document:
            return

        # Update document title
        self.controls['doc_title'].value = self.current_document.get('title', 'Untitled')

        # Update metadata
        metadata_parts = []
        if self.current_document.get('pmid'):
            metadata_parts.append(f"PMID: {self.current_document['pmid']}")
        if self.current_document.get('doi'):
            metadata_parts.append(f"DOI: {self.current_document['doi']}")
        if self.current_document.get('id'):
            metadata_parts.append(f"ID: {self.current_document['id']}")

        self.controls['doc_metadata'].value = " | ".join(metadata_parts)

        # Update abstract
        abstract = self.current_document.get('abstract', 'No abstract available')
        self.controls['doc_abstract'].value = abstract

        self.page.update()

    def _display_suitability(self):
        """Display suitability assessment results."""
        if not self.current_suitability:
            return

        suitability_icon = "✓" if self.current_suitability.is_suitable else "✗"
        suitability_color = ft.Colors.GREEN_700 if self.current_suitability.is_suitable else ft.Colors.RED_700

        suitability_content = ft.Column([
            ft.Text(
                f"{suitability_icon} Suitability Check",
                size=14,
                weight=ft.FontWeight.BOLD,
                color=suitability_color
            ),
            ft.Divider(height=5),
            ft.Text(f"Document Type: {self.current_suitability.document_type}", size=12),
            ft.Text(f"Systematic Review: {'Yes' if self.current_suitability.is_systematic_review else 'No'}", size=12),
            ft.Text(f"Meta-Analysis: {'Yes' if self.current_suitability.is_meta_analysis else 'No'}", size=12),
            ft.Text(f"Confidence: {self.current_suitability.confidence:.1%}", size=12),
            ft.Divider(height=5),
            ft.Text(
                f"Rationale: {self.current_suitability.rationale}",
                size=12,
                color=ft.Colors.GREY_700
            )
        ], spacing=5)

        self.controls['suitability_card'].content = suitability_content
        self.controls['suitability_card'].bgcolor = ft.Colors.GREEN_50 if self.current_suitability.is_suitable else ft.Colors.RED_50
        self.controls['suitability_card'].border = ft.border.all(2, suitability_color)

        self.page.update()

    def _run_assessment(self):
        """Run PRISMA 2020 compliance assessment."""
        if not self.current_document or not self.assessment_agent:
            return

        try:
            # Run PRISMA assessment (skip suitability check since we already did it)
            self.current_assessment = self.assessment_agent.assess_prisma_compliance(
                self.current_document,
                skip_suitability_check=True
            )

            if not self.current_assessment:
                self.controls['status_text'].value = "Assessment failed"
                self.controls['status_text'].color = ft.Colors.RED_600
                self.controls['load_button'].disabled = False
                self.page.update()
                return

            # Display assessment results
            self._display_assessment()

            self.controls['status_text'].value = f"Assessment complete - {self.current_assessment.overall_compliance_percentage:.1f}% compliance"
            self.controls['status_text'].color = ft.Colors.GREEN_600
            self.controls['load_button'].disabled = False
            self.page.update()

        except Exception as err:
            self.controls['status_text'].value = f"Assessment error: {err}"
            self.controls['status_text'].color = ft.Colors.RED_600
            self.controls['load_button'].disabled = False
            self.page.update()

    def _display_assessment(self):
        """Display PRISMA assessment results."""
        if not self.current_assessment:
            return

        assessment_controls = []

        # Overall compliance summary
        compliance_category = self.current_assessment.get_compliance_category()
        compliance_color = self._get_compliance_color(self.current_assessment.overall_compliance_percentage)

        summary_card = ft.Container(
            ft.Column([
                ft.Text(
                    "Overall Compliance Summary",
                    size=16,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.GREY_800
                ),
                ft.Divider(),
                ft.Text(
                    f"Compliance Score: {self.current_assessment.overall_compliance_percentage:.1f}%",
                    size=20,
                    weight=ft.FontWeight.BOLD,
                    color=compliance_color
                ),
                ft.Text(f"Category: {compliance_category}", size=14, color=compliance_color),
                ft.Text(f"Confidence: {self.current_assessment.overall_confidence:.1%}", size=12),
                ft.Divider(),
                ft.Row([
                    ft.Container(
                        ft.Column([
                            ft.Text("✓✓", size=20, color=ft.Colors.GREEN_600),
                            ft.Text(str(self.current_assessment.fully_reported_items), size=16, weight=ft.FontWeight.BOLD),
                            ft.Text("Fully Reported", size=10)
                        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                        padding=ft.padding.all(10),
                        bgcolor=ft.Colors.GREEN_50,
                        border_radius=5
                    ),
                    ft.Container(
                        ft.Column([
                            ft.Text("✓", size=20, color=ft.Colors.ORANGE_600),
                            ft.Text(str(self.current_assessment.partially_reported_items), size=16, weight=ft.FontWeight.BOLD),
                            ft.Text("Partial", size=10)
                        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                        padding=ft.padding.all(10),
                        bgcolor=ft.Colors.ORANGE_50,
                        border_radius=5
                    ),
                    ft.Container(
                        ft.Column([
                            ft.Text("✗", size=20, color=ft.Colors.RED_600),
                            ft.Text(str(self.current_assessment.not_reported_items), size=16, weight=ft.FontWeight.BOLD),
                            ft.Text("Not Reported", size=10)
                        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                        padding=ft.padding.all(10),
                        bgcolor=ft.Colors.RED_50,
                        border_radius=5
                    )
                ], spacing=10)
            ], spacing=10),
            padding=ft.padding.all(15),
            bgcolor=ft.Colors.BLUE_50,
            border_radius=10,
            border=ft.border.all(2, ft.Colors.BLUE_300)
        )

        assessment_controls.append(summary_card)
        assessment_controls.append(ft.Divider(height=20))

        # PRISMA 2020 items breakdown by section
        sections = [
            ("TITLE & ABSTRACT", [
                ("Item 1: Title", self.current_assessment.title_score, self.current_assessment.title_explanation),
                ("Item 2: Abstract", self.current_assessment.abstract_score, self.current_assessment.abstract_explanation)
            ]),
            ("INTRODUCTION", [
                ("Item 3: Rationale", self.current_assessment.rationale_score, self.current_assessment.rationale_explanation),
                ("Item 4: Objectives", self.current_assessment.objectives_score, self.current_assessment.objectives_explanation)
            ]),
            ("METHODS (Items 5-15)", [
                ("Item 5: Eligibility criteria", self.current_assessment.eligibility_criteria_score, self.current_assessment.eligibility_criteria_explanation),
                ("Item 6: Information sources", self.current_assessment.information_sources_score, self.current_assessment.information_sources_explanation),
                ("Item 7: Search strategy", self.current_assessment.search_strategy_score, self.current_assessment.search_strategy_explanation),
                ("Item 8: Selection process", self.current_assessment.selection_process_score, self.current_assessment.selection_process_explanation),
                ("Item 9: Data collection", self.current_assessment.data_collection_score, self.current_assessment.data_collection_explanation),
                ("Item 10: Data items", self.current_assessment.data_items_score, self.current_assessment.data_items_explanation),
                ("Item 11: Risk of bias", self.current_assessment.risk_of_bias_score, self.current_assessment.risk_of_bias_explanation),
                ("Item 12: Effect measures", self.current_assessment.effect_measures_score, self.current_assessment.effect_measures_explanation),
                ("Item 13: Synthesis methods", self.current_assessment.synthesis_methods_score, self.current_assessment.synthesis_methods_explanation),
                ("Item 14: Reporting bias assessment", self.current_assessment.reporting_bias_assessment_score, self.current_assessment.reporting_bias_assessment_explanation),
                ("Item 15: Certainty assessment", self.current_assessment.certainty_assessment_score, self.current_assessment.certainty_assessment_explanation)
            ]),
            ("RESULTS (Items 16-22)", [
                ("Item 16: Study selection", self.current_assessment.study_selection_score, self.current_assessment.study_selection_explanation),
                ("Item 17: Study characteristics", self.current_assessment.study_characteristics_score, self.current_assessment.study_characteristics_explanation),
                ("Item 18: Risk of bias results", self.current_assessment.risk_of_bias_results_score, self.current_assessment.risk_of_bias_results_explanation),
                ("Item 19: Individual studies results", self.current_assessment.individual_studies_results_score, self.current_assessment.individual_studies_results_explanation),
                ("Item 20: Synthesis results", self.current_assessment.synthesis_results_score, self.current_assessment.synthesis_results_explanation),
                ("Item 21: Reporting biases", self.current_assessment.reporting_biases_results_score, self.current_assessment.reporting_biases_results_explanation),
                ("Item 22: Certainty of evidence", self.current_assessment.certainty_of_evidence_score, self.current_assessment.certainty_of_evidence_explanation)
            ]),
            ("DISCUSSION (Items 23-25)", [
                ("Item 23: Discussion", self.current_assessment.discussion_score, self.current_assessment.discussion_explanation),
                ("Item 24: Limitations", self.current_assessment.limitations_score, self.current_assessment.limitations_explanation),
                ("Item 25: Conclusions", self.current_assessment.conclusions_score, self.current_assessment.conclusions_explanation)
            ]),
            ("OTHER INFORMATION (Items 26-27)", [
                ("Item 26: Registration", self.current_assessment.registration_score, self.current_assessment.registration_explanation),
                ("Item 27: Support/Funding", self.current_assessment.support_score, self.current_assessment.support_explanation)
            ])
        ]

        for section_title, items in sections:
            section_controls = [
                ft.Text(
                    section_title,
                    size=15,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.PURPLE_700
                ),
                ft.Divider(height=5)
            ]

            for item_name, score, explanation in items:
                item_card = self._create_item_card(item_name, score, explanation)
                section_controls.append(item_card)

            section_container = ft.Container(
                ft.Column(section_controls, spacing=8),
                padding=ft.padding.all(10),
                bgcolor=ft.Colors.GREY_50,
                border_radius=8
            )

            assessment_controls.append(section_container)
            assessment_controls.append(ft.Container(height=10))  # Spacing

        self.controls['assessment_results'].controls = assessment_controls
        self.page.update()

    def _create_item_card(self, item_name: str, score: float, explanation: str) -> ft.Container:
        """Create a card for a single PRISMA item."""
        # Determine symbol and color
        if score >= 1.9:
            symbol = "✓✓"
            symbol_color = ft.Colors.GREEN_600
            bg_color = ft.Colors.GREEN_50
        elif score >= 0.9:
            symbol = "✓"
            symbol_color = ft.Colors.ORANGE_600
            bg_color = ft.Colors.ORANGE_50
        else:
            symbol = "✗"
            symbol_color = ft.Colors.RED_600
            bg_color = ft.Colors.RED_50

        return ft.Container(
            ft.Row([
                ft.Container(
                    ft.Text(symbol, size=16, color=symbol_color, weight=ft.FontWeight.BOLD),
                    width=30
                ),
                ft.Column([
                    ft.Text(f"{item_name} ({score:.1f}/2.0)", size=13, weight=ft.FontWeight.BOLD),
                    ft.Text(explanation, size=11, color=ft.Colors.GREY_700)
                ], expand=True, spacing=3)
            ], spacing=10),
            padding=ft.padding.all(10),
            bgcolor=bg_color,
            border_radius=5,
            border=ft.border.all(1, symbol_color)
        )

    def _get_compliance_color(self, percentage: float) -> str:
        """Get color based on compliance percentage."""
        if percentage >= 90:
            return ft.Colors.GREEN_700
        elif percentage >= 75:
            return ft.Colors.LIGHT_GREEN_700
        elif percentage >= 60:
            return ft.Colors.ORANGE_700
        elif percentage >= 40:
            return ft.Colors.DEEP_ORANGE_700
        else:
            return ft.Colors.RED_700

    def _clear_all(self, e):
        """Clear all inputs and results."""
        self.controls['doc_id_input'].value = ""
        self.controls['doc_title'].value = "No document loaded"
        self.controls['doc_metadata'].value = ""
        self.controls['doc_abstract'].value = "Load a document to check if it's a systematic review and assess PRISMA 2020 compliance."

        # Reset suitability card
        self.controls['suitability_card'].content = ft.Column([
            ft.Text(
                "Suitability Check",
                size=14,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.GREY_700
            ),
            ft.Text(
                "Document suitability assessment will appear here.",
                size=12,
                color=ft.Colors.GREY_600
            )
        ], spacing=5)
        self.controls['suitability_card'].bgcolor = ft.Colors.GREY_100
        self.controls['suitability_card'].border = ft.border.all(1, ft.Colors.GREY_300)

        # Reset assessment results
        self.controls['assessment_results'].controls = [
            ft.Text(
                "Assessment results will appear here after loading a suitable systematic review.",
                size=13,
                color=ft.Colors.GREY_600
            )
        ]

        self.controls['status_text'].value = "Ready - Enter a document ID to begin PRISMA 2020 assessment"
        self.controls['status_text'].color = ft.Colors.GREY_600
        self.controls['load_button'].disabled = False

        self.current_document = None
        self.current_suitability = None
        self.current_assessment = None

        self.page.update()


def run_prisma2020_lab():
    """Entry point for PRISMA 2020 Lab application."""
    lab = PRISMA2020Lab()
    ft.app(target=lab.main)


if __name__ == '__main__':
    run_prisma2020_lab()
