# Study Assessment System - Developer Documentation

## Overview

The Study Assessment System provides AI-powered quality evaluation of biomedical research publications. This system enables systematic assessment of study design, methodological rigor, bias risk, and overall trustworthiness of evidence.

## Architecture

### Core Components

1. **StudyAssessmentAgent** (`src/bmlibrarian/agents/study_assessment_agent.py`)
   - Main agent class inheriting from `BaseAgent`
   - Handles LLM interaction and JSON response parsing
   - Provides batch processing capabilities
   - Exports assessments to JSON/CSV formats

2. **StudyAssessment** (dataclass)
   - Structured representation of quality assessment
   - Contains study classification, quality metrics, and bias evaluation
   - Supports JSON serialization for export/storage

### Class Hierarchy

```
BaseAgent (abstract)
└── StudyAssessmentAgent
```

## StudyAssessment Dataclass

### Core Fields

```python
@dataclass
class StudyAssessment:
    # Study classification
    study_type: str              # e.g., "RCT", "cohort study"
    study_design: str            # e.g., "prospective, double-blinded"

    # Quality metrics
    quality_score: float         # 0-10 scale
    strengths: List[str]         # Study strengths
    limitations: List[str]       # Weaknesses/limitations

    # Trustworthiness
    overall_confidence: float    # 0-1 scale (agent's confidence)
    confidence_explanation: str  # Explanation of rating
    evidence_level: str          # e.g., "Level 1 (high)"

    # Metadata
    document_id: str
    document_title: str

    # Design characteristics (optional)
    is_prospective: Optional[bool]
    is_retrospective: Optional[bool]
    is_blinded: Optional[bool]
    is_double_blinded: Optional[bool]
    is_randomized: Optional[bool]
    is_controlled: Optional[bool]
    is_multi_center: Optional[bool]
    sample_size: Optional[str]
    follow_up_duration: Optional[str]

    # Bias assessment (optional)
    selection_bias_risk: Optional[str]      # "low/moderate/high/unclear"
    performance_bias_risk: Optional[str]
    detection_bias_risk: Optional[str]
    attrition_bias_risk: Optional[str]
    reporting_bias_risk: Optional[str]

    # Additional metadata
    pmid: Optional[str]
    doi: Optional[str]
    created_at: Optional[datetime]
```

### Design Decisions

1. **Separate confidence and quality**:
   - `overall_confidence`: Agent's confidence in assessment accuracy
   - `quality_score`: Assessed methodological quality of the study
   - This separation allows filtering on both dimensions

2. **Boolean design flags**: Enable programmatic filtering for specific study types
   ```python
   rcts = [a for a in assessments if a.is_randomized and a.is_controlled]
   ```

3. **List-based strengths/limitations**: Structured extraction for analysis
   ```python
   common_limitations = Counter(
       lim for a in assessments for lim in a.limitations
   )
   ```

4. **Standardized bias categories**: Based on Cochrane Risk of Bias tool

## StudyAssessmentAgent Class

### Initialization

```python
def __init__(self,
             model: str = "gpt-oss:20b",
             host: str = "http://localhost:11434",
             temperature: float = 0.1,
             top_p: float = 0.9,
             max_tokens: int = 3000,
             callback: Optional[Callable[[str, str], None]] = None,
             orchestrator=None,
             show_model_info: bool = True,
             max_retries: int = 3)
```

**Configuration Parameters**:
- `model`: LLM model name (recommend `gpt-oss:20b` for thorough assessments)
- `temperature`: 0.1 default for consistent assessments (lower = more deterministic)
- `max_tokens`: 3000 default (assessments can be lengthy with detailed explanations)
- `max_retries`: 3 automatic retries on JSON parse failures

### Core Methods

#### assess_study()

```python
def assess_study(
    self,
    document: Dict[str, Any],
    min_confidence: float = 0.4
) -> Optional[StudyAssessment]
```

**Process Flow**:
1. Validate Ollama connection
2. Extract document text (prefer full_text over abstract)
3. Truncate text if needed (12,000 char limit)
4. Build comprehensive assessment prompt
5. Call LLM with retry logic
6. Parse JSON response (with automatic retries)
7. Validate required fields
8. Check confidence threshold
9. Construct StudyAssessment object
10. Update statistics

