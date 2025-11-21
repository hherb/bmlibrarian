# Step 4: Rule-Based Extractors - PaperWeightAssessmentAgent

## Objective
Implement fast, deterministic rule-based extractors for study type detection and sample size extraction. These extractors use pattern matching and simple heuristics without LLM calls for maximum performance.

## Prerequisites
- Step 1 completed (database migration)
- Step 2 completed (data models)
- Step 3 completed (configuration schema)
- Understanding of regex patterns and text processing

## Implementation Details

### Methods to Implement

1. `_extract_study_type(document: dict) -> DimensionScore`
2. `_extract_sample_size(document: dict) -> DimensionScore`
3. Helper methods for pattern matching

## Study Type Extraction

### Algorithm

1. **Extract text:** Get abstract + methods section (if available)
2. **Normalize:** Convert to lowercase, remove extra whitespace
3. **Keyword matching:** Match against configured keywords in priority order
4. **Priority hierarchy:** Higher-level evidence takes precedence
   - Systematic review/meta-analysis > RCT > Cohort > Case-control > Cross-sectional > Case series > Case report
5. **Assign score:** Use study_type_hierarchy from config
6. **Audit trail:** Record matched keywords and evidence text

### Implementation

```python
def _extract_study_type(self, document: dict) -> DimensionScore:
    """
    Extract study type using keyword matching.

    Matches keywords from config against abstract and methods section.
    Uses priority hierarchy: systematic review > RCT > cohort > etc.

    Args:
        document: Document dict with 'abstract' and optional 'methods_text' fields

    Returns:
        DimensionScore for study design with audit trail
    """
    # Get text to search
    abstract = document.get('abstract', '').lower()
    methods = document.get('methods_text', '').lower()
    search_text = f"{abstract} {methods}"

    # Get config
    keywords_config = self.config.get('study_type_keywords', {})
    hierarchy_config = self.config.get('study_type_hierarchy', {})

    # Priority order (highest to lowest)
    priority_order = [
        'systematic_review',
        'meta_analysis',
        'rct',
        'cohort_prospective',
        'cohort_retrospective',
        'case_control',
        'cross_sectional',
        'case_series',
        'case_report'
    ]

    # Try each study type in priority order
    for study_type in priority_order:
        keywords = keywords_config.get(study_type, [])
        for keyword in keywords:
            if keyword.lower() in search_text:
                # Found match - get score from hierarchy
                score = hierarchy_config.get(study_type, 5.0)

                # Create dimension score with audit trail
                dimension_score = DimensionScore(
                    dimension_name='study_design',
                    score=score
                )

                # Find evidence context (50 chars before/after keyword)
                evidence_text = self._extract_context(search_text, keyword.lower())

                dimension_score.add_detail(
                    component='study_type',
                    value=study_type,
                    contribution=score,
                    evidence=evidence_text,
                    reasoning=f"Matched keyword '{keyword}' indicating {study_type.replace('_', ' ')}"
                )

                return dimension_score

    # No match found - default to unknown
    dimension_score = DimensionScore(
        dimension_name='study_design',
        score=5.0  # Neutral score
    )
    dimension_score.add_detail(
        component='study_type',
        value='unknown',
        contribution=5.0,
        reasoning='No study type keywords matched - assigned neutral score'
    )

    return dimension_score


def _extract_context(self, text: str, keyword: str, context_chars: int = 50) -> str:
    """
    Extract text context around a keyword.

    Args:
        text: Full text to search
        keyword: Keyword to find
        context_chars: Characters to include before/after keyword

    Returns:
        Text snippet with context around keyword
    """
    keyword_pos = text.find(keyword)
    if keyword_pos == -1:
        return ""

    start = max(0, keyword_pos - context_chars)
    end = min(len(text), keyword_pos + len(keyword) + context_chars)

    context = text[start:end]

    # Add ellipsis if truncated
    if start > 0:
        context = "..." + context
    if end < len(text):
        context = context + "..."

    return context
```

## Sample Size Extraction

### Algorithm

1. **Pattern matching:** Use regex to find sample size mentions
   - "n = 450"
   - "N=450"
   - "450 participants"
   - "sample size of 450"
