# PRISMA 2020 Assessment System - Developer Documentation

## Overview

The PRISMA 2020 assessment system provides automated evaluation of systematic reviews and meta-analyses against the PRISMA 2020 (Preferred Reporting Items for Systematic reviews and Meta-Analyses) reporting guidelines. This system helps identify reporting gaps and improve transparency in evidence synthesis.

## Architecture

### Core Components

```
bmlibrarian/
├── agents/
│   └── prisma2020_agent.py          # Main PRISMA 2020 assessment agent
├── lab/
│   └── prisma2020_lab.py            # Interactive GUI laboratory
└── prisma2020_lab.py                # Lab entry point script
```

### PRISMA2020Agent Class

The `PRISMA2020Agent` extends `BaseAgent` and provides:

1. **Suitability Assessment**: Determines if a document is a systematic review or meta-analysis
2. **Comprehensive PRISMA Assessment**: Evaluates all 27 PRISMA 2020 checklist items
3. **Batch Processing**: Supports assessment of multiple documents
4. **Export Capabilities**: JSON and CSV export of assessment results

## Data Models

### SuitabilityAssessment

Pre-assessment check to determine if a document is appropriate for PRISMA evaluation.

```python
@dataclass
class SuitabilityAssessment:
    is_systematic_review: bool
    is_meta_analysis: bool
    is_suitable: bool  # True if systematic review OR meta-analysis
    confidence: float  # 0-1 confidence in suitability assessment
    rationale: str  # Explanation of why suitable or not suitable
    document_type: str  # e.g., "systematic review", "primary RCT", etc.
    document_id: str
    document_title: str
```

### PRISMA2020Assessment

Comprehensive assessment of PRISMA 2020 compliance for all 27 checklist items.

```python
@dataclass
class PRISMA2020Assessment:
    # Suitability
    is_systematic_review: bool
    is_meta_analysis: bool
    suitability_rationale: str

    # All 27 PRISMA items (score + explanation for each)
    # Score scale: 0.0 = Not reported, 1.0 = Partially reported, 2.0 = Fully reported
    title_score: float
    title_explanation: str
    abstract_score: float
    abstract_explanation: str
    # ... (25 more items)

    # Overall metrics
    overall_compliance_score: float  # 0-2 scale (average of all items)
    overall_compliance_percentage: float  # 0-100% (score/2 * 100)
    total_applicable_items: int
    fully_reported_items: int  # Items scoring 2.0
    partially_reported_items: int  # Items scoring 1.0
    not_reported_items: int  # Items scoring 0.0
    overall_confidence: float  # 0-1 confidence in assessment

    # Metadata
    document_id: str
    document_title: str
    pmid: Optional[str]
    doi: Optional[str]
    created_at: Optional[datetime]
```

## PRISMA 2020 Checklist Structure

The checklist consists of 27 items across 7 sections:

### 1. TITLE (Item 1)
- Identifies the report as a systematic review

### 2. ABSTRACT (Item 2)
- Provides structured summary (background, objectives, methods, results, conclusions, funding, registration)

### 3. INTRODUCTION (Items 3-4)
- **Item 3**: Rationale for review in context of existing knowledge
- **Item 4**: Explicit objectives/questions with PICO elements

### 4. METHODS (Items 5-15)
- **Item 5**: Eligibility criteria with rationale
- **Item 6**: Information sources (databases, dates, restrictions)
- **Item 7**: Full search strategy for at least one database
- **Item 8**: Study selection process
- **Item 9**: Data collection methods
- **Item 10**: Data items and variables sought
- **Item 11**: Risk of bias assessment tools/methods
- **Item 12**: Effect measures (e.g., risk ratio, mean difference)
- **Item 13**: Synthesis methods (meta-analysis approach)
- **Item 14**: Reporting bias assessment methods
- **Item 15**: Certainty assessment methods (e.g., GRADE)

### 5. RESULTS (Items 16-22)
- **Item 16**: Study selection results with PRISMA flow diagram
- **Item 17**: Study characteristics of included studies
- **Item 18**: Risk of bias assessments for included studies
- **Item 19**: Results of individual studies with summary statistics
- **Item 20**: Synthesized results (meta-analysis)
- **Item 21**: Publication bias assessments
- **Item 22**: Certainty of evidence with justification

### 6. DISCUSSION (Items 23-25)
- **Item 23**: Interpretation of results in context of other evidence
- **Item 24**: Limitations at study and review level
- **Item 25**: Conclusions related to objectives without overstatement

