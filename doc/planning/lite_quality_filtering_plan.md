# Quality Filtering for BMLibrarian Lite - Implementation Plan

## Executive Summary

This plan outlines how to add document quality evaluation and filtering to BMLibrarian Lite while preserving its lightweight nature, easy deployment, and independence from powerful hardware.

### Design Principles
1. **Tiered approach** - Use free/fast methods first, expensive LLM calls only when necessary
2. **Progressive enhancement** - Each tier adds accuracy but is optional
3. **Cost-conscious** - Minimize Claude API calls for large document sets
4. **Configurable** - Users choose their quality/cost tradeoff
5. **Portable** - No new external dependencies or hardware requirements

---

## Current State Analysis

### BMLibrarian Lite Architecture
- **Storage**: ChromaDB (vectors) + SQLite (metadata)
- **Embeddings**: FastEmbed (local, CPU-only, ONNX)
- **LLM**: Anthropic Claude API (cloud)
- **Search**: PubMed E-utilities API

### Full BMLibrarian Quality Assessment
Three complementary agents:
1. **StudyAssessmentAgent** - Pure LLM, evaluates study design, bias, quality (0-10)
2. **PRISMA2020Agent** - LLM + semantic search, evaluates systematic reviews
3. **PaperWeightAssessmentAgent** - Hybrid rule+LLM, weighted score (0-10)

---

## Proposed Solution: Three-Tier Quality Filtering

### Tier 1: Metadata-Based Filtering (Free, Instant)

**What**: Use PubMed publication types and MeSH terms already returned by E-utilities API.

**PubMed Publication Types** (hierarchy):
```
Highest Quality:
- Meta-Analysis
- Systematic Review
- Randomized Controlled Trial
- Practice Guideline
- Guideline

High Quality:
- Clinical Trial, Phase IV
- Clinical Trial, Phase III
- Multicenter Study
- Validation Study
- Comparative Study

Moderate Quality:
- Clinical Trial, Phase II
- Clinical Trial, Phase I
- Observational Study
- Cohort Study (when available)

Lower Quality:
- Case Reports
- Editorial
- Comment
- Letter
- News
- Personal Narrative
```

**Implementation**:
```python
@dataclass
class QualityTier:
    """Quality tier based on publication type."""
    level: int  # 1-5 (5 = highest)
    publication_types: list[str]
    description: str

QUALITY_TIERS = {
    5: QualityTier(5, ["Meta-Analysis", "Systematic Review"], "Systematic evidence synthesis"),
    4: QualityTier(4, ["Randomized Controlled Trial", "Practice Guideline"], "High-level evidence"),
    3: QualityTier(3, ["Clinical Trial", "Multicenter Study", "Comparative Study"], "Controlled studies"),
    2: QualityTier(2, ["Observational Study", "Cohort", "Case-Control"], "Observational evidence"),
    1: QualityTier(1, ["Case Reports", "Editorial", "Letter"], "Anecdotal/opinion"),
}
```

**User-Facing Filter Options**:
- "Only systematic reviews & meta-analyses" (Tier 5)
- "Only RCTs and above" (Tier 4+)
- "Controlled studies and above" (Tier 3+)
- "All primary research" (Tier 2+)
- "No filtering" (all results)

**Cost**: Zero additional API calls
**Speed**: Instant (metadata already fetched)
**Accuracy**: ~70-80% for well-indexed articles

---

### Tier 2: Rule-Based Quality Extraction (Free, Fast)

**What**: Keyword and pattern matching on abstracts to detect quality indicators.

**Adapted from PaperWeightAssessmentAgent's rule-based extraction**:

