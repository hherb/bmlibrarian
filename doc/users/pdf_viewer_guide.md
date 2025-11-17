# PDF Viewer Guide

## Overview

The Document Interrogation tab includes a powerful PDF viewer with comprehensive features for viewing, navigating, searching, and highlighting PDF documents.

## Features

### Core Capabilities

1. **PDF Rendering**: High-quality page rendering using PyMuPDF (fitz)
2. **Page Navigation**: Previous/next buttons and direct page jumps
3. **Zoom Control**: Zoom in/out from 50% to 300%
4. **Text Search**: Find and highlight text across all pages
5. **Programmatic Highlighting**: API for highlighting specific regions
6. **Text Extraction**: Extract text for LLM processing

## Installation

The PDF viewer requires PyMuPDF:

```bash
# Install PyMuPDF for PDF support
pip install PyMuPDF

# Or with uv
uv pip install PyMuPDF
```

If PyMuPDF is not installed, you'll see an error message with installation instructions when loading PDF files.

## User Interface

### PDF Viewer Layout

```
┌─────────────────────────────────────────────────────────┐
│ Controls (Top Toolbar)                                  │
│ ┌───────────────────────────────────────────────────┐  │
│ │ Page: [<] [1] / 10 [>]  │  Zoom: [-] 100% [+] [⊡] │  │
│ └───────────────────────────────────────────────────┘  │
│ ┌───────────────────────────────────────────────────┐  │
│ │ [Search...] [🔍] [▲] [▼] 1/5 results [✕]         │  │
│ └───────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────┤
│                                                         │
│                   PDF Page Display                      │
│                   (scrollable)                          │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### Navigation Controls

**Page Navigation**
- `[<]` button: Previous page
- `[>]` button: Next page
- Page number field: Type page number and press Enter to jump
- Total pages display: Shows current page / total pages

**Zoom Controls**
- `[-]` button: Zoom out (decrease by 10%)
- `[+]` button: Zoom in (increase by 10%)
- Percentage display: Current zoom level
- `[⊡]` button: Reset to 100% zoom
- Zoom range: 50% - 300%

### Search Controls

**Search Bar**
- Text field: Enter search term
- `[🔍]` button: Execute search
- `[▲]` button: Previous result
- `[▼]` button: Next result
- Results counter: Shows "N / Total results"
- `[✕]` button: Clear search

## Usage Examples

### Basic Navigation

1. **Load PDF**
   - Click "Load Document" in top bar
   - Select a PDF file
   - PDF viewer appears with first page

2. **Navigate Pages**
   - Click next/previous arrows
   - Or type page number and press Enter
   - Example: Type "5" and press Enter to jump to page 5

3. **Zoom In/Out**
   - Click `[+]` to zoom in
   - Click `[-]` to zoom out
   - Click `[⊡]` to reset to 100%

### Searching PDFs

1. **Basic Search**
   ```
   1. Type search term in search box
   2. Click search button or press Enter
   3. Results are highlighted in yellow
   4. Use up/down arrows to navigate between results
   ```

2. **Search Results**
   - All matching instances across all pages are found
   - Current result counter shows position (e.g., "3 / 15")
   - Viewer automatically jumps to result page
   - Yellow highlights show match locations

3. **Clear Search**
   - Click `[✕]` button to clear highlights
   - Search field is cleared
   - Returns to normal view

### Example Workflow

**Reading a Research Paper**:
```
1. Load PDF: paper.pdf
2. Navigate to Abstract: Jump to page 1
3. Search for "methods": Find methodology sections
4. Review results: Use arrows to check each instance
5. Zoom in: 150% for detailed reading
6. Navigate to Discussion: Jump to page 12
7. Search for "limitations": Find study limitations
```

## Programmatic API

For integration with other plugins or automated workflows:

### Highlighting API

```python
# Access the document interrogation tab
doc_tab = app.tab_objects['document_interrogation']

# Highlight a specific region (e.g., a citation)
doc_tab.highlight_pdf_region(
    page_num=0,  # Page 1 (0-indexed)
    rect=(100, 100, 300, 120),  # (x0, y0, x1, y1)
    color=(255, 200, 0),  # Orange RGB
    label="Important Citation"
)

# Highlight multiple regions
citations = [
    (0, (100, 100, 300, 120)),  # Page 1
    (2, (150, 200, 400, 250)),  # Page 3
    (5, (200, 300, 500, 350)),  # Page 6
]

