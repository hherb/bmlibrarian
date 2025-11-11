#!/usr/bin/env python3
"""
Fact Checker Demo - Demonstrates FactCheckerAgent usage

Shows how to use the FactCheckerAgent to verify biomedical statements
against the literature database.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bmlibrarian.factchecker import FactCheckerAgent
from bmlibrarian.config import get_model, get_agent_config


def demo_single_statement():
    """Demonstrate checking a single statement."""
    print("=" * 80)
    print("DEMO 1: Single Statement Fact-Checking")
    print("=" * 80)

    # Get configuration
    model = get_model('fact_checker_agent')
    config = get_agent_config('fact_checker')

    # Create agent
    agent = FactCheckerAgent(
        model=model,
        temperature=config.get('temperature', 0.1),
        top_p=config.get('top_p', 0.9),
        max_tokens=config.get('max_tokens', 2000),
        score_threshold=config.get('score_threshold', 2.5),
        max_search_results=config.get('max_search_results', 50),
        max_citations=config.get('max_citations', 10),
        show_model_info=True
    )

    # Test statement
    statement = "All cases of childhood ulcerative colitis require colectomy"
    expected_answer = "no"

    print(f"\nStatement: {statement}")
    print(f"Expected answer: {expected_answer}")
    print("\nProcessing...\n")

    # Check statement
    result = agent.check_statement(
        statement=statement,
        expected_answer=expected_answer
    )

    # Display results
    print("-" * 80)
    print("RESULT:")
    print("-" * 80)
    print(f"Evaluation: {result.evaluation.upper()}")
    print(f"Confidence: {result.confidence}")
    print(f"Matches expected: {'✓ Yes' if result.matches_expected else '✗ No'}")
    print(f"\nReason: {result.reason}")
    print(f"\nDocuments reviewed: {result.documents_reviewed}")
    print(f"Supporting citations: {result.supporting_citations}")
    print(f"Contradicting citations: {result.contradicting_citations}")
    print(f"Neutral citations: {result.neutral_citations}")

    if result.evidence_list:
        print(f"\nEvidence ({len(result.evidence_list)} citations):")
        for i, evidence in enumerate(result.evidence_list[:5], 1):
            identifiers = []
            if evidence.pmid:
                identifiers.append(f"PMID:{evidence.pmid}")
            if evidence.doi:
                identifiers.append(f"DOI:{evidence.doi}")
            id_str = f" ({', '.join(identifiers)})" if identifiers else ""

            stance = ""
            if evidence.supports_statement is not None:
                stance = " [SUPPORTS]" if evidence.supports_statement else " [CONTRADICTS]"

            print(f"\n  [{i}]{stance}")
            print(f"  {evidence.citation_text[:200]}...{id_str}")

    print("\n" + "=" * 80)


def demo_batch_processing():
    """Demonstrate batch processing of multiple statements."""
    print("\n\n")
    print("=" * 80)
    print("DEMO 2: Batch Statement Processing")
    print("=" * 80)

    # Get configuration
    model = get_model('fact_checker_agent')
    config = get_agent_config('fact_checker')

    # Create agent with progress callback
    def progress_callback(step: str, message: str):
        print(f"  [{step.upper()}] {message}")

    agent = FactCheckerAgent(
        model=model,
        temperature=config.get('temperature', 0.1),
        top_p=config.get('top_p', 0.9),
        max_tokens=config.get('max_tokens', 2000),
        score_threshold=config.get('score_threshold', 2.5),
        max_search_results=20,  # Reduced for faster demo
        max_citations=5,        # Reduced for faster demo
        callback=progress_callback,
        show_model_info=False
    )

    # Test statements
    statements = [
        {
            "statement": "Vitamin D deficiency is common in IBD patients",
            "answer": "yes"
        },
        {
            "statement": "All IBD patients must take immunosuppressants",
            "answer": "no"
        },
        {
            "statement": "Fecal calprotectin is useful for monitoring IBD activity",
            "answer": "yes"
        }
    ]

    print(f"\nProcessing {len(statements)} statements in batch...\n")

    # Process batch
    results = agent.check_batch(statements)

    # Display summary
    print("\n" + "-" * 80)
    print("BATCH RESULTS SUMMARY:")
    print("-" * 80)

    for i, result in enumerate(results, 1):
        match_symbol = "✓" if result.matches_expected else "✗"
        print(f"\n[{i}] {result.statement[:60]}...")
        print(f"    Evaluation: {result.evaluation.upper()} (confidence: {result.confidence})")
        print(f"    Expected: {result.expected_answer} {match_symbol}")
        print(f"    Evidence: {len(result.evidence_list)} citations")

    # Calculate accuracy
    matches = sum(1 for r in results if r.matches_expected)
    accuracy = matches / len(results) * 100

    print(f"\n" + "=" * 80)
    print(f"Accuracy: {matches}/{len(results)} ({accuracy:.1f}%)")
    print("=" * 80)


def demo_custom_configuration():
    """Demonstrate custom agent configuration."""
    print("\n\n")
    print("=" * 80)
    print("DEMO 3: Custom Configuration")
    print("=" * 80)

    # Create agent with custom settings
    agent = FactCheckerAgent(
        model="gpt-oss:20b",
        temperature=0.15,           # Slightly higher temperature
        top_p=0.95,                 # Higher top_p for more diversity
        max_tokens=3000,            # More tokens for detailed reasoning
        score_threshold=3.0,        # Stricter relevance threshold
        max_search_results=30,      # Fewer documents
        max_citations=8,            # More citations
        show_model_info=True
    )

    print("\nCustom Configuration:")
    print(f"  Model: {agent.model}")
    print(f"  Temperature: {agent.temperature}")
    print(f"  Top-p: {agent.top_p}")
    print(f"  Score threshold: {agent.score_threshold}")
    print(f"  Max search results: {agent.max_search_results}")
    print(f"  Max citations: {agent.max_citations}")

    statement = "Probiotics are effective for treating all forms of IBD"
    print(f"\nStatement: {statement}")
    print("\nProcessing with custom configuration...\n")

    result = agent.check_statement(statement)

    print("-" * 80)
    print("RESULT:")
    print("-" * 80)
    print(f"Evaluation: {result.evaluation.upper()}")
    print(f"Confidence: {result.confidence}")
    print(f"Reason: {result.reason}")
    print(f"Evidence: {len(result.evidence_list)} citations")

    print("\n" + "=" * 80)


def demo_json_output():
    """Demonstrate JSON output format."""
    print("\n\n")
    print("=" * 80)
    print("DEMO 4: JSON Output Format")
    print("=" * 80)

    # Get configuration
    model = get_model('fact_checker_agent')
    config = get_agent_config('fact_checker')

    # Create agent
    agent = FactCheckerAgent(
        model=model,
        **{k: v for k, v in config.items() if k in ['temperature', 'top_p', 'max_tokens', 'score_threshold', 'max_search_results', 'max_citations']},
        show_model_info=False
    )

    statement = "Mesalamine is first-line therapy for mild ulcerative colitis"

    print(f"\nStatement: {statement}")
    print("\nProcessing...\n")

    result = agent.check_statement(statement, expected_answer="yes")

    # Convert to dictionary (JSON-serializable)
    result_dict = result.to_dict()

    print("-" * 80)
    print("JSON OUTPUT:")
    print("-" * 80)

    import json
    print(json.dumps(result_dict, indent=2))

    print("\n" + "=" * 80)


def main():
    """Run all demos."""
    print("\n")
    print("╔" + "═" * 78 + "╗")
    print("║" + " " * 20 + "BMLibrarian Fact Checker Demo" + " " * 29 + "║")
    print("╚" + "═" * 78 + "╝")

    try:
        # Demo 1: Single statement
        demo_single_statement()

        # Demo 2: Batch processing
        demo_batch_processing()

        # Demo 3: Custom configuration
        demo_custom_configuration()

        # Demo 4: JSON output
        demo_json_output()

        print("\n")
        print("╔" + "═" * 78 + "╗")
        print("║" + " " * 28 + "Demo Complete!" + " " * 35 + "║")
        print("╚" + "═" * 78 + "╝")
        print("\n")

    except KeyboardInterrupt:
        print("\n\n⚠ Demo interrupted by user")
        return 1
    except Exception as e:
        print(f"\n\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
