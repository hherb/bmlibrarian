# Verify Orphaned PDF Matching Is Working

## Issue
PDFs in the `failed/` subdirectory are not being moved when running `match_orphaned_pdfs.py`.

## Checklist

### 1. Are you running in DRY RUN mode?

**Dry run (NO files moved):**
```bash
python match_orphaned_pdfs.py --dry-run
```

**Actual execution (FILES WILL BE MOVED):**
```bash
python match_orphaned_pdfs.py
```

⚠️ **If you use `--dry-run`, NO FILES WILL BE MOVED!**

### 2. Check the output carefully

**Dry run output:**
```
✓ Dry run completed. Use without --dry-run to link PDFs.
   52 PDFs would be linked to documents.

⚠️  IMPORTANT: No files were moved (dry-run mode)
   To actually move and link PDFs, run:
   python match_orphaned_pdfs.py
```

**Actual execution output:**
```
✓ Matching completed!
   ✅ 52 orphaned PDFs moved and linked to documents.
   📁 PDFs have been moved from their original locations to year-based directories.
```

### 3. Verify files were moved

**Before running (check failed directory):**
```bash
ls ~/knowledgebase/pdf/failed/ | head -5
```

**Run without dry-run:**
```bash
uv run python match_orphaned_pdfs.py
```

**After running (check if files moved):**
```bash
# Failed directory should have fewer files
ls ~/knowledgebase/pdf/failed/ | wc -l

# Year directories should have new files
ls ~/knowledgebase/pdf/2020/ | grep "10.1101"
ls ~/knowledgebase/pdf/2022/ | grep "10.1101"
```

### 4. Check for errors

If files are NOT being moved even without `--dry-run`:

1. **Check database connection:**
   - Are you connected to the correct database?
   - Do you have write permissions?

2. **Check file system permissions:**
   ```bash
   ls -la ~/knowledgebase/pdf/failed/ | head -5
   ```
   - Can you write to the year directories?

3. **Check logs for errors:**
   - Look for error messages in the output
   - Check `--verbose` mode for details

4. **Run with verbose to see what's happening:**
   ```bash
   uv run python match_orphaned_pdfs.py --verbose
   ```

### 5. Test with one file

To test if the move logic works:

```bash
# Create a test PDF in failed directory
cd ~/knowledgebase/pdf/failed/
ls | head -1  # Note the filename

# Run matching (NOT dry-run)
uv run python match_orphaned_pdfs.py

# Check if it moved
ls ~/knowledgebase/pdf/failed/ | grep "<filename>"  # Should not exist
ls ~/knowledgebase/pdf/2020/ | grep "<filename>"   # Should exist here (if 2020 paper)
```

## Expected Behavior

When you run **WITHOUT** `--dry-run`:

1. **Script finds orphaned PDFs:**
   - In `~/knowledgebase/pdf/`
   - In `~/knowledgebase/pdf/failed/`
   - In `~/knowledgebase/pdf/unknown/`

2. **For each PDF with DOI-format filename:**
   - Reconstructs DOI (e.g., `10.1101_2020.pdf` → `10.1101/2020`)
   - Searches database for matching document
   - If found, determines publication year
   - **Moves file** from current location to `~/knowledgebase/pdf/YYYY/filename.pdf`
   - Updates database: `UPDATE document SET pdf_filename = 'YYYY/filename.pdf'`

3. **Files are PHYSICALLY MOVED:**
   - Original location: `~/knowledgebase/pdf/failed/10.1101_2020.pdf`
   - New location: `~/knowledgebase/pdf/2020/10.1101_2020.pdf`

## Common Issue: "Already Linked"

If you see this output:
```
Successfully linked:        0
Already linked:             765
```

**ROOT CAUSE (FIXED):** The script was incorrectly marking files as "already linked" when:
- Document in database has `pdf_filename = '10.1101_xyz.pdf'`
- The orphaned file in `failed/` is the SAME file the database points to
- Script found the file and thought "it's already linked" (WRONG!)
- Result: Files never moved

**FIX APPLIED:** The script now checks if the existing file is the SAME as the orphaned file:
- If SAME file → Proceeds to move and organize it ✅
- If DIFFERENT file → Truly already linked, skip it ✅

**After the fix, you should see:**
```
Successfully linked:        765
Already linked:             0
```

## Summary

✅ **To move files:** Run `python match_orphaned_pdfs.py` (NO --dry-run flag)
❌ **Files won't move:** If you use `python match_orphaned_pdfs.py --dry-run`

**Bug Fixed (2025-10-09):** Files in `failed/` that are referenced in the database will now be properly moved to year-based directories instead of being incorrectly marked as "already linked".
