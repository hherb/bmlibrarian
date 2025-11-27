"""
Citation formatter for generating bibliographic references.

Supports multiple citation styles:
- Vancouver (numbered, common in medical journals)
- APA (author-date)
- Harvard (author-date variant)
- Chicago (Chicago Manual of Style)
"""

import logging
from typing import List, Optional
from abc import ABC, abstractmethod

from .constants import CitationStyle, MAX_AUTHORS_BEFORE_ET_AL
from .models import DocumentMetadata, FormattedReference

logger = logging.getLogger(__name__)


class BaseFormatter(ABC):
    """Abstract base class for citation formatters."""

    @abstractmethod
    def format_reference(
        self,
        metadata: DocumentMetadata,
        number: Optional[int] = None
    ) -> str:
        """
        Format a single reference.

        Args:
            metadata: Document metadata
            number: Reference number (for numbered styles)

        Returns:
            Formatted reference string
        """
        pass

    @abstractmethod
    def format_inline_citation(
        self,
        metadata: DocumentMetadata,
        number: Optional[int] = None
    ) -> str:
        """
        Format an inline citation (for use in text).

        Args:
            metadata: Document metadata
            number: Reference number (for numbered styles)

        Returns:
            Formatted inline citation
        """
        pass

    def _format_authors(
        self,
        authors: List[str],
        max_authors: int = MAX_AUTHORS_BEFORE_ET_AL,
        use_et_al: bool = True
    ) -> str:
        """
        Format author list.

        Args:
            authors: List of author names
            max_authors: Maximum authors before truncation
            use_et_al: Whether to use "et al." for truncation

        Returns:
            Formatted author string
        """
        if not authors:
            return "Unknown author"

        if len(authors) <= max_authors:
            if len(authors) == 1:
                return authors[0]
            return ", ".join(authors[:-1]) + " and " + authors[-1]

        if use_et_al:
            return authors[0] + " et al."

        return ", ".join(authors[:max_authors]) + ", ..."

    def _format_title(self, title: str) -> str:
        """Format title (capitalize first letter, period at end)."""
        if not title:
            return "Untitled"
        title = title.strip()
        if not title.endswith('.'):
            title += '.'
        return title

    def _format_journal(self, journal: Optional[str]) -> str:
        """Format journal name (italicized in markdown)."""
        if not journal:
            return ""
        return f"*{journal}*"


class VancouverFormatter(BaseFormatter):
    """
    Vancouver citation style formatter.

    Common in medical and scientific journals.
    Uses numbered references in order of appearance.

    Example:
        1. Smith J, Johnson A, Williams B. Title of the article.
           Journal Name. 2023;45(2):123-134. doi:10.1234/example
    """

    def format_reference(
        self,
        metadata: DocumentMetadata,
        number: Optional[int] = None
    ) -> str:
        """Format a Vancouver-style reference."""
        parts = []

        # Number prefix
        if number is not None:
            parts.append(f"{number}.")

        # Authors (surname + initials)
        authors = self._format_vancouver_authors(metadata.authors)
        parts.append(authors)

        # Title
        title = self._format_title(metadata.title)
        parts.append(title)

        # Journal
        if metadata.journal:
            journal_part = self._format_journal(metadata.journal)

            # Add year, volume, issue, pages
            year_vol = []
            if metadata.year:
                year_vol.append(str(metadata.year))

            if metadata.volume:
                vol = metadata.volume
                if metadata.issue:
                    vol += f"({metadata.issue})"
                year_vol.append(vol)

            if year_vol:
                journal_part += f". {';'.join(year_vol)}"

            if metadata.pages:
                journal_part += f":{metadata.pages}"

            journal_part += "."
            parts.append(journal_part)

        # DOI or PMID
        if metadata.doi:
            parts.append(f"doi:{metadata.doi}")
        elif metadata.pmid:
            parts.append(f"PMID:{metadata.pmid}")

        return " ".join(parts)

    def format_inline_citation(
        self,
        metadata: DocumentMetadata,
        number: Optional[int] = None
    ) -> str:
        """Format inline citation as [N]."""
        if number is not None:
            return f"[{number}]"
        return f"[{metadata.document_id}]"

    def _format_vancouver_authors(self, authors: List[str]) -> str:
        """Format authors in Vancouver style (Surname Initials)."""
        if not authors:
            return "Unknown author."

        formatted = []
        for i, author in enumerate(authors):
            if i >= MAX_AUTHORS_BEFORE_ET_AL:
                formatted.append("et al")
                break
            formatted.append(self._to_vancouver_author(author))

        return ", ".join(formatted) + "."

    def _to_vancouver_author(self, author: str) -> str:
        """Convert author name to Vancouver format."""
        author = author.strip()

        if ',' in author:
            # Format: "Surname, Firstname Middle"
            parts = author.split(',', 1)
            surname = parts[0].strip()
            given = parts[1].strip() if len(parts) > 1 else ""
            initials = ''.join(n[0].upper() for n in given.split() if n)
            return f"{surname} {initials}"
        else:
            # Format: "Firstname Middle Surname"
            parts = author.split()
            if len(parts) == 1:
                return parts[0]
            surname = parts[-1]
            initials = ''.join(n[0].upper() for n in parts[:-1] if n)
            return f"{surname} {initials}"


