# BMLibrarian Medical Thesaurus Import Guide

## Overview

BMLibrarian includes a comprehensive medical thesaurus system for expanding search terms with synonyms, abbreviations, and related medical concepts. This guide explains how to populate the thesaurus database with MeSH (Medical Subject Headings) data.

## What is MeSH?

MeSH (Medical Subject Headings) is the National Library of Medicine's controlled vocabulary thesaurus used for indexing PubMed articles. It contains:

- **~30,000 medical concepts** (descriptors)
- **~300,000 terms** (preferred terms, synonyms, abbreviations)
- **Hierarchical relationships** (broader/narrower terms)
- **Annual updates** from the NLM

## Prerequisites

- BMLibrarian installed with PostgreSQL database configured
- Python environment activated (`uv sync`)
- Database migration 021 applied (creates thesaurus schema)
- Internet connection for downloading MeSH data

## Step 1: Download MeSH Data

### From NLM FTP Server

1. Visit the MeSH FTP site:
   ```
   https://nlmpubs.nlm.nih.gov/projects/mesh/MESH_FILES/xmlmesh/
   ```

2. Download the latest descriptor file (e.g., `desc2025.xml.gz`):
   ```bash
   # Example for 2025 data
   wget https://nlmpubs.nlm.nih.gov/projects/mesh/MESH_FILES/xmlmesh/desc2025.xml.gz
   ```

3. Extract the XML file:
   ```bash
   gunzip desc2025.xml.gz
   ```

**File size:** ~350 MB uncompressed

### Alternative: Manual Download

If automated download fails (NLM may block automated requests):

1. Open https://nlmpubs.nlm.nih.gov/projects/mesh/MESH_FILES/xmlmesh/ in your browser
2. Right-click on `desc2025.xml.gz` and save
3. Extract using your operating system's archive tool

## Step 2: Verify Database Schema

Ensure the thesaurus schema exists:

```bash
psql -d knowledgebase -c "SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'thesaurus';"
```

If the schema doesn't exist, apply the migration:

```bash
# Check for migration file
ls migrations/021_create_thesaurus_schema.sql

# Apply migration (if using migration system)
# Or apply manually:
psql -d knowledgebase -f migrations/021_create_thesaurus_schema.sql
```

## Step 3: Import MeSH Data

### Basic Import

```bash
uv run python thesaurus_import_cli.py desc2025.xml
```

**Expected output:**
```
2025-01-15 10:00:00 - INFO - Starting MeSH import from: desc2025.xml
2025-01-15 10:00:00 - INFO - Source version: 2025
2025-01-15 10:00:00 - INFO - Parsing XML file...
2025-01-15 10:00:05 - INFO - Found 30082 descriptors to import
2025-01-15 10:00:10 - INFO - Imported 100/30082 descriptors (100 concepts, 850 terms, 245 hierarchies)
2025-01-15 10:00:15 - INFO - Imported 200/30082 descriptors (200 concepts, 1700 terms, 490 hierarchies)
...
2025-01-15 10:15:30 - INFO - Import completed successfully

============================================================
MeSH IMPORT STATISTICS
============================================================
Concepts imported:     30,082
Terms imported:        286,543
Hierarchies imported:  87,219
Errors:                0
Duration:              930 seconds
Import rate:           32.3 concepts/second
============================================================
```

**Import time:** ~15-20 minutes for full MeSH dataset

### Advanced Options

#### Dry Run (Validate Without Importing)

Test XML parsing and validation without database changes:

```bash
uv run python thesaurus_import_cli.py desc2025.xml --dry-run
```

Use this to:
- Verify XML file integrity
- Check expected record counts
- Validate before committing to database

#### Custom Batch Size

Adjust transaction size for performance tuning:

```bash
# Larger batches (faster but more memory)
uv run python thesaurus_import_cli.py desc2025.xml --batch-size 500

# Smaller batches (slower but safer)
uv run python thesaurus_import_cli.py desc2025.xml --batch-size 50
```

**Recommended batch sizes:**
- Default (100): Good balance for most systems
- Large memory (500+): Faster import on powerful systems
- Limited memory (50): Safer on constrained systems

#### Verbose Logging

Enable detailed debug output:

```bash
uv run python thesaurus_import_cli.py desc2025.xml --verbose
```

#### Custom Version Tag

Specify version identifier for tracking:

```bash
uv run python thesaurus_import_cli.py desc2025.xml --version "2025-01-15"
```

## Step 4: Verify Import

### Check Record Counts

