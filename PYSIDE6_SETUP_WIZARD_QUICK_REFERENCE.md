# BMLibrarian PySide6 Setup Wizard - Quick Reference

## Documentation

**Main Guide:** `/home/user/bmlibrarian/doc/developers/PYSIDE6_SETUP_WIZARD_GUIDE.md`

This document contains comprehensive information about:
- PySide6/Qt code patterns
- DPI-aware styling system
- Database configuration and management
- Environment file structure
- Import CLI patterns
- Recommended wizard architecture

---

## Key Files by Category

### PySide6/Qt Framework
```
Entry Point:
  /home/user/bmlibrarian/bmlibrarian_qt.py

Application Bootstrap:
  /home/user/bmlibrarian/src/bmlibrarian/gui/qt/core/application.py

Main Window Pattern:
  /home/user/bmlibrarian/src/bmlibrarian/gui/qt/core/main_window.py

Configuration Management:
  /home/user/bmlibrarian/src/bmlibrarian/gui/qt/core/config_manager.py

Threading Utilities:
  /home/user/bmlibrarian/src/bmlibrarian/gui/qt/utils/threading.py
```

### Styling & DPI System
```
DPI Scaling (MUST USE for dimensions):
  /home/user/bmlibrarian/src/bmlibrarian/gui/qt/resources/styles/dpi_scale.py

Stylesheet Generator (MUST USE for styling):
  /home/user/bmlibrarian/src/bmlibrarian/gui/qt/resources/styles/stylesheet_generator.py

Theme Generator:
  /home/user/bmlibrarian/src/bmlibrarian/gui/qt/resources/styles/theme_generator.py
```

### Database & Configuration
```
Database Manager:
  /home/user/bmlibrarian/src/bmlibrarian/database.py

Configuration System:
  /home/user/bmlibrarian/src/bmlibrarian/config.py

Schema Definition:
  /home/user/bmlibrarian/baseline_schema.sql

Database Migrations:
  /home/user/bmlibrarian/migrations/
```

### Importers
```
MedRxiv Importer:
  /home/user/bmlibrarian/src/bmlibrarian/importers/medrxiv_importer.py
  /home/user/bmlibrarian/medrxiv_import_cli.py (usage example)

PubMed Importer:
  /home/user/bmlibrarian/src/bmlibrarian/importers/pubmed_importer.py
  /home/user/bmlibrarian/pubmed_import_cli.py (usage example)

PubMed Bulk Importer:
  /home/user/bmlibrarian/src/bmlibrarian/importers/pubmed_bulk_importer.py
  /home/user/bmlibrarian/pubmed_bulk_cli.py (usage example)

Importer Module:
  /home/user/bmlibrarian/src/bmlibrarian/importers/__init__.py
```

### Reference Implementation
```
Initial Setup Script (shows setup pattern):
  /home/user/bmlibrarian/initial_setup_and_download.py

Environment Template:
  /home/user/bmlibrarian/test_database.env.example
```

---

## Golden Rules Checklist

When implementing the setup wizard:

- [ ] **No magic numbers** - Use `dpi_scale.py` for all dimensions
- [ ] **No hardcoded paths** - Use `Path.home()` and `expanduser()`
- [ ] **No inline styles** - Use `StylesheetGenerator` class
- [ ] **Type hints everywhere** - All parameters and returns typed
- [ ] **Docstrings required** - All functions/classes documented
- [ ] **Error handling** - All operations wrapped in try/except
- [ ] **Threading for long ops** - Use QThread for DB/network operations
- [ ] **Input validation** - Validate all user inputs before use
- [ ] **Progress feedback** - Show status messages and progress bars
- [ ] **Reversibility** - Allow users to go back and change settings

---

## DPI Scale Keys Quick Reference

### Font Sizes (points)
- `font_micro`, `font_tiny`, `font_small`, `font_normal`, `font_medium`
- `font_large`, `font_xlarge`, `font_icon`

### Spacing & Padding (pixels)
- `spacing_tiny`, `spacing_small`, `spacing_medium`, `spacing_large`, `spacing_xlarge`
- `padding_tiny`, `padding_small`, `padding_medium`, `padding_large`, `padding_xlarge`

