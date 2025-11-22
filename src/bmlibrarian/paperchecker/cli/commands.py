"""
Command handlers for PaperChecker CLI.

Provides functions for loading abstracts from JSON files or database,
processing abstracts with the PaperCheckerAgent, and exporting results.
"""

import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from tqdm import tqdm

from bmlibrarian.paperchecker.agent import PaperCheckerAgent
from bmlibrarian.paperchecker.data_models import PaperCheckResult

logger = logging.getLogger(__name__)

# Constants for validation
MIN_ABSTRACT_LENGTH: int = 50
MAX_ABSTRACT_LENGTH: int = 50000
MIN_PMID: int = 1
MAX_PMID: int = 99999999999  # 11 digits max for PMID

# Progress bar configuration
PROGRESS_BAR_FORMAT: str = "{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]"
PROGRESS_BAR_UNIT: str = "abstract"

# Error message and preview limits
MAX_VALIDATION_ERRORS_DISPLAYED: int = 5
MAX_ERROR_PREVIEW_LENGTH: int = 100
MAX_MISSING_PMIDS_DISPLAYED: int = 10
YEAR_STRING_LENGTH: int = 4


def validate_abstract(abstract: str, index: int) -> Tuple[bool, Optional[str]]:
    """
    Validate abstract text for processing.

    Args:
        abstract: The abstract text to validate
        index: Index position for error reporting

    Returns:
        Tuple of (is_valid, error_message). If valid, error_message is None.
    """
    if not abstract:
        return False, f"Abstract at index {index} is empty"

    if not isinstance(abstract, str):
        return False, f"Abstract at index {index} is not a string (got {type(abstract).__name__})"

    stripped = abstract.strip()
    if len(stripped) < MIN_ABSTRACT_LENGTH:
        return False, (
            f"Abstract at index {index} is too short "
            f"({len(stripped)} chars, minimum: {MIN_ABSTRACT_LENGTH})"
        )

    if len(stripped) > MAX_ABSTRACT_LENGTH:
        return False, (
            f"Abstract at index {index} is too long "
            f"({len(stripped)} chars, maximum: {MAX_ABSTRACT_LENGTH})"
        )

    return True, None


def load_abstracts_from_json(filepath: str) -> List[Dict[str, Any]]:
    """
    Load abstracts from JSON file with validation.

    Expected JSON format:
    [
        {
            "abstract": "Full abstract text...",
            "metadata": {"pmid": 12345678, "title": "...", ...}
        },
        ...
    ]

    Args:
        filepath: Path to JSON file containing abstracts

    Returns:
        List of dictionaries with 'abstract' and optional 'metadata' keys

    Raises:
        FileNotFoundError: If the input file does not exist
        ValueError: If the JSON structure is invalid or abstracts fail validation
        json.JSONDecodeError: If the file contains invalid JSON
    """
    logger.info(f"Loading abstracts from {filepath}")

    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {filepath}")

    if not path.is_file():
        raise ValueError(f"Path is not a file: {filepath}")

    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {filepath}: {e}")
        raise

    # Validate structure
    if not isinstance(data, list):
        raise ValueError(
            f"JSON must be a list of abstract objects, got {type(data).__name__}"
        )

    if len(data) == 0:
        raise ValueError("JSON file contains no abstracts")

    # Validate each abstract
    validated_abstracts: List[Dict[str, Any]] = []
    validation_errors: List[str] = []

    for i, item in enumerate(data):
        if not isinstance(item, dict):
            validation_errors.append(
                f"Item at index {i} is not a dict (got {type(item).__name__})"
            )
            continue

        # Check for 'abstract' key
        if 'abstract' not in item:
            validation_errors.append(f"Item at index {i} missing 'abstract' key")
            continue

        # Validate abstract content
        is_valid, error_msg = validate_abstract(item['abstract'], i)
        if not is_valid:
            validation_errors.append(error_msg)
            continue

        # Normalize structure
        validated_abstracts.append({
            'abstract': item['abstract'].strip(),
            'metadata': item.get('metadata', {})
        })

    if validation_errors:
        error_summary = "; ".join(validation_errors[:MAX_VALIDATION_ERRORS_DISPLAYED])
        if len(validation_errors) > MAX_VALIDATION_ERRORS_DISPLAYED:
            remaining = len(validation_errors) - MAX_VALIDATION_ERRORS_DISPLAYED
            error_summary += f" (and {remaining} more errors)"
        raise ValueError(f"Validation errors in JSON file: {error_summary}")

    logger.info(f"Loaded {len(validated_abstracts)} valid abstracts from {filepath}")
    return validated_abstracts


