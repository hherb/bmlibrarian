"""
Study Assessment Lab - Interactive GUI for study quality assessment

Provides an interface for:
1. Entering a document ID
2. Displaying the document's title and abstract
3. Running quality assessment and displaying results
"""

import flet as ft
import sys
from pathlib import Path
from typing import Optional, Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from bmlibrarian.agents import StudyAssessmentAgent, AgentOrchestrator
from bmlibrarian.agents.study_assessment_agent import StudyAssessment
from bmlibrarian.config import get_config
from bmlibrarian.database import fetch_documents_by_ids
from bmlibrarian.lab.document_display_factory import create_document_display_simple


class StudyAssessmentLab:
    """Interactive lab for study quality assessment."""

    def __init__(self):
        self.config = get_config()
        self.page: Optional[ft.Page] = None
        self.assessment_agent: Optional[StudyAssessmentAgent] = None
        self.orchestrator: Optional[AgentOrchestrator] = None
        self.controls = {}
        self.current_document: Optional[Dict[str, Any]] = None
        self.current_assessment: Optional[StudyAssessment] = None
        self.document_display = None  # Will hold document display widgets

    def main(self, page: ft.Page):
        """Main application entry point."""
        self.page = page
        page.title = "Study Assessment Lab - BMLibrarian"
        page.window.width = 1400
        page.window.height = 900
        page.window.min_width = 1200
        page.window.min_height = 700
        page.window.resizable = True
        page.theme_mode = ft.ThemeMode.LIGHT

        # Initialize agent
        self._init_agent()

        # Create layout
        self._create_layout()

    def _init_agent(self):
        """Initialize StudyAssessmentAgent with orchestrator."""
        try:
            # Initialize orchestrator
            self.orchestrator = AgentOrchestrator(max_workers=2)

            # Get model from config
            model = self.config.get_model('study_assessment_agent') or "gpt-oss:20b"
            agent_config = self.config.get_agent_config('study_assessment') or {}
            host = self.config.get_ollama_config()['host']

            print(f"🚀 Initializing StudyAssessmentAgent with model: {model}")

            self.assessment_agent = StudyAssessmentAgent(
                model=model,
                host=host,
                temperature=agent_config.get('temperature', 0.1),
                top_p=agent_config.get('top_p', 0.9),
                max_tokens=agent_config.get('max_tokens', 3000),
                orchestrator=self.orchestrator,
                show_model_info=True
            )
        except Exception as e:
            print(f"Warning: Failed to initialize StudyAssessmentAgent: {e}")
            self.assessment_agent = None

    def _create_layout(self):
        """Create the main application layout."""

        # Header
        header = ft.Container(
            ft.Column([
                ft.Text(
                    "Study Assessment Laboratory",
                    size=28,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.BLUE_700
                ),
                ft.Text(
                    "Evaluate research quality, study design, and trustworthiness of biomedical evidence",
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

        # Assessment results panel
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
                    width=450,
                    padding=ft.padding.all(15),
                    bgcolor=ft.Colors.GREY_50,
                    border_radius=10
                ),
                ft.VerticalDivider(width=20),
                ft.Container(
                    assessment_panel,
                    expand=True,
                    padding=ft.padding.all(15),
                    bgcolor=ft.Colors.BLUE_50,
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
        current_model = self.config.get_model('study_assessment_agent') or "gpt-oss:20b"

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
            on_submit=lambda _: self._load_document(None)
        )

        self.controls['load_button'] = ft.ElevatedButton(
            "Load & Assess",
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
        """Create document display panel using document display factory."""
        # Create document display using factory (with tabbed abstract/fulltext)
        self.document_display = create_document_display_simple(
            page=self.page,
            initial_title="No document loaded",
            width=450,
            abstract_height=400
        )

        # Store references for backward compatibility
        self.controls['doc_title'] = self.document_display['title']
        self.controls['doc_metadata'] = self.document_display['metadata']

        return self.document_display['container']

    def _create_assessment_panel(self) -> ft.Column:
        """Create assessment results panel."""

        self.controls['assessment_header'] = ft.Text(
            "Quality Assessment",
            size=18,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.GREY_800
        )

        self.controls['assessment_results'] = ft.Column(
            [
                ft.Text(
                    "Assessment results will appear here after loading a document.",
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
            agent_config = self.config.get_agent_config('study_assessment') or {}
            host = self.config.get_ollama_config()['host']

            self.assessment_agent = StudyAssessmentAgent(
                model=new_model,
                host=host,
                temperature=agent_config.get('temperature', 0.1),
                top_p=agent_config.get('top_p', 0.9),
                max_tokens=agent_config.get('max_tokens', 3000),
                orchestrator=self.orchestrator,
                show_model_info=False
            )

            self.controls['status_text'].value = f"Switched to {new_model}"
        except Exception as err:
            self.controls['status_text'].value = f"Error switching model: {err}"

        self.page.update()

    def _load_document(self, e):
        """Load document and run assessment."""
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

            # Run assessment
            self._run_assessment()

        except Exception as err:
            self.controls['status_text'].value = f"Error: {err}"
            self.controls['status_text'].color = ft.Colors.RED_600
            self.controls['load_button'].disabled = False
            self.page.update()

    def _display_document(self):
        """Display loaded document using document display factory."""
        if not self.current_document:
            return

        # Use the document display factory's update function
        if self.document_display:
            self.document_display['update_func'](self.current_document)
        else:
            # Fallback to manual update (shouldn't happen)
            self.page.update()

    def _run_assessment(self):
        """Run study quality assessment."""
        if not self.current_document or not self.assessment_agent:
            return

        self.controls['status_text'].value = "Running quality assessment..."
        self.controls['status_text'].color = ft.Colors.BLUE_600
        self.page.update()

        try:
            # Run assessment
            self.current_assessment = self.assessment_agent.assess_study(
                self.current_document,
                min_confidence=0.3  # Lower threshold for lab exploration
            )

            if self.current_assessment:
                self._display_assessment()
                self.controls['status_text'].value = "Assessment complete"
                self.controls['status_text'].color = ft.Colors.GREEN_600
            else:
                self.controls['status_text'].value = "Assessment failed (check logs)"
                self.controls['status_text'].color = ft.Colors.RED_600

        except Exception as err:
            self.controls['status_text'].value = f"Assessment error: {err}"
            self.controls['status_text'].color = ft.Colors.RED_600

        self.controls['load_button'].disabled = False
        self.page.update()

    def _display_assessment(self):
        """Display assessment results."""
        if not self.current_assessment:
            return

        a = self.current_assessment  # Shorthand

        # Build results display
        results_controls = []

        # Study Classification Section
        results_controls.append(
            ft.Container(
                ft.Column([
                    ft.Text("📊 Study Classification", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_800),
                    ft.Divider(height=5),
                    self._create_info_row("Study Type", a.study_type),
                    self._create_info_row("Study Design", a.study_design),
                    self._create_info_row("Evidence Level", a.evidence_level),
                    self._create_info_row("Sample Size", a.sample_size or "Not reported"),
                    self._create_info_row("Follow-up", a.follow_up_duration or "Not reported")
                ], spacing=8),
                padding=ft.padding.all(10),
                bgcolor=ft.Colors.BLUE_50,
                border_radius=5
            )
        )

        # Quality Metrics Section
        quality_color = self._get_quality_color(a.quality_score)
        confidence_color = self._get_confidence_color(a.overall_confidence)

        results_controls.append(
            ft.Container(
                ft.Column([
                    ft.Text("⭐ Quality Metrics", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.ORANGE_800),
                    ft.Divider(height=5),
                    ft.Row([
                        ft.Text("Quality Score:", weight=ft.FontWeight.BOLD),
                        ft.Text(f"{a.quality_score:.1f}/10", color=quality_color, weight=ft.FontWeight.BOLD)
                    ]),
                    ft.Row([
                        ft.Text("Confidence:", weight=ft.FontWeight.BOLD),
                        ft.Text(f"{a.overall_confidence:.1%}", color=confidence_color, weight=ft.FontWeight.BOLD)
                    ]),
                    ft.Text(
                        a.confidence_explanation,
                        size=12,
                        italic=True,
                        color=ft.Colors.GREY_700
                    )
                ], spacing=8),
                padding=ft.padding.all(10),
                bgcolor=ft.Colors.ORANGE_50,
                border_radius=5
            )
        )

        # Design Characteristics
        design_chars = []
        if a.is_prospective:
            design_chars.append("✓ Prospective")
        if a.is_retrospective:
            design_chars.append("✓ Retrospective")
        if a.is_randomized:
            design_chars.append("✓ Randomized")
        if a.is_controlled:
            design_chars.append("✓ Controlled")
        if a.is_double_blinded:
            design_chars.append("✓ Double-blinded")
        elif a.is_blinded:
            design_chars.append("✓ Blinded")
        if a.is_multi_center:
            design_chars.append("✓ Multi-center")

        if design_chars:
            results_controls.append(
                ft.Container(
                    ft.Column([
                        ft.Text("🔬 Design Characteristics", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.PURPLE_800),
                        ft.Divider(height=5),
                        ft.Text(", ".join(design_chars), color=ft.Colors.PURPLE_700)
                    ], spacing=8),
                    padding=ft.padding.all(10),
                    bgcolor=ft.Colors.PURPLE_50,
                    border_radius=5
                )
            )

        # Strengths
        results_controls.append(
            ft.Container(
                ft.Column([
                    ft.Text("✅ Strengths", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_800),
                    ft.Divider(height=5),
                    *[ft.Text(f"• {s}", size=13) for s in a.strengths]
                ], spacing=5),
                padding=ft.padding.all(10),
                bgcolor=ft.Colors.GREEN_50,
                border_radius=5
            )
        )

        # Limitations
        results_controls.append(
            ft.Container(
                ft.Column([
                    ft.Text("⚠️  Limitations", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.RED_800),
                    ft.Divider(height=5),
                    *[ft.Text(f"• {l}", size=13) for l in a.limitations]
                ], spacing=5),
                padding=ft.padding.all(10),
                bgcolor=ft.Colors.RED_50,
                border_radius=5
            )
        )

        # Bias Assessment
        bias_items = []
        if a.selection_bias_risk:
            bias_items.append(("Selection", a.selection_bias_risk))
        if a.performance_bias_risk:
            bias_items.append(("Performance", a.performance_bias_risk))
        if a.detection_bias_risk:
            bias_items.append(("Detection", a.detection_bias_risk))
        if a.attrition_bias_risk:
            bias_items.append(("Attrition", a.attrition_bias_risk))
        if a.reporting_bias_risk:
            bias_items.append(("Reporting", a.reporting_bias_risk))

        if bias_items:
            bias_controls = [
                ft.Text("🎯 Bias Risk Assessment", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.INDIGO_800),
                ft.Divider(height=5)
            ]
            for bias_type, risk_level in bias_items:
                bias_controls.append(
                    ft.Row([
                        ft.Text(f"{bias_type}:", weight=ft.FontWeight.BOLD, width=120),
                        ft.Container(
                            ft.Text(
                                risk_level.upper(),
                                color=ft.Colors.WHITE,
                                weight=ft.FontWeight.BOLD,
                                size=11
                            ),
                            padding=ft.padding.symmetric(horizontal=8, vertical=4),
                            bgcolor=self._get_bias_color(risk_level),
                            border_radius=3
                        )
                    ])
                )

            results_controls.append(
                ft.Container(
                    ft.Column(bias_controls, spacing=8),
                    padding=ft.padding.all(10),
                    bgcolor=ft.Colors.INDIGO_50,
                    border_radius=5
                )
            )

        # Update results display
        self.controls['assessment_results'].controls = results_controls
        self.page.update()

    def _create_info_row(self, label: str, value: str) -> ft.Row:
        """Create an information row."""
        return ft.Row([
            ft.Text(f"{label}:", weight=ft.FontWeight.BOLD, width=120),
            ft.Text(value, color=ft.Colors.GREY_800)
        ])

    def _get_quality_color(self, score: float) -> str:
        """Get color based on quality score."""
        if score >= 9:
            return ft.Colors.GREEN_700
        elif score >= 7:
            return ft.Colors.GREEN_600
        elif score >= 5:
            return ft.Colors.ORANGE_600
        elif score >= 3:
            return ft.Colors.ORANGE_700
        else:
            return ft.Colors.RED_700

    def _get_confidence_color(self, confidence: float) -> str:
        """Get color based on confidence level."""
        if confidence >= 0.8:
            return ft.Colors.GREEN_700
        elif confidence >= 0.6:
            return ft.Colors.BLUE_600
        elif confidence >= 0.4:
            return ft.Colors.ORANGE_600
        else:
            return ft.Colors.RED_600

    def _get_bias_color(self, risk_level: str) -> str:
        """Get color based on bias risk level."""
        risk_colors = {
            'low': ft.Colors.GREEN_600,
            'moderate': ft.Colors.ORANGE_600,
            'high': ft.Colors.RED_600,
            'unclear': ft.Colors.GREY_600
        }
        return risk_colors.get(risk_level.lower(), ft.Colors.GREY_600)

    def _clear_all(self, e):
        """Clear all fields and results."""
        self.controls['doc_id_input'].value = ""

        # Clear document display using factory
        if self.document_display:
            self.document_display['update_func'](None)

        self.controls['assessment_results'].controls = [
            ft.Text(
                "Assessment results will appear here after loading a document.",
                size=13,
                color=ft.Colors.GREY_600
            )
        ]

        self.controls['status_text'].value = "Ready"
        self.controls['status_text'].color = ft.Colors.GREY_600

        self.current_document = None
        self.current_assessment = None

        self.page.update()


def run_study_assessment_lab():
    """Run the Study Assessment Lab application."""
    app = StudyAssessmentLab()
    ft.app(target=app.main)
