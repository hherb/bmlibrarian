# Document Interrogation Tab Implementation

## Summary

A new **Document Interrogation** tab has been added to the BMLibrarian Configuration GUI, providing an interactive interface for analyzing documents (PDF, Markdown, or text files) using AI language models from Ollama.

## What Was Built

### 1. Main Tab Component
**File**: `src/bmlibrarian/gui/tabs/document_interrogation_tab.py`

A complete Flet-based UI component with:
- **Split-pane layout**: 60% document viewer / 40% chat interface
- **Top bar controls**: File selector button and model dropdown
- **Document viewer**: Supports PDF (placeholder), Markdown (rendered), and text files
- **Chat interface**: Dialogue-style bubbles with user/AI distinction
- **Message input**: Multi-line text field with Enter to send, Shift+Enter for new line
- **Model selection**: Live refresh from Ollama server
- **Programmatic API**: Methods for external plugin integration

### 2. User Documentation
**File**: `doc/users/document_interrogation_guide.md`

Comprehensive 400+ line guide covering:
- Feature overview and capabilities
- Usage instructions and workflow
- UI layout specification with ASCII diagrams
- Keyboard shortcuts
- Future enhancements
- Troubleshooting
- Example workflows
- API reference

### 3. Developer Documentation
**File**: `doc/developers/document_interrogation_ui_spec.md`

Detailed 600+ line technical specification including:
- Complete component hierarchy
- Visual design specifications (colors, spacing, typography)
- State management details
- Interaction states (buttons, fields, dropdowns)
- Animations and transitions
- Accessibility features
- Responsive behavior
- File type handling
- Error handling
- Testing checklist

### 4. Integration

The tab has been integrated into the main config GUI:
- Added to `src/bmlibrarian/gui/tabs/__init__.py`
- Imported in `src/bmlibrarian/gui/config_app.py`
- Positioned as first tab (primary feature)
- Documented in `CLAUDE.md`

### 5. Test Script
**File**: `test_document_interrogation_gui.py`

Simple test harness for:
- Isolated tab testing
- Full GUI integration testing
- Visual verification

## Architecture

### Component Structure

```
DocumentInterrogationTab
├── _build_top_bar()
│   ├── File selector button (ElevatedButton)
│   ├── Current document label (Text)
│   ├── Model dropdown (Dropdown)
│   └── Refresh models button (IconButton)
│
├── _build_split_pane()
│   ├── _build_document_viewer_pane() [60% width]
│   │   ├── Header: "Document Viewer"
│   │   └── Content: Markdown | Text | PDF placeholder
│   │
│   └── _build_chat_interface_pane() [40% width]
│       ├── Header: "Chat"
│       ├── Chat messages (scrollable Column)
│       │   ├── Welcome message
│       │   ├── User messages (blue, right-aligned)
│       │   └── AI messages (grey, left-aligned)
│       └── Input area
│           ├── Message TextField (1-3 lines)
│           └── Send IconButton
│
└── Public API
    ├── load_document_programmatically(file_path)
    └── clear_chat()
```

### Key Features Implemented

1. **File Loading**
   - File picker integration with Flet
   - Support for `.pdf`, `.md`, `.txt` file types
   - Real-time document display
   - Markdown rendering with GitHub styling
   - PDF placeholder (rendering pending future implementation)

2. **Model Selection**
   - Dynamic model list from Ollama server
   - Refresh button to update available models
   - Auto-select first model if available
   - Uses app-wide Ollama configuration

3. **Chat Interface**
   - Styled message bubbles with distinct user/AI appearance
   - Auto-scroll to latest message
   - Message history tracking
   - Selectable text for copying
   - Input validation (requires document + model)

4. **Error Handling**
   - Snackbar notifications for errors
   - Graceful degradation on failures
   - Clear user feedback for missing requirements

## UI Design Highlights

### Layout Proportions
- **Top bar**: 60px fixed height
- **Document pane**: 60% width (expand=3)
- **Chat pane**: 40% width (expand=2)
- **Message bubbles**: Max 500px width for readability

