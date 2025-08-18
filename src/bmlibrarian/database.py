"""Database access layer for BMLibrarian with connection pooling."""

import os
from contextlib import contextmanager
from typing import Dict, Generator, Optional, List, Union
from datetime import date

import psycopg
from psycopg import sql
from psycopg_pool import ConnectionPool
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class DatabaseManager:
    """Manages database connections and provides high-level API access."""
    
    def __init__(self):
        """Initialize the database manager with connection pool."""
        self._pool: Optional[ConnectionPool] = None
        self._source_ids: Optional[Dict[str, Union[int, List[int]]]] = None
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
    
    def _cache_source_ids(self):
        """Cache source IDs for faster queries."""
        self._source_ids = {'others': []}
        
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, name FROM sources")
                for source_id, name in cur.fetchall():
                    name_lower = name.lower()
                    if 'pubmed' in name_lower:
                        self._source_ids['pubmed'] = source_id
                    elif 'medrxiv' in name_lower:
                        self._source_ids['medrxiv'] = source_id
                    else:
                        # Store other source IDs
                        if isinstance(self._source_ids['others'], list):
                            self._source_ids['others'].append(source_id)
    
    @contextmanager
    def get_connection(self):
        """Get a database connection from the pool."""
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        
        with self._pool.connection() as conn:
            yield conn
    
    def refresh_source_cache(self):
        """Refresh the cached source IDs."""
        self._cache_source_ids()
    
    def get_cached_source_ids(self) -> Optional[Dict[str, Union[int, List[int]]]]:
        """Get the cached source IDs."""
        return self._source_ids
    
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
    to_date: Optional[date] = None
) -> Generator[Dict, None, None]:
    """
    Find document abstracts using PostgreSQL text search with optional date filtering.
    
    Args:
        ts_query_str: Text search query string
        max_rows: Maximum number of rows to return (0 = no limit)
        use_pubmed: Include PubMed sources
        use_medrxiv: Include medRxiv sources  
        use_others: Include other sources
        plain: If True, use plainto_tsquery (simple text); if False, use to_tsquery (advanced syntax)
        from_date: Only include documents published on or after this date (inclusive)
        to_date: Only include documents published on or before this date (inclusive)
        
    Yields:
        Dict containing document information with keys:
        - id: Document ID
        - title: Document title
        - abstract: Document abstract
        - authors: List of authors
        - publication: Publication name
        - publication_date: Publication date
        - doi: DOI if available
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
    db_manager = get_db_manager()
    
    # Build source ID filter using cached source IDs (much faster than JOINs)
    source_ids = []
    source_name_map = {}
    
    if db_manager._source_ids:
        if use_pubmed and 'pubmed' in db_manager._source_ids:
            pubmed_id = db_manager._source_ids['pubmed']
            source_ids.append(pubmed_id)
            source_name_map[pubmed_id] = 'pubmed'
        
        if use_medrxiv and 'medrxiv' in db_manager._source_ids:
            medrxiv_id = db_manager._source_ids['medrxiv']
            source_ids.append(medrxiv_id)
            source_name_map[medrxiv_id] = 'medrxiv'
        
        if use_others and 'others' in db_manager._source_ids:
            others_ids = db_manager._source_ids['others']
            if isinstance(others_ids, list):
                source_ids.extend(others_ids)
                for other_id in others_ids:
                    source_name_map[other_id] = 'others'
    
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
    
    # Build optimized query without JOIN
    source_id_placeholders = ','.join(['%s'] * len(source_ids))
    base_query = f"""
    SELECT 
        d.id,
        d.title,
        d.abstract,
        d.authors,
        d.publication,
        d.publication_date,
        d.doi,
        d.url,
        d.source_id,
        d.keywords,
        d.mesh_terms,
        d.augmented_keywords,
        d.all_keywords
    FROM document d
    WHERE d.search_vector @@ {tsquery_func}('english', %s)
    AND d.source_id IN ({source_id_placeholders})
    AND d.abstract IS NOT NULL
    AND d.abstract != ''
    {date_filter}
    ORDER BY ts_rank(d.search_vector, {tsquery_func}('english', %s)) DESC
    """
    
    # Add limit if specified
    if max_rows > 0:
        query = base_query + f" LIMIT {max_rows}"
    else:
        query = base_query
    
    # Prepare query parameters
    query_params = [ts_query_str] + source_ids + date_params + [ts_query_str]
    
    with db_manager.get_connection() as conn:
        with conn.cursor() as cur:
            # Execute the query with parameters
            cur.execute(query, tuple(query_params))
            
            while True:
                row = cur.fetchone()
                if row is None:
                    break
                
                # Convert row to dictionary
                source_id = row[8]
                doc = {
                    'id': row[0],
                    'title': row[1],
                    'abstract': row[2],
                    'authors': row[3] or [],
                    'publication': row[4],
                    'publication_date': row[5],
                    'doi': row[6],
                    'url': row[7],
                    'source_name': source_name_map.get(source_id, 'unknown'),
                    'keywords': row[9] or [],
                    'mesh_terms': row[10] or [],
                    'augmented_keywords': row[11] or [],
                    'all_keywords': row[12] or []
                }
                
                yield doc


def close_database():
    """Close the database connection pool."""
    global _db_manager
    if _db_manager:
        _db_manager.close()
        _db_manager = None