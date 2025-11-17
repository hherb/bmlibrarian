# PDF Import Guide

## Overview

The PDF Import system provides intelligent matching of PDF files to existing documents in the BMLibrarian database. It uses AI-powered metadata extraction to identify papers and automatically organizes them according to BMLibrarian's naming conventions.

## Features

- **LLM-Based Metadata Extraction**: Uses Ollama to extract DOI, PMID, title, and authors from PDF first pages
- **Multiple Matching Strategies**:
  1. Exact DOI match
  2. Exact PMID match
  3. Fuzzy title matching
- **Automatic Organization**: Renames and moves PDFs to year-based directory structure
- **Database Integration**: Updates database with PDF locations
- **Batch Processing**: Process entire directories at once
- **Dry Run Mode**: Preview changes before committing

## Installation

The PDF import functionality requires PyMuPDF for PDF text extraction:

```bash
uv add pymupdf
```

## Usage

### Import a Single PDF File

```bash
# Basic import
uv run python pdf_import_cli.py file /path/to/paper.pdf

# Dry run to see what would happen
uv run python pdf_import_cli.py file paper.pdf --dry-run

# Verbose output to see extracted metadata
uv run python pdf_import_cli.py file paper.pdf --verbose
```

### Import a Directory of PDFs

```bash
# Import all PDFs from a directory
uv run python pdf_import_cli.py directory /path/to/pdfs/

# Include subdirectories recursively
uv run python pdf_import_cli.py directory /path/to/pdfs/ --recursive

# Dry run for entire directory
uv run python pdf_import_cli.py directory /path/to/pdfs/ --dry-run
```

### Check Import Status

```bash
# View statistics about PDF coverage
uv run python pdf_import_cli.py status
```

Example output:
```
============================================================
PDF IMPORT STATUS
============================================================
Total documents:               42,156
Documents with PDFs:           12,834 (30.4%)
Documents missing PDFs:        29,322

By source:
  medrxiv             : 8,234/10,500 (78.4%)
  PubMed              : 4,600/31,656 (14.5%)
============================================================
```

## Configuration Options

### Custom PDF Base Directory

Override the default PDF storage location:

```bash
uv run python pdf_import_cli.py file paper.pdf --pdf-dir /custom/pdf/location
```

### Custom LLM Model

Use a different Ollama model for metadata extraction:

```bash
# Use faster model
uv run python pdf_import_cli.py file paper.pdf --model medgemma4B_it_q8:latest

# Use more powerful model
uv run python pdf_import_cli.py file paper.pdf --model gpt-oss:20b
```

### Custom Ollama URL

If Ollama is running on a different host or port:

```bash
uv run python pdf_import_cli.py file paper.pdf --ollama-url http://192.168.1.100:11434
```

## How It Works

### 1. Text Extraction

The system extracts text from the **first page only** of each PDF using PyMuPDF. This is where metadata typically appears in academic papers.

### 2. Metadata Extraction

An LLM analyzes the extracted text to identify:

- **DOI**: Digital Object Identifier (e.g., "10.1234/example")
- **PMID**: PubMed ID (e.g., "12345678")
- **Title**: Paper title
- **Authors**: List of author names

### 3. Database Matching

The system attempts to match the PDF to an existing document using:

1. **Exact DOI match** (highest priority)
2. **Exact PMID match** (via external_id field)
3. **Fuzzy title match** (using PostgreSQL similarity, threshold 0.6)

### 4. PDF Organization

If a match is found, the PDF is:

1. **Renamed** to: `{doi_with_underscores}.pdf` (e.g., `10.1234_example.pdf`)
2. **Moved** to: `{pdf_base_dir}/{year}/{filename}.pdf`
3. **Database updated** with relative path: `{year}/{filename}.pdf`

Example:
```
Source:  /downloads/random_paper_v2.pdf
Target:  ~/knowledgebase/pdf/2023/10.1234_example.pdf
```

## Matching Strategies

### DOI Matching (Most Reliable)

The system looks for DOI patterns in the extracted text:
- "doi:10.1234/example"
- "DOI: 10.1234/example"
- "https://doi.org/10.1234/example"

If found, it queries the database:
```sql
SELECT * FROM document WHERE doi = '10.1234/example'
```

### PMID Matching (PubMed Papers)

For PubMed papers, the system extracts PMIDs:
- "PMID: 12345678"
- "PubMed ID: 12345678"

Query:
```sql
SELECT * FROM document WHERE external_id = '12345678'
```

### Title Matching (Fallback)

If no DOI or PMID is found, the system uses fuzzy title matching:

```sql
SELECT * FROM document
WHERE similarity(title, 'Extracted Title') > 0.6
ORDER BY similarity(title, 'Extracted Title') DESC
LIMIT 1
```

This uses PostgreSQL's trigram similarity for fuzzy matching.

## Status Codes

The CLI reports various status codes for each PDF:

| Status | Icon | Meaning |
|--------|------|---------|
| `imported` | ✅ | Successfully imported and database updated |
| `would_import` | 🔄 | Would import (dry run mode) |
| `no_match` | ❌ | No matching document found in database |
| `already_exists` | 📋 | PDF already exists at correct location |
| `duplicate` | 📋 | PDF exists with same file size |
| `skipped` | ⏭️ | Skipped (e.g., existing PDF is newer) |
| `failed` | ⚠️ | Import failed due to error |
| `extraction_failed` | 📄 | Could not extract text from PDF |
| `no_metadata` | 📝 | Could not extract metadata from PDF |

