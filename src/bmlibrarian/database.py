"""Database access layer for BMLibrarian with connection pooling."""

import os
import time
import logging
from contextlib import contextmanager
from typing import Dict, Generator, Optional, List, Union, cast, LiteralString, Any
from datetime import date

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get logger for database operations
logger = logging.getLogger('bmlibrarian.database')


class DatabaseManager:
    """Manages database connections and provides high-level API access."""
    
    # Class-level cache for source mappings shared across all instances
    _source_id_cache: Optional[Dict[int, str]] = None
    _source_ids: Optional[Dict[str, Union[int, List[int]]]] = None
    
    def __init__(self):
        """Initialize the database manager with connection pool."""
        self._pool: Optional[ConnectionPool] = None
        self._init_pool()
        self._cache_source_ids()
    
    def _init_pool(self):
        """Initialize the connection pool using environment variables."""
        # Get database configuration from environment
        db_config = {
            "host": os.getenv("POSTGRES_HOST", "localhost"),
            "port": os.getenv("POSTGRES_PORT", "5432"),
            "user": os.getenv("POSTGRES_USER"),
            "password": os.getenv("POSTGRES_PASSWORD"),
            "dbname": os.getenv("POSTGRES_DB", "knowledgebase")
        }
        
        # Validate required credentials
        if not db_config["user"] or not db_config["password"]:
            raise ValueError(
                "Database credentials not configured. Please set POSTGRES_USER and POSTGRES_PASSWORD environment variables."
            )
        
        # Create connection string
        conninfo = " ".join([f"{k}={v}" for k, v in db_config.items() if v])
        
        # Initialize connection pool
        self._pool = ConnectionPool(
            conninfo=conninfo,
            min_size=2,
            max_size=10,
            timeout=30
        )
        
        # Warm up the connection pool
        self._warmup_pool()
    
    def _warmup_pool(self):
        """Warm up the connection pool by establishing minimum connections."""
        try:
            if self._pool:
                # Test connections to ensure they're working and establish min_size connections
                with self._pool.connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT 1")
                        cur.fetchone()
        except Exception as e:
            # Log the error but don't fail initialization
            print(f"Warning: Connection pool warmup failed: {e}")
    
    def _cache_source_ids(self):
        """Cache source IDs for faster queries."""
        # Use class-level cache if already populated
        if DatabaseManager._source_id_cache is not None and DatabaseManager._source_ids is not None:
            return
        
        DatabaseManager._source_ids = {'others': []}
        DatabaseManager._source_id_cache = {}
        
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, name FROM sources")
                for source_id, name in cur.fetchall():
                    name_lower = name.lower()
                    if 'pubmed' in name_lower:
                        DatabaseManager._source_ids['pubmed'] = source_id
                        DatabaseManager._source_id_cache[source_id] = 'pubmed'
                    elif 'medrxiv' in name_lower:
                        DatabaseManager._source_ids['medrxiv'] = source_id
                        DatabaseManager._source_id_cache[source_id] = 'medrxiv'
                    else:
                        # Store other source IDs
                        if isinstance(DatabaseManager._source_ids['others'], list):
                            DatabaseManager._source_ids['others'].append(source_id)
                        DatabaseManager._source_id_cache[source_id] = 'others'
    
    @contextmanager
    def get_connection(self):
        """Get a database connection from the pool."""
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        
        with self._pool.connection() as conn:
            yield conn
    
    def refresh_source_cache(self):
        """Refresh the cached source IDs."""
        DatabaseManager._source_id_cache = None
        DatabaseManager._source_ids = None
        self._cache_source_ids()
    
    def get_cached_source_ids(self) -> Optional[Dict[str, Union[int, List[int]]]]:
        """Get the cached source IDs."""
        return DatabaseManager._source_ids
    
    def close(self):
        """Close the connection pool."""
        if self._pool:
            self._pool.close()
            self._pool = None


