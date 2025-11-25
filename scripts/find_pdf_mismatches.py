#!/usr/bin/env python3
"""Find PDF Mismatches Script for BMLibrarian.

Scans PDFs for PubMed documents (source_id=1) and identifies those where
the PDF content doesn't match the expected document metadata. MedRxiv
documents are skipped as they should always be correctly matched.

This script is useful for:
- Auditing existing PDF collections for incorrect matches
- Finding PDFs that were downloaded via browser fallback and grabbed wrong content
- Generating reports of documents needing manual review

Usage:
    # Scan all PubMed documents with PDFs
    uv run python scripts/find_pdf_mismatches.py

    # Scan with limit for testing
    uv run python scripts/find_pdf_mismatches.py --limit 100

    # Export mismatches to JSON
    uv run python scripts/find_pdf_mismatches.py --output mismatches.json

    # Scan specific date range (by publication date)
    uv run python scripts/find_pdf_mismatches.py --year 2024

    # Verbose output with progress
    uv run python scripts/find_pdf_mismatches.py --verbose

    # Only show mismatches (skip verified)
    uv run python scripts/find_pdf_mismatches.py --mismatches-only
"""

import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, TYPE_CHECKING

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from bmlibrarian.database import get_db_manager
from bmlibrarian.discovery.pdf_verifier import PDFVerifier

if TYPE_CHECKING:
    import psycopg

logger = logging.getLogger(__name__)

# PubMed source ID in the database
PUBMED_SOURCE_ID = 1

# Default batch size for processing
DEFAULT_BATCH_SIZE = 100


@dataclass
class MismatchResult:
    """Result of checking a single document's PDF."""

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

    @property
    def is_mismatch(self) -> bool:
        """Check if this result represents a definite mismatch."""
        return self.verified is False


def get_pdf_base_dir() -> Path:
    """Get PDF base directory from configuration.

    Returns:
        Path to PDF base directory
    """
    from bmlibrarian.config import BMLibrarianConfig
    config = BMLibrarianConfig()
    return Path(config.get('pdf', {}).get('base_dir', '~/knowledgebase/pdf')).expanduser()


def get_pubmed_documents_with_pdfs(
    conn: "psycopg.Connection",
    limit: Optional[int] = None,
    year: Optional[int] = None,
    offset: int = 0
) -> List[Dict[str, Any]]:
    """Query PubMed documents (source_id=1) that have PDFs.

    Args:
        conn: Database connection
        limit: Optional limit on number of documents
        year: Optional year filter (publication year)
        offset: Offset for pagination

    Returns:
        List of document dictionaries
    """
    with conn.cursor() as cur:
        # Build query for PubMed documents only
        # Note: document table uses external_id for PMID (no separate pmid column)
        # Filter out both NULL and empty string pdf_filename values
        query = """
            SELECT id, doi, external_id, title, pdf_filename, publication_date
            FROM document
            WHERE source_id = %s
              AND pdf_filename IS NOT NULL
              AND pdf_filename != ''
        """
        params: List[Any] = [PUBMED_SOURCE_ID]

        if year:
            query += " AND EXTRACT(YEAR FROM publication_date) = %s"
            params.append(year)

        query += " ORDER BY id"

        if limit:
            query += f" LIMIT {limit}"

        if offset:
            query += f" OFFSET {offset}"

        cur.execute(query, params)
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


def count_pubmed_documents_with_pdfs(
    conn: "psycopg.Connection",
    year: Optional[int] = None
) -> int:
    """Count PubMed documents with PDFs.

    Args:
        conn: Database connection
        year: Optional year filter

    Returns:
        Count of documents
    """
    with conn.cursor() as cur:
        # Filter out both NULL and empty string pdf_filename values
        query = """
            SELECT COUNT(*)
            FROM document
            WHERE source_id = %s
              AND pdf_filename IS NOT NULL
              AND pdf_filename != ''
        """
        params: List[Any] = [PUBMED_SOURCE_ID]

        if year:
            query += " AND EXTRACT(YEAR FROM publication_date) = %s"
            params.append(year)

        cur.execute(query, params)
        return cur.fetchone()[0]


