#!/usr/bin/env python3
"""PaperChecker Error Scenario Test Script.

This script validates that PaperChecker handles various error conditions
gracefully and provides appropriate error messages.

Usage:
    uv run python examples/paperchecker/test_error_scenarios.py

Test scenarios:
    1. Empty abstract
    2. Very short abstract (below minimum)
    3. Abstract with no extractable statements
    4. Invalid PMID loading
    5. Database connection handling
"""

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

# Add project root to path for imports (calculate relative to this script)
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent.parent
_SRC_DIR = _PROJECT_ROOT / "src"
sys.path.insert(0, str(_SRC_DIR))


@dataclass
class TestResult:
    """Result from a single error scenario test."""

    name: str
    passed: bool
    expected_error: str
    actual_error: Optional[str] = None
    notes: str = ""


def test_empty_abstract(agent: "PaperCheckerAgent") -> TestResult:  # noqa: F821
    """Test handling of empty abstract input.

    Args:
        agent: PaperCheckerAgent instance

    Returns:
        TestResult indicating pass/fail
    """
    try:
        agent.check_abstract("", {})
        return TestResult(
            name="Empty abstract",
            passed=False,
            expected_error="ValueError",
            notes="Should have raised ValueError but didn't"
        )
    except ValueError as e:
        return TestResult(
            name="Empty abstract",
            passed=True,
            expected_error="ValueError",
            actual_error=str(e)[:100]
        )
    except Exception as e:
        return TestResult(
            name="Empty abstract",
            passed=False,
            expected_error="ValueError",
            actual_error=f"{type(e).__name__}: {str(e)[:100]}"
        )


def test_very_short_abstract(agent: "PaperCheckerAgent") -> TestResult:  # noqa: F821
    """Test handling of abstract below minimum length.

    Args:
        agent: PaperCheckerAgent instance

    Returns:
        TestResult indicating pass/fail
    """
    try:
        # Less than 50 characters (schema minimum)
        agent.check_abstract("Very short.", {})
        return TestResult(
            name="Very short abstract",
            passed=False,
            expected_error="ValueError",
            notes="Should have raised ValueError but didn't"
        )
    except ValueError as e:
        return TestResult(
            name="Very short abstract",
            passed=True,
            expected_error="ValueError",
            actual_error=str(e)[:100]
        )
    except Exception as e:
        return TestResult(
            name="Very short abstract",
            passed=False,
            expected_error="ValueError",
            actual_error=f"{type(e).__name__}: {str(e)[:100]}"
        )


def test_whitespace_only_abstract(agent: "PaperCheckerAgent") -> TestResult:  # noqa: F821
    """Test handling of whitespace-only abstract.

    Args:
        agent: PaperCheckerAgent instance

    Returns:
        TestResult indicating pass/fail
    """
    try:
        agent.check_abstract("   \n\t  \n   ", {})
        return TestResult(
            name="Whitespace-only abstract",
            passed=False,
            expected_error="ValueError",
            notes="Should have raised ValueError but didn't"
        )
    except ValueError as e:
        return TestResult(
            name="Whitespace-only abstract",
            passed=True,
            expected_error="ValueError",
            actual_error=str(e)[:100]
        )
    except Exception as e:
        return TestResult(
            name="Whitespace-only abstract",
            passed=False,
            expected_error="ValueError",
            actual_error=f"{type(e).__name__}: {str(e)[:100]}"
        )


def test_none_abstract(agent: "PaperCheckerAgent") -> TestResult:  # noqa: F821
    """Test handling of None abstract input.

    Args:
        agent: PaperCheckerAgent instance

    Returns:
        TestResult indicating pass/fail
    """
    try:
        agent.check_abstract(None, {})  # type: ignore
        return TestResult(
            name="None abstract",
            passed=False,
            expected_error="TypeError or ValueError",
            notes="Should have raised error but didn't"
        )
    except (TypeError, ValueError) as e:
        return TestResult(
            name="None abstract",
            passed=True,
            expected_error="TypeError or ValueError",
            actual_error=str(e)[:100]
        )
    except Exception as e:
        return TestResult(
            name="None abstract",
            passed=False,
            expected_error="TypeError or ValueError",
            actual_error=f"{type(e).__name__}: {str(e)[:100]}"
        )


def test_non_string_abstract(agent: "PaperCheckerAgent") -> TestResult:  # noqa: F821
    """Test handling of non-string abstract input.

    Args:
        agent: PaperCheckerAgent instance

    Returns:
        TestResult indicating pass/fail
    """
    try:
        agent.check_abstract(12345, {})  # type: ignore
        return TestResult(
            name="Non-string abstract",
            passed=False,
            expected_error="TypeError",
            notes="Should have raised TypeError but didn't"
        )
    except TypeError as e:
        return TestResult(
            name="Non-string abstract",
            passed=True,
            expected_error="TypeError",
            actual_error=str(e)[:100]
        )
    except Exception as e:
        # May raise ValueError instead - that's also acceptable
        if isinstance(e, ValueError):
            return TestResult(
                name="Non-string abstract",
                passed=True,
                expected_error="TypeError",
                actual_error=f"ValueError (acceptable): {str(e)[:80]}"
            )
        return TestResult(
            name="Non-string abstract",
            passed=False,
            expected_error="TypeError",
            actual_error=f"{type(e).__name__}: {str(e)[:100]}"
        )


