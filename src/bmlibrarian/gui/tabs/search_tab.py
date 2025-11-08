"""
Search Settings Tab for BMLibrarian Configuration GUI.

Provides configuration for literature search strategies including:
- Keyword fulltext search
- BM25 ranking
- Semantic search
- Semantic search with HyDE (Hypothetical Document Embeddings)
"""

import flet as ft
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config_app import BMLibrarianConfigApp


class SearchSettingsTab:
    """Search strategy configuration tab."""

    def __init__(self, app: "BMLibrarianConfigApp"):
        self.app = app
        self.controls = {}

    def build(self) -> ft.Container:
        """Build the search settings tab content."""

        # Header
        header = ft.Container(
            ft.Column([
                ft.Text(
                    "Literature Search Strategy",
                    size=20,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.BLUE_700
                ),
                ft.Text(
                    "Configure search methods for literature retrieval. Enable multiple strategies for hybrid search.",
                    size=13,
                    color=ft.Colors.GREY_700,
                    italic=True
                )
            ]),
            margin=ft.margin.only(bottom=20)
        )

        # Search Strategy Sections
        keyword_section = self._build_keyword_search_section()
        bm25_section = self._build_bm25_section()
        semantic_section = self._build_semantic_section()
        hyde_section = self._build_hyde_section()

        # Create scrollable content
        content = ft.Column([
            header,
            keyword_section,
            ft.Divider(height=20),
            bm25_section,
            ft.Divider(height=20),
            semantic_section,
            ft.Divider(height=20),
            hyde_section,
            ft.Container(height=50)  # Bottom padding
        ],
        spacing=10
        )

        return ft.Container(
            content=ft.ListView([content], spacing=0, padding=ft.padding.all(20)),
            expand=True
        )

    def _build_keyword_search_section(self) -> ft.Container:
        """Build keyword fulltext search configuration."""
        search_config = self.app.config.get('search_strategy', {})
        keyword_config = search_config.get('keyword', {})

        # Enable toggle
        self.controls['keyword_enabled'] = ft.Switch(
            label="Enable Keyword Fulltext Search",
            value=keyword_config.get('enabled', True),
            active_color=ft.Colors.GREEN_600,
            on_change=self._on_keyword_toggle,
            tooltip="PostgreSQL fulltext search using keywords"
        )

        # Max results
        self.controls['keyword_max_results'] = ft.TextField(
            label="Max Results",
            value=str(keyword_config.get('max_results', 100)),
            width=200,
            helper_text="Maximum documents to retrieve",
            input_filter=ft.NumbersOnlyInputFilter(),
            disabled=not keyword_config.get('enabled', True)
        )

        # Search operator (AND/OR)
        self.controls['keyword_operator'] = ft.Dropdown(
            label="Search Operator",
            value=keyword_config.get('operator', 'AND'),
            options=[
                ft.dropdown.Option("AND"),
                ft.dropdown.Option("OR")
            ],
            width=150,
            tooltip="How to combine search terms",
            disabled=not keyword_config.get('enabled', True)
        )

        # Case sensitive
        self.controls['keyword_case_sensitive'] = ft.Checkbox(
            label="Case sensitive",
            value=keyword_config.get('case_sensitive', False),
            tooltip="Perform case-sensitive matching",
            disabled=not keyword_config.get('enabled', True)
        )

        return ft.Container(
            ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.SEARCH, color=ft.Colors.BLUE_700, size=24),
                    ft.Text("Keyword Fulltext Search", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_700)
                ], spacing=10),
                ft.Container(height=10),
                self.controls['keyword_enabled'],
                ft.Container(height=10),
                ft.Row([
                    self.controls['keyword_max_results'],
                    self.controls['keyword_operator']
                ], spacing=20),
                self.controls['keyword_case_sensitive']
            ]),
            padding=ft.padding.all(15),
            bgcolor=ft.Colors.GREY_50,
            border_radius=8,
            border=ft.border.all(1, ft.Colors.GREY_300)
        )

    def _build_bm25_section(self) -> ft.Container:
        """Build BM25 ranking configuration."""
        search_config = self.app.config.get('search_strategy', {})
        bm25_config = search_config.get('bm25', {})

        # Enable toggle
        self.controls['bm25_enabled'] = ft.Switch(
            label="Enable BM25 Ranking",
            value=bm25_config.get('enabled', False),
            active_color=ft.Colors.GREEN_600,
            on_change=self._on_bm25_toggle,
            tooltip="Best Match 25 probabilistic ranking algorithm"
        )

        # Max results
        self.controls['bm25_max_results'] = ft.TextField(
            label="Max Results",
            value=str(bm25_config.get('max_results', 100)),
            width=200,
            helper_text="Maximum documents to retrieve",
            input_filter=ft.NumbersOnlyInputFilter(),
            disabled=not bm25_config.get('enabled', False)
        )

        # k1 parameter (term frequency saturation)
        self.controls['bm25_k1_text'] = ft.Text(
            f"{bm25_config.get('k1', 1.2):.2f}",
            size=14,
            weight=ft.FontWeight.W_500,
            width=60
        )
        self.controls['bm25_k1'] = ft.Slider(
            min=0.5,
            max=3.0,
            value=bm25_config.get('k1', 1.2),
            divisions=25,
            label="{value}",
            width=300,
            tooltip="Term frequency saturation parameter (typical: 1.2-2.0)",
            on_change=self._on_bm25_k1_changed,
            disabled=not bm25_config.get('enabled', False)
        )

        # b parameter (length normalization)
        self.controls['bm25_b_text'] = ft.Text(
            f"{bm25_config.get('b', 0.75):.2f}",
            size=14,
            weight=ft.FontWeight.W_500,
            width=60
        )
        self.controls['bm25_b'] = ft.Slider(
            min=0.0,
            max=1.0,
            value=bm25_config.get('b', 0.75),
            divisions=20,
            label="{value}",
            width=300,
            tooltip="Document length normalization (0=none, 1=full, typical: 0.75)",
            on_change=self._on_bm25_b_changed,
            disabled=not bm25_config.get('enabled', False)
        )

        return ft.Container(
            ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.ANALYTICS, color=ft.Colors.PURPLE_700, size=24),
                    ft.Text("BM25 Ranking", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.PURPLE_700)
                ], spacing=10),
                ft.Container(height=10),
                self.controls['bm25_enabled'],
                ft.Container(height=10),
                self.controls['bm25_max_results'],
                ft.Container(height=10),
                ft.Row([
                    ft.Text("k1 (Term Frequency):", width=180),
                    self.controls['bm25_k1'],
                    self.controls['bm25_k1_text']
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Row([
                    ft.Text("b (Length Norm):", width=180),
                    self.controls['bm25_b'],
                    self.controls['bm25_b_text']
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER)
            ]),
            padding=ft.padding.all(15),
            bgcolor=ft.Colors.GREY_50,
            border_radius=8,
            border=ft.border.all(1, ft.Colors.GREY_300)
        )

    def _build_semantic_section(self) -> ft.Container:
        """Build semantic search configuration."""
        search_config = self.app.config.get('search_strategy', {})
        semantic_config = search_config.get('semantic', {})

        # Enable toggle
        self.controls['semantic_enabled'] = ft.Switch(
            label="Enable Semantic Search",
            value=semantic_config.get('enabled', False),
            active_color=ft.Colors.GREEN_600,
            on_change=self._on_semantic_toggle,
            tooltip="Vector similarity search using embeddings"
        )

        # Max results
        self.controls['semantic_max_results'] = ft.TextField(
            label="Max Results",
            value=str(semantic_config.get('max_results', 100)),
            width=200,
            helper_text="Maximum documents to retrieve",
            input_filter=ft.NumbersOnlyInputFilter(),
            disabled=not semantic_config.get('enabled', False)
        )

        # Embedding model
        available_models = self._get_available_models()
        self.controls['semantic_embedding_model'] = ft.Dropdown(
            label="Embedding Model",
            value=semantic_config.get('embedding_model', 'nomic-embed-text:latest'),
            options=[ft.dropdown.Option(model) for model in available_models],
            width=350,
            tooltip="Model for generating query embeddings",
            disabled=not semantic_config.get('enabled', False)
        )

        # Similarity threshold
        self.controls['semantic_threshold_text'] = ft.Text(
            f"{semantic_config.get('similarity_threshold', 0.7):.2f}",
            size=14,
            weight=ft.FontWeight.W_500,
            width=60
        )
        self.controls['semantic_threshold'] = ft.Slider(
            min=0.0,
            max=1.0,
            value=semantic_config.get('similarity_threshold', 0.7),
            divisions=20,
            label="{value}",
            width=300,
            tooltip="Minimum cosine similarity score (0-1)",
            on_change=self._on_semantic_threshold_changed,
            disabled=not semantic_config.get('enabled', False)
        )

        return ft.Container(
            ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.PSYCHOLOGY, color=ft.Colors.TEAL_700, size=24),
                    ft.Text("Semantic Search", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.TEAL_700)
                ], spacing=10),
                ft.Container(height=10),
                self.controls['semantic_enabled'],
                ft.Container(height=10),
                ft.Row([
                    self.controls['semantic_max_results'],
                    self.controls['semantic_embedding_model']
                ], spacing=20),
                ft.Container(height=10),
                ft.Row([
                    ft.Text("Similarity Threshold:", width=180),
                    self.controls['semantic_threshold'],
                    self.controls['semantic_threshold_text']
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER)
            ]),
            padding=ft.padding.all(15),
            bgcolor=ft.Colors.GREY_50,
            border_radius=8,
            border=ft.border.all(1, ft.Colors.GREY_300)
        )

    def _build_hyde_section(self) -> ft.Container:
        """Build HyDE (Hypothetical Document Embeddings) configuration."""
        search_config = self.app.config.get('search_strategy', {})
        hyde_config = search_config.get('hyde', {})

        # Enable toggle
        self.controls['hyde_enabled'] = ft.Switch(
            label="Enable HyDE (Hypothetical Document Embeddings)",
            value=hyde_config.get('enabled', False),
            active_color=ft.Colors.GREEN_600,
            on_change=self._on_hyde_toggle,
            tooltip="Generate hypothetical documents for improved semantic search"
        )

        # Max results
        self.controls['hyde_max_results'] = ft.TextField(
            label="Max Results",
            value=str(hyde_config.get('max_results', 100)),
            width=200,
            helper_text="Maximum documents to retrieve",
            input_filter=ft.NumbersOnlyInputFilter(),
            disabled=not hyde_config.get('enabled', False)
        )

        # Generation model
        available_models = self._get_available_models()
        self.controls['hyde_generation_model'] = ft.Dropdown(
            label="HyDE Generation Model",
            value=hyde_config.get('generation_model', 'medgemma-27b-text-it-Q8_0:latest'),
            options=[ft.dropdown.Option(model) for model in available_models],
            width=350,
            tooltip="Model for generating hypothetical documents",
            disabled=not hyde_config.get('enabled', False)
        )

        # Embedding model
        self.controls['hyde_embedding_model'] = ft.Dropdown(
            label="Embedding Model",
            value=hyde_config.get('embedding_model', 'nomic-embed-text:latest'),
            options=[ft.dropdown.Option(model) for model in available_models],
            width=350,
            tooltip="Model for embedding hypothetical documents",
            disabled=not hyde_config.get('enabled', False)
        )

        # Number of hypothetical documents
        self.controls['hyde_num_docs_text'] = ft.Text(
            f"{hyde_config.get('num_hypothetical_docs', 3)}",
            size=14,
            weight=ft.FontWeight.W_500,
            width=60
        )
        self.controls['hyde_num_docs'] = ft.Slider(
            min=1,
            max=5,
            value=hyde_config.get('num_hypothetical_docs', 3),
            divisions=4,
            label="{value}",
            width=300,
            tooltip="Number of hypothetical documents to generate",
            on_change=self._on_hyde_num_docs_changed,
            disabled=not hyde_config.get('enabled', False)
        )

        # Similarity threshold
        self.controls['hyde_threshold_text'] = ft.Text(
            f"{hyde_config.get('similarity_threshold', 0.7):.2f}",
            size=14,
            weight=ft.FontWeight.W_500,
            width=60
        )
        self.controls['hyde_threshold'] = ft.Slider(
            min=0.0,
            max=1.0,
            value=hyde_config.get('similarity_threshold', 0.7),
            divisions=20,
            label="{value}",
            width=300,
            tooltip="Minimum cosine similarity score (0-1)",
            on_change=self._on_hyde_threshold_changed,
            disabled=not hyde_config.get('enabled', False)
        )

        return ft.Container(
            ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.AUTO_AWESOME, color=ft.Colors.ORANGE_700, size=24),
                    ft.Text("HyDE Search", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.ORANGE_700)
                ], spacing=10),
                ft.Container(height=10),
                self.controls['hyde_enabled'],
                ft.Container(height=10),
                ft.Row([
                    self.controls['hyde_max_results'],
                    self.controls['hyde_generation_model']
                ], spacing=20),
                self.controls['hyde_embedding_model'],
                ft.Container(height=10),
                ft.Row([
                    ft.Text("Hypothetical Docs:", width=180),
                    self.controls['hyde_num_docs'],
                    self.controls['hyde_num_docs_text']
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Row([
                    ft.Text("Similarity Threshold:", width=180),
                    self.controls['hyde_threshold'],
                    self.controls['hyde_threshold_text']
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER)
            ]),
            padding=ft.padding.all(15),
            bgcolor=ft.Colors.GREY_50,
            border_radius=8,
            border=ft.border.all(1, ft.Colors.GREY_300)
        )

    def _get_available_models(self) -> list:
        """Get list of available Ollama models."""
        try:
            import ollama
            host = self.app.config.get_ollama_config()['host']
            client = ollama.Client(host=host)
            models_response = client.list()
            return sorted([model.model for model in models_response.models])
        except Exception as ex:
            print(f"Warning: Could not fetch models: {ex}")
            return [
                "medgemma-27b-text-it-Q8_0:latest",
                "medgemma4B_it_q8:latest",
                "gpt-oss:20b",
                "nomic-embed-text:latest"
            ]

    # Event handlers for toggle switches
    def _on_keyword_toggle(self, e):
        """Handle keyword search toggle."""
        enabled = self.controls['keyword_enabled'].value
        self.controls['keyword_max_results'].disabled = not enabled
        self.controls['keyword_operator'].disabled = not enabled
        self.controls['keyword_case_sensitive'].disabled = not enabled
        self.app.page.update()

    def _on_bm25_toggle(self, e):
        """Handle BM25 toggle."""
        enabled = self.controls['bm25_enabled'].value
        self.controls['bm25_max_results'].disabled = not enabled
        self.controls['bm25_k1'].disabled = not enabled
        self.controls['bm25_b'].disabled = not enabled
        self.app.page.update()

    def _on_semantic_toggle(self, e):
        """Handle semantic search toggle."""
        enabled = self.controls['semantic_enabled'].value
        self.controls['semantic_max_results'].disabled = not enabled
        self.controls['semantic_embedding_model'].disabled = not enabled
        self.controls['semantic_threshold'].disabled = not enabled
        self.app.page.update()

    def _on_hyde_toggle(self, e):
        """Handle HyDE toggle."""
        enabled = self.controls['hyde_enabled'].value
        self.controls['hyde_max_results'].disabled = not enabled
        self.controls['hyde_generation_model'].disabled = not enabled
        self.controls['hyde_embedding_model'].disabled = not enabled
        self.controls['hyde_num_docs'].disabled = not enabled
        self.controls['hyde_threshold'].disabled = not enabled
        self.app.page.update()

    # Event handlers for sliders
    def _on_bm25_k1_changed(self, e):
        """Handle BM25 k1 parameter change."""
        value = self.controls['bm25_k1'].value
        self.controls['bm25_k1_text'].value = f"{value:.2f}"
        self.app.page.update()

    def _on_bm25_b_changed(self, e):
        """Handle BM25 b parameter change."""
        value = self.controls['bm25_b'].value
        self.controls['bm25_b_text'].value = f"{value:.2f}"
        self.app.page.update()

    def _on_semantic_threshold_changed(self, e):
        """Handle semantic threshold change."""
        value = self.controls['semantic_threshold'].value
        self.controls['semantic_threshold_text'].value = f"{value:.2f}"
        self.app.page.update()

    def _on_hyde_num_docs_changed(self, e):
        """Handle HyDE num docs change."""
        value = self.controls['hyde_num_docs'].value
        self.controls['hyde_num_docs_text'].value = f"{int(value)}"
        self.app.page.update()

    def _on_hyde_threshold_changed(self, e):
        """Handle HyDE threshold change."""
        value = self.controls['hyde_threshold'].value
        self.controls['hyde_threshold_text'].value = f"{value:.2f}"
        self.app.page.update()

    def update_config(self):
        """Update configuration from UI controls."""
        print("🔧 Updating search strategy settings from UI...")
        try:
            # Keyword search
            keyword_config = {
                'enabled': self.controls['keyword_enabled'].value,
                'max_results': int(self.controls['keyword_max_results'].value),
                'operator': self.controls['keyword_operator'].value,
                'case_sensitive': self.controls['keyword_case_sensitive'].value
            }
            self.app.config.set('search_strategy.keyword', keyword_config)
            print(f"  Keyword: enabled={keyword_config['enabled']}, max={keyword_config['max_results']}")

            # BM25
            bm25_config = {
                'enabled': self.controls['bm25_enabled'].value,
                'max_results': int(self.controls['bm25_max_results'].value),
                'k1': self.controls['bm25_k1'].value,
                'b': self.controls['bm25_b'].value
            }
            self.app.config.set('search_strategy.bm25', bm25_config)
            print(f"  BM25: enabled={bm25_config['enabled']}, k1={bm25_config['k1']:.2f}, b={bm25_config['b']:.2f}")

            # Semantic
            semantic_config = {
                'enabled': self.controls['semantic_enabled'].value,
                'max_results': int(self.controls['semantic_max_results'].value),
                'embedding_model': self.controls['semantic_embedding_model'].value,
                'similarity_threshold': self.controls['semantic_threshold'].value
            }
            self.app.config.set('search_strategy.semantic', semantic_config)
            print(f"  Semantic: enabled={semantic_config['enabled']}, threshold={semantic_config['similarity_threshold']:.2f}")

            # HyDE
            hyde_config = {
                'enabled': self.controls['hyde_enabled'].value,
                'max_results': int(self.controls['hyde_max_results'].value),
                'generation_model': self.controls['hyde_generation_model'].value,
                'embedding_model': self.controls['hyde_embedding_model'].value,
                'num_hypothetical_docs': int(self.controls['hyde_num_docs'].value),
                'similarity_threshold': self.controls['hyde_threshold'].value
            }
            self.app.config.set('search_strategy.hyde', hyde_config)
            print(f"  HyDE: enabled={hyde_config['enabled']}, num_docs={hyde_config['num_hypothetical_docs']}")

            print("✅ Search strategy settings updated")

        except Exception as ex:
            print(f"❌ Error updating search settings: {ex}")

    def refresh(self):
        """Refresh tab with current configuration."""
        search_config = self.app.config.get('search_strategy', {})

        # Keyword
        keyword_config = search_config.get('keyword', {})
        self.controls['keyword_enabled'].value = keyword_config.get('enabled', True)
        self.controls['keyword_max_results'].value = str(keyword_config.get('max_results', 100))
        self.controls['keyword_operator'].value = keyword_config.get('operator', 'AND')
        self.controls['keyword_case_sensitive'].value = keyword_config.get('case_sensitive', False)

        # BM25
        bm25_config = search_config.get('bm25', {})
        self.controls['bm25_enabled'].value = bm25_config.get('enabled', False)
        self.controls['bm25_max_results'].value = str(bm25_config.get('max_results', 100))
        self.controls['bm25_k1'].value = bm25_config.get('k1', 1.2)
        self.controls['bm25_b'].value = bm25_config.get('b', 0.75)

        # Semantic
        semantic_config = search_config.get('semantic', {})
        self.controls['semantic_enabled'].value = semantic_config.get('enabled', False)
        self.controls['semantic_max_results'].value = str(semantic_config.get('max_results', 100))
        self.controls['semantic_embedding_model'].value = semantic_config.get('embedding_model', 'nomic-embed-text:latest')
        self.controls['semantic_threshold'].value = semantic_config.get('similarity_threshold', 0.7)

        # HyDE
        hyde_config = search_config.get('hyde', {})
        self.controls['hyde_enabled'].value = hyde_config.get('enabled', False)
        self.controls['hyde_max_results'].value = str(hyde_config.get('max_results', 100))
        self.controls['hyde_generation_model'].value = hyde_config.get('generation_model', 'medgemma-27b-text-it-Q8_0:latest')
        self.controls['hyde_embedding_model'].value = hyde_config.get('embedding_model', 'nomic-embed-text:latest')
        self.controls['hyde_num_docs'].value = hyde_config.get('num_hypothetical_docs', 3)
        self.controls['hyde_threshold'].value = hyde_config.get('similarity_threshold', 0.7)

        if self.app.page:
            self.app.page.update()
