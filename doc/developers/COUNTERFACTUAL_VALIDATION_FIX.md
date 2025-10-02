# Counterfactual Citation Validation and Display Fix

## The Critical Problem: Invalid "Contradictory" Evidence

The counterfactual agent had a fatal flaw: it would include citations that **SUPPORTED the original claim** as "contradictory evidence" rather than finding citations that actually contradicted it.

### Example of the Bug

- **Original Claim**: "Macrolides interact with statins via CYP3A4, leading to increased statin exposure and myopathy risk"
- **Counterfactual Statement**: "Macrolides do NOT interact with statins and do NOT increase statin exposure or myopathy risk"
- **Passage Found**: "Clarithromycin increases simvastatin exposure >5-fold and caused rhabdomyolysis in 14 cases"
- **BUG**: This passage CONTRADICTS the counterfactual (confirms the original claim), yet was labeled as "contradictory evidence"!

## Root Cause Analysis

The workflow was:
1. ✓ Generate counterfactual statement (correct)
2. ✓ Search for documents using counterfactual keywords (finds topically relevant documents)
3. ✓ Score documents for relevance to counterfactual topic (finds documents about the topic)
4. ✗ **Extract citations** - Citation agent extracted passages about the topic, regardless of whether they supported or contradicted the counterfactual
5. ✗ **No validation** - No check to verify the passage actually supports the counterfactual claim

**The Problem**: Both the ScoringAgent and CitationAgent measure **topical relevance**, not **agreement/support**. A document about "macrolides and statins" is highly relevant to BOTH:
- "Macrolides increase statin risk" (original)
- "Macrolides don't increase statin risk" (counterfactual)

So the system would find the most authoritative papers on the topic, which typically **confirm the consensus view** (the original claim), not challenge it.

## The Solution: Citation Validation

Added a validation step that explicitly checks if each extracted passage actually **supports** the counterfactual statement.

### New Method: `_validate_citation_supports_counterfactual`

**File**: `src/bmlibrarian/agents/counterfactual_agent.py`

```python
def _validate_citation_supports_counterfactual(
    self,
    passage: str,
    summary: str,
    counterfactual_statement: str,
    original_claim: str
) -> bool:
    """
    Validate that a citation actually SUPPORTS the counterfactual statement.

    Uses LLM to analyze if the passage provides evidence FOR the counterfactual
    or if it merely discusses the topic without supporting it (or contradicts it).
    """
```

### Validation Logic

The validation prompt explicitly asks:

```
COUNTERFACTUAL CLAIM (what we're trying to prove):
{counterfactual_statement}

PASSAGE FROM DOCUMENT:
{passage}

TASK: Does this passage actually SUPPORT the counterfactual claim above?

IMPORTANT:
- Return "YES" ONLY if the passage provides evidence that SUPPORTS the counterfactual claim
- Return "NO" if the passage:
  * Contradicts the counterfactual claim (supports the original claim instead)
  * Is merely topically related without taking a position
  * Discusses the topic but doesn't provide evidence for the counterfactual
```

### Integration into Workflow

```python
# After extracting citation
citation = citation_agent.extract_citation_from_document(
    query_info['counterfactual_statement'], doc, min_relevance=0.4
)

if citation:
    # CRITICAL VALIDATION: Verify the passage actually SUPPORTS the counterfactual
    supports_counterfactual = self._validate_citation_supports_counterfactual(
        citation.passage,
        citation.summary,
        query_info['counterfactual_statement'],
        query_info['target_claim']
    )

    if supports_counterfactual:
        contradictory_citations.append(citation)  # ✓ Valid contradictory evidence
    else:
        logger.info(f"Skipping citation that doesn't support counterfactual")  # ✗ Filtered out
```

## Additional Improvements

### 1. Enhanced Citation Data Structure

Added complete metadata to enable verification:

