# Writing System - Developer Documentation

## Overview

The BMLibrarian Writing System provides a citation-aware markdown editor for academic writing. It consists of a core writing module with citation parsing, formatting, and document persistence, plus a Qt-based GUI plugin.

## Architecture

### Module Structure

```
src/bmlibrarian/
├── writing/                     # Core writing module
│   ├── __init__.py              # Module exports
│   ├── models.py                # Data models (Citation, WritingDocument, etc.)
│   ├── constants.py             # Configuration constants
│   ├── citation_parser.py       # Citation marker extraction
│   ├── citation_formatter.py    # Citation style formatting
│   ├── reference_builder.py     # Reference list generation
│   └── document_store.py        # Database persistence
│
└── gui/qt/plugins/writing/      # Qt GUI plugin
    ├── __init__.py              # Plugin exports
    ├── plugin.py                # Plugin registration
    └── ... (widget files)

migrations/
└── 023_create_writing_schema.sql  # Database schema
```

## Core Components

### Data Models (`models.py`)

#### Citation

Represents a citation marker in text:

```python
@dataclass
class Citation:
    document_id: int      # Database document ID
    label: str            # Human-readable label ("Smith2023")
    position: int         # Character position in text
    text: str             # Full marker text ("[@id:12345:Smith2023]")
```

#### DocumentMetadata

Bibliographic metadata for cited documents:

```python
@dataclass
class DocumentMetadata:
    document_id: int
    title: str
    authors: List[str]
    journal: Optional[str]
    year: Optional[int]
    pmid: Optional[str]
    doi: Optional[str]
    # ... additional fields
```

#### WritingDocument

A document being edited:

```python
@dataclass
class WritingDocument:
    id: Optional[int]
    title: str
    content: str
    metadata: Dict[str, Any]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    user_id: Optional[int]
```

### Citation Parser (`citation_parser.py`)

Extracts citation markers from markdown text:

```python
from bmlibrarian.writing import CitationParser

parser = CitationParser()

# Extract all citations from text
citations = parser.extract_citations(markdown_text)
for citation in citations:
    print(f"Document {citation.document_id}: {citation.label}")

# Get unique document IDs
doc_ids = parser.get_document_ids(markdown_text)
```

#### Citation Pattern

The parser uses this regex pattern:

```python
CITATION_PATTERN = r'\[@id:(\d+):([^\]]+)\]'
# Group 1: document_id
# Group 2: label
```

### Citation Formatter (`citation_formatter.py`)

Formats citations and references in various styles:

```python
from bmlibrarian.writing import CitationFormatter, CitationStyle

formatter = CitationFormatter(style=CitationStyle.VANCOUVER)

# Format in-text citation
in_text = formatter.format_in_text(metadata, number=1)
# Result: "[1]"

# Format reference list entry
reference = formatter.format_reference(metadata, number=1)
# Result: "1. Smith J, Johnson A. Title. Journal. 2023;45(2):123-130."
```

#### Supported Styles

```python
class CitationStyle(Enum):
    VANCOUVER = "vancouver"    # Numeric, biomedical
    APA = "apa"               # Author-year, psychology
    HARVARD = "harvard"       # Author-year variant
    CHICAGO = "chicago"       # Note-based, humanities
```

### Reference Builder (`reference_builder.py`)

Builds complete reference lists:

```python
from bmlibrarian.writing import ReferenceBuilder

builder = ReferenceBuilder(conn, style=CitationStyle.VANCOUVER)

# Build references for a document
content = "Treatment [@id:123:Smith2023] worked well [@id:456:Jones2024]."
references = builder.build_references(content)

for ref in references:
    print(f"{ref.number}. {ref.formatted_text}")
```

### Document Store (`document_store.py`)

Handles database persistence:

```python
from bmlibrarian.writing import DocumentStore, WritingDocument

store = DocumentStore(conn)

# Create document
doc = WritingDocument(title="My Paper", content="# Introduction\n...")
doc_id = store.save(doc)

# Load document
loaded = store.get(doc_id)

# List documents
docs = store.list_documents(user_id=1, limit=10)

# Save version
store.create_version(doc_id, version_type="manual")

# Get versions
versions = store.get_versions(doc_id)
```

## Database Schema

### Schema: `writing`

```sql
-- Writing documents table
CREATE TABLE writing.documents (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_id INTEGER REFERENCES public.users(id)
);

-- Document versions for history
CREATE TABLE writing.document_versions (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES writing.documents(id),
    title TEXT,
    content TEXT NOT NULL,
    version_type TEXT NOT NULL DEFAULT 'autosave',
    saved_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Citation cache for resolved metadata
CREATE TABLE writing.citation_cache (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES writing.documents(id),
    cited_doc_id INTEGER NOT NULL,
    label TEXT NOT NULL,
    metadata JSONB,
    cached_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(document_id, cited_doc_id)
);
```

## Qt GUI Plugin

### Plugin Structure

