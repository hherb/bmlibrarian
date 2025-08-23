"""
QueryAgent Lab - Experimental GUI for testing query generation

Provides an interactive interface for experimenting with the QueryAgent,
including model selection and parameter tuning.
"""

import flet as ft
import asyncio
import json
from typing import Optional, List
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from bmlibrarian.agents import QueryAgent, AgentOrchestrator
from bmlibrarian.config import get_config


class QueryAgentLab:
    """Interactive lab for experimenting with QueryAgent."""
    
    def __init__(self):
        self.config = get_config()
        self.page: Optional[ft.Page] = None
        self.query_agent: Optional[QueryAgent] = None
        self.orchestrator: Optional[AgentOrchestrator] = None
        self.controls = {}
        
    def main(self, page: ft.Page):
        """Main application entry point."""
        self.page = page
        page.title = "QueryAgent Lab - BMLibrarian"
        page.window.width = 1000
        page.window.height = 800
        page.window.min_width = 800
        page.window.min_height = 600
        page.window.resizable = True
        page.theme_mode = ft.ThemeMode.LIGHT
        
        # Initialize agent
        self._init_agent()
        
        # Create layout
        self._create_layout()
        
    def _init_agent(self):
        """Initialize QueryAgent with orchestrator."""
        try:
            # Try to initialize with orchestrator, but handle threading issues gracefully
            self.orchestrator = AgentOrchestrator(max_workers=2)
            
            # Get default model from config or use fallback
            default_model = self.config.get_model('query_agent') or "medgemma4B_it_q8:latest"
            agent_config = self.config.get_agent_config('query')
            host = self.config.get_ollama_config()['host']
            
            print(f"🚀 Initializing QueryAgent with model: {default_model}")
            
            self.query_agent = QueryAgent(
                model=default_model,
                host=host,
                temperature=agent_config.get('temperature', 0.1),
                top_p=agent_config.get('top_p', 0.9),
                orchestrator=self.orchestrator,
                show_model_info=True
            )
        except Exception as e:
            print(f"Warning: Failed to initialize QueryAgent with orchestrator: {e}")
            # Try to initialize QueryAgent without orchestrator for lab testing
            try:
                default_model = self.config.get_model('query_agent') or "medgemma4B_it_q8:latest"
                agent_config = self.config.get_agent_config('query')
                host = self.config.get_ollama_config()['host']
                
                print(f"🔄 Trying QueryAgent without orchestrator, model: {default_model}")
                
                self.query_agent = QueryAgent(
                    model=default_model,
                    host=host,
                    temperature=agent_config.get('temperature', 0.1),
                    top_p=agent_config.get('top_p', 0.9),
                    orchestrator=None,
                    show_model_info=True
                )
            except Exception as e2:
                print(f"Warning: Failed to initialize QueryAgent without orchestrator: {e2}")
                self.query_agent = None
    
    def _create_layout(self):
        """Create the main application layout."""
        
        # Header
        header = ft.Container(
            ft.Column([
                ft.Text(
                    "QueryAgent Laboratory",
                    size=28,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.BLUE_700
                ),
                ft.Text(
                    "Experiment with natural language to PostgreSQL query conversion",
                    size=14,
                    color=ft.Colors.GREY_600
                )
            ]),
            margin=ft.margin.only(bottom=30)
        )
        
        # Configuration Panel
        config_panel = self._create_config_panel()
        
        # Query Input/Output Panel  
        query_panel = self._create_query_panel()
        
        # Control Buttons
        control_panel = self._create_control_panel()
        
        # Main layout
        main_content = ft.Column([
            header,
            ft.Row([
                ft.Container(
                    config_panel,
                    width=350,
                    padding=ft.padding.all(20),
                    bgcolor=ft.Colors.GREY_50,
                    border_radius=10
                ),
                ft.VerticalDivider(width=20),
                ft.Container(
                    query_panel,
                    expand=True,
                    padding=ft.padding.all(20)
                )
            ], expand=True, spacing=10),
            ft.Divider(height=20),
            control_panel
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
    
    def _create_config_panel(self) -> ft.Column:
        """Create configuration panel with model and parameter controls."""
        
        # Model Selection
        available_models = self._get_available_models()
        current_model = self.config.get_model('query_agent')
        
        self.controls['model'] = ft.Dropdown(
            label="Query Agent Model",
            value=current_model if current_model in available_models else (available_models[0] if available_models else ""),
            options=[ft.dropdown.Option(model) for model in available_models],
            width=300,
            on_change=self._on_model_change
        )
        
        # Refresh models button
        refresh_btn = ft.IconButton(
            icon=ft.Icons.REFRESH,
            tooltip="Refresh available models",
            on_click=self._refresh_models
        )
        
        # Model parameters
        agent_config = self.config.get_agent_config('query')
        
        self.controls['temperature'] = ft.Slider(
            min=0.0,
            max=2.0,
            value=agent_config.get('temperature', 0.1),
            divisions=20,
            label="Temperature: {value}",
            width=280,
            on_change=self._on_param_change
        )
        
        self.controls['top_p'] = ft.Slider(
            min=0.0,
            max=1.0,
            value=agent_config.get('top_p', 0.9),
            divisions=10,
            label="Top-p: {value}",
            width=280,
            on_change=self._on_param_change
        )
        
        self.controls['max_tokens'] = ft.TextField(
            label="Max Tokens",
            value=str(agent_config.get('max_tokens', 100)),
            width=150,
            input_filter=ft.NumbersOnlyInputFilter(),
            on_change=self._on_param_change
        )
        
        # Status indicator - check if agent has the convert_question method
        agent_ready = self.query_agent and hasattr(self.query_agent, 'convert_question')
        if agent_ready:
            current_model = self.controls['model'].value if 'model' in self.controls else "unknown"
            status_text = f"Agent: Ready (QueryAgent active) - {current_model}"
            status_color = ft.Colors.GREEN_600
        else:
            status_text = "Agent: Simulation mode"
            status_color = ft.Colors.ORANGE_600
        
        self.controls['agent_status'] = ft.Text(
            status_text,
            size=12,
            color=status_color
        )
        
        return ft.Column([
            ft.Text("Configuration", size=18, weight=ft.FontWeight.BOLD),
            ft.Divider(),
            
            # Model Selection
            ft.Text("Model Selection", size=14, weight=ft.FontWeight.W_500),
            ft.Row([
                self.controls['model'],
                refresh_btn
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            
            ft.Container(height=20),
            
            # Parameters
            ft.Text("Parameters", size=14, weight=ft.FontWeight.W_500),
            ft.Text("Temperature:", size=12),
            self.controls['temperature'],
            ft.Container(height=10),
            ft.Text("Top-p:", size=12),
            self.controls['top_p'],
            ft.Container(height=10),
            self.controls['max_tokens'],
            
            ft.Container(height=20),
            ft.Divider(),
            self.controls['agent_status']
        ], 
        spacing=5
        )
    
    def _create_query_panel(self) -> ft.Column:
        """Create query input/output panel."""
        
        # Human language input
        self.controls['human_query'] = ft.TextField(
            label="Human Language Question",
            hint_text="Enter your medical research question in natural language...",
            multiline=True,
            min_lines=3,
            max_lines=5,
            width=None,  # Full width
            on_change=self._on_query_change
        )
        
        # Generated PostgreSQL query output
        self.controls['postgres_query'] = ft.TextField(
            label="Generated PostgreSQL to_tsquery",
            hint_text="Generated query will appear here...",
            multiline=True,
            min_lines=4,
            max_lines=8,
            width=None,  # Full width
            read_only=True,
            bgcolor=ft.Colors.GREY_100
        )
        
        # Query explanation
        self.controls['query_explanation'] = ft.TextField(
            label="Query Explanation",
            hint_text="Explanation of the generated query...",
            multiline=True,
            min_lines=3,
            max_lines=5,
            width=None,
            read_only=True,
            bgcolor=ft.Colors.BLUE_50
        )
        
        # Processing status
        self.controls['processing_status'] = ft.Text(
            "Ready",
            size=12,
            color=ft.Colors.GREY_600
        )
        
        # Query statistics
        self.controls['query_stats'] = ft.Text(
            "",
            size=11,
            color=ft.Colors.GREY_500
        )
        
        return ft.Column([
            ft.Text("Query Laboratory", size=18, weight=ft.FontWeight.BOLD),
            ft.Divider(),
            
            self.controls['human_query'],
            ft.Container(height=10),
            
            ft.Row([
                ft.Text("Generated Query", size=14, weight=ft.FontWeight.W_500),
                self.controls['processing_status']
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            self.controls['postgres_query'],
            
            ft.Container(height=10),
            ft.Text("Explanation", size=14, weight=ft.FontWeight.W_500),
            self.controls['query_explanation'],
            
            ft.Container(height=5),
            self.controls['query_stats']
        ],
        spacing=5,
        expand=True
        )
    
    def _create_control_panel(self) -> ft.Row:
        """Create control buttons panel."""
        
        return ft.Row([
            ft.ElevatedButton(
                "Generate Query",
                icon=ft.Icons.AUTO_FIX_HIGH,
                on_click=self._generate_query,
                style=ft.ButtonStyle(
                    bgcolor=ft.Colors.GREEN_600,
                    color=ft.Colors.WHITE
                ),
                height=45,
                width=150
            ),
            ft.ElevatedButton(
                "Clear All",
                icon=ft.Icons.CLEAR,
                on_click=self._clear_all,
                height=45,
                width=120
            ),
            ft.ElevatedButton(
                "Save Example",
                icon=ft.Icons.SAVE,
                on_click=self._save_example,
                height=45,
                width=130
            ),
            ft.ElevatedButton(
                "Load Example",
                icon=ft.Icons.UPLOAD,
                on_click=self._load_example,
                height=45,
                width=130
            ),
            ft.ElevatedButton(
                "Test Connection",
                icon=ft.Icons.WIFI,
                on_click=self._test_connection,
                style=ft.ButtonStyle(
                    bgcolor=ft.Colors.BLUE_600,
                    color=ft.Colors.WHITE
                ),
                height=45,
                width=150
            )
        ], 
        alignment=ft.MainAxisAlignment.CENTER,
        spacing=15
        )
    
    def _get_available_models(self) -> List[str]:
        """Get available models from Ollama."""
        try:
            import ollama
            client = ollama.Client(host=self.config.get_ollama_config()['host'])
            models_response = client.list()
            return sorted([model.model for model in models_response.models])
        except Exception:
            return [
                "medgemma4B_it_q8:latest",
                "medgemma-27b-text-it-Q8_0:latest", 
                "gpt-oss:20b"
            ]
    
    def _on_model_change(self, e):
        """Handle model selection change."""
        if self.query_agent:
            # Update agent configuration with new model
            new_model = self.controls['model'].value
            self.config.set('models.query_agent', new_model)
            self._reinit_agent()
    
    def _on_param_change(self, e):
        """Handle parameter change."""
        if self.query_agent:
            # Update agent configuration
            try:
                temp = self.controls['temperature'].value
                top_p = self.controls['top_p'].value
                max_tokens = int(self.controls['max_tokens'].value)
                
                self.config.set('agents.query.temperature', temp)
                self.config.set('agents.query.top_p', top_p)
                self.config.set('agents.query.max_tokens', max_tokens)
                
                self._reinit_agent()
            except ValueError:
                pass  # Ignore invalid input during typing
    
    def _on_query_change(self, e):
        """Handle query input change."""
        query_text = self.controls['human_query'].value
        if query_text:
            char_count = len(query_text)
            word_count = len(query_text.split())
            self.controls['query_stats'].value = f"Input: {char_count} chars, {word_count} words"
        else:
            self.controls['query_stats'].value = ""
        self.page.update()
    
    def _generate_query(self, e):
        """Generate PostgreSQL query from human language input."""
        
        human_query = self.controls['human_query'].value
        if not human_query.strip():
            self._show_error_dialog("Please enter a research question.")
            return
        
        # Update status
        self.controls['processing_status'].value = "Generating..."
        self.controls['processing_status'].color = ft.Colors.BLUE_600
        self.page.update()
        
        try:
            # Generate query using the agent
            result = self._run_query_generation(human_query)
            
            if result and 'query' in result:
                # Display generated query
                self.controls['postgres_query'].value = result['query']
                
                # Display explanation if available
                if 'explanation' in result:
                    self.controls['query_explanation'].value = result['explanation']
                else:
                    self.controls['query_explanation'].value = "Query generated successfully."
                
                # Update stats
                query_len = len(result['query'])
                self.controls['query_stats'].value += f" | Output: {query_len} chars"
                
                # Success status
                self.controls['processing_status'].value = "✅ Generated"
                self.controls['processing_status'].color = ft.Colors.GREEN_600
                
            else:
                raise Exception("No query generated")
                
        except Exception as ex:
            self.controls['processing_status'].value = f"❌ Error: {str(ex)[:50]}..."
            self.controls['processing_status'].color = ft.Colors.RED_600
            self.controls['postgres_query'].value = ""
            self.controls['query_explanation'].value = f"Error: {str(ex)}"
        
        self.page.update()
    
    def _run_query_generation(self, human_query: str):
        """Run query generation using the actual QueryAgent."""
        try:
            if self.query_agent and hasattr(self.query_agent, 'convert_question'):
                # Use the actual QueryAgent with the correct method name
                try:
                    query_result = self.query_agent.convert_question(human_query)
                    return {
                        'query': query_result,
                        'explanation': f"Generated using QueryAgent with model: {self.controls['model'].value}\n\nThis is a real PostgreSQL to_tsquery conversion optimized for biomedical literature search."
                    }
                except Exception as agent_error:
                    print(f"QueryAgent convert_question failed: {agent_error}")
                    # Fall back to simulation if agent method fails
                    return self._simulate_query_generation(human_query)
            else:
                # Fallback simulation when agent is not available
                print("QueryAgent not available or missing convert_question method")
                return self._simulate_query_generation(human_query)
        except Exception as e:
            raise Exception(f"Query generation failed: {str(e)}")
    
    def _simulate_query_generation(self, human_query: str):
        """Simulate query generation for testing purposes."""
        # Simple simulation that converts natural language to basic to_tsquery format
        words = human_query.lower().replace(',', '').replace('.', '').replace('?', '').split()
        
        # Filter out common stop words
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'what', 'how', 'when', 'where', 'why'}
        meaningful_words = [word for word in words if word not in stop_words and len(word) > 2]
        
        if len(meaningful_words) > 6:
            meaningful_words = meaningful_words[:6]  # Limit to first 6 meaningful words
        
        # Create a basic to_tsquery format
        query_terms = ' & '.join(meaningful_words)
        
        return {
            'query': f"to_tsquery('english', '{query_terms}')",
            'explanation': f"Simulated query generation (QueryAgent not fully available).\nExtracted {len(meaningful_words)} key terms from: '{human_query}'\nModel: {self.controls['model'].value}"
        }
    
    def _clear_all(self, e):
        """Clear all input and output fields."""
        self.controls['human_query'].value = ""
        self.controls['postgres_query'].value = ""
        self.controls['query_explanation'].value = ""
        self.controls['query_stats'].value = ""
        self.controls['processing_status'].value = "Ready"
        self.controls['processing_status'].color = ft.Colors.GREY_600
        self.page.update()
    
    def _save_example(self, e):
        """Save current query as an example."""
        human_query = self.controls['human_query'].value
        postgres_query = self.controls['postgres_query'].value
        
        if not human_query.strip() or not postgres_query.strip():
            self._show_error_dialog("Both human query and generated query must be present to save.")
            return
        
        example = {
            'human_query': human_query,
            'postgres_query': postgres_query,
            'model': self.controls['model'].value,
            'temperature': self.controls['temperature'].value,
            'top_p': self.controls['top_p'].value,
            'max_tokens': int(self.controls['max_tokens'].value)
        }
        
        def save_file(result):
            if result.path:
                try:
                    file_path = result.path
                    if not file_path.endswith('.json'):
                        file_path += '.json'
                    
                    with open(file_path, 'w') as f:
                        json.dump(example, f, indent=2)
                    
                    self._show_success_dialog(f"Example saved to {file_path}")
                except Exception as ex:
                    self._show_error_dialog(f"Failed to save example: {str(ex)}")
        
        file_picker = ft.FilePicker(on_result=save_file)
        self.page.overlay.append(file_picker)
        self.page.update()
        
        file_picker.save_file(
            dialog_title="Save Query Example",
            file_name="query_example.json",
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["json"]
        )
    
    def _load_example(self, e):
        """Load a saved example."""
        def load_file(result):
            if result.files:
                try:
                    with open(result.files[0].path, 'r') as f:
                        example = json.load(f)
                    
                    # Load the example data
                    self.controls['human_query'].value = example.get('human_query', '')
                    self.controls['postgres_query'].value = example.get('postgres_query', '')
                    
                    # Load model settings if available
                    if 'model' in example and example['model'] in [opt.key for opt in self.controls['model'].options]:
                        self.controls['model'].value = example['model']
                    
                    if 'temperature' in example:
                        self.controls['temperature'].value = example['temperature']
                    
                    if 'top_p' in example:
                        self.controls['top_p'].value = example['top_p']
                    
                    if 'max_tokens' in example:
                        self.controls['max_tokens'].value = str(example['max_tokens'])
                    
                    self.controls['processing_status'].value = "Example loaded"
                    self.controls['processing_status'].color = ft.Colors.GREEN_600
                    
                    self.page.update()
                    self._show_success_dialog("Example loaded successfully!")
                    
                except Exception as ex:
                    self._show_error_dialog(f"Failed to load example: {str(ex)}")
        
        file_picker = ft.FilePicker(on_result=load_file)
        self.page.overlay.append(file_picker)
        self.page.update()
        
        file_picker.pick_files(
            dialog_title="Load Query Example",
            allowed_extensions=["json"],
            file_type=ft.FilePickerFileType.CUSTOM
        )
    
    def _test_connection(self, e):
        """Test connection to database and Ollama."""
        try:
            # Test Ollama connection
            import ollama
            host = self.config.get_ollama_config()['host']
            client = ollama.Client(host=host)
            models_response = client.list()
            
            # Test QueryAgent initialization
            if self.query_agent:
                agent_status = "✅ QueryAgent initialized"
            else:
                agent_status = "❌ QueryAgent not initialized"
            
            model_count = len(models_response.models)
            
            self._show_success_dialog(
                f"Connection Test Results:\\n\\n"
                f"Ollama Server: ✅ Connected to {host}\\n"
                f"Available Models: {model_count} models found\\n"
                f"QueryAgent: {agent_status}"
            )
            
        except Exception as ex:
            self._show_error_dialog(f"Connection test failed: {str(ex)}")
    
    def _refresh_models(self, e):
        """Refresh available models."""
        try:
            available_models = self._get_available_models()
            current_selection = self.controls['model'].value
            
            self.controls['model'].options = [
                ft.dropdown.Option(model) for model in available_models
            ]
            
            if current_selection and current_selection in available_models:
                self.controls['model'].value = current_selection
            elif available_models:
                self.controls['model'].value = available_models[0]
            
            self.page.update()
            self._show_success_dialog(f"Refreshed models. Found {len(available_models)} models.")
            
        except Exception as ex:
            self._show_error_dialog(f"Failed to refresh models: {str(ex)}")
    
    def _reinit_agent(self):
        """Reinitialize agent with current configuration."""
        try:
            # Get current UI parameters
            model = self.controls['model'].value
            temperature = self.controls['temperature'].value
            top_p = self.controls['top_p'].value
            host = self.config.get_ollama_config()['host']
            
            print(f"🔄 Reinitializing QueryAgent with model: {model}")
            
            if self.orchestrator:
                self.query_agent = QueryAgent(
                    model=model,
                    host=host,
                    temperature=temperature,
                    top_p=top_p,
                    orchestrator=self.orchestrator,
                    show_model_info=True
                )
                # Check if agent is properly initialized
                agent_ready = self.query_agent and hasattr(self.query_agent, 'convert_question')
                if agent_ready:
                    self.controls['agent_status'].value = f"Agent: Ready (QueryAgent active) - {model}"
                    self.controls['agent_status'].color = ft.Colors.GREEN_600
                else:
                    self.controls['agent_status'].value = "Agent: Simulation mode"
                    self.controls['agent_status'].color = ft.Colors.ORANGE_600
            else:
                # Try without orchestrator
                try:
                    self.query_agent = QueryAgent(
                        model=model,
                        host=host,
                        temperature=temperature,
                        top_p=top_p,
                        orchestrator=None,
                        show_model_info=True
                    )
                    agent_ready = self.query_agent and hasattr(self.query_agent, 'convert_question')
                    if agent_ready:
                        self.controls['agent_status'].value = f"Agent: Ready (QueryAgent active) - {model}"
                        self.controls['agent_status'].color = ft.Colors.GREEN_600
                    else:
                        self.controls['agent_status'].value = "Agent: Simulation mode"
                        self.controls['agent_status'].color = ft.Colors.ORANGE_600
                except Exception as ex:
                    print(f"Failed to init without orchestrator: {ex}")
                    self.controls['agent_status'].value = "Agent: Simulation mode"
                    self.controls['agent_status'].color = ft.Colors.ORANGE_600
                    self.query_agent = None
        except Exception as e:
            print(f"Failed to reinitialize agent: {e}")
            self.controls['agent_status'].value = "Agent: Error - Simulation mode"
            self.controls['agent_status'].color = ft.Colors.RED_600
            self.query_agent = None
        
        if self.page:
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
    
    def _close_dialog(self):
        """Close the current dialog."""
        if self.page.overlay:
            self.page.overlay.clear()
            self.page.update()


def run_query_lab():
    """Run the QueryAgent Lab application."""
    app = QueryAgentLab()
    ft.app(target=app.main, view=ft.FLET_APP)


if __name__ == "__main__":
    run_query_lab()