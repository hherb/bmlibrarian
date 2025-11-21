# Counterfactual Analysis Diagnostics

## Overview

The counterfactual agent now provides comprehensive diagnostic logging at each step of the analysis workflow. This allows you to verify and debug the search, scoring, citation extraction, and validation process.

## Diagnostic Information Logged

### 1. PostgreSQL Query Generation

**Callback**: `search_query`
**Log Level**: INFO
**Information**:
- The actual PostgreSQL tsquery used to search the database
- Allows verification that the query matches the counterfactual statement

**Example**:
```
INFO: PostgreSQL query: 'macrolide' & 'statin' & !'interact' & !'increase'
```

### 2. Document Search Results

**Callback**: `search_results`
**Log Level**: INFO
**Information**:
- Number of documents found by the database query
- Zero results indicate the query may be too restrictive or no matching documents exist

**Example**:
```
INFO: Documents found: 15
```

### 3. Document Scoring

**Callback**: `scoring_complete`
**Log Level**: INFO
**Information**:
- Number of documents that passed the relevance score threshold
- Shows ratio: `passed/total_found`
- Low pass rate may indicate:
  - Documents don't actually discuss the counterfactual topic
  - Score threshold is too high
  - Search query found off-topic documents

**Example**:
```
INFO: Documents passing score threshold (>=2.5): 8/15
```

### 4. Citation Extraction

**Log Level**: INFO
**Information**:
- Processing status for each document
- Document title being processed
- Whether citation was successfully extracted

**Example**:
```
INFO: Processing document 1/8: Safety of macrolide-statin combinations...
INFO:   ✓ Citation extracted from: Safety of macrolide-statin combinations
```

### 5. Citation Validation

**Log Level**: INFO
**Information**:
- Validation status for each extracted citation
- Whether the citation SUPPORTS the counterfactual statement
- Detailed passage analysis

**Example**:
```
INFO:   → Validating citation supports counterfactual...
INFO:   ✓ Citation VALIDATED (supports counterfactual)
```

OR

```
INFO:   → Validating citation supports counterfactual...
INFO:   ✗ Citation REJECTED (does not support counterfactual): Clarithromycin interactions with statins
```

### 6. Summary Statistics

**Callback**: `validation_complete`
**Log Level**: INFO
**Information**:
- Total citations extracted
- Total citations validated (passed validation)
- Total citations rejected (failed validation)

**Example**:
```
INFO: Citation extraction summary: Extracted=8, Validated=3, Rejected=5
```

## Complete Workflow Example

```
# Step 1: Search Query
INFO: PostgreSQL query: 'azithromycin' & 'atorvastatin' & 'safe' & !'interaction'

# Step 2: Search Results
INFO: Documents found: 12

# Step 3: Scoring
INFO: Documents passing score threshold (>=2.5): 7/12

# Step 4: Citation Extraction
INFO: Processing top 7 documents for citation extraction
INFO: Processing document 1/7: Safety assessment of azithromycin with statins
INFO:   ✓ Citation extracted from: Safety assessment of azithromycin with statins

# Step 5: Validation
INFO:   → Validating citation supports counterfactual...
INFO:   ✓ Citation VALIDATED (supports counterfactual)

INFO: Processing document 2/7: Clarithromycin increases statin exposure...
INFO:   ✓ Citation extracted from: Clarithromycin increases statin exposure
INFO:   → Validating citation supports counterfactual...
INFO:   ✗ Citation REJECTED (does not support counterfactual): Clarithromycin increases statin exposure

# ... (continues for remaining documents)

# Step 6: Summary
INFO: Citation extraction summary: Extracted=7, Validated=2, Rejected=5
```

## Interpreting the Results

### No Documents Found

```
INFO: Documents found: 0
```

**Possible causes**:
1. PostgreSQL query is too restrictive (too many required terms)
2. No documents in database match the counterfactual statement
3. Counterfactual statement uses terms not present in the literature

**Solutions**:
- Review the PostgreSQL query - are there negation operators (!) that exclude too much?
- Try a broader counterfactual statement
- Check if synonyms or alternative phrasings exist in the literature

### Documents Found But None Pass Scoring

```
INFO: Documents found: 20
INFO: Documents passing score threshold (>=2.5): 0/20
```

**Possible causes**:
1. Documents are topically related but don't actually address the counterfactual
2. Score threshold is too high
3. Counterfactual statement is poorly formed

**Solutions**:
- Lower the score threshold temporarily to see what documents are found
- Review the counterfactual statement - is it clear and specific?
- Check if the documents are truly relevant to the topic

### Citations Extracted But All Rejected

```
INFO: Citation extraction summary: Extracted=8, Validated=0, Rejected=8
```

**Possible causes**:
1. **Most likely**: Citations support the ORIGINAL claim, not the counterfactual
2. This indicates the search/scoring found topically related documents
3. No actual contradictory evidence exists in the database

**Solutions**:
- This is the validation working correctly - filtering out invalid "contradictory" evidence
- Review the rejected citation passages to understand what was found
- Consider that the original claim may be well-established with little contradictory evidence

### Successful Validation

```
INFO: Citation extraction summary: Extracted=5, Validated=3, Rejected=2
```

**Interpretation**:
- 3 citations genuinely support the counterfactual statement
- 2 citations were topically related but supported the original claim
- This is ideal - shows both the search and validation are working correctly

## Debugging Tips

### Enable Debug Logging

To see even more detailed information, enable DEBUG level logging:

```python
import logging
logging.getLogger('bmlibrarian.agents.counterfactual_agent').setLevel(logging.DEBUG)
```

### Check Validation Reasoning

The validation method includes detailed reasoning. To see this:

```python
# In counterfactual_agent.py, line 1086:
logger.debug(f"Citation validation: {supports} - {reasoning}")

# Change to INFO level to always see it:
logger.info(f"Citation validation: {supports} - {reasoning}")
```

### Review PostgreSQL Query

The query is logged at INFO level. Check if it's using:
- **Negation operators (!)**: May exclude too much
- **Too many required terms (&)**: May be too restrictive
- **OR operators (|)**: May be too broad

### Manual Verification

For each rejected citation:
1. Read the passage that was extracted
2. Compare it to the counterfactual statement
3. Verify the validation made the correct decision

## Files Modified

- `src/bmlibrarian/agents/counterfactual_agent.py`: Added comprehensive logging at each workflow step

## Related Documentation

- See `COUNTERFACTUAL_VALIDATION_FIX.md` for validation logic details
- See `COUNTERFACTUAL_FIX_SUMMARY.md` for statement-based search approach
