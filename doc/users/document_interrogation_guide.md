# Document Interrogation Guide

## Overview

The Document Interrogation tab provides an interactive interface for analyzing and asking questions about documents (PDF, Markdown, or text files) using AI language models from Ollama.

## Features

### Split-Pane Layout

The interface is divided into two main areas:

1. **Document Viewer (Left Pane - 60% width)**
   - Displays the loaded document
   - Supports PDF, Markdown (.md), and text (.txt) files
   - Markdown files are rendered with GitHub-style formatting
   - Text files displayed with syntax highlighting
   - PDF preview (rendering to be implemented)

2. **Chat Interface (Right Pane - 40% width)**
   - Dialogue-style chat interface
   - User messages appear in blue bubbles (right-aligned)
   - AI responses appear in grey bubbles (left-aligned)
   - Auto-scrolls to latest messages
   - Full conversation history visible

### Top Bar Controls

**File Selector Button**
- Click "Load Document" to open file picker
- Supports: `.pdf`, `.md`, `.txt` files
- Currently loaded document name displayed next to button

**Model Selector Dropdown**
- Select from available Ollama models
- Automatically populated from your Ollama server
- Refresh button to update model list
- Uses configuration from General Settings tab

## Usage Instructions

### Basic Workflow

1. **Launch the GUI**
   ```bash
   uv run python bmlibrarian_config_gui.py
   ```

2. **Navigate to Document Interrogation Tab**
   - Click the "Document Interrogation" tab (chat icon)