### Color Scheme
- **Primary**: Blue 600 (#1E88E5) for actions and user messages
- **Neutral**: Grey palette for backgrounds and AI messages
- **Semantic**: Red 400 for PDF icons, Green for success states

### Typography
- **Headers**: 14px bold
- **Message content**: 13px normal
- **Labels**: 12px
- **Sender tags**: 10px bold

### Spacing
- Standard padding: 10px
- Message spacing: 5px bottom margin
- Container padding: 10-20px based on hierarchy

## Testing

### Manual Testing Checklist

```bash
# 1. Test isolated tab
uv run python test_document_interrogation_gui.py

# 2. Test full config GUI
uv run python test_document_interrogation_gui.py --full

# Or just launch the config GUI directly
uv run python bmlibrarian_config_gui.py
```

### Visual Tests
- [ ] Top bar displays correctly with all controls
- [ ] Split pane ratio is 60/40
- [ ] File selector opens file picker
- [ ] Model dropdown populates from Ollama
- [ ] Document displays in left pane after loading
- [ ] Chat messages appear correctly styled
- [ ] Message bubbles are properly aligned (user right, AI left)
- [ ] Input field allows multi-line entry
- [ ] Send button works

### Functional Tests
- [ ] Load Markdown file → renders with formatting
- [ ] Load text file → displays as plain text
- [ ] Load PDF file → shows placeholder
- [ ] Type message and send → appears in chat
- [ ] Enter key sends message
- [ ] Shift+Enter adds new line
- [ ] Error when no document loaded
- [ ] Error when no model selected
- [ ] Refresh models button updates dropdown

### Integration Tests
- [ ] Tab appears in config GUI
- [ ] Tab switches without errors
- [ ] Ollama configuration from General Settings works
- [ ] Programmatic document loading API works
- [ ] Clear chat function works

## Current Limitations

### PDF Rendering
**Status**: Placeholder only

**Current behavior**: Shows icon and filename, no actual page rendering

**Future**: Will use PyMuPDF or pdf2image for actual rendering

### LLM Integration
**Status**: Mock responses only

**Current behavior**: Displays placeholder message instead of actual LLM response

**Future**: Will send document context + question to Ollama and display streaming response

### Layout Resizing
**Status**: Fixed 60/40 split

**Current behavior**: Proportions are set via expand properties

**Future**: Draggable splitter for custom proportions

## Future Enhancements

### Phase 1: Core Functionality (Next)
1. **LLM Integration**
   - Send messages to Ollama with document context
   - Stream responses to chat interface
   - Handle errors gracefully

2. **PDF Rendering**
   - Implement PyMuPDF integration
   - Display actual PDF pages
   - Add page navigation

### Phase 2: Enhanced UX
1. **Chat Features**
   - Export conversation as markdown
   - Clear chat button in UI (not just programmatic)
   - Search within conversation
   - Timestamps on messages
   - Copy message buttons

2. **Layout Improvements**
   - Draggable splitter between panes
   - Collapsible document viewer
   - Full-screen mode for document
   - Resizable chat input (more than 3 lines)

### Phase 3: Advanced Features
1. **Document Analysis**
   - Auto-summarize on load
   - Extract table of contents
   - Identify key terms
   - Citation highlighting (click citation in AI response → highlight in document)

2. **Extended Format Support**
   - DOCX files (via python-docx)
   - HTML rendering
   - Code files with syntax highlighting
   - Images with OCR

## API for Plugin Integration

### Loading Documents Programmatically

```python
# Access the document interrogation tab
from src.bmlibrarian.gui.config_app import BMLibrarianConfigApp

app = BMLibrarianConfigApp()
doc_tab = app.tab_objects['document_interrogation']

# Load a document
doc_tab.load_document_programmatically('/path/to/document.pdf')

# Clear chat history
doc_tab.clear_chat()

# Access current state
current_doc = doc_tab.current_document_path
selected_model = doc_tab.selected_model
history = doc_tab.chat_history
```

### Example: Integration with Research Workflow

```python
# After literature search, load a paper for detailed analysis
def analyze_paper(paper_path: str):
    doc_tab = app.tab_objects['document_interrogation']
    doc_tab.load_document_programmatically(paper_path)

    # Optionally add a system message
    doc_tab._add_chat_message(
        f"📊 Loaded paper for analysis. Key findings will be highlighted.",
        is_user=False
    )
```

## Code Quality

### Follows BMLibrarian Patterns
- ✅ Inherits from common tab structure (similar to `GeneralSettingsTab`)
- ✅ Uses Flet framework consistently
- ✅ Follows existing color scheme and spacing
- ✅ Integrates with app-wide configuration
- ✅ Comprehensive error handling
- ✅ Type hints throughout
- ✅ Docstrings for all public methods

### Documentation
- ✅ User guide with examples and troubleshooting
- ✅ Developer spec with complete technical details
- ✅ Updated CLAUDE.md project documentation
- ✅ Code comments for complex sections
- ✅ ASCII diagrams for layout understanding

### Maintainability
- ✅ Modular component structure
- ✅ Clear separation of concerns
- ✅ Reusable message bubble creation
- ✅ Configurable via constants
- ✅ Easy to extend for new file types

## Files Modified

```
src/bmlibrarian/gui/tabs/
├── __init__.py                      [MODIFIED] - Added DocumentInterrogationTab import
└── document_interrogation_tab.py    [NEW]      - Main tab implementation (500+ lines)

src/bmlibrarian/gui/
└── config_app.py                    [MODIFIED] - Added tab to GUI

doc/users/
└── document_interrogation_guide.md  [NEW]      - User documentation (400+ lines)

doc/developers/
└── document_interrogation_ui_spec.md [NEW]     - Technical specification (600+ lines)

./
├── CLAUDE.md                        [MODIFIED] - Updated project documentation
├── test_document_interrogation_gui.py [NEW]    - Test harness
└── DOCUMENT_INTERROGATION_IMPLEMENTATION.md [NEW] - This file
```

## Next Steps

### Immediate (for completion)
1. **Test visual appearance**: Run GUI and verify layout
2. **Test file loading**: Try loading .md, .txt, .pdf files
3. **Test model selection**: Verify Ollama integration
4. **Test chat input**: Ensure messages display correctly

### Short-term (next session)
1. **Implement LLM integration**: Connect chat to Ollama
2. **Add PDF rendering**: Use PyMuPDF for actual page display
3. **Add chat export**: Save conversation as markdown
4. **Add clear chat button**: UI control for clearing history

### Long-term (future enhancements)
1. **Draggable splitter**: Custom pane sizing
2. **Citation highlighting**: Click-to-highlight in document
3. **Multi-document support**: Tabs or side-by-side view
4. **Advanced analysis**: Auto-summarization, key terms

## Credits

- **Framework**: Flet (Python GUI framework)
- **Design Pattern**: Follows BMLibrarian GUI conventions
- **Color Scheme**: Material Design-inspired with blues and greys
- **Layout Inspiration**: Modern document viewers and chat interfaces

## Version

- **Initial Implementation**: 2025-01-XX
- **Status**: UI complete, LLM integration pending
- **Python**: >=3.12
- **Flet**: >=0.24.1

---

**Ready for testing!** Launch the GUI and navigate to the "Document Interrogation" tab (chat icon) to see the new interface.
