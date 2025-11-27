# Citation Editor System - Developer Documentation

## Overview

The Citation Editor is a comprehensive markdown editing system with integrated citation management. It consists of a core `writing` module for data operations and a Qt-based GUI widget for user interaction.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        CitationEditorWidget                              │
│  ┌─────────────────────────────┐  ┌─────────────────────────────┐       │
│  │  Left Panel (QTabWidget)    │  │  Right Panel (QTabWidget)   │       │
│  │  ├─ MarkdownEditorWidget    │  │  ├─ CitationSearchPanel     │       │
│  │  └─ CitationMarkdownPreview │  │  └─ CitationDocumentPanel   │       │
│  └─────────────────────────────┘  └─────────────────────────────┘       │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    CitationManager                                │    │
│  │  (Coordinates between UI components and writing module)          │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                         Writing Module                                    │
│  ┌────────────────┐  ┌──────────────────┐  ┌────────────────────────┐   │
│  │ CitationParser │  │ CitationFormatter │  │   ReferenceBuilder     │   │
│  │ - Parse [@id:] │  │ - Vancouver      │  │ - Fetch metadata       │   │
│  │ - Extract IDs  │  │ - APA            │  │ - Build reference list │   │
│  │ - Format       │  │ - Harvard        │  │ - Validate citations   │   │
│  └────────────────┘  │ - Chicago        │  └────────────────────────┘   │
│                      └──────────────────┘                                │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    DocumentStore                                  │    │
│  │  - CRUD operations for writing.documents                         │    │
│  │  - Version management (writing.document_versions)                │    │
│  │  - Autosave and cleanup                                          │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                         PostgreSQL Database                               │
│  ┌─────────────────────┐  ┌─────────────────────────────────────────┐   │
│  │ writing.documents   │  │ writing.document_versions               │   │
│  │ - id                │  │ - id                                    │   │
│  │ - title             │  │ - document_id (FK)                      │   │
│  │ - content           │  │ - content                               │   │
│  │ - metadata (JSONB)  │  │ - version_type                          │   │
│  │ - user_id (FK)      │  │ - saved_at                              │   │
│  └─────────────────────┘  └─────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────┘
```

## Module Structure

```
src/bmlibrarian/
├── writing/                           # Core writing module
│   ├── __init__.py                    # Module exports
│   ├── constants.py                   # Configuration constants
│   ├── models.py                      # Data models (Citation, WritingDocument, etc.)
│   ├── citation_parser.py             # Parse [@id:N:Label] from text
│   ├── citation_formatter.py          # Format references (Vancouver, APA, etc.)
│   ├── document_store.py              # Database operations
│   └── reference_builder.py           # Build reference lists
│
└── gui/qt/
    ├── widgets/citation_editor/       # Qt widget components
    │   ├── __init__.py
    │   ├── citation_editor_widget.py  # Main widget
    │   ├── markdown_editor.py         # Editor with syntax highlighting
    │   ├── markdown_preview.py        # Preview renderer
    │   ├── search_panel.py            # Citation search
    │   ├── document_panel.py          # Document viewer + insert
    │   ├── citation_manager.py        # Coordination layer
    │   └── syntax_highlighter.py      # Markdown + citation highlighting
    │
    └── plugins/writing/               # BMLibrarian plugin wrapper
        ├── __init__.py
        └── plugin.py                  # WritingPlugin class
```

## Data Models

### Citation

```python
@dataclass
class Citation:
    document_id: int      # Database document ID
    label: str            # Human-readable label (e.g., "Smith2023")
    position: int         # Character position in text
    text: str             # Full marker text: [@id:12345:Smith2023]
```

### DocumentMetadata

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
    volume: Optional[str]
    issue: Optional[str]
    pages: Optional[str]
    publication_date: Optional[str]
```

### WritingDocument

```python
@dataclass
class WritingDocument:
    id: Optional[int]                    # None for unsaved
    title: str = "Untitled Document"
    content: str = ""                    # Markdown with citation markers
    metadata: Dict[str, Any] = {}        # Editor state, settings
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    user_id: Optional[int] = None
```

## Citation Parser

The `CitationParser` class handles parsing and manipulation of citation markers.

### Citation Pattern

