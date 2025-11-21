# Step 5: LLM-Based Assessors - PaperWeightAssessmentAgent

## Objective
Implement LLM-powered assessors for methodological quality and risk of bias evaluation. These require nuanced understanding beyond simple pattern matching.

## Prerequisites
- Step 1-4 completed (database, data models, config, rule-based extractors)
- Understanding of BMLibrarian's BaseAgent pattern
- Familiarity with Ollama API integration

## Implementation Details

### Methods to Implement

1. `_assess_methodological_quality(document: dict, study_assessment: Optional[dict]) -> DimensionScore`
2. `_assess_risk_of_bias(document: dict, study_assessment: Optional[dict]) -> DimensionScore`
3. Helper methods for LLM prompting and parsing

## Methodological Quality Assessment

### Components to Evaluate

From configuration (`methodological_quality_weights`):
- **Randomization (2.0 points)**: Proper sequence generation?
- **Blinding (3.0 points)**: None(0) / Single(1) / Double(2) / Triple(3)
- **Allocation concealment (1.5 points)**: Was allocation hidden?
- **Protocol preregistration (1.5 points)**: Protocol published before study?
- **ITT analysis (1.0 points)**: Intention-to-treat analysis?
- **Attrition handling (1.0 points)**: Based on dropout rate and handling quality

**Total:** 10.0 points

### LLM Prompt Strategy

**Structured extraction approach:**
1. Ask LLM to analyze each component separately
2. Request JSON output for easy parsing
3. Request evidence quotes and reasoning
4. Calculate score based on component weights

### Implementation

```python
def _assess_methodological_quality(
    self,
    document: dict,
    study_assessment: Optional[dict] = None
) -> DimensionScore:
    """
    Assess methodological quality using LLM analysis.

    Evaluates: randomization, blinding, allocation concealment,
    protocol preregistration, ITT analysis, attrition handling.

    Args:
        document: Document dict with 'abstract', 'full_text' fields
        study_assessment: Optional StudyAssessmentAgent output to leverage

    Returns:
        DimensionScore for methodological quality with detailed audit trail
    """
    # Prepare text for analysis
    text = self._prepare_text_for_analysis(document)

    # Check if we can leverage StudyAssessmentAgent output
    if study_assessment:
        # Try to extract relevant info from existing assessment
        return self._extract_mq_from_study_assessment(study_assessment, document)

    # Build LLM prompt
    prompt = self._build_methodological_quality_prompt(text)

    # Call LLM
    response = self._call_llm(prompt)

    # Parse response
    components = self._parse_methodological_quality_response(response)

    # Calculate score
    dimension_score = self._calculate_methodological_quality_score(components)

    return dimension_score


def _build_methodological_quality_prompt(self, text: str) -> str:
    """
    Build prompt for methodological quality assessment.

    Returns:
        Prompt string for LLM
    """
    return f"""You are an expert in biomedical research methodology. Analyze the following research paper and assess its methodological quality across six components.

PAPER TEXT:
{text[:8000]}  # Limit to avoid token limits

TASK:
Analyze the methodological quality and provide assessments for each component:

1. RANDOMIZATION (0-2 points):
   - 0: No randomization or inadequate sequence generation
   - 1: Randomization mentioned but method unclear
   - 2: Proper random sequence generation (e.g., computer-generated, random number table)

2. BLINDING (0-3 points):
   - 0: No blinding
   - 1: Single-blind (participants OR assessors)
   - 2: Double-blind (participants AND assessors)
   - 3: Triple-blind (participants, assessors, AND data analysts)

3. ALLOCATION CONCEALMENT (0-1.5 points):
   - 0: No allocation concealment or inadequate
   - 0.75: Unclear or partially described
   - 1.5: Proper allocation concealment (e.g., sealed envelopes, central randomization)

4. PROTOCOL PREREGISTRATION (0-1.5 points):
   - 0: No protocol registration mentioned
   - 0.75: Protocol mentioned but not verified
   - 1.5: Protocol clearly registered before study (e.g., ClinicalTrials.gov, registry number provided)

5. ITT ANALYSIS (0-1 points):
   - 0: No ITT analysis or per-protocol only
   - 0.5: Modified ITT or unclear
   - 1: Clear intention-to-treat analysis

6. ATTRITION HANDLING (0-1 points):
   - Extract dropout/attrition rate
   - Assess quality of handling (imputation methods, sensitivity analysis)
   - Score based on rate and handling quality

OUTPUT FORMAT (JSON):
{{
  "randomization": {{
    "score": <0-2>,
    "evidence": "<quote from paper>",
    "reasoning": "<explanation>"
  }},
  "blinding": {{
    "score": <0-3>,
    "evidence": "<quote from paper>",
    "reasoning": "<explanation>"
  }},
  "allocation_concealment": {{
    "score": <0-1.5>,
    "evidence": "<quote from paper>",
    "reasoning": "<explanation>"
  }},
  "protocol_preregistration": {{
    "score": <0-1.5>,
    "evidence": "<quote from paper>",
    "reasoning": "<explanation>"
  }},
  "itt_analysis": {{
    "score": <0-1>,
    "evidence": "<quote from paper>",
    "reasoning": "<explanation>"
  }},
  "attrition_handling": {{
    "score": <0-1>,
    "attrition_rate": <decimal or null>,
    "evidence": "<quote from paper>",
    "reasoning": "<explanation>"
  }}
}}

Provide ONLY the JSON output, no additional text."""


def _parse_methodological_quality_response(self, response: str) -> dict:
    """
    Parse LLM response for methodological quality assessment.

    Args:
        response: LLM response string (expected to be JSON)

    Returns:
        Parsed components dict
    """
    import json
    import re

    # Extract JSON from response (handle markdown code blocks)
    json_match = re.search(r'```(?:json)?\s*(\{.*\})\s*```', response, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
    else:
        # Try to find JSON directly
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
        else:
            raise ValueError("Could not find JSON in LLM response")

    try:
        components = json.loads(json_str)
        return components
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JSON from LLM response: {e}")


def _calculate_methodological_quality_score(self, components: dict) -> DimensionScore:
    """
    Calculate methodological quality score from component assessments.

    Args:
        components: Parsed component assessments from LLM

    Returns:
        DimensionScore with full audit trail
    """
    dimension_score = DimensionScore(
        dimension_name='methodological_quality',
        score=0.0
    )

    # Add each component
    for component_name, component_data in components.items():
        score_contribution = component_data.get('score', 0.0)
        evidence = component_data.get('evidence', '')
        reasoning = component_data.get('reasoning', '')

        dimension_score.add_detail(
            component=component_name,
            value=str(score_contribution),
            contribution=score_contribution,
            evidence=evidence,
            reasoning=reasoning
        )

        dimension_score.score += score_contribution

    # Cap at 10.0
    dimension_score.score = min(10.0, dimension_score.score)

    return dimension_score
```

