"""
Thesaurus Query Expander for Medical Term Expansion.

This module provides functionality to expand medical terms using the thesaurus schema,
enabling improved search recall through synonym, abbreviation, and hierarchical term expansion.
"""

import logging
import re
import time
from typing import List, Set, Dict, Optional, Tuple
from dataclasses import dataclass, field

import psycopg
from psycopg.rows import dict_row

logger = logging.getLogger(__name__)

# Constants (golden rule #2: no magic numbers)
DEFAULT_MIN_TERM_LENGTH = 2
DEFAULT_MAX_EXPANSIONS_PER_TERM = 10
DEFAULT_CACHE_MAX_SIZE = 1000
DEFAULT_CACHE_TTL_SECONDS = 3600  # 1 hour
DEFAULT_MAX_QUERY_TERMS = 50  # Maximum terms to expand in a single query


@dataclass
class CacheEntry:
    """A cache entry with TTL tracking."""
    expansion: 'TermExpansion'
    timestamp: float = field(default_factory=time.time)


@dataclass
class ExpansionStats:
    """
    Statistics for tracking expansion effectiveness.

    Attributes:
        cache_hits: Number of cache hits
        cache_misses: Number of cache misses
        expansions_performed: Total number of expansions performed
        terms_expanded: Number of terms with successful expansions (not 'none')
        queries_processed: Number of queries processed
        queries_limited: Number of queries that exceeded term limits
    """
    cache_hits: int = 0
    cache_misses: int = 0
    expansions_performed: int = 0
    terms_expanded: int = 0
    queries_processed: int = 0
    queries_limited: int = 0


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
        min_term_length: int = DEFAULT_MIN_TERM_LENGTH,
        max_expansions_per_term: int = DEFAULT_MAX_EXPANSIONS_PER_TERM,
        include_broader_terms: bool = False,
        include_narrower_terms: bool = False,
        cache_max_size: int = DEFAULT_CACHE_MAX_SIZE,
        cache_ttl: int = DEFAULT_CACHE_TTL_SECONDS,
        max_query_terms: int = DEFAULT_MAX_QUERY_TERMS
    ):
        """
        Initialize the ThesaurusExpander.

        Args:
            min_term_length: Minimum term length to consider for expansion (default: 2)
            max_expansions_per_term: Maximum number of expansions per term (default: 10)
            include_broader_terms: Whether to include broader hierarchical terms (default: False)
            include_narrower_terms: Whether to include narrower hierarchical terms (default: False)
            cache_max_size: Maximum number of entries in the expansion cache (default: 1000)
            cache_ttl: Time-to-live for cache entries in seconds (default: 3600)
            max_query_terms: Maximum number of terms to expand in a single query (default: 50)
        """
        self.min_term_length = min_term_length
        self.max_expansions_per_term = max_expansions_per_term
        self.include_broader_terms = include_broader_terms
        self.include_narrower_terms = include_narrower_terms
        self.cache_max_size = cache_max_size
        self.cache_ttl = cache_ttl
        self.max_query_terms = max_query_terms

        # Cache for term expansions with TTL tracking
        self._expansion_cache: Dict[str, CacheEntry] = {}

        # Statistics for tracking expansion effectiveness
        self._stats = ExpansionStats()

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

    def _is_cache_entry_valid(self, entry: CacheEntry) -> bool:
        """
        Check if a cache entry is still valid based on TTL.

        Args:
            entry: The cache entry to check

        Returns:
            True if entry is still valid, False if expired
        """
        return (time.time() - entry.timestamp) < self.cache_ttl

    def _evict_expired_entries(self) -> None:
        """Remove expired entries from the cache."""
        current_time = time.time()
        expired_keys = [
            key for key, entry in self._expansion_cache.items()
            if (current_time - entry.timestamp) >= self.cache_ttl
        ]
        for key in expired_keys:
            del self._expansion_cache[key]

    def _evict_oldest_entries(self, count: int = 1) -> None:
        """
        Evict the oldest entries from the cache.

        Args:
            count: Number of entries to evict
        """
        if count <= 0 or not self._expansion_cache:
            return

        # Sort by timestamp and remove oldest
        sorted_entries = sorted(
            self._expansion_cache.items(),
            key=lambda x: x[1].timestamp
        )
        for key, _ in sorted_entries[:count]:
            del self._expansion_cache[key]

    def _cache_expansion(self, normalized_term: str, expansion: TermExpansion) -> None:
        """
        Store an expansion in the cache with max size enforcement.

        Args:
            normalized_term: The normalized term key
            expansion: The expansion to cache
        """
        # Evict expired entries periodically (every 100 additions)
        if len(self._expansion_cache) % 100 == 0:
            self._evict_expired_entries()

        # Evict oldest entries if at max size
        if len(self._expansion_cache) >= self.cache_max_size:
            # Evict 10% of entries to avoid frequent evictions
            evict_count = max(1, self.cache_max_size // 10)
            self._evict_oldest_entries(evict_count)

        self._expansion_cache[normalized_term] = CacheEntry(expansion=expansion)

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

        # Check cache with TTL validation
        if use_cache and normalized_term in self._expansion_cache:
            entry = self._expansion_cache[normalized_term]
            if self._is_cache_entry_valid(entry):
                self._stats.cache_hits += 1
                return entry.expansion
            else:
                # Entry expired, remove it
                del self._expansion_cache[normalized_term]

        self._stats.cache_misses += 1
        self._stats.expansions_performed += 1

        # Skip very short terms
        if len(normalized_term) < self.min_term_length:
            expansion = TermExpansion(
                original_term=term,
                all_variants=[term],
                preferred_term=None,
                concept_ids=[],
                expansion_type='none'
            )
            self._cache_expansion(normalized_term, expansion)
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
                        self._cache_expansion(normalized_term, expansion)

                    # Track successful expansions
                    if expansion.expansion_type != 'none':
                        self._stats.terms_expanded += 1

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
        self._stats.queries_processed += 1

        if not ts_query or not ts_query.strip():
            return ts_query

        # Extract individual terms from the query
        terms = self._extract_terms(ts_query)

        # Check query complexity limit
        if len(terms) > self.max_query_terms:
            logger.warning(
                f"Query too complex for expansion: {len(terms)} terms exceeds "
                f"limit of {self.max_query_terms}"
            )
            self._stats.queries_limited += 1
            return ts_query

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

        Handles:
        - Quoted phrases (single and double quotes)
        - Escaped quotes within phrases
        - Hyphenated medical terms (e.g., beta-blocker, anti-inflammatory)
        - Unicode characters in medical terms (e.g., α-blocker, β-carotene)
        - Parentheses and operators
        """
        # Remove parentheses
        query_no_parens = re.sub(r'[()]', ' ', ts_query)

        terms: Set[str] = set()

        # First, extract quoted phrases (handling both single and double quotes)
        # Handle escaped quotes within phrases: 'phrase with \' escaped'
        # Pattern for single-quoted phrases with optional escaped quotes
        single_quoted_pattern = r"'(?:[^'\\]|\\.)*'"
        # Pattern for double-quoted phrases with optional escaped quotes
        double_quoted_pattern = r'"(?:[^"\\]|\\.)*"'

        # Extract all quoted phrases first
        quoted_phrases = re.findall(
            f'{single_quoted_pattern}|{double_quoted_pattern}',
            query_no_parens
        )

        for phrase in quoted_phrases:
            # Remove outer quotes and unescape inner quotes
            term = phrase[1:-1]  # Remove first and last quote
            term = term.replace("\\'", "'").replace('\\"', '"')
            term = term.strip()
            if len(term) >= self.min_term_length:
                terms.add(term)

        # Remove quoted phrases from query for further processing
        remaining = re.sub(
            f'{single_quoted_pattern}|{double_quoted_pattern}',
            ' ',
            query_no_parens
        )

        # Extract individual terms including:
        # - Hyphenated terms (alpha-blocker, anti-inflammatory)
        # - Unicode word characters (\w with Unicode flag)
        # - Terms with numeric suffixes (vitamin-B12, COVID-19)
        # Pattern: word characters, hyphens, and Unicode letters/numbers
        # Using \w with re.UNICODE handles Greek letters, accented chars, etc.
        term_pattern = r'[\w\u0080-\uFFFF][\w\u0080-\uFFFF\-]*[\w\u0080-\uFFFF]|[\w\u0080-\uFFFF]+'
        matches = re.findall(term_pattern, remaining, re.UNICODE)

        # Operators to skip
        operators = {'&', '|', '!', 'and', 'or', 'not'}

        for match in matches:
            term = match.strip()
            # Skip operators and very short terms
            if term.lower() not in operators and len(term) >= self.min_term_length:
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
        """Get the current cache size (excluding expired entries)."""
        # Count only non-expired entries
        current_time = time.time()
        return sum(
            1 for entry in self._expansion_cache.values()
            if (current_time - entry.timestamp) < self.cache_ttl
        )

    def get_expansion_stats(self) -> Dict[str, int]:
        """
        Get statistics about expansion effectiveness.

        Returns:
            Dictionary with expansion statistics:
            - cache_hits: Number of cache hits
            - cache_misses: Number of cache misses
            - cache_hit_rate: Percentage of cache hits (0-100)
            - expansions_performed: Total expansions attempted
            - terms_expanded: Terms with successful expansions
            - expansion_rate: Percentage of successful expansions (0-100)
            - queries_processed: Total queries processed
            - queries_limited: Queries exceeding term limits
            - current_cache_size: Current number of cached entries
        """
        total_lookups = self._stats.cache_hits + self._stats.cache_misses
        cache_hit_rate = (
            int(self._stats.cache_hits * 100 / total_lookups)
            if total_lookups > 0 else 0
        )

        expansion_rate = (
            int(self._stats.terms_expanded * 100 / self._stats.expansions_performed)
            if self._stats.expansions_performed > 0 else 0
        )

        return {
            'cache_hits': self._stats.cache_hits,
            'cache_misses': self._stats.cache_misses,
            'cache_hit_rate': cache_hit_rate,
            'expansions_performed': self._stats.expansions_performed,
            'terms_expanded': self._stats.terms_expanded,
            'expansion_rate': expansion_rate,
            'queries_processed': self._stats.queries_processed,
            'queries_limited': self._stats.queries_limited,
            'current_cache_size': self.get_cache_size()
        }

    def reset_stats(self) -> None:
        """Reset expansion statistics to zero."""
        self._stats = ExpansionStats()


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
