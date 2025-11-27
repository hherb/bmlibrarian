# Citation Editor User Guide

The Citation Editor is a markdown-based writing tool with integrated citation management. It helps you write academic documents while seamlessly inserting and managing references from the BMLibrarian database.

## Overview

The Citation Editor provides:

- **Split-pane layout**: Editor/preview on the left, search/document viewer on the right
- **Markdown support**: Full markdown syntax with live preview
- **Citation management**: Insert references using `[@id:12345:Smith2023]` format
- **Semantic search**: Find relevant papers by searching or right-clicking text
- **Multiple citation styles**: Vancouver, APA, Harvard, Chicago
- **Autosave**: Automatic saving with version history
- **Export**: Export formatted documents with proper reference lists

## Getting Started

### Creating a New Document

1. Launch the Citation Editor from the BMLibrarian menu
2. Enter a document title in the toolbar
3. Start writing in the editor pane

### The Interface

```
┌─────────────────────────────────────────────────────────────────────────┐
│ [Title Input] [New] [Open] [Save] [Export ▼] [Format Citations] [Style]│
├────────────────────────────────────┬────────────────────────────────────┤
│  ┌──────────┬─────────────┐        │  ┌──────────┬─────────────┐        │
│  │ Editor ✓ │ Preview     │        │  │ Search ✓ │ Document    │        │
│  └──────────┴─────────────┘        │  └──────────┴─────────────┘        │
│                                    │                                    │
│  [Markdown editor with             │  [Search bar and results or        │
│   citation highlighting]           │   document viewer with             │
│                                    │   insert citation button]          │
│                                    │                                    │
├────────────────────────────────────┴────────────────────────────────────┤
│ Citations: 5 (3 unique) │ Words: 1,234 │ Auto-saved 2 min ago          │
└─────────────────────────────────────────────────────────────────────────┘
```

## Working with Citations

### Citation Format

Citations use the format: `[@id:12345:Smith2023]`

- `@id:` - Prefix indicating a document ID follows
- `12345` - The database document ID
- `Smith2023` - Human-readable label (author surname + year)

Example in text:
```markdown
Exercise has cardiovascular benefits [@id:12345:Smith2023]. Recent studies show
a 30% reduction in mortality rates [@id:23456:Johnson2022].
```

### Inserting Citations

#### Method 1: Search and Insert

1. Use the search bar in the right panel
2. Enter keywords or a research question
3. Click a result to view the document
4. Click "Insert Citation" to add it at the cursor position

#### Method 2: Right-Click Search

1. Highlight text in the editor (e.g., "cardiovascular benefits")
2. Right-click and select "Find Citations"
3. The system performs a semantic search for relevant papers
4. Click a result and insert the citation

#### Method 3: Keyboard Shortcut

1. View a document in the Document tab
2. Position cursor in editor where you want the citation
3. Press `Ctrl+Shift+K` to insert

#### Method 4: Drag and Drop

1. Drag a document card from search results
2. Drop it into the editor at the desired position
3. The citation is inserted automatically

#### Method 5: Double-Click

1. Double-click a document card in search results
2. The citation is inserted at the current cursor position

### Viewing Citation Information

- **In Editor**: Citations are highlighted in blue
- **In Preview**: Citations appear as clickable links
- **Hover Tooltips**: Hover over a citation to see title, authors, year
- **Click to View**: Click a citation in preview to open the document

## Citation Styles

The Citation Editor supports four citation styles:

### Vancouver (Default)

Best for medical and scientific writing. Uses numbered references.

**In-text**: `[1]`, `[1,2,3]`, `[1-3]`

**Reference list**:
```
1. Smith J, Johnson A. Title of the article. J Cardiol. 2023;45(2):123-134. doi:10.1234/example
```

### APA

Common in psychology and social sciences. Uses author-date format.

**In-text**: `(Smith, 2023)`, `(Smith & Johnson, 2023)`, `(Smith et al., 2023)`

**Reference list**:
```
Smith, J., & Johnson, A. (2023). Title of the article. Journal of Cardiology, 45(2), 123-134. https://doi.org/10.1234/example
```

### Harvard

Author-date variant popular in many disciplines.

**In-text**: `(Smith, 2023)`, `(Smith and Johnson, 2023)`

**Reference list**:
```
Smith, J. and Johnson, A. (2023) 'Title of the article', Journal of Cardiology, 45(2), pp. 123-134. doi: 10.1234/example.
```

### Chicago

Common in humanities. Uses author-date for scientific writing.

**In-text**: `(Smith 2023)`, `(Smith and Johnson 2023)`

**Reference list**:
```
Smith, John, and Anna Johnson. 2023. "Title of the Article." Journal of Cardiology 45 (2): 123-134. https://doi.org/10.1234/example.
```

## Formatting Your Document

### Format Citations Button

Click "Format Citations" to:
1. Replace citation markers with numbered/styled references
2. Generate a reference list
3. Preview the formatted result

The formatted version appears in the Preview tab.

### Export Options

Click the "Export ▼" button for options:

- **Markdown (formatted)**: Citations replaced with numbers, reference list appended
- **Markdown (raw)**: Keep citation markers intact (for further editing)
- **Copy to Clipboard (formatted)**: Copy formatted text
- **Copy to Clipboard (raw)**: Copy with markers

## Document Management

### Saving Documents

- **Manual Save**: Click "Save" or press `Ctrl+S`
- **Autosave**: Documents auto-save every 60 seconds (configurable)
- Saves to the `writing` schema in the database

### Opening Documents

1. Click "Open"
2. Select from the list of saved documents
3. Document loads with all citations intact

### Version History

The system maintains version history:
- Up to 10 autosave versions per document
- Manual saves are preserved separately
- Can restore from previous versions if needed

## Tips and Best Practices

### Efficient Citation Workflow

1. **Start with an outline**: Write your main points first
2. **Insert citations as you go**: Don't leave them for later
3. **Use semantic search**: Highlight key phrases and right-click
4. **Review in preview**: Check how citations will appear

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+S` | Save document |
| `Ctrl+Shift+K` | Insert citation from current document |
| `Ctrl+Z` | Undo |
| `Ctrl+Y` | Redo |
| `Tab` | Indent selection |
| `Shift+Tab` | Unindent selection |

### Search Tips

- **Semantic search**: Best for finding conceptually related papers
- **Keyword search**: Best for specific terms, PMIDs, or titles
- Use the dropdown to switch between search types

### Citation Best Practices

1. Cite primary sources when possible
2. Check that all citations resolve (validation on export)
3. Use consistent citation style throughout
4. Review the reference list before final export

## Configuration

Settings can be configured in `~/.bmlibrarian/config.json`:

```json
{
  "writing": {
    "autosave_interval_seconds": 60,
    "max_versions": 10,
    "default_citation_style": "vancouver",
    "editor_font_family": "monospace",
    "editor_font_size": 12,
    "show_line_numbers": true,
    "preview_sync_scroll": true
  }
}
```

## Troubleshooting

### Citation Not Found

If a citation shows as "[Document X not found]":
1. Check that the document exists in the database
2. Verify the document ID is correct
3. Re-insert the citation from search

### Autosave Not Working

1. Check database connection
2. Verify `writing` schema exists
3. Check `autosave_interval_seconds` in config

### Search Returns No Results

1. Try different search terms
2. Switch between semantic and keyword search
3. Check that the document database has content

## Related Documentation

- [Multi-Model Query Guide](multi_model_query_guide.md) - For advanced search
- [Semantic Search Guide](document_embedding_guide.md) - How search works
- [PDF Import Guide](pdf_import_guide.md) - Adding documents to search
