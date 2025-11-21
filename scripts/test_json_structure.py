#!/usr/bin/env python3
"""
Test script to validate the PubMedQA JSON structure without database access.
"""

import json
from pathlib import Path


def validate_json_structure(json_file: str):
    """Validate JSON structure matches expected PubMedQA format."""

    print(f"Loading JSON file: {json_file}")
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print(f"✓ JSON loaded successfully")
    print(f"  Total entries: {len(data)}")

    # Validate structure
    print("\nValidating structure...")

    # Check first few entries
    sample_size = min(5, len(data))
    for i, (pmid, entry) in enumerate(list(data.items())[:sample_size]):
        print(f"\n  Entry {i+1}: PMID {pmid}")

        # Check required fields
        required_fields = ['QUESTION', 'CONTEXTS', 'LONG_ANSWER', 'final_decision']
        for field in required_fields:
            if field not in entry:
                print(f"    ✗ Missing field: {field}")
                return False
            else:
                if field == 'CONTEXTS':
                    print(f"    ✓ {field}: {len(entry[field])} paragraphs")
                elif field == 'LONG_ANSWER':
                    print(f"    ✓ {field}: {len(entry[field])} characters")
                elif field == 'QUESTION':
                    print(f"    ✓ {field}: {entry[field][:60]}...")
                else:
                    print(f"    ✓ {field}: {entry[field]}")

    # Show statistics
    print("\n" + "=" * 80)
    print("Statistics:")
    print("=" * 80)

    total_questions = len(data)
    total_contexts = sum(len(entry.get('CONTEXTS', [])) for entry in data.values())
    total_long_answers = sum(1 for entry in data.values() if entry.get('LONG_ANSWER'))

    decisions = {}
    for entry in data.values():
        decision = entry.get('final_decision', 'unknown')
        decisions[decision] = decisions.get(decision, 0) + 1

    print(f"  Total questions:    {total_questions}")
    print(f"  Total contexts:     {total_contexts}")
    print(f"  Avg contexts/entry: {total_contexts/total_questions:.2f}")
    print(f"  Long answers:       {total_long_answers}")
    print(f"\n  Decisions:")
    for decision, count in sorted(decisions.items()):
        print(f"    {decision}: {count} ({100*count/total_questions:.1f}%)")

    # Show sample context and long_answer
    print("\n" + "=" * 80)
    print("Sample Entry:")
    print("=" * 80)

    first_pmid, first_entry = next(iter(data.items()))
    print(f"\nPMID: {first_pmid}")
    print(f"\nQUESTION:")
    print(f"  {first_entry['QUESTION']}")
    print(f"\nCONTEXTS ({len(first_entry['CONTEXTS'])} paragraphs):")
    for i, context in enumerate(first_entry['CONTEXTS'], 1):
        print(f"  [{i}] {context[:100]}..." if len(context) > 100 else f"  [{i}] {context}")
    print(f"\nLONG_ANSWER:")
    print(f"  {first_entry['LONG_ANSWER']}")
    print(f"\nfinal_decision: {first_entry['final_decision']}")

    print("\n" + "=" * 80)
    print("✓ JSON structure validation completed successfully!")
    print("=" * 80)

    return True


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python test_json_structure.py <json_file>")
        sys.exit(1)

    json_file = sys.argv[1]

    if not Path(json_file).exists():
        print(f"Error: File not found: {json_file}")
        sys.exit(1)

    try:
        validate_json_structure(json_file)
    except Exception as e:
        print(f"\n✗ Validation failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
