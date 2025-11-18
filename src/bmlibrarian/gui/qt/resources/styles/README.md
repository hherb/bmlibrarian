# DPI-Aware Font-Relative Styling System

## Overview

This module provides a centralized DPI-aware styling system for the BMLibrarian Qt UI. All dimensions (fonts, spacing, padding, control heights, etc.) are calculated relative to the system's default font, ensuring consistent and readable UI across all screen DPIs and user font preferences.

## Why Font-Relative Dimensions?

### The Problem
- **Hard-coded pixel sizes** look tiny on high-DPI displays (e.g., 4K, Retina)
- **User accessibility settings** are ignored if we use fixed pixel values
- **Different operating systems** have different default font sizes
- **Qt points** are DPI-independent for fonts but not for layout dimensions

### The Solution
Calculate all UI dimensions relative to:
1. **Font metrics**: Line height and character width from system default font
2. **Point sizes**: For font sizes (already DPI-independent)
3. **Relative multipliers**: All spacing/padding based on line height

## Quick Start

### Basic Usage

```python
from bmlibrarian.gui.qt.resources.styles import get_font_scale

# Get the scale dictionary
scale = get_font_scale()

# Use in f-strings for stylesheets
widget.setStyleSheet(f"""
    QLabel {{
        font-size: {scale['font_medium']}pt;
        padding: {scale['padding_small']}px;
    }}
""")
```

### Using StylesheetGenerator

```python
from bmlibrarian.gui.qt.resources.styles import StylesheetGenerator

# Create generator (automatically uses system font scale)
gen = StylesheetGenerator()

# Apply common patterns
button.setStyleSheet(gen.button_stylesheet())
input_field.setStyleSheet(gen.input_stylesheet())
header.setStyleSheet(gen.header_stylesheet())

# Custom templates with scale value substitution
widget.setStyleSheet(gen.custom('''
    QWidget {{
        font-size: {font_medium}pt;
        margin: {spacing_large}px;
        border-radius: {radius_medium}px;
    }}
'''))
```

### Convenience Functions

```python
from bmlibrarian.gui.qt.resources.styles import (
    apply_button_style,
    apply_input_style,
    apply_header_style
)

# One-line styling
apply_button_style(my_button, bg_color="#4CAF50")
apply_input_style(my_text_edit)
apply_header_style(my_label, bg_color="#E0E0E0")
```

## Available Scale Values

### Font Sizes (in points, DPI-independent)
```python
'font_tiny'    # 70% of base  - Very small labels
'font_small'   # 85% of base  - Small labels, secondary text
'font_normal'  # 100% of base - System default, body text
'font_medium'  # 110% of base - Emphasized text, chat messages
'font_large'   # 120% of base - Section headers
'font_xlarge'  # 140% of base - Large headers
'font_icon'    # 180% of base - Icon text (emoji)
```

### Spacing (in pixels, relative to line height)
```python
'spacing_tiny'    # 15% of line height (~2-3px)
'spacing_small'   # 25% of line height (~4-6px)
'spacing_medium'  # 40% of line height (~6-10px)
'spacing_large'   # 50% of line height (~8-12px)
'spacing_xlarge'  # 75% of line height (~12-18px)
```

### Padding (in pixels, relative to line height)
```python
'padding_tiny'    # 15% of line height
'padding_small'   # 30% of line height
'padding_medium'  # 40% of line height
'padding_large'   # 60% of line height
'padding_xlarge'  # 90% of line height
```

### Control Heights (in pixels, relative to line height)
```python
'control_height_small'   # 1.8× line height (~24-30px)
'control_height_medium'  # 2.2× line height (~30-40px)
'control_height_large'   # 2.8× line height (~40-50px)
'control_height_xlarge'  # 3.5× line height (~50-65px)
```

### Border Radius (in pixels, relative to line height)
```python
'radius_tiny'    # 15% of line height (~2-3px)
'radius_small'   # 30% of line height (~4-6px)
'radius_medium'  # 50% of line height (~8-12px)
'radius_large'   # 90% of line height (~12-18px)
```

### Icon Sizes (in pixels, relative to line height)
```python
'icon_tiny'    # 0.8× line height (~12-16px)
'icon_small'   # 1.0× line height (~16-20px)
'icon_medium'  # 1.5× line height (~24-30px)
'icon_large'   # 2.0× line height (~32-40px)
'icon_xlarge'  # 3.0× line height (~48-60px)
```

### Base Measurements
```python
'base_font_size'    # System default font size in points
'base_line_height'  # Line spacing in pixels
'char_width'        # Average character width in pixels
```

## Complete Example: Creating a Styled Widget