## Risk of Bias Assessment

### Components to Evaluate

From configuration (`risk_of_bias_weights`):
- **Selection bias (2.5 points)**: Random sampling, inclusion/exclusion criteria
- **Performance bias (2.5 points)**: Blinding, standardization of interventions
- **Detection bias (2.5 points)**: Blinded outcome assessment
- **Reporting bias (2.5 points)**: Selective outcome reporting, protocol adherence

**Total:** 10.0 points

**NOTE:** Inverted scale - 10 = low risk, 0 = high risk

### Implementation

```python
def _assess_risk_of_bias(
    self,
    document: dict,
    study_assessment: Optional[dict] = None
) -> DimensionScore:
    """
    Assess risk of bias using LLM analysis.

    Evaluates: selection bias, performance bias, detection bias, reporting bias.
    Uses INVERTED SCALE: 10 = low risk, 0 = high risk.

    Args:
        document: Document dict with 'abstract', 'full_text' fields
        study_assessment: Optional StudyAssessmentAgent output to leverage

    Returns:
        DimensionScore for risk of bias with detailed audit trail
    """
    # Prepare text
    text = self._prepare_text_for_analysis(document)

    # Check if we can leverage StudyAssessmentAgent output
    if study_assessment:
        return self._extract_rob_from_study_assessment(study_assessment, document)

    # Build LLM prompt
    prompt = self._build_risk_of_bias_prompt(text)

    # Call LLM
    response = self._call_llm(prompt)

    # Parse response
    components = self._parse_risk_of_bias_response(response)

    # Calculate score
    dimension_score = self._calculate_risk_of_bias_score(components)

    return dimension_score


def _build_risk_of_bias_prompt(self, text: str) -> str:
    """
    Build prompt for risk of bias assessment.

    Returns:
        Prompt string for LLM
    """
    return f"""You are an expert in biomedical research methodology and bias assessment. Analyze the following research paper and assess its risk of bias across four domains.

PAPER TEXT:
{text[:8000]}

TASK:
Assess risk of bias using INVERTED SCALE (higher = lower risk):

1. SELECTION BIAS (0-2.5 points):
   - 0: High risk (convenience sampling, no clear criteria)
   - 1.25: Moderate risk (some limitations in sampling)
   - 2.5: Low risk (random/consecutive sampling, clear inclusion/exclusion criteria)

2. PERFORMANCE BIAS (0-2.5 points):
   - 0: High risk (no blinding, unstandardized interventions)
   - 1.25: Moderate risk (partial blinding or standardization)
   - 2.5: Low risk (proper blinding, standardized protocols)

3. DETECTION BIAS (0-2.5 points):
   - 0: High risk (unblinded outcome assessment)
   - 1.25: Moderate risk (partially blinded or objective outcomes only)
   - 2.5: Low risk (blinded outcome assessment for all outcomes)

4. REPORTING BIAS (0-2.5 points):
   - 0: High risk (selective reporting, outcomes not pre-specified)
   - 1.25: Moderate risk (some evidence of selective reporting)
   - 2.5: Low risk (all pre-specified outcomes reported, protocol available)

OUTPUT FORMAT (JSON):
{{
  "selection_bias": {{
    "score": <0-2.5>,
    "risk_level": "<high|moderate|low>",
    "evidence": "<quote from paper>",
    "reasoning": "<explanation>"
  }},
  "performance_bias": {{
    "score": <0-2.5>,
    "risk_level": "<high|moderate|low>",
    "evidence": "<quote from paper>",
    "reasoning": "<explanation>"
  }},
  "detection_bias": {{
    "score": <0-2.5>,
    "risk_level": "<high|moderate|low>",
    "evidence": "<quote from paper>",
    "reasoning": "<explanation>"
  }},
  "reporting_bias": {{
    "score": <0-2.5>,
    "risk_level": "<high|moderate|low>",
    "evidence": "<quote from paper>",
    "reasoning": "<explanation>"
  }}
}}

Provide ONLY the JSON output, no additional text."""


def _parse_risk_of_bias_response(self, response: str) -> dict:
    """
    Parse LLM response for risk of bias assessment.

    Same JSON extraction logic as methodological quality.
    """
    return self._parse_methodological_quality_response(response)


def _calculate_risk_of_bias_score(self, components: dict) -> DimensionScore:
    """
    Calculate risk of bias score from component assessments.

    Args:
        components: Parsed component assessments from LLM

    Returns:
        DimensionScore with full audit trail
    """
    dimension_score = DimensionScore(
        dimension_name='risk_of_bias',
        score=0.0
    )

    # Add each component
    for component_name, component_data in components.items():
        score_contribution = component_data.get('score', 0.0)
        risk_level = component_data.get('risk_level', 'unknown')
        evidence = component_data.get('evidence', '')
        reasoning = component_data.get('reasoning', '')

        dimension_score.add_detail(
            component=component_name,
            value=f"{risk_level} ({score_contribution})",
            contribution=score_contribution,
            evidence=evidence,
            reasoning=reasoning
        )

        dimension_score.score += score_contribution

    # Cap at 10.0
    dimension_score.score = min(10.0, dimension_score.score)

    return dimension_score
```

