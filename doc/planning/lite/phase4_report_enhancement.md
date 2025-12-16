# Phase 4: Report Enhancement

## Overview

This phase enhances generated reports with quality information:
1. Evidence summary section at report start
2. Study quality annotations in citations
3. Quality-aware report structure
4. Export with quality metadata

## Prerequisites

- Phases 1-3 complete (quality module and GUI implemented)
- Understanding of LiteReportingAgent architecture

---

## Step 1: Modify Citation Format

### 1.1 Update citation data model

Add quality information to citations.

```python
# In src/bmlibrarian/lite/data_models.py

@dataclass
class LiteCitation:
    """Citation with quality metadata."""

    document: LiteDocument
    passage: str
    relevance_explanation: str

    # Quality information (optional)
    assessment: Optional[QualityAssessment] = None

    @property
    def formatted_reference(self) -> str:
        """Format citation for report."""
        doc = self.document
        authors = doc.authors[0] if doc.authors else "Unknown"
        if len(doc.authors) > 1:
            authors += " et al."
        year = doc.year or "n.d."
        return f"{authors}, {year}"

    @property
    def quality_annotation(self) -> str:
        """Get quality annotation for inline use."""
        if not self.assessment:
            return ""

        parts = []

        # Study design
        design = self.assessment.study_design.value.replace("_", " ").title()
        if design not in ["Unknown", "Other"]:
            parts.append(design)

        # Sample size
        if self.assessment.sample_size:
            parts.append(f"n={self.assessment.sample_size:,}")

        # Blinding
        if self.assessment.is_blinded and self.assessment.is_blinded != "none":
            parts.append(f"{self.assessment.is_blinded}-blind")

        if parts:
            return f"**{', '.join(parts)}**"
        return ""
```

---

## Step 2: Create Evidence Summary Generator

### 2.1 File: `src/bmlibrarian/lite/quality/evidence_summary.py`

