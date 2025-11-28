#!/usr/bin/env python3
"""
Systematic Review CLI - AI-Assisted Systematic Literature Review Tool

A comprehensive command-line interface for conducting systematic literature reviews
with AI assistance, human oversight at key checkpoints, and complete audit trails.

Features:
- PICO-based query generation for clinical questions
- Multi-strategy search (semantic, keyword, hybrid, HyDE)
- LLM-powered relevance scoring and quality assessment
- Study type filtering and exclusion criteria
- PRISMA 2020 flow diagram generation
- Complete audit trail for reproducibility
- Multiple output formats (JSON, Markdown, CSV)

Workflow:
1. Define search criteria (research question, inclusion/exclusion)
2. Generate search plan with diverse queries
3. Execute searches and collect candidate papers
4. Apply initial filters (date, language, study type)
5. Score relevance using LLM
6. Evaluate quality using multiple agents
7. Rank papers by composite score
8. Generate comprehensive report

Usage:
    python systematic_review_cli.py [options]

    Basic usage:
    python systematic_review_cli.py --question "What is the effect of statins on CVD?"

    With criteria file:
    python systematic_review_cli.py --criteria-file my_criteria.json

    Full example:
    python systematic_review_cli.py \\
        --question "Effect of exercise on depression" \\
        --purpose "Clinical guideline development" \\
        --include "RCTs" "Human studies" \\
        --exclude "Animal studies" "Case reports" \\
        --output-dir ./review_output \\
        --auto

Requirements:
- PostgreSQL database with biomedical literature and pgvector extension
- Ollama service running locally (http://localhost:11434)
- Required models configured in ~/.bmlibrarian/config.json
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from bmlibrarian.agents.systematic_review import (
    SystematicReviewAgent,
    SearchCriteria,
    ScoringWeights,
    StudyTypeFilter,
    SystematicReviewConfig,
    get_systematic_review_config,
)


# =============================================================================
# Constants
# =============================================================================

LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# Default scoring weights (sum to 1.0)
# This comprehensive weight set supports both Cochrane-style systematic review
# dimensions and BMLibrarian's practical paper weight assessment dimensions.
DEFAULT_WEIGHTS = {
    "relevance": 0.25,
    "study_quality": 0.20,
    "methodological_rigor": 0.15,
    "sample_size": 0.05,
    "recency": 0.10,
    "replication_status": 0.05,
    "paper_weight": 0.15,
    "source_reliability": 0.05,
}


# =============================================================================
# CLI Functions
# =============================================================================

def setup_logging(verbose: bool = False, log_file: Optional[str] = None) -> None:
    """
    Configure logging for the CLI.

    Args:
        verbose: Enable debug logging
        log_file: Optional path to log file
    """
    level = logging.DEBUG if verbose else logging.INFO

    handlers: List[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    if log_file:
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(
        level=level,
        format=LOG_FORMAT,
        handlers=handlers,
    )


def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments.

    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description="AI-Assisted Systematic Literature Review Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Basic review
    python systematic_review_cli.py --question "Effect of statins on CVD?"

    # With inclusion/exclusion criteria
    python systematic_review_cli.py \\
        --question "Exercise and depression treatment" \\
        --include "RCTs" "Adult patients" \\
        --exclude "Animal studies"

    # Load criteria from file
    python systematic_review_cli.py --criteria-file review_criteria.json

    # Automatic mode (no checkpoints)
    python systematic_review_cli.py --question "..." --auto
        """,
    )

    # Research question
    parser.add_argument(
        "-q", "--question",
        type=str,
        help="Research question for the systematic review",
    )

    parser.add_argument(
        "--purpose",
        type=str,
        default="Systematic literature review",
        help="Purpose of the review (default: Systematic literature review)",
    )

    # Criteria
    parser.add_argument(
        "--include",
        nargs="+",
        metavar="CRITERION",
        help="Inclusion criteria (multiple allowed)",
    )

    parser.add_argument(
        "--exclude",
        nargs="+",
        metavar="CRITERION",
        help="Exclusion criteria (multiple allowed)",
    )

    parser.add_argument(
        "--study-types",
        nargs="+",
        choices=[st.value for st in StudyTypeFilter],
        help="Target study types (e.g., rct cohort_prospective)",
    )

    parser.add_argument(
        "--date-range",
        nargs=2,
        type=int,
        metavar=("START_YEAR", "END_YEAR"),
        help="Date range filter (e.g., 2018 2024)",
    )

    parser.add_argument(
        "--mesh-terms",
        nargs="+",
        metavar="TERM",
        help="MeSH terms to include in search",
    )

    # Criteria from file
    parser.add_argument(
        "--criteria-file",
        type=str,
        help="Path to JSON file with search criteria",
    )

    # Weights
    parser.add_argument(
        "--weights-file",
        type=str,
        help="Path to JSON file with scoring weights",
    )

    parser.add_argument(
        "--weight-preset",
        choices=["balanced", "cochrane", "practical"],
        default="balanced",
        help=(
            "Weight preset: 'balanced' (default, combines all dimensions), "
            "'cochrane' (emphasizes methodological rigor, sample size, replication), "
            "'practical' (emphasizes paper_weight, source_reliability)"
        ),
    )

    parser.add_argument(
        "--relevance-weight",
        type=float,
        help="Weight for relevance score (0.0-1.0)",
    )

    parser.add_argument(
        "--quality-weight",
        type=float,
        help="Weight for study quality score (0.0-1.0)",
    )

    # Thresholds
    parser.add_argument(
        "--relevance-threshold",
        type=float,
        default=3.0,
        help="Minimum relevance score (1-5, default: 3.0)",
    )

    parser.add_argument(
        "--quality-threshold",
        type=float,
        default=5.0,
        help="Minimum quality threshold (0-10, default: 5.0)",
    )

    # Output options
    parser.add_argument(
        "-o", "--output-dir",
        type=str,
        help="Output directory for results (default: from config, typically ~/.bmlibrarian/systematic_reviews)",
    )

    parser.add_argument(
        "--output-name",
        type=str,
        help="Base name for output files (default: auto-generated)",
    )

    parser.add_argument(
        "--format",
        choices=["json", "markdown", "csv", "all"],
        default="all",
        help="Output format(s) (default: all)",
    )

    # Execution mode
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Automatic mode: skip all checkpoints",
    )

    parser.add_argument(
        "--quick",
        action="store_true",
        help="Quick mode: use reduced limits for faster testing",
    )

    # Logging
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose (debug) logging",
    )

    parser.add_argument(
        "--log-file",
        type=str,
        help="Path to log file",
    )

    # Resume from checkpoint
    parser.add_argument(
        "--resume",
        type=str,
        metavar="REVIEW_ID_OR_PATH",
        help="Resume review from checkpoint file (provide review ID or path to checkpoint JSON)",
    )

    # Display status
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show status of any running/completed reviews",
    )

    return parser.parse_args()


