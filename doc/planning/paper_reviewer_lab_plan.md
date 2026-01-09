# Paper Reviewer Lab - Implementation Plan

**Version:** 1.0.0
**Author:** Claude Code
**Date:** 2025-01-09
**Status:** Planning

## Overview

The Paper Reviewer Lab is a comprehensive paper assessment tool that combines multiple existing agents to provide thorough analysis of research papers. It can function both as a standalone mini-app and as a plugin tab in the main BMLibrarian GUI.

## Requirements Summary

### Input Methods
- **DOI**: Fetch from local database first, then CrossRef/DOI.org
- **PMID**: Fetch from local database first, then PubMed API
- **PDF file**: Process using existing `pdf_processor` for section segmentation
- **Text input**: Accept pasted text (abstract or full text), markdown files, plain text files

### Output Components
1. **Brief Summary**: 2-3 sentence summary of the paper
2. **Core Statement/Hypothesis**: Central claim or research question
3. **PICO Analysis**: Where applicable (auto-detected for clinical studies)
4. **PRISMA Assessment**: Where applicable (auto-detected for systematic reviews)
5. **Study Weight Assessment**: Combined PaperWeightAssessmentAgent + StudyAssessmentAgent
6. **Strengths & Weaknesses Summary**: Synthesized from all assessments
7. **Contradictory Literature Search**: Local + external search using counter-statement query

### UI/UX
- Single-pass automated execution
- Real-time step-by-step feedback during processing
- Export options: Markdown, PDF, JSON

### Integration
- Standalone entry point: `scripts/paper_reviewer_lab.py`
- Plugin tab in GUI: `src/bmlibrarian/gui/qt/plugins/paper_reviewer_lab/`
- Lab module: `src/bmlibrarian/lab/paper_reviewer_lab/`

---

## Architecture

### Component Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Paper Reviewer Lab (GUI/CLI)                      │
├─────────────────────────────────────────────────────────────────────┤
│  Input Layer                                                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐               │
│  │   DOI    │ │   PMID   │ │   PDF    │ │   Text   │               │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘               │
│       └──────┬─────┴─────┬─────┴──────┬─────┘                       │
│              ▼           ▼            ▼                             │
│         ┌─────────────────────────────────┐                         │
│         │     DocumentResolver            │                         │
│         │  (local DB → web fetch)         │                         │
│         └────────────┬────────────────────┘                         │
├──────────────────────┼──────────────────────────────────────────────┤
│  Processing Layer    ▼                                              │
│         ┌─────────────────────────────────┐                         │
│         │   PaperReviewerAgent            │                         │
│         │   (orchestrates all sub-agents) │                         │
│         └────────────┬────────────────────┘                         │
│                      │                                              │
│    ┌────────┬────────┼────────┬────────┬────────┐                  │
│    ▼        ▼        ▼        ▼        ▼        ▼                  │
│ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────────┐         │
│ │Summa-│ │Hypo- │ │PICO  │ │PRISMA│ │Study │ │Paper     │         │
│ │rizer │ │thesis│ │Agent │ │Agent │ │Assess│ │Weight    │         │
│ └──────┘ └──────┘ └──────┘ └──────┘ └──────┘ └──────────┘         │
│                                                                     │
│         ┌─────────────────────────────────┐                         │
│         │   ContradictoryEvidenceFinder   │                         │
│         │   (semantic + HyDE + keyword)   │                         │
│         └─────────────────────────────────┘                         │
├─────────────────────────────────────────────────────────────────────┤
│  Output Layer                                                        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                            │
│  │ Markdown │ │   PDF    │ │   JSON   │                            │
│  └──────────┘ └──────────┘ └──────────┘                            │
└─────────────────────────────────────────────────────────────────────┘
```

### Data Flow

```
Input (DOI/PMID/PDF/Text)
    │
    ▼
DocumentResolver: Resolve to document dict with text
    │
    ▼
Step 1: Summary Generator → 2-3 sentence summary
    │
    ▼
Step 2: Hypothesis Extractor → core statement/hypothesis
    │
    ▼
Step 3: Study Type Detector → classify study type
    │
    ├─ If clinical/intervention study:
    │      ▼
    │  Step 4a: PICOAgent → PICO extraction
    │
    ├─ If systematic review/meta-analysis:
    │      ▼
    │  Step 4b: PRISMA2020Agent → PRISMA assessment
    │
    ▼
