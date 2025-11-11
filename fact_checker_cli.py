#!/usr/bin/env python3
"""
Fact Checker CLI - Audit biomedical statements in LLM training data

Takes JSON input files with biomedical statements and evaluates their veracity
against the BMLibrarian literature database. Stores results in SQLite database
with optional JSON export.

Input JSON format:
[
    {"statement": "...", "answer": "yes|no|maybe"},
    {"statement": "...", "answer": "yes|no|maybe"},
    ...
]

Output JSON format:
{
    "results": [
        {
            "statement": "...",
            "evaluation": "yes|no|maybe",
            "reason": "...",
            "evidence_list": [
                {
                    "citation": "...",
                    "pmid": "PMID:...",
                    "doi": "DOI:...",
                    "relevance_score": 4.5,
                    "stance": "supports|contradicts"
                }
            ],
            "confidence": "high|medium|low",
            "metadata": {...}
        }
    ],
    "summary": {...}
}
"""

import argparse
import json
import sys
import os
from pathlib import Path
from typing import List, Dict, Any, Optional

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from bmlibrarian.agents import FactCheckerAgent
from bmlibrarian.config import get_model, get_agent_config


def load_input_file(file_path: str) -> List[Dict[str, str]]:
    """
    Load statements from JSON input file.

    Args:
        file_path: Path to JSON input file

    Returns:
        List of statement dictionaries

    Raises:
        ValueError: If file format is invalid
    """
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)

        # Validate format
        if not isinstance(data, list):
            raise ValueError("Input must be a JSON array of statement objects")

        for item in data:
            if not isinstance(item, dict):
                raise ValueError("Each item must be a dictionary")
            if 'statement' not in item:
                raise ValueError("Each item must have a 'statement' field")

        return data

    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON format: {e}")
    except Exception as e:
        raise ValueError(f"Error reading input file: {e}")


def save_output_file(results: List[Any], output_path: str, summary: Dict[str, Any]) -> None:
    """
    Save fact-check results to JSON output file.

    Args:
        results: List of FactCheckResult objects
        output_path: Path to output file
        summary: Summary statistics
    """
    output_data = {
        "results": [r.to_dict() for r in results],
        "summary": summary
    }

    with open(output_path, 'w') as f:
        json.dump(output_data, f, indent=2)

    print(f"\n✓ Results saved to: {output_path}")


def print_result_summary(results: List[Any]) -> None:
    """
    Print a summary of fact-check results to console.

    Args:
        results: List of FactCheckResult objects
    """
    print("\n" + "=" * 80)
    print("FACT-CHECK SUMMARY")
    print("=" * 80)

    total = len(results)
    evaluations = {'yes': 0, 'no': 0, 'maybe': 0, 'error': 0}
    confidences = {'high': 0, 'medium': 0, 'low': 0}
    matches = 0
    mismatches = 0

    for result in results:
        evaluations[result.evaluation] = evaluations.get(result.evaluation, 0) + 1
        if result.confidence:
            confidences[result.confidence] = confidences.get(result.confidence, 0) + 1

        if result.matches_expected is not None:
            if result.matches_expected:
                matches += 1
            else:
                mismatches += 1

    print(f"\nTotal statements: {total}")
    print(f"\nEvaluations:")
    print(f"  ✓ Yes:   {evaluations['yes']:3d} ({evaluations['yes']/total*100:5.1f}%)")
    print(f"  ✗ No:    {evaluations['no']:3d} ({evaluations['no']/total*100:5.1f}%)")
    print(f"  ? Maybe: {evaluations['maybe']:3d} ({evaluations['maybe']/total*100:5.1f}%)")
    if evaluations['error'] > 0:
        print(f"  ⚠ Error: {evaluations['error']:3d} ({evaluations['error']/total*100:5.1f}%)")

    print(f"\nConfidence levels:")
    print(f"  High:   {confidences['high']:3d} ({confidences['high']/total*100:5.1f}%)")
    print(f"  Medium: {confidences['medium']:3d} ({confidences['medium']/total*100:5.1f}%)")
    print(f"  Low:    {confidences['low']:3d} ({confidences['low']/total*100:5.1f}%)")

    if matches + mismatches > 0:
        accuracy = matches / (matches + mismatches) * 100
        print(f"\nValidation (vs expected answers):")
        print(f"  Matches:    {matches:3d}")
        print(f"  Mismatches: {mismatches:3d}")
        print(f"  Accuracy:   {accuracy:5.1f}%")

    print("=" * 80)


