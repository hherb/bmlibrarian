# Transparency Assessment System — Developer Documentation

## Architecture Overview

The transparency assessment system evaluates biomedical publications for disclosure completeness across five dimensions: funding, conflicts of interest, data availability, trial registration, and author contributions. It produces a composite transparency score (0-10) and risk classification.

### Design Principles

1. **Fully offline**: Uses local Ollama models and data already in PostgreSQL
2. **Follows StudyAssessmentAgent pattern**: Same BaseAgent inheritance, same JSON generation methods, same batch processing approach
3. **Dual detection strategy**: Pattern matching (fast, deterministic) augmented by LLM analysis (flexible, contextual)
4. **Enrichment from bulk metadata**: Optional post-processing with data from PubMed, ClinicalTrials.gov, and Retraction Watch

## Module Structure

```
src/bmlibrarian/
├── agents/
│   ├── transparency_data.py      # Data models, constants, pattern matching
│   └── transparency_agent.py     # TransparencyAgent (BaseAgent subclass)
├── importers/
│   ├── pubmed_bulk_importer.py   # Extended with transparency metadata extraction
│   ├── clinicaltrials_importer.py # ClinicalTrials.gov bulk importer
│   └── retraction_watch_importer.py # Retraction Watch CSV importer
├── pdf_processor/
│   ├── models.py                 # Extended SectionType enum
│   └── segmenter.py              # Extended section patterns
└── lab/
    └── transparency_lab.py       # PySide6 Laboratory GUI

scripts/
└── transparency_lab.py           # Lab entry point

transparency_analyzer_cli.py      # CLI tool
clinicaltrials_import_cli.py      # ClinicalTrials.gov CLI
retraction_watch_cli.py           # Retraction Watch CLI

migrations/
└── 029_create_transparency_schema.sql  # Database schema
```

## Data Models (`transparency_data.py`)

### TransparencyAssessment

The central data model storing all assessment results:

```python
@dataclass
class TransparencyAssessment:
    document_id: str
    document_title: str
    pmid: Optional[str] = None
    doi: Optional[str] = None

    # Funding disclosure
    has_funding_disclosure: bool = False
    funding_statement: Optional[str] = None
    funding_sources: List[str] = field(default_factory=list)
    is_industry_funded: Optional[bool] = None
    industry_funding_confidence: float = 0.0
    funding_disclosure_quality: float = 0.0

    # Conflict of interest
    has_coi_disclosure: bool = False
    coi_statement: Optional[str] = None
    conflicts_identified: List[str] = field(default_factory=list)
    coi_disclosure_quality: float = 0.0

    # Data availability
    data_availability: str = DataAvailability.NOT_STATED.value
    data_availability_statement: Optional[str] = None

    # Author contributions
    has_author_contributions: bool = False
    contributions_statement: Optional[str] = None

    # Trial registration
    has_trial_registration: bool = False
    trial_registry_ids: List[str] = field(default_factory=list)

    # Overall assessment
    transparency_score: float = 0.0       # 0-10
    overall_confidence: float = 0.0       # 0-1
    risk_level: str = RiskLevel.UNKNOWN.value
    risk_indicators: List[str] = field(default_factory=list)
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)

    # Bulk metadata enrichment
    is_retracted: Optional[bool] = None
    retraction_reason: Optional[str] = None
    trial_sponsor_class: Optional[str] = None

    # Audit
    created_at: Optional[datetime] = None
    model_used: Optional[str] = None
    agent_version: Optional[str] = None
```

### Enums

- `RiskLevel`: LOW, MEDIUM, HIGH, UNKNOWN
- `DataAvailability`: OPEN, ON_REQUEST, RESTRICTED, NOT_AVAILABLE, NOT_STATED

### Constants

All numeric thresholds are named constants:

