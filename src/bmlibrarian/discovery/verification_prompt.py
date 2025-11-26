"""PDF Verification User Prompt Module.

Provides interactive prompts for users to review and decide on PDF downloads
that fail automatic verification (DOI/title mismatch).

Supports both CLI prompts and GUI dialogs.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Callable, Dict, Any

logger = logging.getLogger(__name__)


class VerificationDecision(Enum):
    """User decision for PDF verification."""

    ACCEPT = "accept"  # Accept and ingest the PDF
    SAVE_AS = "save_as"  # Save PDF to custom location without ingesting
    RETRY = "retry"  # Reject and try searching again
    REJECT = "reject"  # Reject completely
    REASSIGN = "reassign"  # Assign PDF to a different document (by extracted DOI)
    MANUAL_UPLOAD = "manual_upload"  # User manually selected a different PDF file


@dataclass
class AlternativeDocument:
    """Information about a document that matches the extracted DOI."""

    doc_id: int
    title: str
    doi: str
    has_pdf: bool  # Whether this document already has a PDF assigned
    authors: Optional[str] = None
    year: Optional[int] = None


@dataclass
class VerificationPromptData:
    """Data for verification prompt."""

    pdf_path: Path
    expected_doi: Optional[str]
    extracted_doi: Optional[str]
    expected_title: Optional[str]
    extracted_title: Optional[str]
    expected_pmid: Optional[str] = None
    extracted_pmid: Optional[str] = None
    title_similarity: Optional[float] = None
    verification_warnings: Optional[list] = None
    doc_id: Optional[int] = None
    # Alternative document that matches the extracted DOI (if found)
    alternative_document: Optional[AlternativeDocument] = None
    # Source URL that led to the mismatched PDF (for "Open in Browser")
    source_url: Optional[str] = None
    # Path to manually uploaded PDF (set by dialog when user uploads)
    manual_upload_path: Optional[Path] = None

    def get_mismatch_summary(self) -> str:
        """Get a human-readable summary of the mismatch."""
        lines = []

        if self.expected_doi and self.extracted_doi:
            if self.expected_doi.lower() != self.extracted_doi.lower():
                lines.append(f"DOI mismatch:")
                lines.append(f"  Expected: {self.expected_doi}")
                lines.append(f"  Found:    {self.extracted_doi}")

        if self.expected_title and self.extracted_title:
            similarity = self.title_similarity or 0.0
            if similarity < 0.9:
                lines.append(f"Title mismatch (similarity: {similarity:.0%}):")
                lines.append(f"  Expected: {self.expected_title[:80]}...")
                lines.append(f"  Found:    {self.extracted_title[:80]}...")

        if self.verification_warnings:
            for warning in self.verification_warnings:
                if warning not in str(lines):
                    lines.append(f"Warning: {warning}")

        return "\n".join(lines) if lines else "Unknown mismatch"


def find_alternative_document(extracted_doi: str) -> Optional[AlternativeDocument]:
    """Look up a document in the database by DOI.

    Args:
        extracted_doi: The DOI extracted from the PDF

    Returns:
        AlternativeDocument if found and has no PDF, None otherwise
    """
    if not extracted_doi:
        return None

    try:
        from bmlibrarian.database import get_db_manager
        db_manager = get_db_manager()

        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                # Look for document with this DOI that doesn't have a PDF yet
                cur.execute("""
                    SELECT id, title, doi, pdf_filename,
                           authors, EXTRACT(YEAR FROM publication_date)::int as year
                    FROM document
                    WHERE LOWER(doi) = LOWER(%s)
                    LIMIT 1
                """, (extracted_doi,))

                row = cur.fetchone()
                if row:
                    doc_id, title, doi, pdf_filename, authors, year = row
                    has_pdf = bool(pdf_filename)

                    return AlternativeDocument(
                        doc_id=doc_id,
                        title=title or "Unknown Title",
                        doi=doi,
                        has_pdf=has_pdf,
                        authors=authors,
                        year=year
                    )

        return None

    except Exception as e:
        logger.warning(f"Failed to look up alternative document for DOI {extracted_doi}: {e}")
        return None


def prompt_cli_verification(
    data: VerificationPromptData,
    show_pdf_callback: Optional[Callable[[Path], None]] = None
) -> tuple[VerificationDecision, Optional[Path], Optional[int]]:
    """Prompt user in CLI for verification decision.

    Args:
        data: Verification prompt data with expected vs extracted info
        show_pdf_callback: Optional callback to display PDF (e.g., open in viewer)

    Returns:
        Tuple of (decision, save_path, reassign_doc_id) where:
        - save_path is only set for SAVE_AS or MANUAL_UPLOAD
        - reassign_doc_id is only set for REASSIGN
    """
    import webbrowser

    print("\n" + "=" * 70)
    print("PDF VERIFICATION REQUIRED")
    print("=" * 70)
    print(f"\nDownloaded PDF: {data.pdf_path.name}")
    print(f"\n{data.get_mismatch_summary()}")

    # Show source URL if available
    if data.source_url:
        print(f"\nSource URL: {data.source_url}")

    # Show alternative document if available
    if data.alternative_document and not data.alternative_document.has_pdf:
        alt = data.alternative_document
        print("\n" + "-" * 70)
        print("📄 MATCHING DOCUMENT FOUND IN DATABASE:")
        print(f"   Title: {alt.title[:70]}{'...' if len(alt.title) > 70 else ''}")
        print(f"   DOI: {alt.doi}")
        if alt.authors:
            print(f"   Authors: {alt.authors[:50]}{'...' if len(alt.authors) > 50 else ''}")
        if alt.year:
            print(f"   Year: {alt.year}")
        print(f"   Document ID: {alt.doc_id}")
        print("   This document does NOT have a PDF assigned yet.")

    print("\n" + "-" * 70)

    # Offer to open PDF if callback provided
    if show_pdf_callback:
        open_pdf = input("Open PDF to review? [y/N]: ").strip().lower()
        if open_pdf == 'y':
            try:
                show_pdf_callback(data.pdf_path)
            except Exception as e:
                logger.warning(f"Failed to open PDF: {e}")

    # Build options dynamically
    print("\nOptions:")
    print("  [A] Accept - Ingest this PDF despite the mismatch")
    if data.alternative_document and not data.alternative_document.has_pdf:
        print(f"  [D] Reassign - Assign this PDF to document {data.alternative_document.doc_id} instead")
    print("  [U] Upload - Manually select a different PDF file")
    if data.source_url:
        print("  [B] Browser - Open source URL in browser to find correct PDF")
    print("  [S] Save As - Save to a different location (then continue)")
    print("  [R] Retry - Try searching for the correct PDF again")
    print("  [X] Reject - Discard this PDF")

    valid_choices = ['A', 'U', 'S', 'R', 'X']
    if data.alternative_document and not data.alternative_document.has_pdf:
        valid_choices.insert(1, 'D')
    if data.source_url:
        valid_choices.insert(-2, 'B')

    while True:
        choice = input(f"\nYour choice [{'/'.join(valid_choices)}]: ").strip().upper()

        if choice == 'A':
            return VerificationDecision.ACCEPT, None, None

        elif choice == 'D' and data.alternative_document and not data.alternative_document.has_pdf:
            return VerificationDecision.REASSIGN, None, data.alternative_document.doc_id

        elif choice == 'U':
            upload_path_str = input("Enter path to PDF file: ").strip()
            if upload_path_str:
                upload_path = Path(upload_path_str).expanduser()
                if upload_path.exists() and upload_path.suffix.lower() == '.pdf':
                    print(f"✓ Selected: {upload_path}")
                    return VerificationDecision.MANUAL_UPLOAD, upload_path, None
                else:
                    print("✗ Invalid file path or not a PDF file")
            continue

        elif choice == 'B' and data.source_url:
            print(f"Opening in browser: {data.source_url}")
            try:
                webbrowser.open(data.source_url)
            except Exception as e:
                print(f"✗ Failed to open browser: {e}")
            # Continue showing options - don't return
            continue

        elif choice == 'S':
            save_path_str = input("Enter save path (or press Enter for Downloads): ").strip()
            if save_path_str:
                save_path = Path(save_path_str).expanduser()
            else:
                save_path = Path("~/Downloads").expanduser() / data.pdf_path.name

            # Copy the file
            import shutil
            try:
                shutil.copy2(data.pdf_path, save_path)
                print(f"✓ Saved to: {save_path}")
            except Exception as e:
                print(f"✗ Failed to save: {e}")

            # After saving, continue with other options (remove Save As from choices)
            print("\nPDF saved. What would you like to do next?")
            print("  [A] Accept - Also ingest this PDF to the original document")
            if data.alternative_document and not data.alternative_document.has_pdf:
                print(f"  [D] Reassign - Assign this PDF to document {data.alternative_document.doc_id}")
            print("  [U] Upload - Manually select a different PDF file")
            print("  [R] Retry - Try searching for the correct PDF again")
            print("  [X] Reject - Discard this PDF (already saved a copy)")

            continue_choices = ['A', 'U', 'R', 'X']
            if data.alternative_document and not data.alternative_document.has_pdf:
                continue_choices.insert(1, 'D')

            while True:
                choice2 = input(f"\nYour choice [{'/'.join(continue_choices)}]: ").strip().upper()
                if choice2 == 'A':
                    return VerificationDecision.ACCEPT, save_path, None
                elif choice2 == 'D' and data.alternative_document and not data.alternative_document.has_pdf:
                    return VerificationDecision.REASSIGN, save_path, data.alternative_document.doc_id
                elif choice2 == 'U':
                    upload_path_str = input("Enter path to PDF file: ").strip()
                    if upload_path_str:
                        upload_path = Path(upload_path_str).expanduser()
                        if upload_path.exists() and upload_path.suffix.lower() == '.pdf':
                            print(f"✓ Selected: {upload_path}")
                            return VerificationDecision.MANUAL_UPLOAD, upload_path, None
                        else:
                            print("✗ Invalid file path or not a PDF file")
                    continue
                elif choice2 == 'R':
                    return VerificationDecision.RETRY, save_path, None
                elif choice2 == 'X':
                    return VerificationDecision.REJECT, save_path, None
                else:
                    print(f"Invalid choice. Please enter {'/'.join(continue_choices)}.")

        elif choice == 'R':
            return VerificationDecision.RETRY, None, None

        elif choice == 'X':
            return VerificationDecision.REJECT, None, None

        else:
            print(f"Invalid choice. Please enter {'/'.join(valid_choices)}.")


def prompt_gui_verification(
    data: VerificationPromptData,
    parent=None
) -> tuple[VerificationDecision, Optional[Path], Optional[int]]:
    """Show GUI dialog for verification decision.

    Args:
        data: Verification prompt data
        parent: Optional parent widget

    Returns:
        Tuple of (decision, path, reassign_doc_id) where:
        - path is save_path for SAVE_AS, or manual_upload_path for MANUAL_UPLOAD
        - reassign_doc_id is only set for REASSIGN
    """
    # Import here to avoid PySide6 dependency for CLI-only usage
    from .verification_dialog import PDFVerificationDialog

    dialog = PDFVerificationDialog(data, parent)
    result = dialog.exec()

    if result == PDFVerificationDialog.Accepted:
        # For MANUAL_UPLOAD, return the manually selected file path
        if dialog.decision == VerificationDecision.MANUAL_UPLOAD:
            return dialog.decision, data.manual_upload_path, dialog.reassign_doc_id
        return dialog.decision, dialog.save_path, dialog.reassign_doc_id
    else:
        return VerificationDecision.REJECT, None, None