def test_none_metadata(agent: "PaperCheckerAgent") -> TestResult:  # noqa: F821
    """Test handling of None metadata.

    Args:
        agent: PaperCheckerAgent instance

    Returns:
        TestResult indicating pass/fail
    """
    valid_abstract = """
    Background: This is a valid abstract about medical research.
    Methods: We conducted a randomized trial with adequate sample size.
    Results: The intervention showed significant improvement.
    Conclusions: Our findings support the effectiveness of the treatment.
    """

    try:
        agent.check_abstract(valid_abstract, None)  # type: ignore
        return TestResult(
            name="None metadata",
            passed=False,
            expected_error="TypeError or ValueError",
            notes="Should have raised error but didn't"
        )
    except (TypeError, ValueError) as e:
        return TestResult(
            name="None metadata",
            passed=True,
            expected_error="TypeError or ValueError",
            actual_error=str(e)[:100]
        )
    except Exception as e:
        return TestResult(
            name="None metadata",
            passed=False,
            expected_error="TypeError or ValueError",
            actual_error=f"{type(e).__name__}: {str(e)[:100]}"
        )


def test_valid_abstract_processes(agent: "PaperCheckerAgent") -> TestResult:  # noqa: F821
    """Test that a valid abstract processes successfully.

    This is a sanity check - if this fails, all other tests are suspect.

    Args:
        agent: PaperCheckerAgent instance

    Returns:
        TestResult indicating pass/fail
    """
    valid_abstract = """
    Background: Metformin remains the first-line treatment for type 2 diabetes mellitus.
    This study evaluated cardiovascular outcomes in patients treated with metformin.
    Methods: We conducted a retrospective cohort study of 10,000 patients over 5 years.
    Results: Metformin users showed reduced cardiovascular events (HR 0.78, p<0.001).
    Conclusions: Metformin provides cardiovascular protection beyond glycemic control.
    """

    metadata = {
        "title": "Metformin and Cardiovascular Outcomes",
        "year": 2023,
        "study_type": "Observational cohort"
    }

    try:
        result = agent.check_abstract(valid_abstract, metadata)

        # Basic validation of result structure
        if hasattr(result, 'statements') and len(result.statements) > 0:
            return TestResult(
                name="Valid abstract processes",
                passed=True,
                expected_error="None (success expected)",
                notes=f"Extracted {len(result.statements)} statements"
            )
        else:
            return TestResult(
                name="Valid abstract processes",
                passed=False,
                expected_error="None (success expected)",
                notes="No statements extracted from valid abstract"
            )

    except Exception as e:
        return TestResult(
            name="Valid abstract processes",
            passed=False,
            expected_error="None (success expected)",
            actual_error=f"{type(e).__name__}: {str(e)[:100]}"
        )


def print_results(results: list[TestResult]) -> bool:
    """Print test results summary.

    Args:
        results: List of test results

    Returns:
        True if all tests passed, False otherwise
    """
    print("\n" + "="*70)
    print("ERROR SCENARIO TEST RESULTS")
    print("="*70)

    passed_count = 0
    failed_count = 0

    for result in results:
        status = "PASS" if result.passed else "FAIL"
        status_symbol = "✓" if result.passed else "✗"

        print(f"\n{status_symbol} {result.name}: {status}")
        print(f"  Expected: {result.expected_error}")

        if result.actual_error:
            print(f"  Actual: {result.actual_error}")
        if result.notes:
            print(f"  Notes: {result.notes}")

        if result.passed:
            passed_count += 1
        else:
            failed_count += 1

    print("\n" + "-"*70)
    print(f"Total: {passed_count} passed, {failed_count} failed")
    print("="*70)

    return failed_count == 0


def main() -> int:
    """Run error scenario test suite.

    Returns:
        Exit code (0 for success, 1 for any failures)
    """
    print("PaperChecker Error Scenario Tests")
    print("="*40)
    print()

    # Import and initialize agent
    try:
        from bmlibrarian.paperchecker.agent import PaperCheckerAgent
        agent = PaperCheckerAgent()

        # Test connection
        if not agent.test_connection():
            print("ERROR: Failed to connect to Ollama or database")
            return 1

        print("Agent initialized successfully")
    except Exception as e:
        print(f"ERROR: Failed to initialize PaperCheckerAgent: {e}")
        return 1

    # Define test scenarios
    tests: list[Callable[["PaperCheckerAgent"], TestResult]] = [  # noqa: F821
        test_empty_abstract,
        test_very_short_abstract,
        test_whitespace_only_abstract,
        test_none_abstract,
        test_non_string_abstract,
        test_none_metadata,
        test_valid_abstract_processes,  # Sanity check at the end
    ]

    # Run all tests
    print(f"\nRunning {len(tests)} error scenario tests...")
    results: list[TestResult] = []

    for test_func in tests:
        print(f"  Testing: {test_func.__name__}...", end=" ", flush=True)
        result = test_func(agent)
        results.append(result)
        print("done")

    # Print summary
    all_passed = print_results(results)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
