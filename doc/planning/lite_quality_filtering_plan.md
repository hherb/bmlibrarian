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

## Proposed Solution: Two-Tier Quality Filtering

### Why Not Rule-Based Keyword Matching?

**REJECTED APPROACH**: Rule-based keyword extraction has proven unreliable because:
- Documents frequently mention OTHER studies' methodologies in their abstracts
- Example: "Unlike the RCT by Smith et al., our observational study..." would incorrectly match "RCT"
- Example: "Previous systematic reviews have not addressed..." would incorrectly match "systematic review"
- Exclusion patterns cannot reliably handle all variations of context
- False positive rate too high for quality filtering decisions

**ADOPTED APPROACH**: Use LLM for all study design classification, with two tiers:
1. **Tier 1**: PubMed metadata (free, instant) - reliable when available
2. **Tier 2**: Fast LLM classification (cheap, accurate) - handles all cases

---

### Tier 1: Metadata-Based Filtering (Free, Instant)

**What**: Use PubMed publication types assigned by NLM indexers (already in E-utilities response).

**PubMed Publication Types** (hierarchy):
```
Highest Quality (Tier 5):
- Meta-Analysis
- Systematic Review
- Randomized Controlled Trial
- Practice Guideline
- Guideline

High Quality (Tier 4):
- Clinical Trial, Phase IV
- Clinical Trial, Phase III
- Multicenter Study
- Validation Study
- Comparative Study

Moderate Quality (Tier 3):
- Clinical Trial, Phase II
- Clinical Trial, Phase I
- Observational Study
- Cohort Study (when available)

Lower Quality (Tier 2):
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
class QualityTierMapping:
    """Quality tier based on publication type."""
    level: int  # 1-5 (5 = highest)
    publication_types: list[str]
    description: str

PUBMED_TYPE_TO_TIER = {
    5: QualityTierMapping(5, ["Meta-Analysis", "Systematic Review"], "Systematic evidence synthesis"),
    4: QualityTierMapping(4, ["Randomized Controlled Trial", "Practice Guideline"], "High-level evidence"),
    3: QualityTierMapping(3, ["Clinical Trial", "Multicenter Study", "Comparative Study"], "Controlled studies"),
    2: QualityTierMapping(2, ["Observational Study", "Cohort", "Case-Control"], "Observational evidence"),
    1: QualityTierMapping(1, ["Case Reports", "Editorial", "Letter"], "Anecdotal/opinion"),
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
**Accuracy**: ~85-95% for well-indexed articles (NLM indexers are experts)
**Limitation**: Not all articles have publication type assigned; newer articles may lack indexing

---

### Tier 2: Fast LLM Classification (Claude Haiku - Cheap, Accurate)

**What**: Use Claude Haiku (fastest, cheapest Claude model) for study design classification when PubMed metadata is missing or insufficient.

**When Used**:
- PubMed publication type not assigned (newer articles, preprints)
- User wants to verify/override PubMed classification
- User enables "AI-verified quality filtering"

**Why Haiku?**:
- **Cost**: ~$0.00025 per abstract (~400 tokens input, 50 tokens output)
- **Speed**: ~0.5-1 second per document
- **Accuracy**: ~90-95% for study design classification (simple, focused task)
- **50 documents**: ~$0.0125 total (negligible)

**LiteStudyClassifier** (minimal, focused prompt):

```python
class LiteStudyClassifier(LiteBaseAgent):
    """Fast study design classification using Claude Haiku."""

    # Use Haiku for speed and cost
    DEFAULT_MODEL = "claude-3-haiku-20240307"

    SYSTEM_PROMPT = """You classify biomedical research papers by study design.
    Focus ONLY on what study design THIS paper used - ignore any other studies mentioned.
    Be concise. Return only the requested JSON."""

    def classify(self, document: LiteDocument) -> StudyClassification:
        """Classify study design using fast LLM."""
        # Short prompt for speed
        prompt = f"""Classify THIS paper's study design:

Title: {document.title}
Abstract: {(document.abstract or "")[:2000]}

Return JSON:
{{
    "study_design": "systematic_review|meta_analysis|rct|cohort_prospective|cohort_retrospective|case_control|cross_sectional|case_series|case_report|editorial|other",
    "is_randomized": true/false/null,
    "is_blinded": "none|single|double|triple|null",
    "sample_size": number or null,
    "confidence": 0.0-1.0
}}

IMPORTANT: Classify what THIS study did, not studies it references."""

        response = self._call_llm(prompt, model=self.DEFAULT_MODEL)
        return self._parse_response(response)
