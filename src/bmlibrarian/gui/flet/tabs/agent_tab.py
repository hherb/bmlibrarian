"""
Agent Configuration Tab for BMLibrarian Configuration GUI.
"""

import flet as ft
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from ..config_app import BMLibrarianConfigApp


class AgentConfigTab:
    """Agent-specific configuration tab."""
    
    def __init__(self, app: "BMLibrarianConfigApp", agent_key: str, display_name: str):
        self.app = app
        self.agent_key = agent_key
        self.display_name = display_name
        self.controls = {}
        
        # Get the agent type for configuration lookup
        # Convert agent_key from 'query_agent' to 'query'
        self.agent_type = agent_key.replace('_agent', '')
        
    def build(self) -> ft.Container:
        """Build the agent configuration tab content."""
        
        # Model Selection Section
        model_section = self._build_model_section()
        
        # Parameters Section
        params_section = self._build_parameters_section()
        
        # Advanced Settings Section
        advanced_section = self._build_advanced_section()
        
        # Create scrollable content
        content = ft.Column([
            model_section,
            ft.Divider(height=20),
            params_section,
            ft.Divider(height=20),
            advanced_section,
            ft.Container(height=50)  # Bottom padding
        ], 
        spacing=10
        )
        
        return ft.Container(
            content=ft.ListView([content], spacing=0, padding=ft.padding.all(20)),
            expand=True
        )
    
    def _build_model_section(self) -> ft.Container:
        """Build model selection section."""
        current_model = self.app.config.get_model(self.agent_key)
        
        # Get available models from Ollama
        available_models = self._get_available_models()
        
        # Ensure current model is in the list even if not currently available
        if current_model and current_model not in available_models:
            available_models.insert(0, current_model)
        
        # Model dropdown
        self.controls['model'] = ft.Dropdown(
            label="Model",
            value=current_model,
            options=[ft.dropdown.Option(model) for model in available_models],
            width=400,
            helper_text="Select the LLM model for this agent"
        )
        
        # Refresh models button
        refresh_btn = ft.IconButton(
            icon=ft.Icons.REFRESH,
            tooltip="Refresh available models from Ollama",
            on_click=self._refresh_models
        )
        
        # Add status text for loading indication
        self.controls['model_status'] = ft.Text(
            f"Loaded {len(available_models)} models from Ollama",
            size=12,
            color=ft.Colors.GREY_600
        )
        
        return ft.Container(
            ft.Column([
                ft.Text(f"{self.display_name} - Model Selection", 
                        size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_700),
                ft.Row([
                    self.controls['model'],
                    refresh_btn
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                self.controls['model_status']
            ]),
            margin=ft.margin.only(bottom=20)
        )
    
    def _build_parameters_section(self) -> ft.Container:
        """Build agent parameters section."""
        agent_config = self.app.config.get_agent_config(self.agent_type)

        # Temperature value display
        temp_value = agent_config.get('temperature', 0.1)
        self.controls['temperature_text'] = ft.Text(
            f"{temp_value:.2f}",
            size=14,
            weight=ft.FontWeight.W_500,
            width=60
        )

        # Temperature slider
        self.controls['temperature'] = ft.Slider(
            min=0.0,
            max=2.0,
            value=temp_value,
            divisions=20,
            label="{value}",
            width=300,
            tooltip="Controls randomness in responses (0.0 = deterministic, 2.0 = very random)",
            on_change=self._on_temperature_changed
        )

        # Top-p value display
        top_p_value = agent_config.get('top_p', 0.9)
        self.controls['top_p_text'] = ft.Text(
            f"{top_p_value:.2f}",
            size=14,
            weight=ft.FontWeight.W_500,
            width=60
        )

        # Top-p slider
        self.controls['top_p'] = ft.Slider(
            min=0.0,
            max=1.0,
            value=top_p_value,
            divisions=10,
            label="{value}",
            width=300,
            tooltip="Nucleus sampling parameter (0.0 = most focused, 1.0 = least focused)",
            on_change=self._on_top_p_changed
        )

        # Max Tokens
        self.controls['max_tokens'] = ft.TextField(
            label="Max Tokens",
            value=str(agent_config.get('max_tokens', 1000)),
            width=200,
            helper_text="Maximum tokens in response",
            input_filter=ft.NumbersOnlyInputFilter()
        )

        return ft.Container(
            ft.Column([
                ft.Text("Model Parameters", size=16, weight=ft.FontWeight.BOLD),
                ft.Row([
                    ft.Text("Temperature:", width=120),
                    self.controls['temperature'],
                    self.controls['temperature_text']
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Row([
                    ft.Text("Top-p:", width=120),
                    self.controls['top_p'],
                    self.controls['top_p_text']
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Row([
                    self.controls['max_tokens']
                ])
            ]),
            margin=ft.margin.only(bottom=20)
        )
    
    def _build_advanced_section(self) -> ft.Container:
        """Build advanced settings section."""
        agent_config = self.app.config.get_agent_config(self.agent_type)
        advanced_controls = []

        # Agent-specific settings
        if self.agent_type == 'query':
            # Multi-model query generation settings
            qg_config = self.app.config.get('query_generation', {})
            enabled = qg_config.get('multi_model_enabled', False)
            models = qg_config.get('models', [])

            # Ensure we have exactly 3 model slots
            while len(models) < 3:
                models.append(None)
            models = models[:3]  # Limit to 3

            # Enable multi-model toggle
            self.controls['multi_model_enabled'] = ft.Switch(
                label="Enable Multi-Model Query Generation",
                value=enabled,
                active_color=ft.Colors.GREEN_600,
                on_change=self._on_multi_model_toggle,
                tooltip="Use multiple models to generate diverse queries"
            )
            advanced_controls.append(self.controls['multi_model_enabled'])
            advanced_controls.append(ft.Container(height=10))

            # Model selectors (3 stacked vertically)
            advanced_controls.append(
                ft.Text("Query Generation Models:", size=14, weight=ft.FontWeight.BOLD)
            )

            # Get available models
            available_models = self._get_available_models()
            model_options = [ft.dropdown.Option("--- None ---")] + [
                ft.dropdown.Option(model) for model in available_models
            ]

            # Model 1 (Primary - always enabled)
            self.controls['model1'] = ft.Dropdown(
                label="Model 1 (Primary)",
                value=models[0] if models[0] else "--- None ---",
                options=model_options,
                width=350,
                disabled=not enabled
            )
            advanced_controls.append(self.controls['model1'])

            # Model 2 (Optional)
            self.controls['model2'] = ft.Dropdown(
                label="Model 2 (Optional)",
                value=models[1] if models[1] else "--- None ---",
                options=model_options,
                width=350,
                disabled=not enabled
            )
            advanced_controls.append(self.controls['model2'])

            # Model 3 (Optional)
            self.controls['model3'] = ft.Dropdown(
                label="Model 3 (Optional)",
                value=models[2] if models[2] else "--- None ---",
                options=model_options,
                width=350,
                disabled=not enabled
            )
            advanced_controls.append(self.controls['model3'])

            advanced_controls.append(ft.Container(height=10))

            # Queries per model
            queries_per_model = qg_config.get('queries_per_model', 1)
            self.controls['queries_per_model_text'] = ft.Text(
                f"{int(queries_per_model)}",
                size=14,
                weight=ft.FontWeight.W_500,
                width=60
            )
            self.controls['queries_per_model'] = ft.Slider(
                min=1,
                max=3,
                value=queries_per_model,
                divisions=2,
                label="{value}",
                width=300,
                tooltip="Number of query variations per model",
                on_change=self._on_queries_per_model_changed,
                disabled=not enabled
            )
            advanced_controls.append(
                ft.Row([
                    ft.Text("Queries per Model:", width=150),
                    self.controls['queries_per_model'],
                    self.controls['queries_per_model_text']
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER)
            )

        elif self.agent_type == 'scoring':
            score_value = agent_config.get('min_relevance_score', 3)
            self.controls['min_relevance_score_text'] = ft.Text(
                f"{int(score_value)}",
                size=14,
                weight=ft.FontWeight.W_500,
                width=60
            )
            self.controls['min_relevance_score'] = ft.Slider(
                min=1,
                max=5,
                value=score_value,
                divisions=4,
                label="{value}",
                width=300,
                tooltip="Minimum relevance score to consider",
                on_change=self._on_min_score_changed
            )
            advanced_controls.append(
                ft.Row([
                    ft.Text("Min Relevance Score:", width=150),
                    self.controls['min_relevance_score'],
                    self.controls['min_relevance_score_text']
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER)
            )

        elif self.agent_type == 'citation':
            relevance_value = agent_config.get('min_relevance', 0.7)
            self.controls['min_relevance_text'] = ft.Text(
                f"{relevance_value:.2f}",
                size=14,
                weight=ft.FontWeight.W_500,
                width=60
            )
            self.controls['min_relevance'] = ft.Slider(
                min=0.0,
                max=1.0,
                value=relevance_value,
                divisions=10,
                label="{value}",
                width=300,
                tooltip="Minimum relevance threshold for citations",
                on_change=self._on_min_relevance_changed
            )
            advanced_controls.append(
                ft.Row([
                    ft.Text("Min Relevance:", width=150),
                    self.controls['min_relevance'],
                    self.controls['min_relevance_text']
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER)
            )
            
        elif self.agent_type == 'editor':
            self.controls['comprehensive_format'] = ft.Checkbox(
                label="Comprehensive Format",
                value=agent_config.get('comprehensive_format', True),
                tooltip="Enable comprehensive report formatting"
            )
            advanced_controls.append(self.controls['comprehensive_format'])
            
        elif self.agent_type == 'counterfactual':
            self.controls['retry_attempts'] = ft.TextField(
                label="Retry Attempts",
                value=str(agent_config.get('retry_attempts', 3)),
                width=200,
                helper_text="Number of retry attempts",
                input_filter=ft.NumbersOnlyInputFilter()
            )
            advanced_controls.append(
                ft.Row([self.controls['retry_attempts']])
            )
        
        # If no specific controls, show generic message
        if not advanced_controls:
            advanced_controls = [
                ft.Text("No advanced settings available for this agent.", 
                       style=ft.TextThemeStyle.BODY_MEDIUM,
                       color=ft.Colors.GREY_600)
            ]
        
        return ft.Container(
            ft.Column([
                ft.Text("Advanced Settings", size=16, weight=ft.FontWeight.BOLD),
                *advanced_controls
            ]),
            margin=ft.margin.only(bottom=20)
        )
    
    def _get_available_models(self):
        """Get list of available models from Ollama."""
        try:
            import ollama
            
            # Create client to get models
            client = ollama.Client(host=self.app.config.get_ollama_config()['host'])
            models_response = client.list()
            available_models = [model.model for model in models_response.models]
            
            return sorted(available_models)
            
        except Exception as ex:
            print(f"Warning: Could not fetch Ollama models: {ex}")
            # Return fallback list if Ollama is not available
            return [
                "medgemma4B_it_q8:latest",
                "medgemma-27b-text-it-Q8_0:latest", 
                "gpt-oss:20b"
            ]
    
    def _refresh_models(self, e):
        """Refresh available models from Ollama."""
        # Update status to show loading
        if 'model_status' in self.controls:
            self.controls['model_status'].value = "Refreshing models from Ollama..."
            self.controls['model_status'].color = ft.Colors.BLUE_600
            self.app.page.update()
        
        try:
            # Get fresh model list
            available_models = self._get_available_models()
            
            # Preserve current selection
            current_selection = self.controls['model'].value
            
            # Update dropdown options
            self.controls['model'].options = [
                ft.dropdown.Option(model) for model in available_models
            ]
            
            # Restore selection if still available
            if current_selection and current_selection in available_models:
                self.controls['model'].value = current_selection
            elif available_models:
                self.controls['model'].value = available_models[0]
            
            # Update status with success
            if 'model_status' in self.controls:
                self.controls['model_status'].value = f"✅ Loaded {len(available_models)} models from Ollama"
                self.controls['model_status'].color = ft.Colors.GREEN_600
            
            self.app.page.update()
            self.app._show_success_dialog(f"Refreshed models. Found {len(available_models)} models.")
            
        except Exception as ex:
            # Update status with error
            if 'model_status' in self.controls:
                self.controls['model_status'].value = f"❌ Failed to load models: {str(ex)}"
                self.controls['model_status'].color = ft.Colors.RED_600
                self.app.page.update()
            
            self.app._show_error_dialog(f"Failed to refresh models: {str(ex)}")

    def _on_temperature_changed(self, e):
        """Handle temperature slider change."""
        value = self.controls['temperature'].value
        self.controls['temperature_text'].value = f"{value:.2f}"
        self.app.page.update()

    def _on_top_p_changed(self, e):
        """Handle top_p slider change."""
        value = self.controls['top_p'].value
        self.controls['top_p_text'].value = f"{value:.2f}"
        self.app.page.update()

    def _on_min_score_changed(self, e):
        """Handle min relevance score slider change."""
        value = self.controls['min_relevance_score'].value
        self.controls['min_relevance_score_text'].value = f"{int(value)}"
        self.app.page.update()

    def _on_min_relevance_changed(self, e):
        """Handle min relevance slider change."""
        value = self.controls['min_relevance'].value
        self.controls['min_relevance_text'].value = f"{value:.2f}"
        self.app.page.update()

    def _on_multi_model_toggle(self, e):
        """Handle multi-model toggle change."""
        enabled = self.controls['multi_model_enabled'].value

        # Enable/disable model selectors
        if 'model1' in self.controls:
            self.controls['model1'].disabled = not enabled
        if 'model2' in self.controls:
            self.controls['model2'].disabled = not enabled
        if 'model3' in self.controls:
            self.controls['model3'].disabled = not enabled
        if 'queries_per_model' in self.controls:
            self.controls['queries_per_model'].disabled = not enabled

        self.app.page.update()

    def _on_queries_per_model_changed(self, e):
        """Handle queries per model slider change."""
        value = self.controls['queries_per_model'].value
        self.controls['queries_per_model_text'].value = f"{int(value)}"
        self.app.page.update()

    def update_config(self):
        """Update configuration from UI controls."""
        print(f"🔧 Updating {self.agent_key} settings from UI...")  # Debug
        try:
            # Update model
            model = self.controls['model'].value
            self.app.config.set(f'models.{self.agent_key}', model)
            print(f"  Model: {model}")

            # Update parameters
            temp = self.controls['temperature'].value
            top_p = self.controls['top_p'].value
            max_tokens = int(self.controls['max_tokens'].value)

            self.app.config.set(f'agents.{self.agent_type}.temperature', temp)
            self.app.config.set(f'agents.{self.agent_type}.top_p', top_p)
            self.app.config.set(f'agents.{self.agent_type}.max_tokens', max_tokens)

            print(f"  Params: temp={temp}, top_p={top_p}, max_tokens={max_tokens}")

            # Update agent-specific settings
            if self.agent_type == 'query' and 'multi_model_enabled' in self.controls:
                # Multi-model query generation settings
                enabled = self.controls['multi_model_enabled'].value
                self.app.config.set('query_generation.multi_model_enabled', enabled)

                # Collect selected models (excluding "--- None ---")
                models = []
                for i in range(1, 4):
                    model_key = f'model{i}'
                    if model_key in self.controls:
                        value = self.controls[model_key].value
                        if value and value != "--- None ---":
                            models.append(value)

                self.app.config.set('query_generation.models', models)

                # Queries per model
                if 'queries_per_model' in self.controls:
                    qpm = int(self.controls['queries_per_model'].value)
                    self.app.config.set('query_generation.queries_per_model', qpm)
                    print(f"  Multi-model: enabled={enabled}, models={len(models)}, qpm={qpm}")

            elif self.agent_type == 'scoring' and 'min_relevance_score' in self.controls:
                score = int(self.controls['min_relevance_score'].value)
                self.app.config.set(f'agents.{self.agent_type}.min_relevance_score', score)
                print(f"  Min relevance score: {score}")
                
            elif self.agent_type == 'citation' and 'min_relevance' in self.controls:
                relevance = self.controls['min_relevance'].value
                self.app.config.set(f'agents.{self.agent_type}.min_relevance', relevance)
                print(f"  Min relevance: {relevance}")
                
            elif self.agent_type == 'editor' and 'comprehensive_format' in self.controls:
                format_flag = self.controls['comprehensive_format'].value
                self.app.config.set(f'agents.{self.agent_type}.comprehensive_format', format_flag)
                print(f"  Comprehensive format: {format_flag}")
                
            elif self.agent_type == 'counterfactual' and 'retry_attempts' in self.controls:
                retries = int(self.controls['retry_attempts'].value)
                self.app.config.set(f'agents.{self.agent_type}.retry_attempts', retries)
                print(f"  Retry attempts: {retries}")
                
            print(f"✅ {self.agent_key} settings updated")
            
        except Exception as ex:
            print(f"❌ Error updating {self.agent_key} settings: {ex}")
    
    def refresh(self):
        """Refresh tab with current configuration."""
        current_model = self.app.config.get_model(self.agent_key)
        agent_config = self.app.config.get_agent_config(self.agent_type)

        # Update model selection
        self.controls['model'].value = current_model

        # Update parameters and their text displays
        temp_value = agent_config.get('temperature', 0.1)
        self.controls['temperature'].value = temp_value
        if 'temperature_text' in self.controls:
            self.controls['temperature_text'].value = f"{temp_value:.2f}"

        top_p_value = agent_config.get('top_p', 0.9)
        self.controls['top_p'].value = top_p_value
        if 'top_p_text' in self.controls:
            self.controls['top_p_text'].value = f"{top_p_value:.2f}"

        self.controls['max_tokens'].value = str(agent_config.get('max_tokens', 1000))

        # Update agent-specific settings and their text displays
        if self.agent_type == 'scoring' and 'min_relevance_score' in self.controls:
            score_value = agent_config.get('min_relevance_score', 3)
            self.controls['min_relevance_score'].value = score_value
            if 'min_relevance_score_text' in self.controls:
                self.controls['min_relevance_score_text'].value = f"{int(score_value)}"

        elif self.agent_type == 'citation' and 'min_relevance' in self.controls:
            relevance_value = agent_config.get('min_relevance', 0.7)
            self.controls['min_relevance'].value = relevance_value
            if 'min_relevance_text' in self.controls:
                self.controls['min_relevance_text'].value = f"{relevance_value:.2f}"

        elif self.agent_type == 'editor' and 'comprehensive_format' in self.controls:
            self.controls['comprehensive_format'].value = agent_config.get('comprehensive_format', True)

        elif self.agent_type == 'counterfactual' and 'retry_attempts' in self.controls:
            self.controls['retry_attempts'].value = str(agent_config.get('retry_attempts', 3))