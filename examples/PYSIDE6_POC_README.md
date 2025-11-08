# PySide6 Migration Proof-of-Concept for BMLibrarian

This directory contains proof-of-concept demonstrations showing how to migrate BMLibrarian's Flet-based GUIs to PySide6 (Qt for Python).

## Files in This POC

1. **pyside6_poc_research_gui.py** - Full research GUI demonstration (~700 lines)
   - Complete working application showing main window with tabs
   - Custom StepCard widget (collapsible progress cards)
   - Threading with signals/slots for workflow execution
   - Markdown report rendering
   - File save dialogs
   - Progress bars and status updates

2. **pyside6_stepcard_demo.py** - Simplified StepCard widget demo (~150 lines)
   - Focused example showing just the StepCard widget
   - Interactive buttons to simulate different states
   - Good starting point to understand the pattern

3. **pyside6_requirements.txt** - Dependencies needed to run the POC

## Installation

```bash
# Option 1: Using pip
pip install -r examples/pyside6_requirements.txt

# Option 2: Using uv (recommended for bmlibrarian)
uv pip install -r examples/pyside6_requirements.txt
```

## Running the Demos

### Simple StepCard Demo (Start Here!)

```bash
python examples/pyside6_stepcard_demo.py
```

This shows:
- Collapsible step cards with status tracking
- Click headers to expand/collapse
- Interactive buttons to change states (running, completed, error)
- Progress bar updates

### Full Research GUI Demo

```bash
python examples/pyside6_poc_research_gui.py
```

This demonstrates:
- Complete research workflow simulation
- Threaded execution keeping GUI responsive
- Real-time progress updates via signals/slots
- Tab-based interface (Workflow, Documents, Report)
- Markdown report rendering
- File save functionality

**What happens when you click "Start Research":**
1. Creates a worker thread for the workflow
2. Simulates each step (query generation, search, scoring, etc.)
3. Updates step cards in real-time via signals
4. Shows progress bars during long operations
5. Generates a mock markdown report
6. Allows saving the report to a file

## Key Patterns Demonstrated

### 1. Custom Widgets (StepCard)

**Flet Pattern (your current code):**
```python
class StepCard:
    def build(self) -> ft.ExpansionTile:
        self.expansion_tile = ft.ExpansionTile(
            title=ft.Row([...]),
            controls=[...]
        )
        return self.expansion_tile
```

**PySide6 Pattern (new):**
```python
class StepCard(QWidget):
    # Custom signals for communication
    expand_changed = Signal(bool)

    def __init__(self, step, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        # Build widget tree with layouts
        layout = QVBoxLayout(self)
        layout.addWidget(self.header_frame)
        layout.addWidget(self.content_widget)
```