def load_abstracts_from_pmids(pmids: List[int]) -> List[Dict[str, Any]]:
    """
    Fetch abstracts from database by PMID.

    Uses the DatabaseManager to query the document table for abstracts
    matching the provided PMIDs.

    Args:
        pmids: List of PubMed IDs to fetch

    Returns:
        List of dictionaries with 'abstract' and 'metadata' keys

    Raises:
        ValueError: If any PMID is invalid
        RuntimeError: If database connection fails
    """
    logger.info(f"Fetching {len(pmids)} abstracts from database")

    # Validate PMIDs
    for pmid in pmids:
        if not isinstance(pmid, int) or pmid < MIN_PMID or pmid > MAX_PMID:
            raise ValueError(f"Invalid PMID: {pmid}. Must be integer between {MIN_PMID} and {MAX_PMID}")

    try:
        from bmlibrarian.database import get_db_manager
        from psycopg.rows import dict_row

        db_manager = get_db_manager()
        abstracts: List[Dict[str, Any]] = []

        with db_manager.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("""
                    SELECT
                        pmid, title, abstract, authors,
                        publication_date, publication AS journal, doi
                    FROM document
                    WHERE pmid = ANY(%s)
                    AND abstract IS NOT NULL
                    AND abstract != ''
                """, (pmids,))

                results = cur.fetchall()

                for row in results:
                    # Extract year from publication_date
                    year = None
                    if row.get("publication_date"):
                        year_str = str(row["publication_date"])[:YEAR_STRING_LENGTH]
                        if year_str.isdigit():
                            year = int(year_str)

                    abstracts.append({
                        "abstract": row["abstract"],
                        "metadata": {
                            "pmid": row["pmid"],
                            "title": row.get("title"),
                            "authors": row.get("authors"),
                            "year": year,
                            "journal": row.get("journal"),
                            "doi": row.get("doi")
                        }
                    })

        # Check for missing PMIDs
        found_pmids = {a["metadata"]["pmid"] for a in abstracts}
        missing_pmids = set(pmids) - found_pmids
        if missing_pmids:
            displayed_pmids = sorted(missing_pmids)[:MAX_MISSING_PMIDS_DISPLAYED]
            ellipsis = "..." if len(missing_pmids) > MAX_MISSING_PMIDS_DISPLAYED else ""
            logger.warning(
                f"Could not find abstracts for {len(missing_pmids)} PMIDs: "
                f"{displayed_pmids}{ellipsis}"
            )

        logger.info(f"Fetched {len(abstracts)} abstracts from database")
        return abstracts

    except ImportError as e:
        logger.error(f"Failed to import database module: {e}")
        raise RuntimeError("Database module not available") from e
    except Exception as e:
        logger.error(f"Failed to fetch abstracts from database: {e}")
        raise RuntimeError(f"Database query failed: {e}") from e


