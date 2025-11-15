"""
CitationAgent Lab - Experimental GUI for testing citation extraction

Provides an interactive interface for experimenting with the CitationFinderAgent,
including custom prompt editing and citation extraction from document abstracts.
"""

import flet as ft
import json
import re
import time
import requests
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from difflib import SequenceMatcher
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from bmlibrarian.config import get_config


# Default citation extraction prompt (extracted from CitationFinderAgent)
DEFAULT_CITATION_PROMPT = """You are a research assistant tasked with extracting ALL relevant citations from scientific papers.

Given the user question and document below, extract ALL passages that either support or contradict the question or statement.

User Question: "{user_question}"

Document Title: {title}
Abstract: {abstract}

Your task:
1. Identify ALL relevant passages from the abstract that answer the question or relate to it
2. For each passage, create a brief 1-2 sentence summary of how it relates
3. Rate the confidence/relevance on a scale of 0.0 to 1.0 (where 1.0 is perfectly relevant)
4. Indicate whether each passage SUPPORTS, CONTRADICTS, or is NEUTRAL regarding the question
5. Only extract passages with confidence >= {min_relevance}

⚠️ CRITICAL REQUIREMENTS:
- Extract ONLY exact text that appears VERBATIM in the abstract above
- Copy the text CHARACTER-FOR-CHARACTER, preserving punctuation and capitalization
- Do NOT paraphrase, summarize, rephrase, or modify the text in ANY way
- Do NOT combine fragments from different parts of the abstract
- Do NOT add interpretations or explanations to the extracted text
- Extract ALL relevant passages, not just one
- Extract complete sentences when possible (don't cut off mid-sentence)

Response format (JSON):
{{
    "citations": [
        {{
            "passage": "EXACT verbatim text copied character-for-character from the abstract",
            "summary": "brief summary of how this passage relates to the question",
            "confidence": 0.85,
            "stance": "SUPPORTS"
        }},
        {{
            "passage": "Another exact passage from the abstract",
            "summary": "summary of this passage",
            "confidence": 0.72,
            "stance": "CONTRADICTS"
        }}
    ],
    "has_relevant_content": true
}}

If no sufficiently relevant content is found, respond with:
{{
    "citations": [],
    "has_relevant_content": false
}}

Respond only with valid JSON."""


@dataclass
class SingleCitation:
    """A single extracted citation."""
    passage: str
    summary: str
    confidence: float
    stance: str  # "SUPPORTS", "CONTRADICTS", "NEUTRAL"
    validation_status: str  # "exact_match", "fuzzy_match", "failed"
    validation_score: float


@dataclass
class CitationResult:
    """Result of citation extraction."""
    citations: List[SingleCitation]
    has_relevant_content: bool


