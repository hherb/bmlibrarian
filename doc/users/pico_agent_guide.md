# PICO Agent User Guide

## Overview

The **PICOAgent** is a specialized AI agent designed to extract structured information from biomedical research papers using the PICO framework. PICO is a standardized approach used in evidence-based medicine to analyze clinical studies and structure research questions.

### What is PICO?

**PICO** stands for:

- **P**opulation: Who was studied? (demographics, condition, setting)
- **I**ntervention: What was done to the study population? (treatment, test, exposure)
- **C**omparison: Who/what do we compare against? (control group, alternative treatment)
- **O**utcome: What was measured? (effects, results, endpoints)

### Why Use PICO Extraction?

PICO extraction is essential for:

- **Systematic Reviews**: Quickly extract key study components from hundreds of papers
- **Meta-Analysis**: Standardize study data for quantitative synthesis
- **Evidence Synthesis**: Compare interventions across different studies
- **Research Gap Analysis**: Identify understudied populations or outcomes
- **Grant Writing**: Structure research questions using evidence-based frameworks
- **Clinical Decision Making**: Rapidly assess study applicability to patient populations

## Quick Start

### Basic Usage

```python
from bmlibrarian.agents import PICOAgent

# Initialize agent
agent = PICOAgent(model="gpt-oss:20b")

# Prepare a document
document = {
    'id': '12345678',
    'title': 'Effect of Metformin on Glycemic Control in Type 2 Diabetes',
    'abstract': """
    We conducted a randomized controlled trial involving 150 adults aged 40-65
    with type 2 diabetes. Participants received either metformin 1000mg twice
    daily (n=75) or placebo (n=75) for 12 weeks. The primary outcome was change
    in HbA1c from baseline to week 12...
    """,
    'pmid': '12345678',
    'doi': '10.1000/example.12345'
}

# Extract PICO components
extraction = agent.extract_pico_from_document(
    document=document,
    min_confidence=0.5  # Minimum confidence threshold (0-1)
)

# Display results
if extraction:
    print(agent.format_pico_summary(extraction))
```

### Output Example

```
================================================================================
PICO EXTRACTION: Effect of Metformin on Glycemic Control in Type 2 Diabetes
================================================================================
Document ID: 12345678
PMID: 12345678
DOI: 10.1000/example.12345
Study Type: RCT
Sample Size: N=150

Overall Confidence: 95.00%

--- POPULATION (Confidence: 0.95) ---
Adults aged 40-65 years with type 2 diabetes and HbA1c > 7%, recruited from
primary care clinics

--- INTERVENTION (Confidence: 0.98) ---
Metformin 1000mg twice daily for 12 weeks

--- COMPARISON (Confidence: 0.95) ---
Matching placebo tablets twice daily for 12 weeks

--- OUTCOME (Confidence: 0.92) ---
Change in HbA1c from baseline to week 12 (primary); fasting plasma glucose,
body weight, adverse events (secondary)
================================================================================
```

## Detailed Usage

### Configuration

#### Using Configuration File

Add to `~/.bmlibrarian/config.json`:

```json
{
  "models": {
    "pico_agent": "gpt-oss:20b"
  },
  "agents": {
    "pico": {
      "temperature": 0.1,
      "top_p": 0.9,
      "max_tokens": 2000,
      "min_confidence": 0.5,
      "max_retries": 3
    }
  }
}
```

#### Programmatic Configuration

```python
from bmlibrarian.agents import PICOAgent

agent = PICOAgent(
    model="gpt-oss:20b",
    temperature=0.1,      # Low temperature for consistent output
    top_p=0.9,
    max_tokens=2000,      # Sufficient for detailed PICO extraction
    max_retries=3,        # Retry attempts for failed extractions
    show_model_info=True  # Display model initialization info
)
```

### Batch Processing

Extract PICO components from multiple documents:

```python
# List of documents to process
documents = [doc1, doc2, doc3, ...]  # Each with 'id', 'title', 'abstract'

# Extract with progress tracking
def progress_callback(current, total, doc_title):
    print(f"Processing {current}/{total}: {doc_title[:50]}...")

extractions = agent.extract_pico_batch(
    documents=documents,
    min_confidence=0.5,
    progress_callback=progress_callback
)

print(f"Successfully extracted PICO from {len(extractions)} documents")
```

### Exporting Results

#### Export to JSON

```python
# Export to JSON with metadata
agent.export_to_json(
    extractions=extractions,
    output_file="pico_extractions.json"
)
```