```python
class WritingPlugin(BaseTabPlugin):
    """Plugin for Citation-Aware Markdown Editor."""

    def get_metadata(self) -> TabPluginMetadata:
        return TabPluginMetadata(
            plugin_id="writing",
            display_name="Writing",
            description="Citation-aware markdown editor...",
            version="1.0.0"
        )

    def create_widget(self, parent: QWidget) -> QWidget:
        return CitationEditorWidget(parent)
```

### CitationEditorWidget

Main editor widget with:

- Markdown editor pane (syntax highlighting)
- Citation search panel
- Reference list preview
- Document management toolbar

#### Signals

```python
# Emitted when document is saved
document_saved = Signal(int)  # document_id

# Emitted when document is exported
document_exported = Signal(str)  # file_path

# Emitted when unsaved changes status changes
unsaved_changes = Signal(bool)  # has_changes
```

## Integration Points

### Research Tab Integration

Send citations from research to writing:

```python
# From research workflow
def on_send_to_writing(citations: List[Citation]):
    writing_plugin = plugin_manager.get_plugin("writing")
    for citation in citations:
        marker = f"[@id:{citation.document_id}:{citation.label}]"
        writing_plugin.insert_at_cursor(marker)
```

### Literature Tab Integration

Cite documents from literature search:

```python
# From document card context menu
def on_cite_document(document_id: int, metadata: DocumentMetadata):
    label = metadata.generate_label()
    marker = f"[@id:{document_id}:{label}]"
    # Insert via plugin API
```

## Configuration

### Constants (`constants.py`)

```python
# Autosave interval in seconds
AUTOSAVE_INTERVAL_SECONDS = 60

# Maximum versions to keep per document
MAX_VERSIONS = 50

# Default citation style
DEFAULT_CITATION_STYLE = CitationStyle.VANCOUVER

# Citation marker pattern
CITATION_PATTERN = r'\[@id:(\d+):([^\]]+)\]'
```

### Config File Settings

```json
{
  "writing": {
    "default_citation_style": "vancouver",
    "autosave_enabled": true,
    "autosave_interval_seconds": 60,
    "max_versions": 50,
    "editor_theme": "light"
  }
}
```

## Example Usage

### Complete Workflow

```python
from bmlibrarian.writing import (
    CitationParser,
    CitationFormatter,
    ReferenceBuilder,
    DocumentStore,
    WritingDocument,
    CitationStyle
)

# Initialize components
conn = get_database_connection()
parser = CitationParser()
builder = ReferenceBuilder(conn, style=CitationStyle.VANCOUVER)
store = DocumentStore(conn)

# Create document
doc = WritingDocument(
    title="Statin Efficacy Review",
    content="""
# Introduction

Statins have been studied extensively [@id:123:Smith2023].

# Methods

We followed PRISMA guidelines [@id:456:Page2021].

# Results

Multiple trials show benefit [@id:123:Smith2023] [@id:789:Jones2024].
"""
)

# Save document
doc_id = store.save(doc)

# Build reference list
references = builder.build_references(doc.content)

# Export with references
output = f"{doc.content}\n\n## References\n\n"
for ref in references:
    output += f"{ref.formatted_text}\n\n"

# Save to file
with open("output.md", "w") as f:
    f.write(output)
```

### Custom Citation Style

```python
from bmlibrarian.writing import CitationFormatter, CitationStyle, DocumentMetadata

# Create custom formatter
formatter = CitationFormatter(style=CitationStyle.APA)

# Format metadata
metadata = DocumentMetadata(
    document_id=123,
    title="Statin Effects on Cardiovascular Disease",
    authors=["Smith, John", "Johnson, Alice"],
    journal="Journal of Medicine",
    year=2023,
    volume="45",
    issue="2",
    pages="123-130"
)

# Get formatted output
in_text = formatter.format_in_text(metadata, number=1)
# "(Smith & Johnson, 2023)"

reference = formatter.format_reference(metadata, number=1)
# "Smith, J., & Johnson, A. (2023). Statin Effects..."
```

## Testing

### Unit Tests

```bash
# Run writing module tests
uv run python -m pytest tests/test_writing.py -v

# Run specific test
uv run python -m pytest tests/test_writing.py::test_citation_parser -v
```

### Test Coverage

```python
# Citation parsing
def test_extract_citations():
    parser = CitationParser()
    text = "Study [@id:123:Smith2023] and [@id:456:Jones2024]."
    citations = parser.extract_citations(text)
    assert len(citations) == 2
    assert citations[0].document_id == 123

# Reference formatting
def test_vancouver_format():
    formatter = CitationFormatter(CitationStyle.VANCOUVER)
    ref = formatter.format_reference(metadata, number=1)
    assert ref.startswith("1. Smith J")
```

## Future Enhancements

1. **Collaborative editing**: Multi-user document editing
2. **Template system**: Document templates for common formats
3. **Bibliography import**: Import from BibTeX, EndNote, Zotero
4. **Citation suggestions**: AI-powered citation recommendations
5. **DOCX export**: Export to Microsoft Word format
6. **LaTeX export**: Export for academic publishing

## Related Documentation

- [User Guide](../users/writing_plugin_guide.md) - End-user documentation
- [Citation System](citation_system.md) - Citation extraction architecture
- [Plugin System](plugin_system.md) - Qt plugin architecture
