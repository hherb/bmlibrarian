"""
Evidence summary generator for quality-aware reports.

Creates structured overview sections showing evidence quality distribution
and interpretive notes about the strength of evidence.
"""

import logging
from collections import Counter
from typing import Optional

from .data_models import (
    StudyDesign,
    QualityTier,
    QualityAssessment,
    DESIGN_LABELS as DATA_MODEL_DESIGN_LABELS,
    TIER_LABELS as DATA_MODEL_TIER_LABELS,
)

logger = logging.getLogger(__name__)


# Descriptions for each quality tier (Oxford CEBM inspired)
# These are lowercase descriptive phrases for use in sentences
TIER_DESCRIPTIONS: dict[QualityTier, str] = {
    QualityTier.TIER_5_SYNTHESIS: "systematic reviews and meta-analyses",
    QualityTier.TIER_4_EXPERIMENTAL: "randomized controlled trials",
    QualityTier.TIER_3_CONTROLLED: "controlled observational studies",
    QualityTier.TIER_2_OBSERVATIONAL: "observational studies",
    QualityTier.TIER_1_ANECDOTAL: "case reports and expert opinion",
    QualityTier.UNCLASSIFIED: "unclassified studies",
}

# Lowercase plural labels for study designs (for use in sentences)
# These are derived from DATA_MODEL_DESIGN_LABELS but in lowercase plural form
DESIGN_LABELS: dict[StudyDesign, str] = {
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
    StudyDesign.COMMENT: "comments",
    StudyDesign.OTHER: "other studies",
    StudyDesign.UNKNOWN: "studies of unknown design",
}

# Threshold for high-quality evidence (Tier 4 and above)
# Using the enum directly for comparison (clearer and type-safe)
HIGH_QUALITY_TIER = QualityTier.TIER_4_EXPERIMENTAL

# Threshold for small sample size warning
SMALL_SAMPLE_SIZE_THRESHOLD = 50

# Threshold for low-quality evidence warning (proportion of total)
LOW_QUALITY_WARNING_THRESHOLD = 0.5

# Threshold for unclassified studies warning (proportion of total)
UNCLASSIFIED_WARNING_THRESHOLD = 0.3