```

**Cost Comparison**:
| Model | Input ($/1M tokens) | Output ($/1M tokens) | Per Abstract |
|-------|---------------------|----------------------|--------------|
| Haiku | $0.25 | $1.25 | ~$0.00025 |
| Sonnet | $3.00 | $15.00 | ~$0.003 |
| Opus | $15.00 | $75.00 | ~$0.015 |

**Recommendation**: Use Haiku for classification, Sonnet only for detailed assessment.

---

### Tier 3 (Optional): Detailed Quality Assessment (Claude Sonnet)

**What**: Comprehensive quality assessment with strengths, limitations, bias evaluation.

**When Used**:
- User explicitly requests detailed assessment
- Preparing evidence tables for systematic reviews
- Generating quality summary for reports

**LiteQualityAgent** (full assessment):

```python
class LiteQualityAgent(LiteBaseAgent):
    """Comprehensive quality assessment using Claude Sonnet."""

    DEFAULT_MODEL = "claude-sonnet-4-20250514"

    SYSTEM_PROMPT = """You are a research quality assessment expert.
    Evaluate the methodological quality of biomedical research papers.

    IMPORTANT: Extract ONLY information that is ACTUALLY PRESENT in the text.
    DO NOT invent or assume information not explicitly stated.
    If information is unclear or not mentioned, indicate this explicitly."""

    def assess_quality(self, document: LiteDocument) -> QualityAssessment:
        """Full quality assessment using LLM."""
        text = (document.abstract or "")[:4000]

        prompt = f"""Assess this research paper's methodological quality:

Title: {document.title}
Abstract: {text}

Provide a JSON response:
{{
    "study_design": "systematic_review|meta_analysis|rct|cohort_prospective|cohort_retrospective|case_control|cross_sectional|case_series|case_report|editorial|other",
    "quality_score": 1-10,
    "evidence_level": "1a|1b|2a|2b|3a|3b|4|5",
    "design_characteristics": {{
        "randomized": true/false/null,
        "controlled": true/false/null,
        "blinded": "none|single|double|triple|null",
        "prospective": true/false/null,
        "multicenter": true/false/null
    }},
    "sample_size": null or number,
    "bias_risk": {{
        "selection": "low|unclear|high",
        "performance": "low|unclear|high",
        "detection": "low|unclear|high",
        "attrition": "low|unclear|high",
        "reporting": "low|unclear|high"
    }},
    "strengths": ["2-3 methodological strengths"],
    "limitations": ["2-3 methodological limitations"],
    "confidence": 0.0-1.0
}}

Focus on THIS study's methodology, not studies it references."""

        response = self._call_llm(prompt)
        return self._parse_response(response)