## Helper Methods

### LLM Communication

```python
def _call_llm(self, prompt: str) -> str:
    """
    Call Ollama LLM with prompt.

    Args:
        prompt: Prompt string

    Returns:
        LLM response text
    """
    import requests

    model = self.config.get('model', 'gpt-oss:20b')
    temperature = self.config.get('temperature', 0.3)
    top_p = self.config.get('top_p', 0.9)

    ollama_url = os.getenv('OLLAMA_URL', 'http://localhost:11434')

    response = requests.post(
        f"{ollama_url}/api/generate",
        json={
            'model': model,
            'prompt': prompt,
            'temperature': temperature,
            'top_p': top_p,
            'stream': False
        },
        timeout=120  # 2 minute timeout for complex analysis
    )

    response.raise_for_status()
    return response.json()['response']


def _prepare_text_for_analysis(self, document: dict) -> str:
    """
    Prepare document text for LLM analysis.

    Combines abstract and full text (if available), limits length.

    Args:
        document: Document dict

    Returns:
        Prepared text string
    """
    title = document.get('title', '')
    abstract = document.get('abstract', '')
    full_text = document.get('full_text', '')

    # Prefer full text, fall back to abstract
    if full_text:
        text = f"TITLE: {title}\n\nFULL TEXT:\n{full_text}"
    else:
        text = f"TITLE: {title}\n\nABSTRACT:\n{abstract}"

    # Limit to ~8000 characters to avoid token limits
    return text[:8000]
```

