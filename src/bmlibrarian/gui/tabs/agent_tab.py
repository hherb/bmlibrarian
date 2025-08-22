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
        
        return ft.Container(
            ft.Column([
                model_section,
                ft.Divider(),
                params_section,
                ft.Divider(),
                advanced_section
            ], scroll=ft.ScrollMode.AUTO),
            padding=ft.padding.all(20)
        )
    
    def _build_model_section(self) -> ft.Container:
        """Build model selection section."""
        current_model = self.app.config.get_model(self.agent_key)
        
        # Get available models (predefined list for now)
        available_models = [
            "medgemma4B_it_q8:latest",
            "medgemma-27b-text-it-Q8_0:latest", 
            "gpt-oss:20b",
            "llama3.1:8b",
            "llama3.1:70b",
            "mistral:7b",
            "gemma2:9b",
            "phi3:mini"
        ]
        
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
        
        return ft.Container(
            ft.Column([
                ft.Text(f"{self.display_name} - Model Selection", 
                        size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_700),
                ft.Row([
                    self.controls['model'],
                    refresh_btn
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER)
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
    
    def _refresh_models(self, e):
        """Refresh available models from Ollama."""
        try:
            from ...agents.base import BaseAgent
            import ollama
            
            # Create temporary client to get models
            client = ollama.Client(host=self.app.config.get_ollama_config()['host'])
            models_response = client.list()
            available_models = [model.model for model in models_response.models]
            
            # Update dropdown options
            self.controls['model'].options = [
                ft.dropdown.Option(model) for model in sorted(available_models)
            ]
            
            self.app.page.update()
            self.app._show_success_dialog(f"Refreshed models. Found {len(available_models)} models.")
            
        except Exception as ex:
            self.app._show_error_dialog(f"Failed to refresh models: {str(ex)}")
    
    def update_config(self):
        """Update configuration from UI controls."""
        # Update model
        self.app.config.set(f'models.{self.agent_key}', self.controls['model'].value)
        
        # Update parameters
        self.app.config.set(f'agents.{self.agent_type}.temperature', self.controls['temperature'].value)
        self.app.config.set(f'agents.{self.agent_type}.top_p', self.controls['top_p'].value)
        self.app.config.set(f'agents.{self.agent_type}.max_tokens', int(self.controls['max_tokens'].value))
        
        # Update agent-specific settings
        if self.agent_type == 'scoring' and 'min_relevance_score' in self.controls:
            self.app.config.set(f'agents.{self.agent_type}.min_relevance_score', 
                               int(self.controls['min_relevance_score'].value))
            
        elif self.agent_type == 'citation' and 'min_relevance' in self.controls:
            self.app.config.set(f'agents.{self.agent_type}.min_relevance', 
                               self.controls['min_relevance'].value)
            
        elif self.agent_type == 'editor' and 'comprehensive_format' in self.controls:
            self.app.config.set(f'agents.{self.agent_type}.comprehensive_format', 
                               self.controls['comprehensive_format'].value)
            
        elif self.agent_type == 'counterfactual' and 'retry_attempts' in self.controls:
            self.app.config.set(f'agents.{self.agent_type}.retry_attempts', 
                               int(self.controls['retry_attempts'].value))
    
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