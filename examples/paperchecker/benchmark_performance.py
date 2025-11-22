#!/usr/bin/env python3
"""PaperChecker Performance Benchmark Script.

This script measures processing times for different abstract complexities
to verify the system meets performance targets.

Usage:
    uv run python examples/paperchecker/benchmark_performance.py

Expected performance targets:
    - Short abstract (~100 words): < 90 seconds
    - Medium abstract (~250 words): < 180 seconds
    - Long abstract (~500 words): < 300 seconds
"""

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Add project root to path for imports (calculate relative to this script)
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent.parent
_SRC_DIR = _PROJECT_ROOT / "src"
sys.path.insert(0, str(_SRC_DIR))

# Performance target constants (in seconds)
# Based on PaperChecker Step 16 planning document
PERFORMANCE_TARGET_SHORT_ABSTRACT_SECONDS = 90
PERFORMANCE_TARGET_MEDIUM_ABSTRACT_SECONDS = 180
PERFORMANCE_TARGET_LONG_ABSTRACT_SECONDS = 300

# Test abstracts of varying complexity
SHORT_ABSTRACT = """
Background: This randomized trial evaluated metformin efficacy in type 2 diabetes.
Methods: 200 patients received metformin or placebo for 6 months. Primary outcome was HbA1c change.
Results: Metformin reduced HbA1c by 1.2% compared to 0.3% with placebo (p<0.001).
Conclusions: Metformin effectively improves glycemic control in type 2 diabetes.
"""

MEDIUM_ABSTRACT = """
Background: Cardiovascular disease remains the leading cause of mortality worldwide.
Exercise has been proposed as a protective intervention, but optimal duration and
intensity remain debated. This randomized controlled trial examined the effects of
structured moderate-intensity aerobic exercise on cardiovascular risk factors.
Methods: We enrolled 400 sedentary adults aged 45-65 years and randomized them to
exercise intervention (supervised aerobic training 3x weekly for 12 months) or
standard lifestyle counseling. Primary outcomes included systolic blood pressure,
LDL cholesterol, and VO2max. Secondary outcomes were body mass index and waist
circumference. Analyses used intention-to-treat principles.
Results: The exercise group showed significant reductions in systolic blood pressure
(-7.8 mmHg, p<0.001), LDL cholesterol (-12.5 mg/dL, p<0.01), and improvements in
VO2max (+4.2 mL/kg/min, p<0.001). Benefits persisted at 6-month follow-up.
Conclusions: Structured aerobic exercise significantly improves cardiovascular risk
factors and should be recommended for primary prevention in middle-aged adults.
"""

LONG_ABSTRACT = """
Background and Objectives: Type 2 diabetes mellitus represents a growing global health
burden with significant cardiovascular complications. First-line pharmacological
treatment options include metformin and newer agents such as SGLT2 inhibitors and
GLP-1 receptor agonists. Comparative effectiveness data on long-term cardiovascular
outcomes remain limited, particularly from real-world settings. We aimed to compare
cardiovascular outcomes between metformin monotherapy and sulfonylurea monotherapy
in newly diagnosed type 2 diabetes patients in routine clinical practice.
Methods: We conducted a retrospective cohort study using electronic health records
from a large integrated health system including 85,000 patients newly diagnosed with
type 2 diabetes between 2010 and 2022. Patients initiating metformin or sulfonylurea
as first-line monotherapy were identified and matched using propensity scores adjusting
for age, sex, baseline HbA1c, comorbidities, and concomitant medications. The primary
composite outcome was cardiovascular death, myocardial infarction, and stroke. Secondary
outcomes included heart failure hospitalization, all-cause mortality, and time to
insulin initiation. Cox proportional hazards models estimated hazard ratios with 95%
confidence intervals. Sensitivity analyses examined different propensity score methods,
outcome definitions, and subgroups defined by baseline cardiovascular risk.
Results: After propensity matching, 32,000 patients remained in each group with well-
balanced baseline characteristics. Over median follow-up of 6.2 years, metformin users
demonstrated significantly lower risk of the primary composite outcome (HR 0.76, 95%
CI 0.70-0.83, p<0.001). This benefit was observed consistently across all individual
components and subgroups. Metformin users also had lower all-cause mortality (HR 0.81,
95% CI 0.74-0.88) and reduced heart failure hospitalization (HR 0.72, 95% CI 0.64-0.81).
Time to insulin initiation was similar between groups. Results remained robust across
all sensitivity analyses.
Conclusions: In this large real-world cohort, metformin monotherapy was associated with
superior long-term cardiovascular outcomes compared to sulfonylurea monotherapy in newly
diagnosed type 2 diabetes. These findings reinforce guideline recommendations for
metformin as first-line therapy and suggest cardiovascular benefits extend beyond
glycemic control.
"""

# Abstract metadata
SHORT_METADATA = {
    "title": "Metformin for Type 2 Diabetes: A Randomized Trial",
    "year": 2023,
    "study_type": "RCT"
}

