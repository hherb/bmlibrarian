"""
Main CLI application for fact checker.

Provides command-line interface for batch fact-checking of biomedical statements.
"""

import sys
import argparse
from pathlib import Path

from .commands import create_agent, load_input_file, save_output_file
from .formatters import print_result_summary, print_detailed_results


def main():
    """Main entry point for fact checker CLI."""
    parser = argparse.ArgumentParser(
        description="BMLibrarian Fact Checker - Audit biomedical statements against literature",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Check statements in input file (creates input.db)
  python fact_checker_cli.py input.json

  # Incremental mode: only process new/unevaluated statements
  python fact_checker_cli.py input.json --incremental

  # Use custom thresholds
  python fact_checker_cli.py input.json --score-threshold 3.0 --max-search-results 100

  # Verbose mode with detailed output
  python fact_checker_cli.py input.json -v --detailed

  # Quick test mode (fewer documents)
  python fact_checker_cli.py input.json --quick

  # Export database to JSON
  python fact_checker_cli.py input.json --export-json -o results.json

  # Legacy JSON-only mode (no database)
  python fact_checker_cli.py input.json -o results.json --json-only

Input file format:
  [
    {"statement": "All cases of childhood ulcerative colitis need colectomy", "answer": "no"},
    {"statement": "Vitamin D deficiency is common in IBD patients", "answer": "yes"}
  ]
        """
    )

    parser.add_argument(
        'input_file',
        type=str,
        help='JSON file with statements to fact-check'
    )

    parser.add_argument(
        '-o', '--output',
        type=str,
        help='Output file (optional JSON export from database)'
    )

    parser.add_argument(
        '--db-path',
        type=str,
        help='SQLite database path (default: auto-generated from input filename)'
    )

    parser.add_argument(
        '--json-only',
        action='store_true',
        help='Use legacy JSON-only mode (no database)'
    )

    parser.add_argument(
        '--incremental',
        action='store_true',
        help='Incremental mode: skip statements that already have AI evaluations'
    )

    parser.add_argument(
        '--export-json',
        action='store_true',
        help='Export database to JSON after processing'
    )

    # Agent configuration
    parser.add_argument(
        '--model',
        type=str,
        help='Ollama model to use (default: from config)'
    )

    parser.add_argument(
        '--temperature',
        type=float,
        help='Model temperature (default: 0.1)'
    )

    # Search configuration
    parser.add_argument(
        '--score-threshold',
        type=float,
        help='Minimum relevance score threshold (default: 2.5)'
    )

    parser.add_argument(
        '--max-search-results',
        type=int,
        help='Maximum number of documents to search (default: 50)'
    )

    parser.add_argument(
        '--max-citations',
        type=int,
        help='Maximum number of citations to extract (default: 10)'
    )

    # Quick mode
    parser.add_argument(
        '--quick',
        action='store_true',
        help='Quick mode: fewer documents for faster testing'
    )

    # Display options
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Verbose output with progress messages'
    )

    parser.add_argument(
        '--detailed',
        action='store_true',
        help='Show detailed results for each statement'
    )

    args = parser.parse_args()

    # Apply quick mode settings
    if args.quick:
        if args.max_search_results is None:
            args.max_search_results = 20
        if args.max_citations is None:
            args.max_citations = 5
        if args.score_threshold is None:
            args.score_threshold = 2.0

    try:
        # Validate input file
        if not Path(args.input_file).exists():
            print(f"\n✗ Error: Input file not found: {args.input_file}")
            return 1

        # Create agent
        print(f"\nInitializing Fact Checker Agent...")
        agent = create_agent(args)

        # Test connection
        if not agent.test_connection():
            print("\n✗ Error: Cannot connect to Ollama server")
            print("  Please ensure Ollama is running on http://localhost:11434")
            return 1

        # Process statements using batch mode
        print(f"\nProcessing statements from: {args.input_file}")
        print("=" * 80)

        results = agent.check_batch_from_file(
            input_file=args.input_file,
            output_file=args.output if args.json_only else None
        )

        # Print results information
        print("=" * 80)
        if agent.use_database and agent.db_path:
            print(f"\n✓ Results stored in database: {agent.db_path}")
            print(f"  Total statements processed: {len(results)}")

            # Export to JSON if requested
            if args.export_json or args.output:
                output_file = args.output or str(Path(args.input_file).parent / f"{Path(args.input_file).stem}_results.json")
                print(f"\nExporting results to JSON...")
                export_path = agent.export_database_to_json(output_file, export_type="full")
                if export_path:
                    print(f"✓ JSON export saved to: {export_path}")
        else:
            print(f"\n✓ Results saved to: {args.output}")

        # Print summary
        print_result_summary(results)

        # Print detailed results if requested
        if args.detailed:
            print_detailed_results(results, verbose=args.verbose)

        return 0

    except KeyboardInterrupt:
        print("\n\n⚠ Interrupted by user")
        return 130
    except Exception as e:
        print(f"\n✗ Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
