"""
Output formatters for fact checker CLI.

Provides console output formatting for fact-check results and summaries.
"""

from typing import List, Any


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