```python
CITATION_PATTERN = re.compile(r'\[@id:(\d+):([^\]]+)\]')
```

Captures:
- Group 1: Document ID (integer)
- Group 2: Label (string)

### Key Methods

```python
class CitationParser:
    def parse_citations(self, text: str) -> List[Citation]:
        """Extract all citations from text in order of appearance."""

    def get_unique_document_ids(self, text: str) -> List[int]:
        """Get unique document IDs in order of first appearance."""

    def create_citation_marker(self, doc_id: int, label: str) -> str:
        """Create: [@id:12345:Smith2023]"""

    def replace_all_citations_with_numbers(
        self, text: str, id_to_number: Dict[int, int]
    ) -> str:
        """Replace markers with [1], [2], etc."""

    def find_adjacent_citations(self, text: str) -> List[List[Citation]]:
        """Group adjacent citations for combining like [1,2,3]."""
```

## Citation Formatter

Supports multiple citation styles via strategy pattern.

### Style Implementations

```python
class CitationFormatter:
    _formatters = {
        CitationStyle.VANCOUVER: VancouverFormatter,
        CitationStyle.APA: APAFormatter,
        CitationStyle.HARVARD: HarvardFormatter,
        CitationStyle.CHICAGO: ChicagoFormatter,
    }

    def format_reference(
        self, metadata: DocumentMetadata, number: Optional[int] = None
    ) -> str:
        """Format a single reference entry."""

    def format_inline_citation(
        self, metadata: DocumentMetadata, number: Optional[int] = None
    ) -> str:
        """Format inline citation (e.g., [1] or (Smith, 2023))."""
```

### Adding a New Style

1. Create a new formatter class inheriting from `BaseFormatter`:

```python
class NewStyleFormatter(BaseFormatter):
    def format_reference(self, metadata, number=None) -> str:
        # Implementation

    def format_inline_citation(self, metadata, number=None) -> str:
        # Implementation
```

2. Add to `CitationStyle` enum in `constants.py`:

```python
class CitationStyle(str, Enum):
    # ...existing...
    NEW_STYLE = "new_style"
```

3. Register in `CitationFormatter._formatters`:

```python
_formatters = {
    # ...existing...
    CitationStyle.NEW_STYLE: NewStyleFormatter,
}
```

## Document Store

Handles persistence to the `writing` schema.

### Key Operations

```python
class DocumentStore:
    def create_document(
        self, title: str, content: str, user_id: Optional[int] = None
    ) -> WritingDocument:
        """Create new document in database."""

    def save_document(
        self, document: WritingDocument, version_type: str = "manual"
    ) -> WritingDocument:
        """Save document and create version snapshot."""

    def autosave_document(self, document: WritingDocument) -> WritingDocument:
        """Autosave only if content changed."""

    def load_document(self, document_id: int) -> Optional[WritingDocument]:
        """Load document by ID."""

    def get_versions(self, document_id: int, limit: int = 20) -> List[DocumentVersion]:
        """Get version history."""

    def restore_version(self, document_id: int, version_id: int) -> Optional[WritingDocument]:
        """Restore to a previous version."""

    def cleanup_old_versions(self, document_id: int, max_versions: int = 10) -> int:
        """Remove old autosave versions."""
```

## Reference Builder

Coordinates citation parsing, metadata fetching, and formatting.

```python
class ReferenceBuilder:
    def build_references(self, text: str) -> Tuple[str, List[FormattedReference]]:
        """
        Build formatted document with reference list.

        Returns:
            - formatted_text: Text with citations replaced
            - references: List of formatted reference entries
        """

    def format_document(
        self, text: str, include_reference_list: bool = True
    ) -> str:
        """Format complete document with optional reference list."""

    def validate_citations(self, text: str) -> List[Dict]:
        """Check all citations reference valid documents."""

    def create_citation_marker(self, document_id: int) -> str:
        """Create marker with auto-generated label."""
```

## Qt Widget Components

### MarkdownEditorWidget

`QPlainTextEdit` subclass with:
- Markdown + citation syntax highlighting
- Line numbers
- Right-click context menu
- Drag-and-drop support
- Keyboard shortcuts

Key signals:
```python
text_changed = Signal(str)
selection_changed = Signal(str)
citation_search_requested = Signal(str)
insert_citation_shortcut = Signal()
```

