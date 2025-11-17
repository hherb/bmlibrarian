"""
Abstract base class for document card factories.

This module provides the foundation for creating document cards across different
UI frameworks (Flet, Qt) with consistent interfaces and functionality.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional, Dict, List
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# Constants for Document Card Factory
# ============================================================================

# Display limits
MAX_AUTHORS_BEFORE_ET_AL = 3  # Maximum authors to show before using "et al."

# Score color thresholds
SCORE_THRESHOLD_EXCELLENT = 4.5  # Threshold for excellent score (green)
SCORE_THRESHOLD_GOOD = 3.5  # Threshold for good score (blue)
SCORE_THRESHOLD_MODERATE = 2.5  # Threshold for moderate score (orange)
# Below MODERATE is considered poor (red)

# Score colors (hex values)
SCORE_COLOR_EXCELLENT = "#2E7D32"  # Dark green
SCORE_COLOR_GOOD = "#1976D2"  # Blue
SCORE_COLOR_MODERATE = "#F57C00"  # Orange
SCORE_COLOR_POOR = "#C62828"  # Red


class CardContext(Enum):
    """Context in which a document card is being displayed."""
    LITERATURE = "literature"  # General literature browsing
    SCORING = "scoring"  # Document relevance scoring
    CITATIONS = "citations"  # Citation extraction
    COUNTERFACTUAL = "counterfactual"  # Counterfactual analysis
    REPORT = "report"  # Final report generation
    SEARCH = "search"  # Search results
    REVIEW = "review"  # Fact-checker review


class PDFButtonState(Enum):
    """State of the PDF button for a document."""
    VIEW = "view"  # Local PDF exists, can view
    FETCH = "fetch"  # PDF URL available, can download
    UPLOAD = "upload"  # No PDF, allow manual upload
    HIDDEN = "hidden"  # No PDF button shown


@dataclass
class PDFButtonConfig:
    """Configuration for PDF button behavior."""
    state: PDFButtonState
    pdf_path: Optional[Path] = None
    pdf_url: Optional[str] = None
    on_view: Optional[Callable] = None  # Callback for viewing PDF
    on_fetch: Optional[Callable] = None  # Callback for fetching PDF
    on_upload: Optional[Callable] = None  # Callback for uploading PDF
    show_notifications: bool = True  # Show success/error notifications


@dataclass
class DocumentCardData:
    """Data for rendering a document card."""
    # Core document data
    doc_id: int
    title: str
    abstract: Optional[str] = None
    authors: Optional[List[str]] = None
    year: Optional[int] = None
    journal: Optional[str] = None
    pmid: Optional[str] = None
    doi: Optional[str] = None
    source: Optional[str] = None  # e.g., "pubmed", "medrxiv"

    # Scoring data
    relevance_score: Optional[float] = None
    human_score: Optional[float] = None
    confidence: Optional[str] = None

    # Citation data
    citations: Optional[List[Dict[str, Any]]] = None  # List of extracted citations

    # PDF data
    pdf_path: Optional[Path] = None
    pdf_url: Optional[str] = None

    # Display options
    context: CardContext = CardContext.LITERATURE
    show_abstract: bool = True
    show_metadata: bool = True
    show_pdf_button: bool = True
    expanded_by_default: bool = False

    # Callbacks
    on_score_change: Optional[Callable] = None  # Callback when score changes
    on_citation_select: Optional[Callable] = None  # Callback when citation selected
    on_pdf_action: Optional[Callable] = None  # Callback for PDF actions


class DocumentCardFactoryBase(ABC):
    """
    Abstract base class for document card factories.

    This class defines the interface that all document card factories must implement,
    regardless of the UI framework being used. It provides common functionality for:

    - Creating document cards with consistent styling
    - Managing PDF button states (View/Fetch/Upload)
    - Handling card variations based on context
    - Formatting document metadata

    Subclasses must implement framework-specific rendering methods.
    """

    def __init__(self, base_pdf_dir: Optional[Path] = None):
        """
        Initialize the document card factory.

        Args:
            base_pdf_dir: Base directory for PDF files (defaults to ~/knowledgebase/pdf)

        Raises:
            ValueError: If base_pdf_dir is not a valid directory path
        """
        if base_pdf_dir is None:
            base_pdf_dir = Path.home() / "knowledgebase" / "pdf"

        self.base_pdf_dir = Path(base_pdf_dir)

        # Validate and create directory if it doesn't exist
        try:
            self.base_pdf_dir.mkdir(parents=True, exist_ok=True)
        except (PermissionError, OSError) as e:
            logger.error(f"Failed to create PDF directory {self.base_pdf_dir}: {e}")
            raise ValueError(f"Invalid PDF directory: {base_pdf_dir}") from e

        # Check if directory is writable
        if not self.base_pdf_dir.is_dir():
            raise ValueError(f"PDF path is not a directory: {base_pdf_dir}")

        # Test write access
        try:
            test_file = self.base_pdf_dir / ".write_test"
            test_file.touch()
            test_file.unlink()
        except (PermissionError, OSError) as e:
            logger.warning(f"PDF directory {self.base_pdf_dir} is not writable: {e}")

    @abstractmethod
    def create_card(self, card_data: DocumentCardData) -> Any:
        """
        Create a document card widget.

        Args:
            card_data: Data and configuration for the card

        Returns:
            A framework-specific card widget (e.g., ft.ExpansionTile for Flet,
            QFrame for Qt)
        """
        pass

    @abstractmethod
    def create_pdf_button(self, config: PDFButtonConfig) -> Any:
        """
        Create a PDF button widget with appropriate state.

        Args:
            config: Configuration for the PDF button

        Returns:
            A framework-specific button widget
        """
        pass

    def determine_pdf_state(
        self,
        doc_id: int,
        pdf_path: Optional[Path] = None,
        pdf_url: Optional[str] = None
    ) -> PDFButtonState:
        """
        Determine the appropriate PDF button state for a document.

        Args:
            doc_id: Document ID
            pdf_path: Explicit PDF path if known
            pdf_url: PDF URL if available

        Returns:
            The appropriate PDFButtonState
        """
        # Check if explicit path provided and exists
        if pdf_path and pdf_path.exists():
            return PDFButtonState.VIEW

        # Check standard location
        standard_path = self.base_pdf_dir / f"{doc_id}.pdf"
        if standard_path.exists():
            return PDFButtonState.VIEW

        # Check if URL available for fetching
        if pdf_url:
            return PDFButtonState.FETCH

        # No PDF available, allow upload
        return PDFButtonState.UPLOAD

    def get_pdf_path(self, doc_id: int, pdf_path: Optional[Path] = None) -> Optional[Path]:
        """
        Get the actual PDF path for a document.

        Args:
            doc_id: Document ID
            pdf_path: Explicit PDF path if known

        Returns:
            Path to PDF file if it exists, None otherwise
        """
        if pdf_path and pdf_path.exists():
            return pdf_path

        standard_path = self.base_pdf_dir / f"{doc_id}.pdf"
        if standard_path.exists():
            return standard_path

        return None

    def format_authors(
        self,
        authors: Optional[List[str]],
        max_authors: int = MAX_AUTHORS_BEFORE_ET_AL
    ) -> str:
        """
        Format author list for display.

        Args:
            authors: List of author names
            max_authors: Maximum number of authors to show before truncating

        Returns:
            Formatted author string
        """
        if not authors:
            return "Unknown authors"

        if len(authors) <= max_authors:
            return ", ".join(authors)

        return f"{', '.join(authors[:max_authors])}, et al."

    def format_metadata(
        self,
        year: Optional[int] = None,
        journal: Optional[str] = None,
        pmid: Optional[str] = None,
        doi: Optional[str] = None,
        source: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Format document metadata for display.

        Args:
            year: Publication year
            journal: Journal name
            pmid: PubMed ID
            doi: DOI
            source: Data source

        Returns:
            Dictionary of formatted metadata items
        """
        metadata = {}

        if year:
            metadata["Year"] = str(year)

        if journal:
            metadata["Journal"] = journal

        if pmid:
            metadata["PMID"] = pmid

        if doi:
            metadata["DOI"] = doi

        if source:
            metadata["Source"] = source.upper()

        return metadata

    def get_score_color(self, score: float, context: CardContext = CardContext.LITERATURE) -> str:
        """
        Get color for relevance score display.

        Args:
            score: Relevance score (typically 1-5)
            context: Context in which the score is being displayed

        Returns:
            Color string (hex or named color)
        """
        if score >= SCORE_THRESHOLD_EXCELLENT:
            return SCORE_COLOR_EXCELLENT
        elif score >= SCORE_THRESHOLD_GOOD:
            return SCORE_COLOR_GOOD
        elif score >= SCORE_THRESHOLD_MODERATE:
            return SCORE_COLOR_MODERATE
        else:
            return SCORE_COLOR_POOR

    def truncate_abstract(self, abstract: Optional[str], max_length: int = None) -> str:
        """
        Return the full abstract (NEVER truncates).

        This method exists for API compatibility but always returns the full abstract.
        Truncation is disabled because users must be able to verify all data.

        Args:
            abstract: Full abstract text
            max_length: Ignored - kept for API compatibility only

        Returns:
            Full abstract text or "No abstract available." if None
        """
        if not abstract:
            return "No abstract available."

        # NEVER truncate - users need to see full abstract for verification
        return abstract
