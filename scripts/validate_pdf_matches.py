#!/usr/bin/env python3
"""PDF Validation Script for BMLibrarian.

Scans existing PDFs and verifies that their content (DOI, PMID, title)
matches the expected values from the database. Helps identify PDFs that
were incorrectly matched or downloaded.

Usage:
    # Check all PDFs (dry run - report only)
    uv run python scripts/validate_pdf_matches.py

    # Check PDFs for specific document IDs
    uv run python scripts/validate_pdf_matches.py --ids 12345 23456 34567

    # Check last N documents with PDFs
    uv run python scripts/validate_pdf_matches.py --limit 100

    # Check and flag mismatches in database
    uv run python scripts/validate_pdf_matches.py --flag-mismatches

    # Export results to JSON
    uv run python scripts/validate_pdf_matches.py --output results.json

    # Verbose output
    uv run python scripts/validate_pdf_matches.py --verbose
"""

import argparse
import json
import logging
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, List, Dict, TYPE_CHECKING

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from bmlibrarian.database import get_db_manager
from bmlibrarian.discovery.pdf_verifier import PDFVerifier, VerificationResult

if TYPE_CHECKING:
    import psycopg

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of validating a single document's PDF."""

    doc_id: int
    doi: Optional[str]
    pmid: Optional[str]
    title: Optional[str]
    pdf_path: str
    pdf_exists: bool
    verified: Optional[bool]
    confidence: Optional[float]
    match_type: Optional[str]
    extracted_doi: Optional[str]
    extracted_pmid: Optional[str]
    extracted_title: Optional[str]
    title_similarity: Optional[float]
    warnings: List[str]
    error: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


def get_database_manager() -> Any:
    """Get DatabaseManager instance.

    Uses the centralized DatabaseManager which handles environment variables,
    configuration files, and connection pooling.

    Returns:
        DatabaseManager instance (use with context manager for connections)

    Raises:
        Exception: If initialization fails
    """
    return get_db_manager()


def get_pdf_base_dir() -> Path:
    """Get PDF base directory from configuration.

    Uses BMLibrarianConfig which respects environment variables and config files.

    Returns:
        Path to PDF base directory
    """
    from bmlibrarian.config import BMLibrarianConfig
    config = BMLibrarianConfig()
    return Path(config.get('pdf', {}).get('base_dir', '~/knowledgebase/pdf')).expanduser()