## Best Practices

### 1. Always Start with Dry Run

Before importing a large batch, run with `--dry-run` to preview:

```bash
uv run python pdf_import_cli.py directory /pdfs/ --dry-run --verbose
```

This shows what would be matched without making changes.

### 2. Use Verbose Mode for Troubleshooting

If matching isn't working as expected:

```bash
uv run python pdf_import_cli.py file paper.pdf --verbose
```

This shows the extracted metadata and helps diagnose issues.

### 3. Check Status Regularly

Monitor PDF coverage across sources:

```bash
uv run python pdf_import_cli.py status
```

### 4. Handle No-Match Cases

PDFs with `no_match` status may need manual intervention:

1. Check if the paper exists in database with different metadata
2. Consider importing the paper metadata first
3. Verify the PDF is a biomedical research paper (not a book chapter, etc.)

## Troubleshooting

### "Cannot connect to Ollama"

**Problem**: The LLM service is not running or not reachable.

**Solution**:
```bash
# Check Ollama is running
curl http://localhost:11434/api/version

# Start Ollama if needed
ollama serve

# Verify model is available
ollama list | grep gpt-oss
```

### "Could not extract text from PDF"

**Problem**: PDF may be image-based (scanned) or corrupted.

**Cause**: PyMuPDF can only extract text from PDFs with text layers, not scanned images.

**Solution**: These PDFs require OCR processing (not currently supported).

### "No matching document found"

**Problem**: The paper may not be in your database yet.

**Solution**:
1. Import the paper metadata first using appropriate importer:
   ```bash
   # For PubMed papers
   uv run python pubmed_import_cli.py pmids 12345678

   # For medRxiv papers
   uv run python medrxiv_import_cli.py update
   ```
2. Then import the PDF again

### "Fuzzy title match selected wrong paper"

**Problem**: Title matching has false positives.

**Solution**:
- Prefer papers with DOI or PMID metadata
- Manually verify title matches when similarity < 0.8
- Consider using more specific search to import exact paper metadata first

## Workflow Example

### Scenario: Import 40,000 legacy PDFs

You have a directory of 40,000 PDFs from a previous research project.

#### Step 1: Dry Run on Sample

```bash
# Test with first 100 PDFs
mkdir /tmp/sample_pdfs
cp /legacy_pdfs/*.pdf /tmp/sample_pdfs/ | head -100

uv run python pdf_import_cli.py directory /tmp/sample_pdfs/ --dry-run --verbose
```

Review results to understand matching rates.

#### Step 2: Run Actual Import

```bash
# Import entire directory
uv run python pdf_import_cli.py directory /legacy_pdfs/ --recursive
```

This processes all PDFs and shows progress bar.

#### Step 3: Check Results

```bash
# View statistics
uv run python pdf_import_cli.py status

# Review logs for issues
grep "no_match" pdf_import.log | wc -l
```

#### Step 4: Handle No-Match Cases

For PDFs that didn't match, you can:

1. **Check the extracted metadata**:
   ```bash
   uv run python pdf_import_cli.py file unmatched.pdf --verbose
   ```

2. **Import missing papers** if they should be in your database:
   ```bash
   # Import by DOI or PMID
   uv run python pubmed_import_cli.py pmids <extracted_pmid>
   ```

3. **Re-run import** after adding papers to database:
   ```bash
   uv run python pdf_import_cli.py file unmatched.pdf
   ```

## Performance Considerations

### Processing Speed

- **LLM analysis**: ~2-5 seconds per PDF
- **Database matching**: <100ms per PDF
- **File operations**: <1 second per PDF

**Estimated throughput**: ~400-600 PDFs per hour

For 40,000 PDFs, expect ~70-100 hours of processing time.

### Optimization Tips

1. **Use faster model** for large batches:
   ```bash
   --model medgemma4B_it_q8:latest
   ```

2. **Run on machine with good CPU**: LLM inference benefits from multi-core processors

3. **Process in batches**: Split large directories into smaller batches for better monitoring

4. **Parallel processing**: Run multiple instances on different subdirectories (future enhancement)

## Limitations

1. **First page only**: Only analyzes first page of PDF for metadata
2. **Text-based PDFs only**: Cannot process scanned/image-based PDFs without OCR
3. **English language**: LLM trained primarily on English text
4. **Biomedical focus**: Optimized for biomedical research papers
5. **No duplicate detection**: If document already has PDF, newer file replaces older

## Future Enhancements

- OCR support for scanned PDFs
- Multi-language support
- Parallel batch processing
- Semantic title matching using embeddings
- Author name disambiguation
- PDF quality assessment
- Automatic metadata correction

## Related Documentation

- [PDF Manager Architecture](../developers/pdf_manager_architecture.md)
- [medRxiv Import Guide](medrxiv_import_guide.md)
- [PubMed Import Guide](pubmed_import_guide.md)
- [Document Embedding Guide](document_embedding_guide.md)

## Support

For issues or questions:
- Review logs with `--verbose` flag
- Check Ollama service status
- Verify database connectivity
- Report issues at: https://github.com/hherb/bmlibrarian/issues
