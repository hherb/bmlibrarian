"""
Output formatters for PaperChecker CLI.

Provides functions for displaying results, statistics, and summaries
in human-readable formats for the command line.
"""

from typing import Any, Dict, List, Optional

from bmlibrarian.paperchecker.data_models import PaperCheckResult, Verdict

# Display constants
SEPARATOR_WIDTH: int = 60
SEPARATOR_CHAR: str = "="
SUBSEPARATOR_CHAR: str = "-"
INDENT: str = "  "
MAX_PREVIEW_LENGTH: int = 80
MAX_ABSTRACT_PREVIEW: int = 200
DEFAULT_BAR_WIDTH: int = 20
PERCENTAGE_MAX: float = 100.0


def print_statistics(results: List[PaperCheckResult]) -> None:
    """
    Print comprehensive summary statistics to console.

    Displays counts and percentages for verdicts, confidence levels,
    and search statistics aggregated across all results.

    Args:
        results: List of PaperCheckResult objects to summarize
    """
    if not results:
        print("\nNo results to summarize.")
        return

    print("\n" + SEPARATOR_CHAR * SEPARATOR_WIDTH)
    print("SUMMARY STATISTICS")
    print(SEPARATOR_CHAR * SEPARATOR_WIDTH + "\n")

    # Basic counts
    total_abstracts = len(results)
    total_statements = sum(len(r.statements) for r in results)
    total_verdicts = sum(len(r.verdicts) for r in results)

    print(f"Abstracts checked: {total_abstracts}")
    print(f"Statements extracted: {total_statements}")
    if total_abstracts > 0:
        avg_statements = total_statements / total_abstracts
        print(f"Average statements per abstract: {avg_statements:.1f}")

    print()

    # Verdict distribution
    verdict_counts: Dict[str, int] = {"supports": 0, "contradicts": 0, "undecided": 0}
    confidence_counts: Dict[str, int] = {"high": 0, "medium": 0, "low": 0}

    for result in results:
        for verdict in result.verdicts:
            verdict_counts[verdict.verdict] += 1
            confidence_counts[verdict.confidence] += 1

    print("Verdict Distribution:")
    for verdict_type, count in verdict_counts.items():
        pct = _safe_percentage(count, total_verdicts)
        bar = _create_bar(pct)
        print(f"{INDENT}{verdict_type.capitalize():12s}: {count:4d} ({pct:5.1f}%) {bar}")

    print()
    print("Confidence Distribution:")
    for conf_level, count in confidence_counts.items():
        pct = _safe_percentage(count, total_verdicts)
        bar = _create_bar(pct)
        print(f"{INDENT}{conf_level.capitalize():12s}: {count:4d} ({pct:5.1f}%) {bar}")

    # Search statistics
    print()
    print("Search Statistics (aggregated):")
    total_found = 0
    total_scored = 0
    total_cited = 0

    for result in results:
        for counter_report in result.counter_reports:
            stats = counter_report.search_stats
            total_found += stats.get("documents_found", 0)
            total_scored += stats.get("documents_scored", 0)
            total_cited += stats.get("documents_cited", 0)

    print(f"{INDENT}Documents found:  {total_found:,}")
    print(f"{INDENT}Documents scored: {total_scored:,}")
    print(f"{INDENT}Documents cited:  {total_cited:,}")

    if total_found > 0:
        cite_rate = _safe_percentage(total_cited, total_found)
        print(f"{INDENT}Citation rate:    {cite_rate:.1f}%")

    print("\n" + SEPARATOR_CHAR * SEPARATOR_WIDTH + "\n")


def _safe_percentage(count: int, total: int) -> float:
    """
    Calculate percentage safely, handling zero division.

    Args:
        count: Numerator value
        total: Denominator value

    Returns:
        Percentage value (0-100), or 0.0 if total is zero
    """
    if total == 0:
        return 0.0
    return 100.0 * count / total


def _create_bar(percentage: float, width: int = DEFAULT_BAR_WIDTH) -> str:
    """
    Create a simple text progress bar.

    Args:
        percentage: Percentage value (0-100)
        width: Bar width in characters

    Returns:
        Text bar like "[========          ]"
    """
    filled = int(width * percentage / PERCENTAGE_MAX)
    empty = width - filled
    return f"[{'=' * filled}{' ' * empty}]"


