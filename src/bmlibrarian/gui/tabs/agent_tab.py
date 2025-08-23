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
        
        # Temperature
        self.controls['temperature'] = ft.Slider(
            min=0.0,
            max=2.0,
            value=agent_config.get('temperature', 0.1),
            divisions=20,
            label="{value}",
            width=300,
            tooltip="Controls randomness in responses (0.0 = deterministic, 2.0 = very random)"
        )
        
        # Top-p
        self.controls['top_p'] = ft.Slider(
            min=0.0,
            max=1.0,
            value=agent_config.get('top_p', 0.9),
            divisions=10,
            label="{value}",
            width=300,
            tooltip="Nucleus sampling parameter (0.0 = most focused, 1.0 = least focused)"
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
                    self.controls['temperature']
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Row([
                    ft.Text("Top-p:", width=120),
                    self.controls['top_p']
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
        if self.agent_type == 'scoring':
            self.controls['min_relevance_score'] = ft.Slider(
                min=1,
                max=5,
                value=agent_config.get('min_relevance_score', 3),
                divisions=4,
                label="{value}",
                width=300,
                tooltip="Minimum relevance score to consider"
            )
            advanced_controls.append(
                ft.Row([
                    ft.Text("Min Relevance Score:", width=150),
                    self.controls['min_relevance_score']
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER)
            )
            
        elif self.agent_type == 'citation':
            self.controls['min_relevance'] = ft.Slider(
                min=0.0,
                max=1.0,
                value=agent_config.get('min_relevance', 0.7),
                divisions=10,
                label="{value}",
                width=300,
                tooltip="Minimum relevance threshold for citations"
            )
            advanced_controls.append(
                ft.Row([
                    ft.Text("Min Relevance:", width=150),
                    self.controls['min_relevance']
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
            if self.agent_type == 'scoring' and 'min_relevance_score' in self.controls:
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
        
        # Update parameters
        self.controls['temperature'].value = agent_config.get('temperature', 0.1)
        self.controls['top_p'].value = agent_config.get('top_p', 0.9)
        self.controls['max_tokens'].value = str(agent_config.get('max_tokens', 1000))
        
        # Update agent-specific settings
        if self.agent_type == 'scoring' and 'min_relevance_score' in self.controls:
            self.controls['min_relevance_score'].value = agent_config.get('min_relevance_score', 3)
            
        elif self.agent_type == 'citation' and 'min_relevance' in self.controls:
            self.controls['min_relevance'].value = agent_config.get('min_relevance', 0.7)
            
        elif self.agent_type == 'editor' and 'comprehensive_format' in self.controls:
            self.controls['comprehensive_format'].value = agent_config.get('comprehensive_format', True)
            
        elif self.agent_type == 'counterfactual' and 'retry_attempts' in self.controls:
            self.controls['retry_attempts'].value = str(agent_config.get('retry_attempts', 3))