# Study Assessment Agent User Guide

## Overview

The StudyAssessmentAgent evaluates biomedical research publications to assess their quality, methodological rigor, and trustworthiness. This agent provides structured assessments that help researchers and clinicians:

- Understand the reliability of evidence
- Make informed decisions about study quality
- Conduct systematic reviews and meta-analyses
- Grade evidence for clinical practice guidelines
- Identify methodological strengths and limitations

## Key Features

- **Study Type Classification**: Identifies research design (RCT, cohort, case-control, meta-analysis, etc.)
- **Design Characteristics**: Detects prospective/retrospective, blinded, randomized, multi-center studies
- **Quality Scoring**: Provides 0-10 quality score based on methodological rigor
- **Bias Risk Assessment**: Evaluates 5 types of bias (selection, performance, detection, attrition, reporting)
- **Evidence Level Grading**: Assigns evidence hierarchy level (Level 1-5)
- **Structured Output**: Returns assessments in JSON format for integration with other tools
- **Batch Processing**: Assess multiple studies efficiently

## Installation and Setup

The StudyAssessmentAgent is included in BMLibrarian's core agents module.

```python
from bmlibrarian.agents import StudyAssessmentAgent, StudyAssessment
```

**Requirements**:
- Ollama server running (default: http://localhost:11434)
- Recommended model: `gpt-oss:20b` (default)
- Python >=3.12

## Basic Usage

### Single Document Assessment

```python
from bmlibrarian.agents import StudyAssessmentAgent

# Initialize agent
agent = StudyAssessmentAgent(
    model="gpt-oss:20b",
    temperature=0.1  # Low temperature for consistent assessments
)

# Prepare document (from your database or file)
document = {
    'id': 12345,
    'title': 'Efficacy of Drug X in Treating Condition Y: A Randomized Trial',
    'abstract': """
    Background: Condition Y affects millions worldwide...
    Methods: We conducted a randomized, double-blind, placebo-controlled trial...
    Results: 150 patients were randomized. Treatment group showed...
    Conclusions: Drug X significantly improved outcomes...
    """,
    'pmid': '98765432',
    'doi': '10.1234/example.2023.001'
}

# Assess study quality
assessment = agent.assess_study(document, min_confidence=0.4)

if assessment:
    print(f"Study Type: {assessment.study_type}")
    print(f"Quality Score: {assessment.quality_score}/10")
    print(f"Evidence Level: {assessment.evidence_level}")
    print(f"Overall Confidence: {assessment.overall_confidence:.2%}")
    print(f"\nStrengths:")
    for strength in assessment.strengths:
        print(f"  - {strength}")
    print(f"\nLimitations:")
    for limitation in assessment.limitations:
        print(f"  - {limitation}")
```

### Display Formatted Assessment

```python
# Get human-readable summary
summary = agent.format_assessment_summary(assessment)
print(summary)
```

**Example Output**:
```
================================================================================
STUDY QUALITY ASSESSMENT: Efficacy of Drug X in Treating Condition Y: A Randomized Trial
================================================================================
Document ID: 12345
PMID: 98765432
DOI: 10.1234/example.2023.001

--- STUDY CLASSIFICATION ---
Study Type: Randomized Controlled Trial (RCT)
Study Design: Prospective, randomized, double-blinded, placebo-controlled
Evidence Level: Level 1 (high)
Sample Size: N=150 patients
Follow-up: 6 months

Characteristics: Prospective, Randomized, Controlled, Double-blinded

--- QUALITY ASSESSMENT ---
Quality Score: 8.5/10
Overall Confidence: 85.00%
Confidence Explanation: High-quality RCT with appropriate randomization, blinding, and adequate sample size

--- STRENGTHS ---
1. Randomized allocation with proper concealment
2. Double-blinding of participants and assessors
3. Adequate sample size with power calculation
4. Low dropout rate (5%)
5. Validated outcome measures

--- LIMITATIONS ---
1. Single-center study limiting generalizability
2. Short follow-up period (6 months)
3. Predominantly white participants (87%)

--- BIAS RISK ASSESSMENT ---
  Selection: low
  Performance: low
  Detection: low
  Attrition: low
  Reporting: moderate

================================================================================
```

### Batch Assessment

```python
# Assess multiple studies
documents = [
    {'id': 1, 'title': 'Study 1', 'abstract': '...'},
    {'id': 2, 'title': 'Study 2', 'abstract': '...'},
    {'id': 3, 'title': 'Study 3', 'abstract': '...'}
]

# Progress callback (optional)
def progress_callback(current, total, doc_title):
    print(f"[{current}/{total}] Assessing: {doc_title}")

# Assess batch
assessments = agent.assess_batch(
    documents=documents,
    min_confidence=0.4,
    progress_callback=progress_callback
)

print(f"\nAssessed {len(assessments)} studies successfully")
```

## Understanding Assessment Fields

### Study Type
Common classifications:
- **Randomized Controlled Trial (RCT)**: Gold standard for intervention studies
- **Cohort study**: Observational follow-up of exposed/unexposed groups
- **Case-control study**: Retrospective comparison of cases and controls
- **Cross-sectional study**: Single time-point observation
- **Case report/series**: Descriptive study of individual patients
- **Meta-analysis**: Statistical synthesis of multiple studies
- **Systematic review**: Comprehensive literature review with methodology

### Quality Score (0-10)
- **9-10**: Exceptional quality, minimal bias risk
- **7-8**: High quality, reliable findings
- **5-6**: Moderate quality, some limitations
- **3-4**: Low quality, significant concerns
- **0-2**: Very poor quality, unreliable

### Evidence Level
Based on Oxford Centre for Evidence-Based Medicine hierarchy:
- **Level 1 (high)**: Systematic reviews of RCTs, high-quality RCTs
- **Level 2 (moderate-high)**: Individual RCTs, systematic reviews of cohorts
- **Level 3 (moderate)**: Cohort studies, case-control studies
- **Level 4 (low-moderate)**: Case series, poor-quality cohort/case-control
- **Level 5 (low)**: Expert opinion, case reports, mechanism-based reasoning

### Bias Risk Categories
- **Selection bias**: Systematic differences between comparison groups
- **Performance bias**: Differences in care/interventions received
- **Detection bias**: Differences in outcome measurement
- **Attrition bias**: Systematic differences in withdrawals/dropouts
- **Reporting bias**: Selective reporting of outcomes

Each rated as: `low`, `moderate`, `high`, or `unclear`

### Overall Confidence (0.0-1.0)
Agent's confidence in the assessment accuracy:
- **0.9-1.0**: Very high confidence, clear methodology description
- **0.7-0.8**: High confidence, most details present
- **0.5-0.6**: Moderate confidence, some ambiguity
- **0.3-0.4**: Low confidence, limited information
- **0.0-0.2**: Very low confidence, unclear or insufficient text

## Exporting Assessments

### Export to JSON

```python
# Export for programmatic use
agent.export_to_json(assessments, 'study_assessments.json')
```

**JSON Structure**:
```json
{
  "assessments": [
    {
      "document_id": "12345",
      "document_title": "...",
      "study_type": "Randomized Controlled Trial (RCT)",
      "study_design": "Prospective, randomized, double-blinded",
      "quality_score": 8.5,
      "overall_confidence": 0.85,
      "evidence_level": "Level 1 (high)",
      "strengths": ["..."],
      "limitations": ["..."],
      "is_randomized": true,
      "is_double_blinded": true,
      "selection_bias_risk": "low",
      ...
    }
  ],
  "metadata": {
    "total_assessments": 50,
    "assessment_date": "2023-10-15T14:30:00Z",
    "agent_model": "gpt-oss:20b",
    "statistics": {
      "success_rate": 0.96
    }
  }
}
```

### Export to CSV

```python
# Export for spreadsheet analysis
agent.export_to_csv(assessments, 'study_assessments.csv')
```

**CSV Columns**:
- document_id, document_title, pmid, doi
- study_type, study_design, evidence_level
- quality_score, overall_confidence
- Design flags (is_randomized, is_blinded, is_multi_center, etc.)
- Bias risk scores
- strengths, limitations (semicolon-separated)

## Analysis and Statistics

### Assessment Statistics

```python
stats = agent.get_assessment_stats()
print(f"Total assessments: {stats['total_assessments']}")
print(f"Successful: {stats['successful_assessments']}")
print(f"Success rate: {stats['success_rate']:.2%}")
print(f"Low confidence: {stats['low_confidence_assessments']}")
print(f"Parse failures: {stats['parse_failures']}")
```

### Quality Distribution

```python
distribution = agent.get_quality_distribution(assessments)
for category, count in distribution.items():
    print(f"{category}: {count} studies")
```

**Example Output**:
```
exceptional (9-10): 5 studies
high (7-8): 23 studies
moderate (5-6): 15 studies
low (3-4): 6 studies
very_low (0-2): 1 studies
```

### Evidence Level Distribution

```python
evidence_dist = agent.get_evidence_level_distribution(assessments)
for level, count in evidence_dist.items():
    print(f"{level}: {count} studies")
```

## Advanced Usage

### Custom Model Configuration

```python
# Use faster model for preliminary screening
agent = StudyAssessmentAgent(
    model="medgemma4B_it_q8:latest",  # Faster, less detailed
    temperature=0.1,
    max_tokens=2000
)

# Use more powerful model for final assessment
agent = StudyAssessmentAgent(
    model="gpt-oss:20b",  # More thorough, slower
    temperature=0.05,  # Even more deterministic
    max_tokens=3000
)
```

### Progress Callbacks

```python
def detailed_progress(current, total, doc_title):
    """Detailed progress reporting"""
    percent = (current / total) * 100
    print(f"[{percent:.1f}%] ({current}/{total}) Assessing: {doc_title[:60]}...")

assessments = agent.assess_batch(
    documents=documents,
    progress_callback=detailed_progress
)
```

### Filtering by Quality

```python
# Get only high-quality studies (score >= 7)
high_quality = [a for a in assessments if a.quality_score >= 7.0]
print(f"High-quality studies: {len(high_quality)}/{len(assessments)}")

# Get only RCTs
rcts = [a for a in assessments if 'RCT' in a.study_type or 'randomized' in a.study_type.lower()]
print(f"RCTs found: {len(rcts)}")

# Get only Level 1 evidence
level1 = [a for a in assessments if 'Level 1' in a.evidence_level]
print(f"Level 1 evidence: {len(level1)}")
```

## Use Cases

### 1. Systematic Review Screening

```python
# Screen studies for inclusion in systematic review
def meets_quality_criteria(assessment):
    """Check if study meets minimum quality standards"""
    return (
        assessment.quality_score >= 6.0 and
        assessment.overall_confidence >= 0.6 and
        'Level 1' in assessment.evidence_level or 'Level 2' in assessment.evidence_level
    )

eligible_studies = [a for a in assessments if meets_quality_criteria(a)]
print(f"Eligible for systematic review: {len(eligible_studies)}/{len(assessments)}")
```

### 2. Evidence Grading for Guidelines

```python
# Grade evidence for clinical practice guidelines
def grade_evidence(assessment):
    """Assign GRADE quality rating"""
    if assessment.quality_score >= 8 and 'Level 1' in assessment.evidence_level:
        return 'HIGH'
    elif assessment.quality_score >= 6 and 'Level 2' in assessment.evidence_level:
        return 'MODERATE'
    elif assessment.quality_score >= 4:
        return 'LOW'
    else:
        return 'VERY LOW'

for assessment in assessments:
    grade = grade_evidence(assessment)
    print(f"{assessment.document_title[:50]}... - GRADE: {grade}")
```

### 3. Identify Studies Needing Replication

```python
# Find studies with high impact but methodological concerns
def needs_replication(assessment):
    """Identify studies that should be replicated"""
    high_bias_count = sum([
        1 for risk in [
            assessment.selection_bias_risk,
            assessment.performance_bias_risk,
            assessment.detection_bias_risk
        ] if risk in ['high', 'moderate']
    ])
    return (
        assessment.quality_score >= 5.0 and  # Interesting but not definitive
        high_bias_count >= 2 and  # Multiple bias concerns
        not assessment.is_multi_center  # Single center
    )

replication_candidates = [a for a in assessments if needs_replication(a)]
print(f"Studies needing replication: {len(replication_candidates)}")
```

## Best Practices

1. **Use Full Text When Available**: Full text provides more complete assessment than abstracts alone
   ```python
   document = {
       'id': 123,
       'title': '...',
       'abstract': '...',
       'full_text': '...'  # Agent will prefer this
   }
   ```

2. **Set Appropriate Confidence Thresholds**: Lower thresholds (0.3-0.4) for screening, higher (0.6-0.7) for final inclusion
   ```python
   # Screening phase
   screening_assessments = agent.assess_batch(documents, min_confidence=0.3)

   # Final assessment
   final_assessments = agent.assess_batch(selected_docs, min_confidence=0.6)
   ```

3. **Verify Critical Assessments**: For high-stakes decisions, manually verify agent assessments
   ```python
   if assessment.quality_score >= 8 and 'Level 1' in assessment.evidence_level:
       print("HIGH-QUALITY STUDY - RECOMMEND MANUAL VERIFICATION")
       print(agent.format_assessment_summary(assessment))
   ```

4. **Track and Report Statistics**: Monitor assessment quality and success rates
   ```python
   stats = agent.get_assessment_stats()
   if stats['success_rate'] < 0.9:
       print(f"WARNING: Success rate {stats['success_rate']:.2%} is below expected")
   ```

5. **Export for Review**: Save assessments for collaborative review and auditing
   ```python
   agent.export_to_json(assessments, f'assessments_{datetime.now().date()}.json')
   agent.export_to_csv(assessments, f'assessments_{datetime.now().date()}.csv')
   ```

## Troubleshooting

### Low Success Rate
- Check Ollama server connectivity
- Verify model is available: `ollama list`
- Try with longer timeout or more retries
- Ensure documents have sufficient text content

### Inconsistent Assessments
- Decrease temperature (e.g., 0.05) for more deterministic output
- Use more powerful model (gpt-oss:20b instead of smaller models)
- Provide full text instead of abstract only

### Parse Failures
- The agent automatically retries JSON parsing
- Check Ollama logs for model errors
- Try with different model if persistent

### Low Confidence Scores
- Normal for case reports and expert opinions (limited methodological detail)
- Consider using abstracts + full text for better context
- Some study types inherently have less structured reporting

## Integration with Other Agents

### With DocumentScoringAgent

```python
from bmlibrarian.agents import DocumentScoringAgent, StudyAssessmentAgent

# First, score documents for relevance
scoring_agent = DocumentScoringAgent()
relevant_docs = [
    doc for doc in documents
    if scoring_agent.evaluate_document(question, doc) >= 3
]

# Then assess quality of relevant studies
assessment_agent = StudyAssessmentAgent()
assessments = assessment_agent.assess_batch(relevant_docs)

# Filter for high-quality, relevant evidence
high_quality_evidence = [
    a for a in assessments
    if a.quality_score >= 7.0
]
```

### With CitationFinderAgent

```python
from bmlibrarian.agents import CitationFinderAgent, StudyAssessmentAgent

# Assess studies first
assessment_agent = StudyAssessmentAgent()
assessments = assessment_agent.assess_batch(documents)

# Extract citations only from high-quality studies
citation_agent = CitationFinderAgent()
high_quality_docs = [
    doc for doc in documents
    if any(a.document_id == str(doc['id']) and a.quality_score >= 7
           for a in assessments)
]
citations = citation_agent.process_scored_documents_for_citations(
    user_question=question,
    scored_documents=[(doc, 5) for doc in high_quality_docs],
    score_threshold=3.0
)
```

## See Also

- [PICOAgent User Guide](pico_guide.md) - Extract study components
- [Citation System Guide](citation_guide.md) - Extract evidence from studies
- [Reporting System Guide](reporting_guide.md) - Synthesize evidence into reports
- [Developer Documentation](../developers/study_assessment_system.md) - Technical details

## Support

For issues or questions:
- Check the troubleshooting section above
- Review examples in `examples/study_assessment_demo.py` (when available)
- Try the interactive laboratory: `uv run python study_assessment_lab.py` (when available)
- Report bugs at: https://github.com/hherb/bmlibrarian/issues
