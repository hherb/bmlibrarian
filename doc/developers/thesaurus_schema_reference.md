# Thesaurus Schema Reference

**Migration**: 021_create_thesaurus_schema.sql
**Date**: 2025-11-26
**Purpose**: Medical terminology thesaurus for keyword expansion in literature search

## Quick Start

### 1. Run Migration

```bash
# Apply migration to database
psql -U postgres -d knowledgebase -f migrations/021_create_thesaurus_schema.sql

# Verify schema
psql -U postgres -d knowledgebase -f scripts/verify_thesaurus_schema.sql
```

### 2. Import MeSH Data

```bash
# Coming soon: MeSH XML importer
uv run python thesaurus_import_cli.py import-mesh desc2025.xml
```

### 3. Use in Queries

```sql
-- Expand a term to all variants
SELECT * FROM thesaurus.expand_term('MI');

-- Get only synonyms (exclude input term)
SELECT * FROM thesaurus.get_all_synonyms('aspirin');

-- Navigate hierarchy
SELECT * FROM thesaurus.get_broader_terms('Myocardial Infarction');
SELECT * FROM thesaurus.get_narrower_terms('Heart Diseases');

-- Search concepts
SELECT * FROM thesaurus.search_concepts('cardiac', 20);
```

## Schema Structure

```
thesaurus/
├── concepts              -- 30K medical concepts (MeSH descriptors)
├── terms                 -- 300K term variants (synonyms, abbreviations)
├── concept_hierarchies   -- MeSH tree relationships
└── import_history        -- Version tracking
```

### Table: thesaurus.concepts

| Column | Type | Description |
|--------|------|-------------|
| concept_id | SERIAL | Internal primary key |
| preferred_term | TEXT | Canonical term (e.g., "Myocardial Infarction") |
| definition | TEXT | Concept definition from MeSH ScopeNote |
| semantic_type | TEXT | Category (disease, drug, procedure, etc.) |
| source_vocabulary | TEXT | Source: mesh, rxnorm, loinc, snomed, umls, custom |
| source_concept_id | TEXT | Original ID (e.g., MeSH "D009203") |

**Example Row**:
```sql
concept_id:       1
preferred_term:   Myocardial Infarction
definition:       NECROSIS of the MYOCARDIUM caused by obstruction...
semantic_type:    disease
source_vocabulary: mesh
source_concept_id: D009203
```

### Table: thesaurus.terms

| Column | Type | Description |
|--------|------|-------------|
| term_id | SERIAL | Internal primary key |
| concept_id | INTEGER | FK to concepts table |
| term_text | TEXT | Actual term string (e.g., "MI", "Heart Attack") |
| term_type | TEXT | preferred, synonym, abbreviation, trade_name |
| lexical_tag | TEXT | Original MeSH tag: NON, ABB, SYN, TRD |
| source_term_id | TEXT | Original term ID (e.g., MeSH "T000745") |

**Example Rows for concept_id=1**:
```sql
term_text                   term_type      lexical_tag
--------------------------- -------------- -----------
Myocardial Infarction       preferred      NON
MI                          abbreviation   ABB
AMI                         abbreviation   ABB
Heart Attack                synonym        SYN
Cardiac Infarction          synonym        SYN
Myocardial Infarct          synonym        SYN
```

### Table: thesaurus.concept_hierarchies

| Column | Type | Description |
|--------|------|-------------|
| hierarchy_id | SERIAL | Internal primary key |
| concept_id | INTEGER | FK to concepts table |
| tree_number | TEXT | MeSH tree location (e.g., "C14.280.647.500") |
| tree_level | INTEGER | Depth in tree (1=root, higher=more specific) |

**Example Tree Structure**:
```
C14                         Cardiovascular Diseases (level 1)
└── C14.280                Heart Diseases (level 2)
    └── C14.280.647       Myocardial Ischemia (level 3)
        └── C14.280.647.500  Myocardial Infarction (level 4)
```

## Utility Functions

### 1. expand_term(text) - Complete Term Expansion

Returns all variants including the input term.

```sql
SELECT * FROM thesaurus.expand_term('MI');
```

**Result**:
```
term                     term_type      preferred_term           is_input_term
------------------------ -------------- ----------------------- --------------
MI                       abbreviation   Myocardial Infarction   true
Myocardial Infarction    preferred      Myocardial Infarction   false
AMI                      abbreviation   Myocardial Infarction   false
Heart Attack             synonym        Myocardial Infarction   false
Cardiac Infarction       synonym        Myocardial Infarction   false
Myocardial Infarct       synonym        Myocardial Infarction   false
```

### 2. get_all_synonyms(text) - Synonyms Only

Returns all variants except the input term.

```sql
SELECT * FROM thesaurus.get_all_synonyms('aspirin');
```

**Result**:
```
synonym                   term_type      preferred_term
------------------------ -------------- ---------------
Acetylsalicylic Acid     synonym        Aspirin
2-Acetoxybenzoic Acid    synonym        Aspirin
ASA                      abbreviation   Aspirin
Bayer Aspirin            trade_name     Aspirin
Ecotrin                  trade_name     Aspirin
```

### 3. get_broader_terms(text) - Navigate Up Hierarchy

Returns parent terms in MeSH tree.

```sql
SELECT * FROM thesaurus.get_broader_terms('Myocardial Infarction');
```

