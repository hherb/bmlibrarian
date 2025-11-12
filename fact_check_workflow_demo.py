#!/usr/bin/env python3
"""
Demonstration of the complete fact-checking workflow.

This script shows how to:
1. Extract question/answer pairs from a structured JSON file
2. Use FactCheckerAgent to verify statements against literature
3. Compare results with expected answers

Usage:
    # Step 1: Extract questions from the original JSON
    python extract_qa.py ~/Downloads/ori_pqal.json extracted_questions.json

    # Step 2: Run fact-checking on extracted questions
    python fact_check_workflow_demo.py extracted_questions.json results.json

    # Step 3: Analyze results
    python fact_check_workflow_demo.py --analyze results.json
"""

import sys
import json
from pathlib import Path
from typing import Optional


def run_fact_check(input_file: str, output_file: str, max_statements: Optional[int] = None):
    """
    Run fact-checking on statements from an extracted JSON file.

    Args:
        input_file: Path to JSON file with extracted questions (id, question, answer)
        output_file: Path to save fact-check results
        max_statements: Optional limit on number of statements to process
    """
    from bmlibrarian.factchecker.agent import FactCheckerAgent
    from bmlibrarian.config import get_model, get_agent_config

    print(f"Loading statements from {input_file}...")

    # Load statements
    with open(input_file, 'r', encoding='utf-8') as f:
        statements = json.load(f)

    if max_statements:
        statements = statements[:max_statements]
        print(f"Limited to first {max_statements} statements")

    print(f"Found {len(statements)} statements to fact-check")

    # Initialize FactCheckerAgent
    print("\nInitializing FactCheckerAgent...")
    model = get_model("fact_checker_agent", default="gpt-oss:20b")
    config = get_agent_config("fact_checker")

    agent = FactCheckerAgent(
        model=model,
        temperature=config.get("temperature", 0.1),
        top_p=config.get("top_p", 0.9),
        max_tokens=config.get("max_tokens", 2000),
        score_threshold=config.get("score_threshold", 2.5),
        max_search_results=config.get("max_search_results", 50),
        max_citations=config.get("max_citations", 10),
        callback=print_progress
    )

    # Run batch fact-checking
    print(f"\nProcessing {len(statements)} statements...\n")
    results = agent.check_batch_from_file(input_file, output_file)

    # Print summary
    print_summary(results)

    return results


def print_progress(stage: str, message: str):
    """Callback for progress updates."""
    stage_labels = {
        "search": "🔍",
        "scoring": "📊",
        "extraction": "📄",
        "evaluation": "🤔",
        "complete": "✅",
        "warning": "⚠️",
        "batch_start": "🚀",
        "batch_complete": "🎉",
        "batch_progress": "⏳"
    }
    label = stage_labels.get(stage, "ℹ️")
    print(f"{label} {message}")


def print_summary(results):
    """Print summary of fact-check results."""
    total = len(results)
    evaluations = {"yes": 0, "no": 0, "maybe": 0, "error": 0}
    confidences = {"high": 0, "medium": 0, "low": 0}
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

    print("\n" + "=" * 60)
    print("FACT-CHECK SUMMARY")
    print("=" * 60)
    print(f"Total statements: {total}")
    print(f"\nEvaluations:")
    print(f"  ✓ Yes: {evaluations['yes']}")
    print(f"  ✗ No: {evaluations['no']}")
    print(f"  ? Maybe: {evaluations['maybe']}")
    if evaluations['error'] > 0:
        print(f"  ⚠️  Error: {evaluations['error']}")

    print(f"\nConfidence levels:")
    print(f"  High: {confidences['high']}")
    print(f"  Medium: {confidences['medium']}")
    print(f"  Low: {confidences['low']}")

    if matches + mismatches > 0:
        accuracy = matches / (matches + mismatches)
        print(f"\nValidation (vs expected answers):")
        print(f"  Matches: {matches}")
        print(f"  Mismatches: {mismatches}")
        print(f"  Accuracy: {accuracy:.1%}")

    print("=" * 60)


def analyze_results(results_file: str):
    """
    Analyze fact-check results from a saved JSON file.

    Args:
        results_file: Path to JSON file with fact-check results
    """
    print(f"Loading results from {results_file}...")

    with open(results_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    results = data.get("results", [])
    summary = data.get("summary", {})

    print(f"\nLoaded {len(results)} results")

    # Print overall summary
    print("\n" + "=" * 60)
    print("ANALYSIS SUMMARY")
    print("=" * 60)

    if summary:
        print(f"Total statements: {summary.get('total_statements', 0)}")

        evaluations = summary.get('evaluations', {})
        print(f"\nEvaluations:")
        print(f"  ✓ Yes: {evaluations.get('yes', 0)}")
        print(f"  ✗ No: {evaluations.get('no', 0)}")
        print(f"  ? Maybe: {evaluations.get('maybe', 0)}")
        if evaluations.get('error', 0) > 0:
            print(f"  ⚠️  Error: {evaluations['error']}")

        confidences = summary.get('confidences', {})
        print(f"\nConfidence levels:")
        print(f"  High: {confidences.get('high', 0)}")
        print(f"  Medium: {confidences.get('medium', 0)}")
        print(f"  Low: {confidences.get('low', 0)}")

        validation = summary.get('validation')
        if validation:
            print(f"\nValidation (vs expected answers):")
            print(f"  Matches: {validation['matches']}")
            print(f"  Mismatches: {validation['mismatches']}")
            print(f"  Accuracy: {validation['accuracy']:.1%}")

    # Show mismatches in detail
    print("\n" + "=" * 60)
    print("MISMATCHES (Expected vs Actual)")
    print("=" * 60)

    mismatches = [r for r in results if r.get('matches_expected') is False]
    if mismatches:
        for i, result in enumerate(mismatches, 1):
            print(f"\n{i}. Statement: {result['statement'][:80]}...")
            print(f"   Expected: {result['expected_answer']}")
            print(f"   Actual: {result['evaluation']}")
            print(f"   Confidence: {result['confidence']}")
            print(f"   Reason: {result['reason'][:100]}...")
    else:
        print("\nNo mismatches found! 🎉")

    print("=" * 60)


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    if sys.argv[1] == "--analyze":
        if len(sys.argv) != 3:
            print("Usage: python fact_check_workflow_demo.py --analyze <results_json>")
            sys.exit(1)
        analyze_results(sys.argv[2])
    else:
        if len(sys.argv) not in [3, 4]:
            print("Usage: python fact_check_workflow_demo.py <input_json> <output_json> [max_statements]")
            sys.exit(1)

        input_file = sys.argv[1]
        output_file = sys.argv[2]
        max_statements = int(sys.argv[3]) if len(sys.argv) == 4 else None

        run_fact_check(input_file, output_file, max_statements)


if __name__ == "__main__":
    main()
