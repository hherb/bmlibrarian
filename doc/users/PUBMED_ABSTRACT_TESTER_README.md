# PubMed Abstract Tester

A standalone PySide6 application for testing and optimizing PubMed abstract extraction before integrating improvements into the main BMLibrarian importer.

## Purpose

This tool was created to diagnose and fix issues with PubMed abstract imports, including:
- **Truncated abstracts** - Missing content due to incomplete XML parsing
- **Lost formatting** - Subscripts, superscripts, and emphasis stripped out
- **Missing line breaks** - Structured sections running together
- **Incomplete metadata** - Ignoring Label and NlmCategory attributes

## Key Features

### 1. Improved Abstract Parsing

**Structured Abstracts:**
- Extracts both `Label` and `NlmCategory` XML attributes
- Preserves section organization (BACKGROUND, METHODS, RESULTS, CONCLUSIONS)
- Adds paragraph breaks between sections for readability

**Inline Formatting:**
- Converts `<b>`, `<bold>` → **bold** (Markdown)
- Converts `<i>`, `<italic>` → *italic* (Markdown)
- Preserves `<sup>` → ^superscript^ (for chemical formulas like CO^2^)
- Preserves `<sub>` → ~subscript~ (for formulas like H~2~O)
- Handles `<u>`, `<underline>` → __underlined__

**Mixed Content Handling:**
- Recursively processes nested XML elements
- Preserves text before, within, and after formatting tags
- Prevents truncation from incomplete element traversal

### 2. Complete Metadata Extraction

Extracts and displays:
- **PMID** (PubMed ID)
- **DOI** (Digital Object Identifier)
- **Title** (with inline formatting)
- **Authors** (comma-separated list)
- **Journal** name
- **Publication date** (YYYY-MM-DD format)
- **Abstract** (Markdown-formatted with sections)

### 3. Lightweight SQLite Database

- No PostgreSQL dependency for testing
- Single-file database (`pubmed_test.db`)
- Fast browsing with forward/backward navigation
- Easy to clear and re-import test data

### 4. FTP Download Integration

- Automatically fetches latest PubMed update file
- Downloads from `ftp.ncbi.nlm.nih.gov/pubmed/updatefiles/`
- Progress bar with status updates
- Handles large gzipped XML files efficiently

## Installation

The tool uses existing BMLibrarian dependencies:

```bash
# PySide6 is already in pyproject.toml
uv sync
```

## Usage

### Launch the Application

```bash
uv run python pubmed_abstract_tester.py
```

### Download and Parse PubMed Data

1. Click **"Download Latest Update File"** button
2. Wait for download and parsing to complete (progress bar shows status)
3. Once complete, articles will be loaded into the database

### Navigate Articles

- **Next →** / **← Previous**: Browse sequentially
- **Go to:** Jump to specific article by number
- **Article counter**: Shows current position (e.g., "45 / 1000")

### Inspect Abstracts

The abstract display shows:
- **Section headers** in bold (e.g., **BACKGROUND:**, **METHODS:**)
- **Paragraph breaks** between sections (double line spacing)
- **Inline formatting** rendered as rich text:
  - **Bold text** for emphasis
  - *Italic text* for terms
  - Superscripts for exponents (e.g., m²)
  - Subscripts for chemical formulas (e.g., H₂O)

### Clear Database

Click **"Clear Database"** to remove all articles and start fresh.

## What Gets Stored

SQLite schema (`pubmed_test.db`):

```sql
CREATE TABLE articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pmid TEXT UNIQUE NOT NULL,
    doi TEXT,
    title TEXT NOT NULL,
    abstract_markdown TEXT,
    authors TEXT,
    publication_date TEXT,
    journal TEXT,
    import_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

## Comparing with Production Importer

### Old Importer Issues

The existing `pubmed_bulk_importer.py` had these problems:

```python
# OLD CODE - Loses nested content
abstract_parts = []
for abstract_text in article.findall('.//AbstractText'):
    if abstract_text is not None:
        text = self._get_element_text(abstract_text)
        if text:
            abstract_parts.append(text)
abstract = ' '.join(abstract_parts)  # No paragraph breaks!
```

**Problems:**
- ❌ No Label/NlmCategory extraction
- ❌ Joins sections with single space (loses paragraph structure)
- ❌ `_get_element_text()` may not handle mixed content properly
- ❌ No inline formatting preservation

### New Tester Improvements

```python
# NEW CODE - Preserves structure and formatting
for abstract_text in abstract_texts:
    # Get label attributes
    label = abstract_text.get('Label', '').strip()
    if not label:
        nlm_category = abstract_text.get('NlmCategory', '').strip()
        if nlm_category and nlm_category not in ('UNASSIGNED', 'UNLABELLED'):
            label = nlm_category

    # Get text with inline formatting
    text = PubMedParser._get_element_text_with_formatting(abstract_text)

    if label:
        markdown_parts.append(f"**{label.upper()}:** {text}")
    else:
        markdown_parts.append(text)