class APAFormatter(BaseFormatter):
    """
    APA (American Psychological Association) citation style.

    Uses author-date format for inline citations.

    Example:
        Smith, J., Johnson, A., & Williams, B. (2023). Title of the article.
        Journal Name, 45(2), 123-134. https://doi.org/10.1234/example
    """

    def format_reference(
        self,
        metadata: DocumentMetadata,
        number: Optional[int] = None
    ) -> str:
        """Format an APA-style reference."""
        parts = []

        # Authors
        authors = self._format_apa_authors(metadata.authors)
        parts.append(authors)

        # Year
        year = f"({metadata.year})" if metadata.year else "(n.d.)"
        parts.append(year)

        # Title (sentence case, no italics for articles)
        title = self._format_title(metadata.title)
        parts.append(title)

        # Journal (italicized)
        if metadata.journal:
            journal_part = self._format_journal(metadata.journal)

            # Volume (italicized) and issue
            if metadata.volume:
                journal_part += f", *{metadata.volume}*"
                if metadata.issue:
                    journal_part += f"({metadata.issue})"

            # Pages
            if metadata.pages:
                journal_part += f", {metadata.pages}"

            journal_part += "."
            parts.append(journal_part)

        # DOI
        if metadata.doi:
            parts.append(f"https://doi.org/{metadata.doi}")

        return " ".join(parts)

    def format_inline_citation(
        self,
        metadata: DocumentMetadata,
        number: Optional[int] = None
    ) -> str:
        """Format inline citation as (Author, Year)."""
        surname = metadata.get_first_author_surname()
        year = metadata.year or "n.d."

        if len(metadata.authors) > 2:
            return f"({surname} et al., {year})"
        elif len(metadata.authors) == 2:
            surname2 = self._get_surname(metadata.authors[1])
            return f"({surname} & {surname2}, {year})"

        return f"({surname}, {year})"

    def _format_apa_authors(self, authors: List[str]) -> str:
        """Format authors in APA style."""
        if not authors:
            return "Unknown author."

        formatted = []
        for i, author in enumerate(authors):
            if i >= MAX_AUTHORS_BEFORE_ET_AL + 1:
                break
            if i == MAX_AUTHORS_BEFORE_ET_AL:
                formatted.append("...")
                formatted.append(self._to_apa_author(authors[-1]))
                break
            formatted.append(self._to_apa_author(author))

        if len(formatted) == 1:
            return formatted[0] + "."
        elif len(formatted) == 2:
            return f"{formatted[0]} & {formatted[1]}."

        return ", ".join(formatted[:-1]) + ", & " + formatted[-1] + "."

    def _to_apa_author(self, author: str) -> str:
        """Convert author name to APA format (Surname, I.)."""
        author = author.strip()

        if ',' in author:
            parts = author.split(',', 1)
            surname = parts[0].strip()
            given = parts[1].strip() if len(parts) > 1 else ""
            initials = '. '.join(n[0].upper() for n in given.split() if n)
            if initials:
                initials += '.'
            return f"{surname}, {initials}"
        else:
            parts = author.split()
            if len(parts) == 1:
                return parts[0]
            surname = parts[-1]
            initials = '. '.join(n[0].upper() for n in parts[:-1] if n)
            if initials:
                initials += '.'
            return f"{surname}, {initials}"

    def _get_surname(self, author: str) -> str:
        """Extract surname from author name."""
        author = author.strip()
        if ',' in author:
            return author.split(',')[0].strip()
        parts = author.split()
        return parts[-1] if parts else "Unknown"