**Key differences:**
- PySide6 widgets inherit from QWidget
- Use layouts (QVBoxLayout, QHBoxLayout) instead of Flet's Container/Column/Row
- Custom signals for events (like Flet's callbacks but more powerful)

### 2. Threading with Signals/Slots

**Why this is better than Flet:**
- Clean separation of worker logic from UI
- Type-safe signal/slot connections
- Automatic thread-safe GUI updates
- Built-in lifecycle management

**Pattern:**
```python
# Worker thread
class WorkflowWorker(QThread):
    # Define signals
    step_started = Signal(WorkflowStep)
    step_completed = Signal(WorkflowStep, str)

    def run(self):
        # Work happens here (in separate thread)
        self.step_started.emit(current_step)
        # ... do work ...
        self.step_completed.emit(current_step, result)

# Main GUI
class ResearchGUI(QMainWindow):
    def start_workflow(self):
        self.worker = WorkflowWorker()

        # Connect signals to slots (handlers)
        self.worker.step_started.connect(self.on_step_started)
        self.worker.step_completed.connect(self.on_step_completed)

        # Start worker thread
        self.worker.start()

    def on_step_completed(self, step, result):
        # This runs in main thread - safe to update GUI
        self.step_cards[step].update_status(COMPLETED, result)
```

### 3. Layouts vs Containers

**Flet approach:**
```python
ft.Column([
    widget1,
    widget2
], spacing=10)
```

**PySide6 approach:**
```python
layout = QVBoxLayout()
layout.setSpacing(10)
layout.addWidget(widget1)
layout.addWidget(widget2)
```

**Layout types:**
- `QVBoxLayout` - Vertical stacking (like Flet Column)
- `QHBoxLayout` - Horizontal arrangement (like Flet Row)
- `QGridLayout` - Grid-based positioning
- `QFormLayout` - Form-style label/field pairs

### 4. Tabs

**Flet:**
```python
ft.Tabs(
    tabs=[
        ft.Tab(text="Tab 1", content=widget1),
        ft.Tab(text="Tab 2", content=widget2)
    ]
)
```

**PySide6:**
```python
tabs = QTabWidget()
tabs.addTab(widget1, "Tab 1")
tabs.addTab(widget2, "Tab 2")
```

### 5. Markdown Rendering

**Basic approach (used in POC):**
```python
text_edit = QTextEdit()
text_edit.setMarkdown(markdown_text)
```

**For better rendering**, you can:
- Use QTextDocument with custom markdown parser
- Integrate QtWebEngine for full HTML rendering
- Use third-party markdown widgets

### 6. File Dialogs

**Flet has issues (as you mentioned with macOS FilePicker).**

**PySide6 (rock solid):**
```python
file_path, _ = QFileDialog.getSaveFileName(
    self,
    "Save Report",
    "report.md",
    "Markdown Files (*.md);;All Files (*)"
)
if file_path:
    # Save file
```

Native dialogs work perfectly on all platforms.

### 7. Progress Bars

**Flet:**
```python
ft.ProgressBar(value=0.5)  # 0.0 to 1.0
```

**PySide6:**
```python
progress = QProgressBar()
progress.setMaximum(100)
progress.setValue(50)
progress.setFormat("%p% (%v/%m)")  # Shows "50% (50/100)"
```

More control and built-in text formatting.

## Migration Strategy for BMLibrarian

### Phase 1: Infrastructure
1. Add PySide6 to dependencies in `pyproject.toml`
2. Create `src/bmlibrarian/gui_qt/` directory for Qt-based GUIs
3. Keep existing Flet GUIs during transition

### Phase 2: Component Migration
Start with reusable components:

1. **StepCard widget** → Use POC as template
   - `src/bmlibrarian/gui_qt/widgets/step_card.py`

2. **Workflow executor** → Adapt threading pattern
   - `src/bmlibrarian/gui_qt/workflow_thread.py`

3. **Dialog manager** → Replace Flet dialogs
   - `src/bmlibrarian/gui_qt/dialogs.py`

### Phase 3: Main Windows
Migrate main applications:

1. **Research GUI**
   - Use POC structure as starting point
   - Integrate real agents (not simulated)
   - Add document display widgets (QTableView for efficiency)
   - Implement citation review interface

2. **Config GUI**
   - Tab-based like Flet version
   - Use QSettings for platform-native config storage
   - Model selection dropdowns (QComboBox)
   - Parameter sliders (QSlider)

### Phase 4: Enhanced Features
Add improvements beyond Flet:

1. **Better document display**
   - QTableView with custom model for thousands of documents
   - Virtual scrolling for performance
   - Sort/filter capabilities

2. **Rich text editing**
   - QTextEdit for query editing with syntax highlighting
   - Real-time validation

3. **Better progress tracking**
   - QProgressDialog for long operations
   - Detailed progress with sub-steps

4. **Settings management**
   - QSettings for cross-platform settings storage
   - No need for manual JSON file handling

## Code Size Comparison

**Flet StepCard** (from your `components.py`): ~577 lines
**PySide6 StepCard** (in POC): ~150 lines for core functionality

**Why smaller?**
- Layouts more concise than nested Containers
- Built-in widgets handle more functionality
- Less boilerplate for state management

## Performance Benefits

1. **Native rendering** - Qt uses native widgets (faster than Flet's web-based rendering)
2. **Efficient updates** - Only changed widgets repaint
3. **Better threading** - Qt's event loop handles concurrency elegantly
4. **Large datasets** - Model/View architecture scales to millions of rows

## Testing the Real Integration

To test with real BMLibrarian agents:

1. Copy the worker thread pattern from POC
2. Replace simulated steps with real agent calls:

```python
class WorkflowWorker(QThread):
    def run(self):
        # Real implementation
        from bmlibrarian.agents import QueryAgent

        self.step_started.emit(WorkflowStep.GENERATE_AND_EDIT_QUERY)
        query_agent = QueryAgent()
        query = query_agent.generate_query(self.research_question)
        self.step_completed.emit(WorkflowStep.GENERATE_AND_EDIT_QUERY, query)

        # ... etc
```

## Architecture Advantages

### 1. Signal/Slot Type Safety
```python
# Compile-time type checking
step_completed = Signal(WorkflowStep, str)

# Error if you emit wrong types
self.step_completed.emit("wrong", 123)  # Type checker catches this
```

### 2. Automatic Cleanup
- Qt's parent/child ownership prevents memory leaks
- Deleting parent automatically deletes children
- Thread cleanup handled properly

### 3. Designer Support
- Qt Designer for visual layout (optional)
- Can generate `.ui` files or use pure Python
- Good for complex layouts

### 4. Extensive Ecosystem
- Qt Charts for data visualization
- Qt WebEngine for embedded browser (if needed)
- Qt Network for advanced HTTP
- Vast collection of third-party Qt widgets

## Common Patterns Cheat Sheet

| Task | Flet | PySide6 |
|------|------|---------|
| Vertical stack | `ft.Column([w1, w2])` | `layout = QVBoxLayout(); layout.addWidget(w1)` |
| Horizontal row | `ft.Row([w1, w2])` | `layout = QHBoxLayout(); layout.addWidget(w1)` |
| Button click | `ft.Button("Click", on_click=handler)` | `btn = QPushButton("Click"); btn.clicked.connect(handler)` |
| Text input | `ft.TextField(value="text")` | `edit = QLineEdit("text")` |
| Checkbox | `ft.Checkbox(value=True)` | `cb = QCheckBox(); cb.setChecked(True)` |
| Update widget | `widget.value = "new"; widget.update()` | `widget.setValue("new")` # Auto-updates |
| Progress bar | `ft.ProgressBar(value=0.5)` | `pb = QProgressBar(); pb.setValue(50)` |
| Tabs | `ft.Tabs(tabs=[...])` | `tabs = QTabWidget(); tabs.addTab(w, "Tab")` |
| Scroll area | Automatic in Flet | `scroll = QScrollArea(); scroll.setWidget(content)` |
| File dialog | `ft.FilePicker().save_file()` | `QFileDialog.getSaveFileName()` |

## Next Steps

1. **Try the POC demos** - Run both examples to see the patterns in action
2. **Experiment with modifications** - Add new step types, change colors, etc.
3. **Review the code comments** - Detailed explanations throughout
4. **Ask questions** - I can provide more examples for specific patterns
5. **Start migration** - Begin with one component (e.g., StepCard)

## Questions to Consider

Before starting full migration:

1. **Which GUI to migrate first?** Research or Config?
2. **Keep Flet versions during transition?** Yes recommended
3. **Use Qt Designer or pure Python?** Pure Python recommended for maintainability
4. **Any specific Flet features you want to preserve?** (web mode, etc.)

## Resources

- **PySide6 Documentation**: https://doc.qt.io/qtforpython-6/
- **Qt Widget Gallery**: https://doc.qt.io/qt-6/gallery.html
- **Qt Examples**: https://doc.qt.io/qtforpython-6/examples/index.html

## My Assistance

I can help with:
- ✅ Complete component migrations (just ask for specific widgets)
- ✅ Threading patterns for your specific agents
- ✅ Custom widget development
- ✅ Layout troubleshooting
- ✅ Signal/slot architecture questions
- ✅ Integration with your existing BMLibrarian agents
- ✅ Performance optimization
- ✅ Styling and themes

Just let me know what you'd like to tackle first!