**Error Handling**:
- Returns `None` on Ollama connection failure
- Returns `None` on missing document text
- Returns `None` on JSON parse failure after retries
- Logs low-confidence assessments but still returns them (unlike PICOAgent)

**Why return low-confidence assessments?**
Study assessments are useful even with lower confidence, as they provide a structured framework for manual review. PICOAgent returns None for low confidence because incomplete PICO extraction is less useful.

#### assess_batch()

```python
def assess_batch(
    self,
    documents: List[Dict[str, Any]],
    min_confidence: float = 0.4,
    progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> List[StudyAssessment]
```

**Process Flow**:
1. Iterate through documents
2. Call progress callback for each (if provided)
3. Call assess_study() for each document
4. Collect successful assessments
5. Return list of assessments

**Performance Considerations**:
- Sequential processing (not parallel) to avoid overwhelming Ollama
- Progress callback for user feedback during long batches
- Failed assessments are logged but don't stop batch processing

### Utility Methods

#### format_assessment_summary()

```python
def format_assessment_summary(self, assessment: StudyAssessment) -> str
```

Returns human-readable formatted text with all assessment details.

**Use Cases**:
- CLI display
- Report generation
- Manual review interfaces

#### export_to_json()

```python
def export_to_json(self, assessments: List[StudyAssessment], output_file: str) -> None
```

Exports assessments with metadata in structured JSON format.

**JSON Structure**:
```json
{
  "assessments": [...],
  "metadata": {
    "total_assessments": 50,
    "assessment_date": "2023-10-15T14:30:00Z",
    "agent_model": "gpt-oss:20b",
    "statistics": {...}
  }
}
```

#### export_to_csv()

```python
def export_to_csv(self, assessments: List[StudyAssessment], output_file: str) -> None
```

Exports flat CSV for spreadsheet analysis.

**CSV Handling**:
- Lists (strengths, limitations) joined with semicolons
- All fields flattened for tabular format
- Headers match dataclass field names

#### get_quality_distribution()

```python
def get_quality_distribution(self, assessments: List[StudyAssessment]) -> Dict[str, int]
```

Returns distribution of quality scores in standard categories.

**Categories**:
- exceptional (9-10)
- high (7-8)
- moderate (5-6)
- low (3-4)
- very_low (0-2)

#### get_evidence_level_distribution()

```python
def get_evidence_level_distribution(self, assessments: List[StudyAssessment]) -> Dict[str, int]
```

Returns distribution of evidence levels across assessments.

### Statistics Tracking

```python
self._assessment_stats = {
    'total_assessments': 0,
    'successful_assessments': 0,
    'failed_assessments': 0,
    'low_confidence_assessments': 0,
    'parse_failures': 0
}
```

**Metrics**:
- `total_assessments`: Total attempts
- `successful_assessments`: Completed assessments
- `failed_assessments`: Connection/validation failures
- `low_confidence_assessments`: Below threshold (still returned)
- `parse_failures`: JSON parsing errors

## Prompt Engineering

### Prompt Structure

The assessment prompt follows a structured format:

1. **Role Definition**: "You are a medical research methodologist and epidemiologist..."
2. **Task Description**: "Conduct a comprehensive quality assessment..."
3. **Input Data**: Paper title and text
4. **Detailed Instructions**: 12 numbered sections covering all assessment aspects
5. **Critical Requirements**: Emphasizing evidence-based assessment, no fabrication
6. **Response Format**: JSON schema with example
7. **Output Constraint**: "Respond ONLY with valid JSON"

### Prompt Design Principles

1. **Specificity**: Detailed examples for each field
   ```
   Example: "Large sample size (N=5000)"
   ```

2. **Evidence-Based**: Explicitly forbid fabrication
   ```
   "Extract ONLY information that is ACTUALLY PRESENT in the text"
   ```

3. **Structured Scales**: Clear rating scales with definitions
   ```
   - 9-10: Exceptional quality, rigorous methods, minimal bias risk
   - 7-8: High quality, good methods, low bias risk
   ...
   ```