JSON output structure:
```json
{
  "extractions": [
    {
      "document_id": "12345678",
      "document_title": "...",
      "population": "...",
      "intervention": "...",
      "comparison": "...",
      "outcome": "...",
      "study_type": "RCT",
      "sample_size": "N=150",
      "extraction_confidence": 0.95,
      "population_confidence": 0.95,
      "intervention_confidence": 0.98,
      "comparison_confidence": 0.95,
      "outcome_confidence": 0.92,
      "pmid": "12345678",
      "doi": "10.1000/example.12345",
      "created_at": "2025-01-15T10:30:00Z"
    }
  ],
  "metadata": {
    "total_extractions": 1,
    "extraction_date": "2025-01-15T10:30:00Z",
    "agent_model": "gpt-oss:20b",
    "statistics": {
      "total_extractions": 10,
      "successful_extractions": 8,
      "success_rate": 0.8
    }
  }
}
```

#### Export to CSV

```python
# Export to CSV for systematic review tools (Covidence, DistillerSR, etc.)
agent.export_to_csv(
    extractions=extractions,
    output_file="pico_extractions.csv"
)
```

CSV columns:
- `document_id`, `document_title`, `pmid`, `doi`
- `study_type`, `sample_size`
- `population`, `intervention`, `comparison`, `outcome`
- `population_confidence`, `intervention_confidence`, `comparison_confidence`, `outcome_confidence`
- `extraction_confidence`, `created_at`

### Extraction Statistics

Monitor extraction performance:

```python
# Get statistics
stats = agent.get_extraction_stats()

print(f"Total extractions: {stats['total_extractions']}")
print(f"Successful: {stats['successful_extractions']}")
print(f"Failed: {stats['failed_extractions']}")
print(f"Low confidence: {stats['low_confidence_extractions']}")
print(f"Parse failures: {stats['parse_failures']}")
print(f"Success rate: {stats['success_rate']:.1%}")
```

## Advanced Usage

### Integration with BMLibrarian Workflow

Combine PICO extraction with document search:

```python
from bmlibrarian.agents import QueryAgent, PICOAgent
from bmlibrarian.database import get_db_manager

# Step 1: Search for relevant documents
query_agent = QueryAgent()
pico_agent = PICOAgent()

research_question = "What are the effects of metformin on type 2 diabetes?"
documents = query_agent.search_documents(research_question, max_results=50)

# Step 2: Extract PICO from all documents
extractions = pico_agent.extract_pico_batch(
    documents=documents,
    min_confidence=0.6
)

# Step 3: Filter by study type
rcts = [e for e in extractions if e.study_type and 'RCT' in e.study_type.upper()]
print(f"Found {len(rcts)} randomized controlled trials")

# Step 4: Export for systematic review
pico_agent.export_to_csv(rcts, "metformin_rcts_pico.csv")
```

### Filtering and Analysis

```python
# Filter by confidence thresholds
high_confidence = [
    e for e in extractions
    if e.extraction_confidence >= 0.8
]

# Filter by specific interventions
drug_trials = [
    e for e in extractions
    if 'metformin' in e.intervention.lower()
]

# Group by study type
from collections import Counter
study_types = Counter(e.study_type for e in extractions if e.study_type)
print("Study type distribution:", dict(study_types))

# Analyze population characteristics
populations_with_diabetes = [
    e for e in extractions
    if 'diabetes' in e.population.lower()
]
```

### Handling Edge Cases

#### Documents Without Full Text

The agent works with abstracts alone:

```python
# Document with only abstract (no full_text field)
abstract_only_doc = {
    'id': '123',
    'title': 'Study Title',
    'abstract': 'Study abstract...'
}

extraction = agent.extract_pico_from_document(abstract_only_doc)
```

#### Documents With Full Text

The agent prefers full text when available:

```python
# Document with both abstract and full text
full_text_doc = {
    'id': '123',
    'title': 'Study Title',
    'abstract': 'Brief abstract...',
    'full_text': 'Complete methods and results section...'
}

# Agent will use full_text for richer extraction
extraction = agent.extract_pico_from_document(full_text_doc)
```

#### Confidence Thresholds

Adjust confidence thresholds based on your needs:

```python
# High confidence (systematic reviews, meta-analyses)
extraction = agent.extract_pico_from_document(doc, min_confidence=0.8)

# Medium confidence (general screening)
extraction = agent.extract_pico_from_document(doc, min_confidence=0.6)

# Low confidence (exploratory analysis, include uncertain cases)
extraction = agent.extract_pico_from_document(doc, min_confidence=0.3)
```

## Best Practices

### 1. Choose Appropriate Confidence Thresholds

- **High confidence (0.8-1.0)**: Use for systematic reviews and meta-analyses where accuracy is critical
- **Medium confidence (0.5-0.7)**: Use for general screening and exploratory analysis
- **Low confidence (0.3-0.5)**: Use when you need comprehensive coverage and will manually verify results