### Control Dimensions (pixels)
- `control_height_small`, `control_height_medium`, `control_height_large`, `control_height_xlarge`
- `control_width_tiny`, `control_width_small`, `control_width_medium`, `control_width_large`, `control_width_xlarge`

### Borders & Icons
- Border radius: `radius_tiny`, `radius_small`, `radius_medium`, `radius_large`
- Icons: `icon_tiny`, `icon_small`, `icon_medium`, `icon_large`, `icon_xlarge`

### Usage
```python
from bmlibrarian.gui.qt.resources.styles.dpi_scale import get_font_scale, get_scale_value

scale = get_font_scale()
height = scale['control_height_medium']
# or
height = get_scale_value('control_height_medium')
```

---

## StylesheetGenerator Quick Reference

### Methods Available
```python
from bmlibrarian.gui.qt.resources.styles.stylesheet_generator import StylesheetGenerator

gen = StylesheetGenerator()

# Pre-made stylesheets
gen.button_stylesheet(bg_color, text_color, hover_color)
gen.input_stylesheet(border_color, focus_color)
gen.label_stylesheet(font_size_key, color, bold)
gen.header_stylesheet(font_size_key, bg_color, text_color)
gen.card_stylesheet(bg_color, border_color, radius_key, padding_key)
gen.combo_stylesheet(font_size_key, padding_key)

# Custom stylesheet with scale substitution
gen.custom("""
    QLineEdit {
        padding: {padding_medium}px;
        font-size: {font_normal}pt;
    }
""")
```

### Convenience Functions
```python
from bmlibrarian.gui.qt.resources.styles.stylesheet_generator import (
    apply_button_style, apply_input_style, apply_header_style
)

apply_button_style(widget, bg_color, text_color, hover_color)
apply_input_style(widget)
apply_header_style(widget, bg_color, text_color)
```

---

## Database Connection Quick Reference

### Test Connection
```python
import psycopg

try:
    with psycopg.connect(
        host=host,
        port=int(port),
        user=user,
        password=password,
        dbname=dbname
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT version()")
            return True, cur.fetchone()[0]
except Exception as e:
    return False, str(e)
```

### Create Database
```python
with psycopg.connect(
    host=host,
    port=int(port),
    user=user,
    password=password,
    dbname="postgres"  # Connect to default postgres db
) as conn:
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(f"CREATE DATABASE {dbname}")
```

### Apply Schema
```python
from pathlib import Path

schema_file = Path("/home/user/bmlibrarian/baseline_schema.sql")
schema_sql = schema_file.read_text()

with psycopg.connect(...) as conn:
    with conn.cursor() as cur:
        cur.execute(schema_sql)
    conn.commit()
```

---

## Environment Variables

### Required (.env file)
```
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=username
POSTGRES_PASSWORD=password
POSTGRES_DB=knowledgebase
```

### Optional (.env file)
```
PDF_BASE_DIR=~/knowledgebase/pdf
NCBI_EMAIL=user@example.com
NCBI_API_KEY=
OLLAMA_HOST=http://localhost:11434
```

---

## Importer Usage Quick Reference

### MedRxiv
```python
from bmlibrarian.importers import MedRxivImporter

importer = MedRxivImporter(pdf_base_dir="~/knowledgebase/pdf")
stats = importer.update_database(download_pdfs=True, days_to_fetch=7)
# Returns: {'total_processed': int, 'dates_processed': str}
```

### PubMed (E-Utilities)
```python
from bmlibrarian.importers import PubMedImporter

importer = PubMedImporter(email="user@example.com", api_key="key")
stats = importer.import_by_search(query="COVID-19", max_results=100)
# Returns: {'total_found': int, 'parsed': int, 'imported': int}
```

### PubMed Bulk (FTP)
```python
from bmlibrarian.importers.pubmed_bulk_importer import PubMedBulkImporter

importer = PubMedBulkImporter(data_dir="./pubmed_data")
count = importer.download_baseline(skip_existing=True)
stats = importer.import_baseline()
# Returns: {'imported': int, 'skipped': int, 'errors': int}
```

