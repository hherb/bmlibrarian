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
6. Validate and normalize it with `_validate_assessment_data()` (see "Validating LLM output" below)
7. Merge pattern-matched results (industry funder names, registry IDs)
8. Build the `TransparencyAssessment`
9. Classify risk level
10. Flag low confidence: below `min_confidence` the assessment is logged and counted in `low_confidence_assessments`, but still returned

#### `assess_transparency_by_id(document_id)`

Convenience method that fetches document from database by ID, then calls `assess_transparency()`.

#### `assess_batch(documents, progress_callback=None)`

Processes multiple documents sequentially with optional progress callback. An exception for one document is logged, counted in `failed_assessments`, and skipped; the rest of the batch continues.

#### `get_score_distribution(assessments)`

Counts assessments per transparency bucket. Buckets come from `score_distribution_label()` and use the same thresholds as `classify_risk()` (`SCORE_THRESHOLD_HIGH_RISK`, `SCORE_THRESHOLD_MEDIUM_RISK`), so the bucket matches the risk level computed from the score alone: `low_transparency (0-<3)` = high risk, `moderate_transparency (3-<6)` = medium, `high_transparency (6-10)` = low. Ranges are half-open (3.0 is moderate, 6.0 is high). `enrich_with_metadata()` can raise the risk level afterwards (a retracted paper becomes high risk) without changing its bucket.

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

### Validating LLM output

The parsed JSON is untrusted. `_validate_assessment_data()` normalizes it using pure helpers from `transparency_data.py`:

- The response must be a JSON object with all `REQUIRED_ASSESSMENT_FIELDS`; otherwise the document fails (`None`, counted in `failed_assessments`).
- Numeric fields (`NUMERIC_ASSESSMENT_FIELDS`) are parsed with `parse_finite_float()`: numbers and numeric strings are accepted; booleans, NaN/infinity and non-numbers are rejected. Ranges: `transparency_score` 0-10, confidences and `*_disclosure_quality` 0-1.
  - Required (`transparency_score`, `overall_confidence`): a rejected **or out-of-range** value fails the document. Out of range usually means the model answered on the wrong scale (e.g. `45` on 0-100); clamping it would produce the most favourable score.
  - Optional: an invalid value falls back to `0.0` with a warning (a missing one silently, debug log only); an out-of-range value is clamped with a warning.
- Booleans go through `coerce_optional_bool()`, which accepts real booleans and `true`/`yes`/`false`/`no` strings (plain `bool("false")` would be `True`). An unrecognisable `has_funding_disclosure` / `has_coi_disclosure` fails the document; `is_industry_funded` falls back to `None` (pattern matching decides) and `has_author_contributions` to `False`, with a warning.
- `data_availability` goes through `coerce_data_availability()` (case-insensitive, spaces/hyphens as underscores); `null` or an unknown value becomes `not_stated` with a warning.
- List fields (`LIST_ASSESSMENT_FIELDS`) go through `coerce_str_list()`: a single string becomes a one-element list, `None` an empty list, items are stringified and stripped with blank/`None` items dropped; any other type becomes an empty list with a warning.
- LLM `trial_registry_ids` go through `filter_trial_registry_ids()`: entries in no known registry format (`"N/A"`, `"registered"`) are dropped with a warning, so they cannot set `has_trial_registration`.

### Pattern-Match Augmentation

After LLM analysis, the agent merges deterministic results:

1. **Industry funding**: If any `funding_sources` match `is_likely_industry_funder()`, sets `is_industry_funded=True` regardless of LLM output, and raises `industry_funding_confidence` to at least `PATTERN_INDUSTRY_MIN_CONFIDENCE` (0.8)
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

97 unit tests in `tests/test_transparency_agent.py`:

- `TestTransparencyAssessment` — dataclass defaults, serialization, risk classification
- `TestIndustryFunderDetection` — known companies, corporate indicators, negative cases
- `TestTrialRegistryExtraction` — all 15 registry patterns, deduplication
- `TestTransparencyAgent` — transparent/opaque documents, augmentation, batch processing, export
- `TestLLMOutputCoercion` — pure helpers that sanitize LLM output (numbers, booleans, data availability, lists, registry IDs) and score buckets
- `TestTransparencyAgentMalformedResponses` — malformed/out-of-range LLM fields, batch resilience, score distribution
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
