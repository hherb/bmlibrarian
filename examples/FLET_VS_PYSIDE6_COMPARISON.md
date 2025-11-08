# Flet vs PySide6: Side-by-Side Comparison

This document shows direct comparisons between your current Flet code and equivalent PySide6 patterns.

## 1. Basic Window Setup

### Flet
```python
import flet as ft

def main(page: ft.Page):
    page.title = "BMLibrarian Research Assistant"
    page.window.width = 1200
    page.window.height = 900
    page.theme_mode = ft.ThemeMode.LIGHT

    # Add widgets
    page.add(ft.Text("Hello"))

ft.app(target=main, view=ft.FLET_APP)
```

### PySide6
```python
from PySide6.QtWidgets import QApplication, QMainWindow, QLabel
import sys

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BMLibrarian Research Assistant")
        self.setGeometry(100, 100, 1200, 900)

        # Add widgets
        label = QLabel("Hello")
        self.setCentralWidget(label)

app = QApplication(sys.argv)
window = MainWindow()
window.show()
sys.exit(app.exec())
```

## 2. Your StepCard Widget - Complete Comparison

### Flet Version (Current)
```python
# From your components.py
class StepCard:
    def __init__(self, step: WorkflowStep, on_expand_change: Optional[Callable] = None):
        self.step = step
        self.expanded = False
        self.status = "pending"
        self.content = ""
        self.on_expand_change = on_expand_change

    def build(self) -> ft.ExpansionTile:
        self.status_icon = ft.Icon(
            name=get_status_icon(self.status),
            color=get_status_color(self.status),
            size=20
        )

        self.progress_bar = create_simple_progress_bar(visible=False)

        self.content_text = ft.Text(
            value=self.content or "Waiting to start...",
            size=12,
            color=ft.Colors.GREY_700,
            selectable=True
        )

        content_container = ft.Container(
            content=ft.Column([
                self.progress_bar,
                ft.Container(
                    content=self.content_text,
                    padding=ft.padding.all(10),
                    bgcolor=ft.Colors.GREY_50,
                    border_radius=5
                )
            ], spacing=5),
            padding=ft.padding.only(left=10, right=10, bottom=10)
        )

        self.expansion_tile = ft.ExpansionTile(
            title=ft.Row([
                self.status_icon,
                ft.Text(self.step.display_name, size=14, weight=ft.FontWeight.W_500),
            ], spacing=8),
            subtitle=ft.Text(self.step.description, size=12, color=ft.Colors.GREY_600),
            controls=[content_container]
        )

        return self.expansion_tile

    def update_status(self, status: str, content: Optional[str] = None):
        self.status = status
        if content is not None:
            self.content = content

        if self.status_icon:
            self.status_icon.name = get_status_icon(self.status)
            self.status_icon.color = get_status_color(self.status)

        if self.progress_bar:
            self.progress_bar.visible = (status == "running")

        if self.content_text:
            self.content_text.value = self.content or "Waiting to start..."
```