```python
# src/bmlibrarian/lite/quality/evidence_summary.py
"""
Generate evidence summary section for reports.

Creates a structured overview of the evidence base including
study design distribution and quality statistics.
"""

from typing import Optional
from collections import Counter

from .data_models import (
    StudyDesign,
    QualityTier,
    QualityAssessment,
    DESIGN_TO_TIER,
)


class EvidenceSummaryGenerator:
    """Generates evidence summary sections for reports."""

    # Evidence level descriptions (Oxford CEBM inspired)
    TIER_DESCRIPTIONS = {
        QualityTier.TIER_5_SYNTHESIS: "systematic reviews and meta-analyses",
        QualityTier.TIER_4_EXPERIMENTAL: "randomized controlled trials",
        QualityTier.TIER_3_CONTROLLED: "controlled observational studies",
        QualityTier.TIER_2_OBSERVATIONAL: "observational studies",
        QualityTier.TIER_1_ANECDOTAL: "case reports and expert opinion",
    }

    DESIGN_LABELS = {
        StudyDesign.SYSTEMATIC_REVIEW: "systematic reviews",
        StudyDesign.META_ANALYSIS: "meta-analyses",
        StudyDesign.RCT: "randomized controlled trials",
        StudyDesign.GUIDELINE: "clinical guidelines",
        StudyDesign.COHORT_PROSPECTIVE: "prospective cohort studies",
        StudyDesign.COHORT_RETROSPECTIVE: "retrospective cohort studies",
        StudyDesign.CASE_CONTROL: "case-control studies",
        StudyDesign.CROSS_SECTIONAL: "cross-sectional studies",
        StudyDesign.CASE_SERIES: "case series",
        StudyDesign.CASE_REPORT: "case reports",
        StudyDesign.EDITORIAL: "editorials",
        StudyDesign.LETTER: "letters",
    }

    def generate_summary(
        self,
        assessments: list[QualityAssessment],
        include_quality_notes: bool = True
    ) -> str:
        """
        Generate markdown evidence summary.

        Args:
            assessments: List of quality assessments for included documents
            include_quality_notes: Whether to include quality interpretation notes

        Returns:
            Markdown-formatted evidence summary section
        """
        if not assessments:
            return ""

        lines = ["## Evidence Summary", ""]

        # Count by tier
        tier_counts = Counter(a.quality_tier for a in assessments)

        # Count by design
        design_counts = Counter(a.study_design for a in assessments)

        # Overall statement
        total = len(assessments)
        lines.append(
            f"This review synthesizes evidence from **{total} "
            f"{'study' if total == 1 else 'studies'}**:"
        )
        lines.append("")

        # List by quality tier (highest first)
        tier_order = [
            QualityTier.TIER_5_SYNTHESIS,
            QualityTier.TIER_4_EXPERIMENTAL,
            QualityTier.TIER_3_CONTROLLED,
            QualityTier.TIER_2_OBSERVATIONAL,
            QualityTier.TIER_1_ANECDOTAL,
        ]

        for tier in tier_order:
            count = tier_counts.get(tier, 0)
            if count > 0:
                # Get specific designs in this tier
                designs_in_tier = [
                    a.study_design for a in assessments
                    if a.quality_tier == tier
                ]
                design_breakdown = Counter(designs_in_tier)

                # Build description
                if len(design_breakdown) == 1:
                    design = list(design_breakdown.keys())[0]
                    desc = self.DESIGN_LABELS.get(design, design.value)
                else:
                    desc = self.TIER_DESCRIPTIONS.get(tier, "studies")

                lines.append(f"- **{count}** {desc}")

        lines.append("")

        # Quality distribution summary
        avg_score = sum(a.quality_score for a in assessments) / total
        high_quality = sum(
            1 for a in assessments
            if a.quality_tier.value >= QualityTier.TIER_4_EXPERIMENTAL.value
        )
        high_quality_pct = (high_quality / total) * 100

        lines.append(
            f"Average quality score: **{avg_score:.1f}/10** | "
            f"High-quality evidence (RCT+): **{high_quality_pct:.0f}%**"
        )
        lines.append("")

        # Quality notes
        if include_quality_notes:
            lines.extend(self._generate_quality_notes(assessments, tier_counts))

        return "\n".join(lines)

    def _generate_quality_notes(
        self,
        assessments: list[QualityAssessment],
        tier_counts: Counter
    ) -> list[str]:
        """Generate interpretive notes about evidence quality."""
        lines = []
        notes = []

        # Check for evidence gaps
        if tier_counts.get(QualityTier.TIER_5_SYNTHESIS, 0) == 0:
            if tier_counts.get(QualityTier.TIER_4_EXPERIMENTAL, 0) == 0:
                notes.append(
                    "No systematic reviews or RCTs were identified; "
                    "conclusions are based on observational evidence."
                )
            else:
                notes.append(
                    "No systematic reviews were identified; "
                    "findings are based primarily on individual RCTs."
                )

        # Check for reliance on low-quality evidence
        low_quality = tier_counts.get(QualityTier.TIER_1_ANECDOTAL, 0)
        if low_quality > len(assessments) * 0.5:
            notes.append(
                "More than half of the evidence comes from case reports "
                "or expert opinion; interpret findings with caution."
            )

        # Check for sample size issues
        with_sample = [a for a in assessments if a.sample_size]
        if with_sample:
            median_n = sorted(a.sample_size for a in with_sample)[len(with_sample) // 2]
            if median_n < 50:
                notes.append(
                    f"Median sample size is {median_n}; small samples may "
                    "limit generalizability."
                )

        if notes:
            lines.append("### Quality Considerations")
            lines.append("")
            for note in notes:
                lines.append(f"- {note}")
            lines.append("")

        return lines

    def generate_study_table(
        self,
        assessments: list[QualityAssessment],
        documents: Optional[list] = None
    ) -> str:
        """
        Generate markdown table of included studies with quality info.

        Args:
            assessments: Quality assessments
            documents: Optional corresponding documents for full metadata

        Returns:
            Markdown table
        """
        if not assessments:
            return ""

        lines = [
            "### Included Studies",
            "",
            "| Study | Design | N | Quality | Confidence |",
            "|-------|--------|---|---------|------------|",
        ]

        for i, assessment in enumerate(assessments):
            # Get study reference if document available
            if documents and i < len(documents):
                doc = documents[i]
                authors = doc.authors[0] if doc.authors else "Unknown"
                year = doc.year or "n.d."
                study = f"{authors}, {year}"
            else:
                study = f"Study {i + 1}"

            design = assessment.study_design.value.replace("_", " ").title()
            n = f"{assessment.sample_size:,}" if assessment.sample_size else "NR"
            quality = f"{assessment.quality_score:.1f}/10"
            confidence = f"{assessment.confidence:.0%}"

            lines.append(f"| {study} | {design} | {n} | {quality} | {confidence} |")

        lines.append("")
        return "\n".join(lines)
```

---

## Step 3: Modify Reporting Agent

### 3.1 Update LiteReportingAgent

Enhance the reporting agent to include quality information.