return '\n\n'.join(markdown_parts)  # Paragraph breaks!
```

**Improvements:**
- ✅ Extracts both Label and NlmCategory
- ✅ Paragraph breaks between sections (`\n\n`)
- ✅ Converts inline XML tags to Markdown
- ✅ Handles structured and unstructured abstracts

## Technical Details

### XML Structure (PubMed DTD)

**Structured Abstract Example:**

```xml
<Abstract>
  <AbstractText Label="BACKGROUND" NlmCategory="BACKGROUND">
    Previous studies have shown that <i>in vitro</i> treatment with CO<sub>2</sub>
    increases cell viability by 15% at 37°C.
  </AbstractText>
  <AbstractText Label="METHODS" NlmCategory="METHODS">
    We conducted a randomized trial with <b>250 patients</b>...
  </AbstractText>
  <AbstractText Label="RESULTS" NlmCategory="RESULTS">
    The treatment group showed significant improvement (p&lt;0.05)...
  </AbstractText>
  <AbstractText Label="CONCLUSIONS" NlmCategory="CONCLUSIONS">
    Our findings suggest that early intervention is critical.
  </AbstractText>
</Abstract>
```

**Rendered Output:**

```
**BACKGROUND:** Previous studies have shown that *in vitro* treatment with CO~2~
increases cell viability by 15% at 37°C.

**METHODS:** We conducted a randomized trial with **250 patients**...

**RESULTS:** The treatment group showed significant improvement (p<0.05)...

**CONCLUSIONS:** Our findings suggest that early intervention is critical.
```

### Inline Elements Supported

From PubMed DTD (https://dtd.nlm.nih.gov/ncbi/pubmed/out/pubmed_250101.dtd):

- `<b>`, `<bold>` - Bold text
- `<i>`, `<italic>` - Italic text
- `<sup>` - Superscript (exponents, footnotes)
- `<sub>` - Subscript (chemical formulas)
- `<u>`, `<underline>` - Underlined text

### Algorithm: Mixed Content Extraction

```python
def _get_element_text_with_formatting(elem):
    if elem is None:
        return ''

    # Leaf node optimization
    if not list(elem):
        return (elem.text or '').strip()

    parts = []

    # Element's direct text (before first child)
    if elem.text:
        parts.append(elem.text)

    # Process each child element
    for child in elem:
        tag = child.tag.lower()
        child_text = _get_element_text_with_formatting(child)

        # Convert to Markdown
        if tag in ('b', 'bold'):
            parts.append(f'**{child_text}**')
        elif tag in ('i', 'italic'):
            parts.append(f'*{child_text}*')
        elif tag == 'sup':
            parts.append(f'^{child_text}^')
        elif tag == 'sub':
            parts.append(f'~{child_text}~')
        else:
            parts.append(child_text)

        # Tail text (after closing tag)
        if child.tail:
            parts.append(child.tail)

    return ''.join(parts).strip()
```

## Next Steps

### Integration into Production

Once tested and validated:

1. **Update `pubmed_bulk_importer.py`:**
   - Replace `_get_element_text()` with `_get_element_text_with_formatting()`
   - Update `_parse_article()` to use `_format_abstract_markdown()`
   - Store markdown-formatted abstracts in PostgreSQL

2. **Database Schema Update:**
   ```sql
   -- Add new column for formatted abstracts
   ALTER TABLE document ADD COLUMN abstract_markdown TEXT;

   -- Migrate existing abstracts (optional)
   UPDATE document SET abstract_markdown = abstract WHERE abstract IS NOT NULL;
   ```

3. **Test with Baseline Files:**
   ```bash
   uv run python pubmed_bulk_cli.py download-updates
   uv run python pubmed_bulk_cli.py import --type update
   ```

4. **Verify Results:**
   - Check abstract formatting in BMLibrarian GUI
   - Compare with PubMed website for accuracy
   - Ensure no truncation or loss of content

### Future Enhancements

- **Copy to clipboard**: Export formatted abstract for documentation
- **Compare mode**: Side-by-side old vs. new abstract display
- **Batch validation**: Automated comparison with PubMed API results
- **Export improvements**: Generate patch file for production importer

## Troubleshooting

### Download Fails

**Error:** `Connection timeout` or `FTP error`

**Solution:** Check firewall settings, retry with longer timeout

### No Articles Displayed

**Error:** Database shows 0 articles after import

**Solution:** Check logs for XML parsing errors, ensure gzip file is valid

### Formatting Not Rendering

**Problem:** Abstract shows Markdown syntax instead of rich formatting

**Solution:** Ensure `_markdown_to_html()` is being called in `show_article()`

## References

- **PubMed DTD:** https://dtd.nlm.nih.gov/ncbi/pubmed/out/pubmed_250101.dtd
- **Structured Abstracts:** https://structuredabstracts.nlm.nih.gov/
- **XML Data Elements:** https://www.nlm.nih.gov/bsd/licensee/elements_descriptions.html
- **PubMed FTP:** ftp://ftp.ncbi.nlm.nih.gov/pubmed/

## Contact

For issues or questions about this testing tool, see the main BMLibrarian documentation.