3. **Configure LLM Model**
   - Select a model from the dropdown
   - Use the refresh button if models don't appear
   - Ensure Ollama server is running (default: http://localhost:11434)

4. **Load a Document**
   - Click "Load Document" button
   - Select a PDF, Markdown, or text file
   - Document will appear in the left pane

5. **Ask Questions**
   - Type your question in the message input field
   - Press Enter or click Send button
   - AI responses will appear in the chat area

### Chat Interface Details

**Message Input**
- Supports multi-line input (up to 3 lines visible)
- Press **Enter** to send message
- Press **Shift+Enter** for new line
- Input validated before sending (requires loaded document and selected model)

**Message Bubbles**
- **User messages**: Blue background, right-aligned, labeled "You"
- **AI responses**: Grey background, left-aligned, labeled "AI Assistant"
- All messages are selectable for copying
- Maximum bubble width: 500px for readability

**System Messages**
- Welcome message when tab first opened
- Confirmation when document loaded
- Notification when model changed

## Programmatic Integration

The Document Interrogation tab can be integrated with other plugins:

```python
# Access the tab from the config app
doc_tab = app.tab_objects['document_interrogation']

# Load document programmatically
doc_tab.load_document_programmatically('/path/to/document.pdf')

# Clear chat history
doc_tab.clear_chat()
```

## UI Layout Specification

### Overall Structure
```
┌─────────────────────────────────────────────────────────────────┐
│ Top Bar (60px height, grey background)                         │
│  [Load Document] 📄 filename.pdf  [Model ▼] [🔄]              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌────────────────────┬────────────────────────────────────┐  │
│  │ Document Viewer    │ Chat                               │  │
│  │ (60% width)        │ (40% width)                        │  │
│  ├────────────────────┼────────────────────────────────────┤  │
│  │                    │ ┌──────────────────────────────┐   │  │
│  │                    │ │ Chat Messages (scrollable)   │   │  │
│  │   Document         │ │                              │   │  │
│  │   Content          │ │  ┌─────────────────┐        │   │  │
│  │   Display          │ │  │ AI: Welcome...  │        │   │  │
│  │   Area             │ │  └─────────────────┘        │   │  │
│  │                    │ │                              │   │  │
│  │   (Scrollable)     │ │        ┌──────────────────┐ │   │  │
│  │                    │ │        │ You: Question... │ │   │  │
│  │                    │ │        └──────────────────┘ │   │  │
│  │                    │ └──────────────────────────────┘   │  │
│  │                    ├────────────────────────────────────┤  │
│  │                    │ [Type message here...] [📤 Send]   │  │
│  └────────────────────┴────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Color Scheme

**Top Bar**
- Background: Grey 100 (#F5F5F5)
- Button: Blue 600 with white text
- Text: Black 87%

**Document Viewer**
- Background: White
- Border: Grey 400 on right side (separator)
- Header: Grey 200 background

**Chat Interface**
- Background: Grey 50
- Border: Grey 300
- User message bubbles: Blue 600 background, white text
- AI message bubbles: Grey 200 background, black 87% text
- Input area: White background with Blue 400 border

### Spacing and Dimensions

- Top bar height: 60px
- Top bar padding: 10px all sides
- Split pane ratio: 3:2 (60%:40%)
- Message bubble padding: 12px all sides
- Message bubble border radius: 12px (with one corner squared based on sender)
- Message bubble max width: 500px
- Message bubble spacing: 5px bottom margin
- Chat input height: Auto (1-3 lines)

## Keyboard Shortcuts

- **Enter**: Send message
- **Shift+Enter**: New line in message input
- **Ctrl+L**: Load document (when button focused)

## Future Enhancements

### Planned Features

1. **PDF Rendering**
   - Full PDF page rendering using PyMuPDF or pdf2image
   - Page navigation controls
   - Zoom in/out functionality
   - Text selection and highlighting

2. **LLM Integration**
   - Complete implementation of LLM processing
   - Document context passing to LLM
   - Streaming responses
   - Citation extraction (highlight relevant passages)

3. **Enhanced Document Support**
   - DOCX file support
   - HTML rendering
   - Code syntax highlighting for source files
   - Image file display

4. **Chat Features**
   - Export chat history
   - Clear chat button
   - Search within conversation
   - Copy message buttons
   - Message timestamps

5. **Layout Improvements**
   - Draggable splitter between panes
   - Collapsible document viewer
   - Full-screen mode for document
   - Resizable chat input

6. **Document Analysis**
   - Automatic document summarization
   - Table of contents extraction
   - Key terms identification
   - Reference extraction

## Technical Details

### Component Architecture

**File**: `src/bmlibrarian/gui/tabs/document_interrogation_tab.py`

**Main Class**: `DocumentInterrogationTab`

**Key Methods**:
- `build()`: Constructs the UI layout
- `_build_top_bar()`: Creates file selector and model dropdown
- `_build_split_pane()`: Creates two-pane layout
- `_build_document_viewer_pane()`: Left pane for documents
- `_build_chat_interface_pane()`: Right pane for chat
- `_load_document()`: Loads and displays documents
- `_create_message_bubble()`: Creates styled chat bubbles
- `load_document_programmatically()`: API for external integration

### Dependencies

- **Flet**: UI framework
- **Ollama**: LLM model provider
- **Python pathlib**: File path handling
- **Future**: PyMuPDF for PDF rendering

### Configuration

Uses configuration from `~/.bmlibrarian/config.json`:
- `ollama.host`: Ollama server URL
- `ollama.timeout`: Request timeout
- `ollama.max_retries`: Connection retry attempts

## Troubleshooting

### Models Not Appearing

**Problem**: Model dropdown is empty

**Solutions**:
1. Ensure Ollama server is running: `ollama serve`
2. Check Ollama host in General Settings tab
3. Click the refresh button (🔄) next to model dropdown
4. Verify network connectivity to Ollama server

### Document Won't Load

**Problem**: Error when loading document

**Solutions**:
1. Check file permissions
2. Verify file format is supported (.pdf, .md, .txt)
3. Ensure file is not corrupted
4. Check file size (very large files may timeout)

### Chat Messages Not Sending

**Problem**: Send button doesn't work

**Solutions**:
1. Ensure document is loaded
2. Verify model is selected
3. Check message input is not empty
4. Confirm Ollama server is running

### PDF Not Displaying

**Status**: PDF rendering is currently a placeholder

**Workaround**: For now, PDF content is loaded for LLM processing but not visually rendered. Use text or markdown files for full preview functionality until PDF rendering is implemented.

## Examples

### Example Workflow 1: Research Paper Analysis

```
1. Load Document: research_paper.pdf
2. Select Model: gpt-oss:20b
3. Ask: "What are the main findings of this study?"
4. Ask: "What methods did the authors use?"
5. Ask: "Are there any limitations mentioned?"
```

### Example Workflow 2: Code Documentation Review

```
1. Load Document: README.md
2. Select Model: medgemma4B_it_q8:latest
3. Ask: "Summarize the installation instructions"
4. Ask: "What are the main features?"
5. Ask: "Are there any API examples?"
```

### Example Workflow 3: Contract Review

```
1. Load Document: contract.txt
2. Select Model: gpt-oss:20b
3. Ask: "What are the key obligations?"
4. Ask: "Are there any termination clauses?"
5. Ask: "What are the payment terms?"
```

## Comparison with Other Tools

### vs. BMLibrarian Research GUI

- **Research GUI**: Multi-agent workflow for literature search
- **Document Interrogation**: Single document Q&A interface
- **Use case**: Different focus - broad research vs. deep document analysis

### vs. Command Line Tools

- **CLI**: Programmatic access, scripting
- **Document Interrogation**: Visual, interactive, user-friendly
- **Use case**: GUI for human interaction, CLI for automation

## API Reference

### DocumentInterrogationTab Class

```python
class DocumentInterrogationTab:
    """Document interrogation tab with split-pane viewer and chat."""

    def __init__(self, app: BMLibrarianConfigApp):
        """Initialize the tab with reference to main app."""

    def build(self) -> ft.Container:
        """Build and return the tab UI layout."""

    def load_document_programmatically(self, file_path: str):
        """
        Load a document programmatically.

        Args:
            file_path: Absolute path to document
        """

    def clear_chat(self):
        """Clear the chat history and reset to welcome message."""
```

### ChatMessage Class

```python
class ChatMessage:
    """Represents a single chat message."""

    def __init__(self, text: str, is_user: bool):
        """
        Create a chat message.

        Args:
            text: Message content
            is_user: True if user message, False if AI response
        """
```

## Best Practices

1. **Document Selection**: Choose the right file format
   - Use Markdown for best rendering quality
   - Text files for simple content
   - PDFs when necessary (rendering pending)

2. **Model Selection**: Match model to task
   - `gpt-oss:20b`: Complex analysis, research papers
   - `medgemma4B_it_q8:latest`: Fast responses, simple questions
   - Larger models: Better accuracy, slower responses

3. **Question Formulation**: Ask clear, specific questions
   - ✅ "What are the three main conclusions?"
   - ❌ "Tell me about this"
   - ✅ "What methods are used in section 3?"
   - ❌ "Summarize everything"

4. **Chat Management**: Keep conversations focused
   - Clear chat when switching topics
   - Load new document for different analysis
   - Export important conversations (future feature)

## Contributing

To enhance the Document Interrogation tab:

1. **PDF Rendering**: Implement using PyMuPDF or pdf2image
2. **LLM Processing**: Add actual Ollama integration
3. **UI Enhancements**: Draggable splitter, better styling
4. **Additional Formats**: DOCX, HTML, images

See `CLAUDE.md` for development guidelines.