Step 5: PaperWeightAssessmentAgent → multi-dimensional weight
    │
    ▼
Step 6: StudyAssessmentAgent → quality assessment
    │
    ▼
Step 7: Synthesize Strengths/Weaknesses from all assessments
    │
    ▼
Step 8: Generate Counter-Statement from hypothesis
    │
    ▼
Step 9: Search local DB (semantic + HyDE + keyword)
    │
    ├─ If results insufficient and external search enabled:
    │      ▼
    │  Step 9b: Search PubMed API
    │
    ▼
Step 10: Cross-rerank results with counter-statement relevance
    │
    ▼
Step 11: Compile Final Report
    │
    ▼
Export (Markdown / PDF / JSON)
```

---

## Implementation Steps

### Phase 1: Core Agent (`PaperReviewerAgent`)

**Location:** `src/bmlibrarian/agents/paper_reviewer/`

#### Step 1.1: Create Data Models
**File:** `src/bmlibrarian/agents/paper_reviewer/models.py`

```python
@dataclass
class PaperReviewResult:
    """Complete paper review result."""

    # Input metadata
    document_id: Optional[int]
    doi: Optional[str]
    pmid: Optional[str]
    title: str
    authors: List[str]
    year: Optional[int]
    source_type: str  # "database", "pdf", "text", "doi_fetch", "pmid_fetch"

    # Summary
    brief_summary: str  # 2-3 sentences

    # Core statement
    core_hypothesis: str
    hypothesis_confidence: float

    # Study type detection
    study_type: str
    is_clinical_study: bool
    is_systematic_review: bool
    is_meta_analysis: bool

    # PICO (if applicable)
    pico_extraction: Optional[PICOExtraction]
    pico_applicable: bool

    # PRISMA (if applicable)
    prisma_assessment: Optional[PRISMA2020Assessment]
    prisma_applicable: bool

    # Paper Weight Assessment
    paper_weight: PaperWeightResult

    # Study Assessment
    study_assessment: StudyAssessment

    # Synthesized strengths/weaknesses
    strengths_summary: List[str]
    weaknesses_summary: List[str]

    # Contradictory evidence
    counter_statement: str
    contradictory_papers: List[ContradictoryPaper]
    search_sources: List[str]  # "local_semantic", "local_hyde", "local_keyword", "pubmed"

    # Metadata
    reviewed_at: datetime
    reviewer_version: str
    total_processing_time_seconds: float


@dataclass
class ContradictoryPaper:
    """Paper potentially contradicting the reviewed paper's hypothesis."""

    document_id: Optional[int]
    pmid: Optional[str]
    doi: Optional[str]
    title: str
    authors: List[str]
    year: Optional[int]
    abstract: str
    relevance_score: float  # 0-1, how relevant to counter-statement
    search_method: str  # "semantic", "hyde", "keyword", "pubmed"
    source: str  # "local", "external"
    contradictory_excerpt: Optional[str]  # Key text that contradicts
```

#### Step 1.2: Create Document Resolver
**File:** `src/bmlibrarian/agents/paper_reviewer/resolver.py`

```python
class DocumentResolver:
    """
    Resolves paper identifiers (DOI, PMID, PDF, text) to document dicts.

    Resolution priority:
    1. Local database (fastest)
    2. Web fetch (DOI.org, PubMed API, CrossRef)
    """

    def resolve_doi(self, doi: str) -> Dict[str, Any]:
        """Resolve DOI to document dict."""
        # 1. Check local database
        # 2. Fetch from CrossRef/DOI.org
        # 3. Return document dict with abstract, title, etc.

    def resolve_pmid(self, pmid: str) -> Dict[str, Any]:
        """Resolve PMID to document dict."""
        # 1. Check local database
        # 2. Fetch from PubMed E-utilities API
        # 3. Return document dict

    def resolve_pdf(self, pdf_path: Path) -> Dict[str, Any]:
        """Extract document from PDF using pdf_processor."""
        # 1. Use PDFExtractor for text extraction
        # 2. Use PDFSegmenter for section identification
        # 3. Extract metadata (DOI, title from first page)
        # 4. Optionally match to database record

    def resolve_text(self, text: str, file_path: Optional[Path] = None) -> Dict[str, Any]:
        """Process raw text or file."""
        # 1. Detect if markdown (parse front matter for metadata)
        # 2. Extract abstract-like summary if full text
        # 3. Return document dict
