# Step 12: CLI Application Implementation

## Context

All core PaperChecker components are now implemented. We need a command-line interface for practical use of the system.

## Objective

Create `paper_checker_cli.py` that provides:
- Batch processing of abstracts from JSON files
- Progress tracking and logging
- Error recovery
- Results export to JSON and markdown
- Statistics reporting

## Requirements

- User-friendly CLI with clear output
- Support for JSON input files
- Progress bars for batch processing
- Graceful error handling
- Multiple output formats

## Implementation Location

Create: `paper_checker_cli.py` (root directory)

## CLI Design

```python
#!/usr/bin/env python3
"""
PaperChecker CLI - Medical abstract fact-checking from command line

Usage:
    uv run python paper_checker_cli.py input.json
    uv run python paper_checker_cli.py input.json -o results.json
    uv run python paper_checker_cli.py input.json --export-markdown reports/
    uv run python paper_checker_cli.py --pmid 12345678 23456789
"""

import sys
import json
import logging
import argparse
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime
from tqdm import tqdm

from bmlibrarian.paperchecker.agent import PaperCheckerAgent
from bmlibrarian.paperchecker.data_models import PaperCheckResult


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="PaperChecker - Medical abstract fact-checking",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Check abstracts from JSON file
  python paper_checker_cli.py abstracts.json

  # Check and export results
  python paper_checker_cli.py abstracts.json -o results.json

  # Check specific PMIDs
  python paper_checker_cli.py --pmid 12345678 23456789

  # Export markdown reports
  python paper_checker_cli.py abstracts.json --export-markdown reports/

Input JSON format:
  [
    {
      "abstract": "Full abstract text...",
      "metadata": {"pmid": 12345678, "title": "..."}
    },
    ...
  ]
        """
    )

    parser.add_argument(
        "input_file",
        nargs="?",
        help="JSON file with abstracts to check"
    )

    parser.add_argument(
        "--pmid",
        nargs="+",
        type=int,
        help="Check abstracts by PMID (fetch from database)"
    )

    parser.add_argument(
        "-o", "--output",
        help="Output JSON file for results"
    )

    parser.add_argument(
        "--export-markdown",
        metavar="DIR",
        help="Export markdown reports to directory"
    )

    parser.add_argument(
        "--config",
        help="Config file path (default: ~/.bmlibrarian/config.json)"
    )

    parser.add_argument(
        "--max-abstracts",
        type=int,
        help="Limit number of abstracts to check"
    )

    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue processing if an abstract fails"
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )

    return parser.parse_args()


def load_abstracts_from_json(filepath: str) -> List[Dict[str, Any]]:
    """Load abstracts from JSON file"""
    logger.info(f"Loading abstracts from {filepath}")

    try:
        with open(filepath, 'r') as f:
            data = json.load(f)

        if not isinstance(data, list):
            raise ValueError("JSON must be a list of abstract objects")

        logger.info(f"Loaded {len(data)} abstracts")
        return data

    except Exception as e:
        logger.error(f"Failed to load JSON file: {e}")
        sys.exit(1)


def load_abstracts_from_pmids(pmids: List[int]) -> List[Dict[str, Any]]:
    """Fetch abstracts from database by PMID"""
    logger.info(f"Fetching {len(pmids)} abstracts from database")

    # Implementation would query public.documents table
    abstracts = []

    import psycopg
    from psycopg.rows import dict_row
    import os

    conn_string = (
        f"dbname={os.getenv('POSTGRES_DB', 'knowledgebase')} "
        f"user={os.getenv('POSTGRES_USER', 'postgres')} "
        f"password={os.getenv('POSTGRES_PASSWORD', '')} "
        f"host={os.getenv('POSTGRES_HOST', 'localhost')} "
        f"port={os.getenv('POSTGRES_PORT', '5432')}"
    )

    try:
        with psycopg.connect(conn_string) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("""
                    SELECT pmid, title, abstract, authors, publication_year, journal, doi
                    FROM public.documents
                    WHERE pmid = ANY(%s)
                """, (pmids,))

                results = cur.fetchall()

                for row in results:
                    abstracts.append({
                        "abstract": row["abstract"],
                        "metadata": {
                            "pmid": row["pmid"],
                            "title": row["title"],
                            "authors": row["authors"],
                            "year": row["publication_year"],
                            "journal": row["journal"],
                            "doi": row["doi"]
                        }
                    })

        logger.info(f"Fetched {len(abstracts)} abstracts")
        return abstracts

    except Exception as e:
        logger.error(f"Failed to fetch from database: {e}")
        sys.exit(1)


def check_abstracts(
    abstracts: List[Dict[str, Any]],
    agent: PaperCheckerAgent,
    continue_on_error: bool = False
) -> List[PaperCheckResult]:
    """Check all abstracts with progress tracking"""
    results = []
    errors = []

    # Progress bar
    pbar = tqdm(abstracts, desc="Checking abstracts", unit="abstract")

    for i, item in enumerate(pbar, 1):
        try:
            # Update progress bar
            pbar.set_postfix({"current": i, "errors": len(errors)})

            # Check abstract
            result = agent.check_abstract(
                abstract=item["abstract"],
                source_metadata=item.get("metadata", {})
            )

            results.append(result)

            # Log summary
            logger.info(
                f"Abstract {i}/{len(abstracts)}: "
                f"{len(result.statements)} statements, "
                f"overall: {result.overall_assessment[:50]}..."
            )

        except Exception as e:
            error_info = {
                "index": i,
                "pmid": item.get("metadata", {}).get("pmid"),
                "error": str(e)
            }
            errors.append(error_info)
            logger.error(f"Failed to check abstract {i}: {e}")

            if not continue_on_error:
                logger.error("Stopping due to error (use --continue-on-error to continue)")
                break

    pbar.close()

    # Summary
    print(f"\n{'='*60}")
    print(f"Completed: {len(results)}/{len(abstracts)} abstracts")
    if errors:
        print(f"Errors: {len(errors)}")
        for err in errors:
            print(f"  - Abstract {err['index']} (PMID: {err.get('pmid', 'N/A')}): {err['error']}")
    print(f"{'='*60}\n")

    return results


def export_results_json(results: List[PaperCheckResult], output_file: str):
    """Export results to JSON file"""
    logger.info(f"Exporting results to {output_file}")

    try:
        # Convert to JSON-serializable format
        output_data = [result.to_json_dict() for result in results]

        with open(output_file, 'w') as f:
            json.dump(output_data, f, indent=2)

        logger.info(f"Exported {len(results)} results to {output_file}")

    except Exception as e:
        logger.error(f"Failed to export JSON: {e}")


def export_markdown_reports(results: List[PaperCheckResult], output_dir: str):
    """Export markdown reports to directory"""
    logger.info(f"Exporting markdown reports to {output_dir}")

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    for i, result in enumerate(results, 1):
        # Generate filename
        pmid = result.source_metadata.get("pmid", f"abstract{i}")
        filename = f"report_{pmid}.md"
        filepath = output_path / filename

        # Generate markdown
        try:
            markdown = result.to_markdown_report()

            with open(filepath, 'w') as f:
                f.write(markdown)

            logger.info(f"Exported report {i}/{len(results)}: {filename}")

        except Exception as e:
            logger.error(f"Failed to export markdown for abstract {i}: {e}")

    logger.info(f"Exported {len(results)} reports to {output_dir}")


def print_statistics(results: List[PaperCheckResult]):
    """Print summary statistics"""
    print("\n" + "="*60)
    print("SUMMARY STATISTICS")
    print("="*60 + "\n")

    total = len(results)
    total_statements = sum(len(r.statements) for r in results)

    # Count verdicts
    verdict_counts = {"supports": 0, "contradicts": 0, "undecided": 0}
    confidence_counts = {"high": 0, "medium": 0, "low": 0}

    for result in results:
        for verdict in result.verdicts:
            verdict_counts[verdict.verdict] += 1
            confidence_counts[verdict.confidence] += 1

    # Print statistics
    print(f"Total abstracts checked: {total}")
    print(f"Total statements extracted: {total_statements}")
    print(f"Average statements per abstract: {total_statements/total:.1f}\n")

    print("Verdict Distribution:")
    for verdict_type, count in verdict_counts.items():
        pct = 100 * count / total_statements if total_statements > 0 else 0
        print(f"  {verdict_type.capitalize():12s}: {count:3d} ({pct:5.1f}%)")

    print("\nConfidence Distribution:")
    for conf_level, count in confidence_counts.items():
        pct = 100 * count / total_statements if total_statements > 0 else 0
        print(f"  {conf_level.capitalize():12s}: {count:3d} ({pct:5.1f}%)")

    print("\n" + "="*60 + "\n")


def main():
    """Main entry point"""
    args = parse_args()

    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Validate input
    if not args.input_file and not args.pmid:
        print("Error: Must provide either input_file or --pmid")
        sys.exit(1)

    # Load abstracts
    if args.input_file:
        abstracts = load_abstracts_from_json(args.input_file)
    else:
        abstracts = load_abstracts_from_pmids(args.pmid)

    # Limit if requested
    if args.max_abstracts and len(abstracts) > args.max_abstracts:
        logger.info(f"Limiting to {args.max_abstracts} abstracts")
        abstracts = abstracts[:args.max_abstracts]

    # Initialize agent
    logger.info("Initializing PaperCheckerAgent")
    agent = PaperCheckerAgent(config_path=args.config)

    # Test connection
    if not agent.test_connection():
        logger.error("Connection test failed. Check Ollama and PostgreSQL.")
        sys.exit(1)

    # Check abstracts
    results = check_abstracts(
        abstracts,
        agent,
        continue_on_error=args.continue_on_error
    )

    # Export results
    if args.output:
        export_results_json(results, args.output)

    if args.export_markdown:
        export_markdown_reports(results, args.export_markdown)

    # Print statistics
    if results:
        print_statistics(results)

    logger.info("PaperChecker CLI complete")


if __name__ == "__main__":
    main()
```