```python
# In src/bmlibrarian/lite/agents/reporting_agent.py

from ..quality.evidence_summary import EvidenceSummaryGenerator
from ..quality.data_models import QualityAssessment

class LiteReportingAgent(LiteBaseAgent):
    """Reporting agent with quality-aware output."""

    def __init__(self, config: LiteConfig):
        super().__init__(config)
        self.evidence_generator = EvidenceSummaryGenerator()

    def generate_report(
        self,
        question: str,
        citations: list[LiteCitation],
        assessments: Optional[list[QualityAssessment]] = None,
        include_quality_summary: bool = True,
        include_quality_annotations: bool = True
    ) -> str:
        """
        Generate a quality-aware research report.

        Args:
            question: Research question
            citations: List of citations with passages
            assessments: Optional quality assessments (uses citation.assessment if None)
            include_quality_summary: Include evidence summary section
            include_quality_annotations: Include quality info in citations

        Returns:
            Markdown-formatted report
        """
        # Get assessments from citations if not provided
        if assessments is None:
            assessments = [c.assessment for c in citations if c.assessment]

        # Build report sections
        sections = []

        # Title
        sections.append(f"# Research Report\n")
        sections.append(f"**Research Question:** {question}\n")

        # Evidence summary (if enabled and assessments available)
        if include_quality_summary and assessments:
            summary = self.evidence_generator.generate_summary(assessments)
            sections.append(summary)

        # Main content with quality-annotated citations
        content = self._generate_content(
            question,
            citations,
            include_quality_annotations
        )
        sections.append(content)

        # References section
        references = self._generate_references(citations)
        sections.append(references)

        return "\n".join(sections)

    def _generate_content(
        self,
        question: str,
        citations: list[LiteCitation],
        include_quality: bool
    ) -> str:
        """Generate main report content with LLM."""
        # Build citation context for LLM
        citation_texts = []
        for i, citation in enumerate(citations, 1):
            text = f"[{i}] {citation.passage}"

            # Add quality annotation
            if include_quality and citation.assessment:
                qual = citation.quality_annotation
                if qual:
                    text = f"[{i}] ({qual}) {citation.passage}"

            citation_texts.append(text)

        citations_context = "\n\n".join(citation_texts)

        prompt = f"""Synthesize these research findings into a coherent report:

Research Question: {question}

Evidence (with quality annotations where available):
{citations_context}

Instructions:
1. Organize findings thematically, not by source
2. When citing, use format: [1], [2], etc.
3. Highlight the strength of evidence when relevant
4. Note if conclusions rest on limited or low-quality evidence
5. Be objective and avoid overstating findings

Generate the main body of the report (2-4 paragraphs):"""

        response = self._call_llm(prompt)
        return response

    def _generate_references(self, citations: list[LiteCitation]) -> str:
        """Generate references section."""
        lines = ["## References", ""]

        for i, citation in enumerate(citations, 1):
            doc = citation.document
            authors = ", ".join(doc.authors[:3]) if doc.authors else "Unknown"
            if len(doc.authors) > 3:
                authors += " et al."

            year = doc.year or "n.d."
            title = doc.title or "Untitled"
            journal = doc.journal or ""
            pmid = doc.pmid or doc.id

            ref = f"{i}. {authors} ({year}). {title}."
            if journal:
                ref += f" *{journal}*."
            ref += f" PMID: {pmid}"

            # Add quality annotation
            if citation.assessment:
                design = citation.assessment.study_design.value
                design = design.replace("_", " ").title()
                ref += f" [{design}]"

            lines.append(ref)

        lines.append("")
        return "\n".join(lines)
```

---

## Step 4: Enhanced Report Formatting

### 4.1 Quality-aware citation formatting

