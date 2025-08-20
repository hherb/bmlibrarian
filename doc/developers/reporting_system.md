# Reporting Agent System

This document describes the BMLibrarian Reporting Agent system for synthesizing citations into cohesive medical publication-style reports with proper reference formatting.

## Overview

The Reporting Agent takes output from the Citation Finder Agent and synthesizes extracted citations into evidence-based reports formatted in the style of peer-reviewed medical publications. It provides proper reference numbering, Vancouver-style citations, and evidence strength assessment.

## Architecture

### Core Components

1. **ReportingAgent**: Main agent class for report synthesis
2. **Reference**: Data structure for formatted references with Vancouver-style output
3. **Report**: Complete report structure with synthesized content and metadata
4. **Evidence Assessment**: Automatic evaluation of evidence strength

### Report Generation Workflow

```
Citations → Reference Creation → Evidence Assessment → LLM Synthesis → Formatting → Report Output
```

1. **Input Processing**: Validate and process citations from CitationFinderAgent
2. **Reference Generation**: Create numbered references with deduplication
3. **Evidence Assessment**: Evaluate evidence strength (Strong/Moderate/Limited/Insufficient)
4. **Synthesis**: Use LLM to create cohesive medical publication-style content
5. **Formatting**: Apply medical publication formatting with proper citations
6. **Output**: Generate complete report with references and metadata

## Data Structures

### Reference Class

```python
@dataclass
class Reference:
    number: int                    # Sequential reference number
    authors: List[str]             # Author list
    title: str                     # Document title
    publication_date: str          # Publication date
    document_id: str               # Verified database document ID
    pmid: Optional[str] = None     # PubMed ID if available
    
    def format_vancouver_style(self) -> str:
        """Format reference in Vancouver style for medical publications."""
```

### Report Class

```python
@dataclass
class Report:
    user_question: str             # Original research question
    synthesized_answer: str        # LLM-synthesized answer with citations
    references: List[Reference]    # Numbered reference list
    evidence_strength: str         # "Strong", "Moderate", "Limited", "Insufficient"
    methodology_note: str          # Synthesis methodology description
    created_at: datetime           # Report generation timestamp
    citation_count: int            # Number of citations analyzed
    unique_documents: int          # Number of unique source documents
```

## Key Features

### 1. Vancouver-Style Reference Formatting

Automatically formats references according to Vancouver style used in medical journals:

```python
# Example Vancouver formatting
reference = Reference(
    number=1,
    authors=["Smith, J.", "Johnson, A.", "Brown, K."],
    title="COVID-19 Vaccine Effectiveness Study",
    publication_date="2023-01-15",
    pmid="37123456"
)

formatted = reference.format_vancouver_style()
# Output: "Smith, J., Johnson, A., Brown, K.. COVID-19 Vaccine Effectiveness Study. 2023; PMID: 37123456"
```

**Features:**
- Author list handling (max 6 authors, then "et al.")
- Automatic year extraction from dates
- PMID inclusion when available
- Consistent formatting across references

### 2. Evidence Strength Assessment

Automatic assessment based on citation quality and quantity:

```python
def assess_evidence_strength(self, citations: List[Citation]) -> str:
    """Assess evidence strength: Strong/Moderate/Limited/Insufficient"""
```

**Assessment Criteria:**
- **Strong**: ≥5 citations, ≥3 unique docs, avg relevance ≥0.85
- **Moderate**: ≥3 citations, ≥2 unique docs, avg relevance ≥0.75  
- **Limited**: ≥2 citations, avg relevance ≥0.70
- **Insufficient**: <2 citations or low relevance scores

### 3. Medical Publication Style Synthesis

Uses structured prompts to generate publication-quality content:

```python
prompt = f"""You are a medical writing expert tasked with synthesizing research citations 
into a cohesive, evidence-based answer in the style of a peer-reviewed medical publication.

Guidelines:
- Use formal medical writing style appropriate for peer-reviewed publications
- Include in-text citations using numbered references [1], [2], etc.
- Be objective and present limitations where evidence is incomplete
- Structure response with clear paragraphs and logical flow
- Use medical terminology appropriately"""
```

