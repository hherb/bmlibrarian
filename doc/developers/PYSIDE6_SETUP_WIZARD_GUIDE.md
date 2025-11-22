# BMLibrarian PySide6 Setup Wizard - Codebase Analysis Guide

## Executive Summary

This document provides a comprehensive map of the BMLibrarian codebase for implementing a PySide6 setup wizard. The wizard will guide users through initial configuration including database setup, API keys, and data source imports.

---

## 1. PYSIDE6/QT CODE PATTERNS

### Entry Point Architecture
**File:** `/home/user/bmlibrarian/bmlibrarian_qt.py`
- Main entry point for Qt GUI applications
- Uses BMLibrarianApplication wrapper pattern
- Loads plugins dynamically via PluginManager

### Application Bootstrap
**Files:**
- `/home/user/bmlibrarian/src/bmlibrarian/gui/qt/core/application.py` - Main QApplication wrapper
- `/home/user/bmlibrarian/src/bmlibrarian/gui/qt/core/main_window.py` - QMainWindow with plugin tabs
- `/home/user/bmlibrarian/src/bmlibrarian/gui/qt/core/config_manager.py` - GUI configuration persistence

### Key Pattern: QMainWindow + Plugin Architecture
```python
from PySide6.QtWidgets import QMainWindow, QTabWidget, QWidget, QVBoxLayout
from PySide6.QtCore import Qt, Slot

class BMLibrarianMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BMLibrarian - Biomedical Literature Research")
        self.setMinimumSize(800, 600)
        
        # Tab widget for plugin-based interface
        self.tab_widget = QTabWidget()
        self.setCentralWidget(self.tab_widget)
```

### Wizard-Appropriate Base: QWizard
For your setup wizard, consider using QWizard instead of QMainWindow:
```python
from PySide6.QtWidgets import QWizard, QWizardPage, QVBoxLayout, QLineEdit, QLabel
from PySide6.QtCore import Qt

class SetupWizard(QWizard):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BMLibrarian Setup Wizard")
        self.setWizardStyle(QWizard.ModernStyle)
        self.setMinimumSize(600, 500)
        
        # Add pages
        self.setPage(PageDatabase, DatabaseConfigPage())
        self.setPage(PagePubMed, PubMedConfigPage())
        self.start()
```

---

## 2. STYLING SYSTEM (DPI-Aware)

### DPI Scale Module
**File:** `/home/user/bmlibrarian/src/bmlibrarian/gui/qt/resources/styles/dpi_scale.py`

**Key Classes:**
- `FontScale` - Singleton for DPI-aware scaling based on system font metrics
- `get_font_scale()` - Get dictionary of all scaling values
- `get_scale_value(key, default)` - Get single value (e.g., 'padding_medium')

**Available Scale Keys:**
```python
# Font sizes (in points)
'font_micro', 'font_tiny', 'font_small', 'font_normal', 'font_medium', 
'font_large', 'font_xlarge', 'font_icon'

# Spacing/Padding (in pixels, relative to line height)
'spacing_tiny', 'spacing_small', 'spacing_medium', 'spacing_large', 'spacing_xlarge'
'padding_tiny', 'padding_small', 'padding_medium', 'padding_large', 'padding_xlarge'

# Control dimensions
'control_height_small', 'control_height_medium', 'control_height_large'
'control_width_small', 'control_width_medium', 'control_width_large'

# Border radius
'radius_tiny', 'radius_small', 'radius_medium', 'radius_large'

# Icon sizes
'icon_tiny', 'icon_small', 'icon_medium', 'icon_large', 'icon_xlarge'
```

**Usage in Wizard:**
```python
from bmlibrarian.gui.qt.resources.styles.dpi_scale import get_font_scale, get_scale_value

scale = get_font_scale()
button.setMinimumHeight(scale['control_height_medium'])
layout.setSpacing(scale['spacing_medium'])
font.setPointSize(scale['font_normal'])
```