MEDIUM_METADATA = {
    "title": "Exercise and Cardiovascular Risk Factors: A Randomized Controlled Trial",
    "year": 2023,
    "study_type": "RCT"
}

LONG_METADATA = {
    "title": "Cardiovascular Outcomes of Metformin vs Sulfonylurea: A Retrospective Cohort Study",
    "year": 2024,
    "study_type": "Observational cohort"
}


@dataclass
class BenchmarkResult:
    """Result from a single benchmark run."""

    name: str
    word_count: int
    processing_time_seconds: float
    num_statements: int
    total_citations: int
    success: bool
    error_message: Optional[str] = None


def count_words(text: str) -> int:
    """Count words in text."""
    return len(text.split())


def run_benchmark(
    name: str,
    abstract: str,
    metadata: dict,
    agent: "PaperCheckerAgent"  # noqa: F821 - forward reference
) -> BenchmarkResult:
    """Run benchmark for a single abstract.

    Args:
        name: Descriptive name for this benchmark
        abstract: The abstract text to process
        metadata: Abstract metadata
        agent: PaperCheckerAgent instance

    Returns:
        BenchmarkResult with timing and success information
    """
    word_count = count_words(abstract)
    print(f"\n{'='*60}")
    print(f"Running: {name} ({word_count} words)")
    print(f"{'='*60}")

    start_time = time.time()

    try:
        result = agent.check_abstract(abstract, metadata)
        end_time = time.time()
        processing_time = end_time - start_time

        num_statements = len(result.statements)
        total_citations = sum(
            r.num_citations for r in result.counter_reports
        )

        print(f"  Statements extracted: {num_statements}")
        print(f"  Total citations found: {total_citations}")
        print(f"  Processing time: {processing_time:.1f}s")

        return BenchmarkResult(
            name=name,
            word_count=word_count,
            processing_time_seconds=processing_time,
            num_statements=num_statements,
            total_citations=total_citations,
            success=True
        )

    except Exception as e:
        end_time = time.time()
        processing_time = end_time - start_time
        print(f"  ERROR: {e}")

        return BenchmarkResult(
            name=name,
            word_count=word_count,
            processing_time_seconds=processing_time,
            num_statements=0,
            total_citations=0,
            success=False,
            error_message=str(e)
        )


def print_summary(results: list[BenchmarkResult]) -> None:
    """Print benchmark summary table.

    Args:
        results: List of benchmark results
    """
    # Performance targets in seconds (using named constants)
    targets = {
        "Short": PERFORMANCE_TARGET_SHORT_ABSTRACT_SECONDS,
        "Medium": PERFORMANCE_TARGET_MEDIUM_ABSTRACT_SECONDS,
        "Long": PERFORMANCE_TARGET_LONG_ABSTRACT_SECONDS,
    }

    print("\n" + "="*70)
    print("BENCHMARK SUMMARY")
    print("="*70)
    print(f"{'Name':<20} {'Words':>6} {'Time':>8} {'Target':>8} {'Status':>10}")
    print("-"*70)

    all_passed = True
    for r in results:
        if not r.success:
            status = "FAILED"
            all_passed = False
        else:
            # Determine target based on name prefix
            target = None
            for prefix, target_time in targets.items():
                if r.name.startswith(prefix):
                    target = target_time
                    break

            if target and r.processing_time_seconds <= target:
                status = "PASS"
            elif target:
                status = "SLOW"
                all_passed = False
            else:
                status = "N/A"

        target_str = f"<{target}s" if target else "N/A"
        print(
            f"{r.name:<20} {r.word_count:>6} "
            f"{r.processing_time_seconds:>7.1f}s {target_str:>8} {status:>10}"
        )

    print("-"*70)

    # Summary statistics
    successful = [r for r in results if r.success]
    if successful:
        avg_time = sum(r.processing_time_seconds for r in successful) / len(successful)
        total_statements = sum(r.num_statements for r in successful)
        total_citations = sum(r.total_citations for r in successful)

        print(f"\nTotal abstracts processed: {len(successful)}/{len(results)}")
        print(f"Average processing time: {avg_time:.1f}s")
        print(f"Total statements extracted: {total_statements}")
        print(f"Total citations found: {total_citations}")

    if all_passed:
        print("\nAll benchmarks PASSED")
    else:
        print("\nSome benchmarks FAILED or exceeded targets")


def main() -> int:
    """Run the performance benchmark suite.

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    print("PaperChecker Performance Benchmark")
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

    # Run benchmarks
    test_cases = [
        ("Short abstract", SHORT_ABSTRACT, SHORT_METADATA),
        ("Medium abstract", MEDIUM_ABSTRACT, MEDIUM_METADATA),
        ("Long abstract", LONG_ABSTRACT, LONG_METADATA),
    ]

    results: list[BenchmarkResult] = []
    for name, abstract, metadata in test_cases:
        result = run_benchmark(name, abstract, metadata, agent)
        results.append(result)

    # Print summary
    print_summary(results)

    # Return exit code based on success
    all_success = all(r.success for r in results)
    return 0 if all_success else 1


if __name__ == "__main__":
    sys.exit(main())