**Result**:
```
broader_term           tree_number      tree_level
--------------------- ---------------- -----------
Myocardial Ischemia   C14.280.647      3
```

### 4. get_narrower_terms(text) - Navigate Down Hierarchy

Returns immediate child terms.

```sql
SELECT * FROM thesaurus.get_narrower_terms('Myocardial Ischemia');
```

**Result**:
```
narrower_term                        tree_number        tree_level
----------------------------------- ------------------ -----------
Myocardial Infarction               C14.280.647.500    4
Angina Pectoris                     C14.280.647.187    4
Myocardial Stunning                 C14.280.647.750    4
```

### 5. search_concepts(text, limit) - Fuzzy Search

Search concepts by partial match.

```sql
SELECT * FROM thesaurus.search_concepts('cardiac', 10);
```

**Result**:
```
preferred_term          definition                        match_type
---------------------- --------------------------------- -----------
Cardiac Arrest         Cessation of cardiac function...  prefix
Cardiac Output         Volume of blood pumped...         prefix
Cardiac Tamponade      Compression of the heart...       prefix
```

## Usage Examples

### Query Expansion in Search

```sql
-- WITHOUT thesaurus (basic search)
SELECT * FROM documents
WHERE abstract_tsvector @@ plainto_tsquery('english', 'MI');
-- Returns: Papers mentioning "MI" only

-- WITH thesaurus (expanded search)
WITH expanded AS (
    SELECT term FROM thesaurus.expand_term('MI')
)
SELECT * FROM documents
WHERE abstract_tsvector @@ to_tsquery('english',
    (SELECT string_agg(term, ' | ') FROM expanded)
);
-- Returns: Papers mentioning "MI" OR "Myocardial Infarction"
--          OR "Heart Attack" OR "AMI" OR other variants
-- Result: 3-5x more relevant papers found
```

### Abbreviation Expansion

```sql
-- Resolve ambiguous abbreviations
SELECT
    preferred_term,
    definition
FROM thesaurus.concepts c
JOIN thesaurus.terms t ON c.concept_id = t.concept_id
WHERE LOWER(t.term_text) = 'mi';
```

**Result**:
```
preferred_term             definition
------------------------- ------------------------------------------
Myocardial Infarction     NECROSIS of the MYOCARDIUM...
Mitral Insufficiency      Backflow of blood from LEFT VENTRICLE...
```

### Hierarchical Query Expansion

```sql
-- Search for "Heart Diseases" and all subtypes
WITH heart_and_subtypes AS (
    -- Get base concept
    SELECT c.concept_id FROM thesaurus.concepts c
    WHERE c.preferred_term = 'Heart Diseases'

    UNION

    -- Get all narrower terms recursively
    SELECT c2.concept_id
    FROM thesaurus.concept_hierarchies h1
    JOIN thesaurus.concepts c1 ON h1.concept_id = c1.concept_id
    JOIN thesaurus.concept_hierarchies h2 ON h2.tree_number LIKE h1.tree_number || '.%'
    JOIN thesaurus.concepts c2 ON h2.concept_id = c2.concept_id
    WHERE c1.preferred_term = 'Heart Diseases'
)
SELECT DISTINCT c.preferred_term
FROM heart_and_subtypes hs
JOIN thesaurus.concepts c ON hs.concept_id = c.concept_id
ORDER BY c.preferred_term;
```

## Performance Characteristics

### Expected Query Times (MeSH data, 300K terms)

| Operation | Response Time | Notes |
|-----------|---------------|-------|
| expand_term() | 5-10 ms | Single term expansion |
| get_all_synonyms() | 5-10 ms | Synonym lookup |
| get_broader_terms() | 10-20 ms | Tree navigation |
| search_concepts() | 20-50 ms | Fuzzy search with ranking |

### Database Size Estimates

| Vocabulary | Concepts | Terms | DB Size |
|------------|----------|-------|---------|
| MeSH only | 30,000 | 300,000 | ~200 MB |
| + RxNorm | 430,000 | 700,000 | ~500 MB |
| + LOINC | 525,000 | 800,000 | ~600 MB |
| Full UMLS | 4,000,000 | 14,000,000 | 10-20 GB |

## Indexes

All critical indexes are created automatically by the migration:

- **Fast term lookup**: `idx_thesaurus_terms_text_lower` (B-tree on LOWER(term_text))
- **Full-text search**: `idx_thesaurus_terms_text_gin` (GIN on tsvector)
- **Concept navigation**: `idx_thesaurus_terms_concept` (B-tree on concept_id)
- **Hierarchy queries**: `idx_thesaurus_hierarchies_tree_pattern` (text pattern ops)

## Next Steps

1. **Import MeSH Data**: Use `thesaurus_import_cli.py` (coming soon)
2. **Verify Import**: Check `thesaurus.import_history` table
3. **Test Expansion**: Run example queries above
4. **Integrate with QueryAgent**: Enable automatic query expansion
5. **Monitor Performance**: Check query times with real data

## References

- Migration: `migrations/021_create_thesaurus_schema.sql`
- Verification: `scripts/verify_thesaurus_schema.sql`
- Analysis: `doc/planning/thesaurus_mesh_analysis.md`
- MeSH Documentation: https://www.nlm.nih.gov/mesh/

---

**Last Updated**: 2025-11-26
**Schema Version**: 1.0