for page, rect in citations:
    doc_tab.highlight_pdf_region(page, rect, label=f"Citation on page {page+1}")

# Clear all highlights
doc_tab.clear_pdf_highlights()
```

### Search API

```python
# Search for text programmatically
count = doc_tab.search_pdf("cardiovascular")
print(f"Found {count} instances of 'cardiovascular'")

# Jump to specific page
doc_tab.jump_to_pdf_page(5)  # Go to page 6 (0-indexed)
```

### Use Case: Citation Highlighting

When an LLM responds with citations, automatically highlight them:

```python
def highlight_citations(citations):
    """
    Highlight citations mentioned in LLM response.

    Args:
        citations: List of (page_num, text_snippet) tuples
    """
    for page_num, text in citations:
        # Search for text on specific page
        count = doc_tab.search_pdf(text)
        if count > 0:
            print(f"Highlighted '{text}' on page {page_num + 1}")

# Example usage
llm_citations = [
    (2, "cardiovascular benefits"),
    (5, "mitochondrial function"),
    (8, "metabolic syndrome")
]

highlight_citations(llm_citations)
```

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Arrow Right` | Next page (when page number field focused) |
| `Arrow Left` | Previous page (when page number field focused) |
| `+` / `=` | Zoom in (when zoom controls focused) |
| `-` / `_` | Zoom out (when zoom controls focused) |
| `Ctrl+F` / `Cmd+F` | Focus search field |
| `Enter` | Execute search / Jump to page |
| `Escape` | Clear search |

## Technical Details

### PDF Rendering

**Technology**: PyMuPDF (fitz library)

**Rendering Process**:
1. PDF loaded into memory
2. Current page rendered to pixmap (bitmap)
3. Zoom matrix applied for scaling
4. Highlights drawn as annotations
5. Pixmap converted to PNG
6. PNG encoded as base64 for Flet display

**Performance**:
- Page render time: ~50-200ms (depends on page complexity)
- Memory usage: ~10-50MB per page (depends on resolution)
- Zoom levels: 50%, 75%, 100%, 125%, 150%, 200%, 300%

### Search Algorithm

**Text Extraction**:
- Uses PyMuPDF's built-in text search
- Case-insensitive matching
- Returns bounding rectangles for each match

**Search Features**:
- Multi-page search (all pages scanned)
- Real-time highlighting
- Navigation between results
- Result count display

**Limitations**:
- Scanned PDFs without OCR: No searchable text
- Complex layouts: May have issues with column detection
- Special characters: Some Unicode characters may not match

### Highlighting System

**Highlight Types**:

1. **Search Highlights** (Yellow)
   - Temporary
   - Cleared when search is cleared
   - Auto-positioned based on text location

2. **Programmatic Highlights** (Orange/Custom)
   - Persistent until cleared
   - Custom colors supported
   - Manual rectangle positioning

**Highlight Rendering**:
- Drawn as PDF annotations
- Alpha transparency: 25% (64/255)
- Overlays on top of page content
- Preserved across zoom levels

## Best Practices

### Performance Optimization

1. **Large PDFs**:
   - Zoom out for faster rendering
   - Search specific terms instead of browsing all pages
   - Close PDF when done to free memory

2. **Search Efficiency**:
   - Use specific terms (not single letters)
   - Clear search when done
   - Limit searches to necessary terms

3. **Memory Management**:
   - Load only one PDF at a time
   - Clear highlights when no longer needed
   - Restart app if memory issues occur

### Reading Strategies

1. **Quick Overview**:
   - Search for "abstract", "introduction", "conclusion"
   - Navigate directly to key sections
   - Use zoom for detailed reading

2. **Citation Verification**:
   - Search for author names
   - Look for reference numbers
   - Highlight cited passages

3. **Comparative Analysis**:
   - Load first PDF, highlight key points
   - Load second PDF, compare highlights
   - Use chat to discuss differences

## Troubleshooting

### PDF Won't Load

**Problem**: Error message when opening PDF

**Solutions**:
1. Check PyMuPDF installation: `pip show PyMuPDF`
2. Verify PDF is not corrupted: Open in another PDF viewer
3. Check file permissions: Ensure read access
4. Try smaller PDF: Test with simple document

