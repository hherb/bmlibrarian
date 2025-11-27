"""
Data models for the writing module.

Provides type-safe dataclasses for citations, references,
documents, and version history.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum

from .constants import CitationStyle


@dataclass
class Citation:
    """
    Represents a citation marker in the document.

    Attributes:
        document_id: The database ID of the cited document
        label: Human-readable label (e.g., "Smith2023")
        position: Character position in the text where citation appears
        text: The full citation marker text (e.g., "[@id:12345:Smith2023]")
    """

    document_id: int
    label: str
    position: int
    text: str

    def __hash__(self) -> int:
        """Hash based on document_id for set operations."""
        return hash(self.document_id)

    def __eq__(self, other: object) -> bool:
        """Equality based on document_id."""
        if not isinstance(other, Citation):
            return False
        return self.document_id == other.document_id


@dataclass
class DocumentMetadata:
    """
    Metadata for a cited document from the database.

    Attributes:
        document_id: Database document ID
        title: Document title
        authors: List of author names
        journal: Journal name
        year: Publication year
        pmid: PubMed ID (if available)
        doi: Digital Object Identifier (if available)
        volume: Journal volume
        issue: Journal issue
        pages: Page range
        publication_date: Full publication date
    """

    document_id: int
    title: str
    authors: List[str] = field(default_factory=list)
    journal: Optional[str] = None
    year: Optional[int] = None
    pmid: Optional[str] = None
    doi: Optional[str] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None
    publication_date: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DocumentMetadata":
        """
        Create DocumentMetadata from a dictionary.

        Args:
            data: Dictionary with document fields

        Returns:
            DocumentMetadata instance
        """
        # Handle authors - could be string or list
        authors = data.get('authors', [])
        if isinstance(authors, str):
            # Split string by common separators
            authors = [a.strip() for a in authors.replace(';', ',').split(',') if a.strip()]

        return cls(
            document_id=data.get('id') or data.get('document_id', 0),
            title=data.get('title', ''),
            authors=authors,
            journal=data.get('journal'),
            year=data.get('year'),
            pmid=str(data.get('pmid')) if data.get('pmid') else None,
            doi=data.get('doi'),
            volume=data.get('volume'),
            issue=data.get('issue'),
            pages=data.get('pages'),
            publication_date=data.get('publication_date'),
        )

    def get_first_author_surname(self) -> str:
        """
        Extract the first author's surname.

        Returns:
            First author surname or "Unknown"
        """
        if not self.authors:
            return "Unknown"

        first_author = self.authors[0]
        # Handle "Surname, Firstname" format
        if ',' in first_author:
            return first_author.split(',')[0].strip()
        # Handle "Firstname Surname" format
        parts = first_author.split()
        return parts[-1] if parts else "Unknown"

    def generate_label(self) -> str:
        """
        Generate a citation label like "Smith2023".

        Returns:
            Citation label string
        """
        surname = self.get_first_author_surname()
        year = self.year or "n.d."
        return f"{surname}{year}"


@dataclass
class FormattedReference:
    """
    A formatted reference for the bibliography.

    Attributes:
        number: Sequential reference number (1-based)
        document_id: Database document ID
        formatted_text: Full formatted bibliographic entry
        metadata: Original document metadata
    """

    number: int
    document_id: int
    formatted_text: str
    metadata: Optional[DocumentMetadata] = None


@dataclass
class WritingDocument:
    """
    A document being written in the citation editor.

    Attributes:
        id: Database document ID (None for unsaved)
        title: Document title
        content: Markdown content with citation markers
        metadata: Additional metadata (cursor position, settings, etc.)
        created_at: Creation timestamp
        updated_at: Last update timestamp
        user_id: Optional user association
    """

    id: Optional[int] = None
    title: str = "Untitled Document"
    content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    user_id: Optional[int] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WritingDocument":
        """
        Create WritingDocument from a dictionary.

        Args:
            data: Dictionary with document fields

        Returns:
            WritingDocument instance
        """
        return cls(
            id=data.get('id'),
            title=data.get('title', 'Untitled Document'),
            content=data.get('content', ''),
            metadata=data.get('metadata', {}),
            created_at=data.get('created_at'),
            updated_at=data.get('updated_at'),
            user_id=data.get('user_id'),
        )

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for serialization.

        Returns:
            Dictionary representation
        """
        return {
            'id': self.id,
            'title': self.title,
            'content': self.content,
            'metadata': self.metadata,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'user_id': self.user_id,
        }

    @property
    def is_new(self) -> bool:
        """Check if document has not been saved yet."""
        return self.id is None


@dataclass
class DocumentVersion:
    """
    A version snapshot of a document.

    Attributes:
        id: Version ID
        document_id: Parent document ID
        content: Full content at time of save
        title: Document title at time of save
        version_type: Type of save (autosave, manual, export)
        saved_at: Timestamp of save
    """

    id: Optional[int] = None
    document_id: int = 0
    content: str = ""
    title: Optional[str] = None
    version_type: str = "autosave"
    saved_at: Optional[datetime] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DocumentVersion":
        """
        Create DocumentVersion from a dictionary.

        Args:
            data: Dictionary with version fields

        Returns:
            DocumentVersion instance
        """
        return cls(
            id=data.get('id'),
            document_id=data.get('document_id', 0),
            content=data.get('content', ''),
            title=data.get('title'),
            version_type=data.get('version_type', 'autosave'),
            saved_at=data.get('saved_at'),
        )


# Re-export CitationStyle from constants for convenience
__all__ = [
    'Citation',
    'DocumentMetadata',
    'FormattedReference',
    'WritingDocument',
    'DocumentVersion',
    'CitationStyle',
]
