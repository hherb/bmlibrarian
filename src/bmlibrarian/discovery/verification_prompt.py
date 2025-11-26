"""PDF Verification User Prompt Module.

Provides interactive prompts for users to review and decide on PDF downloads
that fail automatic verification (DOI/title mismatch).

Supports both CLI prompts and GUI dialogs.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class VerificationDecision(Enum):
    """User decision for PDF verification."""

    ACCEPT = "accept"  # Accept and ingest the PDF
    SAVE_AS = "save_as"  # Save PDF to custom location without ingesting
    RETRY = "retry"  # Reject and try searching again
    REJECT = "reject"  # Reject completely


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


def prompt_cli_verification(
    data: VerificationPromptData,
    show_pdf_callback: Optional[Callable[[Path], None]] = None
) -> tuple[VerificationDecision, Optional[Path]]:
    """Prompt user in CLI for verification decision.

    Args:
        data: Verification prompt data with expected vs extracted info
        show_pdf_callback: Optional callback to display PDF (e.g., open in viewer)

    Returns:
        Tuple of (decision, save_path) where save_path is only set for SAVE_AS
    """
    print("\n" + "=" * 70)
    print("PDF VERIFICATION REQUIRED")
    print("=" * 70)
    print(f"\nDownloaded PDF: {data.pdf_path.name}")
    print(f"\n{data.get_mismatch_summary()}")
    print("\n" + "-" * 70)

    # Offer to open PDF if callback provided
    if show_pdf_callback:
        open_pdf = input("Open PDF to review? [y/N]: ").strip().lower()
        if open_pdf == 'y':
            try:
                show_pdf_callback(data.pdf_path)
            except Exception as e:
                logger.warning(f"Failed to open PDF: {e}")

    print("\nOptions:")
    print("  [A] Accept - Ingest this PDF despite the mismatch")
    print("  [S] Save As - Save to a different location (don't ingest)")
    print("  [R] Retry - Try searching for the correct PDF again")
    print("  [X] Reject - Discard this PDF")

    while True:
        choice = input("\nYour choice [A/S/R/X]: ").strip().upper()

        if choice == 'A':
            return VerificationDecision.ACCEPT, None

        elif choice == 'S':
            save_path_str = input("Enter save path (or press Enter for Downloads): ").strip()
            if save_path_str:
                save_path = Path(save_path_str).expanduser()
            else:
                save_path = Path("~/Downloads").expanduser() / data.pdf_path.name
            return VerificationDecision.SAVE_AS, save_path

        elif choice == 'R':
            return VerificationDecision.RETRY, None

        elif choice == 'X':
            return VerificationDecision.REJECT, None

        else:
            print("Invalid choice. Please enter A, S, R, or X.")


def prompt_gui_verification(
    data: VerificationPromptData,
    parent=None
) -> tuple[VerificationDecision, Optional[Path]]:
    """Show GUI dialog for verification decision.

    Args:
        data: Verification prompt data
        parent: Optional parent widget

    Returns:
        Tuple of (decision, save_path) where save_path is only set for SAVE_AS
    """
    # Import here to avoid PySide6 dependency for CLI-only usage
    from .verification_dialog import PDFVerificationDialog

    dialog = PDFVerificationDialog(data, parent)
    result = dialog.exec()

    if result == PDFVerificationDialog.Accepted:
        return dialog.decision, dialog.save_path
    else:
        return VerificationDecision.REJECT, None