def get_documents_with_pdfs(
    conn: "psycopg.Connection",
    doc_ids: Optional[List[int]] = None,
    limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Query documents that have PDFs.

    Args:
        conn: Database connection
        doc_ids: Optional list of specific document IDs to check
        limit: Optional limit on number of documents

    Returns:
        List of document dictionaries
    """
    with conn.cursor() as cur:
        # Note: document table uses external_id for PMID (no separate pmid column)
        # Filter out both NULL and empty string pdf_filename values
        if doc_ids:
            # Specific document IDs
            placeholders = ','.join(['%s'] * len(doc_ids))
            cur.execute(f"""
                SELECT id, doi, external_id, title, pdf_filename, publication_date
                FROM document
                WHERE id IN ({placeholders})
                  AND pdf_filename IS NOT NULL
                  AND pdf_filename != ''
                ORDER BY id
            """, doc_ids)
        else:
            # All documents with PDFs, optionally limited
            query = """
                SELECT id, doi, external_id, title, pdf_filename, publication_date
                FROM document
                WHERE pdf_filename IS NOT NULL
                  AND pdf_filename != ''
                ORDER BY id DESC
            """
            if limit:
                query += f" LIMIT {limit}"
            cur.execute(query)

        rows = cur.fetchall()

        documents = []
        for row in rows:
            doc_id, doi, external_id, title, pdf_filename, pub_date = row
            documents.append({
                'id': doc_id,
                'doi': doi,
                'pmid': external_id,  # external_id stores PMID for PubMed documents
                'title': title,
                'pdf_filename': pdf_filename,
                'publication_date': str(pub_date) if pub_date else None
            })

        return documents


def find_pdf_path(pdf_filename: str, base_dir: Path) -> Optional[Path]:
    """Find the actual path to a PDF file.

    Handles both relative paths (YYYY/filename.pdf) and flat filenames.

    Args:
        pdf_filename: PDF filename from database
        base_dir: PDF base directory

    Returns:
        Path to PDF if found, None otherwise
    """
    # Try as relative path from base_dir
    relative_path = base_dir / pdf_filename
    if relative_path.exists():
        return relative_path

    # Try as just filename in base_dir
    if '/' in pdf_filename:
        filename_only = Path(pdf_filename).name
        flat_path = base_dir / filename_only
        if flat_path.exists():
            return flat_path

    # Try searching in year directories
    for year_dir in base_dir.iterdir():
        if year_dir.is_dir() and year_dir.name.isdigit():
            year_path = year_dir / Path(pdf_filename).name
            if year_path.exists():
                return year_path

    return None


def validate_document_pdf(
    document: Dict[str, Any],
    verifier: PDFVerifier,
    base_dir: Path
) -> ValidationResult:
    """Validate a single document's PDF.

    Args:
        document: Document dictionary
        verifier: PDFVerifier instance
        base_dir: PDF base directory

    Returns:
        ValidationResult
    """
    doc_id = document['id']
    pdf_filename = document['pdf_filename']

    # Find PDF path
    pdf_path = find_pdf_path(pdf_filename, base_dir)

    if not pdf_path:
        return ValidationResult(
            doc_id=doc_id,
            doi=document.get('doi'),
            pmid=document.get('pmid'),
            title=document.get('title'),
            pdf_path=pdf_filename,
            pdf_exists=False,
            verified=None,
            confidence=None,
            match_type=None,
            extracted_doi=None,
            extracted_pmid=None,
            extracted_title=None,
            title_similarity=None,
            warnings=['PDF file not found'],
            error='File not found'
        )

    try:
        # Verify PDF content
        verification = verifier.verify_pdf(
            pdf_path=pdf_path,
            expected_doi=document.get('doi'),
            expected_pmid=str(document.get('pmid')) if document.get('pmid') else None,
            expected_title=document.get('title')
        )

        return ValidationResult(
            doc_id=doc_id,
            doi=document.get('doi'),
            pmid=document.get('pmid'),
            title=document.get('title'),
            pdf_path=str(pdf_path),
            pdf_exists=True,
            verified=verification.verified,
            confidence=verification.confidence,
            match_type=verification.match_type,
            extracted_doi=verification.extracted_doi,
            extracted_pmid=verification.extracted_pmid,
            extracted_title=verification.extracted_title,
            title_similarity=verification.title_similarity,
            warnings=verification.warnings or [],
            error=verification.error
        )

    except Exception as e:
        return ValidationResult(
            doc_id=doc_id,
            doi=document.get('doi'),
            pmid=document.get('pmid'),
            title=document.get('title'),
            pdf_path=str(pdf_path) if pdf_path else pdf_filename,
            pdf_exists=True,
            verified=None,
            confidence=None,
            match_type=None,
            extracted_doi=None,
            extracted_pmid=None,
            extracted_title=None,
            title_similarity=None,
            warnings=[],
            error=str(e)
        )


def flag_mismatch_in_database(
    conn: "psycopg.Connection",
    doc_id: int,
    reason: str
) -> bool:
    """Flag a mismatched PDF in the database.

    Creates or updates a record in a validation_issues table.

    Args:
        conn: Database connection
        doc_id: Document ID
        reason: Reason for mismatch

    Returns:
        True if flagged successfully
    """
    try:
        with conn.cursor() as cur:
            # Ensure table exists (create if not)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS pdf_validation_issues (
                    id SERIAL PRIMARY KEY,
                    document_id INTEGER NOT NULL REFERENCES document(id),
                    issue_type VARCHAR(50) NOT NULL,
                    details TEXT,
                    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    resolved_at TIMESTAMP,
                    resolved_by VARCHAR(100),
                    UNIQUE (document_id, issue_type)
                )
            """)

            # Insert or update issue
            cur.execute("""
                INSERT INTO pdf_validation_issues (document_id, issue_type, details)
                VALUES (%s, 'content_mismatch', %s)
                ON CONFLICT (document_id, issue_type)
                DO UPDATE SET details = EXCLUDED.details, detected_at = CURRENT_TIMESTAMP
            """, (doc_id, reason))

            conn.commit()
            return True

    except Exception as e:
        logger.error(f"Failed to flag mismatch for document {doc_id}: {e}")
        conn.rollback()
        return False