### Integration with StudyAssessmentAgent

```python
def _extract_mq_from_study_assessment(
    self,
    study_assessment: dict,
    document: dict
) -> DimensionScore:
    """
    Extract methodological quality from StudyAssessmentAgent output.

    If StudyAssessmentAgent has already analyzed the paper, reuse
    relevant assessments to avoid duplicate LLM calls.

    Args:
        study_assessment: Output from StudyAssessmentAgent
        document: Document dict (for fallback if needed)

    Returns:
        DimensionScore for methodological quality
    """
    # Check if study_assessment contains relevant fields
    # This depends on StudyAssessmentAgent output format
    # For now, fall back to direct LLM assessment

    # TODO: Implement extraction from StudyAssessmentAgent output
    # when integration is ready

    # Fallback to direct assessment
    return self._assess_methodological_quality(document, study_assessment=None)


def _extract_rob_from_study_assessment(
    self,
    study_assessment: dict,
    document: dict
) -> DimensionScore:
    """
    Extract risk of bias from StudyAssessmentAgent output.

    Similar to methodological quality extraction.
    """
    # TODO: Implement extraction from StudyAssessmentAgent output

    # Fallback
    return self._assess_risk_of_bias(document, study_assessment=None)
```

## Testing

### Create Test File: `tests/test_paper_weight_llm_assessors.py`

```python
"""Tests for LLM-based assessors in PaperWeightAssessmentAgent"""

import pytest
from bmlibrarian.agents.paper_weight_agent import PaperWeightAssessmentAgent


@pytest.fixture
def agent():
    """Create agent instance for testing"""
    return PaperWeightAssessmentAgent()


@pytest.fixture
def sample_rct_document():
    """Sample RCT document for testing"""
    return {
        'title': 'Effect of Exercise on Cardiovascular Health',
        'abstract': '''This double-blind randomized controlled trial examined
        the effect of exercise on cardiovascular outcomes. Participants were
        randomly assigned using computer-generated random numbers to either
        exercise or control groups. Allocation was concealed using sealed
        envelopes. The study was registered at ClinicalTrials.gov (NCT12345678)
        before enrollment. We enrolled 450 participants and followed them for
        12 months. Outcome assessors were blinded to group assignment.
        Analysis was conducted using intention-to-treat principles.
        The dropout rate was 5%.''',
        'full_text': ''
    }


def test_build_methodological_quality_prompt(agent, sample_rct_document):
    """Test prompt building for methodological quality"""
    text = agent._prepare_text_for_analysis(sample_rct_document)
    prompt = agent._build_methodological_quality_prompt(text)

    assert 'methodological quality' in prompt.lower()
    assert 'randomization' in prompt.lower()
    assert 'blinding' in prompt.lower()
    assert 'JSON' in prompt


def test_parse_methodological_quality_response(agent):
    """Test JSON parsing from LLM response"""
    # Test with markdown code block
    response_with_markdown = '''```json
    {
      "randomization": {"score": 2.0, "evidence": "computer-generated", "reasoning": "Proper method"},
      "blinding": {"score": 2.0, "evidence": "double-blind", "reasoning": "Participants and assessors"}
    }
    ```'''

    result = agent._parse_methodological_quality_response(response_with_markdown)

    assert result['randomization']['score'] == 2.0
    assert result['blinding']['score'] == 2.0

    # Test with bare JSON
    response_bare = '''{
      "randomization": {"score": 2.0, "evidence": "test", "reasoning": "test"}
    }'''

    result = agent._parse_methodological_quality_response(response_bare)
    assert result['randomization']['score'] == 2.0


def test_calculate_methodological_quality_score(agent):
    """Test score calculation from components"""
    components = {
        "randomization": {"score": 2.0, "evidence": "proper random", "reasoning": "good"},
        "blinding": {"score": 3.0, "evidence": "triple-blind", "reasoning": "excellent"},
        "allocation_concealment": {"score": 1.5, "evidence": "sealed envelopes", "reasoning": "proper"},
        "protocol_preregistration": {"score": 1.5, "evidence": "NCT12345", "reasoning": "registered"},
        "itt_analysis": {"score": 1.0, "evidence": "ITT analysis", "reasoning": "proper"},
        "attrition_handling": {"score": 1.0, "evidence": "5% dropout", "reasoning": "excellent"}
    }

    result = agent._calculate_methodological_quality_score(components)

    assert result.dimension_name == 'methodological_quality'
    assert result.score == 10.0  # Perfect score
    assert len(result.details) == 6


@pytest.mark.slow
@pytest.mark.requires_ollama
def test_assess_methodological_quality_integration(agent, sample_rct_document):
    """Integration test for methodological quality assessment (requires Ollama)"""
    result = agent._assess_methodological_quality(sample_rct_document)

    assert result.dimension_name == 'methodological_quality'
    assert 0 <= result.score <= 10
    assert len(result.details) > 0

    # Should detect high quality RCT
    assert result.score > 7.0


def test_build_risk_of_bias_prompt(agent, sample_rct_document):
    """Test prompt building for risk of bias"""
    text = agent._prepare_text_for_analysis(sample_rct_document)
    prompt = agent._build_risk_of_bias_prompt(text)

    assert 'risk of bias' in prompt.lower()
    assert 'selection bias' in prompt.lower()
    assert 'INVERTED SCALE' in prompt


@pytest.mark.slow
@pytest.mark.requires_ollama
def test_assess_risk_of_bias_integration(agent, sample_rct_document):
    """Integration test for risk of bias assessment (requires Ollama)"""
    result = agent._assess_risk_of_bias(sample_rct_document)

    assert result.dimension_name == 'risk_of_bias'
    assert 0 <= result.score <= 10
    assert len(result.details) > 0

    # Should detect low risk of bias (high score)
    assert result.score > 7.0
```