class HarvardFormatter(BaseFormatter):
    """
    Harvard citation style.

    Similar to APA but with minor formatting differences.

    Example:
        Smith, J., Johnson, A. and Williams, B. (2023) 'Title of the article',
        Journal Name, 45(2), pp. 123-134. doi: 10.1234/example.
    """

    def format_reference(
        self,
        metadata: DocumentMetadata,
        number: Optional[int] = None
    ) -> str:
        """Format a Harvard-style reference."""
        parts = []

        # Authors
        authors = self._format_harvard_authors(metadata.authors)
        parts.append(authors)

        # Year
        year = f"({metadata.year})" if metadata.year else "(n.d.)"
        parts.append(year)

        # Title (in quotes)
        title = metadata.title.strip()
        if title.endswith('.'):
            title = title[:-1]
        parts.append(f"'{title}',")

        # Journal (italicized)
        if metadata.journal:
            journal_part = self._format_journal(metadata.journal)

            # Volume and issue
            if metadata.volume:
                journal_part += f", {metadata.volume}"
                if metadata.issue:
                    journal_part += f"({metadata.issue})"

            # Pages
            if metadata.pages:
                journal_part += f", pp. {metadata.pages}"

            journal_part += "."
            parts.append(journal_part)

        # DOI
        if metadata.doi:
            parts.append(f"doi: {metadata.doi}.")

        return " ".join(parts)

    def format_inline_citation(
        self,
        metadata: DocumentMetadata,
        number: Optional[int] = None
    ) -> str:
        """Format inline citation as (Author, Year)."""
        surname = metadata.get_first_author_surname()
        year = metadata.year or "n.d."

        if len(metadata.authors) > 2:
            return f"({surname} et al., {year})"
        elif len(metadata.authors) == 2:
            surname2 = self._get_surname(metadata.authors[1])
            return f"({surname} and {surname2}, {year})"

        return f"({surname}, {year})"

    def _format_harvard_authors(self, authors: List[str]) -> str:
        """Format authors in Harvard style."""
        if not authors:
            return "Unknown author"

        formatted = []
        for i, author in enumerate(authors):
            if i >= MAX_AUTHORS_BEFORE_ET_AL:
                formatted.append("et al.")
                break
            formatted.append(self._to_harvard_author(author))

        if len(formatted) == 1:
            return formatted[0]
        elif len(formatted) == 2:
            return f"{formatted[0]} and {formatted[1]}"

        return ", ".join(formatted[:-1]) + " and " + formatted[-1]

    def _to_harvard_author(self, author: str) -> str:
        """Convert author name to Harvard format."""
        author = author.strip()

        if ',' in author:
            parts = author.split(',', 1)
            surname = parts[0].strip()
            given = parts[1].strip() if len(parts) > 1 else ""
            initials = '.'.join(n[0].upper() for n in given.split() if n)
            if initials:
                initials += '.'
            return f"{surname}, {initials}"
        else:
            parts = author.split()
            if len(parts) == 1:
                return parts[0]
            surname = parts[-1]
            initials = '.'.join(n[0].upper() for n in parts[:-1] if n)
            if initials:
                initials += '.'
            return f"{surname}, {initials}"

    def _get_surname(self, author: str) -> str:
        """Extract surname from author name."""
        author = author.strip()
        if ',' in author:
            return author.split(',')[0].strip()
        parts = author.split()
        return parts[-1] if parts else "Unknown"