4. **Standardized Terminology**: Use established frameworks
   - Evidence levels based on Oxford CEBM
   - Bias categories from Cochrane Risk of Bias tool

5. **JSON Schema**: Complete example showing expected structure
   ```json
   {
     "study_type": "specific study type",
     "quality_score": 7.5,
     ...
   }
   ```

### Handling Edge Cases

**No clear study type**:
```python
"study_type": "Unclear - appears to be observational study"
```

**Missing information**:
```python
"is_blinded": null,
"selection_bias_risk": "unclear"
```

**Case reports** (minimal methodology):
```python
"quality_score": 2.0,
"evidence_level": "Level 5 (low)",
"limitations": ["Single case, no comparison group", "No generalizability"]
```

## JSON Response Parsing

### Parsing Strategy

The agent uses `_generate_and_parse_json()` from BaseAgent:

1. **Generate LLM response** with configured parameters
2. **Parse JSON** using `_parse_json_response()`
3. **On parse failure**: Retry with new LLM generation (not same response)
4. **After max retries**: Raise JSONDecodeError

### Why regenerate on parse failure?

When JSON parsing fails, it's because the LLM didn't follow instructions. Re-parsing the same bad response won't help. Regenerating gives the LLM another chance to produce valid JSON.

### Validation

After successful parsing, validate required fields:

```python
required_fields = ['study_type', 'study_design', 'quality_score', 'strengths',
                  'limitations', 'overall_confidence', 'confidence_explanation',
                  'evidence_level']
if not all(field in assessment_data for field in required_fields):
    logger.error(f"Missing required fields...")
    return None
```

## Integration Patterns

### With Database Queries

```python
from bmlibrarian.agents import QueryAgent, StudyAssessmentAgent
import psycopg

# Query database for studies
query_agent = QueryAgent()
sql_query = query_agent.natural_language_to_sql(
    "Find all RCTs about cardiovascular disease from 2020-2023"
)

# Execute query
with psycopg.connect("dbname=knowledgebase") as conn:
    with conn.cursor() as cur:
        cur.execute(sql_query)
        documents = [dict(row) for row in cur.fetchall()]

# Assess studies
assessment_agent = StudyAssessmentAgent()
assessments = assessment_agent.assess_batch(documents)
```

### With Workflow Orchestration

```python
from bmlibrarian.agents import AgentOrchestrator, StudyAssessmentAgent

# Initialize orchestrator
orchestrator = AgentOrchestrator(max_workers=4)

# Initialize agent with orchestrator
assessment_agent = StudyAssessmentAgent(orchestrator=orchestrator)

# Submit batch tasks to queue
task_ids = assessment_agent.submit_batch_tasks(
    method_name='assess_study',
    data_list=[{'document': doc} for doc in documents]
)

# Process queue
results = orchestrator.process_queue_until_complete()
```

### With Other Agents

**Quality-filtered evidence synthesis**:
```python
# 1. Query for documents
query_agent = QueryAgent()
documents = query_agent.search_documents(question)

# 2. Assess quality
assessment_agent = StudyAssessmentAgent()
assessments = assessment_agent.assess_batch(documents)

# 3. Filter high-quality
high_quality_ids = {
    a.document_id for a in assessments
    if a.quality_score >= 7.0
}

# 4. Score only high-quality documents
scoring_agent = DocumentScoringAgent()
scored_docs = [
    (doc, scoring_agent.evaluate_document(question, doc))
    for doc in documents
    if str(doc['id']) in high_quality_ids
]

# 5. Extract citations
citation_agent = CitationFinderAgent()
citations = citation_agent.process_scored_documents_for_citations(
    user_question=question,
    scored_documents=scored_docs,
    score_threshold=3.0
)

# 6. Generate report
reporting_agent = ReportingAgent()
report = reporting_agent.generate_citation_based_report(
    user_question=question,
    citations=citations
)
```

## Testing

### Unit Tests

**File**: `tests/test_study_assessment_agent.py`

