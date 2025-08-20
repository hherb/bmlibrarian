# Reporting Agent Guide

This guide explains how to use BMLibrarian's Reporting Agent to create professional medical publication-style reports from extracted citations.

## What is the Reporting Agent?

The Reporting Agent takes citations extracted by the Citation Finder and synthesizes them into cohesive, evidence-based reports formatted like peer-reviewed medical publications. It automatically creates proper reference lists, assesses evidence strength, and writes in professional medical style.

**Key Benefits:**
- ✅ **Professional Format**: Medical publication-style writing with proper citations
- ✅ **Vancouver References**: Industry-standard reference formatting
- ✅ **Evidence Assessment**: Automatic evaluation of evidence strength
- ✅ **Quality Control**: Validates citations and detects issues
- ✅ **Complete Reports**: Includes methodology notes and metadata

## How It Works

```
Citations → Validation → Reference Creation → Evidence Assessment → LLM Synthesis → Formatted Report
```

1. **Input**: Takes citations from Citation Finder Agent
2. **Validation**: Checks citation quality and completeness
3. **References**: Creates numbered reference list with Vancouver formatting
4. **Assessment**: Evaluates evidence strength (Strong/Moderate/Limited/Insufficient)
5. **Synthesis**: Uses AI to write cohesive medical publication-style content
6. **Output**: Generates complete formatted report with references

## Basic Usage

### Step 1: Get Citations

First, extract citations using the Citation Finder (see Citation Guide):

```python
from bmlibrarian.agents import CitationFinderAgent, ReportingAgent

# Extract citations from your research question
citation_agent = CitationFinderAgent()
citations = citation_agent.process_scored_documents_for_citations(
    user_question="What are the cardiovascular benefits of exercise?",
    scored_documents=scored_docs,
    score_threshold=2.5
)

print(f"Found {len(citations)} citations for report generation")
```

### Step 2: Generate Report

Create a professional medical report from the citations:

```python
# Initialize reporting agent
reporting_agent = ReportingAgent()

# Generate formatted report
report = reporting_agent.generate_citation_based_report(
    user_question="What are the cardiovascular benefits of exercise?",
    citations=citations,
    format_output=True
)

if report:
    print(report)
else:
    print("❌ Could not generate report - check citations and connection")
```

### Step 3: Review and Use

The generated report includes:

- **Research Question**: Your original question
- **Evidence Strength**: Assessment of evidence quality
- **Synthesized Answer**: Professional medical writing with numbered citations [1], [2], [3]
- **References**: Vancouver-style reference list
- **Methodology**: Description of synthesis approach
- **Metadata**: Generation details and statistics

## Understanding Report Output

### Complete Report Structure

```
Research Question: What are the cardiovascular benefits of exercise?
================================================================================

Evidence Strength: Moderate

Regular aerobic exercise provides significant cardiovascular benefits, including 
improved coronary blood flow and reduced risk of major adverse cardiovascular 
events [1]. Studies demonstrate exercise reduces systolic blood pressure by 
4-9 mmHg and improves lipid profiles with HDL cholesterol increases of 5-10% [2]. 
Meta-analyses indicate 30 minutes of moderate exercise 5 days per week reduces 
cardiovascular mortality by approximately 30% [3].

REFERENCES
--------------------

1. Smith, J., Johnson, A., Brown, K.. Exercise and Coronary Blood Flow Study. 2023; PMID: 37123456
2. Davis, M., Wilson, R., Garcia, L.. Blood Pressure Response to Exercise Training. 2023; PMID: 37234567
3. Miller, P., Anderson, S., Taylor, D., et al.. Exercise and Cardiovascular Mortality Meta-Analysis. 2023; PMID: 37345678

METHODOLOGY
--------------------
Synthesis based on 3 high-quality citations from peer-reviewed studies with 
relevance scores ≥0.80. Evidence strength assessed considering citation quantity, 
source diversity, and methodological rigor.

REPORT METADATA
--------------------
Generated: 2023-06-15 14:25:30 UTC
Citations analyzed: 3
Unique references: 3
Evidence strength: Moderate
```

### Evidence Strength Levels

**Strong Evidence:**
- ≥5 citations from ≥3 different sources
- High relevance scores (≥0.85 average)
- Comprehensive coverage of the research question

