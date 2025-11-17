# Document Interrogation UI Specification

## Component Hierarchy

```
DocumentInterrogationTab
├── TopBar (Container)
│   ├── FileSelectButton (ElevatedButton)
│   ├── CurrentDocLabel (Text)
│   ├── ModelDropdown (Dropdown)
│   └── RefreshModelsButton (IconButton)
├── Divider
└── SplitPane (Container)
    ├── LeftPane (60% - Document Viewer)
    │   ├── Header (Container)
    │   │   └── Title (Text: "Document Viewer")
    │   └── DocumentViewer (Container)
    │       └── Content (Markdown | Text | Placeholder)
    └── RightPane (40% - Chat Interface)
        ├── Header (Container)
        │   └── Title (Text: "Chat")
        ├── ChatContainer (Container - scrollable)
        │   └── ChatMessagesColumn (Column)
        │       ├── WelcomeMessage (MessageBubble)
        │       ├── UserMessage (MessageBubble)
        │       ├── AIMessage (MessageBubble)
        │       └── ... (more messages)
        └── InputArea (Container)
            ├── MessageInput (TextField)
            └── SendButton (IconButton)
```

## Visual Design Specifications

### Top Bar (60px fixed height)

```python
Container(
    bgcolor=ft.Colors.GREY_100,
    height=60,
    padding=ft.padding.all(10)
)
```

**Components**:

1. **File Selector Button**
   - Type: `ft.ElevatedButton`
   - Text: "Load Document"
   - Icon: `ft.Icons.FOLDER_OPEN`
   - Height: 40px
   - Style: Blue 600 background, white text

2. **Current Document Label**
   - Type: `ft.Text`
   - Default: "No document loaded" (italic, grey)
   - Active: "📄 filename.pdf" (normal, black)
   - Size: 12
   - Expands to fill available space

3. **Model Dropdown**
   - Type: `ft.Dropdown`
   - Label: "LLM Model"
   - Width: 300px
   - Populated from Ollama server

4. **Refresh Button**
   - Type: `ft.IconButton`
   - Icon: `ft.Icons.REFRESH`
   - Color: Blue 600
   - Tooltip: "Refresh model list"

### Document Viewer Pane (Left - 60% width)

```python
Container(
    expand=3,  # 60% of Row
    border=ft.border.only(right=ft.BorderSide(1, ft.Colors.GREY_400))
)
```

**Header Bar**:
- Background: Grey 200
- Padding: 10px
- Text: "Document Viewer" (14px, bold)

**Content Area**:
- Background: White
- Padding: 20px for placeholder, 10px for content
- Scrollable: Auto

**Placeholder State** (no document loaded):
```
┌────────────────────────────┐
│                            │
│      [📄 Icon 100px]       │
│                            │
│   "No document loaded"     │
│     (16px, grey 500)       │
│                            │
│  "Click 'Load Document'    │
│   to open a PDF or         │
│   Markdown file"           │
│     (12px, grey 400)       │
│                            │
└────────────────────────────┘
```

**Active State** (document loaded):
- Markdown: Rendered with GitHub-style formatting
- Text: Monospace font, selectable
- PDF: Placeholder with icon and filename

### Chat Interface Pane (Right - 40% width)

```python
Container(
    expand=2,  # 40% of Row
)
```

**Header Bar**:
- Background: Grey 200
- Padding: 10px
- Text: "Chat" (14px, bold)

**Chat Container**:
- Background: Grey 50
- Padding: 10px
- Border: 1px solid Grey 300
- Scrollable: Auto
- Expands to fill vertical space

**Input Area**:
- Background: White
- Padding: 10px
- Border top: 1px solid Grey 300
- Fixed height (based on TextField)

### Message Bubbles

**User Message Bubble** (right-aligned):

```python
Container(
    content=Column([
        Text("You", size=10, weight=BOLD, color=BLUE_900),
        Text(message_text, size=13, color=WHITE, selectable=True)
    ]),
    bgcolor=ft.Colors.BLUE_600,
    padding=ft.padding.all(12),
    border_radius=ft.border_radius.only(12, 12, 0, 12),
    max_width=500,
    margin=ft.margin.only(bottom=5)
)
```

**Visual appearance**:
```
                     ┌─────────────────────┐
                     │ You                 │
                     │ What are the main   │
                     │ findings?           │
                     └─────────────────────┘
```

**AI Message Bubble** (left-aligned):

```python
Container(
    content=Column([
        Text("AI Assistant", size=10, weight=BOLD, color=GREY_800),
        Text(message_text, size=13, color=BLACK87, selectable=True)
    ]),
    bgcolor=ft.Colors.GREY_200,
    padding=ft.padding.all(12),
    border_radius=ft.border_radius.only(12, 12, 12, 0),
    max_width=500,
    margin=ft.margin.only(bottom=5)
)
```