### Stylesheet Generator
**File:** `/home/user/bmlibrarian/src/bmlibrarian/gui/qt/resources/styles/stylesheet_generator.py`

**Available Methods:**
```python
from bmlibrarian.gui.qt.resources.styles.stylesheet_generator import StylesheetGenerator

gen = StylesheetGenerator()

# Pre-made stylesheets
button_style = gen.button_stylesheet(
    bg_color="#2196F3",
    text_color="white",
    hover_color="#1976D2"
)

input_style = gen.input_stylesheet(
    border_color="#CCC",
    focus_color="#2196F3"
)

header_style = gen.header_stylesheet(
    font_size_key='font_large',
    bg_color="#E0E0E0"
)

card_style = gen.card_stylesheet(
    bg_color="#FFFFFF",
    border_color="#CCC"
)

# Custom templates
custom_style = gen.custom("""
    QLineEdit {{
        padding: {padding_medium}px;
        font-size: {font_normal}pt;
        border: 1px solid #CCC;
        border-radius: {radius_small}px;
    }}
""")
```

**Convenience Functions:**
```python
from bmlibrarian.gui.qt.resources.styles.stylesheet_generator import (
    apply_button_style, apply_input_style, apply_header_style
)

apply_button_style(my_button, "#2196F3", "white", "#1976D2")
apply_input_style(my_text_edit)
apply_header_style(my_label, "#E0E0E0", "#000")
```

### Theme Generator
**File:** `/home/user/bmlibrarian/src/bmlibrarian/gui/qt/resources/styles/theme_generator.py`

---

## 3. DATABASE CONNECTION & MANAGEMENT

### DatabaseManager Class
**File:** `/home/user/bmlibrarian/src/bmlibrarian/database.py`

**Key Methods:**
```python
from bmlibrarian.database import DatabaseManager, get_db_manager

# Get singleton instance
db_manager = get_db_manager()

# Get connection from pool
with db_manager.get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT id, name FROM sources")
        results = cur.fetchall()

# Test connection
is_connected = db_manager.test_connection()

# Get table counts
sources = db_manager.get_source_ids()  # Returns dict of source names to IDs
```

### Connection Configuration
**Reads from environment variables:**
```
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=your_username
POSTGRES_PASSWORD=your_password
POSTGRES_DB=knowledgebase
```

### Schema Creation
**File:** `/home/user/bmlibrarian/baseline_schema.sql`

For setup wizard, need to:
1. Validate PostgreSQL connectivity
2. Create database if not exists
3. Apply schema (check migrations in `/home/user/bmlibrarian/migrations/`)

---

## 4. ENVIRONMENT FILE (.ENV) STRUCTURE

### Required Variables for Setup
```
# PostgreSQL Connection (REQUIRED)
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=your_username
POSTGRES_PASSWORD=your_password
POSTGRES_DB=knowledgebase

# File System (OPTIONAL)
PDF_BASE_DIR=~/knowledgebase/pdf

# NCBI/PubMed Configuration (OPTIONAL)
NCBI_EMAIL=your.email@example.com
NCBI_API_KEY=

# Ollama Configuration (OPTIONAL)
OLLAMA_HOST=http://localhost:11434
```

### Config File Format
**Primary location:** `~/.bmlibrarian/config.json`
**Fallback location:** `bmlibrarian_config.json` (current directory)

**Example structure:**
```json
{
  "database": {
    "host": "localhost",
    "port": 5432,
    "user": "postgres",
    "password": "secret",
    "name": "knowledgebase"
  },
  "file_system": {
    "pdf_base_dir": "~/knowledgebase/pdf"
  },
  "ncbi": {
    "email": "user@example.com",
    "api_key": ""
  },
  "ollama": {
    "host": "http://localhost:11434"
  },
  "agents": {
    "query_agent": { "model": "gpt-oss:20b", "temperature": 0.7 },
    "scoring_agent": { "model": "medgemma4B_it_q8:latest" }
  }
}
```

---

## 5. IMPORT CLI PATTERNS