**Moderate Evidence:**
- 3-4 citations from ≥2 different sources  
- Good relevance scores (≥0.75 average)
- Adequate coverage with minor gaps

**Limited Evidence:**
- 2-3 citations with decent relevance (≥0.70 average)
- May have significant evidence gaps
- Conclusions should be interpreted cautiously

**Insufficient Evidence:**
- <2 citations or very low relevance scores
- Report generation may fail or produce low-quality output

## Configuration Options

### Quality Thresholds

Control report generation standards:

```python
# Generate report with custom minimum citation requirement
report = reporting_agent.synthesize_report(
    user_question=question,
    citations=citations,
    min_citations=3  # Require at least 3 citations (default: 2)
)
```

### Model Selection

Choose appropriate AI model for synthesis:

```python
# For high-quality medical writing (default)
reporting_agent = ReportingAgent(model="gpt-oss:20b")

# For faster processing
reporting_agent = ReportingAgent(model="medgemma4B_it_q8:latest")
```

### Output Formatting

Choose between formatted and unformatted output:

```python
# Full formatted report with references and metadata
formatted_report = reporting_agent.generate_citation_based_report(
    user_question=question,
    citations=citations,
    format_output=True  # Default
)

# Just the synthesized content without formatting
synthesis_only = reporting_agent.generate_citation_based_report(
    user_question=question, 
    citations=citations,
    format_output=False
)
```

## Quality Control

### Validating Citations

Always validate citations before report generation:

```python
# Check citation quality
valid_citations, errors = reporting_agent.validate_citations(citations)

if errors:
    print("⚠️  Citation Issues Found:")
    for error in errors:
        print(f"   - {error}")

if len(valid_citations) >= 2:
    print(f"✅ {len(valid_citations)} valid citations ready for reporting")
    # Proceed with report generation
else:
    print("❌ Insufficient valid citations for report generation")
```

### Assessing Evidence Quality

Check evidence strength before interpreting results:

```python
# Assess evidence strength
strength = reporting_agent.assess_evidence_strength(citations)
print(f"Evidence Strength: {strength}")

# Adjust interpretation based on strength
if strength == "Strong":
    print("✅ High confidence in findings")
elif strength == "Moderate": 
    print("⚠️  Moderate confidence - consider additional sources")
elif strength == "Limited":
    print("⚠️  Limited evidence - interpret cautiously")
else:
    print("❌ Insufficient evidence - additional research needed")
```

### Manual Reference Review

For critical research, review key references:

```python
# Create and review references
references = reporting_agent.create_references(citations)

print("📋 References for Manual Review:")
for ref in references:
    vancouver_formatted = ref.format_vancouver_style()
    print(f"{ref.number}. {vancouver_formatted}")
    print(f"   Document ID: {ref.document_id}")
    if ref.pmid:
        print(f"   PubMed: https://pubmed.ncbi.nlm.nih.gov/{ref.pmid}")
    print()
```

## Example Workflows

### Drug Safety Report

```python
question = "What are the safety concerns with long-term metformin use?"

# Get high-quality citations focused on safety
citations = citation_agent.process_scored_documents_for_citations(
    user_question=question,
    scored_documents=safety_focused_docs,
    score_threshold=3.0,  # High threshold for safety data
    min_relevance=0.8     # High relevance requirement
)

# Validate citations
valid_citations, errors = reporting_agent.validate_citations(citations)

if len(valid_citations) >= 3:
    # Generate comprehensive safety report
    report = reporting_agent.generate_citation_based_report(
        user_question=question,
        citations=valid_citations,
        format_output=True
    )
    
    # Save report
    with open('metformin_safety_report.txt', 'w') as f:
        f.write(report)
    
    print("✅ Safety report generated and saved")
else:
    print("❌ Insufficient evidence for comprehensive safety assessment")
```

### Treatment Effectiveness Review

