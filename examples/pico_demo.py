#!/usr/bin/env python3
"""
PICO Agent Demonstration

This script demonstrates the capabilities of the PICOAgent for extracting
Population, Intervention, Comparison, and Outcome components from biomedical
research papers.

Usage:
    uv run python examples/pico_demo.py
"""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from bmlibrarian.agents import PICOAgent


# Sample research papers for demonstration
SAMPLE_PAPERS = [
    {
        'id': '12345678',
        'title': 'Effect of Metformin on Glycemic Control in Type 2 Diabetes: A Randomized Controlled Trial',
        'abstract': """
        Background: Type 2 diabetes mellitus is a major public health concern. Metformin is widely used as first-line therapy.

        Methods: We conducted a randomized, double-blind, placebo-controlled trial involving 150 adults aged 40-65 years
        with type 2 diabetes and HbA1c levels >7.0%. Participants were recruited from 5 primary care clinics in Boston, MA.
        Patients were randomly assigned to receive either metformin 1000mg twice daily (n=75) or matching placebo tablets
        twice daily (n=75) for 12 weeks. The primary outcome was change in HbA1c from baseline to week 12. Secondary outcomes
        included fasting plasma glucose, body weight, and adverse events.

        Results: At 12 weeks, the metformin group showed a mean reduction in HbA1c of -1.2% (95% CI: -1.5 to -0.9) compared
        to -0.3% (95% CI: -0.5 to -0.1) in the placebo group (p<0.001). Fasting glucose decreased by 28 mg/dL in the metformin
        group vs 8 mg/dL in placebo (p<0.01). Body weight decreased by 2.1 kg in metformin vs 0.4 kg in placebo (p<0.05).
        Gastrointestinal side effects were more common in the metformin group (23% vs 8%, p<0.05).

        Conclusions: Metformin 1000mg twice daily for 12 weeks significantly reduced HbA1c and fasting glucose in adults
        with type 2 diabetes compared to placebo, with acceptable tolerability.
        """,
        'pmid': '12345678',
        'doi': '10.1000/example.12345',
        'publication_date': '2023-06-15'
    },
    {
        'id': '23456789',
        'title': 'Low-Dose Aspirin for Prevention of Cardiovascular Events in Elderly Patients: A Cohort Study',
        'abstract': """
        Objective: To assess the effectiveness of low-dose aspirin in preventing cardiovascular events in elderly patients.

        Design: Prospective cohort study with 5-year follow-up.

        Setting: 12 community hospitals in the United Kingdom.

        Participants: 2,450 adults aged 70 years and older without prior cardiovascular disease. Participants were
        categorized as aspirin users (taking 75-100mg daily, n=1,225) or non-users (n=1,225) based on baseline medication review.

        Main outcome measures: Composite endpoint of myocardial infarction, stroke, or cardiovascular death. Secondary
        outcomes included all-cause mortality and major bleeding events.

        Results: Over 5 years, the aspirin group had 112 cardiovascular events (9.1%) compared to 156 events (12.7%) in
        the non-aspirin group (adjusted HR 0.68, 95% CI 0.53-0.87, p=0.002). All-cause mortality was similar between groups
        (HR 0.95, 95% CI 0.78-1.15). Major bleeding occurred in 45 aspirin users (3.7%) vs 28 non-users (2.3%) (HR 1.61,
        95% CI 1.01-2.57, p=0.046).

        Conclusions: Low-dose aspirin was associated with reduced cardiovascular events in elderly patients but increased
        risk of major bleeding. Individual risk-benefit assessment is warranted.
        """,
        'pmid': '23456789',
        'doi': '10.1000/example.23456',
        'publication_date': '2022-11-20'
    },
    {
        'id': '34567890',
        'title': 'Mediterranean Diet vs Low-Fat Diet for Weight Loss in Obese Adults: Meta-Analysis of Randomized Trials',
        'abstract': """
        Purpose: To compare the effectiveness of Mediterranean diet versus low-fat diet for weight loss in obese adults.

        Data sources: PubMed, Embase, and Cochrane Central Register of Controlled Trials from inception to December 2023.

        Study selection: Randomized controlled trials comparing Mediterranean diet with low-fat diet in obese adults
        (BMI ≥30 kg/m²) with at least 12 weeks of follow-up.

        Data extraction: Two reviewers independently extracted data on weight change, BMI change, and adherence rates.

        Data synthesis: Meta-analysis of 15 randomized trials involving 2,832 participants (mean age 48 years, 62% female).
        Mediterranean diet groups consumed 35-40% calories from fat (primarily olive oil and nuts) with emphasis on fruits,
        vegetables, whole grains, and fish. Low-fat diet groups consumed <30% calories from fat with reduced intake of
        all fats. Primary outcome was weight change at 12 months.

        Results: At 12 months, Mediterranean diet resulted in greater weight loss compared to low-fat diet (mean difference
        -1.8 kg, 95% CI -2.9 to -0.7 kg, p=0.001, I²=45%). BMI reduction was also greater with Mediterranean diet (mean
        difference -0.6 kg/m², 95% CI -1.0 to -0.3, p<0.001). Adherence rates were higher in Mediterranean diet groups
        (72% vs 58%, p=0.03).

        Conclusions: Mediterranean diet appears more effective than low-fat diet for weight loss in obese adults, with
        better long-term adherence.
        """,
        'pmid': '34567890',
        'doi': '10.1000/example.34567',
        'publication_date': '2024-03-10'
    }
]