```

#### Step 1.3: Create Summary Generator
**File:** `src/bmlibrarian/agents/paper_reviewer/summarizer.py`

```python
class SummaryGenerator(BaseAgent):
    """Generates brief 2-3 sentence summaries of papers."""

    def generate_summary(self, document: Dict[str, Any]) -> str:
        """
        Generate a concise 2-3 sentence summary.

        Focus on:
        - What type of study
        - Main population/intervention/focus
        - Key finding or conclusion
        """

    def extract_hypothesis(self, document: Dict[str, Any]) -> Tuple[str, float]:
        """
        Extract the core statement/hypothesis.

        Returns:
            Tuple of (hypothesis_text, confidence_score)
        """
```

#### Step 1.4: Create Study Type Detector
**File:** `src/bmlibrarian/agents/paper_reviewer/study_detector.py`

```python
class StudyTypeDetector:
    """
    Detects study type to determine PICO/PRISMA applicability.

    Combines rule-based detection with LLM confirmation.
    """

    def detect_study_type(self, document: Dict[str, Any]) -> StudyTypeResult:
        """
        Detect study type and applicable assessments.

        Returns:
            StudyTypeResult with:
            - study_type: str
            - is_clinical_study: bool (→ PICO applicable)
            - is_systematic_review: bool (→ PRISMA applicable)
            - is_meta_analysis: bool (→ PRISMA applicable)
            - confidence: float
        """
```

#### Step 1.5: Create Contradictory Evidence Finder
**File:** `src/bmlibrarian/agents/paper_reviewer/contradictory_finder.py`

```python
class ContradictoryEvidenceFinder:
    """
    Finds literature that questions or negates the paper's hypothesis.

    Search strategy:
    1. Generate counter-statement from hypothesis (semantic negation)
    2. Generate HyDE abstract for counter-position
    3. Extract keywords from counter-statement
    4. Search local database:
       - Semantic search with counter-statement embedding
       - HyDE search with hypothetical abstract
       - Keyword search with extracted terms
    5. Optionally search PubMed API
    6. Cross-rerank all results by relevance to counter-statement
    """

    def generate_counter_statement(self, hypothesis: str) -> str:
        """Generate semantic negation of the hypothesis."""

    def generate_hyde_abstract(self, counter_statement: str) -> str:
        """Generate hypothetical abstract supporting counter-position."""

    def search_local(self, counter_statement: str, hyde_abstract: str) -> List[ContradictoryPaper]:
        """Search local database using multiple strategies."""

    def search_pubmed(self, counter_statement: str, keywords: List[str]) -> List[ContradictoryPaper]:
        """Search PubMed API for external papers."""

    def cross_rerank(self, papers: List[ContradictoryPaper], counter_statement: str) -> List[ContradictoryPaper]:
        """Rerank all results by relevance to counter-statement."""
```

#### Step 1.6: Create Main Agent
**File:** `src/bmlibrarian/agents/paper_reviewer/agent.py`

```python
class PaperReviewerAgent(BaseAgent):
    """
    Orchestrates comprehensive paper review using multiple sub-agents.

    Workflow:
    1. Resolve input to document
    2. Generate summary
    3. Extract hypothesis
    4. Detect study type
    5. Run PICO (if applicable)
    6. Run PRISMA (if applicable)
    7. Run PaperWeightAssessment
    8. Run StudyAssessment
    9. Synthesize strengths/weaknesses
    10. Find contradictory evidence
    11. Compile final report
    """

    VERSION = "1.0.0"

    def __init__(self, ...):
        # Initialize all sub-agents
        self.resolver = DocumentResolver()
        self.summarizer = SummaryGenerator(...)
        self.study_detector = StudyTypeDetector(...)
        self.pico_agent = PICOAgent(...)
        self.prisma_agent = PRISMA2020Agent(...)
        self.paper_weight_agent = PaperWeightAssessmentAgent(...)
        self.study_assessment_agent = StudyAssessmentAgent(...)
        self.contradictory_finder = ContradictoryEvidenceFinder(...)

    def review_paper(
        self,
        doi: Optional[str] = None,
        pmid: Optional[str] = None,
        pdf_path: Optional[Path] = None,
        text: Optional[str] = None,
        text_file: Optional[Path] = None,
        search_external: bool = True,
        progress_callback: Optional[Callable[[str, float], None]] = None,
        data_callback: Optional[Callable[[str, Dict], None]] = None,
    ) -> PaperReviewResult:
        """
        Perform comprehensive paper review.

        Exactly one of doi, pmid, pdf_path, text, or text_file must be provided.

        Args:
            doi: DOI to look up
            pmid: PubMed ID to look up
            pdf_path: Path to PDF file
            text: Raw text content (abstract or full text)
            text_file: Path to text/markdown file
            search_external: Whether to search PubMed for contradictory evidence
            progress_callback: (step_name, progress_fraction) for UI updates
            data_callback: (step_name, data_dict) for intermediate results

        Returns:
            Complete PaperReviewResult with all assessments
        """