def find_pdf_path(pdf_filename: str, base_dir: Path) -> Optional[Path]:
    """Find the actual path to a PDF file.

    Args:
        pdf_filename: PDF filename from database (e.g., "2024/paper.pdf")
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


def check_document_pdf(
    document: Dict[str, Any],
    verifier: PDFVerifier,
    base_dir: Path
) -> MismatchResult:
    """Check a single document's PDF for mismatches.

    Args:
        document: Document dictionary
        verifier: PDFVerifier instance
        base_dir: PDF base directory

    Returns:
        MismatchResult
    """
    doc_id = document['id']
    pdf_filename = document['pdf_filename']

    # Find PDF path
    pdf_path = find_pdf_path(pdf_filename, base_dir)

    if not pdf_path:
        return MismatchResult(
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

        return MismatchResult(
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
        return MismatchResult(
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


def print_summary(results: List[MismatchResult], total_scanned: int) -> None:
    """Print scan summary.

    Args:
        results: List of mismatch results
        total_scanned: Total documents scanned
    """
    not_found = sum(1 for r in results if not r.pdf_exists)
    verified = sum(1 for r in results if r.verified is True)
    mismatched = sum(1 for r in results if r.verified is False)
    inconclusive = sum(1 for r in results if r.pdf_exists and r.verified is None)
    errors = sum(1 for r in results if r.error and r.pdf_exists)

    print("\n" + "=" * 70)
    print("PDF MISMATCH SCAN SUMMARY (PubMed Documents Only)")
    print("=" * 70)
    print(f"Total PubMed documents scanned:  {total_scanned}")
    print(f"PDFs not found:                  {not_found}")
    print(f"Verified matches:                {verified}")
    print(f"MISMATCHED PDFs:                 {mismatched}")
    print(f"Inconclusive:                    {inconclusive}")
    print(f"Errors during check:             {errors}")
    print("=" * 70)

    if mismatched > 0:
        print("\n⚠️  MISMATCHED PDFs (require investigation):")
        print("-" * 70)
        for r in results:
            if r.verified is False:
                print(f"\n  Document ID: {r.doc_id}")
                print(f"    Expected DOI:   {r.doi}")
                print(f"    Found DOI:      {r.extracted_doi}")
                print(f"    Expected PMID:  {r.pmid}")
                print(f"    Found PMID:     {r.extracted_pmid}")
                print(f"    PDF Path:       {r.pdf_path}")
                if r.title_similarity is not None:
                    print(f"    Title match:    {r.title_similarity:.1%}")
                if r.warnings:
                    for w in r.warnings:
                        print(f"    ⚠ {w}")
        print()


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success, 1 for errors)
    """
    parser = argparse.ArgumentParser(
        description="Find PDF mismatches in PubMed documents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        '--limit',
        type=int,
        help='Limit number of documents to scan'
    )

    parser.add_argument(
        '--year',
        type=int,
        help='Filter by publication year'
    )

    parser.add_argument(
        '--output', '-o',
        type=str,
        help='Output mismatches to JSON file'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Verbose output'
    )

    parser.add_argument(
        '--mismatches-only',
        action='store_true',
        help='Only output mismatched PDFs (skip verified)'
    )

    parser.add_argument(
        '--batch-size',
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f'Batch size for processing (default: {DEFAULT_BATCH_SIZE})'
    )

    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    print("PDF Mismatch Scanner for BMLibrarian")
    print("Scanning PubMed documents only (source_id=1)")
    print("=" * 70)

    # Get database connection via DatabaseManager
    print("Connecting to database...")
    try:
        db_manager = get_db_manager()
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

        # Count total documents
        total_count = count_pubmed_documents_with_pdfs(conn, args.year)
        scan_count = min(total_count, args.limit) if args.limit else total_count
        print(f"\nPubMed documents with PDFs: {total_count}")
        print(f"Documents to scan: {scan_count}")

        if scan_count == 0:
            print("No documents to scan.")
            return 0

        # Initialize verifier
        print("\nInitializing PDF verifier...")
        verifier = PDFVerifier()

        # Process in batches
        print(f"\nScanning PDFs (batch size: {args.batch_size})...")
        results: List[MismatchResult] = []
        processed = 0

        try:
            from tqdm import tqdm
            use_tqdm = True
        except ImportError:
            use_tqdm = False

        if use_tqdm:
            pbar = tqdm(total=scan_count, desc="Scanning", unit="doc")

        offset = 0
        while processed < scan_count:
            batch_limit = min(args.batch_size, scan_count - processed)
            documents = get_pubmed_documents_with_pdfs(
                conn, limit=batch_limit, year=args.year, offset=offset
            )

            if not documents:
                break

            for doc in documents:
                result = check_document_pdf(doc, verifier, base_dir)
                results.append(result)

                if args.verbose and not use_tqdm:
                    status = "✓" if result.verified else "✗" if result.verified is False else "?"
                    print(f"  [{status}] Doc {result.doc_id}: {result.match_type or 'N/A'}")

                processed += 1
                if use_tqdm:
                    pbar.update(1)

            offset += len(documents)

        if use_tqdm:
            pbar.close()

    # Print summary (outside connection context)
    print_summary(results, processed)

    # Export results if requested
    if args.output:
        output_path = Path(args.output)
        output_results = results
        if args.mismatches_only:
            output_results = [r for r in results if r.is_mismatch]

        output_data = {
            'scan_info': {
                'timestamp': datetime.now().isoformat(),
                'source': 'PubMed (source_id=1)',
                'total_scanned': processed,
                'year_filter': args.year,
            },
            'summary': {
                'verified': sum(1 for r in results if r.verified is True),
                'mismatched': sum(1 for r in results if r.verified is False),
                'inconclusive': sum(1 for r in results if r.pdf_exists and r.verified is None),
                'not_found': sum(1 for r in results if not r.pdf_exists),
            },
            'mismatches': [r.to_dict() for r in output_results if r.is_mismatch],
        }

        # Add all results if not mismatches-only
        if not args.mismatches_only:
            output_data['all_results'] = [r.to_dict() for r in output_results]

        with open(output_path, 'w') as f:
            json.dump(output_data, f, indent=2, default=str)

        print(f"\nResults exported to: {output_path}")
        if args.mismatches_only:
            print(f"  ({len(output_results)} mismatches exported)")

    # Return non-zero if mismatches found
    mismatch_count = sum(1 for r in results if r.is_mismatch)
    if mismatch_count > 0:
        print(f"\n⚠️  Found {mismatch_count} mismatched PDFs requiring investigation")
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