#### Study Design Detection
```python
STUDY_DESIGN_PATTERNS = {
    "systematic_review": {
        "keywords": ["systematic review", "meta-analysis", "prisma", "cochrane"],
        "exclusions": ["no systematic review", "unlike systematic"],
        "score": 10.0,
        "tier": 5
    },
    "rct": {
        "keywords": ["randomized controlled", "randomised controlled", "rct",
                     "double-blind", "double blind", "placebo-controlled"],
        "exclusions": ["non-randomized", "not randomized", "quasi-randomized"],
        "score": 8.0,
        "tier": 4
    },
    "prospective_cohort": {
        "keywords": ["prospective cohort", "prospective study", "followed for"],
        "exclusions": ["retrospective"],
        "score": 6.0,
        "tier": 3
    },
    "retrospective": {
        "keywords": ["retrospective", "chart review", "medical records"],
        "exclusions": [],
        "score": 5.0,
        "tier": 2
    },
    "case_control": {
        "keywords": ["case-control", "case control", "matched controls"],
        "exclusions": [],
        "score": 4.0,
        "tier": 2
    },
    "cross_sectional": {
        "keywords": ["cross-sectional", "cross sectional", "survey"],
        "exclusions": [],
        "score": 3.0,
        "tier": 2
    },
    "case_series": {
        "keywords": ["case series", "consecutive patients", "patient series"],
        "exclusions": [],
        "score": 2.0,
        "tier": 1
    },
    "case_report": {
        "keywords": ["case report", "case presentation", "we present a case"],
        "exclusions": [],
        "score": 1.0,
        "tier": 1
    }
}
```

#### Quality Indicator Detection
```python
QUALITY_INDICATORS = {
    "blinding": {
        "single_blind": ["single-blind", "single blind", "assessor-blind"],
        "double_blind": ["double-blind", "double blind", "double-masked"],
        "triple_blind": ["triple-blind", "triple blind"]
    },
    "sample_size": {
        # Regex patterns
        "patterns": [
            r"n\s*=\s*(\d{1,7})",
            r"N\s*=\s*(\d{1,7})",
            r"(\d{1,7})\s*(?:participants|patients|subjects|individuals)"
        ]
    },
    "methodology": {
        "intention_to_treat": ["intention-to-treat", "intention to treat", "itt analysis"],
        "power_calculation": ["power calculation", "sample size calculation", "powered to detect"],
        "preregistered": ["clinicaltrials.gov", "prospero", "pre-registered", "preregistered"]
    }
}
```

#### Rule-Based Assessment Output
```python
@dataclass
class RuleBasedAssessment:
    """Results from rule-based quality extraction."""
    study_design: str  # e.g., "rct", "prospective_cohort"
    study_design_score: float  # 0-10
    quality_tier: int  # 1-5

    # Quality indicators detected
    blinding_level: Optional[str]  # "single", "double", "triple", None
    sample_size: Optional[int]
    has_power_calculation: bool
    has_preregistration: bool
    has_itt_analysis: bool

    # Confidence
    confidence: float  # 0-1 based on keyword match strength
    extraction_details: list[str]  # Audit trail of what was found
```

**Cost**: Zero API calls
**Speed**: <100ms per document
**Accuracy**: ~60-70% for study design, higher for specific indicators

---

### Tier 3: LLM-Based Quality Assessment (Cloud API, Detailed)

**What**: Claude API call for comprehensive quality assessment. Used selectively.

**When to Use Tier 3**:
1. User explicitly requests detailed assessment
2. Rule-based extraction has low confidence
3. Document passes initial filters but needs verification
4. Small batch of high-priority documents

**Simplified LiteQualityAgent** (adapted from StudyAssessmentAgent):