---

## Wizard Page Structure Recommendation

```
1. Welcome Page
   - Quick vs Advanced setup toggle
   - Brief description

2. Database Configuration Page
   - Host input (localhost)
   - Port input (5432)
   - Username input
   - Password input (masked)
   - Database name input (knowledgebase)
   - Test Connection button
   - Status indicator

3. File System Page
   - PDF Base Directory (expandable path)
   - Check directory writable

4. Data Sources Page
   - MedRxiv checkbox + days field
   - PubMed checkbox + query field + max results
   - PubMed Bulk warning checkbox

5. NCBI Configuration Page
   - Email input (optional)
   - API Key input (optional)
   - Explanation of benefits

6. Ollama Configuration Page
   - Host input (http://localhost:11434)
   - Test Connection button
   - Available models list

7. Review Page
   - Summary of all settings
   - Confirm button
   - Back button

8. Progress Page
   - Overall progress bar
   - Current operation status
   - Log/details area
   - Cancel button (if safe)

9. Complete Page
   - Success message
   - Summary of what was created
   - Open BMLibrarian button
   - View Config button
```

---

## Threading Pattern for Wizard

```python
from PySide6.QtCore import QThread, Signal

class SetupWorkerThread(QThread):
    """Worker thread for long-running setup operations."""
    
    progress = Signal(str)  # Status message updates
    completed = Signal(dict)  # Result when done
    error = Signal(str)  # Error message if failed
    
    def __init__(self, task_func, *args, **kwargs):
        super().__init__()
        self.task_func = task_func
        self.args = args
        self.kwargs = kwargs
    
    def run(self):
        try:
            self.progress.emit("Starting operation...")
            result = self.task_func(*self.args, **self.kwargs)
            self.completed.emit(result)
        except Exception as e:
            self.error.emit(str(e))

# Usage in wizard page
def on_test_connection(self):
    self.worker = SetupWorkerThread(test_db_connection, host, port, user, password)
    self.worker.progress.connect(self.update_status)
    self.worker.completed.connect(self.on_connection_success)
    self.worker.error.connect(self.on_connection_error)
    self.worker.start()
```

---

## Files to Create

For the setup wizard implementation:

1. **setup_wizard.py** - Main QWizard subclass
2. **setup_pages.py** - Individual QWizardPage subclasses
3. **setup_validators.py** - Input validation functions
4. **setup_config_writer.py** - Write .env and config.json files
5. **setup_importer_runner.py** - Run importers in background
6. **setup_wizard_main.py** - Entry point (like bmlibrarian_qt.py)

Location: Create in `/home/user/bmlibrarian/src/bmlibrarian/gui/qt/setup_wizard/`

---

## Configuration File Paths

**Primary:** `~/.bmlibrarian/config.json`
**Backup:** `bmlibrarian_config.json` (current directory)
**GUI Config:** `~/.bmlibrarian/gui_config.json`
**Environment:** `.env` (project root or `~/.bmlibrarian/.env`)

---

## Next Steps

1. Read the comprehensive guide: `/home/user/bmlibrarian/doc/developers/PYSIDE6_SETUP_WIZARD_GUIDE.md`
2. Create the wizard directory structure
3. Implement the main QWizard class
4. Implement individual wizard pages
5. Add validators and error handling
6. Implement threading for long operations
7. Test with actual database and importers
8. Create user documentation

---

## Key Requirements from CLAUDE.md

- Python >= 3.12
- PySide6 for GUI
- psycopg >= 3.2.9 for PostgreSQL
- requests >= 2.31.0 for HTTP
- Ollama service for LLM features
- PostgreSQL with pgvector extension

Never:
- Hardcode paths (use Path.home())
- Use magic numbers (use dpi_scale.py)
- Bypass the styling system (use StylesheetGenerator)
- Modify production database
- Trust user input without validation

Always:
- Use type hints
- Include docstrings
- Handle errors gracefully
- Provide user feedback
- Log important operations
- Use threading for long operations