**Visual appearance**:
```
┌─────────────────────┐
│ AI Assistant        │
│ The study found...  │
│ ...                 │
└─────────────────────┘
```

### Message Input Area

```python
Row([
    TextField(
        hint_text="Ask a question about the document...",
        multiline=True,
        min_lines=1,
        max_lines=3,
        expand=True,
        border_color=ft.Colors.BLUE_400
    ),
    IconButton(
        icon=ft.Icons.SEND,
        bgcolor=ft.Colors.BLUE_600,
        icon_color=ft.Colors.WHITE
    )
])
```

## Color Palette

### Primary Colors
- Blue 600: `#1E88E5` - Primary actions, user messages
- Blue 400: `#42A5F5` - Input borders, accents
- Blue 900: `#0D47A1` - User label text
- Blue 700: `#1976D2` - Alternative primary

### Neutral Colors
- Grey 50: `#FAFAFA` - Chat background
- Grey 100: `#F5F5F5` - Top bar background
- Grey 200: `#EEEEEE` - AI message bubbles, headers
- Grey 300: `#E0E0E0` - Borders
- Grey 400: `#BDBDBD` - Dividers, placeholder icons
- Grey 500: `#9E9E9E` - Placeholder text
- Grey 600: `#757575` - Secondary text
- Grey 700: `#616161` - Helper text
- Grey 800: `#424242` - AI label text

### Semantic Colors
- White: `#FFFFFF` - Backgrounds, user message text
- Black 87%: `rgba(0,0,0,0.87)` - Primary text
- Red 400: `#EF5350` - PDF icon color

## Spacing System

### Padding
- Large: 20px (main containers)
- Medium: 15px (section containers)
- Standard: 10px (most elements)
- Small: 5px (tight spacing)

### Margins
- Message bubbles: 5px bottom
- Sections: 20px bottom
- Headers: 10px bottom

### Gaps/Spacing
- Top bar elements: 15px
- Message bubbles: 10px vertical
- Column spacing: Generally 10px

## Typography

### Font Sizes
- Large title: 24px (page title)
- Section title: 18px (not used in tab)
- Subsection: 16px (placeholder primary text)
- Standard: 14px (headers)
- Body: 13px (message content)
- Small: 12px (labels, hints)
- Tiny: 10px (message sender labels)

### Font Weights
- Bold: Headers, labels
- Normal: Body text, messages

### Text Colors
- Primary: Black 87%
- Secondary: Grey 600
- Disabled: Grey 400
- User message: White
- AI message: Black 87%

## Layout Breakpoints

### Main Split Ratio
- Desktop (default): 60% (document) / 40% (chat)
- Future: Draggable splitter for custom ratios

### Minimum Widths
- Total window: 800px
- Document pane: 480px (60% of 800px)
- Chat pane: 320px (40% of 800px)

### Heights
- Top bar: 60px (fixed)
- Main content: Expand to fill (window height - top bar - divider)

## Interaction States

### Buttons

**Normal State**:
- Background: Blue 600
- Text: White
- Border: None

**Hover State**:
- Background: Blue 700 (darker)
- Cursor: Pointer

**Pressed State**:
- Background: Blue 800
- Transform: Scale 0.98

**Disabled State**:
- Background: Grey 300
- Text: Grey 500
- Cursor: Not-allowed

### Text Fields

**Normal State**:
- Border: Blue 400
- Background: White

**Focused State**:
- Border: Blue 600 (thicker)
- Background: White

**Error State**:
- Border: Red 400
- Helper text: Red color

### Dropdowns

**Normal State**:
- Border: Grey 400
- Background: White

**Opened State**:
- Border: Blue 600
- Dropdown panel visible

**Empty State**:
- Hint text: Grey 500
- Background: White

## Animations

### Message Appearance
- Duration: 200ms
- Easing: Ease-out
- Effect: Fade in + slide up

### Chat Scroll
- Duration: 300ms
- Easing: Smooth
- Trigger: New message added

### Tab Change
- Duration: 300ms
- Easing: Ease-in-out
- Effect: Fade

## Accessibility

### Keyboard Navigation
- Tab: Focus next element
- Shift+Tab: Focus previous element
- Enter: Send message / activate button
- Shift+Enter: New line in message input
- Esc: Close file picker / dropdown

### Screen Readers
- All buttons have tooltips
- Message bubbles have sender labels
- Input fields have hint text
- Document status announced

### Text Selection
- All message text is selectable
- Document content is selectable
- Copy functionality available

## Responsive Behavior

### Window Resize
- Top bar: Fixed height, stretches width
- Split panes: Maintain 60/40 ratio, adjust widths
- Message bubbles: Respect max-width, wrap text
- Chat container: Scrolls when content overflows

