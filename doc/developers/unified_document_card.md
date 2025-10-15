# Unified Document Card Component

## Overview

The Unified Document Card component provides a single, consistent design for displaying documents across all tabs in the BMLibrarian GUI. It maintains the same visual appearance while showing context-specific features based on where it's used.

## Key Features

- **Collapsible Design**: Title and score visible when collapsed, full details when expanded
- **Consistent Appearance**: Same look and feel across literature, scoring, citations, and counterfactual tabs
- **Context-Specific Features**: Scoring controls, citation highlights, etc. appear only when relevant
- **Smart Full-Text Access**: Automatically shows the appropriate button based on PDF availability:
  - "View Full Text" if PDF exists locally
  - "Fetch Full Text" if URL is available
  - "Upload Full Text" if no source is available
- **Score Badges**: Color-coded badges for AI scores (1-5 scale), human scores, and relevance scores (0-1 scale)
- **Citation Highlighting**: Automatically highlights cited passages in abstracts

## Architecture

### Main Class

```python
UnifiedDocumentCard(page, pdf_manager=None, on_pdf_status_change=None)
```

The main class that creates document cards with all features.

**Parameters:**
- `page`: Flet page instance (required for dialogs)
- `pdf_manager`: Optional PDFManager instance for PDF operations
- `on_pdf_status_change`: Optional callback when PDF status changes `(doc_id, status)`

### Context Types

```python
class DocumentCardContext:
    LITERATURE = "literature"      # Literature search results
    SCORING = "scoring"            # Document scoring view
    CITATIONS = "citations"        # Citations view
    COUNTERFACTUAL = "counterfactual"  # Counterfactual evidence
    REPORT = "report"              # Final report view
```

## Usage Examples

### Basic Literature Search Card

```python
from bmlibrarian.gui.unified_document_card import UnifiedDocumentCard, DocumentCardContext

# Create card creator
card_creator = UnifiedDocumentCard(page)

# Create basic literature card
card = card_creator.create_card(
    index=0,
    doc=document_dict,
    context=DocumentCardContext.LITERATURE
)
```

### Document Scoring Card with Human Controls

```python
def on_score_change(index: int, score: str, score_type: str):
    """Handle score override."""
    print(f"Document {index} scored {score} ({score_type})")

def on_score_approve(index: int):
    """Handle AI score approval."""
    print(f"AI score approved for document {index}")

# Create scoring card with human controls
card = card_creator.create_card(
    index=0,
    doc=document_dict,
    context=DocumentCardContext.SCORING,
    ai_score=4.5,
    scoring_reasoning="This document directly answers the research question...",
    show_scoring_controls=True,
    on_score_change=on_score_change,
    on_score_approve=on_score_approve
)
```

### Citation Card with Highlighted Passage

```python
citation_data = {
    'summary': 'Brief summary of why this citation is relevant',
    'passage': 'The exact passage extracted from the document...',
    'relevance_score': 0.95
}

# Create citation card
card = card_creator.create_card(
    index=0,
    doc=document_dict,
    context=DocumentCardContext.CITATIONS,
    citation_data=citation_data,
    relevance_score=0.95
)
```

### Card with Both AI and Human Scores

```python
# Create card showing both AI and human scores
card = card_creator.create_card(
    index=0,
    doc=document_dict,
    context=DocumentCardContext.SCORING,
    ai_score=4.5,
    human_score=5.0,
    scoring_reasoning="Original AI assessment",
    show_scoring_controls=False  # Don't show controls, just display scores
)
```

## Convenience Functions

For simpler use cases, convenience functions are provided:

```python
from bmlibrarian.gui.unified_document_card import (
    create_literature_card,
    create_scored_card,
    create_citation_card
)

# Literature card
card = create_literature_card(page, index=0, doc=document_dict)

# Scored card
card = create_scored_card(
    page, index=0, doc=document_dict,
    ai_score=4.5, reasoning="...", show_controls=True
)

# Citation card
card = create_citation_card(
    page, index=0, doc=document_dict, citation_data={...}
)
```

## Document Dictionary Format

The component expects documents in this format:

```python
document = {
    'id': 64396205,                    # Database ID
    'title': 'Document Title',
    'authors': ['Author 1', 'Author 2'],  # List or comma-separated string
    'publication': 'Journal Name',
    'year': '2023',
    'publication_date': '2023-01-01',  # Optional, more precise than year
    'abstract': 'Full abstract text...',
    'pmid': '12345678',                # Optional
    'doi': '10.1234/example',          # Optional
    'pdf_path': '/path/to/file.pdf',   # Optional, local PDF path
    'pdf_url': 'https://...',          # Optional, download URL
}
```

## Full-Text Access Buttons

The component automatically determines which button to show:

1. **View Full Text** (Blue): PDF exists at `pdf_path`
   - Opens PDF in system viewer
   - Uses `PDFViewerDialog.show_pdf()`

2. **Fetch Full Text** (Orange): `pdf_url` is available but no local PDF
   - Downloads PDF from URL
   - Saves to organized storage
   - Opens after download
   - Uses `PDFViewerDialog.download_and_show_pdf()`

3. **Upload Full Text** (Green): No `pdf_path` or `pdf_url`
   - Shows file picker
   - Copies selected PDF to organized storage
   - Opens after import
   - Uses `PDFViewerDialog.import_pdf()`

## Score Display Logic

The component intelligently displays scores in the collapsed title:

- **Human score takes precedence** if available (shown as "Human" badge)
- **AI score** shown if no human score (shown as "AI" badge)
- **Relevance score** for citations (shown as "Rel" badge)
- Color-coded based on value:
  - 1-5 scale: Green (≥4.5), Blue (≥3.5), Orange (≥2.5), Red (<2.5)
  - 0-1 scale: Green (≥0.8), Blue (≥0.6), Orange (≥0.4), Red (<0.4)

## Citation Features

When `citation_data` is provided:

- **Summary Section**: Highlighted in green background
- **Cited Passage**: Yellow background with border and emoji marker
- **Abstract Highlighting**: Automatically finds and highlights the passage in the full abstract
- **Relevance Badge**: Shows 0-1 score in collapsed title

## Integration with Existing Tabs

### Updating Literature Tab

```python
# OLD
from bmlibrarian.gui.document_card_utils import create_document_card

cards = [create_document_card(i, doc) for i, doc in enumerate(documents)]

# NEW
from bmlibrarian.gui.unified_document_card import create_literature_card

card_creator = UnifiedDocumentCard(page)
cards = [card_creator.create_card(i, doc, context=DocumentCardContext.LITERATURE)
         for i, doc in enumerate(documents)]
```

### Updating Scoring Tab

```python
# OLD
from bmlibrarian.gui.document_card_utils import create_scored_document_cards_list

cards = create_scored_document_cards_list(scored_documents)

# NEW
from bmlibrarian.gui.unified_document_card import UnifiedDocumentCard, DocumentCardContext

card_creator = UnifiedDocumentCard(page)
cards = [
    card_creator.create_card(
        i, doc,
        context=DocumentCardContext.SCORING,
        ai_score=score,
        scoring_reasoning=reasoning,
        show_scoring_controls=True,
        on_score_change=handle_score_change,
        on_score_approve=handle_approve
    )
    for i, (doc, score, reasoning) in enumerate(scored_documents)
]
```

### Updating Citations Tab

```python
# OLD
from bmlibrarian.gui.citation_card_utils import create_citation_card

cards = [create_citation_card(i, cit) for i, cit in enumerate(citations)]

# NEW
from bmlibrarian.gui.unified_document_card import create_citation_card

cards = [
    create_citation_card(page, i, citation.document, citation_data={
        'summary': citation.summary,
        'passage': citation.passage,
        'relevance_score': citation.relevance_score
    })
    for i, citation in enumerate(citations)
]
```

## PDF Manager Integration

To enable full PDF functionality, pass a PDFManager instance:

```python
from bmlibrarian.utils.pdf_manager import PDFManager

pdf_manager = PDFManager()
card_creator = UnifiedDocumentCard(
    page,
    pdf_manager=pdf_manager,
    on_pdf_status_change=lambda doc_id, status: print(f"PDF {status} for {doc_id}")
)
```

## Styling and Appearance

The component matches the design shown in your screenshot:

- **Collapsed State**:
  - Title (truncated to 80 chars)
  - Score badge (color-coded, rounded)
  - Authors and publication info in subtitle

- **Expanded State**:
  - Full title (bold, blue)
  - Authors (gray)
  - Metadata section (gray background)
  - Score section (if applicable)
  - Citation sections (if applicable)
  - Abstract (light gray background)
  - Full-text button

- **Colors**:
  - Primary: Blue (#2196F3 family)
  - Success: Green (#4CAF50 family)
  - Warning: Orange (#FF9800 family)
  - Error: Red (#F44336 family)
  - Background: Gray (#ECEFF1 family)

## Testing

Run the demo to see all card variations:

```bash
uv run python examples/unified_card_demo.py
```

The demo shows:
1. Basic literature search card
2. Scoring card with human controls
3. Citation card with highlighted passage
4. Card with both AI and human scores
5. Card with local PDF (View button)
6. Card with URL (Fetch button)
7. Card without PDF source (Upload button)

## Best Practices

1. **Always use the same card creator instance** within a tab to ensure consistent behavior
2. **Provide citation_data only in citation contexts** to keep cards focused
3. **Show scoring controls only when needed** (not for read-only views)
4. **Use appropriate context constants** instead of string literals
5. **Handle callbacks appropriately** - they may be called frequently
6. **Pass PDFManager instance** if PDF functionality is needed

## Migration Guide

To migrate existing code to the unified card:

1. Replace imports:
   ```python
   # OLD
   from bmlibrarian.gui.document_card_utils import create_document_card
   from bmlibrarian.gui.citation_card_utils import create_citation_card

   # NEW
   from bmlibrarian.gui.unified_document_card import UnifiedDocumentCard, DocumentCardContext
   ```

2. Create card creator instance (once per tab):
   ```python
   card_creator = UnifiedDocumentCard(page)
   ```

3. Update card creation calls:
   ```python
   # Determine context
   context = DocumentCardContext.LITERATURE  # or SCORING, CITATIONS, etc.

   # Create card with appropriate parameters
   card = card_creator.create_card(
       index=i,
       doc=doc,
       context=context,
       # Add context-specific parameters as needed
   )
   ```

4. Test thoroughly to ensure callbacks work as expected

## Future Enhancements

Potential future improvements:

- Batch PDF operations (download multiple at once)
- PDF preview thumbnails
- Inline PDF viewer (embedded in card)
- Export citations in various formats
- Drag-and-drop PDF upload
- PDF metadata extraction and validation
- Automatic DOI/PMID lookup for missing PDFs
