# PDF Verification Dialog Guide

This guide explains the PDF verification dialog that appears when a downloaded PDF doesn't match the expected document metadata.

## Overview

When BMLibrarian downloads a PDF, it verifies that the PDF matches the expected document by checking:

- **DOI**: Does the DOI extracted from the PDF match the expected DOI?
- **PMID**: Does the PubMed ID match?
- **Title**: Is the title similar enough (using fuzzy matching)?

If verification fails, an interactive dialog appears allowing you to decide what to do with the mismatched PDF.

## When Does the Dialog Appear?

The verification dialog appears when:

1. A PDF is successfully downloaded
2. The PDF's metadata (DOI, title) doesn't match the expected document
3. Interactive mode is enabled (`prompt_on_mismatch=True`)

## Dialog Layout

The dialog has three main sections:

### Left Panel: PDF Viewer
- Shows a preview of the downloaded PDF
- Allows you to verify the content before making a decision

### Right Panel: Document Comparison
Shows three information cards:

1. **Expected Document** (blue): What you were trying to download
   - DOI, Title, PMID from your database

2. **Downloaded PDF** (red): What was actually downloaded
   - DOI, Title, PMID extracted from the PDF

3. **Mismatch Analysis** (amber): Details about what doesn't match
   - DOI mismatch indicator
   - Title similarity percentage
   - Any verification warnings

4. **Matching Document Found** (green, optional): If the PDF's DOI matches a different document in your database
   - Shows the matching document's details
   - Includes the "Assign PDF to Document X" button

## Available Actions

### Primary Actions (Row 1)

#### ✓ Accept & Ingest (Green)
Accept the PDF despite the mismatch and assign it to the original document.

**Use when**: The PDF is actually correct but metadata extraction had issues.

#### 📁 Manual Upload (Teal)
Open a file browser to select a different PDF file from your computer.

**Use when**: You've manually downloaded the correct PDF and want to use it instead.

### Secondary Actions (Row 2)

#### 🌐 Open in Browser (Cyan)
Opens the source URL in your default browser. The dialog stays open.

**Use when**: You want to manually navigate to find and download the correct PDF.

#### 💾 Save As... (Blue)
Save a copy of the downloaded PDF to a custom location. The dialog stays open.

**Use when**: The PDF is useful but not for this document - save it for later.

#### 🔄 Retry Search (Orange)
Discard this PDF and try searching for the correct one again.

**Use when**: The discovery system found the wrong PDF - try other sources.

#### ✗ Reject (Red)
Discard the downloaded PDF completely and close the dialog.

**Use when**: The PDF is not useful at all.

### Special Action: Assign to Different Document

If a matching document is found in your database (green section), you can:

#### 📄 Assign PDF to Document X (Purple)
Immediately assigns the PDF to the matching document. The dialog stays open so you can:
- Open the browser to find the correct PDF for the original document
- Manually upload the correct PDF
- Reject to close without further action

**Use when**: The PDF is correct, just for the wrong document - assign it to the right one and continue searching for the original.

## Workflow Examples

### Example 1: Simple Mismatch - Accept Anyway
1. Dialog shows: Expected DOI `10.1234/abc`, Found DOI `10.1234/abc.v2`
2. You review the PDF and confirm it's the right paper (just a version difference)
3. Click **Accept & Ingest**

### Example 2: Wrong PDF - Retry
1. Dialog shows: Completely different DOI and title
2. The PDF is clearly for a different paper
3. Click **Retry Search** to try other sources

### Example 3: PDF for Different Document
1. Dialog shows: DOI mismatch
2. Green section appears: "Matching Document Found!"
3. The PDF belongs to document #456 which needs a PDF
4. Click **Assign PDF to Document 456**
5. Now click **Open in Browser** to find the correct PDF for the original document
6. Download it manually, then click **Manual Upload** to select it
7. Or click **Reject** if you're done

### Example 4: Manual Download Workflow
1. Dialog shows: Verification failed
2. Click **Open in Browser** - your browser opens the source URL
3. Navigate to find and download the correct PDF
4. Click **Manual Upload** and select the downloaded file
5. The correct PDF is assigned to the document

## Configuration

Enable interactive verification in your code:

```python
from bmlibrarian.utils.pdf_manager import PDFManager

pdf_manager = PDFManager()
path = pdf_manager.download_pdf_with_discovery(
    document={'doi': '10.1234/example', 'id': 123},
    verify_content=True,       # Enable verification
    prompt_on_mismatch=True,   # Show dialog on mismatch
    parent_widget=self         # For proper dialog parenting
)
```

## CLI Mode

When running without a GUI, the verification prompt appears in the terminal with keyboard-based options:

```
======================================================================
PDF VERIFICATION REQUIRED
======================================================================

Downloaded PDF: 10.1234_example.pdf

DOI mismatch:
  Expected: 10.1234/example
  Found:    10.5678/different

Source URL: https://example.com/pdf/download

----------------------------------------------------------------------
📄 MATCHING DOCUMENT FOUND IN DATABASE:
   Title: Different Paper Title...
   DOI: 10.5678/different
   Document ID: 789
   This document does NOT have a PDF assigned yet.

----------------------------------------------------------------------
Options:
  [A] Accept - Ingest this PDF despite the mismatch
  [D] Reassign - Assign this PDF to document 789 instead
  [U] Upload - Manually select a different PDF file
  [B] Browser - Open source URL in browser to find correct PDF
  [S] Save As - Save to a different location (then continue)
  [R] Retry - Try searching for the correct PDF again
  [X] Reject - Discard this PDF

Your choice [A/D/U/B/S/R/X]:
```

## Troubleshooting

### Dialog doesn't appear
- Ensure `prompt_on_mismatch=True` is set
- Check that you're running in a GUI environment (for the visual dialog)
- Verify that verification is enabled (`verify_content=True`)

### PDF viewer not loading
- The dialog will show a fallback message with file info
- You can still make decisions based on the metadata comparison

### "Open in Browser" doesn't work
- Check your default browser settings
- The URL is shown in the tooltip - you can copy it manually

### Manual Upload fails
- Ensure the file is a valid PDF (.pdf extension)
- Check file permissions
- The file must exist at the selected path