### MedRxiv Importer
**File:** `/home/user/bmlibrarian/medrxiv_import_cli.py`
**Class:** `MedRxivImporter` from `src.bmlibrarian.importers`

**Usage:**
```python
from bmlibrarian.importers import MedRxivImporter

importer = MedRxivImporter(pdf_base_dir="~/knowledgebase/pdf")

# Update database with recent papers
stats = importer.update_database(
    download_pdfs=True,
    days_to_fetch=7,
    start_date_override=None,
    end_date=None
)
# Returns: {'total_processed': int, 'dates_processed': str}

# Fetch missing PDFs
count = importer.fetch_missing_pdfs(max_retries=3, limit=None)

# Get status
status = importer.get_status()
```

### PubMed Importer (E-Utilities)
**File:** `/home/user/bmlibrarian/pubmed_import_cli.py`
**Class:** `PubMedImporter` from `src.bmlibrarian.importers`

**Usage:**
```python
from bmlibrarian.importers import PubMedImporter

importer = PubMedImporter(
    email="user@example.com",  # Optional, required for good NCBI rate limits
    api_key="ncbi_api_key"     # Optional, increases rate limits
)

# Search and import
stats = importer.import_by_search(
    query="COVID-19 vaccine",
    max_results=100,
    min_date=None,
    max_date=None
)
# Returns: {'total_found': int, 'parsed': int, 'imported': int}

# Import by PMIDs
stats = importer.import_by_pmids(pmids=[12345678, 23456789])
```

### PubMed Bulk Importer (FTP)
**File:** `/home/user/bmlibrarian/pubmed_bulk_cli.py`
**Class:** `PubMedBulkImporter` from `src.bmlibrarian.importers.pubmed_bulk_importer`

**Usage:**
```python
from bmlibrarian.importers.pubmed_bulk_importer import PubMedBulkImporter

importer = PubMedBulkImporter(
    data_dir="./pubmed_data",
    use_tracking=True
)

# Download baseline (~38M articles, ~300-400GB)
count = importer.download_baseline(skip_existing=True)

# Download updates (new articles)
count = importer.download_updates(skip_existing=True)

# Import downloaded files
stats = importer.import_baseline()
stats = importer.import_updates()
# Returns: {'imported': int, 'skipped': int, 'errors': int}
```

---

## 6. INITIAL SETUP SCRIPT PATTERN

### File: `/home/user/bmlibrarian/initial_setup_and_download.py`

**Key Functions:**
```python
def load_env_file(env_file_path: Path) -> dict:
    """Parse .env file into environment variables."""
    # Skips comments (#), parses KEY=VALUE format
    # Handles quoted values
    # Validates required variables
    return env_vars  # Dict[str, str]

def test_database_connection(db_config: dict) -> bool:
    """Test PostgreSQL connectivity."""
    # Attempts connection
    # Returns True/False

def create_database(db_config: dict, db_name: str) -> bool:
    """Create database if not exists."""
    # Uses CREATE DATABASE IF NOT EXISTS

def apply_migrations(db_config: dict, migrations_dir: Path) -> bool:
    """Apply database schema migrations."""
    # Reads migration files from directory
    # Executes in order
```

**Wizard can replicate this pattern:**
1. Get user input (database credentials, file paths)
2. Test connection
3. Create database
4. Apply schema
5. Configure importers
6. Optional: Run initial import

---

## 7. RECOMMENDED SETUP WIZARD ARCHITECTURE