def check_abstracts(
    abstracts: List[Dict[str, Any]],
    agent: PaperCheckerAgent,
    continue_on_error: bool = False,
    progress_callback: Optional[Callable[[int, int, Optional[str]], None]] = None
) -> Tuple[List[PaperCheckResult], List[Dict[str, Any]]]:
    """
    Check all abstracts with progress tracking and error recovery.

    Processes each abstract through the PaperCheckerAgent, tracking progress
    and optionally continuing on errors.

    Args:
        abstracts: List of abstract dictionaries to process
        agent: Initialized PaperCheckerAgent instance
        continue_on_error: If True, continue processing after failures
        progress_callback: Optional callback(completed, total, error_message)

    Returns:
        Tuple of (successful_results, errors)
        - successful_results: List of PaperCheckResult objects
        - errors: List of error dictionaries with index, pmid, and error message
    """
    results: List[PaperCheckResult] = []
    errors: List[Dict[str, Any]] = []
    total = len(abstracts)

    logger.info(f"Starting batch check of {total} abstracts")

    # Progress bar
    pbar = tqdm(
        abstracts,
        desc="Checking abstracts",
        unit=PROGRESS_BAR_UNIT,
        bar_format=PROGRESS_BAR_FORMAT
    )

    for i, item in enumerate(pbar, 1):
        pmid = item.get("metadata", {}).get("pmid")

        try:
            # Update progress bar description
            pbar.set_postfix({
                "current": i,
                "ok": len(results),
                "errors": len(errors)
            })

            # Check abstract
            result = agent.check_abstract(
                abstract=item["abstract"],
                source_metadata=item.get("metadata", {})
            )

            results.append(result)

            # Log summary
            stmt_count = len(result.statements)
            verdict_summary = _summarize_verdicts(result)
            logger.info(
                f"Abstract {i}/{total}: {stmt_count} statements, {verdict_summary}"
            )

            # Callback
            if progress_callback:
                progress_callback(i, total, None)

        except Exception as e:
            abstract_text = item["abstract"]
            if len(abstract_text) > MAX_ERROR_PREVIEW_LENGTH:
                preview = abstract_text[:MAX_ERROR_PREVIEW_LENGTH] + "..."
            else:
                preview = abstract_text
            error_info = {
                "index": i,
                "pmid": pmid,
                "error": str(e),
                "abstract_preview": preview
            }
            errors.append(error_info)
            logger.error(f"Failed to check abstract {i} (PMID: {pmid}): {e}")

            # Callback with error
            if progress_callback:
                progress_callback(i, total, str(e))

            if not continue_on_error:
                logger.error("Stopping due to error (use --continue-on-error to continue)")
                break

    pbar.close()

    logger.info(f"Batch check complete: {len(results)}/{total} successful, {len(errors)} errors")

    return results, errors


def _summarize_verdicts(result: PaperCheckResult) -> str:
    """
    Create a brief summary of verdicts for logging.

    Args:
        result: PaperCheckResult to summarize

    Returns:
        Summary string like "2 supports, 1 contradicts"
    """
    verdict_counts = {"supports": 0, "contradicts": 0, "undecided": 0}
    for verdict in result.verdicts:
        verdict_counts[verdict.verdict] += 1

    parts = []
    for vtype, count in verdict_counts.items():
        if count > 0:
            parts.append(f"{count} {vtype}")

    return ", ".join(parts) if parts else "no verdicts"


def export_results_json(
    results: List[PaperCheckResult],
    output_file: str,
    include_metadata: bool = True
) -> None:
    """
    Export results to JSON file.

    Args:
        results: List of PaperCheckResult objects to export
        output_file: Path to output JSON file
        include_metadata: Whether to include processing metadata

    Raises:
        OSError: If file cannot be written
        ValueError: If results list is empty
    """
    if not results:
        raise ValueError("No results to export")

    logger.info(f"Exporting {len(results)} results to {output_file}")

    output_path = Path(output_file)

    # Ensure parent directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Convert to JSON-serializable format
        output_data = [result.to_json_dict() for result in results]

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

        logger.info(f"Exported {len(results)} results to {output_file}")

    except Exception as e:
        logger.error(f"Failed to export JSON: {e}")
        raise


def export_markdown_reports(
    results: List[PaperCheckResult],
    output_dir: str
) -> List[str]:
    """
    Export markdown reports to directory.

    Creates one markdown file per abstract with complete analysis.

    Args:
        results: List of PaperCheckResult objects to export
        output_dir: Directory path for output files

    Returns:
        List of created file paths

    Raises:
        OSError: If directory cannot be created or files cannot be written
        ValueError: If results list is empty
    """
    if not results:
        raise ValueError("No results to export")

    logger.info(f"Exporting {len(results)} markdown reports to {output_dir}")

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    created_files: List[str] = []

    for i, result in enumerate(results, 1):
        # Generate filename from PMID or index
        pmid = result.source_metadata.get("pmid")
        if pmid:
            filename = f"report_pmid_{pmid}.md"
        else:
            filename = f"report_abstract_{i}.md"

        filepath = output_path / filename

        try:
            markdown = result.to_markdown_report()

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(markdown)

            created_files.append(str(filepath))
            logger.debug(f"Exported report {i}/{len(results)}: {filename}")

        except Exception as e:
            logger.error(f"Failed to export markdown for abstract {i}: {e}")
            # Continue with other files

    logger.info(f"Exported {len(created_files)} reports to {output_dir}")
    return created_files