```python
question = "How effective is cognitive behavioral therapy for depression?"

# Process citations with moderate thresholds for broad coverage
citations = citation_agent.process_scored_documents_for_citations(
    user_question=question,
    scored_documents=treatment_docs,
    score_threshold=2.5,
    min_relevance=0.75
)

# Generate report with custom synthesis
report_obj = reporting_agent.synthesize_report(
    user_question=question,
    citations=citations,
    min_citations=4  # Require substantial evidence
)

if report_obj:
    print(f"Evidence Assessment: {report_obj.evidence_strength}")
    print(f"Based on {report_obj.citation_count} citations from {report_obj.unique_documents} studies")
    
    # Format for display
    formatted = reporting_agent.format_report_output(report_obj)
    print(formatted)
    
    # Extract just the synthesis for other uses
    clinical_summary = report_obj.synthesized_answer
    print(f"\nClinical Summary:\n{clinical_summary}")
```

### Comparative Analysis

```python
questions = [
    "What is the effectiveness of aspirin for cardiovascular prevention?",
    "What are the bleeding risks associated with aspirin use?",
    "How do benefits and risks of aspirin compare?"
]

reports = []
for question in questions:
    # Get relevant citations for each question
    citations = get_citations_for_question(question)  # Your citation extraction
    
    # Generate focused report
    report = reporting_agent.generate_citation_based_report(
        user_question=question,
        citations=citations,
        format_output=False  # Just get synthesis content
    )
    
    if report:
        reports.append({
            'question': question,
            'content': report,
            'citations': len(citations)
        })

# Combine into comparative analysis
print("Aspirin Risk-Benefit Analysis")
print("=" * 50)
for report in reports:
    print(f"\n{report['question']}")
    print("-" * 40)
    print(report['content'])
    print(f"(Based on {report['citations']} citations)")
```

## Best Practices

### 1. Ensure Citation Quality

Start with high-quality citations for better reports:

```python
# Before generating reports, check citation statistics
from bmlibrarian.agents.citation_agent import CitationFinderAgent

citation_stats = citation_agent.get_citation_stats(citations)

print(f"📊 Citation Quality Check:")
print(f"   Average relevance: {citation_stats['average_relevance']:.3f}")
print(f"   Unique sources: {citation_stats['unique_documents']}")
print(f"   Total citations: {citation_stats['total_citations']}")

# Recommend thresholds based on stats
if citation_stats['average_relevance'] < 0.75:
    print("⚠️  Consider using higher relevance threshold in citation extraction")
if citation_stats['unique_documents'] < 3:
    print("⚠️  Limited source diversity - consider broader search terms")
```

### 2. Match Model to Use Case

Select appropriate models for different scenarios:

```python
# For high-stakes medical reports (slower but higher quality)
clinical_reporting_agent = ReportingAgent(model="gpt-oss:20b")

# For rapid literature screening (faster but adequate quality)
screening_reporting_agent = ReportingAgent(model="medgemma4B_it_q8:latest")

# For development and testing
test_reporting_agent = ReportingAgent(model="test-model")
```

### 3. Validate Critical Information

For important decisions, manually verify key claims:

```python
report = reporting_agent.generate_citation_based_report(question, citations)

if report and "clinical trial" in report.lower():
    print("🔍 Clinical trial data detected - recommend manual verification")
    
    # Extract cited documents for review
    references = reporting_agent.create_references(citations)
    high_impact_refs = [ref for ref in references if ref.pmid]
    
    print("High-priority references for verification:")
    for ref in high_impact_refs:
        print(f"   PMID {ref.pmid}: {ref.title}")
```

### 4. Handle Insufficient Evidence

Manage cases with limited evidence appropriately:

```python
report_obj = reporting_agent.synthesize_report(question, citations)

if not report_obj:
    print("❌ Insufficient evidence for report generation")
    print("Recommendations:")
    print("   - Lower score thresholds in citation extraction")
    print("   - Broaden search terms") 
    print("   - Consider splitting complex questions")
    print("   - Check database coverage for your topic")
elif report_obj.evidence_strength == "Limited":
    print(f"⚠️  Limited evidence report generated")
    print(f"   Based on only {report_obj.citation_count} citations")
    print(f"   Consider as preliminary findings only")
elif report_obj.evidence_strength == "Insufficient":
    print(f"⚠️  Very low evidence quality")
    print(f"   Report may not be reliable for decision-making")
```

## Troubleshooting

### Common Issues

