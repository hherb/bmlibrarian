# BMLibrarian Plugin Developer Manual

**Version:** 1.0
**Last Updated:** 2025-11-19
**Target Audience:** Developers creating plugins for the BMLibrarian Qt GUI

---

## Table of Contents

1. [Introduction](#introduction)
2. [Architecture Overview](#architecture-overview)
3. [Database Access](#database-access)
4. [AI/LLM Integration](#aillm-integration)
5. [Qt GUI Styling System](#qt-gui-styling-system)
6. [Plugin Development Guide](#plugin-development-guide)
7. [Good Programming Practices](#good-programming-practices)
8. [Testing and Validation](#testing-and-validation)
9. [Examples](#examples)

---

## Introduction

BMLibrarian is a comprehensive Python library providing AI-powered access to biomedical literature databases. It features a multi-agent architecture with specialized agents for query processing, document scoring, citation extraction, report generation, and more.

This manual provides guidance for developers creating **plugins** (custom tabs) for the BMLibrarian Qt GUI application built with **PySide6**.

### What is a Plugin?

A plugin in BMLibrarian is a self-contained Qt widget that appears as a tab in the main application. Examples include:
- Research Tab (multi-agent research workflow)
- Fact Checker Tab (statement verification)
- Query Lab Tab (interactive query development)
- PICO Lab Tab (PICO component extraction)
- Document Interrogation Tab (AI-powered document Q&A)

---

## Architecture Overview

### Core Components

BMLibrarian uses a **layered architecture** with clear separation of concerns:

```
┌─────────────────────────────────────────────────────┐
│             Qt GUI Layer (PySide6)                  │
│  Plugins / Tabs / Widgets / Dialogs                │
└─────────────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────┐
│          Multi-Agent System Layer                   │
│  QueryAgent, ScoringAgent, CitationAgent, etc.     │
└─────────────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────┐
│        Data Access Layer (Database + AI)            │
│  DatabaseManager (Postgres) + Ollama Client         │
└─────────────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────┐
│           External Services                         │
│  PostgreSQL Database + Ollama Server                │
└─────────────────────────────────────────────────────┘
```

### Key Design Patterns

1. **Singleton Pattern**: Configuration, DatabaseManager, FontScale
2. **Context Managers**: Database connections with automatic transaction management
3. **Factory Pattern**: Agent creation with parameter filtering
4. **Base Classes**: BaseAgent for all AI agents, standardized interfaces
5. **Font-Relative Scaling**: All GUI dimensions derived from system font metrics

---

## Database Access

### CRITICAL RULE: Always Use DatabaseManager

**NEVER** create direct PostgreSQL connections in your plugin code. **ALWAYS** use the centralized `DatabaseManager` singleton.

### Why Use DatabaseManager?

- **Connection pooling**: Reuses connections efficiently (min 2, max 10 connections)
- **Transaction safety**: Automatic commit/rollback with context managers
- **Source ID caching**: Fast filtering by data source (PubMed, medRxiv, etc.)
- **Lazy singleton**: Global access without re-initialization

### Getting Database Access

```python
from bmlibrarian.database import get_db_manager

# Get the singleton instance
db_manager = get_db_manager()

# Use context manager for automatic transaction management
with db_manager.get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM document WHERE id = %s", (doc_id,))
        result = cur.fetchone()
        # Connection automatically commits on success
        # or rolls back on exception
```

### Key Database Functions

The `database.py` module provides high-level search functions:

```python
from bmlibrarian.database import (
    find_abstracts,           # Full-text search with metadata
    find_abstract_ids,        # Fast ID-only search for multi-query workflows
    fetch_documents_by_ids,   # Bulk fetch by IDs
    search_by_embedding,      # Vector similarity search
    search_hybrid,            # Multi-strategy hybrid search
    get_db_manager            # Get DatabaseManager singleton
)

# Example: Search for documents
for doc in find_abstracts(
    ts_query_str="covid & vaccine",
    max_rows=100,
    use_pubmed=True,
    use_medrxiv=True,
    plain=False  # Use advanced tsquery syntax
):
    print(f"{doc['title']} - {doc['authors']}")
```

### Database Best Practices

1. **Always use context managers** for connections
2. **Use parameterized queries** to prevent SQL injection
3. **Batch operations** when processing many documents
4. **Let exceptions propagate** - rollback is automatic
5. **Don't hold connections** across UI interactions

### Example: Safe Database Query

```python
from bmlibrarian.database import get_db_manager
from psycopg.rows import dict_row
from typing import List, Dict, Any

def get_recent_documents(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Fetch recent documents from the database.

    Args:
        limit: Maximum number of documents to retrieve

    Returns:
        List of document dictionaries
    """
    db_manager = get_db_manager()
    documents = []

    with db_manager.get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            # Use parameterized query for safety
            cur.execute("""
                SELECT id, title, abstract, publication_date
                FROM document
                ORDER BY publication_date DESC
                LIMIT %s
            """, (limit,))

            documents = cur.fetchall()

    return documents
```

---

## AI/LLM Integration

### CRITICAL RULE: Always Inherit from BaseAgent

**NEVER** create direct Ollama client instances in your plugin code. **ALWAYS** inherit from `BaseAgent` or use existing agent classes.

### Why Use BaseAgent?

The `BaseAgent` class provides:
- **Ollama client management**: Single client instance with host configuration
- **Retry logic**: Exponential backoff for transient failures (1s, 2s, 4s...)
- **Error classification**: Distinguishes retryable vs. non-retryable errors
- **JSON parsing**: Robust parsing with markdown code block removal
- **Callback system**: Progress tracking for long-running operations
- **Queue integration**: Task submission for batch processing
- **Structured logging**: Detailed request/response tracking

### Creating a Custom Agent

```python
"""
Custom agent for specialized biomedical literature analysis.
"""

import logging
from typing import Dict, Optional, Callable
from bmlibrarian.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class CustomAnalysisAgent(BaseAgent):
    """
    Agent for custom biomedical document analysis.

    Inherits all Ollama communication and error handling from BaseAgent.
    """

    def __init__(
        self,
        model: str = "gpt-oss:20b",
        host: str = "http://localhost:11434",
        temperature: float = 0.1,
        top_p: float = 0.9,
        callback: Optional[Callable[[str, str], None]] = None,
        orchestrator: Optional["AgentOrchestrator"] = None,
        show_model_info: bool = True
    ):
        """
        Initialize the CustomAnalysisAgent.

        Args:
            model: Ollama model name
            host: Ollama server URL
            temperature: Model temperature (0.0-1.0)
            top_p: Model top-p sampling (0.0-1.0)
            callback: Optional progress callback
            orchestrator: Optional orchestrator for queuing
            show_model_info: Display model info on init
        """
        super().__init__(
            model, host, temperature, top_p,
            callback, orchestrator, show_model_info
        )

        # Define your system prompt
        self.system_prompt = """You are an expert biomedical analyst..."""

    def get_agent_type(self) -> str:
        """Get the agent type identifier."""
        return "custom_analysis_agent"

    def analyze_document(
        self,
        document: Dict,
        analysis_type: str = "comprehensive"
    ) -> Dict:
        """
        Analyze a document using the LLM.

        Args:
            document: Document dictionary with title, abstract, etc.
            analysis_type: Type of analysis to perform

        Returns:
            Analysis results as dictionary

        Raises:
            ConnectionError: If unable to connect to Ollama
            ValueError: If inputs are invalid
        """
        # Validate inputs
        if not document.get('title') or not document.get('abstract'):
            raise ValueError("Document must have title and abstract")

        # Build prompt
        prompt = f"""Analyze this biomedical document:

Title: {document['title']}
Abstract: {document['abstract']}

Analysis type: {analysis_type}

Provide your analysis in JSON format:
{{
    "key_findings": ["finding1", "finding2", ...],
    "methodology": "description",
    "significance": "assessment"
}}"""

        # Use BaseAgent method with automatic retry and JSON parsing
        response = self._generate_and_parse_json(
            prompt=prompt,
            max_retries=3,
            retry_context="document analysis"
        )

        return response
```

### Available BaseAgent Methods

```python
# Chat-based request (conversation with message history)
response = self._make_ollama_request(
    messages=[
        {'role': 'user', 'content': 'What is aspirin?'}
    ],
    system_prompt="You are a medical expert",
    max_retries=3,
    retry_delay=1.0
)

# Simple generation from prompt
response = self._generate_from_prompt(
    prompt="Summarize this abstract: ...",
    max_retries=3
)

# Generate and parse JSON (recommended for structured output)
result = self._generate_and_parse_json(
    prompt="Return JSON with fields: summary, keywords",
    max_retries=3,
    retry_context="summary generation"
)

# Generate embeddings for semantic search
embedding = self._generate_embedding(
    text="What are the cardiovascular benefits of exercise?",
    model="snowflake-arctic-embed2:latest"
)
```

### Using Configuration for Models

**NEVER hardcode model names.** Always use the configuration system:

```python
from bmlibrarian.config import get_config, get_model, get_agent_config

# Get model for specific agent type
model = get_model('custom_agent', default='gpt-oss:20b')

# Get full agent configuration
agent_config = get_agent_config('custom')
temperature = agent_config.get('temperature', 0.1)
top_p = agent_config.get('top_p', 0.9)
max_tokens = agent_config.get('max_tokens', 2000)

# Create agent with config
agent = CustomAnalysisAgent(
    model=model,
    temperature=temperature,
    top_p=top_p
)
```

### Best Practices for AI Integration

1. **Always inherit from BaseAgent** - don't create raw Ollama clients
2. **Use retry methods** - `_generate_and_parse_json()`, `_make_ollama_request()`
3. **Validate inputs** before making LLM requests
4. **Use configuration** for all models and parameters
5. **Provide context in errors** - use `retry_context` parameter
6. **Handle empty responses** - BaseAgent does this automatically
7. **Log agent operations** - BaseAgent provides structured logging

---

## Qt GUI Styling System

### DPI-Aware Font Scaling

BMLibrarian uses a **font-relative scaling system** that ensures UI elements scale properly across all DPI settings (96 DPI, 144 DPI, 4K displays, etc.).

#### The FontScale Singleton

**NEVER use hardcoded pixel values.** Always use the `FontScale` singleton:

```python
from bmlibrarian.gui.qt.resources.styles.dpi_scale import FontScale, get_font_scale

# Get the singleton instance
scale = FontScale()

# Access scale values
font_size = scale['font_medium']      # 12pt (scaled from system font)
padding = scale['padding_large']      # 8px (scaled to DPI)
spacing = scale['spacing_medium']     # 6px (scaled to DPI)
icon_size = scale['icon_medium']      # 24px (scaled to DPI)
control_height = scale['control_height_medium']  # 30px (scaled to DPI)

# Or use the convenience function
scale_dict = get_font_scale()
margin = scale_dict['spacing_large']
```

#### Available Scale Keys

**Font Sizes** (in points, DPI-independent):
- `font_tiny`: 8-9pt (very small text)
- `font_small`: 10pt (slightly smaller)
- `font_normal`: 11pt (system default)
- `font_medium`: 12pt (slightly larger)
- `font_large`: 13pt (headers)
- `font_xlarge`: 15pt (large headers)
- `font_icon`: 18pt (icon labels)

**Spacing** (in pixels, relative to line height):
- `spacing_tiny`: 2-3px
- `spacing_small`: 4-6px
- `spacing_medium`: 6-10px
- `spacing_large`: 8-12px
- `spacing_xlarge`: 12-18px

**Padding** (in pixels, relative to line height):
- `padding_tiny`: 2px
- `padding_small`: 4px
- `padding_medium`: 6px
- `padding_large`: 8px
- `padding_xlarge`: 12px

**Control Heights** (in pixels, relative to line height):
- `control_height_small`: 24px
- `control_height_medium`: 30px
- `control_height_large`: 40px
- `control_height_xlarge`: 50px

**Border Radius** (in pixels, relative to line height):
- `radius_tiny`: 2px
- `radius_small`: 4px
- `radius_medium`: 8px
- `radius_large`: 12px

**Icon Sizes** (in pixels, relative to line height):
- `icon_tiny`: 12px
- `icon_small`: 16px
- `icon_medium`: 24px
- `icon_large`: 32px
- `icon_xlarge`: 48px

### StylesheetGenerator for Consistent Theming

Use `StylesheetGenerator` for creating DPI-aware stylesheets:

```python
from bmlibrarian.gui.qt.resources.styles.stylesheet_generator import StylesheetGenerator

# Create generator
generator = StylesheetGenerator()

# Generate button stylesheet
button_style = generator.button_stylesheet(
    bg_color="#2196F3",
    text_color="white",
    hover_color="#1976D2",
    font_size_key='font_medium',
    padding_key='padding_small',
    radius_key='radius_small'
)
self.my_button.setStyleSheet(button_style)

# Generate input stylesheet
input_style = generator.input_stylesheet(
    font_size_key='font_medium',
    padding_key='padding_small',
    radius_key='radius_small'
)
self.text_edit.setStyleSheet(input_style)

# Generate label stylesheet
label_style = generator.label_stylesheet(
    font_size_key='font_large',
    color="#333",
    bold=True
)
self.header_label.setStyleSheet(label_style)
```

### Example: Creating a Scaled Widget

```python
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel
from PySide6.QtCore import Qt
from bmlibrarian.gui.qt.resources.styles.dpi_scale import FontScale
from bmlibrarian.gui.qt.resources.styles.stylesheet_generator import StylesheetGenerator


class CustomPluginWidget(QWidget):
    """Custom plugin widget with proper DPI scaling."""

    def __init__(self, parent=None):
        super().__init__(parent)

        # Get scale values
        self.scale = FontScale()
        self.stylesheet_gen = StylesheetGenerator()

        self._setup_ui()

    def _setup_ui(self):
        """Initialize UI with scaled dimensions."""
        layout = QVBoxLayout(self)

        # Use scaled spacing
        layout.setSpacing(self.scale['spacing_medium'])
        layout.setContentsMargins(
            self.scale['padding_large'],
            self.scale['padding_large'],
            self.scale['padding_large'],
            self.scale['padding_large']
        )

        # Create header label with scaled font
        header = QLabel("Custom Plugin")
        header.setStyleSheet(self.stylesheet_gen.label_stylesheet(
            font_size_key='font_xlarge',
            color="#2C3E50",
            bold=True
        ))
        layout.addWidget(header)

        # Create button with scaled dimensions
        action_button = QPushButton("Analyze Documents")
        action_button.setFixedHeight(self.scale['control_height_medium'])
        action_button.setStyleSheet(self.stylesheet_gen.button_stylesheet(
            bg_color="#27AE60",
            text_color="white",
            hover_color="#229954"
        ))
        layout.addWidget(action_button)
```

### Color Constants

Use centralized color constants for consistency:

```python
from bmlibrarian.gui.qt.resources.styles.constants import (
    PDF_BUTTON_VIEW_COLOR,      # "#2196F3" (blue)
    PDF_BUTTON_FETCH_COLOR,     # "#FF9800" (orange)
    PDF_BUTTON_UPLOAD_COLOR,    # "#4CAF50" (green)
    SCORE_COLOR_HIGH,           # "#4CAF50" (green)
    SCORE_COLOR_MEDIUM,         # "#FF9800" (orange)
    SCORE_COLOR_LOW             # "#F44336" (red)
)
```

---

## Plugin Development Guide

### Plugin Structure

A BMLibrarian plugin is a Qt widget that implements a standard interface:

```
src/bmlibrarian/gui/qt/plugins/
└── my_custom_plugin/
    ├── __init__.py              # Plugin exports
    ├── my_plugin_tab.py         # Main tab widget
    ├── widgets/                 # Custom widgets
    │   ├── __init__.py
    │   ├── analysis_widget.py
    │   └── results_widget.py
    └── README.md                # Plugin documentation
```

### Minimal Plugin Template

```python
"""
Custom Plugin for BMLibrarian Qt GUI.

Provides [description of functionality].
"""

import logging
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel
from PySide6.QtCore import Signal

from bmlibrarian.gui.qt.resources.styles.dpi_scale import FontScale
from bmlibrarian.gui.qt.resources.styles.stylesheet_generator import StylesheetGenerator
from bmlibrarian.database import get_db_manager, find_abstracts
from bmlibrarian.config import get_config, get_model

logger = logging.getLogger(__name__)


class MyCustomPluginTab(QWidget):
    """
    Main tab widget for Custom Plugin.

    Signals:
        status_message: Emitted with status text for main window status bar
    """

    # Qt Signal for status updates
    status_message = Signal(str)

    def __init__(self, parent=None):
        """
        Initialize the custom plugin tab.

        Args:
            parent: Parent widget (usually the main window)
        """
        super().__init__(parent)

        # Get styling utilities
        self.scale = FontScale()
        self.stylesheet_gen = StylesheetGenerator()

        # Get configuration
        self.config = get_config()

        # Initialize database access
        self.db_manager = get_db_manager()

        # Set up the UI
        self._setup_ui()

        logger.info("Custom Plugin initialized")

    def _setup_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)
        layout.setSpacing(self.scale['spacing_medium'])
        layout.setContentsMargins(
            self.scale['padding_large'],
            self.scale['padding_large'],
            self.scale['padding_large'],
            self.scale['padding_large']
        )

        # Header
        header = QLabel("Custom Plugin")
        header.setStyleSheet(self.stylesheet_gen.label_stylesheet(
            font_size_key='font_xlarge',
            bold=True
        ))
        layout.addWidget(header)

        # Action button
        self.action_button = QPushButton("Run Analysis")
        self.action_button.setFixedHeight(self.scale['control_height_medium'])
        self.action_button.setStyleSheet(self.stylesheet_gen.button_stylesheet())
        self.action_button.clicked.connect(self._on_action_clicked)
        layout.addWidget(self.action_button)

        # Stretch to push content to top
        layout.addStretch()

    def _on_action_clicked(self):
        """Handle action button click."""
        try:
            self.status_message.emit("Starting analysis...")

            # Your plugin logic here
            # Example: Search database
            documents = list(find_abstracts(
                ts_query_str="aspirin & cardiovascular",
                max_rows=10
            ))

            self.status_message.emit(f"Found {len(documents)} documents")
            logger.info(f"Analysis complete: {len(documents)} documents")

        except Exception as e:
            error_msg = f"Analysis failed: {e}"
            self.status_message.emit(error_msg)
            logger.error(error_msg, exc_info=True)


# Plugin metadata for registration
PLUGIN_NAME = "Custom Plugin"
PLUGIN_TAB_CLASS = MyCustomPluginTab
PLUGIN_DESCRIPTION = "Custom analysis plugin for biomedical literature"
```

### Registering Your Plugin

Add your plugin to the main application in `src/bmlibrarian/gui/qt/core/application.py`:

```python
# Import your plugin
from bmlibrarian.gui.qt.plugins.my_custom_plugin import MyCustomPluginTab

# In the _setup_tabs() method, add:
custom_tab = MyCustomPluginTab(self)
custom_tab.status_message.connect(self._update_status)
self.tabs.addTab(custom_tab, "Custom Plugin")
```

### Plugin Best Practices

1. **Inherit from QWidget** for tab widgets
2. **Use Signal/Slot pattern** for event communication
3. **Emit status_message** signal for status bar updates
4. **Handle errors gracefully** with try/except and user feedback
5. **Use logger** for debugging and audit trail
6. **Follow DPI scaling** guidelines for all dimensions
7. **Test on multiple DPIs** (96, 144, 192 DPI displays)

---

## Good Programming Practices

### 1. Type Hints (MANDATORY)

**Always use type hints** for function signatures and class attributes:

```python
from typing import Dict, List, Optional, Tuple, Any, Callable
from datetime import date

def analyze_documents(
    documents: List[Dict[str, Any]],
    min_score: float = 0.7,
    callback: Optional[Callable[[int, int], None]] = None
) -> Tuple[List[Dict], Dict[str, float]]:
    """
    Analyze documents and return scored results.

    Args:
        documents: List of document dictionaries
        min_score: Minimum relevance score (0.0-1.0)
        callback: Optional progress callback (current, total)

    Returns:
        Tuple of (scored_documents, statistics)
    """
    scored_docs: List[Dict] = []
    stats: Dict[str, float] = {
        'mean_score': 0.0,
        'max_score': 0.0
    }

    # Implementation...
    return scored_docs, stats
```

### 2. Docstrings (MANDATORY)

Use **Google-style docstrings** for all public functions and classes:

```python
def search_literature(
    query: str,
    max_results: int = 100,
    include_preprints: bool = True
) -> List[Dict[str, Any]]:
    """
    Search biomedical literature databases.

    Performs full-text search across PubMed and medRxiv databases
    using PostgreSQL text search with optional preprint filtering.

    Args:
        query: Natural language search query
        max_results: Maximum number of results to return (default: 100)
        include_preprints: Include medRxiv preprints (default: True)

    Returns:
        List of document dictionaries with keys:
        - id: Document ID
        - title: Document title
        - abstract: Document abstract
        - publication_date: Publication date (ISO format)

    Raises:
        ValueError: If query is empty or max_results <= 0
        ConnectionError: If database is unavailable

    Examples:
        >>> docs = search_literature("COVID-19 vaccine", max_results=10)
        >>> print(f"Found {len(docs)} documents")
        Found 10 documents

    Note:
        Results are ordered by publication date (newest first).
    """
    # Implementation...
```

### 3. No Magic Numbers (MANDATORY)

**Never use hardcoded numbers.** Define constants or use configuration:

```python
# BAD - Magic numbers
if score > 0.7:
    documents = documents[:50]

# GOOD - Named constants
MIN_RELEVANCE_THRESHOLD = 0.7
DEFAULT_MAX_DOCUMENTS = 50

if score > MIN_RELEVANCE_THRESHOLD:
    documents = documents[:DEFAULT_MAX_DOCUMENTS]

# BETTER - Use configuration
from bmlibrarian.config import get_agent_config

config = get_agent_config('scoring')
min_relevance = config.get('min_relevance', 0.7)
max_docs = config.get('max_documents', 50)

if score > min_relevance:
    documents = documents[:max_docs]
```

### 4. Configuration-Based Design

**All tunable parameters must be in configuration:**

```python
# Define defaults in config.py
DEFAULT_CONFIG = {
    "agents": {
        "custom_agent": {
            "temperature": 0.1,
            "top_p": 0.9,
            "max_tokens": 2000,
            "min_confidence": 0.7,
            "batch_size": 50
        }
    }
}

# Use in your plugin
from bmlibrarian.config import get_agent_config

config = get_agent_config('custom_agent')
temperature = config.get('temperature', 0.1)
batch_size = config.get('batch_size', 50)
```

### 5. Logging (MANDATORY)

Use Python's logging module, **never print()**:

```python
import logging

logger = logging.getLogger(__name__)

def process_documents(documents: List[Dict]) -> List[Dict]:
    """Process documents with comprehensive logging."""
    logger.info(f"Starting document processing: {len(documents)} documents")

    processed = []
    for i, doc in enumerate(documents):
        try:
            result = analyze_document(doc)
            processed.append(result)
            logger.debug(f"Processed document {i+1}/{len(documents)}: {doc['title']}")
        except Exception as e:
            logger.error(f"Failed to process document {doc.get('id', 'unknown')}: {e}", exc_info=True)
            # Don't re-raise - continue processing

    logger.info(f"Document processing complete: {len(processed)}/{len(documents)} successful")
    return processed
```

### 6. Error Handling

**Always handle errors gracefully:**

```python
from PySide6.QtWidgets import QMessageBox

def perform_analysis(self):
    """Perform analysis with proper error handling."""
    try:
        # Input validation
        if not self.query_input.text().strip():
            QMessageBox.warning(
                self,
                "Invalid Input",
                "Please enter a search query"
            )
            return

        # Perform operation
        self.status_message.emit("Running analysis...")
        results = self._run_analysis()

        # Success feedback
        self.status_message.emit(f"Analysis complete: {len(results)} results")

    except ConnectionError as e:
        logger.error(f"Connection error: {e}")
        QMessageBox.critical(
            self,
            "Connection Error",
            f"Cannot connect to database or Ollama server:\n{e}"
        )
        self.status_message.emit("Analysis failed: connection error")

    except ValueError as e:
        logger.error(f"Invalid data: {e}")
        QMessageBox.warning(
            self,
            "Invalid Data",
            f"Invalid input or configuration:\n{e}"
        )
        self.status_message.emit("Analysis failed: invalid data")

    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        QMessageBox.critical(
            self,
            "Error",
            f"An unexpected error occurred:\n{e}\n\nCheck logs for details."
        )
        self.status_message.emit("Analysis failed")
```

### 7. Code Organization

```python
"""
Module-level docstring describing purpose.
"""

# Standard library imports
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

# Third-party imports
from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtCore import Signal

# BMLibrarian imports
from bmlibrarian.config import get_config
from bmlibrarian.database import get_db_manager
from bmlibrarian.agents.base import BaseAgent
from bmlibrarian.gui.qt.resources.styles.dpi_scale import FontScale

# Module-level constants
DEFAULT_BATCH_SIZE = 50
MIN_CONFIDENCE_THRESHOLD = 0.7

# Module-level logger
logger = logging.getLogger(__name__)


class MyCustomAgent(BaseAgent):
    """Class definition with docstring."""

    def __init__(self, ...):
        """Constructor docstring."""
        # Implementation

    def public_method(self, ...) -> ReturnType:
        """Public method with full docstring."""
        # Implementation

    def _private_method(self, ...) -> ReturnType:
        """Private method (still needs docstring)."""
        # Implementation
```

---

## Testing and Validation

### Unit Testing

Create tests in `tests/` directory:

```python
"""
Unit tests for Custom Analysis Agent.
"""

import unittest
from unittest.mock import Mock, patch
from bmlibrarian.agents.custom_agent import CustomAnalysisAgent


class TestCustomAnalysisAgent(unittest.TestCase):
    """Test suite for CustomAnalysisAgent."""

    def setUp(self):
        """Set up test fixtures."""
        self.agent = CustomAnalysisAgent(
            model="gpt-oss:20b",
            temperature=0.1,
            show_model_info=False
        )

    def test_agent_initialization(self):
        """Test agent initializes correctly."""
        self.assertEqual(self.agent.model, "gpt-oss:20b")
        self.assertEqual(self.agent.temperature, 0.1)
        self.assertEqual(self.agent.get_agent_type(), "custom_analysis_agent")

    @patch('bmlibrarian.agents.base.BaseAgent._generate_and_parse_json')
    def test_analyze_document(self, mock_generate):
        """Test document analysis."""
        # Mock LLM response
        mock_generate.return_value = {
            'key_findings': ['Finding 1', 'Finding 2'],
            'significance': 'High'
        }

        # Test document
        doc = {
            'title': 'Test Study',
            'abstract': 'This is a test abstract.'
        }

        # Run analysis
        result = self.agent.analyze_document(doc)

        # Verify results
        self.assertIn('key_findings', result)
        self.assertEqual(len(result['key_findings']), 2)
        self.assertEqual(result['significance'], 'High')

    def test_invalid_document(self):
        """Test error handling for invalid documents."""
        with self.assertRaises(ValueError):
            self.agent.analyze_document({})  # Missing title/abstract


if __name__ == '__main__':
    unittest.main()
```

### Manual Testing Checklist

- [ ] Test on **96 DPI** display (standard 1920x1080)
- [ ] Test on **144 DPI** display (2K displays)
- [ ] Test on **192+ DPI** display (4K displays)
- [ ] Test with **different system fonts** (Windows/Linux/macOS)
- [ ] Test **database connection failure** scenarios
- [ ] Test **Ollama unavailable** scenarios
- [ ] Test with **empty query results**
- [ ] Test with **very large datasets** (1000+ documents)
- [ ] Test **memory usage** during long-running operations

---

## Examples

### Example 1: Simple Search Plugin

```python
"""
Simple document search plugin.
"""

import logging
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QTextEdit, QLabel
)
from PySide6.QtCore import Signal, Qt

from bmlibrarian.gui.qt.resources.styles.dpi_scale import FontScale
from bmlibrarian.gui.qt.resources.styles.stylesheet_generator import StylesheetGenerator
from bmlibrarian.database import find_abstracts

logger = logging.getLogger(__name__)


class SimpleSearchTab(QWidget):
    """Simple document search interface."""

    status_message = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scale = FontScale()
        self.stylesheet_gen = StylesheetGenerator()
        self._setup_ui()

    def _setup_ui(self):
        """Initialize UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(self.scale['spacing_medium'])

        # Search input
        search_layout = QHBoxLayout()
        search_layout.setSpacing(self.scale['spacing_small'])

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter search query...")
        self.search_input.setFixedHeight(self.scale['control_height_medium'])
        self.search_input.setStyleSheet(self.stylesheet_gen.input_stylesheet())
        search_layout.addWidget(self.search_input)

        search_button = QPushButton("Search")
        search_button.setFixedHeight(self.scale['control_height_medium'])
        search_button.setStyleSheet(self.stylesheet_gen.button_stylesheet())
        search_button.clicked.connect(self._perform_search)
        search_layout.addWidget(search_button)

        layout.addLayout(search_layout)

        # Results display
        self.results_display = QTextEdit()
        self.results_display.setReadOnly(True)
        self.results_display.setStyleSheet(self.stylesheet_gen.input_stylesheet())
        layout.addWidget(self.results_display)

    def _perform_search(self):
        """Perform database search."""
        query = self.search_input.text().strip()

        if not query:
            self.status_message.emit("Please enter a search query")
            return

        try:
            self.status_message.emit(f"Searching for: {query}")

            # Search database
            documents = list(find_abstracts(
                ts_query_str=query,
                max_rows=20,
                plain=True
            ))

            # Display results
            result_text = f"Found {len(documents)} documents:\n\n"
            for i, doc in enumerate(documents, 1):
                result_text += f"{i}. {doc['title']}\n"
                result_text += f"   Authors: {', '.join(doc['authors'][:3])}\n"
                result_text += f"   Date: {doc['publication_date']}\n\n"

            self.results_display.setPlainText(result_text)
            self.status_message.emit(f"Found {len(documents)} documents")

        except Exception as e:
            logger.error(f"Search failed: {e}", exc_info=True)
            self.status_message.emit(f"Search failed: {e}")
            self.results_display.setPlainText(f"Error: {e}")
```

### Example 2: AI-Powered Analysis Plugin

```python
"""
AI-powered document analysis plugin.
"""

import logging
from typing import Dict, List
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton,
    QTextEdit, QProgressBar, QLabel
)
from PySide6.QtCore import Signal, QThread

from bmlibrarian.gui.qt.resources.styles.dpi_scale import FontScale
from bmlibrarian.gui.qt.resources.styles.stylesheet_generator import StylesheetGenerator
from bmlibrarian.database import find_abstracts
from bmlibrarian.config import get_model, get_agent_config
from bmlibrarian.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class AnalysisWorker(QThread):
    """Background worker for AI analysis."""

    finished = Signal(list)
    progress = Signal(int, int)
    error = Signal(str)

    def __init__(self, documents: List[Dict], agent: BaseAgent):
        super().__init__()
        self.documents = documents
        self.agent = agent

    def run(self):
        """Run analysis in background thread."""
        try:
            results = []
            total = len(self.documents)

            for i, doc in enumerate(self.documents):
                # Perform AI analysis
                result = self.agent.analyze_document(doc)
                results.append(result)

                # Emit progress
                self.progress.emit(i + 1, total)

            self.finished.emit(results)

        except Exception as e:
            logger.error(f"Analysis failed: {e}", exc_info=True)
            self.error.emit(str(e))


class AIAnalysisTab(QWidget):
    """AI-powered analysis interface."""

    status_message = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scale = FontScale()
        self.stylesheet_gen = StylesheetGenerator()

        # Initialize agent
        model = get_model('custom_agent', default='gpt-oss:20b')
        config = get_agent_config('custom')
        self.agent = CustomAnalysisAgent(
            model=model,
            temperature=config.get('temperature', 0.1),
            top_p=config.get('top_p', 0.9)
        )

        self.worker = None
        self._setup_ui()

    def _setup_ui(self):
        """Initialize UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(self.scale['spacing_medium'])

        # Start button
        self.start_button = QPushButton("Start Analysis")
        self.start_button.setFixedHeight(self.scale['control_height_medium'])
        self.start_button.setStyleSheet(self.stylesheet_gen.button_stylesheet())
        self.start_button.clicked.connect(self._start_analysis)
        layout.addWidget(self.start_button)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(self.scale['control_height_small'])
        layout.addWidget(self.progress_bar)

        # Results display
        self.results_display = QTextEdit()
        self.results_display.setReadOnly(True)
        self.results_display.setStyleSheet(self.stylesheet_gen.input_stylesheet())
        layout.addWidget(self.results_display)

    def _start_analysis(self):
        """Start AI analysis in background."""
        try:
            # Fetch documents
            self.status_message.emit("Fetching documents...")
            documents = list(find_abstracts(
                ts_query_str="cardiovascular disease",
                max_rows=10
            ))

            if not documents:
                self.status_message.emit("No documents found")
                return

            # Start background analysis
            self.start_button.setEnabled(False)
            self.worker = AnalysisWorker(documents, self.agent)
            self.worker.progress.connect(self._update_progress)
            self.worker.finished.connect(self._analysis_complete)
            self.worker.error.connect(self._analysis_error)
            self.worker.start()

            self.status_message.emit(f"Analyzing {len(documents)} documents...")

        except Exception as e:
            logger.error(f"Failed to start analysis: {e}", exc_info=True)
            self.status_message.emit(f"Error: {e}")

    def _update_progress(self, current: int, total: int):
        """Update progress bar."""
        percentage = int((current / total) * 100)
        self.progress_bar.setValue(percentage)
        self.status_message.emit(f"Analyzing {current}/{total} documents...")

    def _analysis_complete(self, results: List[Dict]):
        """Handle analysis completion."""
        self.start_button.setEnabled(True)
        self.progress_bar.setValue(100)

        # Display results
        result_text = f"Analysis complete: {len(results)} documents analyzed\n\n"
        for i, result in enumerate(results, 1):
            result_text += f"{i}. Key findings: {', '.join(result['key_findings'])}\n"

        self.results_display.setPlainText(result_text)
        self.status_message.emit("Analysis complete")

    def _analysis_error(self, error_msg: str):
        """Handle analysis error."""
        self.start_button.setEnabled(True)
        self.progress_bar.setValue(0)
        self.status_message.emit(f"Analysis failed: {error_msg}")
        self.results_display.setPlainText(f"Error: {error_msg}")
```

---

## Summary

### Key Takeaways

1. **Database Access**: Always use `DatabaseManager` singleton, never direct connections
2. **AI Integration**: Always inherit from `BaseAgent`, never create raw Ollama clients
3. **GUI Styling**: Always use `FontScale` and `StylesheetGenerator`, never hardcoded pixels
4. **Configuration**: All parameters in `config.json`, accessed via `get_config()`
5. **Type Hints**: Mandatory for all functions and class attributes
6. **Docstrings**: Google-style docstrings for all public APIs
7. **No Magic Numbers**: Use named constants or configuration
8. **Logging**: Use `logger`, never `print()`
9. **Error Handling**: Graceful error handling with user feedback
10. **Testing**: Unit tests + manual testing on multiple DPI settings

### Next Steps

1. Review existing plugins in `src/bmlibrarian/gui/qt/plugins/`
2. Study `BaseAgent` implementation in `src/bmlibrarian/agents/base.py`
3. Examine `DatabaseManager` in `src/bmlibrarian/database.py`
4. Review font scaling in `src/bmlibrarian/gui/qt/resources/styles/dpi_scale.py`
5. Create a minimal plugin following the template
6. Test on multiple DPI displays
7. Add comprehensive unit tests

### Support and Resources

- **Project Documentation**: `README.md`, `SETUP_GUIDE.md`
- **Architecture Analysis**: `bmlibrarian_architecture_analysis.md`
- **Quick Reference**: `bmlibrarian_quick_reference.md`
- **Example Plugins**: `src/bmlibrarian/gui/qt/plugins/`
- **Issue Tracker**: GitHub issues

---

**Document Version:** 1.0
**Last Updated:** 2025-11-19
**Maintainer:** BMLibrarian Development Team
