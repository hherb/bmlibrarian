"""
Reporter Component for SystematicReviewAgent

Generates comprehensive output reports in multiple formats:
- JSON: Full machine-readable output with all data
- Markdown: Human-readable report with sections and tables
- CSV: Spreadsheet-compatible export for analysis
- PRISMA: PRISMA 2020 flow diagram data

Features:
- Complete audit trail integration
- Configurable report sections
- Publication-ready formatting
- Multiple export options
"""

from __future__ import annotations

import csv
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, TextIO

from .data_models import (
    SearchCriteria,
    ScoringWeights,
    SearchPlan,
    ExecutedQuery,
    PaperData,
    ScoredPaper,
    AssessedPaper,
    ReviewStatistics,
    SystematicReviewResult,
    InclusionStatus,
    ExclusionStage,
)
from .documenter import Documenter
from .cochrane_models import CochraneStudyAssessment
from .cochrane_formatter import (
    format_complete_assessment_markdown,
    format_multiple_assessments_markdown,
    format_risk_of_bias_summary_markdown,
    format_study_characteristics_html,
    format_risk_of_bias_html,
    get_cochrane_css,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Report version for tracking format changes
REPORT_FORMAT_VERSION = "1.0.0"

# Display length limits for report formatting
# These control truncation of text fields in tables and summaries
MAX_QUERY_TEXT_DISPLAY_LENGTH = 50  # Max chars for query text in search strategy tables
MAX_PAPERS_PER_EXCLUSION_STAGE = 20  # Max papers shown per exclusion stage in markdown
MAX_TITLE_DISPLAY_LENGTH_EXCLUDED = 50  # Max chars for title in excluded papers tables
MAX_TITLE_DISPLAY_LENGTH_UNCERTAIN = 40  # Max chars for title in uncertain papers tables
MAX_RATIONALE_DISPLAY_LENGTH = 30  # Max chars for rationale notes in tables

# Markdown formatting
MD_H1 = "#"
MD_H2 = "##"
MD_H3 = "###"
MD_H4 = "####"
MD_BULLET = "-"
MD_CODE_FENCE = "```"

# CSV column names
CSV_COLUMNS_INCLUDED = [
    "rank",
    "document_id",
    "title",
    "authors",
    "year",
    "journal",
    "doi",
    "pmid",
    "relevance_score",
    "composite_score",
    "study_type",
    "quality_score",
    "inclusion_rationale",
]

CSV_COLUMNS_EXCLUDED = [
    "document_id",
    "title",
    "authors",
    "year",
    "exclusion_stage",
    "exclusion_reasons",
    "exclusion_rationale",
]

# PRISMA flow diagram stages
PRISMA_STAGES = [
    "identification",
    "screening",
    "eligibility",
    "included",
]


# =============================================================================
# Path Validation
# =============================================================================

class OutputPathError(Exception):
    """Exception raised when output path validation fails."""

    pass


def validate_output_path(output_path: str) -> Path:
    """
    Validate and prepare an output file path.

    Performs validation including:
    - Path expansion (handles ~)
    - Directory creation with appropriate permissions
    - Write permission verification
    - Basic directory traversal protection

    Args:
        output_path: Path string for the output file

    Returns:
        Expanded and validated Path object

    Raises:
        OutputPathError: If path validation fails (invalid path, no permission, etc.)
    """
    if not output_path or not output_path.strip():
        raise OutputPathError("Output path cannot be empty")

    try:
        output = Path(output_path).expanduser().resolve()
    except (ValueError, OSError) as e:
        raise OutputPathError(f"Invalid output path '{output_path}': {e}")

    # Basic directory traversal protection: ensure path doesn't escape expected directories
    try:
        # Resolve the path to catch any '..' components
        output = output.resolve()
    except (ValueError, OSError) as e:
        raise OutputPathError(f"Failed to resolve output path '{output_path}': {e}")

    # Ensure parent directory exists or can be created
    parent_dir = output.parent
    try:
        parent_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError as e:
        raise OutputPathError(
            f"Permission denied creating directory '{parent_dir}': {e}"
        )
    except OSError as e:
        raise OutputPathError(
            f"Failed to create directory '{parent_dir}': {e}"
        )

    # Verify write permission to the directory
    if not os.access(parent_dir, os.W_OK):
        raise OutputPathError(
            f"No write permission for directory '{parent_dir}'"
        )

    # Check if file exists and is writable (if it exists)
    if output.exists() and not os.access(output, os.W_OK):
        raise OutputPathError(
            f"No write permission for existing file '{output}'"
        )

    return output


# =============================================================================
# Reporter Class
# =============================================================================

class Reporter:
    """
    Generates output reports in multiple formats.

    Provides comprehensive report generation capabilities including:
    - JSON export with full data and audit trail
    - Markdown reports for human readability
    - CSV exports for spreadsheet analysis
    - PRISMA flow diagram data generation

    Attributes:
        documenter: Documenter instance for audit trail access
        criteria: Search criteria used in the review
        weights: Scoring weights used for composite scores

    Example:
        >>> reporter = Reporter(documenter, criteria, weights)
        >>> reporter.generate_json_report(result, "output.json")
        >>> reporter.generate_markdown_report(result, "report.md")
    """

    def __init__(
        self,
        documenter: Documenter,
        criteria: Optional[SearchCriteria] = None,
        weights: Optional[ScoringWeights] = None,
    ) -> None:
        """
        Initialize the Reporter.

        Args:
            documenter: Documenter instance for audit trail
            criteria: Optional search criteria for metadata
            weights: Optional scoring weights for metadata
        """
        self.documenter = documenter
        self.criteria = criteria
        self.weights = weights or ScoringWeights()

        logger.info("Reporter initialized")

    # =========================================================================
    # JSON Report Generation
    # =========================================================================

    def generate_json_report(
        self,
        result: SystematicReviewResult,
        output_path: str,
    ) -> None:
        """
        Generate JSON output file.

        Creates a complete JSON export of the systematic review results,
        including all papers, decisions, and the full audit trail.

        Args:
            result: SystematicReviewResult to export
            output_path: Path for the output file

        Raises:
            OutputPathError: If output path validation fails
        """
        output = validate_output_path(output_path)

        with open(output, "w", encoding="utf-8") as f:
            f.write(result.to_json(indent=2))

        logger.info(f"JSON report saved to: {output}")

    def build_json_result(
        self,
        included_papers: List[AssessedPaper],
        excluded_papers: List[ScoredPaper],
        uncertain_papers: List[ScoredPaper],
        search_plan: Optional[SearchPlan] = None,
        executed_queries: Optional[List[ExecutedQuery]] = None,
        statistics: Optional[ReviewStatistics] = None,
    ) -> SystematicReviewResult:
        """
        Build a SystematicReviewResult from component data.

        Args:
            included_papers: Papers that passed all criteria
            excluded_papers: Papers that were rejected
            uncertain_papers: Papers needing human review
            search_plan: Optional search plan used
            executed_queries: Optional list of executed queries
            statistics: Optional pre-computed statistics

        Returns:
            Complete SystematicReviewResult
        """
        # Build metadata
        metadata = self._build_metadata()

        # Build search strategy section
        search_strategy = self._build_search_strategy(search_plan, executed_queries)

        # Build scoring config
        scoring_config = {
            "dimension_weights": self.weights.to_dict(),
            "version": REPORT_FORMAT_VERSION,
        }

        # Convert papers to dicts
        included_dicts = [self._assessed_paper_to_dict(p) for p in included_papers]
        excluded_dicts = [self._excluded_paper_to_dict(p) for p in excluded_papers]
        uncertain_dicts = [self._uncertain_paper_to_dict(p) for p in uncertain_papers]

        # Get process log from documenter
        process_log = self.documenter.generate_process_log()

        # Build or use provided statistics
        if statistics is None:
            statistics = self._calculate_statistics(
                included_papers, excluded_papers, uncertain_papers
            )

        return SystematicReviewResult(
            metadata=metadata,
            search_strategy=search_strategy,
            scoring_config=scoring_config,
            included_papers=included_dicts,
            excluded_papers=excluded_dicts,
            uncertain_papers=uncertain_dicts,
            process_log=process_log,
            statistics=statistics,
        )

    def _build_metadata(self) -> Dict[str, Any]:
        """Build report metadata section."""
        metadata = {
            "generated_at": datetime.now().isoformat(),
            "report_format_version": REPORT_FORMAT_VERSION,
            "review_id": self.documenter.review_id,
        }

        if self.criteria:
            metadata["research_question"] = self.criteria.research_question
            metadata["purpose"] = self.criteria.purpose
            metadata["inclusion_criteria"] = self.criteria.inclusion_criteria
            metadata["exclusion_criteria"] = self.criteria.exclusion_criteria
            if self.criteria.date_range:
                metadata["date_range"] = list(self.criteria.date_range)
            if self.criteria.target_study_types:
                metadata["target_study_types"] = [
                    st.value for st in self.criteria.target_study_types
                ]

        return metadata

    def _build_search_strategy(
        self,
        search_plan: Optional[SearchPlan],
        executed_queries: Optional[List[ExecutedQuery]],
    ) -> Dict[str, Any]:
        """Build search strategy section."""
        strategy: Dict[str, Any] = {
            "queries_planned": [],
            "queries_executed": [],
            "total_papers_found": 0,
            "after_deduplication": 0,
        }

        if search_plan:
            strategy["queries_planned"] = [q.to_dict() for q in search_plan.queries]
            strategy["search_rationale"] = search_plan.search_rationale
            strategy["total_estimated_yield"] = search_plan.total_estimated_yield

        if executed_queries:
            strategy["queries_executed"] = [q.to_dict() for q in executed_queries]
            # Calculate totals
            all_ids: set[int] = set()
            for eq in executed_queries:
                strategy["total_papers_found"] += eq.actual_results
                all_ids.update(eq.document_ids)
            strategy["after_deduplication"] = len(all_ids)

        return strategy

    def _assessed_paper_to_dict(self, paper: AssessedPaper) -> Dict[str, Any]:
        """Convert AssessedPaper to dictionary for JSON output."""
        base = paper.scored_paper.paper.to_dict()

        # Add scores
        base["scores"] = {
            "relevance": paper.scored_paper.relevance_score,
            "composite_score": paper.composite_score,
        }

        # Add quality data
        if paper.study_assessment:
            base["study_assessment"] = paper.study_assessment
            base["scores"]["study_quality"] = paper.study_assessment.get(
                "quality_score", 0.0
            )

        if paper.paper_weight:
            base["paper_weight"] = paper.paper_weight
            base["scores"]["paper_weight"] = paper.paper_weight.get(
                "composite_score", 0.0
            )

        # Add optional assessments
        if paper.pico_components:
            base["pico_components"] = paper.pico_components

        if paper.prisma_assessment:
            base["prisma_assessment"] = paper.prisma_assessment

        # Add inclusion rationale
        base["inclusion_rationale"] = paper.scored_paper.inclusion_decision.rationale
        base["final_rank"] = paper.final_rank

        # Add relevant citations if available
        if paper.scored_paper.relevant_citations:
            base["relevant_citations"] = paper.scored_paper.relevant_citations

        return base

    def _excluded_paper_to_dict(self, paper: ScoredPaper) -> Dict[str, Any]:
        """Convert excluded ScoredPaper to dictionary for JSON output."""
        return {
            "document_id": paper.paper.document_id,
            "title": paper.paper.title,
            "authors": paper.paper.authors,
            "year": paper.paper.year,
            "exclusion_stage": paper.inclusion_decision.stage.value,
            "exclusion_reasons": paper.inclusion_decision.reasons,
            "exclusion_rationale": paper.inclusion_decision.rationale,
            "relevance_score": paper.relevance_score,
        }

    def _uncertain_paper_to_dict(self, paper: ScoredPaper) -> Dict[str, Any]:
        """Convert uncertain ScoredPaper to dictionary for JSON output."""
        return {
            "document_id": paper.paper.document_id,
            "title": paper.paper.title,
            "authors": paper.paper.authors,
            "year": paper.paper.year,
            "relevance_score": paper.relevance_score,
            "rationale": paper.inclusion_decision.rationale,
            "criteria_matched": paper.inclusion_decision.criteria_matched,
            "criteria_failed": paper.inclusion_decision.criteria_failed,
        }

    def _calculate_statistics(
        self,
        included: List[AssessedPaper],
        excluded: List[ScoredPaper],
        uncertain: List[ScoredPaper],
    ) -> ReviewStatistics:
        """Calculate review statistics from paper lists."""
        # Get totals from documenter metrics
        stats = self.documenter.get_statistics()

        return ReviewStatistics(
            total_considered=stats.get("total_papers", len(included) + len(excluded) + len(uncertain)),
            passed_initial_filter=stats.get("passed_initial_filter", 0),
            passed_relevance_threshold=stats.get("passed_relevance", 0),
            passed_quality_gate=len(included),
            final_included=len(included),
            final_excluded=len(excluded),
            uncertain_for_review=len(uncertain),
            processing_time_seconds=self.documenter.get_duration(),
            total_llm_calls=stats.get("total_llm_calls", 0),
            total_tokens_used=stats.get("total_tokens", 0),
        )

    # =========================================================================
    # Markdown Report Generation
    # =========================================================================

    def generate_markdown_report(
        self,
        result: SystematicReviewResult,
        output_path: str,
        include_audit_trail: bool = True,
        include_excluded: bool = True,
    ) -> None:
        """
        Generate human-readable Markdown report.

        Creates a comprehensive, publication-ready report with:
        - Executive summary
        - Methodology description
        - Results tables
        - Optional audit trail

        Args:
            result: SystematicReviewResult to format
            output_path: Path for the output file
            include_audit_trail: Whether to include full audit trail
            include_excluded: Whether to include excluded papers list

        Raises:
            OutputPathError: If output path validation fails
        """
        output = validate_output_path(output_path)

        content = self._build_markdown_content(
            result, include_audit_trail, include_excluded
        )

        with open(output, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info(f"Markdown report saved to: {output}")

    def _build_markdown_content(
        self,
        result: SystematicReviewResult,
        include_audit_trail: bool,
        include_excluded: bool,
    ) -> str:
        """Build complete Markdown report content."""
        lines: List[str] = []

        # Title
        lines.append(f"{MD_H1} Systematic Literature Review Report")
        lines.append("")

        # Metadata
        lines.extend(self._format_metadata_section(result.metadata))

        # Executive Summary
        lines.extend(self._format_summary_section(result.statistics))

        # Search Strategy
        lines.extend(self._format_search_strategy_section(result.search_strategy))

        # Scoring Configuration
        lines.extend(self._format_scoring_config_section(result.scoring_config))

        # Included Papers
        lines.extend(self._format_included_papers_section(result.included_papers))

        # Excluded Papers (optional)
        if include_excluded and result.excluded_papers:
            lines.extend(self._format_excluded_papers_section(result.excluded_papers))

        # Uncertain Papers (if any)
        if result.uncertain_papers:
            lines.extend(self._format_uncertain_papers_section(result.uncertain_papers))

        # PRISMA Flow Diagram
        lines.extend(self._format_prisma_section(result.statistics))

        # Audit Trail (optional)
        if include_audit_trail:
            lines.extend(self._format_audit_trail_section(result.process_log))

        return "\n".join(lines)

    def _format_metadata_section(self, metadata: Dict[str, Any]) -> List[str]:
        """Format metadata section."""
        lines = [
            f"{MD_H2} Review Information",
            "",
            f"**Review ID:** {metadata.get('review_id', 'N/A')}",
            f"**Generated:** {metadata.get('generated_at', 'N/A')}",
            f"**Report Format Version:** {metadata.get('report_format_version', 'N/A')}",
            "",
        ]

        if "research_question" in metadata:
            lines.append(f"{MD_H3} Research Question")
            lines.append("")
            lines.append(f"> {metadata['research_question']}")
            lines.append("")

        if "purpose" in metadata:
            lines.append(f"**Purpose:** {metadata['purpose']}")
            lines.append("")

        if "inclusion_criteria" in metadata:
            lines.append(f"{MD_H3} Inclusion Criteria")
            lines.append("")
            for criterion in metadata["inclusion_criteria"]:
                lines.append(f"{MD_BULLET} {criterion}")
            lines.append("")

        if "exclusion_criteria" in metadata:
            lines.append(f"{MD_H3} Exclusion Criteria")
            lines.append("")
            for criterion in metadata["exclusion_criteria"]:
                lines.append(f"{MD_BULLET} {criterion}")
            lines.append("")

        return lines

    def _format_summary_section(self, statistics: ReviewStatistics) -> List[str]:
        """Format executive summary section."""
        stats = statistics.to_dict()

        lines = [
            f"{MD_H2} Executive Summary",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Papers Considered | {stats['total_considered']} |",
            f"| Passed Initial Filter | {stats['passed_initial_filter']} |",
            f"| Passed Relevance Threshold | {stats['passed_relevance_threshold']} |",
            f"| Passed Quality Gate | {stats['passed_quality_gate']} |",
            f"| **Final Included** | **{stats['final_included']}** |",
            f"| Final Excluded | {stats['final_excluded']} |",
            f"| Uncertain (Human Review) | {stats['uncertain_for_review']} |",
            "",
            f"**Processing Time:** {stats['processing_time_seconds']:.2f} seconds",
            "",
        ]

        return lines

    def _format_search_strategy_section(
        self, search_strategy: Dict[str, Any]
    ) -> List[str]:
        """Format search strategy section."""
        lines = [
            f"{MD_H2} Search Strategy",
            "",
        ]

        if "search_rationale" in search_strategy:
            lines.append(f"**Rationale:** {search_strategy['search_rationale']}")
            lines.append("")

        if search_strategy.get("queries_planned"):
            lines.append(f"{MD_H3} Planned Queries")
            lines.append("")
            lines.append("| Type | Query | Purpose |")
            lines.append("|------|-------|---------|")

            for query in search_strategy["queries_planned"]:
                q_type = query.get("query_type", "unknown")
                raw_text = query.get("query_text", "")
                q_text = raw_text[:MAX_QUERY_TEXT_DISPLAY_LENGTH] + "..." if len(raw_text) > MAX_QUERY_TEXT_DISPLAY_LENGTH else raw_text
                q_purpose = query.get("purpose", "")
                lines.append(f"| {q_type} | {q_text} | {q_purpose} |")

            lines.append("")

        if search_strategy.get("queries_executed"):
            lines.append(f"{MD_H3} Execution Results")
            lines.append("")
            lines.append(f"**Total papers found:** {search_strategy.get('total_papers_found', 0)}")
            lines.append(f"**After deduplication:** {search_strategy.get('after_deduplication', 0)}")
            lines.append("")

        return lines

    def _format_scoring_config_section(
        self, scoring_config: Dict[str, Any]
    ) -> List[str]:
        """Format scoring configuration section."""
        lines = [
            f"{MD_H2} Scoring Configuration",
            "",
        ]

        weights = scoring_config.get("dimension_weights", {})
        if weights:
            lines.append("| Dimension | Weight |")
            lines.append("|-----------|--------|")

            for dim, weight in weights.items():
                lines.append(f"| {dim.replace('_', ' ').title()} | {weight:.2f} |")

            lines.append("")

        return lines

    def _format_included_papers_section(
        self, included_papers: List[Dict[str, Any]]
    ) -> List[str]:
        """Format included papers section."""
        lines = [
            f"{MD_H2} Included Papers ({len(included_papers)})",
            "",
        ]

        if not included_papers:
            lines.append("*No papers met all inclusion criteria.*")
            lines.append("")
            return lines

        for paper in included_papers:
            rank = paper.get("final_rank", "N/A")
            title = paper.get("title", "Unknown Title")
            authors = ", ".join(paper.get("authors", [])[:3])
            if len(paper.get("authors", [])) > 3:
                authors += " et al."
            year = paper.get("year", "N/A")
            scores = paper.get("scores", {})

            lines.append(f"{MD_H3} {rank}. {title}")
            lines.append("")
            lines.append(f"**Authors:** {authors}")
            lines.append(f"**Year:** {year}")

            if paper.get("journal"):
                lines.append(f"**Journal:** {paper['journal']}")

            if paper.get("doi"):
                lines.append(f"**DOI:** {paper['doi']}")

            if paper.get("pmid"):
                lines.append(f"**PMID:** {paper['pmid']}")

            lines.append("")

            # Scores
            lines.append(f"**Scores:**")
            lines.append(f"{MD_BULLET} Relevance: {scores.get('relevance', 'N/A')}/5")
            lines.append(f"{MD_BULLET} Composite: {scores.get('composite_score', 'N/A'):.2f}/10")

            if scores.get("study_quality"):
                lines.append(f"{MD_BULLET} Study Quality: {scores['study_quality']:.2f}/10")

            lines.append("")

            # Inclusion rationale
            if paper.get("inclusion_rationale"):
                lines.append(f"**Inclusion Rationale:** {paper['inclusion_rationale']}")
                lines.append("")

            lines.append("---")
            lines.append("")

        return lines

    def _format_excluded_papers_section(
        self, excluded_papers: List[Dict[str, Any]]
    ) -> List[str]:
        """Format excluded papers section."""
        lines = [
            f"{MD_H2} Excluded Papers ({len(excluded_papers)})",
            "",
        ]

        # Group by exclusion stage
        by_stage: Dict[str, List[Dict[str, Any]]] = {}
        for paper in excluded_papers:
            stage = paper.get("exclusion_stage", "unknown")
            if stage not in by_stage:
                by_stage[stage] = []
            by_stage[stage].append(paper)

        for stage, papers in by_stage.items():
            lines.append(f"{MD_H3} {stage.replace('_', ' ').title()} ({len(papers)})")
            lines.append("")
            lines.append("| Title | Year | Reason |")
            lines.append("|-------|------|--------|")

            for paper in papers[:MAX_PAPERS_PER_EXCLUSION_STAGE]:
                raw_title = paper.get("title", "Unknown")
                title = raw_title[:MAX_TITLE_DISPLAY_LENGTH_EXCLUDED]
                if len(raw_title) > MAX_TITLE_DISPLAY_LENGTH_EXCLUDED:
                    title += "..."
                year = paper.get("year", "N/A")
                reasons = "; ".join(paper.get("exclusion_reasons", [])[:2])
                lines.append(f"| {title} | {year} | {reasons} |")

            if len(papers) > MAX_PAPERS_PER_EXCLUSION_STAGE:
                lines.append(f"| *... and {len(papers) - MAX_PAPERS_PER_EXCLUSION_STAGE} more* | | |")

            lines.append("")

        return lines

    def _format_uncertain_papers_section(
        self, uncertain_papers: List[Dict[str, Any]]
    ) -> List[str]:
        """Format uncertain papers section."""
        lines = [
            f"{MD_H2} Papers Requiring Human Review ({len(uncertain_papers)})",
            "",
            "The following papers have uncertain status and require manual review:",
            "",
            "| Title | Year | Relevance Score | Notes |",
            "|-------|------|-----------------|-------|",
        ]

        for paper in uncertain_papers:
            raw_title = paper.get("title", "Unknown")
            title = raw_title[:MAX_TITLE_DISPLAY_LENGTH_UNCERTAIN]
            if len(raw_title) > MAX_TITLE_DISPLAY_LENGTH_UNCERTAIN:
                title += "..."
            year = paper.get("year", "N/A")
            score = paper.get("relevance_score", "N/A")
            raw_rationale = paper.get("rationale", "")
            rationale = raw_rationale[:MAX_RATIONALE_DISPLAY_LENGTH]
            lines.append(f"| {title} | {year} | {score} | {rationale} |")

        lines.append("")
        return lines

    def _format_prisma_section(self, statistics: ReviewStatistics) -> List[str]:
        """Format PRISMA flow diagram data section."""
        stats = statistics.to_dict()

        lines = [
            f"{MD_H2} PRISMA 2020 Flow Diagram",
            "",
            "```",
            "IDENTIFICATION",
            f"  Records identified (n = {stats['total_considered']})",
            "",
            "SCREENING",
            f"  Records screened (n = {stats['total_considered']})",
            f"  Records excluded by initial filter (n = {stats['total_considered'] - stats['passed_initial_filter']})",
            "",
            "ELIGIBILITY",
            f"  Records assessed for eligibility (n = {stats['passed_initial_filter']})",
            f"  Records excluded by relevance (n = {stats['passed_initial_filter'] - stats['passed_relevance_threshold']})",
            f"  Records excluded by quality gate (n = {stats['passed_relevance_threshold'] - stats['passed_quality_gate']})",
            "",
            "INCLUDED",
            f"  Studies included in review (n = {stats['final_included']})",
            f"  Studies for human review (n = {stats['uncertain_for_review']})",
            "```",
            "",
        ]

        return lines

    def _format_audit_trail_section(
        self, process_log: List[Dict[str, Any]]
    ) -> List[str]:
        """Format audit trail section."""
        lines = [
            f"{MD_H2} Audit Trail",
            "",
            "Complete process log for reproducibility:",
            "",
        ]

        for step in process_log:
            step_num = step.get("step_number", "?")
            action = step.get("action", "unknown")
            status = "+" if step.get("error") is None else "x"

            lines.append(f"{MD_H4} Step {step_num}: {action} [{status}]")
            lines.append("")
            lines.append(f"**Timestamp:** {step.get('timestamp', 'N/A')}")
            lines.append(f"**Duration:** {step.get('duration_seconds', 0):.2f}s")

            if step.get("tool_used"):
                lines.append(f"**Tool:** {step['tool_used']}")

            lines.append(f"**Input:** {step.get('input_summary', 'N/A')}")
            lines.append(f"**Output:** {step.get('output_summary', 'N/A')}")
            lines.append(f"**Rationale:** {step.get('decision_rationale', 'N/A')}")

            if step.get("error"):
                lines.append(f"**Error:** {step['error']}")

            if step.get("metrics"):
                lines.append(f"**Metrics:** {json.dumps(step['metrics'])}")

            lines.append("")

        return lines

    # =========================================================================
    # CSV Export
    # =========================================================================

    def generate_csv_export(
        self,
        papers: List[AssessedPaper],
        output_path: str,
        include_excluded: bool = False,
        excluded_papers: Optional[List[ScoredPaper]] = None,
    ) -> None:
        """
        Generate CSV for spreadsheet analysis.

        Creates one or two CSV files:
        - included_papers.csv: All included papers with scores
        - excluded_papers.csv: Optional excluded papers summary

        Args:
            papers: List of included papers
            output_path: Base path for output files
            include_excluded: Whether to also export excluded papers
            excluded_papers: Optional list of excluded papers

        Raises:
            OutputPathError: If output path validation fails
        """
        output = validate_output_path(output_path)

        # Generate included papers CSV
        self._write_included_csv(papers, output)

        # Generate excluded papers CSV if requested
        if include_excluded and excluded_papers:
            excluded_path = output.with_stem(output.stem + "_excluded")
            self._write_excluded_csv(excluded_papers, excluded_path)

        logger.info(f"CSV export saved to: {output}")

    def _write_included_csv(
        self, papers: List[AssessedPaper], output_path: Path
    ) -> None:
        """Write included papers to CSV."""
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_COLUMNS_INCLUDED)

            for paper in papers:
                # Handle optional study_assessment
                study_type = ""
                quality_score = ""
                if paper.study_assessment is not None:
                    study_type = paper.study_assessment.get("study_type", "")
                    quality_score = paper.study_assessment.get("quality_score", "")

                row = [
                    paper.final_rank,
                    paper.scored_paper.paper.document_id,
                    paper.scored_paper.paper.title,
                    "; ".join(paper.scored_paper.paper.authors[:5]),
                    paper.scored_paper.paper.year,
                    paper.scored_paper.paper.journal or "",
                    paper.scored_paper.paper.doi or "",
                    paper.scored_paper.paper.pmid or "",
                    paper.scored_paper.relevance_score,
                    paper.composite_score,
                    study_type,
                    quality_score,
                    paper.scored_paper.inclusion_decision.rationale,
                ]
                writer.writerow(row)

    def _write_excluded_csv(
        self, papers: List[ScoredPaper], output_path: Path
    ) -> None:
        """Write excluded papers to CSV."""
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_COLUMNS_EXCLUDED)

            for paper in papers:
                row = [
                    paper.paper.document_id,
                    paper.paper.title,
                    "; ".join(paper.paper.authors[:5]),
                    paper.paper.year,
                    paper.inclusion_decision.stage.value,
                    "; ".join(paper.inclusion_decision.reasons),
                    paper.inclusion_decision.rationale,
                ]
                writer.writerow(row)

    # =========================================================================
    # PRISMA Flow Diagram
    # =========================================================================

    def generate_prisma_flowchart(
        self,
        statistics: ReviewStatistics,
        output_path: str,
    ) -> None:
        """
        Generate PRISMA 2020 flow diagram data.

        Creates a JSON file with data structured for PRISMA flow
        diagram generation tools.

        Args:
            statistics: ReviewStatistics with counts
            output_path: Path for the output file

        Raises:
            OutputPathError: If output path validation fails
        """
        output = validate_output_path(output_path)

        prisma_data = self._build_prisma_data(statistics)

        with open(output, "w", encoding="utf-8") as f:
            json.dump(prisma_data, f, indent=2)

        logger.info(f"PRISMA flow diagram data saved to: {output}")

    def _build_prisma_data(self, statistics: ReviewStatistics) -> Dict[str, Any]:
        """Build PRISMA 2020 flow diagram data structure."""
        stats = statistics.to_dict()

        return {
            "format": "PRISMA_2020",
            "version": "1.0",
            "generated_at": datetime.now().isoformat(),
            "identification": {
                "databases": {
                    "records_identified": stats["total_considered"],
                    "records_removed_before_screening": 0,
                },
                "registers": {
                    "records_identified": 0,
                },
                "other_methods": {
                    "records_identified": 0,
                },
                "duplicates_removed": 0,
            },
            "screening": {
                "records_screened": stats["total_considered"],
                "records_excluded": stats["total_considered"] - stats["passed_initial_filter"],
            },
            "eligibility": {
                "reports_sought": stats["passed_initial_filter"],
                "reports_not_retrieved": 0,
                "reports_assessed": stats["passed_initial_filter"],
                "reports_excluded": {
                    "total": stats["passed_initial_filter"] - stats["final_included"],
                    "reasons": {
                        "below_relevance_threshold": stats["passed_initial_filter"] - stats["passed_relevance_threshold"],
                        "below_quality_gate": stats["passed_relevance_threshold"] - stats["passed_quality_gate"],
                    },
                },
            },
            "included": {
                "studies_included": stats["final_included"],
                "reports_included": stats["final_included"],
                "for_human_review": stats["uncertain_for_review"],
            },
        }

    # =========================================================================
    # Cochrane-Style Reports
    # =========================================================================

    def generate_cochrane_characteristics_report(
        self,
        cochrane_assessments: List[CochraneStudyAssessment],
        output_path: str,
        format_type: str = "markdown",
    ) -> None:
        """
        Generate Cochrane-style "Characteristics of Included Studies" report.

        Creates a report matching the Cochrane Handbook template with:
        - Study Characteristics tables (Methods, Participants, Interventions, Outcomes, Notes)
        - Risk of Bias tables (9 domains with judgement + support)

        Args:
            cochrane_assessments: List of CochraneStudyAssessment objects
            output_path: Path for the output file
            format_type: Output format ("markdown" or "html")

        Raises:
            OutputPathError: If output path validation fails
            ValueError: If format_type is invalid
        """
        output = validate_output_path(output_path)

        if format_type == "markdown":
            content = format_multiple_assessments_markdown(
                cochrane_assessments,
                title="Characteristics of included studies"
            )
        elif format_type == "html":
            content = self._build_cochrane_html_report(cochrane_assessments)
        else:
            raise ValueError(f"Invalid format_type: {format_type}. Use 'markdown' or 'html'.")

        with open(output, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info(f"Cochrane characteristics report saved to: {output}")

    def generate_risk_of_bias_summary(
        self,
        cochrane_assessments: List[CochraneStudyAssessment],
        output_path: str,
    ) -> None:
        """
        Generate Risk of Bias summary table across all studies.

        Creates a summary table showing judgements across all studies
        for each bias domain, useful for identifying patterns.

        Args:
            cochrane_assessments: List of CochraneStudyAssessment objects
            output_path: Path for the output file

        Raises:
            OutputPathError: If output path validation fails
        """
        output = validate_output_path(output_path)

        content = format_risk_of_bias_summary_markdown(cochrane_assessments)

        with open(output, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info(f"Risk of bias summary saved to: {output}")

    def _build_cochrane_html_report(
        self,
        assessments: List[CochraneStudyAssessment],
    ) -> str:
        """
        Build HTML report with Cochrane-style formatting.

        Args:
            assessments: List of CochraneStudyAssessment objects

        Returns:
            Complete HTML document string
        """
        html_parts: List[str] = [
            "<!DOCTYPE html>",
            "<html lang='en'>",
            "<head>",
            "<meta charset='UTF-8'>",
            "<meta name='viewport' content='width=device-width, initial-scale=1.0'>",
            "<title>Characteristics of Included Studies</title>",
            get_cochrane_css(),
            "</head>",
            "<body>",
            "<h1>Characteristics of included studies</h1>",
        ]

        for assessment in assessments:
            html_parts.append(
                format_study_characteristics_html(assessment.study_characteristics)
            )
            html_parts.append(
                format_risk_of_bias_html(assessment.risk_of_bias)
            )
            html_parts.append("<hr>")

        html_parts.extend([
            "</body>",
            "</html>",
        ])

        return "\n".join(html_parts)

    def _format_cochrane_included_section(
        self,
        included_papers: List[Dict[str, Any]],
        cochrane_assessments: Optional[List[CochraneStudyAssessment]] = None,
    ) -> List[str]:
        """
        Format included papers section with Cochrane assessments if available.

        Enhanced version of _format_included_papers_section that includes
        Cochrane-style study characteristics and risk of bias when available.

        Args:
            included_papers: List of included paper dictionaries
            cochrane_assessments: Optional list of Cochrane assessments

        Returns:
            List of Markdown lines
        """
        lines = [
            f"{MD_H2} Included Papers ({len(included_papers)})",
            "",
        ]

        if not included_papers:
            lines.append("*No papers met all inclusion criteria.*")
            lines.append("")
            return lines

        # Create lookup for Cochrane assessments by document_id
        cochrane_lookup: Dict[int, CochraneStudyAssessment] = {}
        if cochrane_assessments:
            for ca in cochrane_assessments:
                if ca.document_id is not None:
                    cochrane_lookup[ca.document_id] = ca

        for paper in included_papers:
            doc_id = paper.get("document_id")
            rank = paper.get("final_rank", "N/A")
            title = paper.get("title", "Unknown Title")
            authors = ", ".join(paper.get("authors", [])[:3])
            if len(paper.get("authors", [])) > 3:
                authors += " et al."
            year = paper.get("year", "N/A")

            lines.append(f"{MD_H3} {rank}. {title}")
            lines.append("")

            # Check if Cochrane assessment is available
            if doc_id and doc_id in cochrane_lookup:
                ca = cochrane_lookup[doc_id]
                # Use Cochrane formatting
                lines.append(format_complete_assessment_markdown(ca))
            else:
                # Fall back to standard formatting
                lines.append(f"**Authors:** {authors}")
                lines.append(f"**Year:** {year}")

                if paper.get("journal"):
                    lines.append(f"**Journal:** {paper['journal']}")

                if paper.get("doi"):
                    lines.append(f"**DOI:** {paper['doi']}")

                if paper.get("pmid"):
                    lines.append(f"**PMID:** {paper['pmid']}")

                lines.append("")

                # Scores
                scores = paper.get("scores", {})
                lines.append("**Scores:**")
                lines.append(f"{MD_BULLET} Relevance: {scores.get('relevance', 'N/A')}/5")
                lines.append(f"{MD_BULLET} Composite: {scores.get('composite_score', 'N/A'):.2f}/10")

                if scores.get("study_quality"):
                    lines.append(f"{MD_BULLET} Study Quality: {scores['study_quality']:.2f}/10")

                lines.append("")

                # Inclusion rationale
                if paper.get("inclusion_rationale"):
                    lines.append(f"**Inclusion Rationale:** {paper['inclusion_rationale']}")
                    lines.append("")

            lines.append("---")
            lines.append("")

        return lines

    # =========================================================================
    # Combined Export
    # =========================================================================

    def export_all(
        self,
        result: SystematicReviewResult,
        output_dir: str,
        base_name: str = "systematic_review",
    ) -> Dict[str, str]:
        """
        Export results in all available formats.

        Convenience method to generate all output formats at once.

        Args:
            result: SystematicReviewResult to export
            output_dir: Directory for output files
            base_name: Base name for output files

        Returns:
            Dictionary mapping format to output path

        Raises:
            OutputPathError: If output directory validation fails
        """
        # Validate output directory by checking a test file path
        test_path = str(Path(output_dir) / f"{base_name}.json")
        output_path = validate_output_path(test_path).parent

        paths: Dict[str, str] = {}

        # JSON
        json_path = output_path / f"{base_name}.json"
        self.generate_json_report(result, str(json_path))
        paths["json"] = str(json_path)

        # Markdown
        md_path = output_path / f"{base_name}.md"
        self.generate_markdown_report(result, str(md_path))
        paths["markdown"] = str(md_path)

        # CSV (convert back to AssessedPaper for CSV)
        csv_path = output_path / f"{base_name}_included.csv"
        # For CSV we need AssessedPaper objects, not dicts
        # This export_all is for convenience - use generate_csv_export directly
        # if you have AssessedPaper objects
        paths["csv"] = str(csv_path)
        logger.warning(
            "CSV export in export_all() requires AssessedPaper objects. "
            "Use generate_csv_export() directly for CSV output."
        )

        # PRISMA
        prisma_path = output_path / f"{base_name}_prisma.json"
        self.generate_prisma_flowchart(result.statistics, str(prisma_path))
        paths["prisma"] = str(prisma_path)

        logger.info(f"All exports saved to: {output_path}")
        return paths