```python
class LiteQualityAgent(LiteBaseAgent):
    """Lightweight quality assessment using Claude API."""

    SYSTEM_PROMPT = """You are a research quality assessment expert.
    Evaluate the methodological quality of biomedical research papers.

    IMPORTANT: Extract ONLY information that is ACTUALLY PRESENT in the text.
    DO NOT invent or assume information not explicitly stated.
    If information is unclear or not mentioned, indicate this explicitly."""

    def assess_quality(self, document: LiteDocument) -> QualityAssessment:
        """Assess document quality using LLM."""
        # Truncate abstract to save tokens
        text = (document.abstract or "")[:4000]

        prompt = f"""Assess this research paper's quality:

Title: {document.title}
Abstract: {text}

Provide a JSON response with:
{{
    "study_design": "systematic_review|rct|cohort_prospective|cohort_retrospective|case_control|cross_sectional|case_series|case_report|other",
    "quality_score": 1-10,
    "evidence_level": "1a|1b|2a|2b|3a|3b|4|5",
    "design_characteristics": {{
        "randomized": true/false,
        "controlled": true/false,
        "blinded": "none|single|double|triple",
        "prospective": true/false,
        "multicenter": true/false
    }},
    "sample_size": null or number,
    "strengths": ["list of 2-3 strengths"],
    "limitations": ["list of 2-3 limitations"],
    "confidence": 0.0-1.0
}}"""

        response = self._call_llm(prompt)
        return self._parse_response(response)
```

**Cost**: ~$0.003-0.01 per document (Claude 3.5 Sonnet)
**Speed**: 2-5 seconds per document
**Accuracy**: ~85-95%

---

## Integration Architecture

### New Module Structure

```
src/bmlibrarian/lite/
├── quality/
│   ├── __init__.py
│   ├── data_models.py          # Quality-related dataclasses
│   ├── metadata_filter.py      # Tier 1: PubMed publication type filtering
│   ├── rule_extractor.py       # Tier 2: Rule-based quality extraction
│   ├── quality_agent.py        # Tier 3: LLM-based quality assessment
│   └── quality_manager.py      # Orchestrates all tiers
```

### Data Models

```python
# data_models.py
from dataclasses import dataclass
from enum import Enum
from typing import Optional

class StudyDesign(Enum):
    """Study design classification."""
    SYSTEMATIC_REVIEW = "systematic_review"
    META_ANALYSIS = "meta_analysis"
    RCT = "rct"
    COHORT_PROSPECTIVE = "cohort_prospective"
    COHORT_RETROSPECTIVE = "cohort_retrospective"
    CASE_CONTROL = "case_control"
    CROSS_SECTIONAL = "cross_sectional"
    CASE_SERIES = "case_series"
    CASE_REPORT = "case_report"
    OTHER = "other"

class QualityTier(Enum):
    """Quality tier for filtering."""
    TIER_5_SYNTHESIS = 5      # Systematic reviews, meta-analyses
    TIER_4_EXPERIMENTAL = 4   # RCTs, clinical trials
    TIER_3_CONTROLLED = 3     # Controlled observational studies
    TIER_2_OBSERVATIONAL = 2  # Observational studies
    TIER_1_ANECDOTAL = 1      # Case reports, editorials
    UNCLASSIFIED = 0          # Could not classify

@dataclass
class QualityFilter:
    """User-specified quality filter settings."""
    minimum_tier: QualityTier = QualityTier.UNCLASSIFIED
    require_blinding: bool = False
    require_randomization: bool = False
    minimum_sample_size: Optional[int] = None

    # Assessment depth
    use_metadata_filter: bool = True   # Tier 1
    use_rule_extraction: bool = True   # Tier 2
    use_llm_assessment: bool = False   # Tier 3 (opt-in)
    llm_for_uncertain: bool = True     # Use LLM when rules uncertain

@dataclass
class QualityAssessment:
    """Complete quality assessment result."""
    # Source tier that provided the assessment
    assessment_tier: int  # 1, 2, or 3

    # Classification
    study_design: StudyDesign
    quality_tier: QualityTier
    quality_score: float  # 0-10
    evidence_level: Optional[str]  # Oxford CEBM

    # Characteristics
    is_randomized: Optional[bool]
    is_controlled: Optional[bool]
    is_blinded: Optional[str]  # none/single/double/triple
    is_prospective: Optional[bool]
    is_multicenter: Optional[bool]
    sample_size: Optional[int]

    # Assessment quality
    confidence: float  # 0-1
    extraction_method: str  # "metadata", "rule_based", "llm"
    extraction_details: list[str]  # Audit trail

    # Optional detailed assessment (Tier 3 only)
    strengths: Optional[list[str]] = None
    limitations: Optional[list[str]] = None
```