```python
MAX_TEXT_LENGTH = 12000
SCORE_THRESHOLD_HIGH_RISK = 3.0
SCORE_THRESHOLD_MEDIUM_RISK = 6.0
MAX_FUNDING_SCORE = 3.0
MAX_COI_SCORE = 3.0
MAX_DATA_AVAILABILITY_SCORE = 2.0
MAX_TRIAL_REGISTRATION_SCORE = 1.0
MAX_AUTHOR_CONTRIBUTIONS_SCORE = 1.0
MAX_TOTAL_SCORE = 10.0
DEFAULT_MAX_TOKENS = 3000
DEFAULT_MAX_RETRIES = 3
```

### Pattern Matching

Two pure functions handle deterministic detection:

- `is_likely_industry_funder(name)` — checks against `KNOWN_PHARMA_COMPANIES` list and `CORPORATE_INDICATOR_PATTERNS` regexes
- `extract_trial_registry_ids(text)` — extracts NCT, ISRCTN, EudraCT, ACTRN, ChiCTR, CTRI, DRKS, JPRN, KCT, PACTR, SLCTR, TCTR, UMIN, NTR, PROSPERO IDs

## TransparencyAgent (`transparency_agent.py`)

### Class Hierarchy

```
BaseAgent
  └── TransparencyAgent
```

### Key Methods

#### `assess_transparency(document, min_confidence=0.4)`

Main entry point. Accepts a document dict (with `title`, `full_text` or `abstract`, `id`, `doi`, `pmid` fields). Returns `Optional[TransparencyAssessment]`.

Flow:
1. Extract text (prefer `full_text`, fall back to `abstract`)
2. Truncate to `MAX_TEXT_LENGTH`
3. Pre-extract trial registry IDs via regex
4. Build structured prompt with scoring rubric
5. Call `_generate_and_parse_json()` to get LLM response
6. Parse JSON into `TransparencyAssessment`
7. Merge pattern-matched results (industry funder names, registry IDs)
8. Classify risk level
9. Filter by confidence threshold

#### `assess_transparency_by_id(document_id)`

Convenience method that fetches document from database by ID, then calls `assess_transparency()`.

#### `assess_batch(documents, progress_callback=None)`

Processes multiple documents sequentially with optional progress callback.

#### `enrich_with_metadata(assessment)`

Queries `transparency.document_metadata` for bulk-imported data and merges into the assessment:
- Retraction status
- Trial sponsor class
- Grant information → updates industry funding detection
- Adds risk indicator if retracted

#### `_build_prompt(title, text, pre_extracted_ids)`

Constructs a detailed prompt with:
- Scoring rubric for each dimension
- JSON output schema specification
- Pre-extracted trial registry IDs for the LLM to confirm/augment
- Instructions for the specific analysis task

#### `format_assessment_summary(assessment)`

Formats a human-readable text summary with sections for each assessment dimension.

#### `export_to_json(assessments, output_path)` / `export_to_csv(assessments, output_path)`

Batch export methods for reporting.

### LLM Interaction

The agent uses `_generate_and_parse_json()` from `BaseAgent`, which handles:
- Retry logic (up to `DEFAULT_MAX_RETRIES`)
- JSON extraction from LLM response
- Error recovery on malformed JSON

Expected JSON schema from LLM:

```json
{
  "has_funding_disclosure": true,
  "funding_statement": "...",
  "funding_sources": ["NIH", "AHA"],
  "is_industry_funded": false,
  "industry_funding_confidence": 0.9,
  "funding_disclosure_quality": 0.8,
  "has_coi_disclosure": true,
  "coi_statement": "...",
  "conflicts_identified": [],
  "coi_disclosure_quality": 0.7,
  "data_availability": "open",
  "data_availability_statement": "...",
  "has_author_contributions": true,
  "contributions_statement": "...",
  "has_trial_registration": true,
  "trial_registry_ids": ["NCT12345678"],
  "transparency_score": 8.5,
  "overall_confidence": 0.85,
  "risk_indicators": [],
  "strengths": ["Complete funding disclosure", "Data openly available"],
  "weaknesses": ["Generic COI statement"]
}
```

### Pattern-Match Augmentation

After LLM analysis, the agent merges deterministic results:

1. **Industry funding**: If any `funding_sources` match `is_likely_industry_funder()`, sets `is_industry_funded=True` regardless of LLM output
2. **Trial registry IDs**: Union of regex-extracted and LLM-extracted IDs

