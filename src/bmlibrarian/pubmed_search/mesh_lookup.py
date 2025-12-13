"""
MeSH (Medical Subject Headings) lookup and validation service.

This module provides functionality to validate MeSH terms suggested by the LLM
against the official NCBI MeSH vocabulary, expand terms with synonyms and
narrower terms, and cache results for performance.

The module now supports local PostgreSQL database lookup (mesh schema) with
automatic fallback to NLM's public API when local data is unavailable.

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

    # Check if local database is available
    print(f"Local DB: {lookup.is_local_db_available()}")
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

    Uses the local PostgreSQL mesh database when available, with automatic
    fallback to NCBI's MeSH API. Results are cached in SQLite for performance.

    The lookup order is:
    1. Local PostgreSQL database (mesh schema) - if available
    2. SQLite cache - for previously looked up terms
    3. NLM API - for terms not in local DB or cache
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
        use_local_db: bool = True,
    ) -> None:
        """
        Initialize MeSH lookup service.

        Args:
            cache_dir: Directory for cache database (default: ~/.bmlibrarian/cache/)
            cache_ttl_days: Days before cache entries expire
            email: Email for NCBI API (recommended)
            api_key: NCBI API key for higher rate limits
            use_local_db: Whether to check local PostgreSQL database first
        """
        self.cache_ttl_days = cache_ttl_days
        self.email = email
        self.api_key = api_key
        self.request_delay = REQUEST_DELAY_WITHOUT_KEY if not api_key else 0.1
        self.use_local_db = use_local_db

        # Set up cache directory
        if cache_dir is None:
            cache_dir = Path.home() / ".bmlibrarian" / "cache"
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.cache_path = self.cache_dir / MESH_CACHE_FILENAME
        self._init_cache()

        # Initialize local database connection
        self._db_manager = None
        self._local_db_available = False
        if use_local_db:
            self._check_local_db()

        db_status = "available" if self._local_db_available else "unavailable"
        logger.info(
            f"MeSH lookup initialized: local_db={db_status}, cache={self.cache_path}"
        )

    def _check_local_db(self) -> None:
        """Check if local PostgreSQL mesh database is available."""
        try:
            from bmlibrarian.database import get_db_manager

            self._db_manager = get_db_manager()

            # Check if mesh schema exists and has data
            with self._db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT EXISTS (
                            SELECT 1 FROM information_schema.schemata
                            WHERE schema_name = 'mesh'
                        )
                        """
                    )
                    schema_exists = cur.fetchone()[0]

                    if schema_exists:
                        cur.execute("SELECT COUNT(*) FROM mesh.descriptors")
                        count = cur.fetchone()[0]
                        self._local_db_available = count > 0
                        if self._local_db_available:
                            logger.debug(f"Local MeSH database: {count:,} descriptors")
                    else:
                        logger.debug("MeSH schema not found in database")

        except Exception as e:
            logger.debug(f"Local MeSH database not available: {e}")
            self._local_db_available = False

    def is_local_db_available(self) -> bool:
        """
        Check if local PostgreSQL mesh database is available.

        Returns:
            True if local database has MeSH data
        """
        return self._local_db_available

    def _lookup_local_db(self, term: str) -> Optional[MeSHTerm]:
        """
        Look up a term in the local PostgreSQL database.

        Args:
            term: Term to look up

        Returns:
            MeSHTerm if found, None otherwise
        """
        if not self._local_db_available or self._db_manager is None:
            return None

        try:
            with self._db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT * FROM mesh.lookup_term(%s)",
                        (term,),
                    )
                    rows = cur.fetchall()

                    if not rows:
                        return None

                    # Use first result (exact match prioritized by the function)
                    row = rows[0]
                    descriptor_ui = row[0]
                    descriptor_name = row[1]
                    scope_note = row[5]

                    # Get entry terms
                    cur.execute(
                        "SELECT term_text FROM mesh.get_entry_terms(%s)",
                        (descriptor_ui,),
                    )
                    entry_terms = [r[0] for r in cur.fetchall()]

                    # Get tree numbers
                    cur.execute(
                        """
                        SELECT tree_number FROM mesh.tree_numbers tn
                        JOIN mesh.descriptors d ON tn.descriptor_id = d.id
                        WHERE d.descriptor_ui = %s
                        """,
                        (descriptor_ui,),
                    )
                    tree_numbers = [r[0] for r in cur.fetchall()]

                    return MeSHTerm(
                        descriptor_ui=descriptor_ui,
                        descriptor_name=descriptor_name,
                        tree_numbers=tree_numbers,
                        entry_terms=entry_terms,
                        scope_note=scope_note,
                        is_valid=True,
                    )

        except Exception as e:
            logger.warning(f"Local database lookup failed for '{term}': {e}")
            return None

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

    # Default headers for API requests (NLM requires proper User-Agent)
    _DEFAULT_HEADERS: Dict[str, str] = {
        "User-Agent": "BMLibrarian/1.0 (https://github.com/hherb/bmlibrarian; Python requests)",
        "Accept": "application/json",
    }

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
                response = requests.get(
                    url,
                    params=params,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                    headers=self._DEFAULT_HEADERS,
                )
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
        get its descriptor UI. Uses multiple search strategies for robustness.

        Args:
            term: Term to look up

        Returns:
            MeSHTerm if found, None otherwise
        """
        # Strategy 1: Try exact match search in mesh database
        # Use the term directly without field tags for MeSH database search
        params = {
            "db": "mesh",
            "term": f'"{term}"',
            "retmode": "json",
            "retmax": 5,
        }

        if self.email:
            params["email"] = self.email
        if self.api_key:
            params["api_key"] = self.api_key

        response = self._make_request(ESEARCH_URL, params)
        if response:
            try:
                data = response.json()
                result = data.get("esearchresult", {})
                id_list = result.get("idlist", [])

                if id_list:
                    # Found a match - format descriptor UI
                    descriptor_ui = f"D{id_list[0]}" if not id_list[0].startswith("D") else id_list[0]

                    return MeSHTerm(
                        descriptor_ui=descriptor_ui,
                        descriptor_name=term,
                        is_valid=True,
                    )
            except (json.JSONDecodeError, KeyError) as e:
                logger.debug(f"Error parsing MeSH esearch response: {e}")

        # Strategy 2: Try NLM MeSH lookup API for descriptor matching
        mesh_result = self._lookup_via_nlm_mesh_api(term)
        if mesh_result:
            return mesh_result

        # Strategy 3: Try as entry term (synonym) with broader search
        return self._lookup_as_entry_term(term)

    def _lookup_via_nlm_mesh_api(self, term: str) -> Optional[MeSHTerm]:
        """
        Look up a MeSH term via NLM MeSH Browser API.

        This API is specifically designed for MeSH term lookup and is more
        reliable for validating descriptor names.

        Args:
            term: Term to look up

        Returns:
            MeSHTerm if found, None otherwise
        """
        # Use the MeSH lookup/descriptor endpoint
        params = {
            "label": term,
            "match": "exact",
            "limit": 5,
        }

        response = self._make_request(MESH_BROWSER_API_URL, params)
        if not response:
            # Try contains match if exact fails
            params["match"] = "contains"
            response = self._make_request(MESH_BROWSER_API_URL, params)

        if not response:
            return None

        try:
            data = response.json()

            # Response is a list of matching descriptors
            if isinstance(data, list) and len(data) > 0:
                # Find exact match if possible
                for item in data:
                    label = item.get("label", "")
                    if label.lower() == term.lower():
                        resource = item.get("resource", "")
                        # Extract descriptor UI from resource URI
                        descriptor_ui = resource.split("/")[-1] if "/" in resource else ""
                        return MeSHTerm(
                            descriptor_ui=descriptor_ui,
                            descriptor_name=label,
                            is_valid=True,
                        )

                # If no exact match, use first result
                first = data[0]
                resource = first.get("resource", "")
                descriptor_ui = resource.split("/")[-1] if "/" in resource else ""
                label = first.get("label", term)

                return MeSHTerm(
                    descriptor_ui=descriptor_ui,
                    descriptor_name=label,
                    is_valid=True,
                )

        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.debug(f"Error parsing NLM MeSH API response: {e}")

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

        Lookup order:
        1. Local PostgreSQL database (mesh schema) - if available
        2. SQLite cache - for previously looked up terms
        3. NLM API - for terms not in local DB or cache

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

        # 1. Check local PostgreSQL database first (fastest)
        if self.use_local_db and self._local_db_available:
            result = self._lookup_local_db(normalized)
            if result is not None:
                logger.debug(f"MeSH local DB hit: {normalized} -> {result.descriptor_name}")
                return result

        # 2. Check SQLite cache
        if use_cache:
            cached = self._get_from_cache(normalized)
            if cached is not None:
                logger.debug(f"MeSH cache hit: {normalized} -> valid={cached.is_valid}")
                return cached

        # 3. Look up via API
        logger.debug(f"MeSH API lookup: {normalized}")
        result = self._lookup_via_esearch(normalized)

        if result is None:
            result = MeSHTerm(
                descriptor_ui="",
                descriptor_name=normalized,
                is_valid=False,
            )

        # Cache the API result
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

    def cleanup_expired_cache(self) -> int:
        """
        Remove expired cache entries and return count deleted.

        This is an alias for clear_expired_cache() for API consistency.

        Returns:
            Number of entries deleted
        """
        return self.clear_expired_cache()

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