### PySide6 Version (New)
```python
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QProgressBar, QTextEdit
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QFont, QColor

class StepCard(QWidget):
    # Signal replaces callback function - more flexible and type-safe
    expand_changed = Signal(bool)

    def __init__(self, step: WorkflowStep, parent=None):
        super().__init__(parent)
        self.step = step
        self.expanded = False
        self.status = StepStatus.PENDING
        self.content_text = "Waiting to start..."

        self._init_ui()

    def _init_ui(self):
        # Main layout (like ft.Column)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(0)

        # Header frame (like ft.Container with ft.Row inside)
        self.header_frame = QFrame()
        self.header_frame.setStyleSheet("""
            QFrame {
                background-color: #f5f5f5;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        self.header_frame.setCursor(Qt.PointingHandCursor)
        self.header_frame.mousePressEvent = lambda e: self.toggle_expand()

        header_layout = QHBoxLayout(self.header_frame)

        # Status icon (like ft.Icon)
        self.status_label = QLabel(get_status_icon(self.status))
        self.status_label.setFont(QFont("Arial", 12))
        header_layout.addWidget(self.status_label)

        # Title and description (like ft.Column with ft.Text widgets)
        title_layout = QVBoxLayout()
        self.title_label = QLabel(self.step.display_name)
        self.title_label.setFont(QFont("Arial", 11, QFont.Bold))
        title_layout.addWidget(self.title_label)

        self.desc_label = QLabel(self.step.description)
        self.desc_label.setFont(QFont("Arial", 9))
        self.desc_label.setStyleSheet("color: #666;")
        title_layout.addWidget(self.desc_label)

        header_layout.addLayout(title_layout, 1)  # stretch factor

        main_layout.addWidget(self.header_frame)

        # Content widget (collapsible - like ft.ExpansionTile controls)
        self.content_widget = QWidget()
        self.content_widget.setVisible(False)

        content_layout = QVBoxLayout(self.content_widget)

        # Progress bar (like ft.ProgressBar)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        content_layout.addWidget(self.progress_bar)

        # Content text (like ft.Text in ft.Container)
        self.content_display = QTextEdit()
        self.content_display.setReadOnly(True)
        self.content_display.setMaximumHeight(150)
        self.content_display.setStyleSheet("""
            QTextEdit {
                background-color: #fafafa;
                border: 1px solid #ddd;
                border-radius: 3px;
                padding: 8px;
            }
        """)
        self.content_display.setPlainText(self.content_text)
        content_layout.addWidget(self.content_display)

        main_layout.addWidget(self.content_widget)

    def toggle_expand(self):
        """Toggle expanded/collapsed state."""
        self.expanded = not self.expanded
        self.content_widget.setVisible(self.expanded)
        self.expand_changed.emit(self.expanded)  # Emit signal instead of callback

    def update_status(self, status: StepStatus, content: Optional[str] = None):
        """Update step status - same interface as Flet version."""
        self.status = status

        # Update icon (automatic repaint, no .update() needed)
        self.status_label.setText(get_status_icon(status))
        color = get_status_color(status)
        self.status_label.setStyleSheet(
            f"color: rgb({color.red()}, {color.green()}, {color.blue()});"
        )

        # Update content
        if content is not None:
            self.content_text = content
            self.content_display.setPlainText(content)

        # Show/hide progress bar
        self.progress_bar.setVisible(status == StepStatus.RUNNING)

        # Auto-expand on running/error (same as Flet version could do)
        if status in (StepStatus.RUNNING, StepStatus.ERROR):
            if not self.expanded:
                self.toggle_expand()
```

**Key differences:**
- ✅ PySide6 uses QWidget inheritance (more OOP)
- ✅ Layouts (QVBoxLayout/QHBoxLayout) vs Containers
- ✅ Signals instead of callbacks (more flexible - multiple listeners)
- ✅ No need to call `.update()` - Qt handles repainting automatically
- ✅ Styling via QSS (like CSS) instead of individual properties
- ✅ Parent/child ownership prevents memory leaks

## 3. Threading for Long Operations

### Flet Version (Current)
```python
# From your workflow.py or research_app.py
import threading

def execute_workflow(self):
    """Execute workflow in background thread."""

    def workflow_thread():
        # Step 1
        self.page.run_task(lambda: self._update_step_status(step1, "running"))
        result = self.query_agent.generate_query(question)
        self.page.run_task(lambda: self._update_step_status(step1, "completed", result))

        # Step 2
        self.page.run_task(lambda: self._update_step_status(step2, "running"))
        docs = self.search_documents(result)
        self.page.run_task(lambda: self._update_step_status(step2, "completed"))

    thread = threading.Thread(target=workflow_thread, daemon=True)
    thread.start()
```