### Quality Manager (Orchestrator)

```python
# quality_manager.py
class QualityManager:
    """Orchestrates tiered quality assessment."""

    def __init__(
        self,
        config: LiteConfig,
        llm_client: Optional[LLMClient] = None
    ):
        self.config = config
        self.metadata_filter = MetadataFilter()
        self.rule_extractor = RuleBasedExtractor()
        self.quality_agent = LiteQualityAgent(config, llm_client) if llm_client else None

    def assess_document(
        self,
        document: LiteDocument,
        filter_settings: QualityFilter
    ) -> QualityAssessment:
        """
        Assess document quality using tiered approach.

        Tier 1 (metadata) -> Tier 2 (rules) -> Tier 3 (LLM, if enabled)
        """
        # Tier 1: Metadata filtering
        if filter_settings.use_metadata_filter:
            metadata_result = self.metadata_filter.assess(document)
            if metadata_result.confidence >= 0.8:
                return metadata_result

        # Tier 2: Rule-based extraction
        if filter_settings.use_rule_extraction:
            rule_result = self.rule_extractor.assess(document)
            if rule_result.confidence >= 0.7:
                return rule_result

        # Tier 3: LLM assessment (if enabled and needed)
        if filter_settings.use_llm_assessment or (
            filter_settings.llm_for_uncertain and
            rule_result.confidence < 0.5
        ):
            if self.quality_agent:
                return self.quality_agent.assess_quality(document)

        # Return best available result
        return rule_result or metadata_result

    def filter_documents(
        self,
        documents: list[LiteDocument],
        filter_settings: QualityFilter,
        progress_callback: Optional[Callable] = None
    ) -> tuple[list[LiteDocument], list[QualityAssessment]]:
        """
        Filter documents based on quality criteria.

        Returns:
            Tuple of (filtered_documents, assessments)
        """
        results = []
        assessments = []

        for i, doc in enumerate(documents):
            assessment = self.assess_document(doc, filter_settings)
            assessments.append(assessment)

            if self._passes_filter(assessment, filter_settings):
                results.append(doc)

            if progress_callback:
                progress_callback(i + 1, len(documents), assessment)

        return results, assessments

    def _passes_filter(
        self,
        assessment: QualityAssessment,
        settings: QualityFilter
    ) -> bool:
        """Check if assessment passes filter criteria."""
        # Tier check
        if assessment.quality_tier.value < settings.minimum_tier.value:
            return False

        # Blinding requirement
        if settings.require_blinding:
            if assessment.is_blinded in [None, "none"]:
                return False

        # Randomization requirement
        if settings.require_randomization:
            if not assessment.is_randomized:
                return False

        # Sample size requirement
        if settings.minimum_sample_size:
            if assessment.sample_size is None:
                return False
            if assessment.sample_size < settings.minimum_sample_size:
                return False

        return True
```

---

## GUI Integration

### New Quality Filter Panel

Add to `systematic_review_tab.py`:

```python
class QualityFilterPanel(QFrame):
    """Panel for configuring quality filters."""

    filterChanged = Signal(QualityFilter)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Header with expand/collapse
        header = QHBoxLayout()
        self.toggle_btn = QPushButton("Quality Filters")
        self.toggle_btn.setCheckable(True)
        header.addWidget(self.toggle_btn)
        layout.addLayout(header)

        # Filter content (collapsible)
        self.content = QFrame()
        content_layout = QVBoxLayout(self.content)

        # Minimum tier dropdown
        tier_layout = QHBoxLayout()
        tier_layout.addWidget(QLabel("Minimum study quality:"))
        self.tier_combo = QComboBox()
        self.tier_combo.addItems([
            "No filter (include all)",
            "Primary research only (exclude editorials)",
            "Controlled studies (cohort+)",
            "High-quality evidence (RCT+)",
            "Systematic evidence only (SR/MA)"
        ])
        tier_layout.addWidget(self.tier_combo)
        content_layout.addLayout(tier_layout)

        # Checkboxes for specific requirements
        self.require_blinding = QCheckBox("Require blinding (single/double/triple)")
        self.require_randomization = QCheckBox("Require randomization")
        content_layout.addWidget(self.require_blinding)
        content_layout.addWidget(self.require_randomization)

        # Sample size filter
        sample_layout = QHBoxLayout()
        self.require_sample_size = QCheckBox("Minimum sample size:")
        self.sample_size_spin = QSpinBox()
        self.sample_size_spin.setRange(0, 100000)
        self.sample_size_spin.setValue(0)
        sample_layout.addWidget(self.require_sample_size)
        sample_layout.addWidget(self.sample_size_spin)
        content_layout.addLayout(sample_layout)

        # LLM assessment option
        self.use_llm = QCheckBox("Use AI for detailed assessment (slower, costs API tokens)")
        content_layout.addWidget(self.use_llm)

        layout.addWidget(self.content)
        self.content.setVisible(False)

        # Connect signals
        self.toggle_btn.toggled.connect(self.content.setVisible)
        self.tier_combo.currentIndexChanged.connect(self._emit_filter)
        # ... connect other widgets

    def get_filter(self) -> QualityFilter:
        """Get current filter settings."""
        tier_map = {
            0: QualityTier.UNCLASSIFIED,
            1: QualityTier.TIER_2_OBSERVATIONAL,
            2: QualityTier.TIER_3_CONTROLLED,
            3: QualityTier.TIER_4_EXPERIMENTAL,
            4: QualityTier.TIER_5_SYNTHESIS,
        }

        return QualityFilter(
            minimum_tier=tier_map[self.tier_combo.currentIndex()],
            require_blinding=self.require_blinding.isChecked(),
            require_randomization=self.require_randomization.isChecked(),
            minimum_sample_size=self.sample_size_spin.value() if self.require_sample_size.isChecked() else None,
            use_llm_assessment=self.use_llm.isChecked()
        )
```

### Quality Badge in Document Cards

Show quality assessment on document cards:

```python
class QualityBadge(QLabel):
    """Visual badge showing quality tier."""

    TIER_COLORS = {
        5: "#4CAF50",  # Green - systematic
        4: "#2196F3",  # Blue - RCT
        3: "#FF9800",  # Orange - controlled
        2: "#9E9E9E",  # Gray - observational
        1: "#F44336",  # Red - anecdotal
        0: "#BDBDBD",  # Light gray - unknown
    }

    TIER_LABELS = {
        5: "SR/MA",
        4: "RCT",
        3: "Controlled",
        2: "Observational",
        1: "Case/Opinion",
        0: "?",
    }

    def __init__(self, tier: QualityTier, parent=None):
        super().__init__(parent)
        self.setText(self.TIER_LABELS[tier.value])
        self.setStyleSheet(f"""
            background-color: {self.TIER_COLORS[tier.value]};
            color: white;
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 10px;
            font-weight: bold;
        """)
```

---

## Workflow Integration

### Modified Search Workflow

```
User Research Question
        ↓
[1] Query Conversion (unchanged)
        ↓
[2] PubMed Search (unchanged)
        ↓
[NEW] Quality Filtering
    ├── Tier 1: Filter by publication types (instant)
    ├── Tier 2: Rule-based extraction on remaining (fast)
    └── Tier 3: LLM assessment for uncertain cases (if enabled)
        ↓
[3] Relevance Scoring (only quality-filtered docs)
        ↓
[4] Citation Extraction (unchanged)
        ↓
[5] Report Generation (include quality info in citations)
```

### Report Enhancement

Include quality information in generated reports:

```markdown
## Evidence Summary

This review synthesizes evidence from **12 studies**:
- 2 systematic reviews/meta-analyses (highest quality)
- 4 randomized controlled trials
- 6 observational studies

### Key Findings

[Smith et al., 2023](docid:12345) (**RCT**, n=450, double-blind) found that...

[Johnson et al., 2022](docid:12346) (**Systematic Review**, 23 studies) concluded...
```