```

### Phase 2: GUI Lab Module

**Location:** `src/bmlibrarian/lab/paper_reviewer_lab/`

#### Step 2.1: Create Module Structure
```
paper_reviewer_lab/
├── __init__.py           # Module exports and main() entry point
├── constants.py          # UI constants, step names, dimensions
├── utils.py             # Helper functions
├── main_window.py       # Main QMainWindow
├── worker.py            # QThread workers for background processing
├── tabs/
│   ├── __init__.py
│   ├── input_tab.py     # DOI/PMID/text input
│   ├── pdf_tab.py       # PDF upload and preview
│   ├── workflow_tab.py  # Step-by-step progress visualization
│   └── results_tab.py   # Final report display with export
└── widgets/
    ├── __init__.py
    ├── step_card.py     # Collapsible step result card
    ├── assessment_card.py # PICO/PRISMA/Weight display
    └── literature_card.py # Contradictory paper display
```

#### Step 2.2: Define Constants
**File:** `src/bmlibrarian/lab/paper_reviewer_lab/constants.py`

```python
# Window dimensions
WINDOW_MIN_WIDTH = 1000
WINDOW_MIN_HEIGHT = 700
WINDOW_DEFAULT_WIDTH = 1200
WINDOW_DEFAULT_HEIGHT = 800

# Tab indices
TAB_INPUT = 0
TAB_PDF = 1
TAB_WORKFLOW = 2
TAB_RESULTS = 3

# Workflow steps (11 total)
STEPS = [
    ("resolve_input", "Resolving Input"),
    ("generate_summary", "Generating Summary"),
    ("extract_hypothesis", "Extracting Hypothesis"),
    ("detect_study_type", "Detecting Study Type"),
    ("pico_assessment", "PICO Analysis"),
    ("prisma_assessment", "PRISMA Assessment"),
    ("paper_weight", "Paper Weight Assessment"),
    ("study_assessment", "Study Quality Assessment"),
    ("synthesize_strengths", "Synthesizing Strengths/Weaknesses"),
    ("search_contradictory", "Searching for Contradictory Evidence"),
    ("compile_report", "Compiling Final Report"),
]

# Step durations (estimated, for progress bar)
STEP_WEIGHTS = {
    "resolve_input": 0.05,
    "generate_summary": 0.10,
    "extract_hypothesis": 0.08,
    "detect_study_type": 0.05,
    "pico_assessment": 0.12,
    "prisma_assessment": 0.12,
    "paper_weight": 0.15,
    "study_assessment": 0.12,
    "synthesize_strengths": 0.05,
    "search_contradictory": 0.12,
    "compile_report": 0.04,
}
```

#### Step 2.3: Create Input Tab
**File:** `src/bmlibrarian/lab/paper_reviewer_lab/tabs/input_tab.py`

```python
class InputTab(QWidget):
    """
    Tab for DOI/PMID/text input.

    Features:
    - Text field for DOI input with validation
    - Text field for PMID input with validation
    - Large text area for pasted abstract/full text
    - Model selection dropdown
    - "Search external" checkbox
    - "Review Paper" button
    """

    # Signals
    review_requested = Signal(dict)  # Emits input dict
```

#### Step 2.4: Create PDF Tab
**File:** `src/bmlibrarian/lab/paper_reviewer_lab/tabs/pdf_tab.py`

```python
class PDFTab(QWidget):
    """
    Tab for PDF file upload.

    Features:
    - Drag-and-drop zone for PDF
    - File browser button
    - PDF preview (first page thumbnail)
    - Extracted metadata display (DOI if found)
    - "Review Paper" button
    """

    # Signals
    review_requested = Signal(Path)  # Emits PDF path