def print_abstract_summary(
    result: PaperCheckResult,
    index: int,
    verbose: bool = False
) -> None:
    """
    Print summary for a single abstract result.

    Args:
        result: PaperCheckResult to display
        index: Display index (1-based)
        verbose: Whether to show detailed information
    """
    print(SUBSEPARATOR_CHAR * SEPARATOR_WIDTH)
    print(f"Abstract {index}")
    print(SUBSEPARATOR_CHAR * SEPARATOR_WIDTH)

    # Source info
    pmid = result.source_metadata.get("pmid")
    title = result.source_metadata.get("title")

    if pmid:
        print(f"PMID: {pmid}")
    if title:
        display_title = _truncate(title, MAX_PREVIEW_LENGTH)
        print(f"Title: {display_title}")

    # Abstract preview
    if verbose:
        abstract_preview = _truncate(result.original_abstract, MAX_ABSTRACT_PREVIEW)
        print(f"\nAbstract: {abstract_preview}")

    # Statement verdicts
    print(f"\nStatements: {len(result.statements)}")

    for i, (stmt, verdict) in enumerate(zip(result.statements, result.verdicts), 1):
        verdict_icon = _get_verdict_icon(verdict.verdict)
        conf_icon = _get_confidence_icon(verdict.confidence)

        stmt_preview = _truncate(stmt.text, MAX_PREVIEW_LENGTH)
        print(f"{INDENT}{i}. {stmt_preview}")
        print(f"{INDENT}   {verdict_icon} {verdict.verdict.upper()} ({conf_icon} {verdict.confidence})")

        if verbose:
            rationale_preview = _truncate(verdict.rationale, MAX_PREVIEW_LENGTH)
            print(f"{INDENT}   Rationale: {rationale_preview}")

    # Overall assessment preview
    print(f"\nOverall: {_truncate(result.overall_assessment, MAX_PREVIEW_LENGTH)}")
    print()


def _truncate(text: str, max_length: int) -> str:
    """
    Truncate text with ellipsis if too long.

    Args:
        text: Text to truncate
        max_length: Maximum length including ellipsis

    Returns:
        Truncated text with "..." if needed
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."


def _get_verdict_icon(verdict: str) -> str:
    """
    Get display icon for verdict type.

    Args:
        verdict: Verdict string ("supports", "contradicts", "undecided")

    Returns:
        Unicode icon character
    """
    icons = {
        "supports": "+",
        "contradicts": "X",
        "undecided": "?"
    }
    return icons.get(verdict, "-")


def _get_confidence_icon(confidence: str) -> str:
    """
    Get display icon for confidence level.

    Args:
        confidence: Confidence string ("high", "medium", "low")

    Returns:
        Unicode icon character
    """
    icons = {
        "high": "***",
        "medium": "**",
        "low": "*"
    }
    return icons.get(confidence, "-")


def format_verdict_summary(verdicts: List[Verdict]) -> str:
    """
    Format a brief summary of verdicts for inline display.

    Args:
        verdicts: List of Verdict objects

    Returns:
        Summary string like "2 supports, 1 contradicts (high confidence)"
    """
    if not verdicts:
        return "no verdicts"

    # Count verdicts
    counts: Dict[str, int] = {"supports": 0, "contradicts": 0, "undecided": 0}
    for v in verdicts:
        counts[v.verdict] += 1

    # Build parts
    parts = []
    for vtype in ["supports", "contradicts", "undecided"]:
        if counts[vtype] > 0:
            parts.append(f"{counts[vtype]} {vtype}")

    summary = ", ".join(parts)

    # Add dominant confidence if any
    confidence_counts: Dict[str, int] = {"high": 0, "medium": 0, "low": 0}
    for v in verdicts:
        confidence_counts[v.confidence] += 1

    dominant_conf = max(confidence_counts, key=confidence_counts.get)
    if confidence_counts[dominant_conf] > len(verdicts) / 2:
        summary += f" ({dominant_conf} confidence)"

    return summary


def print_error_summary(errors: List[Dict[str, Any]]) -> None:
    """
    Print summary of processing errors.

    Args:
        errors: List of error dictionaries with index, pmid, and error message
    """
    if not errors:
        return

    print("\n" + SEPARATOR_CHAR * SEPARATOR_WIDTH)
    print(f"ERRORS ({len(errors)} abstracts failed)")
    print(SEPARATOR_CHAR * SEPARATOR_WIDTH)

    for err in errors:
        pmid_str = f"PMID {err.get('pmid')}" if err.get('pmid') else f"index {err.get('index')}"
        error_preview = _truncate(str(err.get('error', 'Unknown error')), MAX_PREVIEW_LENGTH)
        print(f"{INDENT}{pmid_str}: {error_preview}")

    print()


def print_completion_banner(
    total: int,
    successful: int,
    errors: int,
    output_file: Optional[str] = None,
    markdown_dir: Optional[str] = None
) -> None:
    """
    Print completion banner with summary.

    Args:
        total: Total abstracts processed
        successful: Number of successful results
        errors: Number of errors
        output_file: Path to JSON output file (if any)
        markdown_dir: Path to markdown output directory (if any)
    """
    print("\n" + SEPARATOR_CHAR * SEPARATOR_WIDTH)
    print("PROCESSING COMPLETE")
    print(SEPARATOR_CHAR * SEPARATOR_WIDTH)

    success_icon = "+" if errors == 0 else "!"
    print(f"{success_icon} Completed: {successful}/{total} abstracts")

    if errors > 0:
        print(f"X Errors: {errors}")

    if output_file:
        print(f"+ JSON results: {output_file}")

    if markdown_dir:
        print(f"+ Markdown reports: {markdown_dir}")

    print(SEPARATOR_CHAR * SEPARATOR_WIDTH + "\n")