# Sample documents for testing
SAMPLE_DOCUMENTS = [
    {
        "title": "Aspirin for Primary Prevention of Cardiovascular Disease",
        "abstract": "Background: Low-dose aspirin has been widely used for primary prevention of cardiovascular disease. Methods: We conducted a randomized, double-blind trial involving 12,546 persons at moderate risk of cardiovascular events. Results: Aspirin use resulted in a significantly lower incidence of nonfatal myocardial infarction (4.3% vs 5.2%; hazard ratio, 0.82; 95% CI, 0.71 to 0.96; P=0.01) but showed no significant effect on death from cardiovascular causes (3.8% vs 3.7%; hazard ratio, 1.02; 95% CI, 0.88 to 1.19; P=0.77). The risk of major bleeding was higher in the aspirin group than in the placebo group (3.1% vs 2.3%; hazard ratio, 1.33; 95% CI, 1.11 to 1.60; P=0.002). Conclusions: In persons at moderate risk of cardiovascular disease, aspirin use was associated with a significantly lower risk of nonfatal myocardial infarction but also with a higher risk of major bleeding.",
        "topic": "Cardiovascular"
    },
    {
        "title": "COVID-19 mRNA Vaccine Effectiveness Against Hospitalization",
        "abstract": "Importance: Understanding the real-world effectiveness of COVID-19 vaccines is critical for public health policy. Objective: To assess the effectiveness of mRNA COVID-19 vaccines in preventing hospitalization. Design: We conducted a test-negative case-control study from March to August 2021. Participants: The study included 2,896 hospitalized adults (aged ≥18 years) with COVID-19-like illness. Results: The estimated vaccine effectiveness against COVID-19 hospitalization was 86% (95% CI, 82%-90%) for full vaccination (≥14 days after dose 2) and 43% (95% CI, 31%-53%) for partial vaccination (≥14 days after dose 1 but before dose 2). Among fully vaccinated persons, vaccine effectiveness remained stable over time, with no evidence of waning immunity during the study period. Conclusions: mRNA COVID-19 vaccines were highly effective at preventing COVID-19-associated hospitalizations among adults.",
        "topic": "Infectious Disease"
    },
    {
        "title": "Plasma Amyloid-β Biomarkers for Early Alzheimer's Disease Detection",
        "abstract": "Background: Blood-based biomarkers could enable widespread screening for Alzheimer's disease pathology. Methods: We measured plasma amyloid-β 42/40 ratio using mass spectrometry in 465 cognitively unimpaired individuals and 231 patients with mild cognitive impairment or Alzheimer's disease dementia. Results: Plasma amyloid-β 42/40 ratio showed high concordance with amyloid-PET status (area under the curve, 0.88; 95% CI, 0.85-0.91). Among cognitively unimpaired individuals, low plasma amyloid-β 42/40 ratio was associated with increased risk of progression to mild cognitive impairment (hazard ratio, 3.5; 95% CI, 2.1-5.8; P<0.001). The plasma biomarker showed comparable performance to cerebrospinal fluid amyloid-β 42/40 ratio (r=0.72, P<0.001). Conclusions: Plasma amyloid-β 42/40 ratio is a promising blood-based biomarker for detecting Alzheimer's disease pathology and predicting cognitive decline in preclinical stages.",
        "topic": "Neurology"
    },
    {
        "title": "Metformin and Cardiovascular Outcomes in Type 2 Diabetes",
        "abstract": "Background: Metformin is the first-line pharmacological treatment for type 2 diabetes, but its cardiovascular effects remain uncertain. Methods: We performed a systematic review and meta-analysis of randomized controlled trials comparing metformin with placebo or other glucose-lowering drugs. Results: Analysis of 13 trials (n=13,110) showed that metformin was associated with reduced risk of all-cause mortality (relative risk, 0.93; 95% CI, 0.88-0.99; P=0.02) and myocardial infarction (relative risk, 0.85; 95% CI, 0.76-0.94; P=0.002). There was no significant effect on stroke risk (relative risk, 0.96; 95% CI, 0.84-1.09; P=0.51). Metformin showed benefits beyond glycemic control, with improvements in lipid profiles and modest weight reduction. Conclusions: Metformin use in type 2 diabetes is associated with reduced cardiovascular mortality and myocardial infarction risk, supporting its role as first-line therapy.",
        "topic": "Diabetes"
    },
    {
        "title": "Exercise Training and Heart Failure With Preserved Ejection Fraction",
        "abstract": "Background: Exercise intolerance is a hallmark of heart failure with preserved ejection fraction (HFpEF), but optimal exercise interventions remain unclear. Methods: We randomly assigned 124 patients with HFpEF to supervised exercise training (3 sessions per week for 12 weeks) or usual care. The primary outcome was change in peak oxygen consumption (VO2). Results: Exercise training resulted in a significant increase in peak VO2 compared with usual care (mean difference, 2.5 mL/kg/min; 95% CI, 1.8-3.2; P<0.001). Quality of life scores improved in the exercise group (mean difference in Kansas City Cardiomyopathy Questionnaire, 8.3 points; 95% CI, 4.2-12.4; P<0.001). Exercise capacity improvements were sustained at 6-month follow-up. No serious adverse events occurred during supervised exercise sessions. Conclusions: Supervised exercise training improves exercise capacity and quality of life in patients with HFpEF and should be recommended as part of comprehensive management.",
        "topic": "Cardiovascular"
    }
]


