# Citation Extraction Debugging Guide

## Issue

Citations are not being extracted even when high-scoring documents are available. The workflow seems to skip the citation extraction step entirely.

## Root Cause Investigation

The citation extraction step can be skipped for several reasons:

### 1. No High-Scoring Documents

**Location**: [workflow.py:379-416](src/bmlibrarian/gui/workflow.py#L379-L416)

If there are **zero** documents above the score threshold, the workflow returns early:

```python
if len(high_scoring_docs) == 0:
    print(f"\n⚠️  CRITICAL: No documents scored above threshold {score_threshold}")
    print(f"    Cannot proceed to citation extraction without relevant documents")
    # ...
    return  # Halt workflow
```

**Fix**: Ensure at least one document scores above the threshold (default: 2.5)

### 2. Workflow Not Reaching Citation Step

The citation extraction happens at line 490+. To verify it's reached, check for these console messages:

```
✓ Found X documents above threshold - proceeding to citation extraction
📍 Interactive mode: False - skipping user approval step
🔍 CITATION EXTRACTION STEP:
   About to extract citations from Y scored documents
   High-scoring (>=threshold): Z
🚀 Calling execute_citation_extraction()...
```

If you don't see these messages, the workflow stopped before reaching citation extraction.

### 3. Citation Extraction Returns Empty

If you see:
```
🚀 Calling execute_citation_extraction()...
✅ execute_citation_extraction() returned 0 citations
```

The extraction ran but found no relevant passages. This could be due to:
- Documents don't contain relevant information
- Score threshold too high (no documents passed)
- Citation extraction agent error

## Diagnostic Logging Added

### Workflow.py Changes

**Line 418**: Confirms proceeding to citation extraction
```python
print(f"✓ Found {len(high_scoring_docs)} documents above threshold - proceeding to citation extraction")
```

**Line 487**: Confirms skipping interactive mode
```python
print(f"📍 Interactive mode: False - skipping user approval step")
```

**Lines 490-492**: Pre-citation extraction info
```python
print(f"\n🔍 CITATION EXTRACTION STEP:")
print(f"   About to extract citations from {len(scored_documents)} scored documents")
print(f"   High-scoring (>={score_threshold}): {len([d for d, s in scored_documents if s.get('score', 0) >= score_threshold])}")
```

**Line 531**: Citation extraction call
```python
print(f"🚀 Calling execute_citation_extraction()...")
```

**Line 536**: Citation extraction result
```python
print(f"✅ execute_citation_extraction() returned {len(citations) if citations else 0} citations")
```

## Expected Console Output

### Successful Citation Extraction

```
✓ Found 1 documents above threshold - proceeding to citation extraction
📍 Interactive mode: False - skipping user approval step

🔍 CITATION EXTRACTION STEP:
   About to extract citations from 62 scored documents
   High-scoring (>=2.5): 1
🚀 Calling execute_citation_extraction()...
[... citation extraction progress ...]
✅ execute_citation_extraction() returned 5 citations
📝 Workflow stored 5 citations for tab access
🔄 Triggering manual tab update for EXTRACT_CITATIONS
```

### Workflow Halted (No High-Scoring Docs)

```
🔍 SCORING VALIDATION:
   Total scored documents: 62
   Score threshold: 2.5
   Documents above threshold: 0
   Interactive mode: False

⚠️  CRITICAL: No documents scored above threshold 2.5
    Cannot proceed to citation extraction without relevant documents
❌ Auto mode: Halting workflow due to insufficient scoring results
```

### Citation Extraction Ran But Found Nothing

```
✓ Found 1 documents above threshold - proceeding to citation extraction
📍 Interactive mode: False - skipping user approval step

🔍 CITATION EXTRACTION STEP:
   About to extract citations from 62 scored documents
   High-scoring (>=2.5): 1
🚀 Calling execute_citation_extraction()...
[... no progress updates ...]
✅ execute_citation_extraction() returned 0 citations
📝 Workflow stored 0 citations for tab access
```

## Troubleshooting Steps

### Step 1: Check Score Distribution

Look for this in the console output:
```
📊 Score distribution:
   1. Document Title... Score: X.X
   2. Another Document... Score: X.X
```

**Action**: If all scores are ≤ threshold, either:
- Lower the score threshold in config
- Manually adjust scores in the GUI scoring tab
- Refine your research question

### Step 2: Verify High-Scoring Count

Look for:
```
✅ High-scoring documents (> 2.5): 1
```

**Action**: If 0, no citations can be extracted. Adjust threshold or scores.

### Step 3: Check If Citation Step Reached

Look for:
```
🔍 CITATION EXTRACTION STEP:
   About to extract citations from...
```

**Action**: If missing, workflow stopped early. Check earlier logs for errors.

### Step 4: Check Citation Extraction Result

Look for:
```
✅ execute_citation_extraction() returned X citations
```

**Action**:
- If 0 citations with high-scoring docs, check citation agent logs
- If message missing, citation extraction crashed (check errors)

### Step 5: Check Tab Update

Look for:
```
📚 Found X citations in workflow_executor
✅ Updating Citations tab with X citations
```

**Action**: If 0 citations, review previous steps. If citations exist but tab not updating, check data_updaters logs.

## Common Issues

### Issue 1: Only 1 High-Scoring Document

**Symptom**: Workflow shows "Found only 1/10 documents above threshold"

**Impact**: Iterative search triggered, which may cause delay but shouldn't prevent citation extraction

**Solution**: Citation extraction should still proceed with the 1 document. Check for the "🔍 CITATION EXTRACTION STEP" log.

### Issue 2: Interactive Mode Interference

**Symptom**: Workflow waits for button click even in auto mode

**Impact**: User must click "Continue Workflow" button

**Solution**: Verify `human_in_loop: False` in console. Should see "📍 Interactive mode: False" log.

### Issue 3: Empty Citation Results

**Symptom**: Citation extraction runs but returns 0 citations

**Possible Causes**:
- Document abstracts too short or generic
- Research question too specific
- Citation agent threshold too strict
- Agent error (check logs for exceptions)

**Solution**:
- Check citation agent configuration
- Try with different research question
- Review high-scoring document abstracts manually

## Files Modified

1. **[src/bmlibrarian/gui/workflow.py](src/bmlibrarian/gui/workflow.py)** (lines 418, 487, 490-492, 531, 536)
   - Added comprehensive logging before, during, and after citation extraction

## Related Documentation

- [SCORING_TAB_ITERATIVE_SEARCH_FIX.md](SCORING_TAB_ITERATIVE_SEARCH_FIX.md) - Scoring tab update issues
- [SCORING_TAB_DEBUG_GUIDE.md](SCORING_TAB_DEBUG_GUIDE.md) - Scoring diagnostics

## Next Steps

1. **Run the GUI** with the new logging:
   ```bash
   uv run python bmlibrarian_research_gui.py
   ```

2. **Execute your query** and watch for the new log messages

3. **Share the console output** especially the sections:
   - "🔍 SCORING VALIDATION:"
   - "✓ Found X documents above threshold"
   - "🔍 CITATION EXTRACTION STEP:"
   - "🚀 Calling execute_citation_extraction()..."
   - "✅ execute_citation_extraction() returned..."

This will help identify exactly where and why citation extraction is not happening.