### 4. Reference Deduplication

Automatically handles duplicate document citations:

```python
def create_references(self, citations: List[Citation]) -> List[Reference]:
    """Create numbered references with automatic deduplication."""
```

**Features:**
- Single reference per unique document ID
- Sequential numbering (1, 2, 3...)
- Maintains citation mapping for in-text references

## API Reference

### ReportingAgent Methods

#### Core Report Generation

```python
def synthesize_report(self, user_question: str, citations: List[Citation],
                     min_citations: int = 2) -> Optional[Report]
```
Generate complete report from citations with evidence assessment.

#### Reference Management

```python
def create_references(self, citations: List[Citation]) -> List[Reference]
```
Create numbered references from citations with deduplication.

```python
def map_citations_to_references(self, citations: List[Citation], 
                               references: List[Reference]) -> Dict[str, int]
```
Create mapping from document IDs to reference numbers for in-text citations.

#### Output Formatting

```python
def format_report_output(self, report: Report) -> str
```
Format complete report for display with references and metadata.

```python
def generate_citation_based_report(self, user_question: str, citations: List[Citation],
                                 format_output: bool = True) -> Optional[str]
```
Complete workflow: synthesize and optionally format report.

#### Quality Control

```python
def validate_citations(self, citations: List[Citation]) -> Tuple[List[Citation], List[str]]
```
Validate citations and return valid ones with error messages.

```python
def assess_evidence_strength(self, citations: List[Citation]) -> str
```
Evaluate evidence strength based on citation quality and quantity.

## Usage Examples

### Basic Report Generation

```python
from bmlibrarian.agents import ReportingAgent, CitationFinderAgent

# Initialize agents
citation_agent = CitationFinderAgent(orchestrator=orchestrator)
reporting_agent = ReportingAgent(orchestrator=orchestrator)

# Extract citations (from previous workflow)
citations = citation_agent.process_scored_documents_for_citations(
    user_question="What are the cardiovascular benefits of exercise?",
    scored_documents=scored_docs,
    score_threshold=2.5
)

# Generate report
formatted_report = reporting_agent.generate_citation_based_report(
    user_question="What are the cardiovascular benefits of exercise?",
    citations=citations,
    format_output=True
)

print(formatted_report)
```

### Advanced Report Generation with Validation

```python
# Validate citations before processing
valid_citations, errors = reporting_agent.validate_citations(citations)

if errors:
    print(f"⚠️  Citation validation errors: {errors}")

if len(valid_citations) >= 3:
    # Generate structured report object
    report = reporting_agent.synthesize_report(
        user_question=question,
        citations=valid_citations,
        min_citations=3
    )
    
    if report:
        print(f"Evidence Strength: {report.evidence_strength}")
        print(f"Citations: {report.citation_count}")
        print(f"Unique Sources: {report.unique_documents}")
        
        # Format for display
        formatted = reporting_agent.format_report_output(report)
        print(formatted)
    else:
        print("❌ Report synthesis failed")
else:
    print("❌ Insufficient citations for report generation")
```

### Custom Report Processing

```python
# Extract just the synthesized content without formatting
synthesized_content = reporting_agent.generate_citation_based_report(
    user_question=question,
    citations=citations,
    format_output=False  # Returns only synthesized text
)

# Create custom references
references = reporting_agent.create_references(citations)
for ref in references:
    vancouver_formatted = ref.format_vancouver_style()
    print(f"{ref.number}. {vancouver_formatted}")

# Assess evidence quality
strength = reporting_agent.assess_evidence_strength(citations)
print(f"Evidence Assessment: {strength}")
```

## Report Output Format

### Complete Formatted Report Structure

```
Research Question: [Original user question]
================================================================================

Evidence Strength: [Strong/Moderate/Limited/Insufficient]

[Synthesized answer with numbered in-text citations [1], [2], [3]...]

REFERENCES
--------------------

1. [Vancouver-formatted reference]
2. [Vancouver-formatted reference]
3. [Vancouver-formatted reference]
...

METHODOLOGY
--------------------
[Description of synthesis methodology and limitations]

REPORT METADATA
--------------------
Generated: 2023-06-15 12:30:45 UTC
Citations analyzed: 5
Unique references: 4
Evidence strength: Moderate
```