```python
{
    'title': citation.document_title,
    'passage': citation.passage,  # ACTUAL quoted text
    'summary': citation.summary,  # LLM interpretation
    'authors': citation.authors,
    'publication_date': citation.publication_date,
    'pmid': citation.pmid,
    'doi': citation.doi,
    'publication': citation.publication,
    'relevance_score': citation.relevance_score,
    'document_score': document_score,
    'score_reasoning': score_reasoning
}
```

### 2. Improved Display (GUI, CLI, Reports)

All interfaces now show:
- **Full citation metadata**: "Authors et al. (Year) | Journal | PMID: xxx | DOI: xxx"
- **Passage text**: The actual quoted passage from the document
- **Summary**: LLM's interpretation (shown separately)
- **Clear labels**: Distinguish between passage and summary

### 3. Graceful Handling of Missing Counterfactual Statements

Changed from strict validation (raises error) to lenient handling:

```python
# OLD: Would fail entire analysis if LLM didn't generate counterfactual
if field not in q_data:
    raise ValueError(f"Missing required question field: {field}")

# NEW: Skips problematic questions with warning
counterfactual_statement = q_data.get('counterfactual_statement', '')
if not counterfactual_statement:
    logger.warning(f"No counterfactual_statement for claim, skipping")
    continue
```

User-facing message:
```
Counterfactual Statement: (No counterfactual statement generated - claim may be too complex or lack specificity)
```

## Testing the Fix

Created `test_citation_validation.py` to verify the validation logic with the real problematic example.

### Expected Behavior

**Counterfactual**: "Macrolides do NOT interact with statins..."

**Passage 1** (should be REJECTED):
```
"Clarithromycin increases simvastatin exposure >5-fold and caused rhabdomyolysis in 14 cases"
```
→ Validation Result: `False` - Passage contradicts counterfactual

**Passage 2** (should be ACCEPTED):
```
"In our large cohort study, azithromycin co-prescription with statins showed no significant increase in myopathy risk (RR 1.02, 95% CI 0.95-1.09)"
```
→ Validation Result: `True` - Passage supports counterfactual

## Impact

This fix ensures:
1. ✓ Only citations that actually **support** the counterfactual are included
2. ✓ Citations that confirm the original claim are **filtered out**
3. ✓ Users can **verify** evidence using passage text and metadata
4. ✓ The counterfactual analysis provides **genuine alternative perspectives**
5. ✓ Analysis doesn't fail when LLM can't generate counterfactuals for complex claims

## Files Modified

1. `src/bmlibrarian/agents/counterfactual_agent.py`:
   - Added `_validate_citation_supports_counterfactual()` method
   - Integrated validation into citation extraction workflow
   - Enhanced citation data structure with full metadata
   - Made counterfactual statement validation more lenient

2. `src/bmlibrarian/gui/display_utils.py`:
   - Show passage text and full metadata
   - Better handling of missing counterfactual statements

3. `src/bmlibrarian/cli/formatting.py`:
   - Enhanced CLI output with passage and metadata

4. `src/bmlibrarian/gui/report_builder.py`:
   - Improved markdown report generation

5. `test_citation_validation.py` (new):
   - Test suite for validation logic

## Performance Considerations

The validation step adds one additional LLM call per citation (up to 10 citations per counterfactual analysis). With `num_predict=300` and `temperature=0.1`, each validation is fast (~1-2 seconds).

This overhead is acceptable given:
- It prevents including invalid "contradictory" evidence
- Citations are limited to top 10 per analysis
- Validation failures default to False for safety

## Future Enhancements

Potential improvements:
1. **Batch validation**: Validate multiple citations in a single LLM call
2. **Confidence scores**: Return confidence level instead of binary true/false
3. **Caching**: Cache validation results for repeated passages
4. **Alternative validation**: Use embedding similarity as a fast pre-filter

## Related Documentation

- See `COUNTERFACTUAL_FIX_SUMMARY.md` for statement-based search refactoring
- All improvements work together to enhance counterfactual analysis accuracy
