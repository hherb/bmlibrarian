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
        
        # Create scrollable content
        content = ft.Column([
            ollama_section,
            ft.Divider(height=20),
            database_section,
            ft.Divider(height=20),
            cli_section,
            ft.Container(height=50)  # Bottom padding
        ], 
        spacing=10
        )
        
        return ft.Container(
            content=ft.ListView([content], spacing=0, padding=ft.padding.all(20)),
            expand=True
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
        
        # Get search config for default values
        search_config = self.app.config.get_search_config()

        # Search Settings - Store controls for later updates
        self.controls['max_search_results'] = ft.TextField(
            label="Max Search Results",
            value=str(search_config.get('max_results', 100)),
            width=200,
            helper_text="Maximum search results to retrieve",
            input_filter=ft.NumbersOnlyInputFilter()
        )

        self.controls['display_limit'] = ft.TextField(
            label="Display Limit",
            value="10",
            width=200,
            helper_text="Maximum documents to display",
            input_filter=ft.NumbersOnlyInputFilter()
        )

        self.controls['score_threshold'] = ft.TextField(
            label="Score Threshold",
            value=str(search_config.get('score_threshold', 2.5)),
            width=200,
            helper_text="Default document score threshold",
            input_filter=ft.InputFilter(allow=True, regex_string=r"[0-9.]", replacement_string="")
        )

        self.controls['min_relevance'] = ft.TextField(
            label="Min Relevance",
            value="0.7",
            width=200,
            helper_text="Minimum citation relevance",
            input_filter=ft.InputFilter(allow=True, regex_string=r"[0-9.]", replacement_string="")
        )

        # Iterative Search Settings (NEW)
        self.controls['min_relevant'] = ft.TextField(
            label="Min Relevant Docs",
            value=str(search_config.get('min_relevant', 10)),
            width=200,
            helper_text="Minimum high-scoring docs to find",
            input_filter=ft.NumbersOnlyInputFilter()
        )

        self.controls['search_max_retry'] = ft.TextField(
            label="Max Retries",
            value=str(search_config.get('max_retry', 3)),
            width=200,
            helper_text="Max retries per search strategy",
            input_filter=ft.NumbersOnlyInputFilter()
        )

        self.controls['search_batch_size'] = ft.TextField(
            label="Search Batch Size",
            value=str(search_config.get('batch_size', 100)),
            width=200,
            helper_text="Documents per iteration",
            input_filter=ft.NumbersOnlyInputFilter()
        )

        search_section = ft.Column([
            ft.Text("Search Settings", size=16, weight=ft.FontWeight.BOLD),
            ft.Row([
                self.controls['max_search_results'],
                self.controls['display_limit']
            ], spacing=20),
            ft.Row([
                self.controls['score_threshold'],
                self.controls['min_relevance']
            ], spacing=20),
            ft.Container(height=5),
            ft.Text("Iterative Search (for finding more relevant documents)", size=14, italic=True, color=ft.Colors.GREY_700),
            ft.Row([
                self.controls['min_relevant'],
                self.controls['search_max_retry']
            ], spacing=20),
            ft.Row([
                self.controls['search_batch_size']
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
        print("🔧 Updating general settings from UI...")  # Debug
        try:
            # Update Ollama settings
            host = self.controls['ollama_host'].value
            timeout = int(self.controls['ollama_timeout'].value)
            retries = int(self.controls['ollama_retries'].value)

            self.app.config.set('ollama.host', host)
            self.app.config.set('ollama.timeout', timeout)
            self.app.config.set('ollama.max_retries', retries)

            print(f"  Ollama: {host}, timeout: {timeout}s, retries: {retries}")

            # Update Database settings
            max_results = int(self.controls['max_results'].value)
            batch_size = int(self.controls['batch_size'].value)
            use_ranking = self.controls['use_ranking'].value

            self.app.config.set('database.max_results_per_query', max_results)
            self.app.config.set('database.batch_size', batch_size)
            self.app.config.set('database.use_ranking', use_ranking)

            print(f"  Database: max_results={max_results}, batch_size={batch_size}, ranking={use_ranking}")

            # Update Search settings (NEW)
            if 'max_search_results' in self.controls:
                max_search_results = int(self.controls['max_search_results'].value)
                score_threshold = float(self.controls['score_threshold'].value)
                min_relevant = int(self.controls['min_relevant'].value)
                search_max_retry = int(self.controls['search_max_retry'].value)
                search_batch_size = int(self.controls['search_batch_size'].value)

                self.app.config.set('search.max_results', max_search_results)
                self.app.config.set('search.score_threshold', score_threshold)
                self.app.config.set('search.min_relevant', min_relevant)
                self.app.config.set('search.max_retry', search_max_retry)
                self.app.config.set('search.batch_size', search_batch_size)

                print(f"  Search: max={max_search_results}, threshold={score_threshold}, min_relevant={min_relevant}")
                print(f"  Iterative: max_retry={search_max_retry}, batch_size={search_batch_size}")

            print("✅ General settings updated")

        except Exception as ex:
            print(f"❌ Error updating general settings: {ex}")
    
    def refresh(self):
        """Refresh tab with current configuration."""
        ollama_config = self.app.config.get_ollama_config()
        db_config = self.app.config.get_database_config()
        search_config = self.app.config.get_search_config()

        self.controls['ollama_host'].value = ollama_config.get('host', 'http://localhost:11434')
        self.controls['ollama_timeout'].value = str(ollama_config.get('timeout', 120))
        self.controls['ollama_retries'].value = str(ollama_config.get('max_retries', 3))

        self.controls['max_results'].value = str(db_config.get('max_results_per_query', 10))
        self.controls['batch_size'].value = str(db_config.get('batch_size', 50))
        self.controls['use_ranking'].value = db_config.get('use_ranking', False)

        # Refresh search settings (NEW)
        if 'max_search_results' in self.controls:
            self.controls['max_search_results'].value = str(search_config.get('max_results', 100))
            self.controls['score_threshold'].value = str(search_config.get('score_threshold', 2.5))
            self.controls['min_relevant'].value = str(search_config.get('min_relevant', 10))
            self.controls['search_max_retry'].value = str(search_config.get('max_retry', 3))
            self.controls['search_batch_size'].value = str(search_config.get('batch_size', 100))