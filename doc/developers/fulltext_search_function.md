# Full-Text Search Function

## Overview

The `fulltext_search()` PostgreSQL function provides a convenient interface for performing full-text searches on the BMLibrarian document database using PostgreSQL's tsquery syntax.

## Function Signature

```sql
fulltext_search(
    ts_query_expression text,
    max_results integer DEFAULT 100
) RETURNS TABLE (
    id integer,
    title text,
    abstract text,
    authors text[],
    publication text,
    publication_date date,
    doi text,
    url text,
    pdf_filename text,
    external_id text,
    source_id integer,
    rank real
)
```

## Parameters

- **ts_query_expression** (text): A search query string in PostgreSQL tsquery format
  - Supports boolean operators: `&` (AND), `|` (OR), `!` (NOT)
  - Supports phrase searches with quotes
  - Falls back to plainto_tsquery for simple queries if parsing fails

- **max_results** (integer, default=100): Maximum number of results to return

## Returns

A table with the following columns:
- **id**: Document primary key
- **title**: Document title
- **abstract**: Document abstract
- **authors**: Array of author names
- **publication**: Publication name
- **publication_date**: Date of publication
- **doi**: Digital Object Identifier
- **url**: Document URL
- **pdf_filename**: Local PDF filename
- **external_id**: External identifier (e.g., PubMed ID)
- **source_id**: Source database ID
- **rank**: Relevance ranking score (higher = more relevant)

Results are ordered by:
1. Relevance rank (descending)
2. Publication date (descending, with NULL dates last)

## Features

- **Automatic Query Parsing**: Attempts to parse as tsquery, falls back to plainto_tsquery
- **Withdrawn Document Filtering**: Automatically excludes withdrawn documents
- **GIN Index Optimization**: Uses the `idx_document_fts` GIN index for fast searches
- **Weighted Search**: Searches prioritize title matches (weight A) over abstract matches (weight B)

## Usage Examples

### Basic Search (AND operator)
```sql
-- Find documents about exercise and cardiovascular health
SELECT * FROM fulltext_search('exercise & cardiovascular', 10);
```

### OR Search
```sql
-- Find documents about diabetes OR insulin
SELECT * FROM fulltext_search('diabetes | insulin', 50);
```

### Complex Boolean Query
```sql
-- Find documents about hypertension or high blood pressure AND treatment
SELECT * FROM fulltext_search('(hypertension | ''high blood pressure'') & treatment', 25);
```

### Negation (NOT operator)
```sql
-- Find documents about diabetes but NOT type 2
SELECT * FROM fulltext_search('diabetes & !''type 2''', 20);
```

### Get Only Specific Fields
```sql
-- Just get titles and ranks
SELECT id, title, rank
FROM fulltext_search('cancer immunotherapy', 15);
```

### Filter Results Further
```sql
-- Get only recent documents (last 5 years)
SELECT id, title, publication_date, rank
FROM fulltext_search('machine learning medical', 50)
WHERE publication_date >= CURRENT_DATE - INTERVAL '5 years';
```

### Count Results
```sql
-- Count how many documents match a query
SELECT COUNT(*)
FROM fulltext_search('covid-19 vaccine', 1000);
```

## Query Syntax Reference

### Basic Operators
- `&` - AND (both terms must appear)
- `|` - OR (either term can appear)
- `!` - NOT (term must not appear)
- `<->` - FOLLOWED BY (adjacent words)
- `<N>` - NEAR (words within N positions)

### Precedence
Operators have precedence: `!` (NOT) > `<->` (FOLLOWED BY) > `&` (AND) > `|` (OR)

Use parentheses to control precedence: `(term1 | term2) & term3`

### Phrase Searches
Use single quotes for multi-word phrases: `'machine learning'`

### Wildcards
Use `:*` for prefix matching: `cardio:*` matches "cardiology", "cardiovascular", etc.

## Performance Notes

- The function uses the GIN index `idx_document_fts` for efficient searching
- Average query time: < 100ms for most queries
- For very broad searches, consider lowering `max_results` to improve response time
- The search is case-insensitive (handled by the English text search configuration)

## Installation

Run the SQL script to create the function:

```bash
psql -d knowledgebase -f scripts/create_fulltext_search_function.sql
```

## Integration with BMLibrarian

This function can be called from Python using psycopg:

```python
import psycopg

# Connect to database
with psycopg.connect("dbname=knowledgebase user=hherb") as conn:
    with conn.cursor() as cur:
        # Execute full-text search
        cur.execute(
            "SELECT * FROM fulltext_search(%s, %s)",
            ("diabetes & treatment", 10)
        )

        # Fetch results
        results = cur.fetchall()
        for row in results:
            print(f"ID: {row[0]}, Title: {row[1]}, Rank: {row[11]}")
```

## Troubleshooting

### Query Parsing Errors
If your query contains special characters or syntax errors, the function automatically falls back to `plainto_tsquery`, which accepts plain text and converts it to a query.

### No Results
- Check your query syntax
- Try a simpler query with fewer boolean operators
- Use OR (`|`) instead of AND (`&`) to broaden results
- Try prefix matching with `:*` for partial word matches

### Slow Queries
- Reduce `max_results` parameter
- Narrow your query with more specific terms
- Check that the GIN index exists: `\d document` should show `idx_document_fts`

## See Also

- PostgreSQL Full-Text Search Documentation: https://www.postgresql.org/docs/current/textsearch.html
- BMLibrarian QueryAgent: Uses this function for document retrieval
- Database Schema: See `document` table definition in database documentation