### PySide6 Version (New)
```python
from PySide6.QtCore import QThread, Signal

class WorkflowWorker(QThread):
    # Define signals for communication
    step_started = Signal(WorkflowStep)
    step_completed = Signal(WorkflowStep, str)
    step_error = Signal(WorkflowStep, str)

    def __init__(self, question: str):
        super().__init__()
        self.question = question
        self.is_running = True

    def run(self):
        """This runs in separate thread automatically."""
        try:
            # Step 1
            self.step_started.emit(WorkflowStep.GENERATE_AND_EDIT_QUERY)
            result = self.query_agent.generate_query(self.question)
            self.step_completed.emit(WorkflowStep.GENERATE_AND_EDIT_QUERY, result)

            # Step 2
            self.step_started.emit(WorkflowStep.SEARCH_DOCUMENTS)
            docs = self.search_documents(result)
            self.step_completed.emit(WorkflowStep.SEARCH_DOCUMENTS, f"Found {len(docs)} docs")

        except Exception as e:
            self.step_error.emit(current_step, str(e))

    def stop(self):
        self.is_running = False

# In your main window
class MainWindow(QMainWindow):
    def start_workflow(self):
        self.worker = WorkflowWorker(self.question)

        # Connect signals to GUI update methods (thread-safe)
        self.worker.step_started.connect(self.on_step_started)
        self.worker.step_completed.connect(self.on_step_completed)
        self.worker.step_error.connect(self.on_step_error)

        self.worker.start()  # Starts thread automatically

    def on_step_started(self, step: WorkflowStep):
        # This runs in MAIN thread - safe to update GUI
        self.step_cards[step].update_status(StepStatus.RUNNING, "Processing...")

    def on_step_completed(self, step: WorkflowStep, result: str):
        # This runs in MAIN thread - safe to update GUI
        self.step_cards[step].update_status(StepStatus.COMPLETED, result)
```

**Key advantages:**
- ✅ Type-safe signals (catches errors at development time)
- ✅ No need for `page.run_task()` - Qt handles thread safety
- ✅ Cleaner separation of worker logic from GUI
- ✅ Built-in thread lifecycle management
- ✅ Can connect multiple handlers to same signal
- ✅ Easier to test worker independently

## 4. Tabs Interface

### Flet Version
```python
# From your research_app.py
tabs = ft.Tabs(
    selected_index=0,
    animation_duration=300,
    tabs=[
        ft.Tab(
            text="Workflow Progress",
            icon=ft.Icons.LIST,
            content=workflow_content
        ),
        ft.Tab(
            text="Documents",
            icon=ft.Icons.DESCRIPTION,
            content=documents_content
        ),
        ft.Tab(
            text="Report",
            icon=ft.Icons.ARTICLE,
            content=report_content
        )
    ],
    expand=True
)
```

### PySide6 Version
```python
from PySide6.QtWidgets import QTabWidget

tabs = QTabWidget()
tabs.setTabPosition(QTabWidget.North)

# Add tabs
tabs.addTab(workflow_content, "📊 Workflow Progress")
tabs.addTab(documents_content, "📄 Documents")
tabs.addTab(report_content, "📝 Report")

# Switch tabs programmatically
tabs.setCurrentIndex(0)

# Connect tab change event
tabs.currentChanged.connect(self.on_tab_changed)

def on_tab_changed(self, index: int):
    print(f"Switched to tab {index}")
```

**Differences:**
- Similar API, slightly different method names
- Icons can be added via QIcon (not emoji strings, though emojis work in text)
- More styling options via stylesheets

## 5. File Dialogs

### Flet Version (Has Issues)
```python
def save_report(self, e):
    def file_picker_result(result: ft.FilePickerResultEvent):
        if result.path:
            # Save file
            pass

    file_picker = ft.FilePicker(on_result=file_picker_result)
    self.page.overlay.append(file_picker)
    self.page.update()

    file_picker.save_file(
        dialog_title="Save Report",
        file_name="report.md"
    )
```

### PySide6 Version (Works Perfectly)
```python
from PySide6.QtWidgets import QFileDialog

def save_report(self):
    file_path, selected_filter = QFileDialog.getSaveFileName(
        self,  # parent
        "Save Report",  # dialog title
        "report.md",  # default filename
        "Markdown Files (*.md);;Text Files (*.txt);;All Files (*)"  # filters
    )

    if file_path:
        with open(file_path, 'w') as f:
            f.write(self.report_content)
```

