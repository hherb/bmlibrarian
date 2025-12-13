"""
Type-safe dataclasses for MeSH module.

This module defines all data structures used throughout the MeSH system,
ensuring type safety and clear interfaces between components.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List


class MeSHSource(Enum):
    """Source of MeSH lookup result."""

    LOCAL_DATABASE = "local_database"
    NLM_API = "nlm_api"
    CACHE = "cache"
    NOT_FOUND = "not_found"


@dataclass
class MeSHTermInfo:
    """
    Information about a MeSH term variant.

    Attributes:
        term_text: The term string (e.g., "MI", "Heart Attack")
        is_preferred: Whether this is the preferred term for its concept
        lexical_tag: Type of term (ABB, SYN, TRD, etc.)
        concept_name: Name of the parent concept
    """

    term_text: str
    is_preferred: bool = False
    lexical_tag: Optional[str] = None
    concept_name: Optional[str] = None


@dataclass
class MeSHTreeInfo:
    """
    Information about a MeSH tree number (hierarchy position).

    Attributes:
        tree_number: The tree number (e.g., "C14.280.647.500")
        tree_level: Depth in hierarchy (1 = top level)
        parent_tree_number: Parent tree number if exists
        parent_descriptor_ui: Parent descriptor UI
        parent_descriptor_name: Parent descriptor name
    """

    tree_number: str
    tree_level: int
    parent_tree_number: Optional[str] = None
    parent_descriptor_ui: Optional[str] = None
    parent_descriptor_name: Optional[str] = None


@dataclass
class MeSHDescriptorInfo:
    """
    Complete information about a MeSH descriptor.

    Attributes:
        descriptor_ui: Unique identifier (e.g., "D009203")
        descriptor_name: Preferred/canonical name
        scope_note: Definition/description
        entry_terms: All term variants (synonyms, abbreviations, etc.)
        tree_numbers: Hierarchical tree positions
        tree_info: Detailed tree hierarchy information
    """

    descriptor_ui: str
    descriptor_name: str
    scope_note: Optional[str] = None
    entry_terms: List[str] = field(default_factory=list)
    tree_numbers: List[str] = field(default_factory=list)
    tree_info: List[MeSHTreeInfo] = field(default_factory=list)
    term_details: List[MeSHTermInfo] = field(default_factory=list)

    def get_abbreviations(self) -> List[str]:
        """Get all abbreviation terms."""
        return [
            t.term_text
            for t in self.term_details
            if t.lexical_tag in ("ABB", "ABX", "ACR")
        ]

    def get_synonyms(self) -> List[str]:
        """Get all synonym terms (excluding abbreviations)."""
        return [
            t.term_text
            for t in self.term_details
            if t.lexical_tag not in ("ABB", "ABX", "ACR")
            and not t.is_preferred
        ]


@dataclass
class MeSHSearchResult:
    """
    Result from a MeSH search operation.

    Attributes:
        descriptor_ui: MeSH descriptor UI
        descriptor_name: Preferred descriptor name
        matched_term: The term that matched the search
        match_type: Type of match (exact, prefix, partial)
        score: Relevance score
    """

    descriptor_ui: str
    descriptor_name: str
    matched_term: str
    match_type: str = "partial"
    score: float = 0.0


@dataclass
class MeSHResult:
    """
    Result of a MeSH term lookup operation.

    Attributes:
        found: Whether the term was found
        source: Where the result came from (local DB, API, cache)
        descriptor_ui: MeSH descriptor UI if found
        descriptor_name: Preferred descriptor name if found
        scope_note: Definition if available
        entry_terms: All term variants
        tree_numbers: Hierarchical tree positions
        searched_term: Original term that was searched
        is_valid: Whether term is a valid MeSH term
    """

    found: bool
    source: MeSHSource
    searched_term: str
    descriptor_ui: str = ""
    descriptor_name: str = ""
    scope_note: Optional[str] = None
    entry_terms: List[str] = field(default_factory=list)
    tree_numbers: List[str] = field(default_factory=list)
    is_valid: bool = False

    @classmethod
    def not_found(cls, searched_term: str) -> "MeSHResult":
        """Create a not-found result."""
        return cls(
            found=False,
            source=MeSHSource.NOT_FOUND,
            searched_term=searched_term,
            is_valid=False,
        )

    @classmethod
    def from_descriptor_info(
        cls,
        info: MeSHDescriptorInfo,
        searched_term: str,
        source: MeSHSource,
    ) -> "MeSHResult":
        """Create result from descriptor info."""
        return cls(
            found=True,
            source=source,
            searched_term=searched_term,
            descriptor_ui=info.descriptor_ui,
            descriptor_name=info.descriptor_name,
            scope_note=info.scope_note,
            entry_terms=info.entry_terms,
            tree_numbers=info.tree_numbers,
            is_valid=True,
        )

    def to_pubmed_syntax(self, explode: bool = True) -> str:
        """
        Convert to PubMed query syntax.

        Args:
            explode: If True, include narrower terms (default MeSH behavior)

        Returns:
            PubMed-formatted MeSH term query
        """
        if not self.is_valid or not self.descriptor_name:
            return ""

        if explode:
            return f'"{self.descriptor_name}"[MeSH Terms]'
        else:
            return f'"{self.descriptor_name}"[MeSH Terms:noexp]'