### Run Tests

```bash
# Unit tests only (fast)
uv run python -m pytest tests/test_paper_weight_llm_assessors.py -v -m "not slow"

# Integration tests (requires Ollama)
uv run python -m pytest tests/test_paper_weight_llm_assessors.py -v -m slow
```

## Success Criteria
- [ ] `_assess_methodological_quality()` implemented with LLM prompting
- [ ] `_assess_risk_of_bias()` implemented with LLM prompting
- [ ] JSON parsing robust (handles markdown code blocks and bare JSON)
- [ ] Component scores calculated correctly
- [ ] Full audit trail recorded for each component
- [ ] LLM communication working (Ollama API)
- [ ] Text preparation limits length appropriately
- [ ] Integration tests passing (with Ollama)
- [ ] Placeholder for StudyAssessmentAgent integration created

## Performance Expectations
- **Methodological quality assessment:** ~5-10 seconds per document (LLM call)
- **Risk of bias assessment:** ~5-10 seconds per document (LLM call)
- **Total LLM time:** ~10-20 seconds per document for both assessments

## Error Handling

Add robust error handling for LLM failures:

```python
def _assess_methodological_quality(self, document: dict, study_assessment: Optional[dict] = None) -> DimensionScore:
    """...docstring..."""
    try:
        # Normal assessment logic
        ...
    except Exception as e:
        # Log error and return degraded score
        print(f"Error in methodological quality assessment: {e}")

        dimension_score = DimensionScore(
            dimension_name='methodological_quality',
            score=5.0  # Neutral score on error
        )
        dimension_score.add_detail(
            component='error',
            value='assessment_failed',
            contribution=5.0,
            reasoning=f'LLM assessment failed: {str(e)}'
        )
        return dimension_score
```

## Notes for Future Reference
- **JSON Parsing:** LLMs sometimes wrap JSON in markdown code blocks - handle both formats
- **Temperature:** 0.3 provides good balance between determinism and reasoning
- **Token Limits:** 8000 characters (~2000 tokens) leaves room for prompt + response
- **StudyAssessmentAgent Integration:** Implement when ready to avoid duplicate LLM calls
- **Error Recovery:** Graceful degradation to neutral scores on LLM failures

## Next Step
After LLM assessors are complete and tested, proceed to **Step 6: Database Persistence and Caching**.