```python
# In src/bmlibrarian/lite/quality/report_formatter.py
"""
Format reports with quality-aware styling.

Provides utilities for formatting citations and references
with quality information.
"""

from ..data_models import LiteCitation
from .data_models import QualityTier, QualityAssessment


class QualityReportFormatter:
    """Format reports with quality annotations."""

    # Emoji indicators for quality tiers (optional)
    TIER_EMOJI = {
        QualityTier.TIER_5_SYNTHESIS: "🟢",      # Green
        QualityTier.TIER_4_EXPERIMENTAL: "🔵",   # Blue
        QualityTier.TIER_3_CONTROLLED: "🟠",     # Orange
        QualityTier.TIER_2_OBSERVATIONAL: "⚪",  # White
        QualityTier.TIER_1_ANECDOTAL: "🔴",      # Red
        QualityTier.UNCLASSIFIED: "⚫",          # Black
    }

    def __init__(self, use_emoji: bool = False):
        """
        Initialize formatter.

        Args:
            use_emoji: Whether to use emoji quality indicators
        """
        self.use_emoji = use_emoji

    def format_inline_citation(
        self,
        citation: LiteCitation,
        citation_number: int
    ) -> str:
        """
        Format a citation for inline use in text.

        Args:
            citation: The citation to format
            citation_number: Citation reference number

        Returns:
            Formatted citation string
        """
        ref = citation.formatted_reference
        parts = [f"[{ref}]({citation_number})"]

        if citation.assessment:
            qual = self._format_quality_inline(citation.assessment)
            if qual:
                parts.append(qual)

        return " ".join(parts)

    def _format_quality_inline(self, assessment: QualityAssessment) -> str:
        """Format quality annotation for inline use."""
        parts = []

        # Design shorthand
        design_short = {
            "systematic_review": "SR",
            "meta_analysis": "MA",
            "rct": "RCT",
            "cohort_prospective": "prospective",
            "cohort_retrospective": "retrospective",
        }
        design = design_short.get(
            assessment.study_design.value,
            assessment.study_design.value.split("_")[0]
        )

        if design not in ["unknown", "other"]:
            parts.append(design)

        # Sample size
        if assessment.sample_size:
            parts.append(f"n={assessment.sample_size}")

        # Blinding
        if assessment.is_blinded and assessment.is_blinded != "none":
            parts.append(f"{assessment.is_blinded}-blind")

        if parts:
            if self.use_emoji:
                emoji = self.TIER_EMOJI.get(assessment.quality_tier, "")
                return f"{emoji} **{', '.join(parts)}**"
            return f"(**{', '.join(parts)}**)"

        return ""

    def format_reference_entry(
        self,
        citation: LiteCitation,
        number: int
    ) -> str:
        """
        Format a citation for the references section.

        Args:
            citation: The citation to format
            number: Reference number

        Returns:
            Formatted reference entry
        """
        doc = citation.document

        # Authors
        if doc.authors:
            if len(doc.authors) <= 3:
                authors = ", ".join(doc.authors)
            else:
                authors = f"{doc.authors[0]} et al."
        else:
            authors = "Unknown"

        # Year and title
        year = doc.year or "n.d."
        title = doc.title or "Untitled"

        # Journal
        journal = f"*{doc.journal}*" if doc.journal else ""

        # Build reference
        ref = f"{number}. {authors} ({year}). {title}."
        if journal:
            ref += f" {journal}."

        # Add PMID/DOI
        if doc.pmid:
            ref += f" PMID: {doc.pmid}"
        elif doc.doi:
            ref += f" DOI: {doc.doi}"

        # Add quality badge
        if citation.assessment:
            design = citation.assessment.study_design.value
            design_label = design.replace("_", " ").title()
            tier = citation.assessment.quality_tier.value

            if self.use_emoji:
                emoji = self.TIER_EMOJI.get(
                    citation.assessment.quality_tier, ""
                )
                ref += f" {emoji}"
            else:
                ref += f" [{design_label}]"

        return ref
```

---

## Step 5: Export Quality Metadata

### 5.1 Add quality info to JSON export

```python
# In src/bmlibrarian/lite/export.py

import json
from typing import Optional
from pathlib import Path

from .data_models import LiteDocument, LiteCitation
from .quality.data_models import QualityAssessment


class ReportExporter:
    """Export reports with quality metadata."""

    def export_json(
        self,
        output_path: Path,
        question: str,
        citations: list[LiteCitation],
        assessments: list[QualityAssessment],
        report_markdown: str
    ) -> None:
        """
        Export complete report data as JSON.

        Args:
            output_path: Path for JSON output
            question: Research question
            citations: List of citations
            assessments: Quality assessments
            report_markdown: Generated report text
        """
        data = {
            "research_question": question,
            "report": report_markdown,
            "evidence_summary": self._build_evidence_summary(assessments),
            "citations": [
                self._serialize_citation(c) for c in citations
            ],
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _build_evidence_summary(
        self,
        assessments: list[QualityAssessment]
    ) -> dict:
        """Build evidence summary statistics."""
        if not assessments:
            return {}

        from collections import Counter

        tier_counts = Counter(a.quality_tier.name for a in assessments)
        design_counts = Counter(a.study_design.value for a in assessments)

        return {
            "total_studies": len(assessments),
            "by_quality_tier": dict(tier_counts),
            "by_study_design": dict(design_counts),
            "average_quality_score": sum(a.quality_score for a in assessments) / len(assessments),
            "average_confidence": sum(a.confidence for a in assessments) / len(assessments),
        }

    def _serialize_citation(self, citation: LiteCitation) -> dict:
        """Serialize citation with quality info."""
        data = {
            "document": {
                "id": citation.document.id,
                "title": citation.document.title,
                "authors": citation.document.authors,
                "year": citation.document.year,
                "journal": citation.document.journal,
                "pmid": citation.document.pmid,
            },
            "passage": citation.passage,
            "relevance_explanation": citation.relevance_explanation,
        }

        if citation.assessment:
            data["quality"] = {
                "study_design": citation.assessment.study_design.value,
                "quality_tier": citation.assessment.quality_tier.name,
                "quality_score": citation.assessment.quality_score,
                "is_randomized": citation.assessment.is_randomized,
                "is_blinded": citation.assessment.is_blinded,
                "sample_size": citation.assessment.sample_size,
                "confidence": citation.assessment.confidence,
                "assessment_tier": citation.assessment.assessment_tier,
            }

        return data
```