### Wizard Page Structure
```
Page 1: Welcome
├─ Welcome message
├─ "Quick Setup" vs "Advanced Setup" toggle

Page 2: Database Configuration
├─ PostgreSQL Host (default: localhost)
├─ PostgreSQL Port (default: 5432)
├─ Database User
├─ Database Password (masked input)
├─ Database Name (default: knowledgebase)
├─ "Test Connection" button
└─ Status indicator

Page 3: File System Configuration
├─ PDF Base Directory (default: ~/knowledgebase/pdf)
└─ Verify directory writable

Page 4: Data Sources (Optional)
├─ Checkbox: Import from MedRxiv
│  └─ Days to fetch (default: 7)
├─ Checkbox: Import from PubMed
│  ├─ Search query (optional)
│  └─ Max results (default: 100)
└─ Checkbox: Download PubMed Baseline (warn: 300-400GB)

Page 5: NCBI/PubMed Configuration (Optional)
├─ NCBI Email
├─ NCBI API Key
└─ Note: Improves rate limits

Page 6: Ollama Configuration (Optional)
├─ Ollama Host (default: http://localhost:11434)
├─ "Test Connection" button
└─ Available models list

Page 7: Review & Confirm
├─ Summary of configuration
├─ Final "Apply Setup" button
└─ Status progress indicator

Page 8: Setup Complete
├─ Success message
├─ Import progress (if imports selected)
├─ "Open BMLibrarian" button
└─ "View Configuration File" button
```

### Key Implementation Files to Create
1. `setup_wizard.py` - Main QWizard subclass
2. `setup_pages.py` - Individual QWizardPage subclasses
3. `setup_validators.py` - Database, network, file system validation
4. `setup_config_writer.py` - Write .env and config.json files
5. `setup_importer_runner.py` - Run importers in background thread

---

## 8. KEY FILE PATHS SUMMARY

### Configuration
```
~/.bmlibrarian/config.json           # Main config file
~/.bmlibrarian/gui_config.json       # GUI-specific config
.env                                  # Environment variables (root)
test_database.env.example             # Template for test config
```

### Styling & DPI System
```
src/bmlibrarian/gui/qt/resources/styles/dpi_scale.py
src/bmlibrarian/gui/qt/resources/styles/stylesheet_generator.py
src/bmlibrarian/gui/qt/resources/styles/theme_generator.py
```

### Core Modules
```
src/bmlibrarian/database.py           # DatabaseManager class
src/bmlibrarian/config.py             # Configuration system
src/bmlibrarian/importers/            # Importer classes
  ├── medrxiv_importer.py
  ├── pubmed_importer.py
  └── pubmed_bulk_importer.py
```

### Qt GUI Framework
```
src/bmlibrarian/gui/qt/core/application.py       # QApplication wrapper
src/bmlibrarian/gui/qt/core/main_window.py       # QMainWindow pattern
src/bmlibrarian/gui/qt/core/config_manager.py    # GUI config persistence
src/bmlibrarian/gui/qt/core/plugin_manager.py    # Plugin loading
```

### Database
```
baseline_schema.sql                  # Base schema definition
migrations/                          # Database migration scripts
```

### Entry Points
```
bmlibrarian_qt.py                    # Qt GUI entry point
pubmed_import_cli.py                 # PubMed import reference
medrxiv_import_cli.py                # MedRxiv import reference
pubmed_bulk_cli.py                   # Bulk import reference
initial_setup_and_download.py        # Setup reference
```

---

## 9. THREADING PATTERN FOR LONG-RUNNING OPERATIONS

### Qt Threading Utilities
**File:** `/home/user/bmlibrarian/src/bmlibrarian/gui/qt/utils/threading.py`

**Pattern for non-blocking operations:**
```python
from PySide6.QtCore import QThread, Signal

class WorkerThread(QThread):
    progress = Signal(str)
    completed = Signal(dict)
    error = Signal(str)
    
    def __init__(self, task_func, *args):
        super().__init__()
        self.task_func = task_func
        self.args = args
    
    def run(self):
        try:
            result = self.task_func(*self.args)
            self.completed.emit(result)
        except Exception as e:
            self.error.emit(str(e))

# Usage in wizard page
def test_connection(self):
    self.worker = WorkerThread(
        DatabaseManager().test_connection
    )
    self.worker.completed.connect(self.on_connection_success)
    self.worker.error.connect(self.on_connection_error)
    self.worker.start()
```

---

## 10. DATABASE TESTING & VALIDATION

