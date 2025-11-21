# Step 6: Database Persistence and Caching - PaperWeightAssessmentAgent

## Objective
Implement database persistence and intelligent caching to avoid redundant assessments. Store full audit trail in PostgreSQL for reproducibility.

## Prerequisites
- Step 1-5 completed (database, data models, config, extractors, LLM assessors)
- Understanding of PostgreSQL with psycopg
- Database migration applied from Step 1

## Implementation Details

### Methods to Implement

1. `_get_cached_assessment(document_id: int) -> Optional[PaperWeightResult]`
2. `_store_assessment(result: PaperWeightResult) -> None`
3. `assess_paper(document_id: int, force_reassess: bool = False) -> PaperWeightResult`
4. Helper methods for database operations

## Caching Strategy

### When to Use Cache

**Use cached assessment when:**
- Assessment exists for `(document_id, assessor_version)`
- `force_reassess=False`

**Re-assess when:**
- No cached assessment exists
- `assessor_version` has changed (methodology improvement)
- `force_reassess=True` (manual override)

### Version-Based Invalidation

When methodology changes:
1. Increment `version` in config (`"1.0.0"` → `"1.1.0"`)
2. Next assessment run will skip old cache (different version)
3. Old assessments remain in database for historical analysis

## Database Operations

### Fetching Cached Assessment

```python
def _get_cached_assessment(self, document_id: int) -> Optional[PaperWeightResult]:
    """
    Retrieve cached assessment from database.

    Checks for existing assessment with matching document_id and assessor_version.

    Args:
        document_id: Database ID of document

    Returns:
        PaperWeightResult if cached, None otherwise
    """
    import psycopg
    import os

    version = self.config.get('version', '1.0.0')

    try:
        with psycopg.connect(
            dbname=os.getenv('POSTGRES_DB', 'knowledgebase'),
            user=os.getenv('POSTGRES_USER'),
            password=os.getenv('POSTGRES_PASSWORD'),
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=os.getenv('POSTGRES_PORT', '5432')
        ) as conn:
            with conn.cursor() as cur:
                # Fetch assessment
                cur.execute("""
                    SELECT
                        assessment_id,
                        document_id,
                        assessed_at,
                        assessor_version,
                        study_design_score,
                        sample_size_score,
                        methodological_quality_score,
                        risk_of_bias_score,
                        replication_status_score,
                        final_weight,
                        dimension_weights,
                        study_type,
                        sample_size
                    FROM paper_weights.assessments
                    WHERE document_id = %s AND assessor_version = %s
                """, (document_id, version))

                row = cur.fetchone()
                if not row:
                    return None

                assessment_id = row[0]

                # Fetch assessment details
                cur.execute("""
                    SELECT
                        dimension,
                        component,
                        extracted_value,
                        score_contribution,
                        evidence_text,
                        reasoning
                    FROM paper_weights.assessment_details
                    WHERE assessment_id = %s
                    ORDER BY detail_id
                """, (assessment_id,))

                details = cur.fetchall()

                # Convert to PaperWeightResult
                return self._reconstruct_result_from_db(row, details)

    except Exception as e:
        print(f"Error fetching cached assessment: {e}")
        return None


def _reconstruct_result_from_db(self, assessment_row: tuple, detail_rows: list) -> PaperWeightResult:
    """
    Reconstruct PaperWeightResult from database rows.

    Args:
        assessment_row: Row from paper_weights.assessments
        detail_rows: Rows from paper_weights.assessment_details

    Returns:
        Reconstructed PaperWeightResult
    """
    import json

    # Unpack assessment row
    (assessment_id, document_id, assessed_at, assessor_version,
     study_design_score, sample_size_score, methodological_quality_score,
     risk_of_bias_score, replication_status_score, final_weight,
     dimension_weights, study_type, sample_size_n) = assessment_row

    # Parse dimension weights (JSONB)
    if isinstance(dimension_weights, str):
        dimension_weights = json.loads(dimension_weights)

    # Group details by dimension
    dimension_details = {
        'study_design': [],
        'sample_size': [],
        'methodological_quality': [],
        'risk_of_bias': [],
        'replication_status': []
    }

    for detail_row in detail_rows:
        (dimension, component, extracted_value, score_contribution,
         evidence_text, reasoning) = detail_row

        if dimension in dimension_details:
            dimension_details[dimension].append(AssessmentDetail(
                dimension=dimension,
                component=component,
                extracted_value=extracted_value,
                score_contribution=float(score_contribution) if score_contribution else 0.0,
                evidence_text=evidence_text,
                reasoning=reasoning
            ))

    # Create dimension scores
    study_design = DimensionScore(
        dimension_name='study_design',
        score=float(study_design_score),
        details=dimension_details['study_design']
    )

    sample_size_dim = DimensionScore(
        dimension_name='sample_size',
        score=float(sample_size_score),
        details=dimension_details['sample_size']
    )

    methodological_quality = DimensionScore(
        dimension_name='methodological_quality',
        score=float(methodological_quality_score),
        details=dimension_details['methodological_quality']
    )

    risk_of_bias = DimensionScore(
        dimension_name='risk_of_bias',
        score=float(risk_of_bias_score),
        details=dimension_details['risk_of_bias']
    )

    replication_status = DimensionScore(
        dimension_name='replication_status',
        score=float(replication_status_score),
        details=dimension_details['replication_status']
    )

    # Create result
    return PaperWeightResult(
        document_id=document_id,
        assessor_version=assessor_version,
        assessed_at=assessed_at,
        study_design=study_design,
        sample_size=sample_size_dim,
        methodological_quality=methodological_quality,
        risk_of_bias=risk_of_bias,
        replication_status=replication_status,
        final_weight=float(final_weight),
        dimension_weights=dimension_weights,
        study_type=study_type,
        sample_size_n=sample_size_n
    )
```