### 2. Use Full Text When Available

Full text provides richer context than abstracts alone. Extract full text from PDFs when possible for better PICO extraction accuracy.

### 3. Batch Process for Efficiency

Process multiple documents in batches rather than individually:

```python
# Good: Batch processing
extractions = agent.extract_pico_batch(documents)

# Less efficient: Individual processing
extractions = [agent.extract_pico_from_document(doc) for doc in documents]
```

### 4. Monitor Extraction Statistics

Regularly check statistics to ensure quality:

```python
stats = agent.get_extraction_stats()
if stats['success_rate'] < 0.7:
    print("Warning: Success rate below 70%, consider adjusting confidence threshold")
```

### 5. Verify Critical Extractions

For systematic reviews, always manually verify PICO extractions, especially:
- High-impact papers
- Studies with conflicting results
- Extractions with confidence < 0.8

### 6. Use Appropriate Models

- **gpt-oss:20b** (default): Best accuracy for complex medical papers
- **medgemma-27b**: Good balance of speed and accuracy
- **medgemma4B**: Faster but less accurate (use for initial screening only)

## Troubleshooting

### Low Success Rate

**Problem**: Many extractions failing or returning low confidence

**Solutions**:
1. Lower the `min_confidence` threshold
2. Use a larger model (gpt-oss:20b instead of smaller models)
3. Increase `max_retries` for problematic documents
4. Check that documents have complete abstracts or full text

### Incomplete PICO Components

**Problem**: Some PICO fields show "Not clearly stated"

**Explanation**: This is expected behavior when information is genuinely missing from the paper. The agent will not fabricate information.

**Solutions**:
1. Review the original paper manually
2. Extract from full text instead of abstract
3. Accept that some papers don't report all PICO components

### Parse Failures

**Problem**: JSON parsing errors in extraction

**Solutions**:
1. Increase `max_retries` in configuration
2. Check Ollama server connectivity
3. Ensure the model is properly loaded
4. Review Ollama logs for errors

### Slow Processing

**Problem**: Batch processing takes too long

**Solutions**:
1. Use a smaller/faster model for initial screening
2. Process in smaller batches
3. Run on a machine with better GPU resources
4. Filter documents before PICO extraction (e.g., by study type in metadata)

## Use Cases

### Systematic Review Workflow

```python
# 1. Search for studies
documents = query_agent.search_documents(
    "metformin AND type 2 diabetes",
    max_results=500
)

# 2. Extract PICO components
extractions = agent.extract_pico_batch(documents, min_confidence=0.7)

# 3. Filter by study design
rcts = [e for e in extractions if e.study_type and 'RCT' in e.study_type.upper()]

# 4. Export for review
agent.export_to_csv(rcts, "systematic_review_pico.csv")

# 5. Manual verification in Excel/systematic review software
print(f"Exported {len(rcts)} RCTs for manual review")
```

### Research Gap Analysis

```python
# Find understudied populations
all_populations = [e.population.lower() for e in extractions]

# Check for elderly populations
elderly_studies = sum(1 for p in all_populations if 'elderly' in p or 'older adults' in p)
print(f"Studies including elderly: {elderly_studies}/{len(extractions)}")

# Check for pediatric populations
pediatric_studies = sum(1 for p in all_populations if 'child' in p or 'pediatric' in p)
print(f"Studies including children: {pediatric_studies}/{len(extractions)}")
```

### Comparative Effectiveness Analysis

```python
# Compare different interventions for the same outcome
diabetes_interventions = [
    e for e in extractions
    if 'diabetes' in e.population.lower()
    and 'hba1c' in e.outcome.lower()
]

# Group by intervention
from collections import defaultdict
by_intervention = defaultdict(list)
for e in diabetes_interventions:
    intervention = e.intervention.split()[0]  # First word (e.g., "Metformin")
    by_intervention[intervention].append(e)

# Report
for drug, studies in by_intervention.items():
    print(f"{drug}: {len(studies)} studies")
```

## API Reference

See [Developer Documentation](../developers/pico_agent.md) for detailed API reference.

## Related Documentation

- [CitationFinderAgent Guide](citation_guide.md) - Extract citations from papers
- [QueryAgent Guide](query_agent_guide.md) - Search for relevant papers
- [ReportingAgent Guide](reporting_guide.md) - Generate synthesis reports

## Support

For issues or questions:
- Review troubleshooting section above
- Check [GitHub Issues](https://github.com/hherb/bmlibrarian/issues)
- Consult BMLibrarian documentation: `doc/`