# Global database manager instance
_db_manager = None


def get_db_manager() -> DatabaseManager:
    """Get the global database manager instance."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager


def find_abstracts(
    ts_query_str: str,
    max_rows: int = 100,
    use_pubmed: bool = True,
    use_medrxiv: bool = True,
    use_others: bool = True,
    plain: bool = True,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    batch_size: int = 50,
    use_ranking: bool = False,
    offset: int = 0
) -> Generator[Dict, None, None]:
    """
    Find documents using PostgreSQL text search with optional date and source filtering.
    
    Args:
        ts_query_str: Text search query string
        max_rows: Maximum number of rows to return (0 = no limit)
        use_pubmed: Include PubMed sources
        use_medrxiv: Include medRxiv sources
        use_others: Include other sources
        plain: If True, use plainto_tsquery (simple text); if False, use to_tsquery (advanced syntax)
        from_date: Only include documents published on or after this date (inclusive)
        to_date: Only include documents published on or before this date (inclusive)
        batch_size: Number of rows to fetch in each database round trip (default: 50)
        use_ranking: If True, calculate and order by relevance ranking (default: False for speed)
        offset: Number of rows to skip before returning results (default: 0)
        
    Yields:
        Dict containing document information with keys:
        - id: Document ID
        - title: Document title
        - abstract: Document abstract (may be None/empty)
        - authors: List of authors
        - publication: Publication name
        - publication_date: Publication date
        - doi: DOI if available
        - pmid: PubMed ID (extracted from external_id)
        - url: Document URL
        - source_name: Source name
        - keywords: Document keywords
        - mesh_terms: MeSH terms
        
    Examples:
        Simple text search:
        >>> for doc in find_abstracts("covid vaccine", max_rows=10):
        ...     print(f"{doc['title']} - {doc['publication_date']}")
        
        Advanced query syntax:
        >>> for doc in find_abstracts("covid & vaccine", max_rows=10, plain=False):
        ...     print(f"{doc['title']} - {doc['publication_date']}")
        
        Date-filtered search:
        >>> from datetime import date
        >>> for doc in find_abstracts("covid", from_date=date(2020, 1, 1), to_date=date(2021, 12, 31)):
        ...     print(f"{doc['title']} - {doc['publication_date']}")
    """
    # Log query start
    start_time = time.time()
    logger.info(f"Starting document search: query='{ts_query_str[:100]}...', max_rows={max_rows}")
    
    db_manager = get_db_manager()
    
    # Build source ID filter using cached source IDs (much faster than JOINs)
    # Only filter by source if not all sources are enabled
    source_ids = []
    all_sources_enabled = use_pubmed and use_medrxiv and use_others
    
    # Log search parameters
    search_params = {
        'ts_query_str': ts_query_str,
        'max_rows': max_rows,
        'use_pubmed': use_pubmed,
        'use_medrxiv': use_medrxiv,
        'use_others': use_others,
        'plain': plain,
        'from_date': from_date.isoformat() if from_date else None,
        'to_date': to_date.isoformat() if to_date else None,
        'batch_size': batch_size,
        'use_ranking': use_ranking
    }
    
    logger.debug(f"Search parameters", extra={'structured_data': {
        'event_type': 'database_search_params',
        'parameters': search_params,
        'timestamp': time.time()
    }})
    
    if not all_sources_enabled and DatabaseManager._source_ids:
        if use_pubmed and 'pubmed' in DatabaseManager._source_ids:
            pubmed_id = DatabaseManager._source_ids['pubmed']
            source_ids.append(pubmed_id)
        
        if use_medrxiv and 'medrxiv' in DatabaseManager._source_ids:
            medrxiv_id = DatabaseManager._source_ids['medrxiv']
            source_ids.append(medrxiv_id)
        
        if use_others and 'others' in DatabaseManager._source_ids:
            others_ids = DatabaseManager._source_ids['others']
            if isinstance(others_ids, list):
                source_ids.extend(others_ids)
        
        # If no sources selected, return empty
        if not source_ids:
            return
    
    # Choose the appropriate tsquery function based on plain parameter
    if plain:
        tsquery_func = "plainto_tsquery"
    else:
        tsquery_func = "to_tsquery"
    
    # Build date filter conditions
    date_conditions = []
    date_params = []
    
    if from_date is not None:
        date_conditions.append("d.publication_date >= %s")
        date_params.append(from_date)
    
    if to_date is not None:
        date_conditions.append("d.publication_date <= %s")
        date_params.append(to_date)
    
    # Combine date conditions
    date_filter = ""
    if date_conditions:
        date_filter = "AND " + " AND ".join(date_conditions)
    
    # Build optimized query
    # Only add source filter if not all sources are enabled
    if all_sources_enabled:
        source_filter = ""
        source_id_placeholders = ""
    else:
        source_id_placeholders = ','.join(['%s'] * len(source_ids))
        source_filter = f"AND d.source_id IN ({source_id_placeholders})"
    
    # Build query with optional ranking
    # IMPORTANT: Always include d.id in ORDER BY to ensure stable ordering for OFFSET
    if use_ranking:
        base_query = f"""
        SELECT d.*, ts_rank_cd(d.search_vector, {tsquery_func}('english', %s)) AS rank_score
        FROM document d
        WHERE d.search_vector @@ {tsquery_func}('english', %s)
        {source_filter}
        {date_filter}
        ORDER BY rank_score DESC, d.publication_date DESC NULLS LAST, d.id ASC
        """
    else:
        base_query = f"""
        SELECT d.*
        FROM document d
        WHERE d.search_vector @@ {tsquery_func}('english', %s)
        {source_filter}
        {date_filter}
        ORDER BY d.publication_date DESC NULLS LAST, d.id ASC
        """
    
    # Add limit and offset if specified
    if max_rows > 0:
        query = base_query + f" LIMIT {max_rows}"
        if offset > 0:
            query += f" OFFSET {offset}"
    else:
        if offset > 0:
            query = base_query + f" OFFSET {offset}"
        else:
            query = base_query
    
    # Prepare query parameters based on ranking and filtering
    if use_ranking:
        # Ranking queries need tsquery twice (SELECT and WHERE)
        if all_sources_enabled:
            query_params = [ts_query_str, ts_query_str] + date_params
        else:
            query_params = [ts_query_str, ts_query_str] + source_ids + date_params
    else:
        # Non-ranking queries need tsquery only once (WHERE)
        if all_sources_enabled:
            query_params = [ts_query_str] + date_params
        else:
            query_params = [ts_query_str] + source_ids + date_params
    
    # Log the final query and parameters
    logger.info(f"Executing database query", extra={'structured_data': {
        'event_type': 'database_query_execution',
        'query': query,
        'parameter_count': len(query_params),
        'query_type': 'document_search',
        'timestamp': time.time()
    }})
    
    all_results = []
    total_rows = 0
    
    with db_manager.get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            # Set cursor arraysize for efficient batching
            cur.arraysize = batch_size
            
            # Execute the query with parameters
            query_start = time.time()
            cur.execute(cast(LiteralString, query), tuple(query_params))
            query_execution_time = (time.time() - query_start) * 1000  # Convert to milliseconds
            
            logger.info(f"Query executed in {query_execution_time:.2f}ms")
            
            while True:
                # Fetch a batch of rows
                batch_start = time.time()
                rows = cur.fetchmany(batch_size)
                if not rows:
                    break
                
                batch_time = (time.time() - batch_start) * 1000
                logger.debug(f"Fetched batch of {len(rows)} rows in {batch_time:.2f}ms")
                
                for row in rows:
                    # Add source name mapping using cached mappings
                    source_id = row['source_id']
                    row['source_name'] = DatabaseManager._source_id_cache.get(source_id, 'unknown') if DatabaseManager._source_id_cache else 'unknown'
                    
                    # Extract PMID from external_id if available
                    external_id = row.get('external_id', '')
                    pmid = None
                    if external_id and external_id.isdigit():
                        # Simple case: external_id is just a PMID number
                        pmid = external_id
                    elif external_id and 'pmid:' in external_id.lower():
                        # Handle cases like "PMID:12345678" or "pmid:12345678"
                        import re
                        pmid_match = re.search(r'pmid:(\d+)', external_id.lower())
                        if pmid_match:
                            pmid = pmid_match.group(1)
                    
                    # Add PMID to the row data
                    row['pmid'] = pmid
                    
                    # Ensure list fields are not None
                    for field in ['authors', 'keywords', 'mesh_terms', 'augmented_keywords', 'all_keywords']:
                        if row.get(field) is None:
                            row[field] = []
                    
                    # Convert date/datetime objects to strings for JSON serialization compatibility
                    date_fields = ['publication_date', 'added_date', 'updated_date', 'withdrawn_date']
                    for field in date_fields:
                        if field in row and row[field] is not None:
                            if hasattr(row[field], 'isoformat'):
                                row[field] = row[field].isoformat()
                            else:
                                row[field] = str(row[field])
                    
                    row_dict = dict(row)
                    all_results.append(row_dict)  # Store for logging
                    total_rows += 1
                    
                    yield row_dict
    
    # Log complete results and performance metrics
    total_time = (time.time() - start_time) * 1000
    
    logger.info(f"Document search completed: {total_rows} documents in {total_time:.2f}ms")
    
    # Log detailed results for full observability
    logger.debug("Complete search results", extra={'structured_data': {
        'event_type': 'database_search_results',
        'query': ts_query_str,
        'total_results': total_rows,
        'execution_time_ms': total_time,
        'query_execution_time_ms': query_execution_time,
        'results': all_results,  # Full result set for observability
        'timestamp': time.time()
    }})


def find_abstract_ids(
    ts_query_str: str,
    max_rows: int = 100,
    use_pubmed: bool = True,
    use_medrxiv: bool = True,
    use_others: bool = True,
    plain: bool = False,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    offset: int = 0
) -> set[int]:
    """
    Execute search and return ONLY document IDs (fast).

    This is much faster than find_abstracts() because:
    - No JOINs with authors table
    - No text field transfers
    - Returns set[int] for easy de-duplication

    Designed for multi-query workflows where document IDs are collected
    from multiple queries before fetching full documents.

    Args:
        ts_query_str: Text search query string
        max_rows: Maximum number of IDs to return
        use_pubmed: Include PubMed sources
        use_medrxiv: Include medRxiv sources
        use_others: Include other sources
        plain: If True, use plainto_tsquery; if False, use to_tsquery
        from_date: Only include documents published on or after this date
        to_date: Only include documents published on or before this date
        offset: Number of rows to skip before returning results

    Returns:
        Set of document IDs

    Example:
        >>> ids = find_abstract_ids("aspirin & heart", max_rows=100, plain=False)
        >>> print(f"Found {len(ids)} documents")
        Found 87 documents
    """
    logger.info(f"Searching for document IDs: query='{ts_query_str[:100]}...', max_rows={max_rows}")

    db_manager = get_db_manager()

    # Build source ID filter (same logic as find_abstracts)
    source_ids = []
    all_sources_enabled = use_pubmed and use_medrxiv and use_others

    if not all_sources_enabled and DatabaseManager._source_ids:
        if use_pubmed and 'pubmed' in DatabaseManager._source_ids:
            source_ids.append(DatabaseManager._source_ids['pubmed'])
        if use_medrxiv and 'medrxiv' in DatabaseManager._source_ids:
            source_ids.append(DatabaseManager._source_ids['medrxiv'])
        if use_others and 'others' in DatabaseManager._source_ids:
            source_ids.extend(DatabaseManager._source_ids['others'])

    # Build WHERE clause
    where_clauses = []
    params = []

    # Text search condition
    if plain:
        where_clauses.append("d.search_vector @@ plainto_tsquery('english', %s)")
    else:
        where_clauses.append("d.search_vector @@ to_tsquery('english', %s)")
    params.append(ts_query_str)

    # Source filtering
    if source_ids:
        where_clauses.append(f"d.source_id = ANY(%s)")
        params.append(source_ids)

    # Date filtering
    if from_date:
        where_clauses.append("d.publication_date >= %s")
        params.append(from_date)
    if to_date:
        where_clauses.append("d.publication_date <= %s")
        params.append(to_date)

    where_clause = " AND ".join(where_clauses)

    # Simple ID-only query - no JOINs, no text fields
    # Note: Must include publication_date in SELECT when using it in ORDER BY with DISTINCT
    sql = f"""
        SELECT DISTINCT d.id, d.publication_date
        FROM document d
        WHERE {where_clause}
        ORDER BY d.publication_date DESC NULLS LAST
        LIMIT %s OFFSET %s
    """
    params.extend([max_rows, offset])

    # Execute and collect IDs
    document_ids = set()
    start_time = time.time()

    with db_manager.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            for row in cur.fetchall():
                document_ids.add(row[0])  # Still only collect the ID, ignore publication_date

    elapsed = time.time() - start_time
    logger.info(f"Found {len(document_ids)} document IDs in {elapsed:.2f}s")

    return document_ids


def fetch_documents_by_ids(
    document_ids: set[int],
    batch_size: int = 50
) -> list[Dict[str, Any]]:
    """
    Fetch full document details for given IDs.

    Designed for multi-query workflows: collect IDs from multiple queries,
    de-duplicate them, then fetch full documents once.

    Args:
        document_ids: Set of document IDs to fetch
        batch_size: Number of documents per database query (prevents param limits)

    Returns:
        List of document dictionaries (same format as find_abstracts)

    Example:
        >>> ids = {123, 456, 789}
        >>> docs = fetch_documents_by_ids(ids)
        >>> print(f"Fetched {len(docs)} documents")
        Fetched 3 documents
    """
    if not document_ids:
        logger.debug("No document IDs provided, returning empty list")
        return []

    logger.info(f"Fetching {len(document_ids)} documents in batches of {batch_size}")

    db_manager = get_db_manager()
    documents = []

    # Convert set to list for batching
    id_list = list(document_ids)

    # Fetch in batches to avoid PostgreSQL parameter limits
    for i in range(0, len(id_list), batch_size):
        batch_ids = id_list[i:i + batch_size]

        logger.debug(f"Fetching batch {i // batch_size + 1}: {len(batch_ids)} documents")

        # Simple query - authors are stored as text array in document table
        sql = """
            SELECT
                d.*,
                s.name as source_name
            FROM document d
            LEFT JOIN sources s ON d.source_id = s.id
            WHERE d.id = ANY(%s)
            ORDER BY d.publication_date DESC NULLS LAST
        """

        with db_manager.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(sql, [batch_ids])
                batch_docs = cur.fetchall()
                documents.extend(batch_docs)

    logger.info(f"Fetched {len(documents)} documents")

    return documents


def search_with_bm25(
    query_text: str,
    max_results: int = 100,
    use_pubmed: bool = True,
    use_medrxiv: bool = True,
    use_others: bool = True
) -> Generator[Dict, None, None]:
    """
    Search documents using BM25 ranked full-text search.

    Uses the PostgreSQL bm25() function for superior relevance ranking
    with length normalization (approximates BM25 k1=1.2, b=0.75).

    Args:
        query_text: PostgreSQL tsquery expression (e.g., "diabetes & treatment")
        max_results: Maximum number of results to return
        use_pubmed: Include PubMed results
        use_medrxiv: Include medRxiv results
        use_others: Include other sources

    Yields:
        Document dictionaries ordered by BM25 rank (highest relevance first)
    """
    db_manager = get_db_manager()

    # Build source filter
    source_filters = []
    if use_pubmed and 'pubmed' in DatabaseManager._source_ids:
        source_filters.append(f"source_id = {DatabaseManager._source_ids['pubmed']}")
    if use_medrxiv and 'medrxiv' in DatabaseManager._source_ids:
        source_filters.append(f"source_id = {DatabaseManager._source_ids['medrxiv']}")
    if use_others and 'others' in DatabaseManager._source_ids:
        others = DatabaseManager._source_ids['others']
        if isinstance(others, list) and len(others) > 0:
            source_filters.append(f"source_id = ANY(ARRAY{others})")
        elif not isinstance(others, list):
            source_filters.append(f"source_id = {others}")

    source_filter = ""
    if source_filters:
        source_filter = "AND (" + " OR ".join(source_filters) + ")"

    logger.info(f"BM25 search: '{query_text}', max_results={max_results}")

    with db_manager.get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            # Use BM25 function with source filtering
            sql = f"""
                SELECT b.*, s.name as source_name
                FROM bm25(%s, %s) b
                LEFT JOIN sources s ON b.source_id = s.id
                WHERE 1=1 {source_filter}
            """

            cur.execute(sql, (query_text, max_results))

            for row in cur:
                yield dict(row)

    logger.info(f"BM25 search completed for: '{query_text}'")


def search_with_semantic(
    search_text: str,
    threshold: float = 0.7,
    max_results: int = 100
) -> Generator[Dict, None, None]:
    """
    Search documents using semantic search with vector embeddings.

    Uses the PostgreSQL semantic_search() function which calls ollama_embedding()
    to generate embeddings and performs cosine similarity search on chunk embeddings.

    Args:
        search_text: Natural language search query
        threshold: Minimum similarity score (0.0 to 1.0, default: 0.7)
        max_results: Maximum number of results to return

    Yields:
        Document dictionaries with semantic similarity scores

    Note:
        - Uses snowflake-arctic-embed2:latest embedding model
        - Returns chunk-level results, so documents may appear multiple times
        - Embedding generation takes ~2-5 seconds per query
    """
    db_manager = get_db_manager()

    logger.info(f"Semantic search: '{search_text}', threshold={threshold}, max_results={max_results}")

    with db_manager.get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            # Use semantic_search function, then join with document table
            # Group by document to get unique documents with their best score
            sql = """
                WITH semantic_results AS (
                    SELECT
                        document_id,
                        MAX(score) as best_score,
                        COUNT(*) as matching_chunks
                    FROM semantic_search(%s, %s, %s)
                    GROUP BY document_id
                )
                SELECT
                    d.*,
                    s.name as source_name,
                    sr.best_score as semantic_score,
                    sr.matching_chunks
                FROM semantic_results sr
                JOIN document d ON sr.document_id = d.id
                LEFT JOIN sources s ON d.source_id = s.id
                ORDER BY sr.best_score DESC
            """

            cur.execute(sql, (search_text, threshold, max_results))

            for row in cur:
                yield dict(row)

    logger.info(f"Semantic search completed for: '{search_text}'")


def search_with_fulltext_function(
    query_text: str,
    max_results: int = 100,
    use_pubmed: bool = True,
    use_medrxiv: bool = True,
    use_others: bool = True
) -> Generator[Dict, None, None]:
    """
    Search documents using the fulltext_search PostgreSQL function.

    Uses the PostgreSQL fulltext_search() function for basic full-text search
    with ts_rank scoring.

    Args:
        query_text: PostgreSQL tsquery expression (e.g., "diabetes & treatment")
        max_results: Maximum number of results to return
        use_pubmed: Include PubMed results
        use_medrxiv: Include medRxiv results
        use_others: Include other sources

    Yields:
        Document dictionaries ordered by ts_rank (highest relevance first)
    """
    db_manager = get_db_manager()

    # Build source filter
    source_filters = []
    if use_pubmed and 'pubmed' in DatabaseManager._source_ids:
        source_filters.append(f"source_id = {DatabaseManager._source_ids['pubmed']}")
    if use_medrxiv and 'medrxiv' in DatabaseManager._source_ids:
        source_filters.append(f"source_id = {DatabaseManager._source_ids['medrxiv']}")
    if use_others and 'others' in DatabaseManager._source_ids:
        others = DatabaseManager._source_ids['others']
        if isinstance(others, list) and len(others) > 0:
            source_filters.append(f"source_id = ANY(ARRAY{others})")
        elif not isinstance(others, list):
            source_filters.append(f"source_id = {others}")

    source_filter = ""
    if source_filters:
        source_filter = "AND (" + " OR ".join(source_filters) + ")"

    logger.info(f"Fulltext search: '{query_text}', max_results={max_results}")

    with db_manager.get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            # Use fulltext_search function with source filtering
            sql = f"""
                SELECT f.*, s.name as source_name
                FROM fulltext_search(%s, %s) f
                LEFT JOIN sources s ON f.source_id = s.id
                WHERE 1=1 {source_filter}
            """

            cur.execute(sql, (query_text, max_results))

            for row in cur:
                yield dict(row)

    logger.info(f"Fulltext search completed for: '{query_text}'")


def search_hybrid(
    search_text: str,
    query_text: str,
    search_config: Optional[Dict[str, Any]] = None,
    use_pubmed: bool = True,
    use_medrxiv: bool = True,
    use_others: bool = True
) -> tuple[List[Dict], Dict[str, Any]]:
    """
    Orchestrate hybrid search combining multiple search strategies.

    Executes enabled search strategies (semantic, BM25, fulltext) based on
    configuration, merges results, deduplicates by document ID, and returns
    both the merged document list and metadata about which strategies were used.

    Args:
        search_text: Original natural language question
        query_text: Generated PostgreSQL tsquery expression
        search_config: Search strategy configuration dict (from config.json)
        use_pubmed: Include PubMed results
        use_medrxiv: Include medRxiv results
        use_others: Include other sources

    Returns:
        Tuple of (documents, strategy_metadata):
            - documents: List of unique documents with scores from each strategy
            - strategy_metadata: Dict containing strategies used and their parameters
    """
    from .config import get_config

    # Get search strategy configuration
    if search_config is None:
        search_config = get_config().get("search_strategy", {})

    # Initialize result tracking
    all_documents = {}  # document_id -> document dict with scores
    strategies_used = []
    strategy_metadata = {
        'strategies_used': [],
        'semantic_search_params': None,
        'bm25_search_params': None,
        'fulltext_search_params': None
    }

    logger.info("Starting hybrid search")
    logger.info(f"  Search text: '{search_text}'")
    logger.info(f"  Query text: '{query_text}'")

    # Priority order: semantic -> BM25 -> fulltext
    # 1. Semantic Search (if enabled)
    semantic_config = search_config.get('semantic', {})
    if semantic_config.get('enabled', False):
        try:
            threshold = semantic_config.get('similarity_threshold', 0.7)
            max_results = semantic_config.get('max_results', 100)
            embedding_model = semantic_config.get('embedding_model', 'snowflake-arctic-embed2:latest')

            logger.info(f"Executing semantic search (threshold={threshold}, max={max_results})")

            semantic_count = 0
            for doc in search_with_semantic(search_text, threshold, max_results):
                doc_id = doc['id']
                if doc_id not in all_documents:
                    all_documents[doc_id] = doc
                    all_documents[doc_id]['_search_scores'] = {}
                all_documents[doc_id]['_search_scores']['semantic'] = doc.get('semantic_score', 0)
                semantic_count += 1

            strategies_used.append('semantic')
            strategy_metadata['semantic_search_params'] = {
                'model': embedding_model,
                'threshold': threshold,
                'max_results': max_results,
                'documents_found': semantic_count
            }

            logger.info(f"  Semantic search found {semantic_count} documents")

        except Exception as e:
            logger.error(f"Semantic search failed: {e}", exc_info=True)

    # 2. BM25 Search (if enabled)
    bm25_config = search_config.get('bm25', {})
    if bm25_config.get('enabled', False):
        try:
            max_results = bm25_config.get('max_results', 100)
            k1 = bm25_config.get('k1', 1.2)
            b = bm25_config.get('b', 0.75)

            logger.info(f"Executing BM25 search (k1={k1}, b={b}, max={max_results})")

            bm25_count = 0
            for doc in search_with_bm25(query_text, max_results, use_pubmed, use_medrxiv, use_others):
                doc_id = doc['id']
                if doc_id not in all_documents:
                    all_documents[doc_id] = doc
                    all_documents[doc_id]['_search_scores'] = {}
                all_documents[doc_id]['_search_scores']['bm25'] = doc.get('rank', 0)
                bm25_count += 1

            strategies_used.append('bm25')
            strategy_metadata['bm25_search_params'] = {
                'k1': k1,
                'b': b,
                'max_results': max_results,
                'query_expression': query_text,
                'documents_found': bm25_count
            }

            logger.info(f"  BM25 search found {bm25_count} documents")

        except Exception as e:
            logger.error(f"BM25 search failed: {e}", exc_info=True)

    # 3. Fulltext Search (if enabled) - fallback to keyword if neither semantic nor BM25
    fulltext_config = search_config.get('keyword', {})  # Using 'keyword' for backward compatibility
    fulltext_enabled = fulltext_config.get('enabled', False)

    # Enable fulltext as fallback if no other strategies are enabled
    if not strategies_used:
        fulltext_enabled = True
        logger.info("No search strategies enabled - using fulltext as fallback")

    if fulltext_enabled:
        try:
            max_results = fulltext_config.get('max_results', 100)

            logger.info(f"Executing fulltext search (max={max_results})")

            fulltext_count = 0
            for doc in search_with_fulltext_function(query_text, max_results, use_pubmed, use_medrxiv, use_others):
                doc_id = doc['id']
                if doc_id not in all_documents:
                    all_documents[doc_id] = doc
                    all_documents[doc_id]['_search_scores'] = {}
                all_documents[doc_id]['_search_scores']['fulltext'] = doc.get('rank', 0)
                fulltext_count += 1

            strategies_used.append('fulltext')
            strategy_metadata['fulltext_search_params'] = {
                'max_results': max_results,
                'query_expression': query_text,
                'documents_found': fulltext_count
            }

            logger.info(f"  Fulltext search found {fulltext_count} documents")

        except Exception as e:
            logger.error(f"Fulltext search failed: {e}", exc_info=True)

    # Update strategy metadata
    strategy_metadata['strategies_used'] = strategies_used

    # Convert to list and sort by combined score
    documents = list(all_documents.values())

    # Calculate combined scores (simple sum for now)
    for doc in documents:
        scores = doc.get('_search_scores', {})
        doc['_combined_score'] = sum(scores.values())

    # Sort by combined score (highest first)
    documents.sort(key=lambda d: d.get('_combined_score', 0), reverse=True)

    total_unique = len(documents)
    logger.info(f"Hybrid search complete: {total_unique} unique documents from {len(strategies_used)} strategies")

    return documents, strategy_metadata


def close_database():
    """Close the database connection pool."""
    global _db_manager
    if _db_manager:
        _db_manager.close()
        _db_manager = None