### CitationSearchPanel

Search interface with:
- Search bar (semantic/keyword toggle)
- Document card list
- Background search worker

Key signals:
```python
document_selected = Signal(dict)
document_double_clicked = Signal(dict)
```

### CitationDocumentPanel

Document viewer with:
- 3-tab document display (metadata, PDF, full text)
- Insert Citation button
- Back to Search button

Key signals:
```python
insert_citation = Signal(int, str)  # document_id, label
back_to_search = Signal()
```

### CitationManager

Coordination layer between UI and writing module.

```python
class CitationManager(QObject):
    citations_updated = Signal(int, int)  # total, unique
    reference_list_ready = Signal(str, list)
    validation_complete = Signal(list)

    def update_text(self, text: str) -> None:
        """Update text and emit citation count."""

    def format_citations(self, text: Optional[str] = None) -> Tuple[str, list]:
        """Format document with references."""

    def get_citation_metadata_for_preview(self) -> Dict[int, Dict]:
        """Get metadata for tooltip previews."""
```

## Database Schema

### Migration: 023_create_writing_schema.sql

```sql
CREATE SCHEMA IF NOT EXISTS writing;

CREATE TABLE writing.documents (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL DEFAULT 'Untitled Document',
    content TEXT NOT NULL DEFAULT '',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_id INTEGER REFERENCES public.users(id)
);

CREATE TABLE writing.document_versions (
    id SERIAL PRIMARY KEY,
    document_id INTEGER REFERENCES writing.documents(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    title VARCHAR(255),
    version_type VARCHAR(20) NOT NULL DEFAULT 'autosave',
    saved_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

## Plugin Integration

The `WritingPlugin` class integrates with BMLibrarian's plugin system:

```python
class WritingPlugin(BaseTabPlugin):
    def get_metadata(self) -> TabPluginMetadata:
        return TabPluginMetadata(
            plugin_id="writing",
            display_name="Writing",
            description="Citation-aware markdown editor",
            version="1.0.0"
        )

    def create_widget(self, parent=None) -> QWidget:
        return CitationEditorWidget(parent)
```

## Extending the System

### Adding New Features

1. **New search source**: Extend `SearchWorker` with additional search methods
2. **New export format**: Add methods to `CitationEditorWidget._export_*`
3. **New editor features**: Extend `MarkdownEditorWidget`

### Custom Citation Handling

For special citation needs, subclass `CitationParser`:

```python
class CustomCitationParser(CitationParser):
    def __init__(self):
        super().__init__()
        self._pattern = re.compile(r'your_custom_pattern')
```

### Integration with Other Modules

The widget can be embedded in other applications:

```python
from bmlibrarian.gui.qt.widgets.citation_editor import CitationEditorWidget

editor = CitationEditorWidget(parent=my_window)
editor.set_content("# My Document")
editor.trigger_search("cardiovascular disease")
```

## Testing

Run tests for the writing module:

```bash
uv run python -m pytest tests/test_citation_parser.py
uv run python -m pytest tests/test_citation_formatter.py
uv run python -m pytest tests/test_document_store.py
```

## Configuration

Default configuration in `constants.py`:

```python
AUTOSAVE_INTERVAL_SECONDS = 60
MAX_VERSIONS = 10
DEFAULT_CITATION_STYLE = CitationStyle.VANCOUVER
SEMANTIC_SEARCH_THRESHOLD = 0.5
SEMANTIC_SEARCH_LIMIT = 20
MAX_AUTHORS_BEFORE_ET_AL = 6
```

Override via `~/.bmlibrarian/config.json`:

```json
{
  "writing": {
    "autosave_interval_seconds": 120,
    "max_versions": 20,
    "default_citation_style": "apa"
  }
}
```

## Performance Considerations

1. **Autosave debouncing**: Content changes trigger autosave timer reset
2. **Preview update debouncing**: 500ms delay after text changes
3. **Metadata caching**: Citation metadata cached in `CitationManager`
4. **Version cleanup**: Old autosave versions automatically removed

## Error Handling

The system handles:
- Missing documents (validation warnings)
- Database connection errors (logged, autosave skipped)
- Invalid citation format (parser skips, logs warning)
- Search failures (error displayed, search aborted)