### Example Output

```
Research Question: What is the effectiveness of aspirin for cardiovascular prevention?
================================================================================

Evidence Strength: Moderate

Aspirin demonstrates significant efficacy for primary prevention of cardiovascular 
disease, with meta-analyses showing a 22% reduction in major cardiovascular events 
(95% CI: 18-26%) [1]. However, this benefit must be balanced against bleeding risks, 
as aspirin use increases major bleeding events by approximately 50% (RR 1.5, 95% CI 
1.2-1.9), occurring in 0.3% of users versus 0.2% of controls [2]. Risk-benefit 
analyses support aspirin use in patients with 10-year cardiovascular risk exceeding 
10%, where the cardiovascular benefits outweigh bleeding risks [3].

REFERENCES
--------------------

1. Johnson, M., Smith, R., Davis, L.. Aspirin for Primary Prevention of Cardiovascular Disease: Meta-Analysis. 2023; PMID: 37654321
2. Taylor, K., Brown, P., Wilson, J., Garcia, M., Anderson, S., White, T., et al.. Bleeding Risks Associated with Low-Dose Aspirin: Systematic Review. 2023; PMID: 37543210
3. Miller, A., Thompson, D.. Risk-Benefit Assessment of Aspirin for Primary Prevention. 2023; PMID: 37432109

METHODOLOGY
--------------------
Synthesis based on 3 high-quality citations from peer-reviewed studies with 
relevance scores ≥0.87. Evidence assessment considered citation quantity, 
source diversity, and methodological quality.

REPORT METADATA
--------------------
Generated: 2023-06-15 14:25:30 UTC
Citations analyzed: 3
Unique references: 3
Evidence strength: Moderate
```

## Configuration

### Agent Initialization

```python
reporting_agent = ReportingAgent(
    orchestrator=orchestrator,           # Optional: for future queue integration
    ollama_url="http://localhost:11434", # Ollama service URL
    model="gpt-oss:20b"                 # LLM model for synthesis (default)
)
```

### Model Selection

**Recommended Models:**
- **gpt-oss:20b**: Default, balanced quality and speed for medical writing
- **medgemma4B_it_q8:latest**: Faster processing for large-scale report generation
- **Custom models**: Any Ollama-compatible model with strong reasoning capabilities

### Synthesis Parameters

```python
# In agent initialization
self.temperature = 0.3  # Higher temperature for more natural medical writing

# In synthesis method
min_citations = 2       # Minimum citations required for report generation
```

## Quality Control

### Citation Validation

Reports undergo comprehensive validation:

```python
def validate_citations(self, citations: List[Citation]) -> Tuple[List[Citation], List[str]]:
    """Validate citations for completeness and accuracy."""
```

**Validation Checks:**
- **Passage Content**: Non-empty relevant passages
- **Document IDs**: Valid database document identifiers
- **Titles**: Complete document titles
- **Relevance Scores**: Valid range (0.0-1.0)
- **Required Fields**: All mandatory citation fields present

### Evidence Assessment

Multi-factor evidence evaluation:

1. **Quantity Metrics**: Number of citations and unique sources
2. **Quality Metrics**: Average relevance scores and score distribution  
3. **Source Diversity**: Variety of contributing documents
4. **Methodological Quality**: Assessment based on citation metadata

### Reference Integrity

Ensures reference accuracy:

- **Deduplication**: One reference per unique document
- **Sequential Numbering**: Proper 1, 2, 3... ordering
- **Format Consistency**: Standardized Vancouver formatting
- **Database Verification**: All references link to verified documents

## Performance Considerations

### Scaling Factors

Report generation time depends on:

- **Citation Count**: Linear scaling with number of citations
- **Content Length**: Longer citations require more processing
- **Model Performance**: Larger models provide better quality but slower generation
- **Network Latency**: Local Ollama faster than remote services

### Optimization Strategies

