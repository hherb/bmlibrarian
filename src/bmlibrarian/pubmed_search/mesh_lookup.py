"""
MeSH (Medical Subject Headings) lookup and validation service.

This module provides functionality to validate MeSH terms suggested by the LLM
against the official NCBI MeSH vocabulary, expand terms with synonyms and
narrower terms, and cache results for performance.

Example usage:
    from bmlibrarian.pubmed_search import MeSHLookup

    lookup = MeSHLookup()

    # Validate a single term
    result = lookup.validate_term("Cardiovascular Diseases")
    if result.is_valid:
        print(f"Valid: {result.descriptor_name}")
        print(f"Entry terms: {result.entry_terms}")

    # Validate multiple terms
    results = lookup.validate_terms(["Exercise", "Invalid Term", "Diabetes"])
    valid_terms = [r for r in results if r.is_valid]
"""

import logging
import sqlite3
import time
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
import requests

from .constants import (
    MESH_BROWSER_API_URL,
    ESEARCH_URL,
    REQUEST_TIMEOUT_SECONDS,
    MAX_RETRIES,
    INITIAL_RETRY_DELAY_SECONDS,
    RETRY_BACKOFF_MULTIPLIER,
    MESH_CACHE_FILENAME,
    MESH_CACHE_TTL_DAYS,
    REQUEST_DELAY_WITHOUT_KEY,
)
from .data_types import MeSHTerm

logger = logging.getLogger(__name__)


