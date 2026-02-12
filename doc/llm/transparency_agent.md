# Transparency Agent — LLM Guidance

## Purpose

The TransparencyAgent evaluates biomedical research publications for disclosure completeness and undisclosed bias risk. It analyzes full-text articles to assess funding transparency, conflict of interest declarations, data availability, trial registration, and author contributions.

## Agent Identity

- **Class**: `TransparencyAgent` (inherits from `BaseAgent`)
- **Version**: 1.0.0
- **Location**: `src/bmlibrarian/agents/transparency_agent.py`
- **Data models**: `src/bmlibrarian/agents/transparency_data.py`
- **Default model**: `gpt-oss:20b`

## What the Agent Does

Given a biomedical publication's text (full-text preferred, abstract as fallback), the agent:

1. **Analyzes funding disclosure**: Identifies funding statements, names funders, detects industry vs. governmental/academic funding
2. **Evaluates COI disclosure**: Finds conflict of interest statements, identifies declared conflicts
3. **Assesses data availability**: Classifies data sharing level (open, on request, restricted, not available, not stated)
4. **Checks trial registration**: Identifies clinical trial registry IDs (NCT, ISRCTN, etc.)
5. **Checks author contributions**: Identifies CRediT or author contribution statements
6. **Computes transparency score**: 0-10 composite score
7. **Classifies risk level**: Low (>6), Medium (3-6), High (<3)

## Scoring Rubric

The LLM is instructed to score each dimension:

- **Funding (0-3)**: 0=absent, 1=vague, 2=named sources, 3=complete with grants
- **COI (0-3)**: 0=absent, 1=generic, 2=explicit none/specific, 3=detailed per-author
- **Data availability (0-2)**: 0=absent, 1=restricted/on request, 2=open access
- **Trial registration (0-1)**: 0=not registered/not applicable, 1=registered with ID
- **Author contributions (0-1)**: 0=absent, 1=present

Total: 0-10

## JSON Output Schema

The LLM must return valid JSON matching this schema:

```json
{
  "has_funding_disclosure": boolean,
  "funding_statement": "extracted text or null",
  "funding_sources": ["list", "of", "funders"],
  "is_industry_funded": boolean,
  "industry_funding_confidence": float (0-1),
  "funding_disclosure_quality": float (0-1),
  "has_coi_disclosure": boolean,
  "coi_statement": "extracted text or null",
  "conflicts_identified": ["list of conflicts"],
  "coi_disclosure_quality": float (0-1),
  "data_availability": "open|on_request|restricted|not_available|not_stated",
  "data_availability_statement": "extracted text or null",
  "has_author_contributions": boolean,
  "contributions_statement": "extracted text or null",
  "has_trial_registration": boolean,
  "trial_registry_ids": ["NCT12345678"],
  "transparency_score": float (0-10),
  "overall_confidence": float (0-1),
  "risk_indicators": ["list of concerns"],
  "strengths": ["list of positive aspects"],
  "weaknesses": ["list of gaps"]
}
```

## Pattern Matching (Pre-LLM)

Before calling the LLM, the agent performs deterministic extraction:

1. **Trial registry IDs**: Regex extraction for 15 registry formats (NCT, ISRCTN, EudraCT, ACTRN, ChiCTR, CTRI, DRKS, JPRN, KCT, PACTR, SLCTR, TCTR, UMIN, NTR, PROSPERO)
2. These pre-extracted IDs are included in the prompt for the LLM to confirm or augment

## Post-LLM Augmentation

After the LLM returns its analysis, the agent:

1. **Checks funding sources** against `KNOWN_PHARMA_COMPANIES` and `CORPORATE_INDICATOR_PATTERNS` — if any match, sets `is_industry_funded=True`
2. **Merges trial registry IDs** — union of regex-extracted and LLM-extracted, deduplicated
3. **Classifies risk level** based on final transparency score

## Key Constants

- `MAX_TEXT_LENGTH = 12000` — text truncation limit
- `SCORE_THRESHOLD_HIGH_RISK = 3.0` — below this = high risk
- `SCORE_THRESHOLD_MEDIUM_RISK = 6.0` — below this = medium risk
- `DEFAULT_MIN_CONFIDENCE = 0.4` — minimum confidence to accept result
- `DEFAULT_MAX_TOKENS = 3000` — LLM response token limit
- `DEFAULT_MAX_RETRIES = 3` — retry count for failed LLM calls

## Industry Detection

The `KNOWN_PHARMA_COMPANIES` tuple contains ~60 major pharmaceutical, biotech, medical device, CRO, diagnostics, and tobacco companies. The `CORPORATE_INDICATOR_PATTERNS` tuple contains compiled regexes for corporate suffixes and industry keywords.

## Enrichment

After LLM assessment, the agent can optionally query `transparency.document_metadata` for bulk-imported data:
- PubMed grants → updates industry funding flag
- ClinicalTrials.gov sponsor class → adds to assessment
- Retraction Watch → sets retraction status and adds risk indicator

## Error Handling

- Empty or missing text: Returns `None`
- LLM connection failure: Returns `None` with error logged
- JSON parse failure: Retries up to `DEFAULT_MAX_RETRIES` times
- Missing JSON fields: Uses dataclass defaults (safe degradation)
- Low confidence: Filtered out if below `DEFAULT_MIN_CONFIDENCE`