def load_criteria_from_file(filepath: str) -> SearchCriteria:
    """
    Load search criteria from JSON file.

    Args:
        filepath: Path to JSON file

    Returns:
        SearchCriteria instance

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If file format is invalid
    """
    path = Path(filepath).expanduser()

    if not path.exists():
        raise FileNotFoundError(f"Criteria file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Convert study types if present
    if "target_study_types" in data:
        data["target_study_types"] = [
            StudyTypeFilter(st) for st in data["target_study_types"]
        ]

    # Convert date range tuple
    if "date_range" in data and isinstance(data["date_range"], list):
        data["date_range"] = tuple(data["date_range"])

    return SearchCriteria(**data)


def load_weights_from_file(filepath: str) -> ScoringWeights:
    """
    Load scoring weights from JSON file.

    Args:
        filepath: Path to JSON file

    Returns:
        ScoringWeights instance
    """
    path = Path(filepath).expanduser()

    if not path.exists():
        raise FileNotFoundError(f"Weights file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return ScoringWeights(**data)


def build_criteria_from_args(args: argparse.Namespace) -> SearchCriteria:
    """
    Build SearchCriteria from command-line arguments.

    Args:
        args: Parsed arguments

    Returns:
        SearchCriteria instance

    Raises:
        ValueError: If required arguments are missing
    """
    # If criteria file specified, load from file
    if args.criteria_file:
        criteria = load_criteria_from_file(args.criteria_file)

        # Override with command-line args if provided
        if args.question:
            criteria = SearchCriteria(
                research_question=args.question,
                purpose=criteria.purpose,
                inclusion_criteria=criteria.inclusion_criteria,
                exclusion_criteria=criteria.exclusion_criteria,
                target_study_types=criteria.target_study_types,
                date_range=criteria.date_range,
                mesh_terms=criteria.mesh_terms,
            )

        return criteria

    # Build from arguments
    if not args.question:
        raise ValueError(
            "Research question is required. "
            "Use --question or --criteria-file."
        )

    # Parse study types
    study_types = None
    if args.study_types:
        study_types = [StudyTypeFilter(st) for st in args.study_types]

    # Parse date range
    date_range = None
    if args.date_range:
        date_range = tuple(args.date_range)

    return SearchCriteria(
        research_question=args.question,
        purpose=args.purpose,
        inclusion_criteria=args.include or [],
        exclusion_criteria=args.exclude or [],
        target_study_types=study_types,
        date_range=date_range,
        mesh_terms=args.mesh_terms,
    )


def apply_weight_overrides(
    weights: ScoringWeights, args: argparse.Namespace
) -> ScoringWeights:
    """
    Apply command-line weight overrides to existing weights.

    Creates a new ScoringWeights instance with any command-line specified
    weight values overriding the base weights. Only relevance_weight and
    quality_weight can be overridden via CLI.

    Args:
        weights: Base ScoringWeights to override
        args: Parsed arguments with potential weight overrides

    Returns:
        New ScoringWeights with overrides applied, or original if no overrides
    """
    overrides: Dict[str, float] = {}

    if args.relevance_weight is not None:
        overrides["relevance"] = args.relevance_weight
    if args.quality_weight is not None:
        overrides["study_quality"] = args.quality_weight

    if overrides:
        return ScoringWeights(**{**weights.to_dict(), **overrides})
    return weights


def build_weights_from_args(args: argparse.Namespace) -> ScoringWeights:
    """
    Build ScoringWeights from command-line arguments.

    Supports both:
    - Cochrane-style dimensions: methodological_rigor, sample_size, replication_status
    - BMLibrarian dimensions: paper_weight, source_reliability

    Weight presets:
    - 'balanced': Default weights combining all dimensions
    - 'cochrane': Emphasizes Cochrane systematic review methodology
    - 'practical': Emphasizes BMLibrarian paper weight assessment

    Args:
        args: Parsed arguments

    Returns:
        ScoringWeights instance
    """
    # If weights file specified, load from file (highest priority)
    if args.weights_file:
        weights = load_weights_from_file(args.weights_file)
        return apply_weight_overrides(weights, args)

    # Check for weight preset
    preset = getattr(args, "weight_preset", "balanced")

    if preset == "cochrane":
        weights = ScoringWeights.cochrane_focused()
    elif preset == "practical":
        weights = ScoringWeights.practical_focused()
    else:
        # Use balanced defaults
        weights = ScoringWeights(
            relevance=DEFAULT_WEIGHTS["relevance"],
            study_quality=DEFAULT_WEIGHTS["study_quality"],
            methodological_rigor=DEFAULT_WEIGHTS["methodological_rigor"],
            sample_size=DEFAULT_WEIGHTS["sample_size"],
            recency=DEFAULT_WEIGHTS["recency"],
            replication_status=DEFAULT_WEIGHTS["replication_status"],
            paper_weight=DEFAULT_WEIGHTS["paper_weight"],
            source_reliability=DEFAULT_WEIGHTS["source_reliability"],
        )

    # Apply command-line overrides if provided
    return apply_weight_overrides(weights, args)


def get_output_dir(args: argparse.Namespace, config: SystematicReviewConfig) -> Path:
    """
    Get output directory, creating if necessary.

    Uses the configuration system for default path.

    Args:
        args: Parsed arguments
        config: SystematicReviewConfig instance

    Returns:
        Path to output directory
    """
    if args.output_dir:
        output_dir = Path(args.output_dir).expanduser()
    else:
        # Use output_dir from configuration system
        output_dir = Path(config.output_dir).expanduser()

    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def get_output_name(args: argparse.Namespace, criteria: SearchCriteria) -> str:
    """
    Generate output file base name.

    Args:
        args: Parsed arguments
        criteria: Search criteria

    Returns:
        Base name for output files
    """
    if args.output_name:
        return args.output_name

    # Generate from question and timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Sanitize question for filename
    question_part = criteria.research_question[:30].lower()
    question_part = "".join(c if c.isalnum() else "_" for c in question_part)
    question_part = "_".join(question_part.split())

    return f"review_{question_part}_{timestamp}"


def print_banner() -> None:
    """Print CLI banner."""
    print()
    print("=" * 70)
    print("  Systematic Literature Review Agent")
    print("  AI-Assisted Evidence Synthesis Tool")
    print("=" * 70)
    print()


def print_criteria_summary(criteria: SearchCriteria) -> None:
    """Print summary of search criteria."""
    print("Search Criteria:")
    print("-" * 50)
    print(f"  Research Question: {criteria.research_question}")
    print(f"  Purpose: {criteria.purpose}")

    if criteria.inclusion_criteria:
        print(f"  Inclusion Criteria:")
        for c in criteria.inclusion_criteria:
            print(f"    - {c}")

    if criteria.exclusion_criteria:
        print(f"  Exclusion Criteria:")
        for c in criteria.exclusion_criteria:
            print(f"    - {c}")

    if criteria.target_study_types:
        types = ", ".join(st.value for st in criteria.target_study_types)
        print(f"  Target Study Types: {types}")

    if criteria.date_range:
        print(f"  Date Range: {criteria.date_range[0]} - {criteria.date_range[1]}")

    print()


def progress_callback(event: str, data: str) -> None:
    """
    Progress callback for agent events.

    Args:
        event: Event type
        data: Event data/message
    """
    # Format based on event type
    if event.endswith("_started"):
        print(f"\n[>] {data}")
    elif event.endswith("_completed"):
        print(f"[+] {data}")
    elif event.endswith("_failed"):
        print(f"[!] {data}")
    else:
        print(f"    {data}")


def checkpoint_callback(
    checkpoint_type: str,
    state: Dict[str, Any],
) -> bool:
    """
    Interactive checkpoint callback.

    Args:
        checkpoint_type: Type of checkpoint
        state: Current state information

    Returns:
        True to continue, False to abort
    """
    print()
    print(f"{'=' * 50}")
    print(f"CHECKPOINT: {checkpoint_type.upper()}")
    print(f"{'=' * 50}")

    # Display relevant state info
    for key, value in state.items():
        if isinstance(value, list) and len(value) > 5:
            print(f"  {key}: [{len(value)} items]")
        elif isinstance(value, dict) and len(value) > 5:
            print(f"  {key}: {{{len(value)} keys}}")
        else:
            print(f"  {key}: {value}")

    print()

    while True:
        response = input("Continue? [Y/n/q]: ").strip().lower()

        if response in ("", "y", "yes"):
            return True
        elif response in ("n", "no", "q", "quit"):
            print("Review aborted by user.")
            return False
        else:
            print("Please enter 'y' to continue or 'n' to abort.")


def run_review(args: argparse.Namespace) -> int:
    """
    Run the systematic review.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    print_banner()

    try:
        # Build criteria and weights
        criteria = build_criteria_from_args(args)
        weights = build_weights_from_args(args)

        print_criteria_summary(criteria)

        # Get config and apply overrides (needed for output_dir)
        config = get_systematic_review_config()

        # Get output paths (uses config for default output directory)
        output_dir = get_output_dir(args, config)
        output_name = get_output_name(args, criteria)
        output_path = output_dir / f"{output_name}.json"

        print(f"Output will be saved to: {output_dir}")
        print()

        if args.relevance_threshold:
            config.relevance_threshold = args.relevance_threshold

        if args.quality_threshold:
            config.quality_threshold = args.quality_threshold

        if args.quick:
            config.max_results_per_query = 50
            config.run_study_assessment = False
            config.run_paper_weight = True
            config.run_pico_extraction = False
            config.run_prisma_assessment = False
            print("Quick mode: Using reduced limits for faster testing")
            print()

        # Initialize agent
        agent = SystematicReviewAgent(
            config=config,
            callback=progress_callback,
        )

        # Run review
        interactive = not args.auto

        if args.auto:
            print("Running in automatic mode (no checkpoints)")
            print()

        result = agent.run_review(
            criteria=criteria,
            weights=weights,
            interactive=interactive,
            output_path=str(output_path) if not args.auto else None,
            checkpoint_callback=checkpoint_callback if interactive else None,
        )

        # Save results if not already saved
        if args.auto or args.format != "json":
            from bmlibrarian.agents.systematic_review.reporter import Reporter

            reporter = Reporter(
                documenter=agent.documenter,
                criteria=criteria,
                weights=weights,
            )

            # Save based on format
            if args.format in ("json", "all"):
                reporter.generate_json_report(result, str(output_path))
                print(f"\nJSON report saved: {output_path}")

            if args.format in ("markdown", "all"):
                md_path = output_dir / f"{output_name}.md"
                reporter.generate_markdown_report(result, str(md_path))
                print(f"Markdown report saved: {md_path}")

            if args.format in ("csv", "all"):
                csv_path = output_dir / f"{output_name}_included.csv"
                # CSV requires AssessedPaper objects, skip if not available
                print(f"CSV export: Use JSON data for spreadsheet analysis")

            # PRISMA flow diagram
            prisma_path = output_dir / f"{output_name}_prisma.json"
            reporter.generate_prisma_flowchart(result.statistics, str(prisma_path))
            print(f"PRISMA flow diagram data saved: {prisma_path}")

        # Print summary
        print()
        print("=" * 50)
        print("REVIEW COMPLETE")
        print("=" * 50)

        stats = result.statistics.to_dict()
        print(f"  Total papers considered: {stats['total_considered']}")
        print(f"  Passed initial filter: {stats['passed_initial_filter']}")
        print(f"  Passed relevance threshold: {stats['passed_relevance_threshold']}")
        print(f"  Final included: {stats['final_included']}")
        print(f"  Final excluded: {stats['final_excluded']}")
        print(f"  Uncertain (human review): {stats['uncertain_for_review']}")
        print(f"  Processing time: {stats['processing_time_seconds']:.2f}s")
        print()

        return 0

    except ValueError as e:
        print(f"\nError: {e}", file=sys.stderr)
        return 1
    except FileNotFoundError as e:
        print(f"\nFile not found: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n\nReview interrupted by user.")
        return 130
    except Exception as e:
        logging.exception("Unexpected error during review")
        print(f"\nError: {e}", file=sys.stderr)
        return 1


def show_status() -> int:
    """
    Show status of reviews (placeholder for future implementation).

    Returns:
        Exit code
    """
    config = get_systematic_review_config()
    output_dir = Path(config.output_dir).expanduser()
    print("Review status tracking is not yet implemented.")
    print(f"Check {output_dir} for completed reviews.")
    return 0


def resume_review(args: argparse.Namespace) -> int:
    """
    Resume a systematic review from a checkpoint.

    Args:
        args: Parsed command-line arguments with resume parameter

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    print_banner()

    try:
        # Find checkpoint file
        checkpoint_path = find_checkpoint_file(args.resume)

        if not checkpoint_path:
            print(f"Error: Could not find checkpoint for review: {args.resume}")
            print()
            print("Checkpoint files are stored in:")
            print("  <output_dir>/checkpoints/<review_id>_<checkpoint_type>.json")
            print()
            print("You can provide:")
            print("  - Full path to checkpoint file")
            print("  - Review ID (e.g., review_abc123def456)")
            return 1

        print(f"Resuming from checkpoint: {checkpoint_path}")
        print()

        # Load checkpoint to display info
        with open(checkpoint_path, "r", encoding="utf-8") as f:
            checkpoint_data = json.load(f)

        review_id = checkpoint_data.get("review_id", "unknown")
        checkpoint_type = checkpoint_data.get("checkpoint_type", "unknown")
        paper_count = checkpoint_data.get("paper_count", 0)
        timestamp = checkpoint_data.get("timestamp", "unknown")

        print("Checkpoint Information:")
        print(f"  Review ID: {review_id}")
        print(f"  Checkpoint Type: {checkpoint_type}")
        print(f"  Papers Saved: {paper_count}")
        print(f"  Created: {timestamp}")
        print()

        # Get config
        config = get_systematic_review_config()
        output_dir = get_output_dir(args, config)

        # Initialize agent
        agent = SystematicReviewAgent(
            config=config,
            callback=progress_callback,
        )

        # Determine output path
        output_name = f"{review_id}_resumed"
        output_path = output_dir / f"{output_name}.json"

        # Interactive mode unless --auto specified
        interactive = not args.auto

        if args.auto:
            print("Running in automatic mode (no checkpoints)")
            print()

        # Resume the review
        result = agent.run_review_from_checkpoint(
            checkpoint_path=str(checkpoint_path),
            interactive=interactive,
            output_path=str(output_path),
            checkpoint_callback=checkpoint_callback if interactive else None,
        )

        # Save results
        from bmlibrarian.agents.systematic_review.reporter import Reporter
        from bmlibrarian.agents.systematic_review.data_models import SearchCriteria, ScoringWeights

        criteria = result.criteria
        weights = result.weights

        reporter = Reporter(
            documenter=agent.documenter,
            criteria=criteria,
            weights=weights,
        )

        # Save JSON report
        reporter.generate_json_report(result, str(output_path))
        print(f"\nJSON report saved: {output_path}")

        # Save Markdown report
        md_path = output_dir / f"{output_name}.md"
        reporter.generate_markdown_report(result, str(md_path))
        print(f"Markdown report saved: {md_path}")

        # PRISMA flow diagram
        prisma_path = output_dir / f"{output_name}_prisma.json"
        reporter.generate_prisma_flowchart(result.statistics, str(prisma_path))
        print(f"PRISMA flow diagram data saved: {prisma_path}")

        # Print summary
        print()
        print("=" * 50)
        print("REVIEW COMPLETE (RESUMED)")
        print("=" * 50)

        stats = result.statistics.to_dict()
        print(f"  Total papers considered: {stats['total_considered']}")
        print(f"  Passed initial filter: {stats['passed_initial_filter']}")
        print(f"  Passed relevance threshold: {stats['passed_relevance_threshold']}")
        print(f"  Final included: {stats['final_included']}")
        print(f"  Final excluded: {stats['final_excluded']}")
        print(f"  Processing time: {stats['processing_time_seconds']:.2f}s")
        print()

        return 0

    except FileNotFoundError as e:
        print(f"\nCheckpoint not found: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"\nInvalid checkpoint: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n\nResume interrupted by user.")
        return 130
    except Exception as e:
        logging.exception("Unexpected error during resume")
        print(f"\nError: {e}", file=sys.stderr)
        return 1


def find_checkpoint_file(resume_arg: str) -> Optional[Path]:
    """
    Find checkpoint file from resume argument.

    Args:
        resume_arg: Either a path to checkpoint file or a review ID

    Returns:
        Path to checkpoint file, or None if not found
    """
    # First, check if it's a direct path
    direct_path = Path(resume_arg).expanduser()
    if direct_path.exists() and direct_path.is_file():
        return direct_path

    # Otherwise, search for checkpoint files by review ID
    config = get_systematic_review_config()
    output_dir = Path(config.output_dir).expanduser()
    checkpoint_dir = output_dir / "checkpoints"

    if not checkpoint_dir.exists():
        return None

    # Look for files matching the review ID pattern
    pattern = f"{resume_arg}_*.json"
    matches = list(checkpoint_dir.glob(pattern))

    if not matches:
        # Try with review_ prefix
        if not resume_arg.startswith("review_"):
            pattern = f"review_{resume_arg}_*.json"
            matches = list(checkpoint_dir.glob(pattern))

    if not matches:
        return None

    # If multiple matches, prefer the most recent checkpoint type
    # Order: initial_results > search_strategy (resume from later is better)
    checkpoint_priority = {
        "initial_results": 2,
        "scoring_complete": 3,
        "quality_assessment": 4,
        "search_strategy": 1,
    }

    def get_priority(path: Path) -> int:
        for cp_type, priority in checkpoint_priority.items():
            if cp_type in path.name:
                return priority
        return 0

    matches.sort(key=get_priority, reverse=True)
    return matches[0]


def main() -> int:
    """
    Main entry point for CLI.

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    args = parse_args()

    # Setup logging
    setup_logging(args.verbose, args.log_file)

    # Handle status command
    if args.status:
        return show_status()

    # Handle resume from checkpoint
    if args.resume:
        return resume_review(args)

    # Validate we have something to do
    if not args.question and not args.criteria_file:
        print("Error: Either --question or --criteria-file is required.")
        print("Use --help for usage information.")
        return 1

    # Run review
    return run_review(args)


if __name__ == "__main__":
    sys.exit(main())