### Search Not Working

**Problem**: Search returns "No results" for known text

**Solutions**:
1. Check if PDF is scanned image (needs OCR)
2. Try different search terms
3. Check for special characters or formatting
4. Verify text is selectable in other PDF viewers

### Slow Rendering

**Problem**: Pages take long time to load

**Solutions**:
1. Reduce zoom level (try 75% or 50%)
2. Close other applications to free memory
3. Try smaller PDF or fewer pages
4. Restart application

### Highlights Not Showing

**Problem**: Programmatic highlights don't appear

**Solutions**:
1. Check page number is correct (0-indexed)
2. Verify rectangle coordinates are within page bounds
3. Ensure color alpha is not 0 (fully transparent)
4. Refresh page by navigating away and back

## Limitations

### Current Limitations

1. **Annotations**: Cannot add permanent annotations to PDF file
2. **Export**: Cannot save PDF with highlights
3. **OCR**: Does not perform OCR on scanned documents
4. **Forms**: Cannot fill PDF forms
5. **Bookmarks**: Does not show PDF bookmarks/outline
6. **Thumbnails**: No page thumbnail view
7. **Selection**: Cannot select and copy text from viewer

### Future Enhancements

1. **Text Selection**: Select and copy text from PDF
2. **Bookmarks Panel**: Show document outline
3. **Thumbnail View**: Grid of page thumbnails
4. **Annotations**: Add notes and comments
5. **Export**: Save PDF with highlights
6. **Print**: Print pages from viewer
7. **Split View**: View two pages side-by-side

## Integration Examples

### Example 1: Auto-highlight LLM Citations

```python
def process_llm_response_with_citations(response):
    """
    Parse LLM response and highlight cited passages.

    Response format: "According to page 3, 'cardiovascular benefits...'
    """
    import re

    # Find citations in format: page N, 'text'
    pattern = r"page (\d+), '([^']+)'"
    matches = re.findall(pattern, response)

    for page_str, text in matches:
        page_num = int(page_str) - 1  # Convert to 0-indexed
        doc_tab.search_pdf(text)
        doc_tab.jump_to_pdf_page(page_num)
```

### Example 2: Highlight All Key Terms

```python
def highlight_key_terms(terms):
    """
    Search and highlight multiple key terms.

    Args:
        terms: List of terms to highlight
    """
    for term in terms:
        count = doc_tab.search_pdf(term)
        print(f"'{term}': {count} occurrences")

# Usage
key_terms = ["diabetes", "insulin", "glucose", "metabolism"]
highlight_key_terms(key_terms)
```

### Example 3: Extract and Analyze

```python
def extract_and_analyze_page(page_num):
    """
    Extract text from page and send to LLM for analysis.

    Args:
        page_num: Page number (0-indexed)
    """
    # Jump to page
    doc_tab.jump_to_pdf_page(page_num)

    # Extract text (via PDF viewer API)
    text = doc_tab.pdf_viewer.get_text_from_page(page_num)

    # Send to LLM for analysis
    doc_tab.message_input.value = f"Summarize this page: {text}"
    doc_tab._on_send_message(None)
```

## Comparison with Other PDF Viewers

| Feature | BMLibrarian PDF Viewer | Adobe Acrobat | Browser PDF |
|---------|----------------------|---------------|-------------|
| Text Search | ✅ Yes | ✅ Yes | ✅ Yes |
| Highlighting | ✅ Programmatic | ✅ Manual | ❌ No |
| LLM Integration | ✅ Yes | ❌ No | ❌ No |
| Annotations | ❌ View only | ✅ Full support | ❌ Limited |
| Text Selection | ❌ Not yet | ✅ Yes | ✅ Yes |
| Zoom | ✅ 50-300% | ✅ Unlimited | ✅ Unlimited |
| Page Navigation | ✅ Yes | ✅ Yes | ✅ Yes |
| Export | ❌ Not yet | ✅ Yes | ✅ Print only |

## Credits

- **PDF Engine**: PyMuPDF (fitz) - https://pymupdf.readthedocs.io/
- **UI Framework**: Flet - https://flet.dev/
- **Design**: Material Design inspired

## Version History

- **v1.0**: Initial PDF viewer implementation
  - Page rendering
  - Navigation controls
  - Search functionality
  - Programmatic highlighting API
  - Zoom controls
