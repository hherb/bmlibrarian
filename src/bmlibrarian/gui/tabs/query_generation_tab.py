"""Query Generation Configuration Tab for BMLibrarian GUI."""

import flet as ft
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from ..config_app import BMLibrarianConfigApp


class QueryGenerationTab:
    """Tab for configuring multi-model query generation settings."""

    def __init__(self, app: 'BMLibrarianConfigApp'):
        """Initialize the query generation tab.

        Args:
            app: Parent application instance
        """
        self.app = app
        self.config = app.config

        # UI controls
        self.enabled_toggle: ft.Switch = None
        self.models_display: ft.Column = None
        self.queries_per_model_slider: ft.Slider = None
        self.queries_per_model_text: ft.Text = None
        self.show_queries_checkbox: ft.Checkbox = None
        self.allow_selection_checkbox: ft.Checkbox = None
        self.deduplicate_checkbox: ft.Checkbox = None
        self.available_models_list: List[str] = []
        self.selected_models: List[str] = []

    def build(self) -> ft.Container:
        """Build the query generation tab UI.

        Returns:
            ft.Container with tab content
        """
        # Get current configuration
        qg_config = self.config.get('query_generation', {})
        enabled = qg_config.get('multi_model_enabled', False)
        models = qg_config.get('models', ['medgemma-27b-text-it-Q8_0:latest'])
        queries_per_model = qg_config.get('queries_per_model', 1)
        show_queries = qg_config.get('show_all_queries_to_user', True)
        allow_selection = qg_config.get('allow_query_selection', True)
        deduplicate = qg_config.get('deduplicate_results', True)

        self.selected_models = models.copy() if models else []

        # Feature toggle
        self.enabled_toggle = ft.Switch(
            label="Enable Multi-Model Query Generation",
            value=enabled,
            on_change=self._on_enabled_changed,
            active_color=ft.Colors.GREEN_600,
            tooltip="Enable using multiple models to generate diverse queries"
        )

        # Queries per model slider with value display
        self.queries_per_model_value_text = ft.Text(
            f"{queries_per_model}",
            size=14,
            weight=ft.FontWeight.W_500,
            width=60
        )

        self.queries_per_model_slider = ft.Slider(
            min=1,
            max=3,
            divisions=2,
            value=queries_per_model,
            label="{value}",
            on_change=self._on_queries_per_model_changed,
            disabled=not enabled,
            width=300
        )

        # Checkboxes for options
        self.show_queries_checkbox = ft.Checkbox(
            label="Show all queries to user for review",
            value=show_queries,
            disabled=not enabled,
            tooltip="Display generated queries in CLI for user review"
        )

        self.allow_selection_checkbox = ft.Checkbox(
            label="Allow user to select which queries to execute",
            value=allow_selection,
            disabled=not enabled,
            tooltip="Let user choose which queries to run in interactive mode"
        )

        self.deduplicate_checkbox = ft.Checkbox(
            label="De-duplicate documents across queries",
            value=deduplicate,
            disabled=not enabled,
            tooltip="Automatically remove duplicate documents (recommended)"
        )

        # Model selection area
        self.models_display = ft.Column(
            controls=[
                ft.Text("Selected Models:", size=14, weight=ft.FontWeight.W_500),
                ft.Text(
                    "Loading available models...",
                    size=12,
                    color=ft.Colors.GREY_600,
                    italic=True
                )
            ],
            spacing=10
        )

        # Create main content
        content = ft.Container(
            content=ft.Column([
                # Header
                ft.Container(
                    ft.Text(
                        "Multi-Model Query Generation",
                        size=20,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.BLUE_700
                    ),
                    margin=ft.margin.only(bottom=10)
                ),

                # Description
                ft.Container(
                    ft.Text(
                        "Use multiple AI models to generate diverse database queries, "
                        "improving document retrieval quality by 20-40%.",
                        size=12,
                        color=ft.Colors.GREY_700
                    ),
                    margin=ft.margin.only(bottom=15),
                    padding=ft.padding.all(10),
                    bgcolor=ft.Colors.BLUE_50,
                    border_radius=5
                ),

                # Feature toggle
                ft.Container(
                    self.enabled_toggle,
                    margin=ft.margin.only(bottom=20)
                ),

                ft.Divider(height=1, color=ft.Colors.GREY_300),

                # Settings section (disabled when feature is off)
                ft.Container(
                    ft.Column([
                        # Model selection
                        ft.Container(
                            ft.Column([
                                ft.Row([
                                    ft.Text(
                                        "Models (select 1-3)",
                                        size=16,
                                        weight=ft.FontWeight.W_600
                                    ),
                                    ft.IconButton(
                                        icon=ft.Icons.REFRESH,
                                        tooltip="Refresh available models from Ollama",
                                        on_click=self._refresh_models,
                                        disabled=not enabled
                                    )
                                ]),
                                self.models_display
                            ], spacing=5),
                            margin=ft.margin.only(bottom=20)
                        ),

                        # Queries per model
                        ft.Container(
                            ft.Column([
                                ft.Text("Queries per model", size=14, weight=ft.FontWeight.W_500),
                                ft.Row([
                                    self.queries_per_model_slider,
                                    self.queries_per_model_value_text
                                ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                                ft.Text(
                                    "More queries = better coverage but slower",
                                    size=11,
                                    color=ft.Colors.GREY_600,
                                    italic=True
                                )
                            ], spacing=5),
                            margin=ft.margin.only(bottom=20)
                        ),

                        # Interactive options
                        ft.Container(
                            ft.Column([
                                ft.Text(
                                    "Interactive Options",
                                    size=16,
                                    weight=ft.FontWeight.W_600
                                ),
                                self.show_queries_checkbox,
                                self.allow_selection_checkbox,
                                self.deduplicate_checkbox
                            ], spacing=8),
                            margin=ft.margin.only(bottom=15)
                        ),

                        # Performance info
                        ft.Container(
                            ft.Column([
                                ft.Text(
                                    "Performance Impact",
                                    size=14,
                                    weight=ft.FontWeight.W_600
                                ),
                                ft.Text(
                                    "• 2 models, 1 query each: ~5-8 sec (2x slower, +20-30% documents)",
                                    size=11,
                                    color=ft.Colors.GREY_700
                                ),
                                ft.Text(
                                    "• 3 models, 2 queries each: ~15-25 sec (3-4x slower, +40-60% documents)",
                                    size=11,
                                    color=ft.Colors.GREY_700
                                ),
                                ft.Text(
                                    "• Serial execution optimized for local Ollama + PostgreSQL",
                                    size=11,
                                    color=ft.Colors.GREY_700
                                )
                            ], spacing=5),
                            padding=ft.padding.all(10),
                            bgcolor=ft.Colors.GREY_100,
                            border_radius=5
                        )
                    ], spacing=10),
                    margin=ft.margin.only(top=15)
                )
            ], spacing=5, scroll=ft.ScrollMode.AUTO),
            padding=ft.padding.all(20)
        )

        # Load available models after UI is built
        if self.app.page:
            self._refresh_models(None)

        return content

    def _on_enabled_changed(self, e):
        """Handle feature toggle change."""
        enabled = self.enabled_toggle.value

        # Update UI element states
        self.queries_per_model_slider.disabled = not enabled
        self.show_queries_checkbox.disabled = not enabled
        self.allow_selection_checkbox.disabled = not enabled
        self.deduplicate_checkbox.disabled = not enabled

        # Update model selection buttons
        self._update_models_display()

        self.app.page.update()

    def _on_queries_per_model_changed(self, e):
        """Handle queries per model slider change."""
        value = int(self.queries_per_model_slider.value)
        self.queries_per_model_value_text.value = f"{value}"
        self.app.page.update()

    def _refresh_models(self, e):
        """Refresh available models from Ollama."""
        try:
            import requests

            # Get Ollama host from config
            ollama_host = self.config.get('ollama_host', 'http://localhost:11434')

            # Fetch available models
            response = requests.get(f"{ollama_host}/api/tags", timeout=5)
            response.raise_for_status()

            data = response.json()
            self.available_models_list = [model['name'] for model in data.get('models', [])]

            if not self.available_models_list:
                self.models_display.controls = [
                    ft.Text("Selected Models:", size=14, weight=ft.FontWeight.W_500),
                    ft.Text(
                        "No models found in Ollama. Please pull some models first.",
                        size=12,
                        color=ft.Colors.ORANGE_700,
                        italic=True
                    )
                ]
            else:
                self._update_models_display()

        except Exception as ex:
            self.models_display.controls = [
                ft.Text("Selected Models:", size=14, weight=ft.FontWeight.W_500),
                ft.Text(
                    f"Failed to fetch models: {str(ex)}",
                    size=12,
                    color=ft.Colors.RED_700,
                    italic=True
                ),
                ft.Text(
                    "Make sure Ollama is running and accessible.",
                    size=11,
                    color=ft.Colors.GREY_600,
                    italic=True
                )
            ]

        if self.app.page:
            self.app.page.update()

    def _update_models_display(self):
        """Update the models display with checkboxes."""
        enabled = self.enabled_toggle.value if self.enabled_toggle else False

        if not self.available_models_list:
            return

        # Create checkboxes for each available model
        model_checkboxes = []
        for model in self.available_models_list:
            checkbox = ft.Checkbox(
                label=model,
                value=model in self.selected_models,
                on_change=lambda e, m=model: self._on_model_toggled(e, m),
                disabled=not enabled
            )
            model_checkboxes.append(checkbox)

        # Update display
        self.models_display.controls = [
            ft.Text("Selected Models (choose 1-3):", size=14, weight=ft.FontWeight.W_500),
            ft.Text(
                f"Currently selected: {len(self.selected_models)} model(s)",
                size=12,
                color=ft.Colors.BLUE_700 if len(self.selected_models) <= 3 else ft.Colors.ORANGE_700,
                weight=ft.FontWeight.W_500
            ),
            ft.Container(
                ft.Column(model_checkboxes, spacing=5),
                padding=ft.padding.only(left=10)
            )
        ]

        if len(self.selected_models) > 3:
            self.models_display.controls.insert(2, ft.Text(
                "⚠ Warning: More than 3 models selected (not recommended)",
                size=11,
                color=ft.Colors.ORANGE_700,
                italic=True
            ))

    def _on_model_toggled(self, e, model: str):
        """Handle model checkbox toggle."""
        if e.control.value:
            # Add model if not already in list
            if model not in self.selected_models:
                self.selected_models.append(model)
        else:
            # Remove model
            if model in self.selected_models:
                self.selected_models.remove(model)

        # Update display to show count
        self._update_models_display()
        self.app.page.update()

    def get_config(self) -> dict:
        """Get current configuration from UI.

        Returns:
            dict with query_generation configuration
        """
        return {
            'multi_model_enabled': self.enabled_toggle.value if self.enabled_toggle else False,
            'models': self.selected_models if self.selected_models else ['medgemma-27b-text-it-Q8_0:latest'],
            'queries_per_model': int(self.queries_per_model_slider.value) if self.queries_per_model_slider else 1,
            'execution_mode': 'serial',  # Always serial
            'deduplicate_results': self.deduplicate_checkbox.value if self.deduplicate_checkbox else True,
            'show_all_queries_to_user': self.show_queries_checkbox.value if self.show_queries_checkbox else True,
            'allow_query_selection': self.allow_selection_checkbox.value if self.allow_selection_checkbox else True
        }

    def refresh_from_config(self):
        """Refresh UI from current configuration."""
        qg_config = self.config.get('query_generation', {})

        if self.enabled_toggle:
            self.enabled_toggle.value = qg_config.get('multi_model_enabled', False)

        if self.queries_per_model_slider:
            value = qg_config.get('queries_per_model', 1)
            self.queries_per_model_slider.value = value
            if self.queries_per_model_value_text:
                self.queries_per_model_value_text.value = f"{value}"

        if self.show_queries_checkbox:
            self.show_queries_checkbox.value = qg_config.get('show_all_queries_to_user', True)

        if self.allow_selection_checkbox:
            self.allow_selection_checkbox.value = qg_config.get('allow_query_selection', True)

        if self.deduplicate_checkbox:
            self.deduplicate_checkbox.value = qg_config.get('deduplicate_results', True)

        # Update selected models
        models = qg_config.get('models', [])
        self.selected_models = models.copy() if models else []

        # Refresh display
        self._update_models_display()

        if self.app.page:
            self.app.page.update()