### Connection Testing Pattern
```python
from bmlibrarian.database import DatabaseManager

def validate_postgres_connection(host, port, user, password, dbname):
    """Test PostgreSQL connection before creating database."""
    import psycopg
    
    try:
        with psycopg.connect(
            host=host,
            port=int(port),
            user=user,
            password=password,
            dbname=dbname  # Connect to dbname, or 'postgres' for initial check
        ) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT version()")
                version = cur.fetchone()
                return True, version[0]
    except Exception as e:
        return False, str(e)
```

### Schema Application Pattern
```python
def apply_database_schema(db_config):
    """Apply baseline schema and migrations."""
    from pathlib import Path
    
    # 1. Read baseline schema
    schema_file = Path(__file__).parent / "baseline_schema.sql"
    with open(schema_file) as f:
        schema_sql = f.read()
    
    # 2. Apply schema
    from bmlibrarian.database import DatabaseManager
    db = DatabaseManager()
    
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(schema_sql)
        conn.commit()
    
    # 3. Apply migrations
    migrations_dir = Path(__file__).parent / "migrations"
    for migration_file in sorted(migrations_dir.glob("*.sql")):
        with open(migration_file) as f:
            migration_sql = f.read()
        
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(migration_sql)
            conn.commit()
```

---

## 11. CONFIGURATION FILE WRITING

### .env File Writing
```python
def write_env_file(config_dict: dict, output_path: Path):
    """Write configuration to .env file."""
    lines = []
    
    for key, value in config_dict.items():
        # Quote strings containing spaces/special chars
        if isinstance(value, str) and any(c in value for c in ' ='):
            value = f'"{value}"'
        lines.append(f"{key}={value}\n")
    
    output_path.write_text("".join(lines))
    output_path.chmod(0o600)  # Protect file (owner read/write only)
```

### config.json File Writing
```python
import json
from pathlib import Path

def write_config_json(config_dict: dict, output_path: Path = None):
    """Write configuration to config.json."""
    if output_path is None:
        output_path = Path.home() / ".bmlibrarian" / "config.json"
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w') as f:
        json.dump(config_dict, f, indent=2)
    
    output_path.chmod(0o600)  # Protect file
```

---

## 12. GOLDEN RULES FOR SETUP WIZARD

Based on CLAUDE.md requirements:

1. **No magic numbers** - All dimensions from DPI scale system
2. **No hardcoded paths** - Use expanduser(), Path.home()
3. **No inline styles** - Use StylesheetGenerator
4. **Type hints everywhere** - All parameters typed
5. **Docstrings required** - All functions/classes documented
6. **Error handling** - All operations wrapped in try/except with user feedback
7. **Threading** - Long operations (DB, network) in QThread to prevent UI freeze
8. **Validation** - Input validation before any operations
9. **Progress feedback** - Status messages for all operations
10. **Reversibility** - Allow users to go back and change settings

---

## 13. EXAMPLE CONFIGURATION VALUES

### Minimal Setup
```json
{
  "database": {
    "host": "localhost",
    "port": 5432,
    "user": "bmuser",
    "password": "secure_password",
    "name": "knowledgebase"
  },
  "file_system": {
    "pdf_base_dir": "~/knowledgebase/pdf"
  }
}
```

### Full Setup with Imports
```json
{
  "database": {
    "host": "localhost",
    "port": 5432,
    "user": "bmuser",
    "password": "secure_password",
    "name": "knowledgebase"
  },
  "file_system": {
    "pdf_base_dir": "~/knowledgebase/pdf"
  },
  "ncbi": {
    "email": "user@example.com",
    "api_key": "ncbi_api_key_here"
  },
  "ollama": {
    "host": "http://localhost:11434"
  },
  "imports": {
    "medrxiv": {
      "enabled": true,
      "days_to_fetch": 7,
      "download_pdfs": true
    },
    "pubmed": {
      "enabled": true,
      "search_query": "your search query",
      "max_results": 100
    }
  }
}
```