class CitationAgentLab:
    """Interactive lab for experimenting with citation extraction."""

    def __init__(self):
        self.config = get_config()
        self.page: Optional[ft.Page] = None
        self.controls = {}
        self.current_prompt = DEFAULT_CITATION_PROMPT
        self.current_model = None
        self.current_temperature = 0.1
        self.current_top_p = 0.9
        self.current_min_relevance = 0.7

    def main(self, page: ft.Page):
        """Main application entry point."""
        self.page = page
        page.title = "CitationAgent Lab - BMLibrarian"
        page.window.width = 1200
        page.window.height = 900
        page.window.min_width = 1000
        page.window.min_height = 700
        page.window.resizable = True
        page.theme_mode = ft.ThemeMode.LIGHT

        # Initialize agent
        self._init_agent()

        # Create layout
        self._create_layout()

    def _init_agent(self):
        """Initialize lab settings from config (no actual agent needed - we call Ollama directly)."""
        try:
            # Get default model from config or use fallback
            default_model = self.config.get_model('citation_agent') or "medgemma4B_it_q8:latest"
            agent_config = self.config.get_agent_config('citation')

            print(f"🚀 Citation Lab initialized with default model: {default_model}")

            self.current_model = default_model
            self.current_temperature = agent_config.get('temperature', 0.1)
            self.current_top_p = agent_config.get('top_p', 0.9)
            self.current_min_relevance = agent_config.get('min_relevance', 0.7)
        except Exception as e:
            print(f"Warning: Failed to load config defaults: {e}")
            # Use hardcoded fallbacks
            self.current_model = "medgemma4B_it_q8:latest"
            self.current_temperature = 0.1
            self.current_top_p = 0.9
            self.current_min_relevance = 0.7

    def _create_layout(self):
        """Create the main application layout with tabs."""

        # Header
        header = ft.Container(
            ft.Column([
                ft.Text(
                    "CitationAgent Laboratory",
                    size=28,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.BLUE_900
                ),
                ft.Text(
                    "Experimental interface for testing citation extraction with custom prompts",
                    size=14,
                    color=ft.Colors.GREY_700
                ),
            ]),
            padding=20,
            bgcolor=ft.Colors.BLUE_50,
            border_radius=10,
        )

        # Create tabs
        tabs = ft.Tabs(
            selected_index=0,
            animation_duration=300,
            tabs=[
                ft.Tab(
                    text="Citation Extraction",
                    icon=ft.Icons.SEARCH,
                    content=self._create_extraction_tab()
                ),
                ft.Tab(
                    text="Prompt Editor",
                    icon=ft.Icons.EDIT_NOTE,
                    content=self._create_prompt_tab()
                )
            ],
            expand=True,
        )

        # Main container
        main_container = ft.Column(
            [
                header,
                ft.Divider(height=1, color=ft.Colors.GREY_300),
                tabs,
            ],
            spacing=0,
            expand=True,
        )

        self.page.add(main_container)
        self.page.update()

    def _create_extraction_tab(self) -> ft.Container:
        """Create the citation extraction tab."""

        # Left panel: Configuration
        config_panel = self._create_config_panel()

        # Right panel: Input/Output
        extraction_panel = self._create_extraction_panel()

        # Main row with both panels
        main_row = ft.Row(
            [
                config_panel,
                ft.VerticalDivider(width=1, color=ft.Colors.GREY_300),
                extraction_panel,
            ],
            spacing=0,
            expand=True,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

        return ft.Container(
            content=main_row,
            padding=10,
            expand=True,
        )

    def _create_config_panel(self) -> ft.Container:
        """Create the configuration panel (left side)."""

        # Model selection
        model_dropdown = ft.Dropdown(
            label="Ollama Model",
            hint_text="Select model",
            options=[],
            width=250,
            on_change=self._on_model_changed,
        )
        self.controls['model_dropdown'] = model_dropdown

        refresh_models_btn = ft.IconButton(
            icon=ft.Icons.REFRESH,
            tooltip="Refresh model list",
            on_click=self._refresh_models,
        )

        model_row = ft.Row(
            [model_dropdown, refresh_models_btn],
            spacing=5,
        )

        # Temperature slider
        temperature_slider = ft.Slider(
            min=0.0,
            max=1.0,
            value=self.current_temperature,
            divisions=20,
            label="{value}",
            on_change=self._on_parameter_changed,
        )
        self.controls['temperature'] = temperature_slider

        # Top-p slider
        top_p_slider = ft.Slider(
            min=0.0,
            max=1.0,
            value=self.current_top_p,
            divisions=20,
            label="{value}",
            on_change=self._on_parameter_changed,
        )
        self.controls['top_p'] = top_p_slider

        # Min relevance slider
        min_relevance_slider = ft.Slider(
            min=0.0,
            max=1.0,
            value=self.current_min_relevance,
            divisions=20,
            label="{value}",
            on_change=self._on_parameter_changed,
        )
        self.controls['min_relevance'] = min_relevance_slider

        # Agent status
        status_text = ft.Text(
            "Agent: Not initialized",
            size=12,
            color=ft.Colors.RED_700,
        )
        self.controls['status_text'] = status_text

        # Config panel content
        config_content = ft.Column(
            [
                ft.Text("Model Configuration", size=16, weight=ft.FontWeight.BOLD),
                ft.Divider(),
                model_row,
                ft.Text("Temperature", size=12),
                temperature_slider,
                ft.Text("Top-p", size=12),
                top_p_slider,
                ft.Text("Min Relevance Threshold", size=12),
                min_relevance_slider,
                ft.Divider(),
                status_text,
            ],
            spacing=10,
            scroll=ft.ScrollMode.AUTO,
            horizontal_alignment=ft.CrossAxisAlignment.START,
        )

        # Load initial model list
        self._refresh_models(None)

        return ft.Container(
            content=config_content,
            width=300,
            padding=15,
            bgcolor=ft.Colors.GREY_50,
        )

    def _create_extraction_panel(self) -> ft.Container:
        """Create the extraction panel (right side)."""

        # Research question input (single line)
        question_field = ft.TextField(
            label="Research Question",
            hint_text="Enter your research question here...",
        )
        self.controls['question'] = question_field

        # Document input (title + abstract combined)
        document_field = ft.TextField(
            label="Document (Title + Abstract)",
            hint_text="Paste document title and abstract here...",
            multiline=True,
            min_lines=15,
            max_lines=20,
        )
        self.controls['document'] = document_field

        # Sample document dropdown
        sample_options = [
            ft.dropdown.Option(key=str(i), text=f"{doc['topic']}: {doc['title'][:50]}...")
            for i, doc in enumerate(SAMPLE_DOCUMENTS)
        ]
        sample_dropdown = ft.Dropdown(
            label="Load Sample Document",
            hint_text="Select a sample...",
            options=sample_options,
            on_change=self._on_sample_selected,
        )
        self.controls['sample_dropdown'] = sample_dropdown

        # Extract button
        extract_btn = ft.ElevatedButton(
            "Extract Citation",
            icon=ft.Icons.SEARCH,
            on_click=self._extract_citation,
            style=ft.ButtonStyle(
                color=ft.Colors.WHITE,
                bgcolor=ft.Colors.GREEN_700,
            ),
        )

        # Clear button
        clear_btn = ft.OutlinedButton(
            "Clear All",
            icon=ft.Icons.CLEAR,
            on_click=self._clear_all,
        )

        button_row = ft.Row(
            [extract_btn, clear_btn],
            spacing=10,
        )

        # Results section
        results_container = ft.Container(
            content=ft.Text("Results will appear here after extraction", color=ft.Colors.GREY_500),
            padding=15,
            border=ft.border.all(1, ft.Colors.GREY_300),
            border_radius=5,
        )
        self.controls['results_container'] = results_container

        # Extraction panel content
        extraction_content = ft.Column(
            [
                question_field,
                ft.Row([sample_dropdown], spacing=10),
                document_field,
                button_row,
                ft.Divider(),
                ft.Text("Extraction Results", size=16, weight=ft.FontWeight.BOLD),
                results_container,
            ],
            spacing=10,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
            horizontal_alignment=ft.CrossAxisAlignment.START,
        )

        return ft.Container(
            content=extraction_content,
            padding=15,
            expand=True,
        )

    def _create_prompt_tab(self) -> ft.Container:
        """Create the prompt editor tab."""

        # Prompt editor
        prompt_field = ft.TextField(
            value=self.current_prompt,
            multiline=True,
            min_lines=25,
            max_lines=30,
            on_change=self._on_prompt_changed,
        )
        self.controls['prompt_field'] = prompt_field

        # Reset button
        reset_btn = ft.OutlinedButton(
            "Reset to Default",
            icon=ft.Icons.RESTORE,
            on_click=self._reset_prompt,
        )

        # Preview button
        preview_btn = ft.ElevatedButton(
            "Preview with Current Question/Document",
            icon=ft.Icons.PREVIEW,
            on_click=self._preview_prompt,
        )

        button_row = ft.Row(
            [reset_btn, preview_btn],
            spacing=10,
        )

        # Preview display
        preview_container = ft.Container(
            content=ft.Text("Preview will appear here", color=ft.Colors.GREY_500),
            padding=15,
            border=ft.border.all(1, ft.Colors.GREY_300),
            border_radius=5,
            bgcolor=ft.Colors.GREY_50,
        )
        self.controls['preview_container'] = preview_container

        # Prompt tab content
        prompt_content = ft.Column(
            [
                ft.Text("Citation Extraction Prompt Editor", size=20, weight=ft.FontWeight.BOLD),
                ft.Text(
                    "Edit the prompt template below. Use placeholders: {user_question}, {title}, {abstract}, {min_relevance}",
                    size=12,
                    color=ft.Colors.GREY_700,
                ),
                ft.Divider(),
                prompt_field,
                button_row,
                ft.Divider(),
                ft.Text("Prompt Preview", size=16, weight=ft.FontWeight.BOLD),
                preview_container,
            ],
            spacing=10,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
            horizontal_alignment=ft.CrossAxisAlignment.START,
        )

        return ft.Container(
            content=prompt_content,
            padding=20,
            expand=True,
        )

    def _refresh_models(self, e):
        """Refresh the list of available models from Ollama."""
        try:
            host = self.config.get_ollama_config()['host']
            response = requests.get(f"{host}/api/tags", timeout=5)

            if response.status_code == 200:
                data = response.json()
                models = [model['name'] for model in data.get('models', [])]

                self.controls['model_dropdown'].options = [
                    ft.dropdown.Option(text=model) for model in models
                ]

                # Set current model if available
                if self.current_model and self.current_model in models:
                    self.controls['model_dropdown'].value = self.current_model
                elif models:
                    self.controls['model_dropdown'].value = models[0]
                    self.current_model = models[0]

                self._update_status("Agent: Ready", ft.Colors.GREEN_700)
            else:
                self._show_error("Failed to fetch models from Ollama")
                self._update_status("Agent: Connection failed", ft.Colors.RED_700)
        except Exception as e:
            print(f"Error fetching models: {e}")
            self._show_error(f"Could not connect to Ollama: {e}")
            self._update_status("Agent: Offline", ft.Colors.RED_700)

            # Fallback to common models
            fallback_models = ["medgemma4B_it_q8:latest", "gpt-oss:20b"]
            self.controls['model_dropdown'].options = [
                ft.dropdown.Option(text=model) for model in fallback_models
            ]

        self.page.update()

    def _on_model_changed(self, e):
        """Handle model selection change."""
        self.current_model = e.control.value
        self._update_status("Agent: Model changed", ft.Colors.ORANGE_700)
        self.page.update()

    def _on_parameter_changed(self, e):
        """Handle parameter slider changes."""
        self.current_temperature = self.controls['temperature'].value
        self.current_top_p = self.controls['top_p'].value
        self.current_min_relevance = self.controls['min_relevance'].value
        self.page.update()

    def _on_prompt_changed(self, e):
        """Handle prompt text changes."""
        self.current_prompt = e.control.value

    def _on_sample_selected(self, e):
        """Handle sample document selection."""
        if e.control.value:
            idx = int(e.control.value)
            doc = SAMPLE_DOCUMENTS[idx]

            # Combine title and abstract
            combined_text = f"{doc['title']}\n\n{doc['abstract']}"
            self.controls['document'].value = combined_text

            # Set a default question for the sample
            sample_questions = {
                "Cardiovascular": "What are the benefits and risks of aspirin for cardiovascular disease prevention?",
                "Infectious Disease": "How effective are COVID-19 mRNA vaccines at preventing hospitalization?",
                "Neurology": "Can blood tests detect Alzheimer's disease pathology?",
                "Diabetes": "Does metformin reduce cardiovascular risk in type 2 diabetes?",
            }

            self.controls['question'].value = sample_questions.get(
                doc['topic'],
                "What are the main findings of this study?"
            )

            self.page.update()

    def _extract_json_from_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        """Extract JSON from LLM response, handling common malformations."""
        # Try direct JSON parse first
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            pass

        # Try to find JSON block in response (sometimes LLMs add text before/after)
        # Look for content between first { and last }
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        # Try to find JSON array pattern
        json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(0))
                # Wrap in expected format if it's a raw array
                if isinstance(data, list):
                    return {"citations": data, "has_relevant_content": len(data) > 0}
            except json.JSONDecodeError:
                pass

        return None

    def _call_ollama_with_retry(self, prompt: str, max_retries: int = 3) -> Optional[str]:
        """Call Ollama with retry logic for robustness."""
        host = self.config.get_ollama_config()['host']

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    # Exponential backoff: 1s, 2s, 4s
                    wait_time = 2 ** (attempt - 1)
                    self._update_status(f"Agent: Retry {attempt}/{max_retries} (waiting {wait_time}s)...", ft.Colors.ORANGE_700)
                    if self.page:
                        self.page.update()
                    time.sleep(wait_time)

                response = requests.post(
                    f"{host}/api/generate",
                    json={
                        "model": self.current_model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": self.current_temperature,
                            "top_p": self.current_top_p,
                        }
                    },
                    timeout=60
                )

                if response.status_code == 200:
                    result = response.json()
                    return result.get('response', '')
                else:
                    if attempt == max_retries - 1:
                        self._show_error(f"Ollama request failed: {response.status_code}")
                        return None
            except requests.exceptions.RequestException as e:
                if attempt == max_retries - 1:
                    self._show_error(f"Network error: {e}")
                    return None

        return None

    def _extract_citation(self, e):
        """Extract citation using custom prompt with retry logic."""
        question = self.controls['question'].value
        document_text = self.controls['document'].value

        if not question or not document_text:
            self._show_error("Please provide research question and document text")
            return

        # Parse document into title and abstract
        # Assume first line is title, rest is abstract
        lines = document_text.strip().split('\n')
        title = lines[0] if lines else ""
        abstract = '\n'.join(lines[1:]).strip() if len(lines) > 1 else document_text

        if not self.current_model:
            self._show_error("Please select a model")
            return

        self._update_status("Agent: Extracting citations...", ft.Colors.BLUE_700)
        self.page.update()

        try:
            # Format prompt with current values
            formatted_prompt = self.current_prompt.format(
                user_question=question,
                title=title,
                abstract=abstract,
                min_relevance=self.current_min_relevance
            )

            # Call Ollama with retry logic
            llm_response = self._call_ollama_with_retry(formatted_prompt, max_retries=3)

            if llm_response is None:
                self._update_status("Agent: Request failed", ft.Colors.RED_700)
                return

            # Extract JSON from response with multiple strategies
            citation_data = self._extract_json_from_response(llm_response)

            if citation_data is None:
                self._show_error(f"Failed to parse JSON response after multiple attempts.\n\nResponse: {llm_response[:500]}")
                self._update_status("Agent: Parse error", ft.Colors.RED_700)
                return

            # Process multiple citations
            citations_list = []
            raw_citations = citation_data.get('citations', [])

            for cit in raw_citations:
                # Validate extracted passage
                validation_result = self._validate_extracted_passage(
                    cit.get('passage', ''),
                    abstract
                )

                citations_list.append(SingleCitation(
                    passage=cit.get('passage', ''),
                    summary=cit.get('summary', ''),
                    confidence=cit.get('confidence', 0.0),
                    stance=cit.get('stance', 'NEUTRAL'),
                    validation_status=validation_result['status'],
                    validation_score=validation_result['score']
                ))

            # Create citation result
            citation_result = CitationResult(
                citations=citations_list,
                has_relevant_content=citation_data.get('has_relevant_content', False)
            )

            # Display results
            self._display_citation_results(citation_result)
            self._update_status("Agent: Extraction complete", ft.Colors.GREEN_700)

        except Exception as e:
            self._show_error(f"Extraction failed: {e}")
            self._update_status("Agent: Error", ft.Colors.RED_700)

        self.page.update()

    def _validate_extracted_passage(self, passage: str, abstract: str) -> Dict[str, Any]:
        """Validate that extracted passage exists in abstract."""
        if not passage:
            return {"status": "no_content", "score": 0.0}

        # Check for exact match
        if passage in abstract:
            return {"status": "exact_match", "score": 1.0}

        # Fuzzy matching
        matcher = SequenceMatcher(None, passage.lower(), abstract.lower())
        ratio = matcher.ratio()

        if ratio >= 0.95:
            return {"status": "fuzzy_match", "score": ratio}
        else:
            return {"status": "failed", "score": ratio}

    def _display_citation_results(self, result: CitationResult):
        """Display citation extraction results with multiple citations."""

        # Status colors and icons
        status_colors = {
            "exact_match": ft.Colors.GREEN_700,
            "fuzzy_match": ft.Colors.ORANGE_700,
            "failed": ft.Colors.RED_700,
        }

        status_icons = {
            "exact_match": ft.Icons.CHECK_CIRCLE,
            "fuzzy_match": ft.Icons.WARNING,
            "failed": ft.Icons.ERROR,
        }

        # Stance colors
        stance_colors = {
            "SUPPORTS": ft.Colors.GREEN_700,
            "CONTRADICTS": ft.Colors.RED_700,
            "NEUTRAL": ft.Colors.GREY_700,
        }

        if not result.has_relevant_content or not result.citations:
            results_content = ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.INFO, color=ft.Colors.GREY_700),
                    ft.Text("No relevant citations found", size=16, weight=ft.FontWeight.BOLD),
                ]),
            ], spacing=10)
        else:
            # Build citation cards
            citation_cards = []

            for i, citation in enumerate(result.citations, 1):
                # Confidence color
                if citation.confidence >= 0.8:
                    conf_color = ft.Colors.GREEN_700
                elif citation.confidence >= 0.6:
                    conf_color = ft.Colors.ORANGE_700
                else:
                    conf_color = ft.Colors.RED_700

                # Build single citation card
                card = ft.Container(
                    content=ft.Column([
                        # Header with citation number, confidence, stance
                        ft.Row([
                            ft.Text(f"Citation {i}", size=16, weight=ft.FontWeight.BOLD),
                            ft.Container(
                                content=ft.Text(
                                    f"{citation.confidence:.0%}",
                                    size=14,
                                    weight=ft.FontWeight.BOLD,
                                    color=ft.Colors.WHITE
                                ),
                                bgcolor=conf_color,
                                padding=ft.padding.symmetric(horizontal=8, vertical=4),
                                border_radius=5,
                            ),
                            ft.Container(
                                content=ft.Text(
                                    citation.stance,
                                    size=14,
                                    weight=ft.FontWeight.BOLD,
                                    color=ft.Colors.WHITE
                                ),
                                bgcolor=stance_colors.get(citation.stance, ft.Colors.GREY_700),
                                padding=ft.padding.symmetric(horizontal=8, vertical=4),
                                border_radius=5,
                            ),
                            ft.Icon(
                                status_icons[citation.validation_status],
                                color=status_colors[citation.validation_status],
                                size=20,
                                tooltip=f"Validation: {citation.validation_status} ({citation.validation_score:.2%})"
                            ),
                        ], spacing=10),

                        # Extracted passage
                        ft.Text("Passage:", size=12, weight=ft.FontWeight.BOLD),
                        ft.Container(
                            content=ft.Text(citation.passage, size=12, selectable=True),
                            padding=10,
                            bgcolor=ft.Colors.YELLOW_50,
                            border=ft.border.all(1, ft.Colors.YELLOW_700),
                            border_radius=5,
                        ),

                        # Summary
                        ft.Text("Summary:", size=12, weight=ft.FontWeight.BOLD),
                        ft.Text(citation.summary, size=12, color=ft.Colors.GREY_700),
                    ], spacing=8),
                    padding=15,
                    border=ft.border.all(2, ft.Colors.BLUE_200),
                    border_radius=10,
                    bgcolor=ft.Colors.WHITE,
                )

                citation_cards.append(card)

            # Summary header
            summary_header = ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.LIBRARY_BOOKS, color=ft.Colors.BLUE_700),
                    ft.Text(
                        f"Found {len(result.citations)} citation(s)",
                        size=18,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.BLUE_700
                    ),
                ]),
                padding=10,
                bgcolor=ft.Colors.BLUE_50,
                border_radius=5,
            )

            # Combine all elements
            results_content = ft.Column([
                summary_header,
                *citation_cards,
            ], spacing=15)

        self.controls['results_container'].content = results_content
        self.page.update()

    def _clear_all(self, e):
        """Clear all input and output fields."""
        self.controls['question'].value = ""
        self.controls['document'].value = ""
        self.controls['sample_dropdown'].value = None
        self.controls['results_container'].content = ft.Text(
            "Results will appear here after extraction",
            color=ft.Colors.GREY_500
        )
        self.page.update()

    def _reset_prompt(self, e):
        """Reset prompt to default."""
        self.current_prompt = DEFAULT_CITATION_PROMPT
        self.controls['prompt_field'].value = DEFAULT_CITATION_PROMPT
        self.controls['preview_container'].content = ft.Text(
            "Preview will appear here",
            color=ft.Colors.GREY_500
        )
        self.page.update()

    def _preview_prompt(self, e):
        """Preview prompt with current question/document."""
        question = self.controls['question'].value or "[Enter research question]"
        document_text = self.controls['document'].value or "[Enter document text]"

        # Parse document into title and abstract
        lines = document_text.strip().split('\n')
        title = lines[0] if lines else "[Title]"
        abstract = '\n'.join(lines[1:]).strip() if len(lines) > 1 else document_text

        try:
            formatted_prompt = self.current_prompt.format(
                user_question=question,
                title=title,
                abstract=abstract,
                min_relevance=self.current_min_relevance
            )

            preview_content = ft.Column([
                ft.Text(formatted_prompt, size=12, font_family="monospace", selectable=True),
            ], scroll=ft.ScrollMode.AUTO)

            self.controls['preview_container'].content = preview_content
        except Exception as e:
            self.controls['preview_container'].content = ft.Text(
                f"Error formatting prompt: {e}",
                color=ft.Colors.RED_700
            )

        self.page.update()

    def _update_status(self, message: str, color):
        """Update agent status text."""
        if 'status_text' in self.controls:
            self.controls['status_text'].value = message
            self.controls['status_text'].color = color

    def _show_error(self, message: str):
        """Show error dialog."""
        def close_dlg(e):
            dlg.open = False
            self.page.update()

        dlg = ft.AlertDialog(
            title=ft.Text("Error"),
            content=ft.Text(message),
            actions=[
                ft.TextButton("OK", on_click=close_dlg),
            ],
        )

        self.page.dialog = dlg
        dlg.open = True
        self.page.update()


def run_citation_lab():
    """Run the CitationAgent Lab application."""
    app = CitationAgentLab()
    ft.app(target=app.main)


if __name__ == "__main__":
    run_citation_lab()