class EvidenceSummaryGenerator:
    """
    Generates evidence summary sections for research reports.

    Creates markdown-formatted summaries showing:
    - Total study count
    - Breakdown by quality tier
    - Average quality metrics
    - Interpretive notes about evidence gaps
    """

    def generate_summary(
        self,
        assessments: list[QualityAssessment],
        include_quality_notes: bool = True
    ) -> str:
        """
        Generate markdown evidence summary section.

        Args:
            assessments: List of quality assessments for included documents
            include_quality_notes: Whether to include interpretive quality notes

        Returns:
            Markdown-formatted evidence summary section
        """
        if not assessments:
            return ""

        lines = ["## Evidence Summary", ""]

        # Count by tier and design
        tier_counts = Counter(a.quality_tier for a in assessments)
        design_counts = Counter(a.study_design for a in assessments)

        # Overall statement
        total = len(assessments)
        study_word = "study" if total == 1 else "studies"
        lines.append(
            f"This review synthesizes evidence from **{total} {study_word}**:"
        )
        lines.append("")

        # List by quality tier (highest first)
        tier_order = [
            QualityTier.TIER_5_SYNTHESIS,
            QualityTier.TIER_4_EXPERIMENTAL,
            QualityTier.TIER_3_CONTROLLED,
            QualityTier.TIER_2_OBSERVATIONAL,
            QualityTier.TIER_1_ANECDOTAL,
            QualityTier.UNCLASSIFIED,
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
                    desc = DESIGN_LABELS.get(design, design.value)
                else:
                    desc = TIER_DESCRIPTIONS.get(tier, "studies")

                lines.append(f"- **{count}** {desc}")

        lines.append("")

        # Quality distribution summary
        avg_score = sum(a.quality_score for a in assessments) / total
        # Use direct enum comparison via @total_ordering
        high_quality = sum(
            1 for a in assessments
            if a.quality_tier >= HIGH_QUALITY_TIER
        )
        high_quality_pct = (high_quality / total) * 100

        lines.append(
            f"Average quality score: **{avg_score:.1f}/10** | "
            f"High-quality evidence (RCT+): **{high_quality_pct:.0f}%**"
        )
        lines.append("")

        # Quality notes
        if include_quality_notes:
            notes = self._generate_quality_notes(assessments, tier_counts)
            lines.extend(notes)

        return "\n".join(lines)

    def _generate_quality_notes(
        self,
        assessments: list[QualityAssessment],
        tier_counts: Counter
    ) -> list[str]:
        """
        Generate interpretive notes about evidence quality.

        Args:
            assessments: List of quality assessments
            tier_counts: Counter of tier frequencies

        Returns:
            List of markdown lines for quality notes section
        """
        lines: list[str] = []
        notes: list[str] = []

        # Check for evidence gaps
        has_synthesis = tier_counts.get(QualityTier.TIER_5_SYNTHESIS, 0) > 0
        has_experimental = tier_counts.get(QualityTier.TIER_4_EXPERIMENTAL, 0) > 0

        if not has_synthesis:
            if not has_experimental:
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
        if len(assessments) > 0 and low_quality > len(assessments) * LOW_QUALITY_WARNING_THRESHOLD:
            notes.append(
                "More than half of the evidence comes from case reports "
                "or expert opinion; interpret findings with caution."
            )

        # Check for sample size issues
        with_sample = [a for a in assessments if a.sample_size]
        if with_sample:
            sorted_samples = sorted(a.sample_size for a in with_sample)
            median_n = sorted_samples[len(sorted_samples) // 2]
            if median_n < SMALL_SAMPLE_SIZE_THRESHOLD:
                notes.append(
                    f"Median sample size is {median_n}; small samples may "
                    "limit generalizability."
                )

        # Check for unclassified studies
        unclassified = tier_counts.get(QualityTier.UNCLASSIFIED, 0)
        if len(assessments) > 0 and unclassified > len(assessments) * UNCLASSIFIED_WARNING_THRESHOLD:
            notes.append(
                f"{unclassified} studies could not be classified; "
                "quality interpretation is limited."
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
            assessments: Quality assessments for each study
            documents: Optional corresponding LiteDocument objects for metadata

        Returns:
            Markdown-formatted table of studies
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

    def generate_brief_summary(
        self,
        assessments: list[QualityAssessment]
    ) -> str:
        """
        Generate a brief one-line evidence summary.

        Args:
            assessments: List of quality assessments

        Returns:
            Brief summary string (e.g., "12 studies (2 RCTs, 4 cohort, 6 other)")
        """
        if not assessments:
            return "No studies available"

        total = len(assessments)
        tier_counts = Counter(a.quality_tier for a in assessments)

        parts = []
        if tier_counts.get(QualityTier.TIER_5_SYNTHESIS, 0) > 0:
            n = tier_counts[QualityTier.TIER_5_SYNTHESIS]
            parts.append(f"{n} SR/MA")
        if tier_counts.get(QualityTier.TIER_4_EXPERIMENTAL, 0) > 0:
            n = tier_counts[QualityTier.TIER_4_EXPERIMENTAL]
            parts.append(f"{n} RCT")
        if tier_counts.get(QualityTier.TIER_3_CONTROLLED, 0) > 0:
            n = tier_counts[QualityTier.TIER_3_CONTROLLED]
            parts.append(f"{n} controlled")
        if tier_counts.get(QualityTier.TIER_2_OBSERVATIONAL, 0) > 0:
            n = tier_counts[QualityTier.TIER_2_OBSERVATIONAL]
            parts.append(f"{n} observational")

        # Combine low tier and unclassified as "other"
        other = (
            tier_counts.get(QualityTier.TIER_1_ANECDOTAL, 0) +
            tier_counts.get(QualityTier.UNCLASSIFIED, 0)
        )
        if other > 0:
            parts.append(f"{other} other")

        study_word = "study" if total == 1 else "studies"
        if parts:
            return f"{total} {study_word} ({', '.join(parts)})"
        return f"{total} {study_word}"