### Storing Assessment

```python
def _store_assessment(self, result: PaperWeightResult) -> None:
    """
    Store assessment in database with full audit trail.

    Inserts into both paper_weights.assessments and paper_weights.assessment_details.
    Uses ON CONFLICT to handle re-assessments with same version.

    Args:
        result: PaperWeightResult to store
    """
    import psycopg
    import os
    import json

    try:
        with psycopg.connect(
            dbname=os.getenv('POSTGRES_DB', 'knowledgebase'),
            user=os.getenv('POSTGRES_USER'),
            password=os.getenv('POSTGRES_PASSWORD'),
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=os.getenv('POSTGRES_PORT', '5432')
        ) as conn:
            with conn.cursor() as cur:
                # Insert/update assessment
                cur.execute("""
                    INSERT INTO paper_weights.assessments (
                        document_id,
                        assessor_version,
                        assessed_at,
                        study_design_score,
                        sample_size_score,
                        methodological_quality_score,
                        risk_of_bias_score,
                        replication_status_score,
                        final_weight,
                        dimension_weights,
                        study_type,
                        sample_size
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (document_id, assessor_version)
                    DO UPDATE SET
                        assessed_at = EXCLUDED.assessed_at,
                        study_design_score = EXCLUDED.study_design_score,
                        sample_size_score = EXCLUDED.sample_size_score,
                        methodological_quality_score = EXCLUDED.methodological_quality_score,
                        risk_of_bias_score = EXCLUDED.risk_of_bias_score,
                        replication_status_score = EXCLUDED.replication_status_score,
                        final_weight = EXCLUDED.final_weight,
                        dimension_weights = EXCLUDED.dimension_weights,
                        study_type = EXCLUDED.study_type,
                        sample_size = EXCLUDED.sample_size
                    RETURNING assessment_id
                """, (
                    result.document_id,
                    result.assessor_version,
                    result.assessed_at,
                    result.study_design.score,
                    result.sample_size.score,
                    result.methodological_quality.score,
                    result.risk_of_bias.score,
                    result.replication_status.score,
                    result.final_weight,
                    json.dumps(result.dimension_weights),
                    result.study_type,
                    result.sample_size_n
                ))

                assessment_id = cur.fetchone()[0]

                # Delete old details (if updating)
                cur.execute("""
                    DELETE FROM paper_weights.assessment_details
                    WHERE assessment_id = %s
                """, (assessment_id,))

                # Insert new details
                all_details = result.get_all_details()
                for detail in all_details:
                    cur.execute("""
                        INSERT INTO paper_weights.assessment_details (
                            assessment_id,
                            dimension,
                            component,
                            extracted_value,
                            score_contribution,
                            evidence_text,
                            reasoning
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (
                        assessment_id,
                        detail.dimension,
                        detail.component,
                        detail.extracted_value,
                        detail.score_contribution,
                        detail.evidence_text,
                        detail.reasoning
                    ))

                conn.commit()

    except Exception as e:
        print(f"Error storing assessment: {e}")
        raise
```

