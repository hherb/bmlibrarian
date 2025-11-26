# Document Fetching System

This document describes the canonical approach for fetching document metadata in BMLibrarian UI components.

## Overview

BMLibrarian uses a centralized document fetching pattern to ensure consistency across all widgets and components. The `get_document_details()` function in `bmlibrarian.database` is the single source of truth for fetching complete document metadata.

## The Canonical Function

### `get_document_details(document_id: int) -> Optional[Dict[str, Any]]`

Located in: `src/bmlibrarian/database.py`

This function fetches comprehensive document details by database ID and returns a dictionary with properly formatted fields.

### Return Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Document database ID |
| `title` | str | Document title |
| `abstract` | str | Document abstract |
| `authors` | str | Pre-formatted author string (e.g., "Smith J, Jones A, et al.") |
| `authors_list` | list | Original authors array from database |
| `journal` | str | Publication/journal name (from `publication` field) |
| `year` | int | Publication year |
| `publication_date` | str | Full publication date as ISO string |
| `doi` | str | DOI if available |
| `pmid` | str | PubMed ID (extracted from external_id for PubMed sources) |
| `external_id` | str | Original external_id value |
| `source_id` | int | Source ID |
| `source_name` | str | Source name (PubMed, medRxiv, etc.) |
| `url` | str | Document URL |
| `pdf_url` | str | PDF URL if available |
| `pdf_filename` | str | PDF filename if available |
| `full_text` | str | Full text content if available |
| `keywords` | list | List of keywords |
| `mesh_terms` | list | List of MeSH terms |
| `has_full_text` | bool | Convenience boolean for full text availability |

### Key Features

1. **Pre-formatted Authors**: The `authors` field is always a formatted string, not a list. If there are more than 3 authors, it's truncated with "et al."

2. **PMID Extraction**: The function automatically extracts PMID from `external_id` for PubMed sources (source_id=1) or from various PMID formats.

3. **Date Conversion**: `publication_date` is converted to ISO string format.

4. **Null Safety**: List fields (`keywords`, `mesh_terms`) are guaranteed to be lists, never None.

## PDF Path Resolution

### `resolve_pdf_path(doc: Dict[str, Any]) -> Optional[str]`

Located in: `src/bmlibrarian/database.py`

This companion function takes a document dict (from `get_document_details`) and resolves the `pdf_filename` to a full filesystem path.

**Important**: The `pdf_filename` field from `get_document_details` is just the filename (e.g., `"paper.pdf"` or `"2023/paper.pdf"`), NOT a full path. Use `resolve_pdf_path()` to get the actual file path.

```python
from bmlibrarian.database import get_document_details, resolve_pdf_path

doc = get_document_details(12345)
pdf_path = resolve_pdf_path(doc)  # Returns "/Users/.../knowledgebase/pdf/2023/paper.pdf" or None
```

## Usage Pattern

### In Widget/Tab Code

```python
from bmlibrarian.database import get_document_details, resolve_pdf_path
from bmlibrarian.gui.qt.widgets import DocumentViewData

def _load_document(self, doc_id: int):
    """Load and display a document."""
    # Fetch using canonical function
    doc = get_document_details(doc_id)

    if not doc:
        # Handle not found
        return

    # Resolve PDF path from pdf_filename
    pdf_path = resolve_pdf_path(doc)

    # Create DocumentViewData - fields are already properly formatted
    doc_data = DocumentViewData(
        document_id=doc.get('id'),
        title=doc.get('title') or "",
        authors=doc.get('authors'),  # Already a formatted string
        journal=doc.get('journal'),
        year=doc.get('year'),
        pmid=doc.get('pmid'),
        doi=doc.get('doi'),
        abstract=doc.get('abstract'),
        full_text=doc.get('full_text'),
        pdf_path=pdf_path,  # Use resolved path, not pdf_filename
        pdf_url=doc.get('pdf_url'),
        publication_date=doc.get('publication_date'),
    )

    self.document_view.set_document(doc_data)
```

### In Background Workers

```python
from PySide6.QtCore import QThread, Signal
from bmlibrarian.database import get_document_details

class DocumentFetchWorker(QThread):
    fetch_complete = Signal(dict)
    fetch_error = Signal(str)

    def __init__(self, document_id: int):
        super().__init__()
        self.document_id = document_id

    def run(self):
        try:
            doc = get_document_details(self.document_id)
            if doc:
                self.fetch_complete.emit(doc)
            else:
                self.fetch_error.emit(f"Document {self.document_id} not found")
        except Exception as e:
            self.fetch_error.emit(str(e))
```

## Components Using This Pattern

The following components use `get_document_details()`:

| Component | File |
|-----------|------|
| DocumentViewWidget | `src/bmlibrarian/gui/qt/widgets/document_view_widget.py` |
| Document Interrogation Tab | `src/bmlibrarian/gui/qt/plugins/document_interrogation/document_interrogation_tab.py` |
| PICO Lab Tab | `src/bmlibrarian/gui/qt/plugins/pico_lab/pico_lab_tab.py` |
| PRISMA2020 Lab Tab | `src/bmlibrarian/gui/qt/plugins/prisma2020_lab/prisma2020_lab_tab.py` |
| Study Assessment Tab | `src/bmlibrarian/gui/qt/plugins/study_assessment/study_assessment_tab.py` |
| Paper Weight Lab Plugin | `src/bmlibrarian/gui/qt/plugins/paper_weight_lab/plugin.py` |
| Paper Checker Lab Worker | `src/bmlibrarian/lab/paper_checker_lab/worker.py` |

## Why This Pattern?

### Before (Anti-pattern)

```python
# DON'T DO THIS - inline SQL with inconsistent field handling
def _load_document(self, doc_id):
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, title, authors, journal, ...
                FROM document WHERE id = %s
            """, (doc_id,))
            row = cur.fetchone()

    # Manual author formatting (duplicated everywhere)
    authors = row['authors']
    if isinstance(authors, list):
        authors = ', '.join(authors)

    # Missing PMID extraction, date formatting, etc.
```

### Problems with the Anti-pattern

1. **Code Duplication**: Each widget had its own author formatting logic
2. **Inconsistent Fields**: Different widgets expected different field names
3. **Missing Data**: Some widgets didn't extract PMID or format dates
4. **Maintenance Burden**: Changes needed in multiple places
5. **Bug Prone**: Easy to forget a field or format incorrectly

### After (Current Pattern)

```python
# DO THIS - use the canonical function
def _load_document(self, doc_id):
    doc = get_document_details(doc_id)
    if doc:
        # All fields are consistently formatted
        self._display_document(doc)
```

### Benefits

1. **Single Source of Truth**: One function handles all document fetching
2. **Consistent Formatting**: Authors, dates, and IDs are always formatted the same way
3. **Complete Data**: All relevant fields are always available
4. **Easy Maintenance**: Changes in one place affect all widgets
5. **Type Safety**: Well-documented return type with predictable fields

## Related Documentation

- [Document Card Factory System](document_card_factory_system.md) - Creating document cards
- [Document Interrogation UI Spec](document_interrogation_ui_spec.md) - Document viewer component
- [Golden Rules](../llm/golden_rules.md) - Rule #18 on document fetching