def print_section(title: str) -> None:
    """Print a formatted section header."""
    print(f"\n{'='*80}")
    print(f"{title}")
    print(f"{'='*80}\n")


def demo_single_extraction():
    """Demonstrate single document PICO extraction."""
    print_section("DEMO 1: Single Document PICO Extraction")

    # Initialize agent
    print("Initializing PICOAgent with gpt-oss:20b...")
    agent = PICOAgent(model="gpt-oss:20b")

    # Extract PICO from first paper
    paper = SAMPLE_PAPERS[0]
    print(f"\nExtracting PICO from: {paper['title'][:60]}...")
    print(f"PMID: {paper['pmid']}")

    extraction = agent.extract_pico_from_document(
        document=paper,
        min_confidence=0.5
    )

    if extraction:
        print(agent.format_pico_summary(extraction))
    else:
        print("❌ Extraction failed or confidence too low")


def demo_batch_extraction():
    """Demonstrate batch PICO extraction with progress tracking."""
    print_section("DEMO 2: Batch PICO Extraction")

    agent = PICOAgent(model="gpt-oss:20b")

    print(f"Processing {len(SAMPLE_PAPERS)} research papers...\n")

    def progress_callback(current, total, doc_title):
        print(f"  [{current}/{total}] {doc_title[:60]}...")

    extractions = agent.extract_pico_batch(
        documents=SAMPLE_PAPERS,
        min_confidence=0.5,
        progress_callback=progress_callback
    )

    print(f"\n✓ Successfully extracted PICO from {len(extractions)}/{len(SAMPLE_PAPERS)} papers\n")

    # Display results
    for i, extraction in enumerate(extractions, 1):
        print(f"\n--- Paper {i}: {extraction.document_title[:60]}... ---")
        print(f"Study Type: {extraction.study_type or 'Not identified'}")
        print(f"Sample Size: {extraction.sample_size or 'Not reported'}")
        print(f"Confidence: {extraction.extraction_confidence:.1%}")
        print(f"\nPopulation: {extraction.population[:150]}...")
        print(f"Intervention: {extraction.intervention[:150]}...")
        print(f"Comparison: {extraction.comparison[:150]}...")
        print(f"Outcome: {extraction.outcome[:150]}...")


def demo_filtering_and_analysis():
    """Demonstrate filtering and analysis of PICO extractions."""
    print_section("DEMO 3: Filtering and Analysis")

    agent = PICOAgent(model="gpt-oss:20b")

    # Extract from all papers
    print("Extracting PICO components from all papers...")
    extractions = agent.extract_pico_batch(
        documents=SAMPLE_PAPERS,
        min_confidence=0.4  # Lower threshold for demo
    )

    # Filter by study type
    print("\n--- Filtering by Study Type ---")
    rcts = [e for e in extractions if e.study_type and 'RCT' in e.study_type.upper()]
    cohort = [e for e in extractions if e.study_type and 'cohort' in e.study_type.lower()]
    meta_analyses = [e for e in extractions if e.study_type and 'meta' in e.study_type.lower()]

    print(f"Randomized Controlled Trials: {len(rcts)}")
    print(f"Cohort Studies: {len(cohort)}")
    print(f"Meta-Analyses: {len(meta_analyses)}")

    # Filter by intervention type
    print("\n--- Filtering by Intervention Type ---")
    drug_trials = [e for e in extractions if any(
        drug in e.intervention.lower()
        for drug in ['metformin', 'aspirin', 'statin', 'insulin']
    )]
    diet_trials = [e for e in extractions if 'diet' in e.intervention.lower()]

    print(f"Drug Interventions: {len(drug_trials)}")
    for e in drug_trials:
        print(f"  - {e.intervention[:80]}...")

    print(f"\nDiet Interventions: {len(diet_trials)}")
    for e in diet_trials:
        print(f"  - {e.intervention[:80]}...")

    # High confidence extractions
    print("\n--- High Confidence Extractions ---")
    high_confidence = [e for e in extractions if e.extraction_confidence >= 0.8]
    print(f"Extractions with ≥80% confidence: {len(high_confidence)}/{len(extractions)}")

    for e in high_confidence:
        print(f"\n{e.document_title[:60]}...")
        print(f"  Overall Confidence: {e.extraction_confidence:.1%}")
        print(f"  Component Confidences:")
        print(f"    Population: {e.population_confidence or 'N/A'}")
        print(f"    Intervention: {e.intervention_confidence or 'N/A'}")
        print(f"    Comparison: {e.comparison_confidence or 'N/A'}")
        print(f"    Outcome: {e.outcome_confidence or 'N/A'}")


