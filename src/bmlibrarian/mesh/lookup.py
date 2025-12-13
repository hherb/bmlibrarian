"""
MeSH lookup service with local database and API fallback.

This module provides a unified interface for MeSH term lookup that:
1. First checks the local PostgreSQL database (mesh schema)
2. Falls back to NLM's public MeSH API if local data unavailable
3. Caches API results in a local SQLite database

Example usage:
    from bmlibrarian.mesh import MeSHService

    service = MeSHService()

    # Lookup a term
    result = service.lookup("heart attack")
    if result.found:
        print(f"Found: {result.descriptor_name}")
        print(f"Source: {result.source}")

    # Expand to all synonyms
    terms = service.expand("MI")

    # Search by partial match
    results = service.search("cardio", limit=10)
"""

import json
import logging
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
import requests

from .data_types import (
    MeSHSource,
    MeSHResult,
    MeSHDescriptorInfo,
    MeSHTermInfo,
    MeSHTreeInfo,
    MeSHSearchResult,
)

logger = logging.getLogger(__name__)

# Import shared constants from pubmed_search to avoid duplication (golden rule #2)
try:
    from bmlibrarian.pubmed_search.constants import (
        MESH_BROWSER_API_URL,
        ESEARCH_URL,
        EFETCH_URL,
        REQUEST_TIMEOUT_SECONDS,
        MAX_RETRIES,
        INITIAL_RETRY_DELAY_SECONDS,
        RETRY_BACKOFF_MULTIPLIER,
        REQUEST_DELAY_WITHOUT_KEY,
        MESH_CACHE_TTL_DAYS as CACHE_TTL_DAYS,
        MESH_DESCRIPTOR_PREFIX,
    )
except ImportError:
    # Fallback constants if pubmed_search not available
    MESH_BROWSER_API_URL = "https://id.nlm.nih.gov/mesh/lookup/descriptor"
    ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    REQUEST_TIMEOUT_SECONDS = 30
    MAX_RETRIES = 3
    INITIAL_RETRY_DELAY_SECONDS = 1
    RETRY_BACKOFF_MULTIPLIER = 2
    REQUEST_DELAY_WITHOUT_KEY = 0.34
    CACHE_TTL_DAYS = 30
    MESH_DESCRIPTOR_PREFIX = "D"

# Cache settings (specific to this module)
DEFAULT_CACHE_DIR = Path.home() / ".bmlibrarian" / "cache"
CACHE_FILENAME = "mesh_api_cache.db"


