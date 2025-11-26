# MeSH Data Structure Analysis for Medical Thesaurus System

**Date**: 2025-11-26
**Purpose**: Inform database schema design for BMLibrarian medical thesaurus
**Source**: MeSH 2025 XML format analysis

## Executive Summary

This document presents findings from analyzing the MeSH (Medical Subject Headings) XML structure to inform the design of BMLibrarian's medical thesaurus system. MeSH provides comprehensive biomedical terminology with synonyms, abbreviations, and hierarchical relationships ideal for keyword expansion in literature search.

## MeSH Data Sources

### Official Download Locations

- **Primary Source**: [NLM MeSH Download Page](https://www.nlm.nih.gov/databases/download/mesh.html)
- **Release Announcement**: [2025 MeSH Release](https://www.nlm.nih.gov/pubs/techbull/nd24/brief/nd24_annual_mesh_processing.html)
- **Available Formats**: XML, RDF, ASCII, MARC 21
- **Update Schedule**:
  - Descriptors & Qualifiers: Annual (January)
  - Supplemental Concept Records (SCR): Daily (Monday-Friday)

### Key MeSH Files

1. **desc2025.xml** - Descriptors (~30,000 main medical concepts)
2. **supp2025.xml** - Supplementary Concept Records (~400,000 additional terms)
3. **qual2025.xml** - Qualifiers (~80 subheadings for indexing)

### Access Considerations

- **Note**: NLM website blocks automated downloads (403 Forbidden)
- **Solution**: Manual download or institutional access may be required
- **License**: Public domain for research use
- **Size**: Complete MeSH XML ~300-500 MB

## MeSH XML Structure Analysis

### Sample Analysis Results

From representative sample of 4 descriptors (Myocardial Infarction, Aspirin, C-Reactive Protein, Percutaneous Coronary Intervention):

**Term Type Distribution**:
- Synonyms (SYN): 9 terms (41%)
- Abbreviations (ABB): 7 terms (32%)
- Preferred Terms (NON): 4 terms (18%)
- Trade Names (TRD): 2 terms (9%)

**Average Terms per Descriptor**: 5.5 terms
**Range**: 5-6 terms per descriptor in sample

### XML Element Hierarchy

```
DescriptorRecord
├── DescriptorUI (unique ID: e.g., "D009203")
├── DescriptorName
│   └── String (preferred term)
├── DescriptorClass (semantic type indicator)
├── DateCreated, DateRevised, DateEstablished
├── ActiveMeSHYearList
├── Annotation (indexing notes)
├── ConceptList
│   └── Concept (one or more)
│       ├── ConceptUI (e.g., "M0014343")
│       ├── ConceptName
│       ├── ScopeNote (definition)
│       ├── TermList
│       │   └── Term (multiple)
│       │       ├── TermUI (e.g., "T000745")
│       │       ├── String (actual term text)
│       │       ├── LexicalTag (NON, ABB, SYN, TRD)
│       │       ├── RecordPreferredTermYN
│       │       └── ConceptPreferredTermYN
│       └── ConceptRelationList (relationships between concepts)
└── TreeNumberList (hierarchical classification)
    └── TreeNumber (e.g., "C14.280.647.500")
```

### Lexical Tags (Term Types)

| Tag | Meaning | Use Case | Example |
|-----|---------|----------|---------|
| **NON** | Preferred Term | Main entry term | "Myocardial Infarction" |
| **ABB** | Abbreviation | Acronyms and short forms | "MI", "AMI", "CRP" |
| **SYN** | Synonym | Alternative names | "Heart Attack" |
| **TRD** | Trade Name | Brand/commercial names | "Bayer Aspirin", "Ecotrin" |

### Real-World Examples

#### Example 1: Myocardial Infarction (Disease)
```
Descriptor ID: D009203
Preferred Term: Myocardial Infarction
Definition: NECROSIS of the MYOCARDIUM caused by obstruction of blood supply

Term Expansion:
- Abbreviations: MI, AMI
- Synonyms: Heart Attack, Cardiac Infarction, Myocardial Infarct
- ALL TERMS: [Myocardial Infarction, MI, Heart Attack, Cardiac Infarction,
               Myocardial Infarct, AMI]

Tree Numbers: C14.280.647.500, C14.907.585.500, C23.550.513.355
(C = Diseases category)
```

#### Example 2: Aspirin (Drug)
```
Descriptor ID: D001241
Preferred Term: Aspirin
Definition: Prototypical analgesic with anti-inflammatory and antipyretic properties

Term Expansion:
- Abbreviation: ASA
- Synonyms: Acetylsalicylic Acid, 2-Acetoxybenzoic Acid
- Trade Names: Bayer Aspirin, Ecotrin
- ALL TERMS: [Aspirin, Acetylsalicylic Acid, 2-Acetoxybenzoic Acid, ASA,
               Bayer Aspirin, Ecotrin]

Tree Numbers: D02.455.426.559.389.657.056, D03.383.663.283.446.056
(D = Chemicals and Drugs category)
```

#### Example 3: C-Reactive Protein (Lab Test)
```
Descriptor ID: D002097
Preferred Term: C-Reactive Protein
Definition: Plasma protein elevated during inflammation and tissue damage

Term Expansion:
- Abbreviations: CRP, hs-CRP
- Synonyms: High-Sensitivity C-Reactive Protein, Acute Phase Protein
- ALL TERMS: [C-Reactive Protein, CRP, hs-CRP,
               High-Sensitivity C-Reactive Protein, Acute Phase Protein]

Tree Numbers: D12.776.124.125.350, D12.776.124.486.274, D23.119.190
```

#### Example 4: Percutaneous Coronary Intervention (Procedure)
```
Descriptor ID: D062645
Preferred Term: Percutaneous Coronary Intervention
Definition: Percutaneous techniques for managing coronary occlusion

Term Expansion:
- Abbreviations: PCI, PTCA
- Synonyms: Coronary Angioplasty, Percutaneous Transluminal Coronary Angioplasty
- ALL TERMS: [Percutaneous Coronary Intervention, PCI, Coronary Angioplasty,
               PTCA, Percutaneous Transluminal Coronary Angioplasty]

Tree Numbers: E04.100.814.868.500, E04.928.220.520
(E = Analytical, Diagnostic and Therapeutic Techniques category)
```

## MeSH Tree Number System

### Hierarchical Classification

Tree numbers represent hierarchical placement in MeSH ontology:

```
C14.280.647.500
 │  │    │   └── Specific level 4
 │  │    └────── Level 3
 │  └─────────── Level 2
 └────────────── Top level category (C = Diseases)
```

### Top-Level Categories

- **A**: Anatomical terms
- **C**: Diseases
- **D**: Chemicals and Drugs
- **E**: Analytical, Diagnostic and Therapeutic Techniques
- **F**: Psychiatry and Psychology
- **G**: Phenomena and Processes
- **... and others**

### Use for Relationships

- **Broader terms**: Remove last segment (e.g., C14.280.647.500 → C14.280.647)
- **Narrower terms**: Add segments or find children at same level
- **Related terms**: Concepts sharing partial tree paths

## Schema Design Implications

### Key Requirements Identified

1. **Bidirectional Lookup**
   - Input any term (preferred, synonym, abbreviation) → find concept
   - Get all variants for a concept

2. **Term Type Preservation**
   - Store original lexical tags (NON, ABB, SYN, TRD)
   - Map to simplified types: preferred, synonym, abbreviation, trade_name

3. **Definition Storage**
   - ScopeNote contains valuable context for disambiguation
   - Essential for semantic search enhancement

4. **Hierarchical Navigation**
   - Tree numbers enable broader/narrower term discovery
   - Support ontology-aware query expansion

5. **Source Provenance**
   - Track DescriptorUI for updates and version control
   - Record TermUI for granular term tracking

### Recommended Tables

#### 1. thesaurus.concepts
```sql
CREATE TABLE thesaurus.concepts (
    concept_id SERIAL PRIMARY KEY,
    preferred_term TEXT NOT NULL,
    definition TEXT,
    semantic_type TEXT,  -- Derived from tree numbers or descriptor class
    source_vocabulary TEXT NOT NULL DEFAULT 'mesh',
    source_concept_id TEXT NOT NULL,  -- DescriptorUI like 'D009203'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_vocabulary, source_concept_id)
);
```

#### 2. thesaurus.terms
```sql
CREATE TABLE thesaurus.terms (
    term_id SERIAL PRIMARY KEY,
    concept_id INTEGER NOT NULL REFERENCES thesaurus.concepts(concept_id) ON DELETE CASCADE,
    term_text TEXT NOT NULL,
    term_type TEXT NOT NULL,  -- 'preferred', 'synonym', 'abbreviation', 'trade_name'
    lexical_tag TEXT,  -- Original MeSH tag: NON, ABB, SYN, TRD
    case_sensitive BOOLEAN DEFAULT FALSE,
    source_term_id TEXT,  -- TermUI like 'T000745'
    language TEXT DEFAULT 'en',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### 3. thesaurus.concept_hierarchies
```sql
CREATE TABLE thesaurus.concept_hierarchies (
    hierarchy_id SERIAL PRIMARY KEY,
    concept_id INTEGER NOT NULL REFERENCES thesaurus.concepts(concept_id) ON DELETE CASCADE,
    tree_number TEXT NOT NULL,  -- e.g., 'C14.280.647.500'
    tree_level INTEGER,  -- Calculated depth (4 for example above)
    UNIQUE(concept_id, tree_number)
);
```

#### 4. thesaurus.import_history
```sql
CREATE TABLE thesaurus.import_history (
    import_id SERIAL PRIMARY KEY,
    source_vocabulary TEXT NOT NULL,
    source_version TEXT,  -- e.g., '2025'
    import_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    records_imported INTEGER,
    notes TEXT
);
```

### Essential Indexes

```sql
-- Fast term lookup (case-insensitive)
CREATE INDEX idx_terms_text_lower ON thesaurus.terms(LOWER(term_text));

-- Full-text search support
CREATE INDEX idx_terms_text_gin ON thesaurus.terms
    USING gin(to_tsvector('english', term_text));

-- Concept lookup
CREATE INDEX idx_terms_concept ON thesaurus.terms(concept_id);

-- Source tracking
CREATE INDEX idx_concepts_source ON thesaurus.concepts(source_vocabulary, source_concept_id);

-- Hierarchical queries
CREATE INDEX idx_hierarchies_tree ON thesaurus.concept_hierarchies(tree_number);
CREATE INDEX idx_hierarchies_concept ON thesaurus.concept_hierarchies(concept_id);
```

### Utility Functions

```sql
-- Expand any term to all variants
CREATE OR REPLACE FUNCTION thesaurus.get_all_synonyms(input_term TEXT)
RETURNS TABLE(synonym TEXT, term_type TEXT) AS $$
BEGIN
    RETURN QUERY
    WITH matched_concepts AS (
        SELECT DISTINCT c.concept_id
        FROM thesaurus.terms t
        JOIN thesaurus.concepts c ON t.concept_id = c.concept_id
        WHERE LOWER(t.term_text) = LOWER(input_term)
    )
    SELECT DISTINCT
        t.term_text AS synonym,
        t.term_type
    FROM thesaurus.terms t
    WHERE t.concept_id IN (SELECT concept_id FROM matched_concepts)
      AND LOWER(t.term_text) != LOWER(input_term);
END;
$$ LANGUAGE plpgsql;

-- Get broader terms via tree hierarchy
CREATE OR REPLACE FUNCTION thesaurus.get_broader_terms(input_term TEXT)
RETURNS TABLE(broader_term TEXT, tree_number TEXT) AS $$
BEGIN
    RETURN QUERY
    WITH input_concepts AS (
        SELECT DISTINCT c.concept_id, h.tree_number
        FROM thesaurus.terms t
        JOIN thesaurus.concepts c ON t.concept_id = c.concept_id
        JOIN thesaurus.concept_hierarchies h ON c.concept_id = h.concept_id
        WHERE LOWER(t.term_text) = LOWER(input_term)
    ),
    broader_trees AS (
        SELECT
            substring(tree_number from '^(.+)\.[^.]+$') AS parent_tree
        FROM input_concepts
        WHERE tree_number ~ '\.'  -- Has at least one dot
    )
    SELECT DISTINCT
        c.preferred_term AS broader_term,
        h.tree_number
    FROM thesaurus.concept_hierarchies h
    JOIN thesaurus.concepts c ON h.concept_id = c.concept_id
    WHERE h.tree_number IN (SELECT parent_tree FROM broader_trees);
END;
$$ LANGUAGE plpgsql;
```

## Integration Strategy

### Phase 1: QueryAgent Enhancement

```python
# In query_agent.py
def expand_query_terms(self, user_question: str) -> List[str]:
    """Expand medical terms using thesaurus."""
    # 1. Extract key medical terms from question
    # 2. Query thesaurus.get_all_synonyms() for each term
    # 3. Generate expanded query variants
    # 4. Return list of query variations
    pass
```

### Phase 2: Search Function Integration

```sql
-- Enhanced search with automatic expansion
CREATE OR REPLACE FUNCTION public.search_documents_with_thesaurus(
    p_search_query TEXT,
    p_expand_terms BOOLEAN DEFAULT TRUE,
    p_max_results INTEGER DEFAULT 100
) RETURNS TABLE(...) AS $$
DECLARE
    v_expanded_terms TEXT[];
    v_search_tsquery tsquery;
BEGIN
    IF p_expand_terms THEN
        -- Extract medical terms and expand
        SELECT array_agg(DISTINCT synonym)
        INTO v_expanded_terms
        FROM thesaurus.get_all_synonyms(p_search_query);

        -- Combine original + expanded terms with OR logic
        v_search_tsquery := to_tsquery('english',
            array_to_string(v_expanded_terms, ' | '));
    ELSE
        v_search_tsquery := plainto_tsquery('english', p_search_query);
    END IF;

    -- Execute search with expanded query
    RETURN QUERY
    SELECT * FROM public.documents
    WHERE abstract_tsvector @@ v_search_tsquery
    ORDER BY ts_rank(abstract_tsvector, v_search_tsquery) DESC
    LIMIT p_max_results;
END;
$$ LANGUAGE plpgsql;
```

### Phase 3: HyDE Generator Enhancement

```python
# In paperchecker/components/hyde_generator.py
def generate_with_term_expansion(self, statement: str) -> str:
    """Generate HyDE with medical term expansion."""
    # 1. Extract medical terms from statement
    # 2. Get abbreviation expansions (MI → Myocardial Infarction)
    # 3. Include both forms in generated abstract
    # 4. Improves semantic search recall
    pass
```

## Performance Considerations

### Expected Scale

- **MeSH Descriptors**: ~30,000 concepts
- **Total Terms**: ~300,000 terms (avg 10 terms per concept)
- **Supplementary Concepts**: ~400,000 additional (if imported)
- **Total Database Size**: ~100-200 MB (with indexes)

### Optimization Strategies

1. **Materialized View for Common Expansions**
   ```sql
   CREATE MATERIALIZED VIEW thesaurus.common_expansions AS
   SELECT
       t.term_text AS input_term,
       array_agg(t2.term_text) AS all_variants,
       array_agg(t2.term_type) AS variant_types
   FROM thesaurus.terms t
   JOIN thesaurus.terms t2 ON t.concept_id = t2.concept_id
   GROUP BY t.term_text, t.concept_id;

   CREATE INDEX idx_common_expansions_input
       ON thesaurus.common_expansions(LOWER(input_term));
   ```

2. **Query Result Caching** (application level)
   - Cache expansion results with TTL (e.g., 1 hour)
   - Reduce database load for repeated queries

3. **Partial Loading** (if needed)
   - Import only high-frequency medical terms initially
   - Expand coverage based on usage patterns

## Next Steps

1. ✅ **Completed**: Analyzed MeSH XML structure
2. **Next**: Create migration script (`0XX_create_thesaurus_schema.sql`)
3. **Then**: Build MeSH XML importer (`thesaurus_import_cli.py`)
4. **Following**: Integrate with QueryAgent
5. **Finally**: Add configuration and documentation

## References

- [MeSH Download Page](https://www.nlm.nih.gov/databases/download/mesh.html)
- [2025 MeSH Release Notes](https://www.nlm.nih.gov/pubs/techbull/nd24/brief/nd24_annual_mesh_processing.html)
- [MeSH XML Data Elements](https://www.nlm.nih.gov/mesh/xml_data_elements.html)
- [Introduction to MeSH in XML](https://www.nlm.nih.gov/mesh/xmlmesh.html)

## Appendix: Sample Data Location

Analysis artifacts stored in `/tmp/mesh_analysis/`:
- `mesh_sample.xml` - Representative MeSH XML sample
- `analyze_mesh.py` - Python analysis script
- `mesh_analysis.json` - Detailed JSON output

---

**Document Version**: 1.0
**Last Updated**: 2025-11-26
**Author**: BMLibrarian Development Team