```

**Cost**: ~$0.003-0.005 per document (Claude Sonnet)
**Speed**: 2-4 seconds per document
**Accuracy**: ~90-95% with detailed breakdown

---

## Integration Architecture

### New Module Structure

```
src/bmlibrarian/lite/
├── quality/
│   ├── __init__.py
│   ├── data_models.py          # Quality-related dataclasses
│   ├── metadata_filter.py      # Tier 1: PubMed publication type filtering
│   ├── study_classifier.py     # Tier 2: Fast LLM classification (Haiku)
│   ├── quality_agent.py        # Tier 3: Detailed LLM assessment (Sonnet, optional)
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
    use_metadata_only: bool = False     # Tier 1 only (free, fast, less complete)
    use_llm_classification: bool = True # Tier 2: Haiku for unclassified docs
    use_detailed_assessment: bool = False  # Tier 3: Sonnet for full quality report

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
        self.study_classifier = LiteStudyClassifier(config, llm_client) if llm_client else None
        self.quality_agent = LiteQualityAgent(config, llm_client) if llm_client else None

    def assess_document(
        self,
        document: LiteDocument,
        filter_settings: QualityFilter
    ) -> QualityAssessment:
        """
        Assess document quality using tiered approach.

        Tier 1 (metadata) -> Tier 2 (Haiku classification) -> Tier 3 (Sonnet detailed, if enabled)
        """
        # Tier 1: Metadata filtering (always try first - it's free)
        metadata_result = self.metadata_filter.assess(document)

        # If metadata provides confident classification and user accepts metadata-only
        if filter_settings.use_metadata_only:
            return metadata_result

        # If metadata has high confidence, use it (NLM indexers are reliable)
        if metadata_result.confidence >= 0.9 and metadata_result.quality_tier != QualityTier.UNCLASSIFIED:
            # Optionally enhance with LLM for detailed assessment
            if filter_settings.use_detailed_assessment and self.quality_agent:
                return self.quality_agent.assess_quality(document)
            return metadata_result

        # Tier 2: Fast LLM classification (Haiku) for unclassified or low-confidence docs
        if filter_settings.use_llm_classification and self.study_classifier:
            classification = self.study_classifier.classify(document)

            # Tier 3: Detailed assessment if requested
            if filter_settings.use_detailed_assessment and self.quality_agent:
                return self.quality_agent.assess_quality(document)

            # Convert classification to assessment
            return self._classification_to_assessment(classification)

        # Fallback to metadata result
        return metadata_result

    def _classification_to_assessment(
        self,
        classification: StudyClassification
    ) -> QualityAssessment:
        """Convert fast classification to full assessment structure."""
        return QualityAssessment(
            assessment_tier=2,
            study_design=classification.study_design,
            quality_tier=self._design_to_tier(classification.study_design),
            quality_score=self._design_to_score(classification.study_design),
            evidence_level=None,  # Not available from fast classification
            is_randomized=classification.is_randomized,
            is_controlled=None,
            is_blinded=classification.is_blinded,
            is_prospective=None,
            is_multicenter=None,
            sample_size=classification.sample_size,
            confidence=classification.confidence,
            extraction_method="llm_haiku",
            extraction_details=["Fast classification via Claude Haiku"]
        )

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
    ├── Tier 1: Filter by PubMed publication types (instant, free)
    ├── Tier 2: Haiku classification for unclassified docs (~$0.00025/doc)
    └── Tier 3: Sonnet detailed assessment (optional, ~$0.003/doc)
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
    "use_metadata_only": false,
    "use_llm_classification": true,
    "use_detailed_assessment": false,
    "classification_model": "claude-3-haiku-20240307",
    "assessment_model": "claude-sonnet-4-20250514",
    "show_quality_badges": true,
    "include_quality_in_reports": true
  }
}
```

### Constants Addition

```python
# constants.py additions
DEFAULT_MINIMUM_QUALITY_TIER = 0  # No filtering
DEFAULT_USE_METADATA_ONLY = False
DEFAULT_USE_LLM_CLASSIFICATION = True
DEFAULT_USE_DETAILED_ASSESSMENT = False
DEFAULT_CLASSIFICATION_MODEL = "claude-3-haiku-20240307"
DEFAULT_ASSESSMENT_MODEL = "claude-sonnet-4-20250514"
DEFAULT_SHOW_QUALITY_BADGES = True
```

---

## Implementation Phases

### Phase 1: Core Quality Module
1. Create `quality/` module structure
2. Implement data models (`data_models.py`)
3. Implement Tier 1 metadata filter (`metadata_filter.py`)
4. Unit tests for metadata filtering

### Phase 2: LLM Classification
1. Implement Tier 2 study classifier (`study_classifier.py`) using Haiku
2. Implement Tier 3 quality agent (`quality_agent.py`) using Sonnet
3. Implement quality manager orchestrator (`quality_manager.py`)
4. Integration tests for tiered approach
5. Add configuration options

### Phase 3: GUI Integration
1. Create QualityFilterPanel widget
2. Add quality badges to document cards
3. Integrate with systematic review workflow
4. Update settings dialog with quality options

### Phase 4: Report Enhancement
1. Modify LiteReportingAgent to include quality information
2. Add evidence summary section
3. Include study characteristics in citations
4. Documentation and user guide

---

## Testing Strategy

### Unit Tests
- Metadata filter accuracy on known publication types
- LLM classifier response parsing and error handling
- Quality agent response parsing and validation
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

**Critical Test Cases** (to avoid keyword matching failures):
- Abstracts that MENTION RCTs but ARE NOT RCTs
- Abstracts that DISCUSS systematic reviews but ARE observational studies
- Abstracts that COMPARE to double-blind studies but ARE open-label

---

## Cost Analysis

### API Cost per Search Session

| Scenario | Documents | Haiku Calls | Sonnet Calls | Est. Cost |
|----------|-----------|-------------|--------------|-----------|
| Metadata only | 50 | 0 | 0 | $0.00 |
| Metadata + Haiku (30% need classification) | 50 | 15 | 0 | ~$0.004 |
| Full Haiku classification | 50 | 50 | 0 | ~$0.0125 |
| Haiku + Sonnet detailed | 50 | 50 | 50 | ~$0.16 |

**Default Recommendation**: Metadata + Haiku for unclassified (~$0.004/session)
- Fast and cheap enough to always enable
- Sonnet detailed assessment opt-in for systematic reviews

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

1. **Preserves lightweight nature** - No new heavy dependencies, uses existing Claude API
2. **Reliable classification** - LLM understands context, avoids keyword matching failures
3. **Cost-effective** - Haiku classification is ~$0.00025/doc, negligible for typical searches
4. **User-configurable** - Researchers choose metadata-only, Haiku, or full Sonnet assessment
5. **Transparent** - Quality badges and audit trails show classification reasoning

### Why LLM Over Keywords?

The critical insight is that **keyword matching fails on scientific abstracts** because:
- Authors frequently reference other studies' methodologies
- Context determines meaning: "unlike the RCT..." vs "we conducted an RCT..."
- Exclusion patterns cannot capture all linguistic variations

LLM classification solves this by understanding semantic context. With Haiku's low cost (~$0.01 per 50 documents), it's practical to use LLM for all classification rather than maintaining fragile keyword rules.

### Tiered Approach

```
Tier 1: PubMed Metadata (free, instant)
    ↓ (if unclassified or low confidence)
Tier 2: Claude Haiku (cheap, accurate)
    ↓ (if detailed assessment requested)
Tier 3: Claude Sonnet (comprehensive, optional)
```

This matches researcher workflow: trust NLM indexers when available, use AI for the rest.