def print_summary(results: List[ValidationResult]) -> None:
    """Print validation summary.

    Args:
        results: List of validation results
    """
    total = len(results)
    not_found = sum(1 for r in results if not r.pdf_exists)
    verified = sum(1 for r in results if r.verified is True)
    mismatched = sum(1 for r in results if r.verified is False)
    inconclusive = sum(1 for r in results if r.pdf_exists and r.verified is None)
    errors = sum(1 for r in results if r.error and r.pdf_exists)

    print("\n" + "=" * 70)
    print("PDF VALIDATION SUMMARY")
    print("=" * 70)
    print(f"Total documents checked:  {total}")
    print(f"PDFs not found:           {not_found}")
    print(f"Verified matches:         {verified}")
    print(f"Mismatched PDFs:          {mismatched}")
    print(f"Inconclusive:             {inconclusive}")
    print(f"Errors during check:      {errors}")
    print("=" * 70)

    if mismatched > 0:
        print("\nMISMATCHED PDFs (require investigation):")
        print("-" * 70)
        for r in results:
            if r.verified is False:
                print(f"  Doc ID {r.doc_id}:")
                print(f"    Expected DOI:  {r.doi}")
                print(f"    Found DOI:     {r.extracted_doi}")
                if r.warnings:
                    for w in r.warnings:
                        print(f"    Warning: {w}")
                print()


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success, 1 for errors)
    """
    parser = argparse.ArgumentParser(
        description="Validate PDF content matches database records",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        '--ids',
        type=int,
        nargs='+',
        help='Specific document IDs to check'
    )

    parser.add_argument(
        '--limit',
        type=int,
        help='Limit number of documents to check'
    )

    parser.add_argument(
        '--flag-mismatches',
        action='store_true',
        help='Flag mismatches in database (creates pdf_validation_issues table)'
    )

    parser.add_argument(
        '--output', '-o',
        type=str,
        help='Output results to JSON file'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Verbose output'
    )

    parser.add_argument(
        '--mismatches-only',
        action='store_true',
        help='Only show mismatched PDFs in output'
    )

    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    print("PDF Validation Tool for BMLibrarian")
    print("=" * 70)

    # Get database manager
    print("Connecting to database...")
    try:
        db_manager = get_database_manager()
    except Exception as e:
        print(f"  Failed to initialize database manager: {e}")
        return 1

    # Get PDF base directory
    base_dir = get_pdf_base_dir()
    print(f"PDF base directory: {base_dir}")

    if not base_dir.exists():
        print(f"  Warning: Directory does not exist!")

    # Use context manager for database connection
    with db_manager.get_connection() as conn:
        print("  Connected successfully")

        # Query documents
        print("\nQuerying documents with PDFs...")
        documents = get_documents_with_pdfs(conn, args.ids, args.limit)
        print(f"  Found {len(documents)} documents to validate")

        if not documents:
            print("No documents to validate.")
            return 0

        # Validate each document
        print("\nValidating PDFs...")
        verifier = PDFVerifier()
        results: List[ValidationResult] = []

        try:
            from tqdm import tqdm
            progress = tqdm(documents, desc="Validating", unit="doc")
        except ImportError:
            progress = documents

        for doc in progress:
            result = validate_document_pdf(doc, verifier, base_dir)
            results.append(result)

            # Verbose output
            if args.verbose:
                status = "VERIFIED" if result.verified else "MISMATCH" if result.verified is False else "UNKNOWN"
                print(f"  [{status}] Doc {result.doc_id}: {result.match_type or 'N/A'}")

            # Flag mismatches in database if requested
            if args.flag_mismatches and result.verified is False:
                reason = "; ".join(result.warnings) if result.warnings else "Content mismatch"
                flag_mismatch_in_database(conn, result.doc_id, reason)

    # Print summary (outside connection context)
    print_summary(results)

    # Export results if requested
    if args.output:
        output_path = Path(args.output)
        output_results = results
        if args.mismatches_only:
            output_results = [r for r in results if r.verified is False]

        output_data = {
            'timestamp': datetime.now().isoformat(),
            'total_checked': len(results),
            'mismatches': sum(1 for r in results if r.verified is False),
            'results': [r.to_dict() for r in output_results]
        }

        with open(output_path, 'w') as f:
            json.dump(output_data, f, indent=2, default=str)

        print(f"\nResults exported to: {output_path}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