## Input JSON Format

```json
[
  {
    "abstract": "Background: Type 2 diabetes management requires effective long-term glycemic control. Objective: To compare the efficacy of metformin versus GLP-1 receptor agonists in long-term outcomes. Methods: Retrospective cohort study of 10,000 patients over 5 years. Results: Metformin demonstrated superior HbA1c reduction (1.5% vs 1.2%, p<0.001) and lower cardiovascular events (HR 0.75, 95% CI 0.65-0.85). Conclusion: Metformin shows superior long-term efficacy compared to GLP-1 agonists for T2DM.",
    "metadata": {
      "pmid": 12345678,
      "title": "Metformin vs GLP-1 in Type 2 Diabetes",
      "authors": ["Smith J", "Jones A"],
      "year": 2023,
      "journal": "Diabetes Care",
      "doi": "10.1234/example"
    }
  },
  {
    "abstract": "Another abstract...",
    "metadata": {
      "pmid": 23456789
    }
  }
]
```

## Usage Examples

```bash
# Basic usage
uv run python paper_checker_cli.py abstracts.json

# Export results to JSON
uv run python paper_checker_cli.py abstracts.json -o results.json

# Export markdown reports
uv run python paper_checker_cli.py abstracts.json --export-markdown reports/

# Check specific PMIDs from database
uv run python paper_checker_cli.py --pmid 12345678 23456789 34567890

# Limit number of abstracts
uv run python paper_checker_cli.py abstracts.json --max-abstracts 10

# Continue on errors
uv run python paper_checker_cli.py abstracts.json --continue-on-error

# Verbose output
uv run python paper_checker_cli.py abstracts.json -v
```

## Success Criteria

- [ ] CLI application implemented
- [ ] Command-line argument parsing working
- [ ] JSON input file loading working
- [ ] PMID-based loading working
- [ ] Progress tracking with tqdm
- [ ] Error handling and recovery
- [ ] JSON export working
- [ ] Markdown export working
- [ ] Statistics reporting informative
- [ ] User-friendly error messages
- [ ] All command-line options functional

## Next Steps

After completing this step, proceed to:
- **Step 13**: Laboratory Interface (13_LABORATORY_INTERFACE.md)
- Create paper_checker_lab.py for interactive testing