```

#### Step 2.5: Create Workflow Tab
**File:** `src/bmlibrarian/lab/paper_reviewer_lab/tabs/workflow_tab.py`

```python
class WorkflowTab(QWidget):
    """
    Step-by-step workflow visualization.

    Features:
    - Vertical list of step cards (collapsible)
    - Each card shows: step name, status, progress, results preview
    - Overall progress bar at top
    - Abort button
    - Steps expand to show intermediate results as they complete
    """

    def update_step(self, step_name: str, status: str, data: Optional[Dict] = None):
        """Update a step's status and optionally show results."""

    def reset(self):
        """Reset all steps to pending state."""
```

#### Step 2.6: Create Results Tab
**File:** `src/bmlibrarian/lab/paper_reviewer_lab/tabs/results_tab.py`

```python
class ResultsTab(QWidget):
    """
    Final report display with export options.

    Features:
    - Tabbed view of all assessment components
    - Sub-tabs: Summary, PICO, PRISMA, Weight, Quality, Literature
    - Export buttons: Markdown, PDF, JSON
    - Copy to clipboard button
    """

    def display_result(self, result: PaperReviewResult):
        """Display the complete review result."""

    def export_markdown(self, path: Path):
        """Export to markdown file."""

    def export_pdf(self, path: Path):
        """Export to PDF using PDFExporter."""

    def export_json(self, path: Path):
        """Export to JSON file."""
```

#### Step 2.7: Create Worker Thread
**File:** `src/bmlibrarian/lab/paper_reviewer_lab/worker.py`

```python
class PaperReviewWorker(QThread):
    """
    Background worker for paper review.

    Signals:
        progress_update: (step_name, progress_fraction)
        step_complete: (step_name, data_dict)
        review_complete: (PaperReviewResult)
        review_error: (error_message)
    """

    progress_update = Signal(str, float)
    step_complete = Signal(str, dict)
    review_complete = Signal(object)
    review_error = Signal(str)

    def __init__(self, agent: PaperReviewerAgent, input_dict: Dict[str, Any]):
        ...

    def run(self):
        """Execute the review in background thread."""
```

#### Step 2.8: Create Main Window
**File:** `src/bmlibrarian/lab/paper_reviewer_lab/main_window.py`

```python
class PaperReviewerLab(QMainWindow):
    """
    Main window for Paper Reviewer Laboratory.

    Coordinates the tabbed interface for input, workflow visualization,
    and results display.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Paper Reviewer Lab - Comprehensive Paper Assessment")
        # ... setup UI, tabs, signals

    def _start_review(self, input_dict: Dict[str, Any]):
        """Start paper review from input."""

    def _on_step_complete(self, step_name: str, data: Dict):
        """Handle step completion."""

    def _on_review_complete(self, result: PaperReviewResult):
        """Handle review completion."""
```

### Phase 3: GUI Plugin Tab

**Location:** `src/bmlibrarian/gui/qt/plugins/paper_reviewer_lab/`

#### Step 3.1: Create Plugin
**File:** `src/bmlibrarian/gui/qt/plugins/paper_reviewer_lab/plugin.py`

```python
class PaperReviewerLabPlugin(LabPluginBase):
    """
    Paper Reviewer Lab plugin for main GUI.

    Embeds the lab functionality as a tab in the main application.
    """

    NAME = "Paper Reviewer"
    ICON = "paper_review"
    DESCRIPTION = "Comprehensive paper quality assessment"

    def create_widget(self, parent: QWidget) -> QWidget:
        """Create the plugin widget."""
        return PaperReviewerLabWidget(parent)
```

### Phase 4: CLI Entry Point

**File:** `scripts/paper_reviewer_lab.py`

```python
#!/usr/bin/env python3
"""
Paper Reviewer Laboratory - Comprehensive paper quality assessment.

Usage:
    uv run python paper_reviewer_lab.py
    uv run python paper_reviewer_lab.py --debug