class MeSHLookup:
    """
    Service for validating and expanding MeSH terms.

    Uses NCBI's MeSH database to validate terms suggested by the LLM,
    find official descriptor names, and retrieve synonyms (entry terms)
    for query expansion.

    Includes SQLite caching to minimize API calls and improve performance.
    """

    # SQL for cache database schema
    _CACHE_SCHEMA = """
        CREATE TABLE IF NOT EXISTS mesh_terms (
            descriptor_ui TEXT PRIMARY KEY,
            descriptor_name TEXT NOT NULL,
            tree_numbers TEXT,
            entry_terms TEXT,
            scope_note TEXT,
            cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS mesh_name_lookup (
            search_name TEXT PRIMARY KEY,
            descriptor_ui TEXT,
            is_valid INTEGER DEFAULT 1,
            cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_mesh_cached_at ON mesh_terms(cached_at);
        CREATE INDEX IF NOT EXISTS idx_lookup_cached_at ON mesh_name_lookup(cached_at);
    """

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        cache_ttl_days: int = MESH_CACHE_TTL_DAYS,
        email: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> None:
        """
        Initialize MeSH lookup service.

        Args:
            cache_dir: Directory for cache database (default: ~/.bmlibrarian/cache/)
            cache_ttl_days: Days before cache entries expire
            email: Email for NCBI API (recommended)
            api_key: NCBI API key for higher rate limits
        """
        self.cache_ttl_days = cache_ttl_days
        self.email = email
        self.api_key = api_key
        self.request_delay = REQUEST_DELAY_WITHOUT_KEY if not api_key else 0.1

        # Set up cache directory
        if cache_dir is None:
            cache_dir = Path.home() / ".bmlibrarian" / "cache"
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.cache_path = self.cache_dir / MESH_CACHE_FILENAME
        self._init_cache()

        logger.info(f"MeSH lookup initialized with cache at {self.cache_path}")

    def _init_cache(self) -> None:
        """Initialize the SQLite cache database."""
        with sqlite3.connect(self.cache_path) as conn:
            conn.executescript(self._CACHE_SCHEMA)

    def _get_cache_connection(self) -> sqlite3.Connection:
        """Get a connection to the cache database."""
        conn = sqlite3.connect(self.cache_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _is_cache_valid(self, cached_at: str) -> bool:
        """
        Check if a cached entry is still valid.

        Args:
            cached_at: ISO format timestamp of when entry was cached

        Returns:
            True if cache entry is still valid
        """
        try:
            cached_time = datetime.fromisoformat(cached_at)
            expiry = cached_time + timedelta(days=self.cache_ttl_days)
            return datetime.now() < expiry
        except (ValueError, TypeError):
            return False

    def _get_from_cache(self, search_name: str) -> Optional[MeSHTerm]:
        """
        Look up a term in the cache.

        Args:
            search_name: Term to look up (case-insensitive)

        Returns:
            MeSHTerm if found and valid, None otherwise
        """
        normalized = search_name.lower().strip()

        with self._get_cache_connection() as conn:
            # First check the name lookup table
            cursor = conn.execute(
                "SELECT descriptor_ui, is_valid, cached_at FROM mesh_name_lookup WHERE search_name = ?",
                (normalized,),
            )
            lookup_row = cursor.fetchone()

            if lookup_row is None:
                return None

            if not self._is_cache_valid(lookup_row["cached_at"]):
                # Cache expired, delete and return None
                conn.execute(
                    "DELETE FROM mesh_name_lookup WHERE search_name = ?",
                    (normalized,),
                )
                return None

            if not lookup_row["is_valid"]:
                # Cached as invalid term
                return MeSHTerm(
                    descriptor_ui="",
                    descriptor_name=search_name,
                    is_valid=False,
                )

            # Look up the full term data
            descriptor_ui = lookup_row["descriptor_ui"]
            cursor = conn.execute(
                "SELECT * FROM mesh_terms WHERE descriptor_ui = ?",
                (descriptor_ui,),
            )
            term_row = cursor.fetchone()

            if term_row is None:
                return None

            return MeSHTerm(
                descriptor_ui=term_row["descriptor_ui"],
                descriptor_name=term_row["descriptor_name"],
                tree_numbers=json.loads(term_row["tree_numbers"] or "[]"),
                entry_terms=json.loads(term_row["entry_terms"] or "[]"),
                scope_note=term_row["scope_note"],
                is_valid=True,
            )

    def _save_to_cache(self, search_name: str, term: MeSHTerm) -> None:
        """
        Save a term to the cache.

        Args:
            search_name: Original search term
            term: MeSHTerm result to cache
        """
        normalized = search_name.lower().strip()

        with self._get_cache_connection() as conn:
            if term.is_valid:
                # Save full term data
                conn.execute(
                    """
                    INSERT OR REPLACE INTO mesh_terms
                    (descriptor_ui, descriptor_name, tree_numbers, entry_terms, scope_note, cached_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        term.descriptor_ui,
                        term.descriptor_name,
                        json.dumps(term.tree_numbers),
                        json.dumps(term.entry_terms),
                        term.scope_note,
                        datetime.now().isoformat(),
                    ),
                )

                # Save lookup mapping
                conn.execute(
                    """
                    INSERT OR REPLACE INTO mesh_name_lookup
                    (search_name, descriptor_ui, is_valid, cached_at)
                    VALUES (?, ?, 1, ?)
                    """,
                    (normalized, term.descriptor_ui, datetime.now().isoformat()),
                )
            else:
                # Cache as invalid
                conn.execute(
                    """
                    INSERT OR REPLACE INTO mesh_name_lookup
                    (search_name, descriptor_ui, is_valid, cached_at)
                    VALUES (?, NULL, 0, ?)
                    """,
                    (normalized, datetime.now().isoformat()),
                )

    def _make_request(
        self,
        url: str,
        params: Dict[str, Any],
        retries: int = MAX_RETRIES,
    ) -> Optional[requests.Response]:
        """
        Make an HTTP request with retry logic.

        Args:
            url: API endpoint URL
            params: Query parameters
            retries: Number of retry attempts

        Returns:
            Response object or None if failed
        """
        delay = INITIAL_RETRY_DELAY_SECONDS

        for attempt in range(retries):
            try:
                time.sleep(self.request_delay)  # Rate limiting
                response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
                response.raise_for_status()
                return response
            except requests.exceptions.RequestException as e:
                logger.warning(f"MeSH API request failed (attempt {attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:
                    time.sleep(delay)
                    delay *= RETRY_BACKOFF_MULTIPLIER
                else:
                    logger.error(f"MeSH API request failed after {retries} attempts")
                    return None

        return None

    def _lookup_via_esearch(self, term: str) -> Optional[MeSHTerm]:
        """
        Look up a MeSH term via NCBI E-utilities esearch.

        This method searches the MeSH database to validate a term and
        get its descriptor UI.

        Args:
            term: Term to look up

        Returns:
            MeSHTerm if found, None otherwise
        """
        params = {
            "db": "mesh",
            "term": f'"{term}"[MeSH Terms]',
            "retmode": "json",
            "retmax": 1,
        }

        if self.email:
            params["email"] = self.email
        if self.api_key:
            params["api_key"] = self.api_key

        response = self._make_request(ESEARCH_URL, params)
        if not response:
            return None

        try:
            data = response.json()
            result = data.get("esearchresult", {})
            id_list = result.get("idlist", [])

            if not id_list:
                # Term not found - try as entry term
                return self._lookup_as_entry_term(term)

            # Found a descriptor UI
            descriptor_ui = f"D{id_list[0]}" if not id_list[0].startswith("D") else id_list[0]

            # For now, return minimal info - could enhance with efetch
            return MeSHTerm(
                descriptor_ui=descriptor_ui,
                descriptor_name=term,
                is_valid=True,
            )

        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Error parsing MeSH esearch response: {e}")
            return None

    def _lookup_as_entry_term(self, term: str) -> Optional[MeSHTerm]:
        """
        Look up a term that might be an entry term (synonym).

        Args:
            term: Term to look up

        Returns:
            MeSHTerm with the official descriptor name, or None
        """
        # Search more broadly
        params = {
            "db": "mesh",
            "term": term,
            "retmode": "json",
            "retmax": 5,
        }

        if self.email:
            params["email"] = self.email
        if self.api_key:
            params["api_key"] = self.api_key

        response = self._make_request(ESEARCH_URL, params)
        if not response:
            return None

        try:
            data = response.json()
            result = data.get("esearchresult", {})
            id_list = result.get("idlist", [])

            if not id_list:
                return None

            # Found potential matches
            descriptor_ui = f"D{id_list[0]}" if not id_list[0].startswith("D") else id_list[0]

            return MeSHTerm(
                descriptor_ui=descriptor_ui,
                descriptor_name=term,  # Will need to fetch official name
                entry_terms=[term],
                is_valid=True,
            )

        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Error parsing MeSH entry term response: {e}")
            return None

    def validate_term(self, term: str, use_cache: bool = True) -> MeSHTerm:
        """
        Validate a single MeSH term.

        Checks if the term exists in the official MeSH vocabulary.
        If the term is an entry term (synonym), returns the official
        descriptor name.

        Args:
            term: MeSH term to validate
            use_cache: Whether to use cached results

        Returns:
            MeSHTerm with validation result
        """
        if not term or not term.strip():
            return MeSHTerm(
                descriptor_ui="",
                descriptor_name=term or "",
                is_valid=False,
            )

        normalized = term.strip()

        # Check cache first
        if use_cache:
            cached = self._get_from_cache(normalized)
            if cached is not None:
                logger.debug(f"MeSH cache hit: {normalized} -> valid={cached.is_valid}")
                return cached

        # Look up via API
        logger.debug(f"MeSH lookup: {normalized}")
        result = self._lookup_via_esearch(normalized)

        if result is None:
            result = MeSHTerm(
                descriptor_ui="",
                descriptor_name=normalized,
                is_valid=False,
            )

        # Cache the result
        if use_cache:
            self._save_to_cache(normalized, result)

        return result

    def validate_terms(
        self,
        terms: List[str],
        use_cache: bool = True,
    ) -> List[MeSHTerm]:
        """
        Validate multiple MeSH terms.

        Args:
            terms: List of MeSH terms to validate
            use_cache: Whether to use cached results

        Returns:
            List of MeSHTerm results in same order as input
        """
        results = []
        for term in terms:
            result = self.validate_term(term, use_cache=use_cache)
            results.append(result)
        return results

    def expand_term(self, term: str) -> List[str]:
        """
        Expand a MeSH term to include entry terms (synonyms).

        Args:
            term: MeSH term to expand

        Returns:
            List of terms including original and all synonyms
        """
        mesh_term = self.validate_term(term)
        if not mesh_term.is_valid:
            return [term]

        expanded = [mesh_term.descriptor_name]
        expanded.extend(mesh_term.entry_terms)
        return list(set(expanded))  # Remove duplicates

    def suggest_mesh_terms(self, keyword: str) -> List[str]:
        """
        Suggest MeSH terms for a keyword.

        Searches the MeSH database for terms matching the keyword
        and returns the official descriptor names.

        Args:
            keyword: Keyword to search for

        Returns:
            List of matching MeSH descriptor names
        """
        params = {
            "db": "mesh",
            "term": keyword,
            "retmode": "json",
            "retmax": 10,
        }

        if self.email:
            params["email"] = self.email
        if self.api_key:
            params["api_key"] = self.api_key

        response = self._make_request(ESEARCH_URL, params)
        if not response:
            return []

        try:
            data = response.json()
            translation_stack = data.get("esearchresult", {}).get("translationstack", [])

            suggestions = []
            for item in translation_stack:
                if isinstance(item, dict) and "term" in item:
                    # Extract the MeSH term from the translation
                    term = item["term"]
                    if "[MeSH Terms]" in term:
                        mesh_name = term.replace("[MeSH Terms]", "").strip().strip('"')
                        if mesh_name:
                            suggestions.append(mesh_name)

            return suggestions[:10]  # Limit to top 10

        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Error parsing MeSH suggestions: {e}")
            return []

    def clear_cache(self) -> int:
        """
        Clear all cached MeSH data.

        Returns:
            Number of entries cleared
        """
        with self._get_cache_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM mesh_terms")
            count = cursor.fetchone()[0]

            conn.execute("DELETE FROM mesh_terms")
            conn.execute("DELETE FROM mesh_name_lookup")

            logger.info(f"Cleared {count} entries from MeSH cache")
            return count

    def clear_expired_cache(self) -> int:
        """
        Clear only expired cache entries.

        Returns:
            Number of entries cleared
        """
        expiry_date = (datetime.now() - timedelta(days=self.cache_ttl_days)).isoformat()

        with self._get_cache_connection() as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM mesh_terms WHERE cached_at < ?",
                (expiry_date,),
            )
            count = cursor.fetchone()[0]

            conn.execute("DELETE FROM mesh_terms WHERE cached_at < ?", (expiry_date,))
            conn.execute("DELETE FROM mesh_name_lookup WHERE cached_at < ?", (expiry_date,))

            logger.info(f"Cleared {count} expired entries from MeSH cache")
            return count

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the cache.

        Returns:
            Dictionary with cache statistics
        """
        with self._get_cache_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM mesh_terms")
            term_count = cursor.fetchone()[0]

            cursor = conn.execute("SELECT COUNT(*) FROM mesh_name_lookup")
            lookup_count = cursor.fetchone()[0]

            cursor = conn.execute("SELECT COUNT(*) FROM mesh_name_lookup WHERE is_valid = 0")
            invalid_count = cursor.fetchone()[0]

            expiry_date = (datetime.now() - timedelta(days=self.cache_ttl_days)).isoformat()
            cursor = conn.execute(
                "SELECT COUNT(*) FROM mesh_terms WHERE cached_at < ?",
                (expiry_date,),
            )
            expired_count = cursor.fetchone()[0]

        return {
            "cached_terms": term_count,
            "cached_lookups": lookup_count,
            "invalid_terms_cached": invalid_count,
            "expired_entries": expired_count,
            "cache_path": str(self.cache_path),
            "cache_ttl_days": self.cache_ttl_days,
        }
