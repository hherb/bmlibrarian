#!/usr/bin/env python3
"""
Extract ID, question, and final_decision from a structured JSON file.

This script processes JSON files with nested structure where each entry contains
QUESTION and final_decision fields, and outputs a simplified JSON format.
"""

import json
import sys
from pathlib import Path


def extract_qa_data(input_file: str, output_file: str) -> None:
    """
    Extract ID, question, and answer from input JSON and write to output JSON.

    Args:
        input_file: Path to input JSON file
        output_file: Path to output JSON file
    """
    # Read input JSON
    input_path = Path(input_file)
    if not input_path.exists():
        print(f"Error: Input file '{input_file}' not found")
        sys.exit(1)

    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Extract relevant fields
    extracted_data = []
    for doc_id, content in data.items():
        entry = {
            "id": doc_id,
            "question": content.get("QUESTION", ""),
            "answer": content.get("final_decision", "")
        }
        extracted_data.append(entry)

    # Write output JSON
    output_path = Path(output_file)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(extracted_data, f, indent=2, ensure_ascii=False)

    print(f"Extracted {len(extracted_data)} entries from '{input_file}'")
    print(f"Output written to '{output_file}'")


def main():
    """Main entry point for the script."""
    if len(sys.argv) != 3:
        print("Usage: python extract_qa.py <input_json> <output_json>")
        print("\nExample:")
        print("  python extract_qa.py ~/Downloads/ori_pqal.json output_qa.json")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]

    extract_qa_data(input_file, output_file)


if __name__ == "__main__":
    main()