**"No report generated"**
- Check if you have at least 2 valid citations
- Verify Ollama service is running: `curl http://localhost:11434/api/tags`
- Run citation validation: `validate_citations(citations)`
- Try lowering `min_citations` parameter

**"Poor quality synthesis"**
- Improve citation quality (higher relevance scores)
- Use more citations (aim for ≥3)
- Check citation passage content for relevance
- Consider using a higher-quality model

**"References look wrong"**
- Check original citation author lists and titles
- Verify publication dates are properly formatted
- Ensure document IDs are from database
- Test Vancouver formatting: `reference.format_vancouver_style()`

**"Evidence strength seems incorrect"**
- Review citation relevance scores
- Check number of unique source documents
- Verify citation count meets thresholds
- Consider evidence assessment criteria

### Performance Issues

**"Report generation is slow"**
- Use faster model: `medgemma4B_it_q8:latest`
- Reduce citation count if possible
- Check Ollama model is downloaded locally
- Monitor system resources during generation

**"Running out of memory"**
- Process smaller batches of citations
- Use lighter AI models
- Check citation content length
- Restart Ollama service if needed

### Connection Problems

**"Cannot connect to Ollama"**
```bash
# Check Ollama status
curl http://localhost:11434/api/tags

# If not running, start Ollama
ollama serve

# Check available models
ollama list

# Download required model if missing
ollama pull gpt-oss:20b
```

**"Model not found"**
```python
# Test connection and model availability
if reporting_agent.test_connection():
    print("✅ Ollama connected")
else:
    print("❌ Ollama connection failed")
    print("   Check: ollama serve")
    print("   Check: ollama pull gpt-oss:20b")
```

## Advanced Usage

### Custom Report Processing

```python
# Get structured report object for custom processing
report_obj = reporting_agent.synthesize_report(question, citations)

if report_obj:
    # Extract components for custom formatting
    synthesis = report_obj.synthesized_answer
    references = report_obj.references
    evidence = report_obj.evidence_strength
    
    # Custom output format
    print(f"CLINICAL SUMMARY")
    print(f"Question: {report_obj.user_question}")
    print(f"Evidence Level: {evidence}")
    print(f"Summary: {synthesis}")
    
    # Export references in custom format
    print(f"\nSOURCES ({len(references)} references):")
    for ref in references:
        print(f"[{ref.number}] {ref.title} ({ref.publication_date[:4]})")
        if ref.pmid:
            print(f"    PubMed: {ref.pmid}")
```

### Export Integration

```python
# Export report data for external systems
report_data = {
    'question': report_obj.user_question,
    'synthesis': report_obj.synthesized_answer,
    'evidence_strength': report_obj.evidence_strength,
    'generation_date': report_obj.created_at.isoformat(),
    'references': [
        {
            'number': ref.number,
            'title': ref.title,
            'authors': ref.authors,
            'date': ref.publication_date,
            'pmid': ref.pmid,
            'vancouver': ref.format_vancouver_style()
        }
        for ref in report_obj.references
    ]
}

# Save as JSON
import json
with open('report_export.json', 'w') as f:
    json.dump(report_data, f, indent=2)
```

### Batch Report Generation

```python
# Generate multiple reports efficiently
questions_and_citations = [
    ("Question 1", citations_1),
    ("Question 2", citations_2),
    ("Question 3", citations_3)
]

reports = []
for question, citations in questions_and_citations:
    print(f"Generating report for: {question[:50]}...")
    
    report = reporting_agent.generate_citation_based_report(
        user_question=question,
        citations=citations,
        format_output=False
    )
    
    if report:
        reports.append({
            'question': question,
            'content': report,
            'timestamp': datetime.now().isoformat()
        })
    
print(f"Generated {len(reports)} reports")
```

## Getting Help

For additional support:

1. **Test Connection**: Use `reporting_agent.test_connection()` to verify Ollama
2. **Validate Citations**: Run `validate_citations()` to check input quality  
3. **Check Logs**: Review error messages for specific issues
4. **Try Demo**: Run `python examples/reporting_demo.py` for examples
5. **Review Documentation**: See developer docs for technical details

The Reporting Agent transforms citations into professional medical publication-style reports, providing the evidence-based synthesis needed for informed decision-making in biomedical research and clinical practice.