class MeSHService:
    """
    Unified MeSH lookup service with local database and API fallback.

    Provides methods for:
    - Term lookup (exact match)
    - Term expansion (get all synonyms)
    - Term search (partial match)
    - Broader/narrower term navigation

    Automatically uses local PostgreSQL database when available,
    falls back to NLM API when needed, and caches API results.
    """

    def __init__(
        self,
        use_local_db: bool = True,
        use_api_fallback: bool = True,
        cache_dir: Optional[Path] = None,
        cache_ttl_days: int = CACHE_TTL_DAYS,
        email: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> None:
        """
        Initialize MeSH service.

        Args:
            use_local_db: Whether to check local PostgreSQL database
            use_api_fallback: Whether to fall back to NLM API
            cache_dir: Directory for API cache (default: ~/.bmlibrarian/cache)
            cache_ttl_days: Days before cache entries expire
            email: Email for NCBI API (recommended)
            api_key: NCBI API key for higher rate limits
        """
        self.use_local_db = use_local_db
        self.use_api_fallback = use_api_fallback
        self.cache_ttl_days = cache_ttl_days
        self.email = email
        self.api_key = api_key
        self.request_delay = REQUEST_DELAY_WITHOUT_KEY if not api_key else 0.1

        # Initialize local database connection
        self._db_manager = None
        self._local_db_available = False
        if use_local_db:
            self._check_local_db()

        # Initialize API cache
        if cache_dir is None:
            cache_dir = DEFAULT_CACHE_DIR
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_path = self.cache_dir / CACHE_FILENAME
        self._init_cache()

        logger.info(
            f"MeSH service initialized: "
            f"local_db={'available' if self._local_db_available else 'unavailable'}, "
            f"api_fallback={use_api_fallback}"
        )

    def _check_local_db(self) -> None:
        """Check if local PostgreSQL database is available and has MeSH data."""
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
                            logger.info(f"Local MeSH database available: {count:,} descriptors")
                    else:
                        logger.info("MeSH schema not found in database")

        except Exception as e:
            logger.warning(f"Could not connect to local database: {e}")
            self._local_db_available = False

    def _init_cache(self) -> None:
        """Initialize the SQLite API cache database."""
        with sqlite3.connect(self.cache_path) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS mesh_cache (
                    search_term TEXT PRIMARY KEY,
                    result_json TEXT NOT NULL,
                    source TEXT NOT NULL,
                    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_mesh_cache_cached_at
                    ON mesh_cache(cached_at);
                """
            )

    def _get_from_cache(self, search_term: str) -> Optional[MeSHResult]:
        """
        Get a cached result if valid.

        Args:
            search_term: Term to look up

        Returns:
            Cached MeSHResult or None
        """
        normalized = search_term.lower().strip()

        with sqlite3.connect(self.cache_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT result_json, cached_at FROM mesh_cache WHERE search_term = ?",
                (normalized,),
            )
            row = cursor.fetchone()

            if row is None:
                return None

            # Check if cache is expired
            cached_at = datetime.fromisoformat(row["cached_at"])
            if datetime.now() - cached_at > timedelta(days=self.cache_ttl_days):
                conn.execute("DELETE FROM mesh_cache WHERE search_term = ?", (normalized,))
                return None

            try:
                data = json.loads(row["result_json"])
                return MeSHResult(
                    found=data["found"],
                    source=MeSHSource.CACHE,
                    searched_term=search_term,
                    descriptor_ui=data.get("descriptor_ui", ""),
                    descriptor_name=data.get("descriptor_name", ""),
                    scope_note=data.get("scope_note"),
                    entry_terms=data.get("entry_terms", []),
                    tree_numbers=data.get("tree_numbers", []),
                    is_valid=data.get("is_valid", False),
                )
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Invalid cache entry for {search_term}: {e}")
                return None

    def _save_to_cache(self, result: MeSHResult) -> None:
        """
        Save a result to cache.

        Thread safety note: SQLite handles concurrent writes using database-level
        locking. The default timeout (5 seconds) allows waiting for locks. For
        high-concurrency scenarios with many writers, consider:
        1. Using WAL mode: PRAGMA journal_mode=WAL
        2. Increasing timeout: sqlite3.connect(..., timeout=30)
        3. Using a connection pool for very heavy workloads

        Current usage pattern (single writer, multiple readers during lookup
        operations) is safe with default SQLite behavior.

        Args:
            result: MeSHResult to cache
        """
        normalized = result.searched_term.lower().strip()

        data = {
            "found": result.found,
            "descriptor_ui": result.descriptor_ui,
            "descriptor_name": result.descriptor_name,
            "scope_note": result.scope_note,
            "entry_terms": result.entry_terms,
            "tree_numbers": result.tree_numbers,
            "is_valid": result.is_valid,
        }

        with sqlite3.connect(self.cache_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO mesh_cache (search_term, result_json, source, cached_at)
                VALUES (?, ?, ?, ?)
                """,
                (normalized, json.dumps(data), result.source.value, datetime.now().isoformat()),
            )

    def _lookup_local(self, term: str) -> Optional[MeSHResult]:
        """
        Look up a term in the local PostgreSQL database.

        Note on SQL security: This method uses parameterized queries (%s placeholders)
        with psycopg's built-in parameter binding. The stored function mesh.lookup_term()
        receives the term as a properly escaped parameter, not as raw SQL. The function
        itself uses PostgreSQL's type system and internal query execution which prevents
        SQL injection. See: https://www.psycopg.org/psycopg3/docs/basic/params.html

        Args:
            term: Term to look up

        Returns:
            MeSHResult or None if not found
        """
        if not self._local_db_available or self._db_manager is None:
            return None

        try:
            with self._db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    # Parameterized query - term is bound as a parameter, not interpolated
                    cur.execute(
                        "SELECT * FROM mesh.lookup_term(%s)",
                        (term,),
                    )
                    rows = cur.fetchall()

                    if not rows:
                        return None

                    # Use first result (exact match prioritized)
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

                    return MeSHResult(
                        found=True,
                        source=MeSHSource.LOCAL_DATABASE,
                        searched_term=term,
                        descriptor_ui=descriptor_ui,
                        descriptor_name=descriptor_name,
                        scope_note=scope_note,
                        entry_terms=entry_terms,
                        tree_numbers=tree_numbers,
                        is_valid=True,
                    )

        except Exception as e:
            logger.warning(f"Local database lookup failed: {e}")
            return None

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
        headers = {
            "User-Agent": "BMLibrarian/1.0 (https://github.com/hherb/bmlibrarian; Python requests)",
            "Accept": "application/json",
        }

        for attempt in range(retries):
            try:
                time.sleep(self.request_delay)
                response = requests.get(
                    url,
                    params=params,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                    headers=headers,
                )
                response.raise_for_status()
                return response
            except requests.exceptions.RequestException as e:
                logger.warning(f"API request failed (attempt {attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:
                    time.sleep(delay)
                    delay *= RETRY_BACKOFF_MULTIPLIER
                else:
                    logger.error(f"API request failed after {retries} attempts")
                    return None

        return None

    def _lookup_api(self, term: str) -> Optional[MeSHResult]:
        """
        Look up a term via NLM MeSH API.

        Args:
            term: Term to look up

        Returns:
            MeSHResult or None if not found
        """
        if not self.use_api_fallback:
            return None

        # Try NLM MeSH Browser API first
        params = {
            "label": term,
            "match": "exact",
            "limit": 5,
        }

        response = self._make_request(MESH_BROWSER_API_URL, params)

        # Try contains match if exact fails
        if response and response.status_code == 200:
            data = response.json()
            if not data:
                params["match"] = "contains"
                response = self._make_request(MESH_BROWSER_API_URL, params)
                if response:
                    data = response.json()
        elif response is None:
            return None
        else:
            data = []

        if not data:
            # Try NCBI E-utilities as fallback
            return self._lookup_via_esearch(term)

        try:
            # Find exact match if possible
            best_match = None
            for item in data:
                label = item.get("label", "")
                if label.lower() == term.lower():
                    best_match = item
                    break

            if best_match is None and data:
                best_match = data[0]

            if best_match:
                resource = best_match.get("resource", "")
                descriptor_ui = resource.split("/")[-1] if "/" in resource else ""
                descriptor_name = best_match.get("label", term)

                return MeSHResult(
                    found=True,
                    source=MeSHSource.NLM_API,
                    searched_term=term,
                    descriptor_ui=descriptor_ui,
                    descriptor_name=descriptor_name,
                    is_valid=True,
                )

        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.debug(f"Error parsing NLM MeSH API response: {e}")

        return None

    def _lookup_via_esearch(self, term: str) -> Optional[MeSHResult]:
        """
        Look up a term via NCBI E-utilities esearch.

        Args:
            term: Term to look up

        Returns:
            MeSHResult or None if not found
        """
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
        if not response:
            return None

        try:
            data = response.json()
            result = data.get("esearchresult", {})
            id_list = result.get("idlist", [])

            if id_list:
                # Format descriptor UI with standard prefix
                descriptor_ui = (
                    f"{MESH_DESCRIPTOR_PREFIX}{id_list[0]}"
                    if not id_list[0].startswith(MESH_DESCRIPTOR_PREFIX)
                    else id_list[0]
                )

                return MeSHResult(
                    found=True,
                    source=MeSHSource.NLM_API,
                    searched_term=term,
                    descriptor_ui=descriptor_ui,
                    descriptor_name=term,  # Name not available from esearch
                    is_valid=True,
                )

        except (json.JSONDecodeError, KeyError) as e:
            logger.debug(f"Error parsing esearch response: {e}")

        return None

    def lookup(self, term: str, use_cache: bool = True) -> MeSHResult:
        """
        Look up a MeSH term.

        Checks sources in order:
        1. Local PostgreSQL database (if available)
        2. Local SQLite cache (if use_cache=True)
        3. NLM API (if use_api_fallback=True)

        Args:
            term: MeSH term to look up
            use_cache: Whether to use/update cache

        Returns:
            MeSHResult with lookup results
        """
        if not term or not term.strip():
            return MeSHResult.not_found("")

        normalized_term = term.strip()

        # 1. Try local database first
        if self.use_local_db and self._local_db_available:
            result = self._lookup_local(normalized_term)
            if result:
                logger.debug(f"MeSH lookup: {term} -> found in local DB")
                return result

        # 2. Try cache
        if use_cache:
            result = self._get_from_cache(normalized_term)
            if result:
                logger.debug(f"MeSH lookup: {term} -> found in cache")
                return result

        # 3. Try API
        if self.use_api_fallback:
            result = self._lookup_api(normalized_term)
            if result:
                logger.debug(f"MeSH lookup: {term} -> found via API")
                if use_cache:
                    self._save_to_cache(result)
                return result

        # Not found
        logger.debug(f"MeSH lookup: {term} -> not found")
        result = MeSHResult.not_found(normalized_term)
        if use_cache:
            self._save_to_cache(result)
        return result

    def expand(self, term: str) -> List[str]:
        """
        Expand a MeSH term to all its synonyms/entry terms.

        Args:
            term: MeSH term to expand

        Returns:
            List of all terms including the original
        """
        if not term or not term.strip():
            return [term] if term else []

        # Try local database first
        if self.use_local_db and self._local_db_available:
            try:
                with self._db_manager.get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT term_text FROM mesh.expand_term(%s)",
                            (term,),
                        )
                        terms = [row[0] for row in cur.fetchall()]
                        if terms:
                            return terms
            except Exception as e:
                logger.warning(f"Local database expansion failed: {e}")

        # Fall back to lookup and use entry terms
        result = self.lookup(term)
        if result.found:
            all_terms = [result.descriptor_name] + result.entry_terms
            return list(set(all_terms))

        return [term]

    def search(self, query: str, limit: int = 20) -> List[MeSHSearchResult]:
        """
        Search MeSH by partial match.

        Args:
            query: Search query
            limit: Maximum results to return

        Returns:
            List of MeSHSearchResult objects
        """
        if not query or not query.strip():
            return []

        # Try local database first
        if self.use_local_db and self._local_db_available:
            try:
                with self._db_manager.get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT * FROM mesh.search(%s, %s)",
                            (query, limit),
                        )
                        return [
                            MeSHSearchResult(
                                descriptor_ui=row[0],
                                descriptor_name=row[1],
                                matched_term=row[2],
                                match_type=row[3],
                                score=row[4] or 0.0,
                            )
                            for row in cur.fetchall()
                        ]
            except Exception as e:
                logger.warning(f"Local database search failed: {e}")

        # Fall back to API search
        if self.use_api_fallback:
            params = {
                "label": query,
                "match": "contains",
                "limit": limit,
            }
            response = self._make_request(MESH_BROWSER_API_URL, params)
            if response:
                try:
                    data = response.json()
                    return [
                        MeSHSearchResult(
                            descriptor_ui=item.get("resource", "").split("/")[-1],
                            descriptor_name=item.get("label", ""),
                            matched_term=item.get("label", ""),
                            match_type="api_search",
                            score=0.0,
                        )
                        for item in data[:limit]
                    ]
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(f"Error parsing search response: {e}")

        return []

    def get_broader_terms(self, descriptor_ui: str) -> List[MeSHSearchResult]:
        """
        Get broader (parent) terms for a descriptor.

        Args:
            descriptor_ui: MeSH descriptor UI

        Returns:
            List of parent descriptors
        """
        if self.use_local_db and self._local_db_available:
            try:
                with self._db_manager.get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT * FROM mesh.get_broader_terms(%s)",
                            (descriptor_ui,),
                        )
                        return [
                            MeSHSearchResult(
                                descriptor_ui=row[0],
                                descriptor_name=row[1],
                                matched_term=row[1],
                                match_type="broader",
                            )
                            for row in cur.fetchall()
                        ]
            except Exception as e:
                logger.warning(f"Could not get broader terms: {e}")

        return []

    def get_narrower_terms(self, descriptor_ui: str) -> List[MeSHSearchResult]:
        """
        Get narrower (child) terms for a descriptor.

        Args:
            descriptor_ui: MeSH descriptor UI

        Returns:
            List of child descriptors
        """
        if self.use_local_db and self._local_db_available:
            try:
                with self._db_manager.get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT * FROM mesh.get_narrower_terms(%s)",
                            (descriptor_ui,),
                        )
                        return [
                            MeSHSearchResult(
                                descriptor_ui=row[0],
                                descriptor_name=row[1],
                                matched_term=row[1],
                                match_type="narrower",
                            )
                            for row in cur.fetchall()
                        ]
            except Exception as e:
                logger.warning(f"Could not get narrower terms: {e}")

        return []

    def validate_term(self, term: str) -> MeSHResult:
        """
        Validate a MeSH term (alias for lookup).

        Args:
            term: Term to validate

        Returns:
            MeSHResult with validation results
        """
        return self.lookup(term)

    def validate_terms(self, terms: List[str]) -> List[MeSHResult]:
        """
        Validate multiple MeSH terms.

        Args:
            terms: List of terms to validate

        Returns:
            List of MeSHResult objects in same order
        """
        return [self.lookup(term) for term in terms]

    def is_local_db_available(self) -> bool:
        """Check if local database is available."""
        return self._local_db_available

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get MeSH service statistics.

        Returns:
            Dictionary with statistics
        """
        stats = {
            "local_db_available": self._local_db_available,
            "api_fallback_enabled": self.use_api_fallback,
            "cache_path": str(self.cache_path),
            "cache_ttl_days": self.cache_ttl_days,
        }

        # Get local DB stats if available
        if self._local_db_available and self._db_manager:
            try:
                with self._db_manager.get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT * FROM mesh.get_statistics()")
                        for row in cur.fetchall():
                            stats[f"local_{row[0]}"] = row[1]
            except Exception:
                pass

        # Get cache stats
        try:
            with sqlite3.connect(self.cache_path) as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM mesh_cache")
                stats["cache_entries"] = cursor.fetchone()[0]
        except Exception:
            pass

        return stats

    def clear_cache(self) -> int:
        """
        Clear all cached API results.

        Returns:
            Number of entries cleared
        """
        with sqlite3.connect(self.cache_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM mesh_cache")
            count = cursor.fetchone()[0]
            conn.execute("DELETE FROM mesh_cache")
            logger.info(f"Cleared {count} entries from MeSH API cache")
            return count