---

## Configuration

### New Config Options

```json
{
  "quality_filtering": {
    "enabled": true,
    "default_minimum_tier": 0,
    "default_use_llm": false,
    "llm_confidence_threshold": 0.5,
    "show_quality_badges": true,
    "include_quality_in_reports": true
  }
}
```

### Constants Addition

```python
# constants.py additions
DEFAULT_MINIMUM_QUALITY_TIER = 0  # No filtering
DEFAULT_LLM_CONFIDENCE_THRESHOLD = 0.5
DEFAULT_SHOW_QUALITY_BADGES = True
```

---

## Implementation Phases

### Phase 1: Core Quality Module (Week 1)
1. Create `quality/` module structure
2. Implement data models (`data_models.py`)
3. Implement Tier 1 metadata filter (`metadata_filter.py`)
4. Implement Tier 2 rule extractor (`rule_extractor.py`)
5. Unit tests for Tier 1 and 2

### Phase 2: LLM Integration (Week 2)
1. Implement Tier 3 quality agent (`quality_agent.py`)
2. Implement quality manager orchestrator (`quality_manager.py`)
3. Integration tests for full tiered approach
4. Add configuration options

### Phase 3: GUI Integration (Week 3)
1. Create QualityFilterPanel widget
2. Add quality badges to document cards
3. Integrate with systematic review workflow
4. Update settings dialog with quality options

### Phase 4: Report Enhancement (Week 4)
1. Modify LiteReportingAgent to include quality information
2. Add evidence summary section
3. Include study characteristics in citations
4. Documentation and user guide

---

## Testing Strategy

### Unit Tests
- Metadata filter accuracy on known publication types
- Rule extractor on sample abstracts with known study designs
- LLM agent response parsing
- Quality manager tier selection logic

### Integration Tests
- Full workflow with quality filtering
- GUI filter changes propagate correctly
- Report generation includes quality info

### Validation Set
Create curated set of ~100 abstracts with known study designs for validation:
- 10 systematic reviews
- 20 RCTs
- 20 cohort studies
- 20 case-control studies
- 20 case reports
- 10 editorials/letters

---

## Cost Analysis

### API Cost per Search Session

| Scenario | Documents | Tier 3 Calls | Est. Cost |
|----------|-----------|--------------|-----------|
| No LLM filtering | 50 | 0 | $0.00 |
| LLM for uncertain (20%) | 50 | 10 | $0.03-0.10 |
| Full LLM assessment | 50 | 50 | $0.15-0.50 |

**Recommendation**: Default to Tier 1+2 only, with LLM opt-in for detailed assessment.

---

## Future Enhancements

### Potential Phase 5+ Features

1. **PRISMA-Lite Assessment**
   - Simplified systematic review quality check
   - Only for documents classified as SR/MA
   - 10-item abbreviated checklist

2. **Bias Risk Visualization**
   - Traffic light display (low/unclear/high)
   - Per-document bias indicators

3. **Quality Score Caching**
   - Store assessments in SQLite
   - Reuse for repeated searches

4. **Custom Quality Criteria**
   - User-defined keyword patterns
   - Domain-specific quality rules

5. **Export Quality Report**
   - CSV export of quality assessments
   - PRISMA flow diagram generation

---

## Summary

This plan provides a pragmatic approach to adding quality filtering to BMLibrarian Lite:

1. **Preserves lightweight nature** - No new heavy dependencies
2. **Cost-effective** - Free tiers handle most cases, LLM is opt-in
3. **Progressively accurate** - Higher tiers add precision
4. **User-configurable** - Researchers choose their quality/speed tradeoff
5. **Transparent** - Quality badges and audit trails show reasoning

The tiered approach (metadata → rules → LLM) matches how researchers naturally filter literature: quick scan of publication types, then deeper read of promising abstracts, then detailed quality assessment of key papers.