**Test Coverage**:
1. **Connection testing**: Verify Ollama connectivity
2. **Single assessment**: Test assess_study() with various study types
3. **Batch processing**: Test assess_batch() with multiple documents
4. **Export functions**: Test JSON and CSV export
5. **Statistics**: Test get_assessment_stats()
6. **Distributions**: Test quality and evidence level distributions
7. **Edge cases**: Test with minimal abstracts, case reports, unclear studies
8. **Error handling**: Test missing text, connection failures, parse errors

**Example Test**:
```python
def test_assess_rct():
    """Test assessment of high-quality RCT"""
    agent = StudyAssessmentAgent(model="gpt-oss:20b")

    document = {
        'id': 1,
        'title': 'Efficacy of Drug X: A Randomized Trial',
        'abstract': """
        We conducted a randomized, double-blind, placebo-controlled trial
        of 500 patients...
        """
    }

    assessment = agent.assess_study(document, min_confidence=0.5)

    assert assessment is not None
    assert 'RCT' in assessment.study_type or 'randomized' in assessment.study_type.lower()
    assert assessment.is_randomized is True
    assert assessment.quality_score >= 7.0
    assert 'Level 1' in assessment.evidence_level
    assert len(assessment.strengths) > 0
    assert len(assessment.limitations) > 0
```

### Integration Tests

Test interaction with database and other agents:

```python
def test_assess_from_database():
    """Test assessment of real documents from database"""
    import psycopg

    # Query database
    with psycopg.connect("dbname=knowledgebase") as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, title, abstract, pmid, doi
                FROM documents
                WHERE source = 'pubmed'
                LIMIT 10
            """)
            documents = [dict(row) for row in cur.fetchall()]

    # Assess
    agent = StudyAssessmentAgent()
    assessments = agent.assess_batch(documents)

    assert len(assessments) > 0
    assert all(a.document_id.isdigit() for a in assessments)
```

## Performance Considerations

### Throughput

- **Single assessment**: 3-8 seconds (depends on text length and model)
- **Batch processing**: Linear scaling (no parallelization)
- **Recommended batch size**: 50-100 documents per session

### Optimization Strategies

1. **Use faster model for screening**:
   ```python
   # Quick screening
   agent = StudyAssessmentAgent(model="medgemma4B_it_q8:latest")

   # Detailed assessment
   agent = StudyAssessmentAgent(model="gpt-oss:20b")
   ```

2. **Cache assessments**:
   ```python
   # Save to database for reuse
   assessments_by_id = {a.document_id: a for a in assessments}
   ```

3. **Filter before assessing**:
   ```python
   # Assess only relevant documents
   relevant_docs = [doc for doc in documents if doc['relevance_score'] >= 3]
   assessments = agent.assess_batch(relevant_docs)
   ```

### Memory Usage

- **Per assessment**: ~2KB (StudyAssessment object)
- **Batch of 1000**: ~2MB
- **Full text processing**: Text truncated to 12,000 chars to fit in context window

## Extending the System

### Adding Custom Assessment Criteria

To add custom assessment fields:

1. **Update StudyAssessment dataclass**:
   ```python
   @dataclass
   class StudyAssessment:
       # ... existing fields ...

       # New custom field
       patient_reported_outcomes: Optional[bool] = None
       industry_funded: Optional[bool] = None
   ```

2. **Update prompt**:
   ```python
   prompt = f"""
   ...
   13. Patient-Reported Outcomes: Does the study include patient-reported outcomes? (true/false)
   14. Industry Funding: Is the study funded by industry? (true/false)
   ...
   """
   ```

3. **Update JSON schema in prompt**:
   ```json
   {
     ...,
     "patient_reported_outcomes": true,
     "industry_funded": false
   }
   ```

4. **Update assessment construction**:
   ```python
   assessment = StudyAssessment(
       # ... existing fields ...
       patient_reported_outcomes=assessment_data.get('patient_reported_outcomes'),
       industry_funded=assessment_data.get('industry_funded')
   )
   ```

### Custom Quality Scoring

Implement custom scoring logic:

```python
class CustomStudyAssessmentAgent(StudyAssessmentAgent):
    """Custom agent with domain-specific quality scoring"""

    def calculate_custom_quality_score(
        self,
        assessment: StudyAssessment
    ) -> float:
        """Apply custom quality scoring algorithm"""
        score = assessment.quality_score

        # Bonus for specific characteristics
        if assessment.is_double_blinded:
            score += 0.5
        if assessment.is_multi_center:
            score += 0.5
        if assessment.sample_size and 'N=' in assessment.sample_size:
            n = int(assessment.sample_size.split('N=')[1].split()[0])
            if n > 1000:
                score += 1.0

        # Penalty for bias
        high_bias_count = sum([
            1 for risk in [
                assessment.selection_bias_risk,
                assessment.performance_bias_risk
            ] if risk == 'high'
        ])
        score -= (high_bias_count * 1.0)

        return max(0.0, min(10.0, score))
```

## Database Schema (Optional)

If storing assessments in PostgreSQL:

```sql
CREATE SCHEMA IF NOT EXISTS study_assessments;

CREATE TABLE study_assessments.assessments (
    id SERIAL PRIMARY KEY,
    document_id INTEGER REFERENCES documents(id),

    -- Classification
    study_type TEXT NOT NULL,
    study_design TEXT NOT NULL,
    evidence_level TEXT NOT NULL,

    -- Quality metrics
    quality_score DECIMAL(3,1) NOT NULL CHECK (quality_score >= 0 AND quality_score <= 10),
    overall_confidence DECIMAL(3,2) NOT NULL CHECK (overall_confidence >= 0 AND overall_confidence <= 1),
    confidence_explanation TEXT NOT NULL,

    strengths TEXT[] NOT NULL,
    limitations TEXT[] NOT NULL,

    -- Design characteristics
    is_prospective BOOLEAN,
    is_retrospective BOOLEAN,
    is_randomized BOOLEAN,
    is_controlled BOOLEAN,
    is_blinded BOOLEAN,
    is_double_blinded BOOLEAN,
    is_multi_center BOOLEAN,

    sample_size TEXT,
    follow_up_duration TEXT,

    -- Bias assessment
    selection_bias_risk TEXT CHECK (selection_bias_risk IN ('low', 'moderate', 'high', 'unclear')),
    performance_bias_risk TEXT CHECK (performance_bias_risk IN ('low', 'moderate', 'high', 'unclear')),
    detection_bias_risk TEXT CHECK (detection_bias_risk IN ('low', 'moderate', 'high', 'unclear')),
    attrition_bias_risk TEXT CHECK (attrition_bias_risk IN ('low', 'moderate', 'high', 'unclear')),
    reporting_bias_risk TEXT CHECK (reporting_bias_risk IN ('low', 'moderate', 'high', 'unclear')),

    -- Metadata
    agent_model TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(document_id, agent_model)
);

CREATE INDEX idx_assessments_quality ON study_assessments.assessments(quality_score);
CREATE INDEX idx_assessments_evidence_level ON study_assessments.assessments(evidence_level);
CREATE INDEX idx_assessments_study_type ON study_assessments.assessments(study_type);
```

## Future Enhancements

1. **GRADE Assessment**: Full GRADE evidence quality assessment
2. **Risk of Bias 2.0**: Cochrane RoB 2.0 tool integration
3. **PRISMA Compliance**: Check systematic review reporting standards
4. **Statistical Power**: Assess sample size adequacy
5. **Conflict of Interest**: Extract and evaluate funding/COI statements
6. **Reproducibility Score**: Assess transparency and data availability
7. **Clinical Significance**: Evaluate effect sizes and clinical relevance
8. **Subgroup Analysis**: Assess credibility of subgroup findings

## References

- Oxford Centre for Evidence-Based Medicine (OCEBM) Levels of Evidence
- Cochrane Risk of Bias Tool
- GRADE Working Group
- PRISMA Statement for systematic reviews
- CONSORT Statement for RCTs

## See Also

- [User Guide](../users/study_assessment_guide.md) - End-user documentation
- [PICOAgent](pico_system.md) - Extract study components
- [Base Agent](base_agent.md) - Common agent functionality
- [Agent Module](agent_module.md) - Multi-agent architecture overview
