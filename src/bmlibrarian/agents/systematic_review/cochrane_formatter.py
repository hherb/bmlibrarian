"""
Cochrane-Style Output Formatter

This module generates Cochrane-compliant output formats for systematic review
study assessments, including:
- Study Characteristics tables
- Risk of Bias tables
- Markdown and HTML output formats

The output matches the standard Cochrane Handbook template format.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .cochrane_models import (
    CochraneStudyAssessment,
    CochraneStudyCharacteristics,
    CochraneRiskOfBias,
    RiskOfBiasItem,
    ROB_JUDGEMENT_LOW,
    ROB_JUDGEMENT_HIGH,
    ROB_JUDGEMENT_UNCLEAR,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Markdown formatting
MD_TABLE_SEPARATOR = "|"
MD_HEADER_LINE = "|-"
MD_BOLD_START = "**"
MD_BOLD_END = "**"
MD_ITALIC_START = "*"
MD_ITALIC_END = "*"

# Table column widths for formatting (approximate character counts)
STUDY_CHAR_LABEL_WIDTH = 20
STUDY_CHAR_VALUE_WIDTH = 80
ROB_DOMAIN_WIDTH = 40
ROB_JUDGEMENT_WIDTH = 15
ROB_SUPPORT_WIDTH = 60


# =============================================================================
# Markdown Formatters
# =============================================================================

def format_study_characteristics_markdown(
    study_chars: CochraneStudyCharacteristics
) -> str:
    """
    Format study characteristics as Markdown table.

    Produces output matching Cochrane template format:

    | Study characteristics |                                        |
    |-----------------------|----------------------------------------|
    | Methods               | Parallel randomised trial              |
    | Participants          | Setting: Romania                       |
    |                       | People with chronic heart failure...   |
    | Interventions         | Admission avoidance hospital at home   |
    | Outcomes              | Mortality, biological measures, cost   |
    | Notes                 | Follow-up at 1, 3, 6, and 12 months   |

    Args:
        study_chars: CochraneStudyCharacteristics object

    Returns:
        Markdown formatted table string
    """
    lines: List[str] = []

    # Title with study ID
    lines.append(f"### {study_chars.study_id}")
    lines.append("")

    # Study characteristics header
    lines.append(f"{MD_ITALIC_START}Study characteristics{MD_ITALIC_END}")
    lines.append("")

    # Build table
    lines.append(f"| {MD_BOLD_START}Characteristic{MD_BOLD_END} | {MD_BOLD_START}Description{MD_BOLD_END} |")
    lines.append("|---|---|")

    # Methods
    lines.append(f"| Methods | {study_chars.methods} |")

    # Participants (may have multiple lines)
    participants_text = study_chars.participants.format_for_table()
    participant_lines = participants_text.split("\n")
    first_line = True
    for p_line in participant_lines:
        if p_line.strip():
            if first_line:
                lines.append(f"| Participants | {p_line} |")
                first_line = False
            else:
                lines.append(f"| | {p_line} |")

    # Interventions
    lines.append(f"| Interventions | {study_chars.interventions.description} |")

    # Outcomes
    lines.append(f"| Outcomes | {study_chars.outcomes.description} |")

    # Notes (may have multiple lines)
    notes_text = study_chars.notes.format_for_table()
    notes_lines = notes_text.split("\n\n")
    first_line = True
    for n_line in notes_lines:
        if n_line.strip():
            if first_line:
                lines.append(f"| Notes | {n_line} |")
                first_line = False
            else:
                lines.append(f"| | {n_line} |")

    lines.append("")
    return "\n".join(lines)


def format_risk_of_bias_markdown(rob: CochraneRiskOfBias) -> str:
    """
    Format risk of bias assessment as Markdown table.

    Produces output matching Cochrane RoB table format:

    | Bias | Authors' judgement | Support for judgement |
    |------|-------------------|----------------------|
    | Random sequence generation (selection bias) | Unclear risk | The study was... |
    | Allocation concealment (selection bias) | Unclear risk | The study was... |

    Args:
        rob: CochraneRiskOfBias object

    Returns:
        Markdown formatted table string
    """
    lines: List[str] = []

    # Risk of bias header
    lines.append(f"{MD_ITALIC_START}Risk of bias{MD_ITALIC_END}")
    lines.append("")

    # Build table
    lines.append(f"| {MD_BOLD_START}Bias{MD_BOLD_END} | {MD_BOLD_START}Authors' judgement{MD_BOLD_END} | {MD_BOLD_START}Support for judgement{MD_BOLD_END} |")
    lines.append("|---|---|---|")

    # Add all domains in Cochrane order
    for item in rob.to_list():
        domain_with_type = f"{item.domain} ({item.bias_type})"
        if item.outcome_type:
            domain_with_type = f"{item.domain}"
        lines.append(
            f"| {domain_with_type} | {item.judgement} | {item.support_for_judgement} |"
        )

    lines.append("")
    return "\n".join(lines)


def format_complete_assessment_markdown(assessment: CochraneStudyAssessment) -> str:
    """
    Format complete Cochrane assessment as Markdown.

    Combines study characteristics and risk of bias tables with optional
    additional assessment metadata.

    Args:
        assessment: CochraneStudyAssessment object

    Returns:
        Complete Markdown formatted assessment string
    """
    lines: List[str] = []

    # Study characteristics
    lines.append(format_study_characteristics_markdown(assessment.study_characteristics))

    # Risk of bias
    lines.append(format_risk_of_bias_markdown(assessment.risk_of_bias))

    # Additional metadata if present
    if assessment.overall_quality_score is not None or assessment.evidence_level:
        lines.append(f"{MD_ITALIC_START}Assessment Summary{MD_ITALIC_END}")
        lines.append("")

        if assessment.overall_quality_score is not None:
            lines.append(f"- **Quality Score:** {assessment.overall_quality_score:.1f}/10")

        if assessment.overall_confidence is not None:
            lines.append(f"- **Assessment Confidence:** {assessment.overall_confidence:.0%}")

        if assessment.evidence_level:
            lines.append(f"- **Evidence Level:** {assessment.evidence_level}")

        lines.append("")

    # Assessment notes if present
    if assessment.assessment_notes:
        lines.append(f"{MD_ITALIC_START}Notes{MD_ITALIC_END}")
        lines.append("")
        for note in assessment.assessment_notes:
            lines.append(f"- {note}")
        lines.append("")

    return "\n".join(lines)


def format_multiple_assessments_markdown(
    assessments: List[CochraneStudyAssessment],
    title: str = "Characteristics of included studies"
) -> str:
    """
    Format multiple study assessments as a single Markdown document.

    This matches the Cochrane "Characteristics of included studies" section
    format used in systematic review outputs.

    Args:
        assessments: List of CochraneStudyAssessment objects
        title: Section title

    Returns:
        Complete Markdown document with all assessments
    """
    lines: List[str] = []

    # Section header
    lines.append(f"## {title}")
    lines.append("")

    # Each assessment
    for assessment in assessments:
        lines.append(format_complete_assessment_markdown(assessment))
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


# =============================================================================
# Risk of Bias Summary
# =============================================================================

def format_risk_of_bias_summary_markdown(
    assessments: List[CochraneStudyAssessment]
) -> str:
    """
    Format risk of bias summary across all studies.

    Creates a summary table showing judgements across all studies
    for each bias domain, useful for identifying patterns.

    Args:
        assessments: List of CochraneStudyAssessment objects

    Returns:
        Markdown formatted summary table
    """
    lines: List[str] = []

    if not assessments:
        return "No assessments to summarize."

    # Header
    lines.append("## Risk of Bias Summary")
    lines.append("")

    # Get domain names from first assessment
    domains = [
        "Random sequence generation (selection bias)",
        "Allocation concealment (selection bias)",
        "Baseline outcome measurements (selection bias)",
        "Baseline characteristics (selection bias)",
        "Blinding of participants and personnel (performance bias)",
        "Blinding of outcome assessment - subjective (detection bias)",
        "Blinding of outcome assessment - objective (detection bias)",
        "Incomplete outcome data (attrition bias)",
        "Selective reporting (reporting bias)",
    ]

    # Build header row
    study_ids = [a.study_id for a in assessments]
    header = "| Domain | " + " | ".join(study_ids) + " |"
    separator = "|---" + "|---" * len(study_ids) + "|"

    lines.append(header)
    lines.append(separator)

    # Build domain rows
    domain_attrs = [
        "random_sequence_generation",
        "allocation_concealment",
        "baseline_outcome_measurements",
        "baseline_characteristics",
        "blinding_participants_personnel",
        "blinding_outcome_assessment_subjective",
        "blinding_outcome_assessment_objective",
        "incomplete_outcome_data",
        "selective_reporting",
    ]

    for domain, attr in zip(domains, domain_attrs):
        judgements = []
        for assessment in assessments:
            rob_item = getattr(assessment.risk_of_bias, attr)
            judgement = _format_judgement_symbol(rob_item.judgement)
            judgements.append(judgement)

        row = f"| {domain} | " + " | ".join(judgements) + " |"
        lines.append(row)

    lines.append("")

    # Legend
    lines.append("**Legend:** + Low risk | - High risk | ? Unclear risk")
    lines.append("")

    return "\n".join(lines)


def _format_judgement_symbol(judgement: str) -> str:
    """
    Convert judgement text to symbol for summary table.

    Args:
        judgement: Full judgement text

    Returns:
        Single character symbol (+, -, ?)
    """
    if judgement == ROB_JUDGEMENT_LOW:
        return "+"
    elif judgement == ROB_JUDGEMENT_HIGH:
        return "-"
    else:
        return "?"


# =============================================================================
# HTML Formatters
# =============================================================================

def format_study_characteristics_html(
    study_chars: CochraneStudyCharacteristics
) -> str:
    """
    Format study characteristics as HTML table.

    Produces HTML output that can be styled with CSS to match
    Cochrane publication format.

    Args:
        study_chars: CochraneStudyCharacteristics object

    Returns:
        HTML formatted table string
    """
    html_parts: List[str] = []

    # Title
    html_parts.append(f'<h3 class="study-id">{study_chars.study_id}</h3>')
    html_parts.append('<p class="section-header"><em>Study characteristics</em></p>')

    # Table
    html_parts.append('<table class="cochrane-characteristics">')
    html_parts.append('<thead>')
    html_parts.append('<tr><th>Characteristic</th><th>Description</th></tr>')
    html_parts.append('</thead>')
    html_parts.append('<tbody>')

    # Methods
    html_parts.append(f'<tr><td>Methods</td><td>{_escape_html(study_chars.methods)}</td></tr>')

    # Participants
    participants_text = study_chars.participants.format_for_table()
    html_parts.append(f'<tr><td>Participants</td><td>{_escape_html(participants_text).replace(chr(10), "<br>")}</td></tr>')

    # Interventions
    html_parts.append(f'<tr><td>Interventions</td><td>{_escape_html(study_chars.interventions.description)}</td></tr>')

    # Outcomes
    html_parts.append(f'<tr><td>Outcomes</td><td>{_escape_html(study_chars.outcomes.description)}</td></tr>')

    # Notes
    notes_text = study_chars.notes.format_for_table()
    html_parts.append(f'<tr><td>Notes</td><td>{_escape_html(notes_text).replace(chr(10), "<br>")}</td></tr>')

    html_parts.append('</tbody>')
    html_parts.append('</table>')

    return "\n".join(html_parts)


def format_risk_of_bias_html(rob: CochraneRiskOfBias) -> str:
    """
    Format risk of bias as HTML table.

    Args:
        rob: CochraneRiskOfBias object

    Returns:
        HTML formatted table string
    """
    html_parts: List[str] = []

    html_parts.append('<p class="section-header"><em>Risk of bias</em></p>')

    html_parts.append('<table class="cochrane-risk-of-bias">')
    html_parts.append('<thead>')
    html_parts.append("<tr><th>Bias</th><th>Authors' judgement</th><th>Support for judgement</th></tr>")
    html_parts.append('</thead>')
    html_parts.append('<tbody>')

    for item in rob.to_list():
        judgement_class = _get_judgement_css_class(item.judgement)
        domain_text = f"{item.domain} ({item.bias_type})"

        html_parts.append(
            f'<tr>'
            f'<td>{_escape_html(domain_text)}</td>'
            f'<td class="{judgement_class}">{_escape_html(item.judgement)}</td>'
            f'<td>{_escape_html(item.support_for_judgement)}</td>'
            f'</tr>'
        )

    html_parts.append('</tbody>')
    html_parts.append('</table>')

    return "\n".join(html_parts)


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _get_judgement_css_class(judgement: str) -> str:
    """Get CSS class for judgement styling."""
    if judgement == ROB_JUDGEMENT_LOW:
        return "judgement-low"
    elif judgement == ROB_JUDGEMENT_HIGH:
        return "judgement-high"
    else:
        return "judgement-unclear"


# =============================================================================
# CSS for HTML Output
# =============================================================================

COCHRANE_CSS = """
<style>
.cochrane-characteristics, .cochrane-risk-of-bias {
    border-collapse: collapse;
    width: 100%;
    margin-bottom: 1.5em;
    font-size: 0.9em;
}