## Main Assessment Method

```python
def assess_paper(
    self,
    document_id: int,
    force_reassess: bool = False,
    study_assessment: Optional[dict] = None
) -> PaperWeightResult:
    """
    Assess paper weight with intelligent caching.

    This is the main entry point for paper weight assessment.

    Args:
        document_id: Database ID of document to assess
        force_reassess: If True, skip cache and re-assess
        study_assessment: Optional StudyAssessmentAgent output to leverage

    Returns:
        PaperWeightResult with full audit trail

    Workflow:
        1. Check cache (unless force_reassess=True)
        2. If cached and version matches, return cached result
        3. Otherwise, perform full assessment:
           a. Fetch document from database
           b. Extract study type (rule-based)
           c. Extract sample size (rule-based + LLM)
           d. Assess methodological quality (LLM)
           e. Assess risk of bias (LLM)
           f. Check replication status (database query)
           g. Compute final weight
           h. Store in database
        4. Return result
    """
    version = self.config.get('version', '1.0.0')

    # Check cache
    if not force_reassess:
        cached = self._get_cached_assessment(document_id)
        if cached:
            print(f"Using cached assessment for document {document_id} (version {version})")
            return cached

    print(f"Performing fresh assessment for document {document_id}...")

    # Fetch document
    document = self._get_document(document_id)

    # Perform assessments
    study_design_score = self._extract_study_type(document)
    sample_size_score = self._extract_sample_size(document)
    methodological_quality_score = self._assess_methodological_quality(document, study_assessment)
    risk_of_bias_score = self._assess_risk_of_bias(document, study_assessment)
    replication_status_score = self._check_replication_status(document_id)

    # Compute final weight
    final_weight = self._compute_final_weight({
        'study_design': study_design_score,
        'sample_size': sample_size_score,
        'methodological_quality': methodological_quality_score,
        'risk_of_bias': risk_of_bias_score,
        'replication_status': replication_status_score
    })

    # Create result
    result = PaperWeightResult(
        document_id=document_id,
        assessor_version=version,
        assessed_at=datetime.now(),
        study_design=study_design_score,
        sample_size=sample_size_score,
        methodological_quality=methodological_quality_score,
        risk_of_bias=risk_of_bias_score,
        replication_status=replication_status_score,
        final_weight=final_weight,
        dimension_weights=self._get_dimension_weights(),
        study_type=study_design_score.details[0].extracted_value if study_design_score.details else None,
        sample_size_n=int(sample_size_score.details[0].extracted_value) if sample_size_score.details and sample_size_score.details[0].extracted_value.isdigit() else None
    )

    # Store in database
    self._store_assessment(result)

    return result


def _compute_final_weight(self, dimension_scores: dict) -> float:
    """
    Compute final weight from dimension scores.

    Formula: final_weight = sum(dimension_score * weight)

    Args:
        dimension_scores: Dict mapping dimension names to DimensionScore objects

    Returns:
        Final weight (0-10)
    """
    weights = self._get_dimension_weights()

    final_weight = 0.0
    for dim_name, dim_score in dimension_scores.items():
        weight = weights.get(dim_name, 0.0)
        final_weight += dim_score.score * weight

    return min(10.0, max(0.0, final_weight))


def _get_dimension_weights(self) -> dict:
    """Get dimension weights from config"""
    return self.config.get('dimension_weights', {
        'study_design': 0.25,
        'sample_size': 0.15,
        'methodological_quality': 0.30,
        'risk_of_bias': 0.20,
        'replication_status': 0.10
    })
```

## Replication Status (Placeholder)