def demo_export():
    """Demonstrate exporting PICO extractions."""
    print_section("DEMO 4: Export to JSON and CSV")

    agent = PICOAgent(model="gpt-oss:20b")

    # Extract from papers
    print("Extracting PICO components...")
    extractions = agent.extract_pico_batch(
        documents=SAMPLE_PAPERS,
        min_confidence=0.5
    )

    # Export to JSON
    json_file = "/tmp/pico_demo_extractions.json"
    print(f"\nExporting to JSON: {json_file}")
    agent.export_to_json(extractions, json_file)
    print(f"✓ Exported {len(extractions)} extractions to JSON")

    # Export to CSV
    csv_file = "/tmp/pico_demo_extractions.csv"
    print(f"\nExporting to CSV: {csv_file}")
    agent.export_to_csv(extractions, csv_file)
    print(f"✓ Exported {len(extractions)} extractions to CSV")

    print("\n--- Exported Files ---")
    print(f"JSON: {json_file}")
    print(f"CSV:  {csv_file}")
    print("\nThese files can be imported into systematic review tools like:")
    print("  - Covidence")
    print("  - DistillerSR")
    print("  - RevMan")
    print("  - Excel/Google Sheets")


def demo_statistics():
    """Demonstrate extraction statistics tracking."""
    print_section("DEMO 5: Extraction Statistics")

    agent = PICOAgent(model="gpt-oss:20b")

    # Process with different confidence thresholds
    print("Testing different confidence thresholds...\n")

    for threshold in [0.3, 0.5, 0.7, 0.9]:
        # Reset agent statistics
        agent._extraction_stats = {
            'total_extractions': 0,
            'successful_extractions': 0,
            'failed_extractions': 0,
            'low_confidence_extractions': 0,
            'parse_failures': 0
        }

        print(f"--- Confidence Threshold: {threshold:.1f} ---")

        extractions = agent.extract_pico_batch(
            documents=SAMPLE_PAPERS,
            min_confidence=threshold
        )

        stats = agent.get_extraction_stats()
        print(f"Total Attempts: {stats['total_extractions']}")
        print(f"Successful: {stats['successful_extractions']}")
        print(f"Failed: {stats['failed_extractions']}")
        print(f"Low Confidence: {stats['low_confidence_extractions']}")
        print(f"Parse Failures: {stats['parse_failures']}")
        print(f"Success Rate: {stats['success_rate']:.1%}\n")


def demo_integration_with_search():
    """Demonstrate integration with QueryAgent for complete workflow."""
    print_section("DEMO 6: Integration with Document Search (Simulation)")

    print("Complete Workflow Demonstration:")
    print("1. Search for relevant papers (simulated)")
    print("2. Extract PICO components")
    print("3. Filter by study design")
    print("4. Export for systematic review\n")

    # Simulate search results (in practice, use QueryAgent)
    print("Simulating database search for 'diabetes metformin'...")
    search_results = SAMPLE_PAPERS[:1]  # Just use metformin paper
    print(f"Found {len(search_results)} relevant documents\n")

    # Extract PICO
    agent = PICOAgent(model="gpt-oss:20b")
    print("Extracting PICO components from search results...")
    extractions = agent.extract_pico_batch(
        documents=search_results,
        min_confidence=0.6
    )

    # Filter by study design (systematic review typically wants RCTs)
    rcts = [e for e in extractions if e.study_type and 'RCT' in e.study_type.upper()]
    print(f"\nFiltered to {len(rcts)} Randomized Controlled Trials")

    # Export
    if rcts:
        output_file = "/tmp/diabetes_metformin_rcts_pico.csv"
        agent.export_to_csv(rcts, output_file)
        print(f"✓ Exported RCTs to: {output_file}")
        print("\nReady for systematic review!")


def main():
    """Run all demonstrations."""
    print("\n" + "="*80)
    print(" "*20 + "PICO Agent Demonstration Suite")
    print("="*80)
    print("\nThis demonstration showcases the PICOAgent's capabilities for extracting")
    print("Population, Intervention, Comparison, and Outcome components from")
    print("biomedical research papers.")
    print("\nNote: These demos use the gpt-oss:20b model. Make sure Ollama is running")
    print("and the model is available.")

    input("\nPress Enter to start demonstrations...")

    # Run demos
    try:
        demo_single_extraction()
        input("\nPress Enter to continue to next demo...")

        demo_batch_extraction()
        input("\nPress Enter to continue to next demo...")

        demo_filtering_and_analysis()
        input("\nPress Enter to continue to next demo...")

        demo_export()
        input("\nPress Enter to continue to next demo...")

        demo_statistics()
        input("\nPress Enter to continue to next demo...")

        demo_integration_with_search()

        print("\n" + "="*80)
        print(" "*25 + "Demonstrations Complete!")
        print("="*80)
        print("\nFor more information, see:")
        print("  - User Guide: doc/users/pico_agent_guide.md")
        print("  - Developer Docs: doc/developers/pico_agent.md")
        print("  - Tests: tests/test_pico_agent.py")

    except KeyboardInterrupt:
        print("\n\nDemo interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Error during demonstration: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