.cochrane-characteristics th, .cochrane-characteristics td,
.cochrane-risk-of-bias th, .cochrane-risk-of-bias td {
    border: 1px solid #ccc;
    padding: 8px 12px;
    text-align: left;
    vertical-align: top;
}

.cochrane-characteristics th, .cochrane-risk-of-bias th {
    background-color: #f5f5f5;
    font-weight: bold;
}

.cochrane-characteristics td:first-child {
    font-weight: bold;
    width: 150px;
    background-color: #fafafa;
}

.cochrane-risk-of-bias td:first-child {
    width: 35%;
}

.cochrane-risk-of-bias td:nth-child(2) {
    width: 15%;
    text-align: center;
}

.section-header {
    margin-top: 1em;
    margin-bottom: 0.5em;
}

.study-id {
    margin-top: 1.5em;
    padding-bottom: 0.5em;
    border-bottom: 2px solid #333;
}

.judgement-low {
    background-color: #d4edda;
    color: #155724;
}

.judgement-high {
    background-color: #f8d7da;
    color: #721c24;
}

.judgement-unclear {
    background-color: #fff3cd;
    color: #856404;
}
</style>
"""


def get_cochrane_css() -> str:
    """
    Get CSS stylesheet for Cochrane HTML output.

    Returns:
        CSS stylesheet string
    """
    return COCHRANE_CSS