---

## Step 6: Integration with Workflow

### 6.1 Update workflow to pass quality data to reporter

```python
# In src/bmlibrarian/lite/gui/workers.py (or workflow handler)

class ReportGenerationWorker(QThread):
    """Worker for generating quality-aware reports."""

    finished = Signal(str)  # report markdown
    error = Signal(str)

    def __init__(
        self,
        reporting_agent: LiteReportingAgent,
        question: str,
        citations: list[LiteCitation],
        assessments: list[QualityAssessment],
        include_quality: bool = True
    ):
        super().__init__()
        self.reporting_agent = reporting_agent
        self.question = question
        self.citations = citations
        self.assessments = assessments
        self.include_quality = include_quality

    def run(self):
        """Generate report in background."""
        try:
            # Attach assessments to citations
            for citation, assessment in zip(self.citations, self.assessments):
                citation.assessment = assessment

            report = self.reporting_agent.generate_report(
                question=self.question,
                citations=self.citations,
                assessments=self.assessments,
                include_quality_summary=self.include_quality,
                include_quality_annotations=self.include_quality
            )

            self.finished.emit(report)

        except Exception as e:
            self.error.emit(str(e))
```

---

## Example Report Output

After implementing Phase 4, reports will include:

```markdown
# Research Report

**Research Question:** What are the cardiovascular benefits of regular exercise?

## Evidence Summary

This review synthesizes evidence from **12 studies**:

- **2** systematic reviews and meta-analyses
- **4** randomized controlled trials
- **4** prospective cohort studies
- **2** case reports

Average quality score: **7.2/10** | High-quality evidence (RCT+): **50%**

### Quality Considerations

- Findings are based primarily on individual RCTs and observational studies.
- Median sample size is 234; adequate for detecting moderate effects.

## Main Findings

Evidence from multiple RCTs demonstrates that regular aerobic exercise
significantly reduces cardiovascular disease risk [1, 2]. A meta-analysis
of 23 studies (**SR**, 45,000 participants) found a 30% reduction in
major cardiac events among physically active adults [3].

Prospective cohort data (**prospective**, n=12,500) suggests that even
moderate exercise (150 min/week) provides substantial benefits [4].
However, case reports indicate that extreme endurance exercise may
carry some risks [5].

## References

1. Smith J et al. (2023). Exercise and heart health: A randomized trial.
   *JAMA Cardiology*. PMID: 12345678 [RCT]
2. Johnson A et al. (2022). Aerobic training in older adults.
   *Circulation*. PMID: 23456789 [RCT]
3. Williams R et al. (2024). Physical activity and CVD: A systematic review.
   *Lancet*. PMID: 34567890 [Systematic Review]
...
```

---

## Verification Checklist

After implementing Phase 4, verify:

- [ ] Evidence summary generates correctly
- [ ] Quality annotations appear in citations
- [ ] References include study design labels
- [ ] JSON export includes quality metadata
- [ ] Quality notes identify evidence gaps
- [ ] Study table formats correctly
- [ ] Workflow integrates quality into reports

---

## Summary

Phase 4 completes the quality filtering feature by ensuring that quality information flows through to the final output. Users can now:

1. See an evidence summary at the start of each report
2. Understand the quality of each cited study
3. Identify gaps in evidence quality
4. Export quality metadata for further analysis