def print_detailed_results(results: List[Any], verbose: bool = False) -> None:
    """
    Print detailed results for each statement.

    Args:
        results: List of FactCheckResult objects
        verbose: Whether to include full evidence text
    """
    print("\n" + "=" * 80)
    print("DETAILED RESULTS")
    print("=" * 80)

    for i, result in enumerate(results, 1):
        print(f"\n[{i}] {result.statement}")
        print(f"    Evaluation: {result.evaluation.upper()}")
        print(f"    Confidence: {result.confidence}")
        print(f"    Reason: {result.reason}")

        if result.expected_answer:
            match_symbol = "✓" if result.matches_expected else "✗"
            print(f"    Expected: {result.expected_answer} {match_symbol}")

        print(f"    Evidence: {len(result.evidence_list)} citations")
        print(f"      Supporting: {result.supporting_citations}")
        print(f"      Contradicting: {result.contradicting_citations}")
        print(f"      Neutral: {result.neutral_citations}")

        if verbose and result.evidence_list:
            print(f"    Citations:")
            for j, evidence in enumerate(result.evidence_list[:5], 1):  # Show first 5
                identifiers = []
                if evidence.pmid:
                    identifiers.append(f"PMID:{evidence.pmid}")
                if evidence.doi:
                    identifiers.append(f"DOI:{evidence.doi}")
                id_str = f" ({', '.join(identifiers)})" if identifiers else ""
                stance_str = ""
                if evidence.supports_statement is not None:
                    stance = "supports" if evidence.supports_statement else "contradicts"
                    stance_str = f" [{stance}]"
                print(f"      [{j}]{stance_str} {evidence.citation_text[:100]}...{id_str}")


def create_agent(args: argparse.Namespace) -> FactCheckerAgent:
    """
    Create and configure FactCheckerAgent.

    Args:
        args: Command-line arguments

    Returns:
        Configured FactCheckerAgent
    """
    # Get model and config from centralized configuration
    if args.model:
        model = args.model
    else:
        # Try to get fact_checker_agent model from config, fallback to query_agent
        from bmlibrarian.config import BMLibrarianConfig
        config = BMLibrarianConfig()
        model = config.get_model('fact_checker_agent')
        if not model:
            model = config.get_model('query_agent')

    # Get agent configuration
    agent_config = get_agent_config('fact_checker') or {}

    # Override with command-line arguments
    if args.temperature is not None:
        agent_config['temperature'] = args.temperature
    if args.score_threshold is not None:
        score_threshold = args.score_threshold
    else:
        score_threshold = agent_config.get('score_threshold', 2.5)

    if args.max_search_results is not None:
        max_search_results = args.max_search_results
    else:
        max_search_results = agent_config.get('max_search_results', 50)

    if args.max_citations is not None:
        max_citations = args.max_citations
    else:
        max_citations = agent_config.get('max_citations', 10)

    # Progress callback
    def progress_callback(step: str, message: str):
        if args.verbose:
            print(f"  [{step}] {message}")

    # Determine database mode
    use_database = not args.json_only if hasattr(args, 'json_only') else True
    db_path = getattr(args, 'db_path', None)
    incremental = getattr(args, 'incremental', False)

    # Create agent
    agent = FactCheckerAgent(
        model=model,
        temperature=agent_config.get('temperature', 0.1),
        top_p=agent_config.get('top_p', 0.9),
        max_tokens=agent_config.get('max_tokens', 2000),
        callback=progress_callback if args.verbose else None,
        show_model_info=True,
        score_threshold=score_threshold,
        max_search_results=max_search_results,
        max_citations=max_citations,
        db_path=db_path,
        use_database=use_database,
        incremental=incremental
    )

    return agent


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
