"""
Thesaurus Query Expander for Medical Term Expansion.

This module provides functionality to expand medical terms using the thesaurus schema,
enabling improved search recall through synonym, abbreviation, and hierarchical term expansion.
"""

import logging
import re
from typing import List, Set, Dict, Optional, Tuple
from dataclasses import dataclass

import psycopg
from psycopg.rows import dict_row

logger = logging.getLogger(__name__)


@dataclass
class TermExpansion:
    """
    Represents an expansion of a medical term.

    Attributes:
        original_term: The input term that was expanded
        all_variants: List of all term variants (synonyms, abbreviations, etc.)
        preferred_term: The canonical/preferred term for the concept
        concept_ids: List of concept IDs for this term (can be multiple for ambiguous terms)
        expansion_type: Type of expansion performed ('exact', 'partial', 'none')
    """
    original_term: str
    all_variants: List[str]
    preferred_term: Optional[str]
    concept_ids: List[int]
    expansion_type: str


class ThesaurusExpander:
    """
    Expands medical terms using the thesaurus database schema.

    Provides methods for term expansion, synonym lookup, and query enhancement
    for improved biomedical literature search recall.
    """

    def __init__(
        self,
        min_term_length: int = 2,
        max_expansions_per_term: int = 10,
        include_broader_terms: bool = False,
        include_narrower_terms: bool = False
    ):
        """
        Initialize the ThesaurusExpander.

        Args:
            min_term_length: Minimum term length to consider for expansion (default: 2)
            max_expansions_per_term: Maximum number of expansions per term (default: 10)
            include_broader_terms: Whether to include broader hierarchical terms (default: False)
            include_narrower_terms: Whether to include narrower hierarchical terms (default: False)
        """
        self.min_term_length = min_term_length
        self.max_expansions_per_term = max_expansions_per_term
        self.include_broader_terms = include_broader_terms
        self.include_narrower_terms = include_narrower_terms

        # Cache for term expansions to avoid repeated database queries
        self._expansion_cache: Dict[str, TermExpansion] = {}

    def _get_connection(self) -> psycopg.Connection:
        """
        Get a database connection using DatabaseManager.

        Returns:
            psycopg.Connection instance

        Raises:
            RuntimeError: If connection cannot be established
        """
        # Always use DatabaseManager (golden rule #5)
        try:
            from ..database import DatabaseManager
            db = DatabaseManager()
            return db.get_connection()
        except Exception as e:
            raise RuntimeError(f"Failed to get database connection: {e}")

    def expand_term(self, term: str, use_cache: bool = True) -> TermExpansion:
        """
        Expand a single medical term to all its variants.

        Args:
            term: The term to expand
            use_cache: Whether to use cached results (default: True)

        Returns:
            TermExpansion object with all variants
        """
        # Normalize term for cache lookup
        normalized_term = term.strip().lower()

        # Check cache
        if use_cache and normalized_term in self._expansion_cache:
            return self._expansion_cache[normalized_term]

        # Skip very short terms
        if len(normalized_term) < self.min_term_length:
            expansion = TermExpansion(
                original_term=term,
                all_variants=[term],
                preferred_term=None,
                concept_ids=[],
                expansion_type='none'
            )
            self._expansion_cache[normalized_term] = expansion
            return expansion

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    # Use thesaurus.expand_term() function
                    cur.execute(
                        """
                        SELECT
                            term,
                            term_type,
                            preferred_term,
                            concept_id,
                            is_input_term
                        FROM thesaurus.expand_term(%s)
                        LIMIT %s
                        """,
                        (term, self.max_expansions_per_term)
                    )

                    results = cur.fetchall()

                    if not results:
                        # No expansion found
                        expansion = TermExpansion(
                            original_term=term,
                            all_variants=[term],
                            preferred_term=None,
                            concept_ids=[],
                            expansion_type='none'
                        )
                    else:
                        # Extract all variants and metadata
                        all_variants = [row['term'] for row in results]
                        preferred_term = results[0]['preferred_term']
                        concept_ids = list(set(row['concept_id'] for row in results))

                        # Optionally add hierarchical terms
                        if self.include_broader_terms:
                            broader_terms = self._get_broader_terms(term, cur)
                            all_variants.extend(broader_terms)

                        if self.include_narrower_terms:
                            narrower_terms = self._get_narrower_terms(term, cur)
                            all_variants.extend(narrower_terms)

                        # Remove duplicates while preserving order
                        seen = set()
                        unique_variants = []
                        for variant in all_variants:
                            variant_lower = variant.lower()
                            if variant_lower not in seen:
                                seen.add(variant_lower)
                                unique_variants.append(variant)

                        expansion = TermExpansion(
                            original_term=term,
                            all_variants=unique_variants[:self.max_expansions_per_term],
                            preferred_term=preferred_term,
                            concept_ids=concept_ids,
                            expansion_type='exact'
                        )

                    # Cache the result
                    if use_cache:
                        self._expansion_cache[normalized_term] = expansion

                    return expansion

        except Exception as e:
            logger.warning(f"Failed to expand term '{term}': {e}")
            # Return minimal expansion on error
            expansion = TermExpansion(
                original_term=term,
                all_variants=[term],
                preferred_term=None,
                concept_ids=[],
                expansion_type='none'
            )
            return expansion

    def _get_broader_terms(self, term: str, cursor: psycopg.Cursor) -> List[str]:
        """Get broader hierarchical terms."""
        try:
            cursor.execute(
                "SELECT broader_term FROM thesaurus.get_broader_terms(%s)",
                (term,)
            )
            return [row['broader_term'] for row in cursor.fetchall()]
        except Exception as e:
            logger.debug(f"Failed to get broader terms for '{term}': {e}")
            return []

    def _get_narrower_terms(self, term: str, cursor: psycopg.Cursor) -> List[str]:
        """Get narrower hierarchical terms."""
        try:
            cursor.execute(
                "SELECT narrower_term FROM thesaurus.get_narrower_terms(%s)",
                (term,)
            )
            return [row['narrower_term'] for row in cursor.fetchall()]
        except Exception as e:
            logger.debug(f"Failed to get narrower terms for '{term}': {e}")
            return []

    def expand_query(
        self,
        ts_query: str,
        expand_or_groups: bool = True,
        expand_and_groups: bool = True
    ) -> str:
        """
        Expand a PostgreSQL to_tsquery string with term variants.

        Args:
            ts_query: Original to_tsquery string
            expand_or_groups: Whether to expand terms in OR groups (default: True)
            expand_and_groups: Whether to expand terms in AND groups (default: True)

        Returns:
            Expanded to_tsquery string with additional term variants

        Example:
            Input:  "aspirin & (heart | cardiac)"
            Output: "(aspirin | ASA | acetylsalicylic acid) & ((heart | cardiac) | cardiovascular)"
        """
        if not ts_query or not ts_query.strip():
            return ts_query

        # Extract individual terms from the query
        terms = self._extract_terms(ts_query)

        # Build expansion map
        expansion_map: Dict[str, List[str]] = {}
        for term in terms:
            expansion = self.expand_term(term)
            if expansion.expansion_type != 'none' and len(expansion.all_variants) > 1:
                expansion_map[term.lower()] = expansion.all_variants

        if not expansion_map:
            # No expansions found, return original
            return ts_query

        # Apply expansions to the query
        expanded_query = self._apply_expansions(
            ts_query,
            expansion_map,
            expand_or_groups,
            expand_and_groups
        )

        return expanded_query

    def _extract_terms(self, ts_query: str) -> Set[str]:
        """
        Extract individual terms from a to_tsquery string.

        Handles quoted phrases, parentheses, and operators.
        """
        # Remove operators and parentheses, split on whitespace
        # This is a simple extraction - could be made more sophisticated

        # Remove parentheses
        query_no_parens = re.sub(r'[()]', ' ', ts_query)

        # Remove operators but preserve quoted phrases
        # Match either quoted phrases or individual words
        pattern = r"'[^']+'|\b\w+\b"
        matches = re.findall(pattern, query_no_parens)

        terms = set()
        for match in matches:
            # Remove quotes if present
            term = match.strip("'").strip()

            # Skip operators and very short terms
            if term.lower() not in ('&', '|', '!', 'and', 'or', 'not') and len(term) >= self.min_term_length:
                terms.add(term)

        return terms

    def _apply_expansions(
        self,
        ts_query: str,
        expansion_map: Dict[str, List[str]],
        expand_or_groups: bool,
        expand_and_groups: bool
    ) -> str:
        """
        Apply term expansions to the query string.

        This is a simplified implementation that replaces individual terms.
        A more sophisticated version would parse the query structure properly.
        """
        expanded = ts_query

        for original_term, variants in expansion_map.items():
            # Create OR group of all variants
            # Quote multi-word phrases
            quoted_variants = []
            for variant in variants:
                if ' ' in variant or '-' in variant:
                    quoted_variants.append(f"'{variant}'")
                else:
                    quoted_variants.append(variant)

            expansion_group = ' | '.join(quoted_variants)

            # Replace the original term with the expansion group
            # Use word boundaries to avoid partial matches
            pattern = r'\b' + re.escape(original_term) + r'\b'
            replacement = f"({expansion_group})"

            expanded = re.sub(pattern, replacement, expanded, flags=re.IGNORECASE)

        return expanded

    def clear_cache(self) -> None:
        """Clear the term expansion cache."""
        self._expansion_cache.clear()

    def get_cache_size(self) -> int:
        """Get the current cache size."""
        return len(self._expansion_cache)


def expand_query_terms(
    ts_query: str,
    max_expansions_per_term: int = 10
) -> str:
    """
    Convenience function to expand a query string with thesaurus terms.

    Args:
        ts_query: Original to_tsquery string
        max_expansions_per_term: Maximum expansions per term (default: 10)

    Returns:
        Expanded query string

    Example:
        >>> expand_query_terms("aspirin & heart attack")
        "(aspirin | ASA | acetylsalicylic acid) & (heart attack | myocardial infarction | MI)"
    """
    expander = ThesaurusExpander(
        max_expansions_per_term=max_expansions_per_term
    )
    return expander.expand_query(ts_query)