2. **Extract largest number:** Multiple mentions → take largest (usually total sample size)
3. **Logarithmic scoring:** Apply formula from config
4. **Power calculation detection:** Simple keyword matching
5. **Confidence interval detection:** Check for CI reporting
6. **Audit trail:** Record extracted values and calculations

### Regex Patterns

```python
SAMPLE_SIZE_PATTERNS = [
    r'n\s*=\s*(\d+)',  # n = 450
    r'N\s*=\s*(\d+)',  # N = 450
    r'(\d+)\s+participants',  # 450 participants
    r'(\d+)\s+subjects',  # 450 subjects
    r'(\d+)\s+patients',  # 450 patients
    r'sample\s+size\s+of\s+(\d+)',  # sample size of 450
    r'total\s+of\s+(\d+)\s+participants',  # total of 450 participants
    r'enrolled\s+(\d+)\s+participants',  # enrolled 450 participants
]

POWER_CALC_KEYWORDS = [
    'power calculation',
    'power analysis',
    'sample size calculation',
    'calculated sample size',
    'statistical power'
]

CI_KEYWORDS = [
    'confidence interval',
    'CI',
    '95% CI',
    'confidence intervals'
]
```

### Implementation

```python
import re
import math
from typing import Optional, List, Tuple


def _extract_sample_size(self, document: dict) -> DimensionScore:
    """
    Extract sample size and calculate score.

    Uses regex patterns to find sample size mentions, applies logarithmic
    scoring, and adds bonuses for power calculation and CI reporting.

    Args:
        document: Document dict with 'abstract' and optional 'methods_text' fields

    Returns:
        DimensionScore for sample size with audit trail
    """
    # Get text to search
    abstract = document.get('abstract', '')
    methods = document.get('methods_text', '')
    search_text = f"{abstract} {methods}"

    # Extract sample size
    sample_size = self._find_sample_size(search_text)

    if sample_size is None:
        # No sample size found
        dimension_score = DimensionScore(
            dimension_name='sample_size',
            score=0.0
        )
        dimension_score.add_detail(
            component='extracted_n',
            value='not_found',
            contribution=0.0,
            reasoning='No sample size could be extracted from text'
        )
        return dimension_score

    # Calculate base score using logarithmic scaling
    base_score = self._calculate_sample_size_score(sample_size)

    # Create dimension score
    dimension_score = DimensionScore(
        dimension_name='sample_size',
        score=base_score
    )

    # Add base score detail
    dimension_score.add_detail(
        component='extracted_n',
        value=str(sample_size),
        contribution=base_score,
        reasoning=f"Log10({sample_size}) * {self.config['sample_size_scoring']['log_multiplier']} = {base_score:.2f}"
    )

    # Check for power calculation
    if self._has_power_calculation(search_text):
        power_bonus = self.config['sample_size_scoring']['power_calculation_bonus']
        dimension_score.score = min(10.0, dimension_score.score + power_bonus)
        dimension_score.add_detail(
            component='power_calculation',
            value='yes',
            contribution=power_bonus,
            evidence=self._find_power_calc_context(search_text),
            reasoning=f'Power calculation mentioned, bonus +{power_bonus}'
        )

    # Check for confidence interval reporting
    if self._has_ci_reporting(search_text):
        ci_bonus = self.config['sample_size_scoring']['ci_reported_bonus']
        dimension_score.score = min(10.0, dimension_score.score + ci_bonus)
        dimension_score.add_detail(
            component='ci_reporting',
            value='yes',
            contribution=ci_bonus,
            reasoning=f'Confidence intervals reported, bonus +{ci_bonus}'
        )

    return dimension_score


def _find_sample_size(self, text: str) -> Optional[int]:
    """
    Find sample size in text using regex patterns.

    Returns largest number found (usually total sample size).

    Args:
        text: Text to search

    Returns:
        Sample size (int) or None if not found
    """
    patterns = [
        r'n\s*=\s*(\d+)',
        r'N\s*=\s*(\d+)',
        r'(\d+)\s+participants',
        r'(\d+)\s+subjects',
        r'(\d+)\s+patients',
        r'sample\s+size\s+of\s+(\d+)',
        r'total\s+of\s+(\d+)\s+(?:participants|subjects|patients)',
        r'enrolled\s+(\d+)\s+(?:participants|subjects|patients)',
        r'recruited\s+(\d+)\s+(?:participants|subjects|patients)',
    ]

    found_sizes = []

    for pattern in patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            size = int(match.group(1))
            # Filter out unrealistic values (too small or too large)
            if 5 <= size <= 1000000:  # Reasonable range
                found_sizes.append(size)

    if not found_sizes:
        return None

    # Return largest (usually total sample size)
    return max(found_sizes)


def _calculate_sample_size_score(self, n: int) -> float:
    """
    Calculate sample size score using logarithmic scaling.

    Formula: min(10, log10(n) * log_multiplier)

    Args:
        n: Sample size

    Returns:
        Score (0-10)
    """
    config = self.config['sample_size_scoring']
    log_multiplier = config['log_multiplier']

    if n <= 0:
        return 0.0

    score = math.log10(n) * log_multiplier
    return min(10.0, max(0.0, score))


def _has_power_calculation(self, text: str) -> bool:
    """Check if text mentions power calculation"""
    keywords = [
        'power calculation',
        'power analysis',
        'sample size calculation',
        'calculated sample size',
        'statistical power',
        'power to detect'
    ]

    text_lower = text.lower()
    return any(keyword in text_lower for keyword in keywords)


def _find_power_calc_context(self, text: str) -> str:
    """Find context around power calculation mention"""
    keywords = [
        'power calculation',
        'power analysis',
        'sample size calculation'
    ]

    text_lower = text.lower()
    for keyword in keywords:
        if keyword in text_lower:
            return self._extract_context(text_lower, keyword)

    return ""


def _has_ci_reporting(self, text: str) -> bool:
    """Check if text reports confidence intervals"""
    patterns = [
        r'confidence interval',
        r'\bCI\b',
        r'95%\s*CI',
        r'\[\s*\d+\.?\d*\s*,\s*\d+\.?\d*\s*\]',  # [1.2, 3.4]
        r'\(\s*\d+\.?\d*\s*-\s*\d+\.?\d*\s*\)',  # (1.2-3.4)
    ]

    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True

    return False
```