### 7. OTHER INFORMATION (Items 26-27)
- **Item 26**: Protocol registration information
- **Item 27**: Funding sources and sponsor roles

## Usage Examples

### Basic Assessment

```python
from bmlibrarian.agents import PRISMA2020Agent, AgentOrchestrator
from bmlibrarian.database import fetch_documents_by_ids

# Initialize agent
orchestrator = AgentOrchestrator(max_workers=2)
agent = PRISMA2020Agent(
    model="gpt-oss:20b",
    host="http://localhost:11434",
    temperature=0.1,
    orchestrator=orchestrator
)

# Fetch systematic review from database
documents = fetch_documents_by_ids([12345])
document = documents[0]

# Assess PRISMA compliance (includes suitability check)
assessment = agent.assess_prisma_compliance(document)

if assessment:
    print(f"Compliance: {assessment.overall_compliance_percentage:.1f}%")
    print(f"Category: {assessment.get_compliance_category()}")
    print(f"Fully reported: {assessment.fully_reported_items}/27")
    print(f"Partially reported: {assessment.partially_reported_items}/27")
    print(f"Not reported: {assessment.not_reported_items}/27")
```

### Suitability Check Only

```python
# Check if document is suitable before full assessment
suitability = agent.check_suitability(document)

if suitability.is_suitable:
    print(f"Document is a {suitability.document_type}")
    print(f"Confidence: {suitability.confidence:.1%}")
    print(f"Rationale: {suitability.rationale}")
else:
    print(f"Not suitable: {suitability.rationale}")
```

### Batch Assessment

```python
# Assess multiple systematic reviews
documents = fetch_documents_by_ids([12345, 23456, 34567])

assessments = agent.assess_batch(
    documents,
    min_confidence=0.5,
    skip_suitability_check=False,
    progress_callback=lambda curr, total, title: print(f"{curr}/{total}: {title}")
)

print(f"Successfully assessed {len(assessments)} documents")
```

### Export Results

```python
# Export to JSON
agent.export_to_json(assessments, "prisma_assessments.json")

# Export to CSV for analysis
agent.export_to_csv(assessments, "prisma_assessments.csv")

# Format individual assessment as text
summary = agent.format_assessment_summary(assessment)
print(summary)
```

## Scoring System

Each of the 27 PRISMA items is scored on a 3-point scale:

- **2.0**: Fully reported / Adequately reported
  - All required information present
  - Meets PRISMA 2020 standards completely

- **1.0**: Partially reported / Inadequately reported
  - Some required information present
  - Missing key details or insufficient detail

- **0.0**: Not reported / Not present
  - Required information absent
  - Item not addressed in the document

### Overall Compliance Calculation

```python
# Average score across all 27 items
overall_compliance_score = sum(all_item_scores) / 27  # Range: 0-2

# Convert to percentage
overall_compliance_percentage = (overall_compliance_score / 2.0) * 100  # Range: 0-100%

# Compliance categories
# 90-100%: Excellent
# 75-89%: Good
# 60-74%: Adequate
# 40-59%: Poor
# 0-39%: Very Poor
```

## Configuration

The agent can be configured through `~/.bmlibrarian/config.json`:

```json
{
  "models": {
    "prisma2020_agent": "gpt-oss:20b"
  },
  "agents": {
    "prisma2020": {
      "temperature": 0.1,
      "top_p": 0.9,
      "max_tokens": 4000
    }
  }
}
```

## Implementation Details

### Text Analysis Strategy

1. **Suitability Check**:
   - Analyzes title + abstract (first 3000 chars)
   - Fast preliminary assessment
   - Identifies systematic reviews vs. primary research

2. **Full PRISMA Assessment**:
   - Analyzes full text if available, else abstract
   - Truncates to 15,000 characters for context window
   - Comprehensive evaluation of all 27 items

### LLM Prompting

The agent uses carefully crafted prompts that:
- Define each PRISMA item precisely
- Provide scoring criteria (0.0, 1.0, 2.0)
- Request JSON-formatted responses
- Include examples and edge cases
- Enforce evidence-based assessment (no assumptions)

### Error Handling

- **Connection failures**: Gracefully handled with retry logic (max 3 attempts)
- **JSON parsing errors**: Robust error recovery with informative logging
- **Missing documents**: Clear error messages
- **Unsuitable documents**: Returned with rationale, no false assessment

### Statistics Tracking

The agent maintains internal statistics:

```python
stats = agent.get_assessment_stats()
# Returns:
# {
#     'total_assessments': 50,
#     'successful_assessments': 45,
#     'failed_assessments': 2,
#     'unsuitable_documents': 3,
#     'low_confidence_assessments': 5,
#     'parse_failures': 0,
#     'success_rate': 0.9
# }
```

## GUI Laboratory

The PRISMA 2020 Lab (`prisma2020_lab.py`) provides an interactive interface:

### Features

1. **Document Loading**: Enter document ID to load from database
2. **Suitability Display**: Visual suitability assessment with color coding
3. **Compliance Summary**: Overall compliance metrics with progress indicators
4. **Item-by-Item Breakdown**: All 27 items organized by section
5. **Visual Scoring**: Color-coded cards (green/orange/red) for each item
6. **Model Selection**: Switch between available Ollama models

### Usage

```bash
uv run python prisma2020_lab.py
```

## Testing

### Unit Tests

Create comprehensive tests for the PRISMA 2020 agent:

```python
# tests/test_prisma2020_agent.py

def test_suitability_check_systematic_review():
    """Test suitability check identifies systematic reviews."""
    agent = PRISMA2020Agent(model="test-model")

    # Document that is a systematic review
    doc = {
        'id': 123,
        'title': 'Systematic review of exercise interventions',
        'abstract': 'We conducted a systematic review and meta-analysis...'
    }

    suitability = agent.check_suitability(doc)
    assert suitability.is_suitable
    assert suitability.is_systematic_review

def test_suitability_check_primary_research():
    """Test suitability check rejects primary research."""
    agent = PRISMA2020Agent(model="test-model")

    # Document that is an RCT (not systematic review)
    doc = {
        'id': 124,
        'title': 'Randomized controlled trial of exercise',
        'abstract': 'We randomized 100 participants to exercise or control...'
    }

    suitability = agent.check_suitability(doc)
    assert not suitability.is_suitable
    assert not suitability.is_systematic_review

def test_prisma_assessment_scoring():
    """Test PRISMA assessment provides valid scores."""
    agent = PRISMA2020Agent(model="test-model")

    # Systematic review document
    doc = {...}  # Complete systematic review

    assessment = agent.assess_prisma_compliance(doc)

    # Verify score ranges
    assert 0 <= assessment.overall_compliance_score <= 2
    assert 0 <= assessment.overall_compliance_percentage <= 100
    assert assessment.fully_reported_items >= 0
    assert assessment.partially_reported_items >= 0
    assert assessment.not_reported_items >= 0

    # Total should equal 27
    total = (assessment.fully_reported_items +
             assessment.partially_reported_items +
             assessment.not_reported_items)
    assert total == 27
```

## Performance Considerations

### Processing Time

- **Suitability check**: ~2-5 seconds (lightweight)
- **Full PRISMA assessment**: ~30-60 seconds (comprehensive)
- **Batch processing**: Serial execution (safe for local Ollama)

### Resource Usage

- **Token usage**: ~2000-3000 tokens per suitability check
- **Token usage**: ~8000-12000 tokens per full assessment
- **Memory**: Minimal (SQLite queue-based processing)

## Integration with BMLibrarian

The PRISMA 2020 agent integrates seamlessly with the BMLibrarian ecosystem:

1. **Database**: Uses `fetch_documents_by_ids()` for document retrieval
2. **Configuration**: Respects `~/.bmlibrarian/config.json` settings
3. **Orchestrator**: Supports queue-based processing via `AgentOrchestrator`
4. **Factory**: Available through `AgentFactory` for dynamic creation

## Future Enhancements

Potential improvements for the PRISMA 2020 system:

1. **Abstract-Specific Checklist**: Support for 12-item PRISMA abstract checklist
2. **Temporal Analysis**: Track PRISMA compliance trends over time
3. **Journal Comparison**: Compare compliance across journals
4. **Recommendation Engine**: Suggest specific improvements for low-scoring items
5. **PostgreSQL Storage**: Store assessments in database for longitudinal analysis
6. **PDF Annotation**: Generate annotated PDFs highlighting PRISMA items
7. **Multi-Language Support**: Assess non-English systematic reviews

## References

- Page MJ, McKenzie JE, Bossuyt PM, et al. The PRISMA 2020 statement: an updated guideline for reporting systematic reviews. BMJ 2021;372:n71. doi: 10.1136/bmj.n71
- Official PRISMA website: https://www.prisma-statement.org/

## Support

For issues or questions about the PRISMA 2020 system:
- Check documentation: `doc/users/prisma2020_guide.md`
- Review examples in `prisma2020_lab.py`
- File issues on GitHub
