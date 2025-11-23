# PDF Upload Widget User Guide

The PDF Upload Widget is a reusable Qt component for importing PDF files into BMLibrarian. It provides a streamlined workflow for:

- Viewing PDF documents
- Extracting document metadata (DOI, PMID, title, authors)
- Matching PDFs to existing database records
- Creating new document entries

## Features

### Split View Interface

The widget provides a split-pane interface:

- **Left Panel (60%)**: PDF viewer with page navigation and zoom controls
- **Right Panel (40%)**: Metadata extraction and document matching controls

### Fast Identifier Extraction

The widget uses a tiered extraction approach for optimal performance:

1. **Regex Extraction (~100ms)**: First attempts fast pattern matching for:
   - DOI patterns (e.g., `10.1234/example`)
   - PMID patterns (e.g., `PMID: 12345678`)

2. **Quick Database Lookup (~100ms)**: If identifiers are found, performs exact-match database queries.

3. **LLM Extraction (5-30s)**: Falls back to AI-based extraction only when needed.

### Document Matching

When matches are found, you can:

- **Accept Quick Match**: If a high-confidence match is found immediately
- **View Alternatives**: Browse multiple potential matches ranked by similarity
- **Create New Document**: Add a new entry if no matches exist

## Usage

### Starting the Widget

The widget can be used standalone for testing:

```bash
# Launch the demo application
uv run python pdf_upload_widget_demo.py

# Or with a specific PDF file
uv run python pdf_upload_widget_demo.py /path/to/paper.pdf
```

### Workflow

1. **Select PDF File**
   - Click "Browse..." to open a file selection dialog
   - Or drag-and-drop a PDF file (when integrated into applications)

2. **Automatic Extraction**
   - The widget automatically extracts text from the first page
   - Searches for DOI and PMID using regex patterns
   - If found, performs quick database lookup

3. **Quick Match Found**
   - If a database match is found via DOI/PMID, a green panel appears
   - Review the matched document details
   - Click "Use This Match" to accept, or "Search for More Matches" to continue

4. **LLM Extraction (if needed)**
   - If no quick match, LLM extraction runs automatically
   - The AI extracts title, authors, DOI, and PMID from the text
   - Multiple potential matches are displayed in the results tree

5. **Select or Create**
   - Click on a match in the tree to select it
   - Click "Use Selected Match" to confirm selection
   - Or click "Create New Document" to add a new entry

### Creating New Documents

When no matching document is found in the database, you can create a new entry:

1. **Click "Create New Document"** - Opens the document creation dialog
2. **Review Pre-filled Data** - The dialog pre-fills:
   - Title (extracted from PDF)
   - DOI and PMID (if found)
   - Authors (if extracted)
   - Year (if identified)
3. **Edit as Needed** - All fields are editable
4. **Required Fields**:
   - Title (required)
   - External ID (auto-generated if not provided)
5. **Optional Fields**:
   - DOI, PMID, Authors, Year, Journal, Abstract
   - Source (defaults to "Manual Import")
6. **Click "Save Document"** - Creates the database record

The dialog validates all input before saving:
- DOI format must be valid (10.xxxx/...)
- PMID must be a valid number
- Year must be reasonable (1800-2100)

### Options

- **Ingest PDF**: Check this box to:
  - Store the PDF in the library file system
  - Create text embeddings for semantic search
  - This is optional and can be done later

## Integration

The PDF Upload Widget is used in several BMLibrarian applications:

- **Paper Weight Lab**: For loading papers for assessment
- **Paper Checker Lab**: For fact-checking medical abstracts

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+O` | Browse for PDF (when focused) |
| `Enter` | Confirm selection |
| `Escape` | Cancel operation |

## Tips

1. **PDFs with DOI/PMID**: Papers with visible DOI or PMID on the first page will match almost instantly.

2. **Preprints**: MedRxiv and bioRxiv preprints typically have DOIs that enable quick matching.

3. **Older Papers**: Papers without digital identifiers will require LLM extraction and title-based matching.

4. **Multiple Matches**: When multiple similar papers exist, review the similarity scores to choose the correct one.

## Troubleshooting

### "No text extracted"

- The PDF may be scanned or image-based
- Try OCR processing before import
- Some protected PDFs cannot be read

### "No matches found"

- The paper may not be in the database yet
- Try different search terms
- Create a new document entry

### "LLM extraction taking too long"

- Ensure Ollama service is running
- Check network connectivity to local LLM
- The first extraction may be slower as the model loads

## See Also

- [PDF Import Guide](pdf_import_guide.md) - Batch PDF import CLI
- [Document Embedding Guide](document_embedding_guide.md) - Creating embeddings
- [Paper Weight Lab Guide](paper_weight_lab_guide.md) - Using the assessment lab