## Database Integration

### Fetching Document Data

```python
def _get_document(self, document_id: int) -> dict:
    """
    Fetch document from database.

    Gets abstract, title, and full text (if available) for analysis.

    Args:
        document_id: Database ID of document

    Returns:
        Document dict with 'abstract', 'title', 'full_text', etc.
    """
    import psycopg

    with psycopg.connect(
        dbname=os.getenv('POSTGRES_DB', 'knowledgebase'),
        user=os.getenv('POSTGRES_USER'),
        password=os.getenv('POSTGRES_PASSWORD'),
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=os.getenv('POSTGRES_PORT', '5432')
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, title, abstract, full_text, pmid, doi
                FROM public.documents
                WHERE id = %s
            """, (document_id,))

            row = cur.fetchone()
            if not row:
                raise ValueError(f"Document {document_id} not found")

            return {
                'id': row[0],
                'title': row[1],
                'abstract': row[2] or '',
                'full_text': row[3] or '',
                'pmid': row[4],
                'doi': row[5]
            }
```

## Testing

### Create Test File: `tests/test_paper_weight_extractors.py`

```python
"""Tests for rule-based extractors in PaperWeightAssessmentAgent"""

import pytest
from bmlibrarian.agents.paper_weight_agent import PaperWeightAssessmentAgent


@pytest.fixture
def agent():
    """Create agent instance for testing"""
    return PaperWeightAssessmentAgent()


def test_extract_study_type_rct(agent):
    """Test RCT detection"""
    document = {
        'abstract': 'This randomized controlled trial examined the effect of...'
    }

    result = agent._extract_study_type(document)

    assert result.dimension_name == 'study_design'
    assert result.score == 8.0  # RCT baseline
    assert len(result.details) > 0
    assert result.details[0].extracted_value == 'rct'


def test_extract_study_type_priority(agent):
    """Test that systematic review takes priority over RCT"""
    document = {
        'abstract': 'This systematic review of randomized controlled trials...'
    }

    result = agent._extract_study_type(document)

    assert result.score == 10.0  # Systematic review, not RCT
    assert result.details[0].extracted_value == 'systematic_review'


def test_extract_study_type_unknown(agent):
    """Test handling of unknown study type"""
    document = {
        'abstract': 'We examined some data and found interesting results.'
    }

    result = agent._extract_study_type(document)

    assert result.details[0].extracted_value == 'unknown'
    assert result.score == 5.0  # Neutral score


def test_extract_sample_size_basic(agent):
    """Test basic sample size extraction"""
    document = {
        'abstract': 'We enrolled n=450 participants in this study.'
    }

    result = agent._extract_sample_size(document)

    assert result.dimension_name == 'sample_size'
    assert result.details[0].extracted_value == '450'
    # log10(450) * 2 ≈ 5.3
    assert 5.0 <= result.score <= 6.0


def test_extract_sample_size_with_power_calc(agent):
    """Test sample size extraction with power calculation bonus"""
    document = {
        'abstract': 'Sample size was calculated using power analysis. We enrolled n=450 participants.'
    }

    result = agent._extract_sample_size(document)

    # Base score + power calculation bonus (2.0)
    assert result.score > 7.0  # Should be ~7.3
    assert any(d.component == 'power_calculation' for d in result.details)


def test_extract_sample_size_not_found(agent):
    """Test handling when sample size not found"""
    document = {
        'abstract': 'We studied many participants.'
    }

    result = agent._extract_sample_size(document)

    assert result.score == 0.0
    assert result.details[0].extracted_value == 'not_found'


def test_extract_sample_size_multiple_mentions(agent):
    """Test that largest sample size is selected"""
    document = {
        'abstract': 'We screened 1000 participants and enrolled 450 participants in the final analysis.'
    }

    result = agent._extract_sample_size(document)

    # Should extract 1000, not 450
    assert result.details[0].extracted_value == '1000'


def test_calculate_sample_size_score(agent):
    """Test logarithmic sample size scoring"""
    # n=10: log10(10) * 2 = 2.0
    assert agent._calculate_sample_size_score(10) == pytest.approx(2.0, abs=0.1)

    # n=100: log10(100) * 2 = 4.0
    assert agent._calculate_sample_size_score(100) == pytest.approx(4.0, abs=0.1)

    # n=1000: log10(1000) * 2 = 6.0
    assert agent._calculate_sample_size_score(1000) == pytest.approx(6.0, abs=0.1)

    # n=100000: log10(100000) * 2 = 10.0
    assert agent._calculate_sample_size_score(100000) == pytest.approx(10.0, abs=0.1)


def test_has_power_calculation(agent):
    """Test power calculation detection"""
    text_with_power = "Sample size was determined using power calculation to detect..."
    text_without_power = "We enrolled participants between 2020 and 2022."

    assert agent._has_power_calculation(text_with_power) is True
    assert agent._has_power_calculation(text_without_power) is False


def test_has_ci_reporting(agent):
    """Test confidence interval detection"""
    text_with_ci = "The mean difference was 2.5 (95% CI: 1.2, 3.8)"
    text_without_ci = "The mean difference was 2.5"

    assert agent._has_ci_reporting(text_with_ci) is True
    assert agent._has_ci_reporting(text_without_ci) is False
```