1. **Citation Pre-filtering**: Remove low-quality citations before synthesis
2. **Model Selection**: Use faster models for bulk report generation
3. **Batch Processing**: Generate multiple reports in sequence
4. **Content Caching**: Reuse similar synthesis patterns (not implemented)

### Resource Requirements

**Memory Usage:**
- Base agent: ~50MB
- Per citation: ~1KB
- Report synthesis: ~10-100MB depending on model

**Processing Time:**
- Reference creation: <1s for typical citation sets
- LLM synthesis: 10-60s depending on model and content length
- Formatting: <1s for typical reports

## Integration Points

### Upstream Dependencies

- **CitationFinderAgent**: Provides input citations
- **DocumentScoringAgent**: Indirectly via citation quality
- **PostgreSQL Database**: Document verification and metadata

### Output Consumers  

- **Research Workflows**: Evidence-based research reports
- **Clinical Decision Support**: Medical literature summaries
- **Export Systems**: Formatted reports for external systems
- **Documentation Systems**: Research documentation with proper citations

### Queue System Integration

While not currently implemented, the ReportingAgent is designed for future queue integration:

```python
# Future queue-based report generation
def submit_report_generation_task(self, user_question: str, 
                                citations: List[Citation],
                                priority: TaskPriority = TaskPriority.NORMAL) -> Optional[str]:
    """Submit report generation to processing queue."""
```

## Error Handling

### Common Errors and Solutions

**"Insufficient citations for report generation"**
- Ensure minimum citation count (default: 2)
- Check citation validation results
- Lower min_citations parameter if appropriate

**"Cannot connect to Ollama"**
- Verify Ollama service is running
- Check ollama_url parameter
- Ensure specified model is downloaded

**"Empty synthesis response"**
- Check model availability and performance
- Verify citation content quality
- Review prompt formatting

**"Reference formatting errors"**
- Validate citation author lists
- Check publication date formats
- Ensure document titles are complete

### Robust Error Recovery

```python
try:
    report = reporting_agent.synthesize_report(question, citations)
    if report:
        formatted = reporting_agent.format_report_output(report)
        print(formatted)
    else:
        print("Report synthesis failed - check citations and model availability")
except Exception as e:
    logger.error(f"Report generation error: {e}")
    print(f"Error generating report: {e}")
```

## Future Enhancements

### Planned Improvements

1. **Multi-format Export**: Support APA, MLA, and other citation styles
2. **Template Customization**: User-defined report templates
3. **Quality Metrics**: More sophisticated evidence assessment
4. **Interactive Refinement**: User feedback integration
5. **Batch Processing**: Queue-based report generation

### Advanced Features

1. **Citation Networks**: Visual citation relationship mapping
2. **Evidence Grading**: GRADE-style evidence evaluation
3. **Contradiction Detection**: Identify conflicting findings
4. **Meta-synthesis**: Combine multiple topic reports
5. **Export Integration**: Direct export to reference management systems

## Best Practices

### For High-Quality Reports

1. **Use Sufficient Citations**: Aim for ≥3 citations from diverse sources
2. **Validate Inputs**: Always validate citations before synthesis
3. **Review Evidence Strength**: Consider evidence assessment in interpretation
4. **Check References**: Verify reference formatting and completeness
5. **Consider Limitations**: Note evidence gaps and study limitations

### For Production Use

1. **Monitor Model Performance**: Track synthesis quality over time
2. **Implement Caching**: Cache similar report patterns for efficiency
3. **Error Logging**: Comprehensive error tracking and alerting
4. **Quality Assurance**: Human review for critical reports
5. **Version Control**: Track report generation methodology changes

### For Research Applications

1. **Document Methodology**: Include synthesis approach in methodology sections
2. **Cite Source System**: Reference BMLibrarian in methods when appropriate
3. **Validate Critical Claims**: Manually verify key evidence claims
4. **Consider Bias**: Account for potential database and selection biases
5. **Update Regularly**: Refresh reports as new evidence becomes available

The Reporting Agent provides a robust foundation for generating evidence-based medical reports with proper citation formatting and quality assessment. It integrates seamlessly with the Citation Finder Agent to provide complete literature synthesis capabilities.