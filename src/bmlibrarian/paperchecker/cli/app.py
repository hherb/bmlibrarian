"""
Main CLI application for PaperChecker.

Provides command-line interface for batch fact-checking of medical abstracts.
Supports JSON input files, PMID-based loading, progress tracking,
error recovery, and multiple output formats.

Usage:
    uv run python paper_checker_cli.py input.json
    uv run python paper_checker_cli.py input.json -o results.json
    uv run python paper_checker_cli.py input.json --export-markdown reports/
    uv run python paper_checker_cli.py --pmid 12345678 23456789
"""

import sys
import logging
import argparse
from pathlib import Path
from typing import Optional

from .commands import (
    load_abstracts_from_json,
    load_abstracts_from_pmids,
    check_abstracts,
    export_results_json,
    export_markdown_reports,
)
from .formatters import (
    print_statistics,
    print_abstract_summary,
    print_error_summary,
    print_completion_banner,
)

# Logging configuration
LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"

# Default values for configuration
DEFAULT_OLLAMA_HOST: str = "http://localhost:11434"
QUICK_MODE_MAX_ABSTRACTS: int = 5
MAX_FAILED_EXPORTS_DISPLAYED: int = 5

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """
    Parse command line arguments.

    Returns:
        Namespace object with parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="PaperChecker - Medical abstract fact-checking against literature",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Check abstracts from JSON file
  uv run python paper_checker_cli.py abstracts.json

  # Check and export results to JSON
  uv run python paper_checker_cli.py abstracts.json -o results.json

  # Export markdown reports
  uv run python paper_checker_cli.py abstracts.json --export-markdown reports/

  # Check specific PMIDs from database
  uv run python paper_checker_cli.py --pmid 12345678 23456789

  # Limit number of abstracts
  uv run python paper_checker_cli.py abstracts.json --max-abstracts 10

  # Continue processing on errors
  uv run python paper_checker_cli.py abstracts.json --continue-on-error

  # Quick test mode
  uv run python paper_checker_cli.py abstracts.json --quick

  # Verbose output with individual results
  uv run python paper_checker_cli.py abstracts.json -v --detailed

Input JSON format:
  [
    {
      "abstract": "Full abstract text...",
      "metadata": {"pmid": 12345678, "title": "...", "authors": [...]}
    },
    ...
  ]
        """
    )

    # Input sources (mutually exclusive group)
    input_group = parser.add_mutually_exclusive_group()

    input_group.add_argument(
        "input_file",
        nargs="?",
        help="JSON file with abstracts to check"
    )

    input_group.add_argument(
        "--pmid",
        nargs="+",
        type=int,
        metavar="PMID",
        help="Check abstracts by PMID (fetch from database)"
    )

    # Output options
    parser.add_argument(
        "-o", "--output",
        metavar="FILE",
        help="Output JSON file for results"
    )

    parser.add_argument(
        "--export-markdown",
        metavar="DIR",
        help="Export markdown reports to directory"
    )

    # Configuration
    parser.add_argument(
        "--config",
        metavar="FILE",
        help="Config file path (default: ~/.bmlibrarian/config.json)"
    )

    # Processing options
    parser.add_argument(
        "--max-abstracts",
        type=int,
        metavar="N",
        help="Limit number of abstracts to check"
    )

    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue processing if an abstract fails"
    )

    # Quick mode
    parser.add_argument(
        "--quick",
        action="store_true",
        help=f"Quick test mode: process max {QUICK_MODE_MAX_ABSTRACTS} abstracts"
    )

    # Display options
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output with debug messages"
    )

    parser.add_argument(
        "--detailed",
        action="store_true",
        help="Show detailed results for each abstract"
    )

    parser.add_argument(
        "--no-stats",
        action="store_true",
        help="Skip printing statistics summary"
    )

    return parser.parse_args()