### Run Tests
```bash
uv run python -m pytest tests/test_paper_weight_extractors.py -v
```

## Success Criteria
- [ ] `_extract_study_type()` implemented with keyword matching
- [ ] Study type priority hierarchy working correctly
- [ ] `_extract_sample_size()` implemented with regex patterns
- [ ] Logarithmic scoring formula working correctly
- [ ] Power calculation detection working
- [ ] Confidence interval detection working
- [ ] Largest sample size selected when multiple mentions found
- [ ] Context extraction working for evidence text
- [ ] All audit trail details recorded
- [ ] All tests passing

## Performance Expectations
- **Study type extraction:** <10ms per document
- **Sample size extraction:** <10ms per document
- **No LLM calls:** Pure rule-based (fast and deterministic)

## Notes for Future Reference
- **False Positives:** Keyword matching may occasionally misclassify. Battle testing will reveal needed adjustments.
- **Missing Patterns:** If sample sizes are missed, add regex patterns to `SAMPLE_SIZE_PATTERNS`
- **Context Size:** 50 characters before/after keyword provides good balance between brevity and context
- **Largest Sample Size:** Taking max() handles screening vs. enrollment mentions

## Next Step
After rule-based extractors are complete and tested, proceed to **Step 5: PaperWeightAssessmentAgent - LLM-Based Assessors**.