```sql
-- Count imported concepts
SELECT COUNT(*) FROM thesaurus.concepts;
-- Expected: ~30,000

-- Count imported terms
SELECT COUNT(*) FROM thesaurus.terms;
-- Expected: ~286,000

-- Count hierarchies
SELECT COUNT(*) FROM thesaurus.concept_hierarchies;
-- Expected: ~87,000

-- View import history
SELECT * FROM thesaurus.import_history ORDER BY imported_at DESC LIMIT 5;
```

### Test Term Expansion

```sql
-- Expand "MI" (myocardial infarction)
SELECT * FROM thesaurus.expand_term('MI');

-- Expected results:
-- MI, Myocardial Infarction, Heart Attack, AMI, etc.

-- Expand "aspirin"
SELECT * FROM thesaurus.expand_term('aspirin');

-- Expected results:
-- aspirin, ASA, acetylsalicylic acid, etc.
```

### Verify Hierarchies

```sql
-- Find broader terms for "myocardial infarction"
SELECT * FROM thesaurus.get_broader_terms('myocardial infarction');

-- Find narrower terms for "cardiovascular diseases"
SELECT * FROM thesaurus.get_narrower_terms('cardiovascular diseases');
```

## Step 5: Enable in QueryAgent

### Configuration File Method

Edit `~/.bmlibrarian/config.json`:

```json
{
  "agents": {
    "query_agent": {
      "model": "medgemma4B_it_q8:latest",
      "use_thesaurus": true,
      "thesaurus_max_expansions": 10
    }
  }
}
```

### Programmatic Method

```python
from bmlibrarian.agents import QueryAgent

# Create agent with thesaurus enabled
query_agent = QueryAgent(
    use_thesaurus=True,
    thesaurus_max_expansions=10
)

# Search with automatic term expansion
documents = query_agent.find_abstracts(
    "What are the benefits of aspirin for MI prevention?"
)
# Query automatically expands:
# - aspirin → (aspirin | ASA | acetylsalicylic acid)
# - MI → (MI | myocardial infarction | heart attack | AMI)
```

### Test Expansion

```python
from bmlibrarian.thesaurus import ThesaurusExpander

expander = ThesaurusExpander(max_expansions_per_term=10)

# Test single term
result = expander.expand_term("aspirin")
print(f"Original: {result.original_term}")
print(f"Preferred: {result.preferred_term}")
print(f"All variants: {result.all_variants}")

# Test query expansion
expanded = expander.expand_query("aspirin & heart attack")
print(f"Expanded query: {expanded}")
# Output: (aspirin | ASA | acetylsalicylic acid) & (heart attack | myocardial infarction | MI)
```

## Updating MeSH Data

MeSH is updated annually. To update your thesaurus:

1. Download the new year's descriptor file (e.g., `desc2026.xml`)
2. Run the importer with the new file:
   ```bash
   uv run python thesaurus_import_cli.py desc2026.xml --version 2026
   ```
3. The importer uses `ON CONFLICT` clauses to:
   - Update existing concepts
   - Add new concepts
   - Preserve existing terms
   - Add new hierarchies

**Note:** The import is additive and updates existing records. Old/obsolete terms are marked but not deleted.

## Troubleshooting

### Import Fails with Memory Error

**Symptom:** Process killed or out-of-memory error

**Solution:** Reduce batch size:
```bash
uv run python thesaurus_import_cli.py desc2025.xml --batch-size 25
```

### Slow Import Performance

**Symptom:** Import taking >30 minutes

**Solutions:**
1. Increase batch size (if memory allows):
   ```bash
   uv run python thesaurus_import_cli.py desc2025.xml --batch-size 200
   ```

2. Temporarily disable indexes:
   ```sql
   -- Drop indexes before import
   DROP INDEX thesaurus.idx_terms_text_gin;
   DROP INDEX thesaurus.idx_terms_concept_id;
   -- ... other indexes ...

   -- Run import

   -- Rebuild indexes after import
   CREATE INDEX idx_terms_text_gin ON thesaurus.terms USING GIN (to_tsvector('english', term_text));
   -- ... other indexes ...
   ```

3. Check database configuration:
   ```sql
   -- Increase work_mem for batch operations
   SET work_mem = '256MB';
   ```

### Import Completes with Errors

**Symptom:** Statistics show errors > 0

**Solutions:**
1. Review log output for specific error messages
2. Run with `--verbose` flag for detailed diagnostics:
   ```bash
   uv run python thesaurus_import_cli.py desc2025.xml --verbose
   ```