```python
def _check_replication_status(self, document_id: int) -> DimensionScore:
    """
    Check replication status from database.

    Queries paper_weights.replications table for this document.
    Initially manual entry only - automated discovery is future work.

    Args:
        document_id: Database ID of document

    Returns:
        DimensionScore for replication status
    """
    import psycopg
    import os

    try:
        with psycopg.connect(
            dbname=os.getenv('POSTGRES_DB', 'knowledgebase'),
            user=os.getenv('POSTGRES_USER'),
            password=os.getenv('POSTGRES_PASSWORD'),
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=os.getenv('POSTGRES_PORT', '5432')
        ) as conn:
            with conn.cursor() as cur:
                # Check for replications
                cur.execute("""
                    SELECT
                        replication_id,
                        replication_type,
                        quality_comparison,
                        confidence
                    FROM paper_weights.replications
                    WHERE source_document_id = %s
                    AND replication_type = 'confirms'
                """, (document_id,))

                replications = cur.fetchall()

                if not replications:
                    # No replications found
                    dimension_score = DimensionScore(
                        dimension_name='replication_status',
                        score=0.0
                    )
                    dimension_score.add_detail(
                        component='replication_count',
                        value='0',
                        contribution=0.0,
                        reasoning='No confirming replications found in database'
                    )
                    return dimension_score

                # Calculate score based on replications
                replication_count = len(replications)
                quality_comparison = replications[0][2]  # First replication quality

                # Scoring logic
                if replication_count == 1 and quality_comparison == 'comparable':
                    score = 5.0
                elif replication_count == 1 and quality_comparison == 'higher':
                    score = 8.0
                elif replication_count >= 2 and quality_comparison == 'comparable':
                    score = 8.0
                elif replication_count >= 2 and quality_comparison == 'higher':
                    score = 10.0
                else:
                    score = 3.0  # Lower quality replications

                dimension_score = DimensionScore(
                    dimension_name='replication_status',
                    score=score
                )

                dimension_score.add_detail(
                    component='replication_count',
                    value=str(replication_count),
                    contribution=score,
                    reasoning=f'{replication_count} confirming replications found (quality: {quality_comparison})'
                )

                return dimension_score

    except Exception as e:
        print(f"Error checking replication status: {e}")

        # Return zero score on error
        dimension_score = DimensionScore(
            dimension_name='replication_status',
            score=0.0
        )
        dimension_score.add_detail(
            component='error',
            value='query_failed',
            contribution=0.0,
            reasoning=f'Database query failed: {str(e)}'
        )
        return dimension_score
```

## Testing

### Create Test File: `tests/test_paper_weight_persistence.py`