This ensures high recall for industry funding and registry ID detection.

## Database Schema

### `transparency.assessments`

Stores LLM-generated assessments. One row per document (UNIQUE on `document_id`).

Key columns match `TransparencyAssessment` fields. Indexed on `risk_level`, `transparency_score`, `is_industry_funded`, `is_retracted`.

### `transparency.document_metadata`

Stores structured metadata from bulk imports. One row per document.

Key columns:
- `grants` JSONB — from PubMed `<GrantList>`
- `publication_types` TEXT[] — from PubMed `<PublicationTypeList>`
- `is_retracted` BOOLEAN — from PubMed XML or Retraction Watch
- `author_affiliations` JSONB — from PubMed `<AffiliationInfo>`
- `clinical_trial_id` TEXT — NCT number from ClinicalTrials.gov
- `trial_sponsor`, `trial_sponsor_class` — from ClinicalTrials.gov

### Views

- `transparency.v_full_assessment` — joins assessments + document + metadata
- `transparency.v_statistics` — aggregate stats (counts by risk level, disclosure rates, etc.)

## Bulk Importers

### PubMed Metadata Extension

The existing `PubMedBulkImporter` was extended with:
- `_extract_transparency_metadata(article_elem)` — parses `<GrantList>`, `<PublicationTypeList>`, `<CommentsCorrectionsList>`, `<AffiliationInfo>`
- `_store_transparency_metadata_batch(metadata_list)` — UPSERT into `transparency.document_metadata`

This runs automatically during normal PubMed bulk imports. Gracefully skips if the transparency schema doesn't exist.

### ClinicalTrials.gov Importer

`ClinicalTrialsBulkImporter` in `clinicaltrials_importer.py`:
- Downloads `AllPublicXML.zip` (~10GB, resumable)
- Streams ZIP entries (no full extraction needed)
- Parses XML for NCT ID, sponsor, sponsor class, titles
- Matches trials to documents by searching for NCT IDs in document text
- Stores in `transparency.document_metadata`

### Retraction Watch Importer

`RetractionWatchImporter` in `retraction_watch_importer.py`:
- Parses CSV with flexible column detection
- Matches by DOI first, then PMID
- Updates `transparency.document_metadata` and `doi_metadata.is_retracted`
- Handles multiple CSV encodings (utf-8, latin-1, cp1252)

## PDF Processor Extensions

Four new `SectionType` values were added:
- `FUNDING`
- `CONFLICTS`
- `DATA_AVAILABILITY`
- `AUTHOR_CONTRIBUTIONS`

Corresponding heading patterns were added to the segmenter for each type, covering common variations (e.g., "Conflict of Interest", "Competing Interests", "Disclosures", etc.).

## Testing

43 unit tests in `tests/test_transparency_agent.py`:

- `TestTransparencyAssessment` — dataclass defaults, serialization, risk classification
- `TestIndustryFunderDetection` — known companies, corporate indicators, negative cases
- `TestTrialRegistryExtraction` — all 15 registry patterns, deduplication
- `TestTransparencyAgent` — transparent/opaque documents, augmentation, batch processing, export
- `TestPDFProcessorExtension` — new section types and segmenter patterns

Run tests:
```bash
uv run python -m pytest tests/test_transparency_agent.py -v
```

## Integration Points

### With Existing Agents

The TransparencyAgent is standalone and does not integrate into the workflow orchestration system. It can be used independently via:
- CLI (`transparency_analyzer_cli.py`)
- Laboratory GUI (`scripts/transparency_lab.py`)
- Python API (`from bmlibrarian.agents import TransparencyAgent`)

### With Database

- Reads documents from `public.document` table
- Writes assessments to `transparency.assessments` table
- Reads/writes metadata to `transparency.document_metadata` table
- Uses `fetch_documents_by_ids()` for document retrieval

### With Configuration

Uses `BMLibrarianConfig` for:
- Model selection: `config.get_model("transparency")` (defaults to `gpt-oss:20b`)
- Ollama host: `config.get_ollama_config().get("host")`
- Agent parameters: temperature, etc.