**Advantages:**
- ✅ Synchronous call (simpler logic)
- ✅ Native dialogs on all platforms
- ✅ No macOS FilePicker bugs
- ✅ Better file filtering
- ✅ Can set default directory easily

## 6. Progress Bars

### Flet Version
```python
# Simple progress bar
progress = ft.ProgressBar(value=0.5, width=400)

# Update it
progress.value = 0.75
progress.update()
```

### PySide6 Version
```python
# Simple progress bar
progress = QProgressBar()
progress.setMaximum(100)
progress.setValue(50)  # 50%

# Or with text format
progress.setFormat("%p% - %v/%m items")  # "50% - 50/100 items"
progress.setValue(75)  # Automatically updates display
```

**Advantages:**
- ✅ More control over text display
- ✅ Can show current/max values easily
- ✅ No need to call update() - automatic
- ✅ Can set different value ranges (not just 0-1)

## 7. Markdown Rendering

### Flet Version
```python
# Limited markdown support in Flet
# Usually need to use ft.Markdown but it's basic

markdown = ft.Markdown(
    value="""# Report
## Summary
Some **bold** and *italic* text.
""",
    selectable=True,
    extension_set=ft.MarkdownExtensionSet.GITHUB_WEB
)
```

### PySide6 Version
```python
# Built-in markdown support
text_edit = QTextEdit()
text_edit.setReadOnly(True)
text_edit.setMarkdown("""# Report
## Summary
Some **bold** and *italic* text.
""")

# Or use HTML for even more control
text_edit.setHtml("""
<h1>Report</h1>
<h2>Summary</h2>
<p>Some <b>bold</b> and <i>italic</i> text.</p>
""")

# For production: integrate a full markdown library
from markdown import markdown
html = markdown(markdown_text, extensions=['tables', 'fenced_code'])
text_edit.setHtml(html)
```

**Advantages:**
- ✅ Full HTML rendering capability
- ✅ Can integrate any Python markdown library
- ✅ Better styling control
- ✅ Supports CSS styling

## 8. Form Layouts (Settings/Config)

### Flet Version
```python
# From config_gui.py pattern
settings = ft.Column([
    ft.Row([
        ft.Text("Temperature:", width=120),
        ft.Slider(min=0, max=2, value=0.7, on_change=on_temp_change),
        ft.Text("0.7", width=50)
    ]),
    ft.Row([
        ft.Text("Top P:", width=120),
        ft.Slider(min=0, max=1, value=0.9, on_change=on_top_p_change),
        ft.Text("0.9", width=50)
    ]),
    ft.Row([
        ft.Text("Model:", width=120),
        ft.Dropdown(
            options=[ft.dropdown.Option(m) for m in models],
            on_change=on_model_change
        )
    ])
])
```

### PySide6 Version
```python
from PySide6.QtWidgets import QFormLayout, QSlider, QComboBox, QDoubleSpinBox

# QFormLayout automatically aligns labels and fields
form = QFormLayout()

# Temperature slider
temp_slider = QSlider(Qt.Horizontal)
temp_slider.setRange(0, 200)  # 0.0 to 2.0 (multiply by 100)
temp_slider.setValue(70)
temp_slider.valueChanged.connect(lambda v: self.on_temp_change(v/100))
form.addRow("Temperature:", temp_slider)

# Or use QDoubleSpinBox for more control
temp_spin = QDoubleSpinBox()
temp_spin.setRange(0.0, 2.0)
temp_spin.setValue(0.7)
temp_spin.setSingleStep(0.1)
temp_spin.valueChanged.connect(self.on_temp_change)
form.addRow("Temperature:", temp_spin)

# Top P slider
top_p_slider = QSlider(Qt.Horizontal)
top_p_slider.setRange(0, 100)
top_p_slider.setValue(90)
top_p_slider.valueChanged.connect(lambda v: self.on_top_p_change(v/100))
form.addRow("Top P:", top_p_slider)

# Model dropdown
model_combo = QComboBox()
model_combo.addItems(models)
model_combo.currentTextChanged.connect(self.on_model_change)
form.addRow("Model:", model_combo)
```

