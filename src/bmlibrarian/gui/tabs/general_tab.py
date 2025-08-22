"""
General Settings Tab for BMLibrarian Configuration GUI.
"""

import flet as ft
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config_app import BMLibrarianConfigApp


class GeneralSettingsTab:
    """General settings configuration tab."""
    
    def __init__(self, app: "BMLibrarianConfigApp"):
        self.app = app
        self.controls = {}
        
    def build(self) -> ft.Container:
        """Build the general settings tab content."""
        
        # Ollama Settings Section
        ollama_section = self._build_ollama_section()
        
        # Database Settings Section  
        database_section = self._build_database_section()
        
        # CLI Settings Section
        cli_section = self._build_cli_section()
        
        return ft.Container(
            ft.Column([
                ollama_section,
                ft.Divider(),
                database_section,
                ft.Divider(),
                cli_section
            ], scroll=ft.ScrollMode.AUTO),
            padding=ft.padding.all(20)
        )
    
    def _build_ollama_section(self) -> ft.Container:
        """Build Ollama configuration section."""
        ollama_config = self.app.config.get_ollama_config()
        
        # Ollama Host
        self.controls['ollama_host'] = ft.TextField(
            label="Ollama Host",
            value=ollama_config.get('host', 'http://localhost:11434'),
            width=400,
            helper_text="URL of the Ollama server"
        )
        
        # Ollama Timeout
        self.controls['ollama_timeout'] = ft.TextField(
            label="Timeout (seconds)",
            value=str(ollama_config.get('timeout', 120)),
            width=200,
            helper_text="Request timeout in seconds",
            input_filter=ft.NumbersOnlyInputFilter()
        )
        
        # Max Retries
        self.controls['ollama_retries'] = ft.TextField(
            label="Max Retries",
            value=str(ollama_config.get('max_retries', 3)),
            width=200,
            helper_text="Maximum retry attempts",
            input_filter=ft.NumbersOnlyInputFilter()
        )
        
        return ft.Container(
            ft.Column([
                ft.Text("Ollama Settings", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_700),
                ft.Row([
                    self.controls['ollama_host']
                ]),
                ft.Row([
                    self.controls['ollama_timeout'],
                    self.controls['ollama_retries']
                ], spacing=20)
            ]),
            margin=ft.margin.only(bottom=20)
        )
    
    def _build_database_section(self) -> ft.Container:
        """Build database configuration section."""
        db_config = self.app.config.get_database_config()
        
        # Max Results Per Query
        self.controls['max_results'] = ft.TextField(
            label="Max Results Per Query",
            value=str(db_config.get('max_results_per_query', 10)),
            width=200,
            helper_text="Maximum documents per query",
            input_filter=ft.NumbersOnlyInputFilter()
        )
        
        # Batch Size
        self.controls['batch_size'] = ft.TextField(
            label="Batch Size",
            value=str(db_config.get('batch_size', 50)),
            width=200,
            helper_text="Processing batch size",
            input_filter=ft.NumbersOnlyInputFilter()
        )
        
        # Use Ranking
        self.controls['use_ranking'] = ft.Checkbox(
            label="Use document ranking",
            value=db_config.get('use_ranking', False),
            tooltip="Enable document ranking algorithms"
        )
        
        return ft.Container(
            ft.Column([
                ft.Text("Database Settings", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_700),
                ft.Row([
                    self.controls['max_results'],
                    self.controls['batch_size']
                ], spacing=20),
                self.controls['use_ranking']
            ]),
            margin=ft.margin.only(bottom=20)
        )
    
    def _build_cli_section(self) -> ft.Container:
        """Build CLI configuration section."""
        # Create CLI config controls based on existing CLI config structure
        cli_controls = []
        
        # Search Settings
        search_section = ft.Column([
            ft.Text("Search Settings", size=16, weight=ft.FontWeight.BOLD),
            ft.Row([
                ft.TextField(
                    label="Max Search Results",
                    value="100",
                    width=200,
                    helper_text="Maximum search results to retrieve",
                    input_filter=ft.NumbersOnlyInputFilter()
                ),
                ft.TextField(
                    label="Display Limit",
                    value="10",
                    width=200,
                    helper_text="Maximum documents to display",
                    input_filter=ft.NumbersOnlyInputFilter()
                )
            ], spacing=20),
            ft.Row([
                ft.TextField(
                    label="Score Threshold",
                    value="2.5",
                    width=200,
                    helper_text="Default document score threshold",
                    input_filter=ft.InputFilter(allow=True, regex_string=r"[0-9.]", replacement_string="")
                ),
                ft.TextField(
                    label="Min Relevance",
                    value="0.7",
                    width=200,
                    helper_text="Minimum citation relevance",
                    input_filter=ft.InputFilter(allow=True, regex_string=r"[0-9.]", replacement_string="")
                )
            ], spacing=20)
        ])
        
        # Processing Settings
        processing_section = ft.Column([
            ft.Text("Processing Settings", size=16, weight=ft.FontWeight.BOLD),
            ft.Row([
                ft.TextField(
                    label="Timeout (minutes)",
                    value="5.0",
                    width=200,
                    helper_text="Processing timeout in minutes",
                    input_filter=ft.InputFilter(allow=True, regex_string=r"[0-9.]", replacement_string="")
                ),
                ft.TextField(
                    label="Max Workers",
                    value="4",
                    width=200,
                    helper_text="Number of worker threads",
                    input_filter=ft.NumbersOnlyInputFilter()
                )
            ], spacing=20)
        ])
        
        return ft.Container(
            ft.Column([
                ft.Text("CLI Settings", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_700),
                search_section,
                ft.Container(height=10),  # Spacer
                processing_section
            ]),
            margin=ft.margin.only(bottom=20)
        )
    
    def update_config(self):
        """Update configuration from UI controls."""
        # Update Ollama settings
        self.app.config.set('ollama.host', self.controls['ollama_host'].value)
        self.app.config.set('ollama.timeout', int(self.controls['ollama_timeout'].value))
        self.app.config.set('ollama.max_retries', int(self.controls['ollama_retries'].value))
        
        # Update Database settings
        self.app.config.set('database.max_results_per_query', int(self.controls['max_results'].value))
        self.app.config.set('database.batch_size', int(self.controls['batch_size'].value))
        self.app.config.set('database.use_ranking', self.controls['use_ranking'].value)
    
    def refresh(self):
        """Refresh tab with current configuration."""
        ollama_config = self.app.config.get_ollama_config()
        db_config = self.app.config.get_database_config()
        
        self.controls['ollama_host'].value = ollama_config.get('host', 'http://localhost:11434')
        self.controls['ollama_timeout'].value = str(ollama_config.get('timeout', 120))
        self.controls['ollama_retries'].value = str(ollama_config.get('max_retries', 3))
        
        self.controls['max_results'].value = str(db_config.get('max_results_per_query', 10))
        self.controls['batch_size'].value = str(db_config.get('batch_size', 50))
        self.controls['use_ranking'].value = db_config.get('use_ranking', False)