def setup_logging(verbose: bool = False) -> None:
    """
    Configure logging based on verbosity level.

    Args:
        verbose: If True, set DEBUG level; otherwise INFO level
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format=LOG_FORMAT,
        datefmt=LOG_DATE_FORMAT
    )


def create_agent(config_path: Optional[str] = None):
    """
    Create and initialize PaperCheckerAgent.

    Args:
        config_path: Optional path to configuration file

    Returns:
        Initialized PaperCheckerAgent instance

    Raises:
        FileNotFoundError: If specified config file does not exist
        ImportError: If paperchecker module cannot be imported
        RuntimeError: If agent initialization fails
    """
    try:
        from bmlibrarian.paperchecker import PaperCheckerAgent

        # Validate config file exists before attempting to load
        config = None
        if config_path:
            config_file = Path(config_path)
            if not config_file.exists():
                raise FileNotFoundError(f"Config file not found: {config_path}")
            if not config_file.is_file():
                raise ValueError(f"Config path is not a file: {config_path}")
            from bmlibrarian.config import Config
            config = Config(config_path=config_path)._config

        agent = PaperCheckerAgent(config=config)
        return agent

    except FileNotFoundError:
        raise
    except ImportError as e:
        logger.error(f"Failed to import PaperCheckerAgent: {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to initialize PaperCheckerAgent: {e}")
        raise RuntimeError(f"Agent initialization failed: {e}") from e


def main() -> int:
    """
    Main entry point for PaperChecker CLI.

    Returns:
        Exit code (0 for success, non-zero for errors)
    """
    args = parse_args()

    # Setup logging
    setup_logging(args.verbose)

    # Validate input source
    if not args.input_file and not args.pmid:
        print("\nError: Must provide either input_file or --pmid")
        print("Use --help for usage information")
        return 1

    try:
        # Load abstracts
        print("\nLoading abstracts...")

        if args.input_file:
            if not Path(args.input_file).exists():
                print(f"\nX Error: Input file not found: {args.input_file}")
                return 1
            abstracts = load_abstracts_from_json(args.input_file)
        else:
            abstracts = load_abstracts_from_pmids(args.pmid)

        if not abstracts:
            print("\nX Error: No abstracts to process")
            return 1

        print(f"+ Loaded {len(abstracts)} abstracts")

        # Apply limits
        if args.quick and args.max_abstracts is None:
            args.max_abstracts = QUICK_MODE_MAX_ABSTRACTS
            print(f"  (Quick mode: limiting to {QUICK_MODE_MAX_ABSTRACTS} abstracts)")

        if args.max_abstracts and len(abstracts) > args.max_abstracts:
            logger.info(f"Limiting to {args.max_abstracts} abstracts")
            abstracts = abstracts[:args.max_abstracts]
            print(f"  (Limited to {args.max_abstracts} abstracts)")

        # Initialize agent
        print("\nInitializing PaperCheckerAgent...")
        agent = create_agent(args.config)

        # Test connection
        print("Testing connections...")
        if not agent.test_connection():
            print("\nX Error: Connection test failed")
            print("  Please ensure:")
            print(f"  - Ollama is running at {DEFAULT_OLLAMA_HOST}")
            print("  - PostgreSQL is running and accessible")
            print("  - Required models are available")
            return 1
        print("+ All connections successful")

        # Process abstracts
        print(f"\nProcessing {len(abstracts)} abstracts...")
        print("=" * 60)

        results, errors = check_abstracts(
            abstracts=abstracts,
            agent=agent,
            continue_on_error=args.continue_on_error
        )

        print("=" * 60)

        # Show detailed results if requested
        if args.detailed and results:
            print("\nDetailed Results:")
            for i, result in enumerate(results, 1):
                print_abstract_summary(result, i, verbose=args.verbose)

        # Export results
        if args.output and results:
            try:
                export_results_json(results, args.output)
                print(f"+ JSON results exported to: {args.output}")
            except Exception as e:
                logger.error(f"Failed to export JSON: {e}")
                print(f"X Error exporting JSON: {e}")

        if args.export_markdown and results:
            try:
                created_files, failed_exports = export_markdown_reports(results, args.export_markdown)
                print(f"+ {len(created_files)} markdown reports exported to: {args.export_markdown}")
                if failed_exports:
                    print(f"  ! {len(failed_exports)} exports failed:")
                    for failed in failed_exports[:MAX_FAILED_EXPORTS_DISPLAYED]:
                        pmid_info = f" (PMID: {failed['pmid']})" if failed.get('pmid') else ""
                        print(f"    - {failed['filename']}{pmid_info}: {failed['error']}")
                    if len(failed_exports) > MAX_FAILED_EXPORTS_DISPLAYED:
                        remaining = len(failed_exports) - MAX_FAILED_EXPORTS_DISPLAYED
                        print(f"    ... and {remaining} more failures")
            except Exception as e:
                logger.error(f"Failed to export markdown: {e}")
                print(f"X Error exporting markdown: {e}")

        # Print statistics
        if not args.no_stats and results:
            print_statistics(results)

        # Print error summary
        if errors:
            print_error_summary(errors)

        # Print completion banner
        print_completion_banner(
            total=len(abstracts),
            successful=len(results),
            errors=len(errors),
            output_file=args.output,
            markdown_dir=args.export_markdown
        )

        # Return success only if all abstracts processed successfully
        return 0 if len(errors) == 0 else 1

    except KeyboardInterrupt:
        print("\n\n! Interrupted by user")
        return 130
    except ValueError as e:
        print(f"\nX Validation error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1
    except RuntimeError as e:
        print(f"\nX Runtime error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1
    except Exception as e:
        print(f"\nX Unexpected error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
