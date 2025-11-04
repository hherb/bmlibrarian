# Phase 3: Database Layer Updates

**Estimated Time**: 3-4 hours

## Objectives
1. Add ID-only query function (fast, no full document fetch)
2. Add bulk document fetch by IDs
3. Keep existing functions unchanged

## Files to Modify

### 1. src/bmlibrarian/database.py

**Current**: find_abstracts() returns full documents (lines 200+)

**Add new function** (around line 400, after find_abstracts):

```python
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
) -> Set[int]:
    """
    Execute search and return ONLY document IDs (fast).

    This is much faster than find_abstracts() because:
    - No JOINs with authors table
    - No text field transfers
    - Returns Set[int] for easy de-duplication

    Args:
        Same as find_abstracts()

    Returns:
        Set of document IDs

    Example:
        ids = find_abstract_ids("aspirin & heart", max_rows=100)
        # Returns: {123, 456, 789, ...}
    """
    db = DatabaseManager()

    # Similar to find_abstracts but query only:
    # SELECT DISTINCT d.id FROM documents d ...
    # No authors JOIN, no text fields

    query_parts = []
    params = []

    # Build WHERE clause (same logic as find_abstracts)
    if plain:
        query_parts.append("d.search_vector @@ plainto_tsquery('english', %s)")
    else:
        query_parts.append("d.search_vector @@ to_tsquery('english', %s)")
    params.append(ts_query_str)

    # Source filtering (same as find_abstracts)
    source_filters = []
    if use_pubmed and db._source_ids and 'pubmed' in db._source_ids:
        source_filters.append(f"d.source_id = {db._source_ids['pubmed']}")
    # ... etc for medrxiv, others

    if source_filters:
        query_parts.append(f"({' OR '.join(source_filters)})")

    # Date filtering (same as find_abstracts)
    if from_date:
        query_parts.append("d.publish_time >= %s")
        params.append(from_date)
    if to_date:
        query_parts.append("d.publish_time <= %s")
        params.append(to_date)

    # Build final query - ID ONLY
    where_clause = " AND ".join(query_parts)

    sql = f"""
        SELECT DISTINCT d.id
        FROM documents d
        WHERE {where_clause}
        ORDER BY d.publish_time DESC
        LIMIT %s OFFSET %s
    """
    params.extend([max_rows, offset])

    # Execute and collect IDs
    document_ids = set()
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            for row in cur.fetchall():
                document_ids.add(row[0])

    return document_ids
```

**Add bulk fetch function** (after find_abstract_ids):

```python
def fetch_documents_by_ids(
    document_ids: Set[int],
    batch_size: int = 50
) -> List[Dict[str, Any]]:
    """
    Fetch full document details for given IDs.

    Args:
        document_ids: Set of document IDs to fetch
        batch_size: Number of documents per database query

    Returns:
        List of document dictionaries (same format as find_abstracts)

    Example:
        ids = {123, 456, 789}
        docs = fetch_documents_by_ids(ids)
        # Returns list of full documents
    """
    if not document_ids:
        return []

    db = DatabaseManager()
    documents = []

    # Convert set to list for batching
    id_list = list(document_ids)

    # Fetch in batches to avoid query size limits
    for i in range(0, len(id_list), batch_size):
        batch_ids = id_list[i:i + batch_size]

        # Use same query structure as find_abstracts
        sql = """
            SELECT
                d.*,
                s.name as source_name,
                COALESCE(
                    json_agg(
                        json_build_object(
                            'first', a.first,
                            'last', a.last,
                            'middle', a.middle,
                            'suffix', a.suffix
                        ) ORDER BY da.author_order
                    ) FILTER (WHERE a.id IS NOT NULL),
                    '[]'::json
                ) as authors
            FROM documents d
            LEFT JOIN sources s ON d.source_id = s.id
            LEFT JOIN document_authors da ON d.id = da.document_id
            LEFT JOIN authors a ON da.author_id = a.id
            WHERE d.id = ANY(%s)
            GROUP BY d.id, s.name
            ORDER BY d.publish_time DESC
        """

        with db.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(sql, [batch_ids])
                documents.extend(cur.fetchall())

    return documents
```

## Update Exports

**Modify** `src/bmlibrarian/database.py` (around line 10):

```python
# Add to __all__ or create if doesn't exist
__all__ = [
    'DatabaseManager',
    'find_abstracts',
    'find_abstract_ids',  # NEW
    'fetch_documents_by_ids',  # NEW
]
```

## Testing Phase 3

### Manual Test
```python
from bmlibrarian.database import find_abstract_ids, fetch_documents_by_ids

# Test 1: Get IDs only
ids = find_abstract_ids("aspirin & heart", max_rows=10)
print(f"Found {len(ids)} document IDs")

# Test 2: Fetch full documents
docs = fetch_documents_by_ids(ids)
print(f"Fetched {len(docs)} full documents")

# Test 3: Verify same as find_abstracts
from bmlibrarian.database import find_abstracts
original_docs = list(find_abstracts("aspirin & heart", max_rows=10))
print(f"Original: {len(original_docs)} documents")

# IDs should match
original_ids = {doc['id'] for doc in original_docs}
assert ids == original_ids, "ID sets should match"
```

### Performance Test
```python
import time

# Test: ID-only vs full fetch
query = "diabetes & kidney"

# Method 1: ID-only
start = time.time()
ids = find_abstract_ids(query, max_rows=100)
docs = fetch_documents_by_ids(ids)
time_split = time.time() - start

# Method 2: Direct full fetch
start = time.time()
docs_direct = list(find_abstracts(query, max_rows=100))
time_direct = time.time() - start

print(f"Split method: {time_split:.2f}s")
print(f"Direct method: {time_direct:.2f}s")
# Should be similar since single query
```

## Completion Criteria
- [x] find_abstract_ids() implemented
- [x] fetch_documents_by_ids() implemented
- [x] Exports updated
- [x] Manual tests pass
- [x] Performance acceptable

## Next Step
Update `00_OVERVIEW.md`, read `04_PHASE4_CLI.md`.

## Key Implementation Notes
- **ID-only query**: Much simpler SQL, no JOINs, no text fields
- **Batched fetch**: Prevents query size limits (PostgreSQL has max params)
- **Same format**: Return documents in identical format to find_abstracts()
- **Set-based**: Uses Set[int] for automatic de-duplication