```python
"""Tests for database persistence in PaperWeightAssessmentAgent"""

import pytest
from datetime import datetime
from bmlibrarian.agents.paper_weight_agent import (
    PaperWeightAssessmentAgent,
    PaperWeightResult,
    DimensionScore
)


@pytest.fixture
def agent():
    """Create agent instance for testing"""
    return PaperWeightAssessmentAgent()


@pytest.fixture
def sample_result():
    """Create sample result for testing"""
    study_design = DimensionScore('study_design', 8.0)
    study_design.add_detail('study_type', 'RCT', 8.0, reasoning='RCT detected')

    sample_size = DimensionScore('sample_size', 7.5)
    sample_size.add_detail('extracted_n', '450', 5.5)
    sample_size.add_detail('power_calculation', 'yes', 2.0)

    return PaperWeightResult(
        document_id=99999,  # Test document ID
        assessor_version='1.0.0',
        assessed_at=datetime.now(),
        study_design=study_design,
        sample_size=sample_size,
        methodological_quality=DimensionScore('methodological_quality', 6.5),
        risk_of_bias=DimensionScore('risk_of_bias', 7.0),
        replication_status=DimensionScore('replication_status', 0.0),
        final_weight=7.2,
        dimension_weights={'study_design': 0.25, 'sample_size': 0.15},
        study_type='RCT',
        sample_size_n=450
    )


@pytest.mark.requires_database
def test_store_and_retrieve_assessment(agent, sample_result):
    """Test storing and retrieving assessment from database"""
    # Store assessment
    agent._store_assessment(sample_result)

    # Retrieve from cache
    cached = agent._get_cached_assessment(sample_result.document_id)

    assert cached is not None
    assert cached.document_id == sample_result.document_id
    assert cached.final_weight == sample_result.final_weight
    assert cached.study_type == sample_result.study_type

    # Cleanup
    # (In real tests, use transaction rollback or test database)


@pytest.mark.requires_database
def test_cache_invalidation_on_version_change(agent, sample_result):
    """Test that cache is invalidated when version changes"""
    # Store with version 1.0.0
    agent._store_assessment(sample_result)

    # Should retrieve with same version
    cached = agent._get_cached_assessment(sample_result.document_id)
    assert cached is not None

    # Change version in config
    agent.config['version'] = '2.0.0'

    # Should NOT retrieve (version mismatch)
    cached = agent._get_cached_assessment(sample_result.document_id)
    assert cached is None


def test_compute_final_weight(agent):
    """Test final weight calculation"""
    dimension_scores = {
        'study_design': DimensionScore('study_design', 8.0),
        'sample_size': DimensionScore('sample_size', 7.0),
        'methodological_quality': DimensionScore('methodological_quality', 6.0),
        'risk_of_bias': DimensionScore('risk_of_bias', 7.0),
        'replication_status': DimensionScore('replication_status', 5.0)
    }

    # Default weights: 0.25, 0.15, 0.30, 0.20, 0.10
    # Expected: 8.0*0.25 + 7.0*0.15 + 6.0*0.30 + 7.0*0.20 + 5.0*0.10
    #         = 2.0 + 1.05 + 1.8 + 1.4 + 0.5 = 6.75

    final_weight = agent._compute_final_weight(dimension_scores)

    assert final_weight == pytest.approx(6.75, abs=0.01)
```

### Run Tests

```bash
# Unit tests
uv run python -m pytest tests/test_paper_weight_persistence.py -v -m "not requires_database"

# Database integration tests
uv run python -m pytest tests/test_paper_weight_persistence.py -v -m requires_database
```

## Success Criteria
- [ ] `_get_cached_assessment()` retrieves cached assessments correctly
- [ ] Cache invalidation works when version changes
- [ ] `_store_assessment()` persists to database with full audit trail
- [ ] `assess_paper()` orchestrates full workflow correctly
- [ ] Final weight calculation correct
- [ ] Replication status checking implemented (placeholder)
- [ ] Error handling robust
- [ ] All tests passing

## Performance Expectations
- **Cache hit:** <50ms (database query only)
- **Cache miss:** ~15-30 seconds (full assessment with LLM calls)
- **Storage:** <100ms per assessment

## Error Handling

Ensure robust error handling:

```python
def assess_paper(self, document_id: int, force_reassess: bool = False, study_assessment: Optional[dict] = None) -> PaperWeightResult:
    """...docstring..."""
    try:
        # Main workflow
        ...
    except Exception as e:
        print(f"Error assessing paper {document_id}: {e}")
        # Return degraded assessment with error noted
        return self._create_error_result(document_id, str(e))


def _create_error_result(self, document_id: int, error_message: str) -> PaperWeightResult:
    """Create minimal result on error"""
    error_score = DimensionScore('error', 0.0)
    error_score.add_detail('error', 'assessment_failed', 0.0, reasoning=error_message)

    return PaperWeightResult(
        document_id=document_id,
        assessor_version=self.config.get('version', '1.0.0'),
        assessed_at=datetime.now(),
        study_design=error_score,
        sample_size=error_score,
        methodological_quality=error_score,
        risk_of_bias=error_score,
        replication_status=error_score,
        final_weight=0.0,
        dimension_weights=self._get_dimension_weights()
    )
```

## Notes for Future Reference
- **ON CONFLICT:** Uses PostgreSQL's UPSERT to handle re-assessments gracefully
- **Version Strategy:** Change version when methodology improves, old assessments remain for comparison
- **Audit Trail:** Every detail stored ensures complete reproducibility
- **Replication Tracking:** Manual initially via GUI, automated discovery = future project
- **Transaction Safety:** Uses psycopg's connection context manager for automatic commit/rollback

## Next Step
After database persistence is complete and tested, proceed to **Step 7: Laboratory GUI (PySide6)**.
