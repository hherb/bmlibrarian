# Citation-Aware Writing Editor - User Guide

## Overview

The BMLibrarian Writing Plugin provides a citation-aware markdown editor designed for academic and biomedical writing. It integrates directly with the literature database to enable seamless citation management while writing manuscripts, reports, and systematic review documents.

## Key Features

- **Citation-Aware Markdown Editor**: Write in markdown with automatic citation formatting
- **Semantic Search Integration**: Find and cite references from your local literature database
- **Multiple Citation Styles**: Support for Vancouver, APA, Harvard, and Chicago citation formats
- **Autosave with Version History**: Never lose your work with automatic saves
- **Export with Formatted References**: Export to markdown or other formats with properly formatted reference lists
- **Database Persistence**: Documents saved to PostgreSQL for reliable storage

## Quick Start

### Launching the Editor

```bash
# Launch the main Qt GUI with Writing tab
uv run python bmlibrarian_qt.py

# Navigate to the "Writing" tab
```

### Basic Workflow

1. **Open or create a document** - Start a new document or load an existing one
2. **Write your content** - Use standard markdown syntax
3. **Add citations** - Use the citation search panel to find references
4. **Insert citations** - Click to insert citations at cursor position
5. **Export** - Generate formatted output with reference list

## Citation Format

Citations are inserted using a special marker format:

```markdown
This treatment has shown efficacy in clinical trials [@id:12345:Smith2023].
```

The format is: `[@id:{document_id}:{label}]`

- `{document_id}`: The database ID of the cited document
- `{label}`: Human-readable label (typically "FirstAuthorYear")

### Example Document

```markdown
# Treatment Efficacy Review

## Background

Statins have been widely studied for cardiovascular disease prevention
[@id:54321:Johnson2020]. Multiple trials have demonstrated their
effectiveness [@id:67890:Williams2022].

## Methods

We followed PRISMA guidelines [@id:11111:Page2021] for this review.

## Results

...
```

## Citation Styles

The editor supports multiple academic citation styles:

### Vancouver (Default)

Numeric citations for biomedical journals:

**In-text**: "...has been shown effective [1]."

**Reference list**:
```
1. Smith J, Johnson A. Title of article. J Med. 2023;45(2):123-130.
```

### APA

Author-year citations for psychology and social sciences:

**In-text**: "...has been shown effective (Smith & Johnson, 2023)."

**Reference list**:
```
Smith, J., & Johnson, A. (2023). Title of article. Journal of Medicine, 45(2), 123-130.
```

### Harvard

Similar to APA but with different formatting:

**In-text**: "...has been shown effective (Smith & Johnson 2023)."

**Reference list**:
```
Smith, J. and Johnson, A. (2023) 'Title of article', Journal of Medicine, 45(2), pp. 123-130.
```

### Chicago

Note-based citations for humanities:

**In-text**: "...has been shown effective.¹"

**Reference list**:
```
1. John Smith and Alice Johnson, "Title of Article," Journal of Medicine 45, no. 2 (2023): 123-130.
```

## Searching for References

### Semantic Search

Use the search panel to find relevant references:

1. Enter your search query (e.g., "statin cardiovascular prevention")
2. Click "Search" or press Enter
3. Results show matching documents with relevance scores
4. Click a result to view details
5. Click "Insert Citation" to add to your document

### Search Tips

- Use natural language queries for best results
- Search by topic, author, or specific concepts
- Results are ranked by semantic similarity to your query
- PMID and DOI searches also supported

## Document Management

### Creating Documents

1. Click "New Document" button
2. Enter a title when prompted
3. Start writing immediately

### Saving Documents

- **Autosave**: Enabled by default (every 60 seconds)
- **Manual save**: Ctrl+S or click "Save" button
- **Save As**: Save with a new title

### Version History

The editor maintains version history:

- Autosave versions preserved automatically
- Manual saves marked distinctly
- Export operations create version snapshots
- Restore previous versions from history panel

### Loading Documents

1. Click "Open" button
2. Select from recent documents
3. Or search by title/content

## Export Options

### Markdown Export

Export with formatted citations and reference list:

```bash
# Example output file structure
document.md       # Main content with formatted citations
references.md     # Formatted reference list
```

### Export Settings

Configure export options:

- **Citation style**: Select from Vancouver, APA, Harvard, Chicago
- **Include abstract**: Add document abstract if available
- **Reference section title**: Customize "References" heading
- **Number references**: Use numbered or author-year format

## Integration with Research Workflow

### From Research Tab

Research results can be sent to the Writing tab:

1. Complete a research workflow
2. Click "Send to Writing" on citations or report
3. Content inserted at cursor position

### From Literature Tab

Documents from literature search can be cited:

1. Find relevant documents in Literature tab
2. Right-click and select "Send to Writing"
3. Citation marker inserted

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Ctrl+S | Save document |
| Ctrl+N | New document |
| Ctrl+O | Open document |
| Ctrl+F | Find in document |
| Ctrl+B | Bold text |
| Ctrl+I | Italic text |
| Ctrl+Shift+C | Insert citation (opens search) |
| Ctrl+E | Export document |

## Configuration

Settings can be adjusted in `~/.bmlibrarian/config.json`:

```json
{
  "writing": {
    "default_citation_style": "vancouver",
    "autosave_enabled": true,
    "autosave_interval_seconds": 60,
    "max_versions": 50,
    "default_export_format": "markdown"
  }
}
```

## Troubleshooting

### Citations Not Resolving

If citation labels show as `[?]`:

1. Check that the document ID exists in the database
2. Verify database connection is active
3. Try refreshing the document

### Autosave Not Working

1. Check disk space availability
2. Verify PostgreSQL connection
3. Check config for `autosave_enabled: true`

### Export Formatting Issues

1. Verify citation style is properly selected
2. Check that all cited documents have metadata
3. Try a different export format

## Best Practices

### Writing Workflow

1. **Start with outline** - Create document structure first
2. **Add citations as you go** - Insert citations while writing
3. **Review citation completeness** - Ensure all claims are cited
4. **Check reference list** - Verify all references before submission
5. **Export and review** - Export final document for formatting review

### Citation Management

1. **Use consistent labels** - Maintain readable citation labels
2. **Verify document IDs** - Double-check citation links
3. **Organize by section** - Keep related citations together
4. **Update as needed** - Refresh citations if database changes

## Related Documentation

- [Document Interrogation Guide](document_interrogation_guide.md) - Q&A with documents
- [Research GUI Guide](research_gui_guide.md) - Research workflow integration
- [Citation Guide](citation_guide.md) - Citation extraction details