class ChicagoFormatter(BaseFormatter):
    """
    Chicago Manual of Style citation formatter.

    Uses author-date system (similar to APA) for scientific writing.

    Example:
        Smith, John, Anna Johnson, and Brian Williams. 2023.
        "Title of the Article." Journal Name 45 (2): 123-134.
        https://doi.org/10.1234/example.
    """

    def format_reference(
        self,
        metadata: DocumentMetadata,
        number: Optional[int] = None
    ) -> str:
        """Format a Chicago-style reference."""
        parts = []

        # Authors
        authors = self._format_chicago_authors(metadata.authors)
        parts.append(authors)

        # Year
        year = str(metadata.year) if metadata.year else "n.d."
        parts.append(f"{year}.")

        # Title (in quotes)
        title = metadata.title.strip()
        if title.endswith('.'):
            title = title[:-1]
        parts.append(f'"{title}."')

        # Journal (italicized)
        if metadata.journal:
            journal_part = self._format_journal(metadata.journal)

            # Volume and issue
            if metadata.volume:
                journal_part += f" {metadata.volume}"
                if metadata.issue:
                    journal_part += f" ({metadata.issue})"

            # Pages
            if metadata.pages:
                journal_part += f": {metadata.pages}"

            journal_part += "."
            parts.append(journal_part)

        # DOI
        if metadata.doi:
            parts.append(f"https://doi.org/{metadata.doi}.")

        return " ".join(parts)

    def format_inline_citation(
        self,
        metadata: DocumentMetadata,
        number: Optional[int] = None
    ) -> str:
        """Format inline citation as (Author Year)."""
        surname = metadata.get_first_author_surname()
        year = metadata.year or "n.d."

        if len(metadata.authors) > 2:
            return f"({surname} et al. {year})"
        elif len(metadata.authors) == 2:
            surname2 = self._get_surname(metadata.authors[1])
            return f"({surname} and {surname2} {year})"

        return f"({surname} {year})"

    def _format_chicago_authors(self, authors: List[str]) -> str:
        """Format authors in Chicago style."""
        if not authors:
            return "Unknown author."

        formatted = []
        for i, author in enumerate(authors):
            if i >= MAX_AUTHORS_BEFORE_ET_AL:
                formatted.append("et al")
                break
            # First author: Surname, Firstname
            # Others: Firstname Surname
            if i == 0:
                formatted.append(self._to_chicago_first_author(author))
            else:
                formatted.append(self._to_chicago_other_author(author))

        if len(formatted) == 1:
            return formatted[0] + "."
        elif len(formatted) == 2:
            return f"{formatted[0]}, and {formatted[1]}."

        return ", ".join(formatted[:-1]) + ", and " + formatted[-1] + "."

    def _to_chicago_first_author(self, author: str) -> str:
        """Format first author: Surname, Firstname."""
        author = author.strip()

        if ',' in author:
            return author  # Already in "Surname, Firstname" format

        parts = author.split()
        if len(parts) == 1:
            return parts[0]
        surname = parts[-1]
        given = ' '.join(parts[:-1])
        return f"{surname}, {given}"

    def _to_chicago_other_author(self, author: str) -> str:
        """Format subsequent authors: Firstname Surname."""
        author = author.strip()

        if ',' in author:
            parts = author.split(',', 1)
            surname = parts[0].strip()
            given = parts[1].strip() if len(parts) > 1 else ""
            return f"{given} {surname}".strip()

        return author  # Already in "Firstname Surname" format

    def _get_surname(self, author: str) -> str:
        """Extract surname from author name."""
        author = author.strip()
        if ',' in author:
            return author.split(',')[0].strip()
        parts = author.split()
        return parts[-1] if parts else "Unknown"


class CitationFormatter:
    """
    Main citation formatter that delegates to style-specific formatters.

    Usage:
        formatter = CitationFormatter(CitationStyle.VANCOUVER)
        ref = formatter.format_reference(metadata, number=1)
        inline = formatter.format_inline_citation(metadata, number=1)
    """

    _formatters = {
        CitationStyle.VANCOUVER: VancouverFormatter,
        CitationStyle.APA: APAFormatter,
        CitationStyle.HARVARD: HarvardFormatter,
        CitationStyle.CHICAGO: ChicagoFormatter,
    }

    def __init__(self, style: CitationStyle = CitationStyle.VANCOUVER) -> None:
        """
        Initialize formatter with specified style.

        Args:
            style: Citation style to use
        """
        self._style = style
        self._formatter = self._formatters[style]()

    @property
    def style(self) -> CitationStyle:
        """Get current citation style."""
        return self._style

    @style.setter
    def style(self, new_style: CitationStyle) -> None:
        """Set citation style."""
        self._style = new_style
        self._formatter = self._formatters[new_style]()

    def format_reference(
        self,
        metadata: DocumentMetadata,
        number: Optional[int] = None
    ) -> str:
        """
        Format a single reference.

        Args:
            metadata: Document metadata
            number: Reference number (for numbered styles like Vancouver)

        Returns:
            Formatted reference string
        """
        return self._formatter.format_reference(metadata, number)

    def format_inline_citation(
        self,
        metadata: DocumentMetadata,
        number: Optional[int] = None
    ) -> str:
        """
        Format an inline citation.

        Args:
            metadata: Document metadata
            number: Reference number (for numbered styles)

        Returns:
            Formatted inline citation
        """
        return self._formatter.format_inline_citation(metadata, number)

    def format_reference_list(
        self,
        references: List[FormattedReference]
    ) -> str:
        """
        Format a complete reference list.

        Args:
            references: List of FormattedReference objects

        Returns:
            Complete reference list as markdown
        """
        lines = ["", "---", "", "## References", ""]

        for ref in references:
            lines.append(ref.formatted_text)
            lines.append("")

        return "\n".join(lines)

    @classmethod
    def get_available_styles(cls) -> List[CitationStyle]:
        """Get list of available citation styles."""
        return list(cls._formatters.keys())

    @classmethod
    def get_style_description(cls, style: CitationStyle) -> str:
        """Get description of a citation style."""
        descriptions = {
            CitationStyle.VANCOUVER: "Vancouver (numbered, common in medical journals)",
            CitationStyle.APA: "APA (Author-Date, common in psychology and social sciences)",
            CitationStyle.HARVARD: "Harvard (Author-Date variant)",
            CitationStyle.CHICAGO: "Chicago (Author-Date, common in humanities)",
        }
        return descriptions.get(style, str(style.value))