**Advantages:**
- ✅ QFormLayout auto-aligns labels
- ✅ More widget types (QDoubleSpinBox, QSpinBox)
- ✅ Built-in validation
- ✅ Better keyboard navigation

## 9. Scrolling Large Content

### Flet Version
```python
# Flet handles scrolling automatically for Column/Row
content = ft.Column(
    controls=[widget1, widget2, widget3, ...],
    scroll=ft.ScrollMode.AUTO
)
```

### PySide6 Version
```python
# Need explicit QScrollArea
scroll_area = QScrollArea()
scroll_area.setWidgetResizable(True)  # Important!
scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

# Create content widget
content_widget = QWidget()
content_layout = QVBoxLayout(content_widget)
content_layout.addWidget(widget1)
content_layout.addWidget(widget2)
content_layout.addWidget(widget3)

scroll_area.setWidget(content_widget)
```

**Note:** More explicit but gives you finer control over scrolling behavior.

## 10. Styling

### Flet Version
```python
# Individual widget properties
container = ft.Container(
    content=ft.Text("Hello"),
    bgcolor=ft.Colors.BLUE_50,
    border=ft.border.all(2, ft.Colors.BLUE_300),
    border_radius=5,
    padding=ft.padding.all(10)
)

# Limited theming
page.theme_mode = ft.ThemeMode.LIGHT
```

### PySide6 Version
```python
# CSS-like stylesheets (QSS)
widget.setStyleSheet("""
    QWidget {
        background-color: #E3F2FD;
        border: 2px solid #64B5F6;
        border-radius: 5px;
        padding: 10px;
    }
    QWidget:hover {
        background-color: #BBDEFB;
    }
""")

# Application-wide themes
app.setStyle("Fusion")  # Modern cross-platform style

# Or use third-party themes
import qt_material
qt_material.apply_stylesheet(app, theme='dark_blue.xml')
```

**Advantages:**
- ✅ More powerful styling with QSS
- ✅ Can style entire application consistently
- ✅ Pseudo-states (hover, pressed, disabled, etc.)
- ✅ Third-party theme libraries available

## Summary of Key Differences

| Aspect | Flet | PySide6 |
|--------|------|---------|
| **Philosophy** | Declarative, web-inspired | Traditional OOP, desktop-native |
| **Updates** | Manual `.update()` calls | Automatic repainting |
| **Threading** | `page.run_task()` | Signal/slot system |
| **Layouts** | Container-based | Layout managers |
| **Events** | Callbacks | Signals/slots |
| **Memory** | Garbage collected | Parent-child ownership |
| **Styling** | Individual properties | QSS (CSS-like) stylesheets |
| **Performance** | Web-based rendering | Native widgets |
| **File dialogs** | Buggy on macOS | Native, reliable |
| **Large datasets** | Can be slow | Model/View for millions of rows |
| **Type safety** | Limited | Full with signals/slots |

## Migration Checklist

When migrating a component from Flet to PySide6:

- [ ] Replace `ft.Column` with `QVBoxLayout`
- [ ] Replace `ft.Row` with `QHBoxLayout`
- [ ] Replace `ft.Container` with `QWidget` + layout + stylesheet
- [ ] Replace callbacks with signal/slot connections
- [ ] Remove all `.update()` calls (not needed)
- [ ] Replace `ft.Text` with `QLabel` or `QTextEdit`
- [ ] Replace `ft.TextField` with `QLineEdit` or `QTextEdit`
- [ ] Replace `ft.Button` with `QPushButton`
- [ ] Replace threading with `QThread` and signals
- [ ] Add parent relationships for proper ownership
- [ ] Test on all platforms (Qt handles differences automatically)

## Questions?

This comparison should help you understand the migration patterns. Let me know if you need:
- More specific examples for your use cases
- Help with particular widgets or layouts
- Assistance with the actual migration process