"""

import argparse
from bmlibrarian.lab.paper_reviewer_lab import main

if __name__ == "__main__":
    main()
```

### Phase 5: Documentation

#### Step 5.1: User Guide
**File:** `doc/users/paper_reviewer_guide.md`

Contents:
- Quick start
- Input methods (DOI, PMID, PDF, text)
- Understanding the assessment components
- Interpreting results
- Export options
- Troubleshooting

#### Step 5.2: Developer Guide
**File:** `doc/developers/paper_reviewer_system.md`

Contents:
- Architecture overview
- Agent orchestration
- Adding new assessment components
- Extending the search functionality
- Testing strategies

---

## Implementation Order

### Sprint 1: Core Agent (3-4 days)
1. [ ] Create `src/bmlibrarian/agents/paper_reviewer/` directory structure
2. [ ] Implement `models.py` with all dataclasses
3. [ ] Implement `resolver.py` (DocumentResolver)
4. [ ] Implement `summarizer.py` (SummaryGenerator)
5. [ ] Implement `study_detector.py` (StudyTypeDetector)
6. [ ] Implement `contradictory_finder.py` (ContradictoryEvidenceFinder)
7. [ ] Implement `agent.py` (PaperReviewerAgent orchestrator)
8. [ ] Write unit tests for all components

### Sprint 2: GUI Lab Module (3-4 days)
1. [ ] Create `src/bmlibrarian/lab/paper_reviewer_lab/` directory structure
2. [ ] Implement `constants.py` and `utils.py`
3. [ ] Implement `tabs/input_tab.py`
4. [ ] Implement `tabs/pdf_tab.py`
5. [ ] Implement `tabs/workflow_tab.py` with step cards
6. [ ] Implement `tabs/results_tab.py` with export
7. [ ] Implement `worker.py`
8. [ ] Implement `main_window.py`
9. [ ] Create `__init__.py` with main() entry point

### Sprint 3: Integration & Polish (2-3 days)
1. [ ] Create `scripts/paper_reviewer_lab.py` entry point
2. [ ] Create GUI plugin at `src/bmlibrarian/gui/qt/plugins/paper_reviewer_lab/`
3. [ ] Add to agents `__init__.py` exports
4. [ ] Write integration tests
5. [ ] Write user documentation
6. [ ] Write developer documentation
7. [ ] Update CLAUDE.md with new commands

---

## Testing Strategy

### Unit Tests
- `tests/agents/paper_reviewer/test_models.py`
- `tests/agents/paper_reviewer/test_resolver.py`
- `tests/agents/paper_reviewer/test_summarizer.py`
- `tests/agents/paper_reviewer/test_study_detector.py`
- `tests/agents/paper_reviewer/test_contradictory_finder.py`
- `tests/agents/paper_reviewer/test_agent.py`

### Integration Tests
- `tests/agents/paper_reviewer/test_end_to_end.py`
- Test with sample DOIs, PMIDs, PDFs, text inputs

### Manual Testing
- Run `paper_reviewer_lab.py` with various inputs
- Test all export formats
- Test external search toggle
- Test cancellation during processing

---

## Dependencies

### Existing Dependencies (already in project)
- `PySide6` - GUI framework
- `ollama` - LLM communication
- `psycopg` - Database access
- `reportlab` - PDF export

### Existing Agents to Reuse
- `PICOAgent` - PICO extraction
- `PRISMA2020Agent` - PRISMA assessment
- `PaperWeightAssessmentAgent` - Multi-dimensional weight
- `StudyAssessmentAgent` - Quality assessment
- `QueryAgent` - Search query generation (for keyword extraction)

### Existing Utilities to Reuse
- `pdf_processor` - PDF text extraction and segmentation
- `PDFExporter` - PDF report generation
- `get_font_scale()`, `get_stylesheet_generator()` - DPI scaling and styling
- `DatabaseManager` - Database access

---

## Configuration

Add to `~/.bmlibrarian/config.json`:

```json
{
  "paper_reviewer": {
    "model": "gpt-oss:20b",
    "temperature": 0.1,
    "search_external_by_default": true,
    "max_contradictory_papers": 10,
    "search_strategies": ["semantic", "hyde", "keyword"],
    "cross_rerank_model": "gpt-oss:20b"
  }
}
```

---

## Open Questions / Future Enhancements

1. **Caching**: Should we cache review results by DOI/PMID?
2. **Batch processing**: Support reviewing multiple papers at once?
3. **Comparison mode**: Compare two papers side-by-side?
4. **Citation network**: Visualize citing/cited papers?
5. **API endpoint**: Expose as REST API for integration?

---

## Changelog

- 2025-01-09: Initial plan created
