#!/usr/bin/env python3
"""
Test script for document Q&A functionality.

Usage:
    python searchagenttest.py "What is the effect of X on Y?"
    python searchagenttest.py "Your question here" --document-id 12345
"""
import argparse
import sys

from bmlibrarian.qa import answer_from_document

DEFAULT_DOCUMENT_ID = 62843873


def main():
    """Run document Q&A test with CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Test document Q&A functionality",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python searchagenttest.py "What is the effect of soleus activation?"
    python searchagenttest.py "What are the main findings?" --document-id 12345
        """
    )
    parser.add_argument(
        "question",
        help="The question to ask about the document"
    )
    parser.add_argument(
        "--document-id",
        type=int,
        default=DEFAULT_DOCUMENT_ID,
        help=f"Database document ID (default: {DEFAULT_DOCUMENT_ID})"
    )

    args = parser.parse_args()

    result = answer_from_document(
        document_id=args.document_id,
        question=args.question
    )

    if result.success:
        print(result.answer)
        if result.reasoning:  # For thinking models
            print(f"\nReasoning: {result.reasoning}")
    else:
        print(f"Error: {result.error_message}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()