"""
Quality-aware report formatting utilities.

Provides formatting utilities for citations and references that include
quality information such as study design, sample size, and quality tier.
"""

import logging
from typing import TYPE_CHECKING

from .data_models import QualityTier, QualityAssessment

if TYPE_CHECKING:
    from ..data_models import Citation

logger = logging.getLogger(__name__)


# Color indicators for quality tiers (emoji version, optional)
TIER_EMOJI: dict[QualityTier, str] = {
    QualityTier.TIER_5_SYNTHESIS: "🟢",      # Green
    QualityTier.TIER_4_EXPERIMENTAL: "🔵",   # Blue
    QualityTier.TIER_3_CONTROLLED: "🟠",     # Orange
    QualityTier.TIER_2_OBSERVATIONAL: "⚪",  # White
    QualityTier.TIER_1_ANECDOTAL: "🔴",      # Red
    QualityTier.UNCLASSIFIED: "⚫",          # Black
}

# Short labels for study designs (for inline use)
DESIGN_SHORT_LABELS: dict[str, str] = {
    "systematic_review": "SR",
    "meta_analysis": "MA",
    "rct": "RCT",
    "guideline": "GL",
    "cohort_prospective": "prospective",
    "cohort_retrospective": "retrospective",
    "case_control": "CC",
    "cross_sectional": "XS",
    "case_series": "series",
    "case_report": "case",
    "editorial": "editorial",
    "letter": "letter",
    "comment": "comment",
    "review": "review",
    "other": "other",
    "unknown": "unknown",
}


class QualityReportFormatter:
    """
    Format citations and references with quality annotations.

    Supports both plain text and emoji-enhanced quality indicators.
    """

    def __init__(self, use_emoji: bool = False):
        """
        Initialize formatter.

        Args:
            use_emoji: Whether to use emoji quality indicators
        """
        self.use_emoji = use_emoji

    def format_inline_citation(
        self,
        citation: "Citation",
        citation_number: int
    ) -> str:
        """
        Format a citation for inline use in text.

        Args:
            citation: The citation to format
            citation_number: Citation reference number

        Returns:
            Formatted citation string with quality annotation
        """
        ref = citation.formatted_reference
        base = f"[{ref}]({citation_number})"

        if citation.assessment:
            qual = self._format_quality_inline(citation.assessment)
            if qual:
                return f"{base} {qual}"

        return base

    def format_numbered_citation(
        self,
        citation: "Citation",
        citation_number: int
    ) -> str:
        """
        Format a citation with just the number and optional quality.

        Args:
            citation: The citation to format
            citation_number: Citation reference number

        Returns:
            Formatted string like "[1]" or "[1] (RCT, n=150)"
        """
        base = f"[{citation_number}]"

        if citation.assessment:
            qual = self._format_quality_inline(citation.assessment)
            if qual:
                return f"{base} {qual}"

        return base

    def _format_quality_inline(self, assessment: QualityAssessment) -> str:
        """
        Format quality annotation for inline use.

        Args:
            assessment: Quality assessment data

        Returns:
            Formatted quality string (e.g., "(RCT, n=150)")
        """
        parts = []

        # Design shorthand
        design_value = assessment.study_design.value
        design = DESIGN_SHORT_LABELS.get(
            design_value,
            design_value.split("_")[0]
        )

        if design.lower() not in ["unknown", "other"]:
            parts.append(design)

        # Sample size
        if assessment.sample_size:
            parts.append(f"n={assessment.sample_size}")

        # Blinding
        if assessment.is_blinded and assessment.is_blinded != "none":
            parts.append(f"{assessment.is_blinded}-blind")

        if parts:
            if self.use_emoji:
                emoji = TIER_EMOJI.get(assessment.quality_tier, "")
                return f"{emoji} **{', '.join(parts)}**"
            return f"(**{', '.join(parts)}**)"

        return ""

    def format_reference_entry(
        self,
        citation: "Citation",
        number: int
    ) -> str:
        """
        Format a citation for the references section.

        Args:
            citation: The citation to format
            number: Reference number

        Returns:
            Formatted reference entry with quality badge
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

            if self.use_emoji:
                emoji = TIER_EMOJI.get(
                    citation.assessment.quality_tier, ""
                )
                ref += f" {emoji}"
            else:
                ref += f" [{design_label}]"

        return ref

    def format_quality_badge(
        self,
        assessment: QualityAssessment
    ) -> str:
        """
        Format a standalone quality badge.

        Args:
            assessment: Quality assessment

        Returns:
            Quality badge string (e.g., "[RCT, Level 4]")
        """
        design = assessment.study_design.value.replace("_", " ").title()
        tier = assessment.quality_tier.value

        if self.use_emoji:
            emoji = TIER_EMOJI.get(assessment.quality_tier, "")
            return f"{emoji} {design} (Level {tier})"
        return f"[{design}, Level {tier}]"

    def format_citations_for_prompt(
        self,
        citations: list["Citation"],
        include_quality: bool = True
    ) -> str:
        """
        Format citations for inclusion in an LLM prompt.

        Args:
            citations: List of citations to format
            include_quality: Whether to include quality annotations

        Returns:
            Formatted string with numbered citations
        """
        formatted = []
        for i, citation in enumerate(citations, 1):
            doc = citation.document

            # Build citation text
            text = f"""[{i}] {doc.formatted_authors} ({doc.year or 'n.d.'})
Document ID: {doc.id}
Title: {doc.title}
Journal: {doc.journal or 'Unknown'}"""

            # Add quality info if available
            if include_quality and citation.assessment:
                assessment = citation.assessment
                design = assessment.study_design.value.replace("_", " ").title()
                text += f"\nStudy Design: {design}"
                if assessment.sample_size:
                    text += f" | Sample Size: {assessment.sample_size}"
                if assessment.is_blinded:
                    text += f" | Blinding: {assessment.is_blinded}"
                text += f" | Quality Score: {assessment.quality_score:.1f}/10"

            text += f'\nPassage: "{citation.passage}"'
            formatted.append(text)

        return "\n\n".join(formatted)