### Content Overflow
- Document viewer: Vertical scroll
- Chat container: Vertical scroll, auto-scroll to bottom
- Message input: Grows to max 3 lines, then scrolls
- Message bubbles: Text wraps, max-width 500px

## File Type Handling

### Markdown (.md)
```python
ft.Markdown(
    content,
    selectable=True,
    extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
    on_tap_link=lambda e: page.launch_url(e.data)
)
```
- Renders with GitHub styling
- Links are clickable
- Code blocks syntax highlighted

### Text (.txt)
```python
ft.Container(
    content=ft.Text(
        content,
        size=12,
        selectable=True,
        color=ft.Colors.BLACK87
    ),
    padding=ft.padding.all(10)
)
```
- Plain text rendering
- Monospace font ideal (future)
- Selectable content

### PDF (.pdf)
```python
# Placeholder until rendering implemented
ft.Column([
    ft.Icon(ft.Icons.PICTURE_AS_PDF, size=80, color=ft.Colors.RED_400),
    ft.Text(filename, size=16, weight=ft.FontWeight.BOLD),
    ft.Text("PDF Preview", size=14, color=ft.Colors.GREY_600),
    ft.Text("Rendering to be implemented", size=12, italic=True)
])
```
- Future: PyMuPDF rendering
- Future: Page navigation
- Future: Zoom controls

## State Management

### Component State
```python
class DocumentInterrogationTab:
    # Document state
    current_document_path: Optional[str] = None
    current_document_content: Optional[str] = None

    # Model state
    selected_model: Optional[str] = None

    # Chat state
    chat_history: List[ChatMessage] = []

    # UI references
    file_selector_button: ft.ElevatedButton
    model_dropdown: ft.Dropdown
    document_viewer: ft.Container
    chat_container: ft.Container
    chat_messages_column: ft.Column
    message_input: ft.TextField
    send_button: ft.IconButton
```

### State Transitions

1. **Initial State** → **Document Loaded**
   - Trigger: File selected
   - Update: `current_document_path`, `current_document_content`
   - UI: Update document viewer, show filename

2. **Any State** → **Model Selected**
   - Trigger: Dropdown change
   - Update: `selected_model`
   - UI: Show confirmation message

3. **Ready State** → **Message Sent**
   - Trigger: Send button / Enter key
   - Update: Add to `chat_history`
   - UI: Display user bubble, clear input

4. **Message Sent** → **Response Received**
   - Trigger: LLM response (future)
   - Update: Add to `chat_history`
   - UI: Display AI bubble, auto-scroll

## Error Handling

### File Loading Errors
- **Unsupported format**: Snackbar "Unsupported file type: .xyz"
- **Read error**: Snackbar "Failed to read document: <error>"
- **Large file**: Snackbar "File too large: <size>"

### Model Errors
- **No models**: Empty dropdown with hint "No models available"
- **Connection failed**: Snackbar "Failed to fetch models: <error>"
- **No selection**: Snackbar "Please select an LLM model first"

### Chat Errors
- **No document**: Snackbar "Please load a document first"
- **Empty message**: No action (validation)
- **LLM error**: AI message bubble with error text

## Testing Checklist

### Visual Testing
- [ ] Top bar elements align correctly
- [ ] Split pane ratio is 60/40
- [ ] Message bubbles display correctly (user vs AI)
- [ ] Document content renders properly
- [ ] Colors match specification
- [ ] Spacing is consistent

### Functional Testing
- [ ] File picker opens and loads documents
- [ ] Model dropdown populates from Ollama
- [ ] Message sending works (Enter key)
- [ ] Chat scrolls to bottom on new message
- [ ] Multi-line input works (Shift+Enter)
- [ ] Error messages display as snackbars

### Integration Testing
- [ ] Tab switches without errors
- [ ] Configuration loads correctly
- [ ] Ollama connection works
- [ ] Programmatic document loading works
- [ ] Chat clear function works

### Accessibility Testing
- [ ] Keyboard navigation works
- [ ] All interactive elements focusable
- [ ] Tooltips present on icon buttons
- [ ] Text is selectable
- [ ] Contrast ratios meet WCAG guidelines

## Future Enhancements

### Layout Improvements
1. **Draggable Splitter**: Use custom widget or library
2. **Collapsible Panes**: Hide document viewer for full chat view
3. **Full-screen Mode**: Maximize document or chat pane
4. **Picture-in-Picture**: Float chat while working

### UI Polish
1. **Loading States**: Spinners during document load
2. **Skeleton Screens**: Placeholder content while loading
3. **Animations**: Smooth transitions for all state changes
4. **Dark Mode**: Complete dark theme support

### Advanced Features
1. **Split View**: Multiple documents side-by-side
2. **Tabs**: Multiple document tabs
3. **Annotations**: Highlight and comment on documents
4. **Export**: Save chat as markdown or PDF
