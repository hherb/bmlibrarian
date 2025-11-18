# Qt UI Styling Migration Guide

## Overview

BMLibrarian now has a **centralized DPI-aware styling system** that eliminates hard-coded font sizes and dimensions. All Qt widgets should use this system to ensure consistent appearance across different screen DPIs and user font preferences.

## Quick Reference

### Import Statement
```python
from bmlibrarian.gui.qt.resources.styles import get_font_scale, StylesheetGenerator
```

### Basic Pattern
```python
class MyWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.scale = get_font_scale()  # Get once in __init__
        self._setup_ui()

    def _setup_ui(self):
        s = self.scale  # Shorthand

        # Use f-strings with scale values
        label.setStyleSheet(f"""
            QLabel {{
                font-size: {s['font_medium']}pt;
                padding: {s['padding_small']}px;
            }}
        """)

        # Set control heights
        button.setFixedHeight(s['control_height_medium'])
```

## Migration Steps

### Step 1: Import the styling system

**Before:**
```python
from PySide6.QtWidgets import QWidget, QPushButton
```

**After:**
```python
from PySide6.QtWidgets import QWidget, QPushButton
from bmlibrarian.gui.qt.resources.styles import get_font_scale
```

### Step 2: Get scale in `__init__`

**Before:**
```python
def __init__(self):
    super().__init__()
    self._setup_ui()
```

**After:**
```python
def __init__(self):
    super().__init__()
    self.scale = get_font_scale()  # Add this line
    self._setup_ui()
```

### Step 3: Replace hard-coded values

**Before:**
```python
label.setStyleSheet("font-size: 11pt; padding: 6px;")
button.setFixedHeight(30)
layout.setSpacing(8)
```

**After:**
```python
s = self.scale
label.setStyleSheet(f"font-size: {s['font_large']}pt; padding: {s['padding_small']}px;")
button.setFixedHeight(s['control_height_medium'])
layout.setSpacing(s['spacing_medium'])
```

## Common Conversions

### Font Sizes
| Hard-coded | Scale Value | Description |
|------------|-------------|-------------|
| `8pt` | `font_small` | Small labels, secondary text |
| `9pt` | `font_small` | Small labels, secondary text |
| `10pt` | `font_normal` | Body text (system default) |
| `11pt` | `font_medium` | Emphasized text |
| `12pt` | `font_large` | Headers |
| `14pt` | `font_xlarge` | Large headers |

### Spacing/Padding
| Hard-coded | Scale Value | Description |
|------------|-------------|-------------|
| `2px`, `3px` | `spacing_tiny` or `padding_tiny` | Minimal space |
| `4px`, `5px`, `6px` | `spacing_small` or `padding_small` | Small space |
| `6px`, `8px`, `10px` | `spacing_medium` or `padding_medium` | Medium space |
| `8px`, `10px`, `12px` | `spacing_large` or `padding_large` | Large space |

### Control Heights
| Hard-coded | Scale Value | Description |
|------------|-------------|-------------|
| `24px`, `28px` | `control_height_small` | Small buttons, inputs |
| `30px`, `32px` | `control_height_medium` | Normal buttons, inputs |
| `40px`, `44px` | `control_height_large` | Large buttons, text areas |
| `50px+` | `control_height_xlarge` | Extra large controls |

### Border Radius
| Hard-coded | Scale Value | Description |
|------------|-------------|-------------|
| `2px`, `3px` | `radius_tiny` | Subtle rounding |
| `4px`, `5px` | `radius_small` | Small rounding |
| `8px`, `10px` | `radius_medium` | Medium rounding |
| `12px`, `16px` | `radius_large` | Large rounding |

## Examples

### Example 1: Simple Label
**Before:**
```python
label = QLabel("Hello")
label.setStyleSheet("font-size: 11pt; color: #666;")
```

**After:**
```python
s = self.scale
label = QLabel("Hello")
label.setStyleSheet(f"font-size: {s['font_large']}pt; color: #666;")
```

### Example 2: Styled Button
**Before:**
```python
button = QPushButton("Click")
button.setFixedHeight(32)
button.setStyleSheet("""
    QPushButton {
        background-color: #2196F3;
        color: white;
        border-radius: 5px;
        font-size: 10pt;
        padding: 6px;
    }
""")
```

**After:**
```python
s = self.scale
button = QPushButton("Click")
button.setFixedHeight(s['control_height_medium'])
button.setStyleSheet(f"""
    QPushButton {{
        background-color: #2196F3;
        color: white;
        border-radius: {s['radius_small']}px;
        font-size: {s['font_medium']}pt;
        padding: {s['padding_small']}px;
    }}
""")
```

### Example 3: Layout Spacing
**Before:**
```python
layout = QVBoxLayout()
layout.setContentsMargins(10, 10, 10, 10)
layout.setSpacing(8)
```

**After:**
```python
s = self.scale
layout = QVBoxLayout()
layout.setContentsMargins(
    s['spacing_large'],
    s['spacing_large'],
    s['spacing_large'],
    s['spacing_large']
)
layout.setSpacing(s['spacing_medium'])
```

## Using StylesheetGenerator (Advanced)

For complex or repeated patterns, use `StylesheetGenerator`:

```python
from bmlibrarian.gui.qt.resources.styles import StylesheetGenerator

gen = StylesheetGenerator()

# Apply common patterns
button.setStyleSheet(gen.button_stylesheet())
input.setStyleSheet(gen.input_stylesheet())
header.setStyleSheet(gen.header_stylesheet())

# Custom template
widget.setStyleSheet(gen.custom('''
    QWidget {{
        font-size: {font_medium}pt;
        margin: {spacing_large}px;
    }}
'''))
```

## Priority Files to Migrate

1. **Document Cards** - `src/bmlibrarian/gui/qt/widgets/document_card.py`
2. **Configuration Tabs** - `src/bmlibrarian/gui/qt/plugins/configuration/*.py`
3. **Research Tab** - `src/bmlibrarian/gui/qt/plugins/research/research_tab.py`
4. **Fact Checker Tab** - `src/bmlibrarian/gui/qt/plugins/fact_checker/fact_checker_tab.py`
5. **All Custom Widgets** - `src/bmlibrarian/gui/qt/widgets/*.py`

## Testing

After migration, test your widget at different DPI settings:

```python
from bmlibrarian.gui.qt.resources.styles import FontScale

scale = FontScale()
print(f"Base font: {scale['base_font_size']}pt")
print(f"Line height: {scale['base_line_height']}px")
print(f"Medium control: {scale['control_height_medium']}px")
```

## Complete Documentation

See comprehensive guide: `src/bmlibrarian/gui/qt/resources/styles/README.md`

## Questions?

- Example implementation: `document_interrogation_tab.py`
- Demo widget: `src/bmlibrarian/gui/qt/resources/styles/example_widget.py`
- Run demo: `python -m bmlibrarian.gui.qt.resources.styles.example_widget`