3. Check XML file integrity:
   ```bash
   xmllint --noout desc2025.xml
   ```

### Database Connection Errors

**Symptom:** "Failed to connect to database"

**Solutions:**
1. Verify PostgreSQL is running:
   ```bash
   pg_isready -h localhost -p 5432
   ```

2. Check environment variables in `.env`:
   ```bash
   cat .env | grep POSTGRES
   ```

3. Test connection manually:
   ```bash
   psql -h localhost -U your_user -d knowledgebase
   ```

### XML Parsing Errors

**Symptom:** "Invalid MeSH XML format"

**Solutions:**
1. Verify file is complete (not truncated):
   ```bash
   tail -20 desc2025.xml
   # Should end with </DescriptorRecordSet>
   ```

2. Check file size (should be ~350 MB):
   ```bash
   ls -lh desc2025.xml
   ```

3. Re-download if file appears corrupted

### Term Expansion Not Working

**Symptom:** Queries return no expanded terms

**Solutions:**
1. Verify data import:
   ```sql
   SELECT COUNT(*) FROM thesaurus.concepts;
   ```

2. Check term exists:
   ```sql
   SELECT * FROM thesaurus.expand_term('your_term');
   ```

3. Verify QueryAgent configuration:
   ```python
   from bmlibrarian.agents import QueryAgent
   agent = QueryAgent()
   print(f"Thesaurus enabled: {agent.use_thesaurus}")
   ```

4. Test expansion function directly:
   ```sql
   SELECT * FROM thesaurus.expand_term('aspirin');
   ```

## Performance Characteristics

### Import Performance

| Dataset Size | Batch Size | Duration | Rate |
|-------------|-----------|----------|------|
| 30,000 concepts | 100 | ~15 min | 33 concepts/sec |
| 30,000 concepts | 200 | ~12 min | 42 concepts/sec |
| 30,000 concepts | 50 | ~20 min | 25 concepts/sec |

### Query Performance

| Operation | Avg Time | Notes |
|-----------|----------|-------|
| Single term expansion | <5ms | With cache |
| Single term expansion | <15ms | Without cache |
| Query expansion (3 terms) | <20ms | With cache |
| Query expansion (10 terms) | <50ms | With cache |

### Storage Requirements

| Component | Size |
|-----------|------|
| MeSH XML file | ~350 MB |
| Database tables | ~150 MB |
| Database indexes | ~200 MB |
| **Total** | ~700 MB |

## Best Practices

### For Production Use

1. **Schedule Updates**: Run annual MeSH updates when released (typically December)
2. **Monitor Import**: Log import statistics to track data growth
3. **Backup Before Update**: Create database backup before running updates
4. **Test in Development**: Run dry-run and test imports in dev environment first
5. **Index Maintenance**: Rebuild indexes after large imports for optimal performance

### For Query Expansion

1. **Limit Expansions**: Use `max_expansions_per_term=10` to prevent query bloat
2. **Cache Warming**: Pre-expand common medical terms at startup
3. **Monitor Performance**: Track query expansion overhead in search logs
4. **Selective Expansion**: Only expand medical terms, not common words
5. **Combine with Filters**: Use thesaurus expansion with source/date filters

### For Development

1. **Use Dry Run**: Always test with `--dry-run` before importing to production
2. **Small Batches**: Use smaller batch sizes for easier debugging
3. **Verbose Logging**: Enable `--verbose` to understand import behavior
4. **Sample Data**: Create small test XML files for rapid iteration

## Next Steps

After successful import:

1. **Test Search Improvements**: Compare search results with and without thesaurus
2. **Analyze Expansion Quality**: Review expanded queries for relevance
3. **Tune Parameters**: Adjust `max_expansions_per_term` based on performance
4. **Monitor Usage**: Track thesaurus cache hit rates and expansion frequency
5. **User Feedback**: Gather feedback on search recall improvements

## Additional Resources

- **Developer Guide**: `doc/developers/thesaurus_schema_reference.md`
- **Integration Summary**: `doc/developers/thesaurus_integration_summary.md`
- **MeSH Documentation**: https://www.nlm.nih.gov/mesh/
- **QueryAgent Guide**: `doc/users/query_agent_guide.md`

## Support

For issues or questions:

1. Check troubleshooting section above
2. Review developer documentation for technical details
3. Examine import logs for error messages
4. Test expansion functions directly in PostgreSQL
5. Report issues with log output and statistics