```python
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel
from bmlibrarian.gui.qt.resources.styles import get_font_scale

class MyStyledWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.scale = get_font_scale()  # Get scale once in __init__
        self._setup_ui()

    def _setup_ui(self):
        s = self.scale  # Shorthand for cleaner code

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            s['spacing_medium'],
            s['spacing_medium'],
            s['spacing_medium'],
            s['spacing_medium']
        )
        layout.setSpacing(s['spacing_large'])

        # Header with scaled font and padding
        header = QLabel("My Header")
        header.setStyleSheet(f"""
            QLabel {{
                font-size: {s['font_large']}pt;
                font-weight: bold;
                padding: {s['padding_small']}px;
                background-color: #E0E0E0;
            }}
        """)
        layout.addWidget(header)

        # Button with scaled dimensions
        button = QPushButton("Click Me")
        button.setFixedHeight(s['control_height_medium'])
        button.setStyleSheet(f"""
            QPushButton {{
                background-color: #2196F3;
                color: white;
                border-radius: {s['radius_small']}px;
                font-size: {s['font_medium']}pt;
                padding: {s['padding_small']}px;
            }}
            QPushButton:hover {{
                background-color: #1976D2;
            }}
        """)
        layout.addWidget(button)
```

## Best Practices

### DO ✅

1. **Get scale once in `__init__`** and reuse:
   ```python
   def __init__(self):
       super().__init__()
       self.scale = get_font_scale()
   ```

2. **Use shorthand `s = self.scale`** in methods for cleaner code:
   ```python
   def _create_widget(self):
       s = self.scale
       widget.setStyleSheet(f"font-size: {s['font_medium']}pt;")
   ```

3. **Use f-strings** for dynamic stylesheet generation:
   ```python
   self.setStyleSheet(f"padding: {s['padding_large']}px;")
   ```

4. **Prefer point sizes for fonts**, pixel sizes for layout:
   ```python
   font-size: {s['font_medium']}pt;  # Points for fonts
   padding: {s['padding_small']}px;   # Pixels for layout
   ```

5. **Use StylesheetGenerator** for complex/repeated patterns:
   ```python
   gen = StylesheetGenerator()
   widget.setStyleSheet(gen.button_stylesheet())
   ```

### DON'T ❌

1. **Don't hard-code pixel or point values:**
   ```python
   # BAD
   widget.setStyleSheet("font-size: 10pt; padding: 8px;")

   # GOOD
   s = self.scale
   widget.setStyleSheet(f"font-size: {s['font_medium']}pt; padding: {s['padding_medium']}px;")
   ```

2. **Don't call `get_font_scale()` repeatedly:**
   ```python
   # BAD - wasteful
   def method1(self):
       s = get_font_scale()
       ...
   def method2(self):
       s = get_font_scale()
       ...

   # GOOD - call once
   def __init__(self):
       self.scale = get_font_scale()
   ```

3. **Don't mix scaled and hard-coded values:**
   ```python
   # BAD - inconsistent
   widget.setStyleSheet(f"font-size: {s['font_medium']}pt; padding: 8px;")

   # GOOD - all scaled
   widget.setStyleSheet(f"font-size: {s['font_medium']}pt; padding: {s['padding_medium']}px;")
   ```

## Advanced: FontScale Singleton

For better performance when accessing scale values frequently:

```python
from bmlibrarian.gui.qt.resources.styles import FontScale

# Access singleton directly (only calculated once)
scale = FontScale()

# Dictionary-style access
font_size = scale['font_medium']

# Method access with default
spacing = scale.get('spacing_large', 8)

# Refresh if system font changes (rare)
scale.refresh()
```

## Migration Guide

### Converting Existing Hard-Coded Styles

**Before:**
```python
widget.setStyleSheet("""
    QLabel {
        font-size: 11pt;
        padding: 6px 8px;
    }
""")
button.setFixedHeight(30)
```

**After:**
```python
s = self.scale
widget.setStyleSheet(f"""
    QLabel {{
        font-size: {s['font_large']}pt;
        padding: {s['padding_small']}px {s['padding_medium']}px;
    }}
""")
button.setFixedHeight(s['control_height_medium'])
```

## Testing Different DPIs

To test how your UI looks at different DPIs:

```python
from bmlibrarian.gui.qt.resources.styles import FontScale

# Simulate different base font sizes
scale = FontScale()
print(f"Current base font: {scale['base_font_size']}pt")
print(f"Line height: {scale['base_line_height']}px")
print(f"Control height medium: {scale['control_height_medium']}px")
```

## See Also

- **Document Interrogation Tab**: Example implementation using this system
  - `src/bmlibrarian/gui/qt/plugins/document_interrogation/document_interrogation_tab.py`
- **Qt Style Sheets**: https://doc.qt.io/qt-6/stylesheet-reference.html
- **QFontMetrics**: https://doc.qt.io/qt-6/qfontmetrics.html
