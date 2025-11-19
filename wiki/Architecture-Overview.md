# BMLibrarian Architecture Overview

**Comprehensive guide to BMLibrarian's system design and components**

## Table of Contents

1. [System Architecture](#system-architecture)
2. [Core Components](#core-components)
3. [Multi-Agent System](#multi-agent-system)
4. [Database Layer](#database-layer)
5. [Qt GUI Architecture](#qt-gui-architecture)
6. [Data Flow](#data-flow)
7. [Design Patterns](#design-patterns)

## System Architecture

BMLibrarian uses a **layered architecture** with clear separation of concerns:

```
┌─────────────────────────────────────────────────────┐
│             User Interface Layer                     │
│  Qt GUI (PySide6) / CLI / Python API                │
└─────────────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────┐
│          Multi-Agent Orchestration Layer            │
│  QueryAgent, ScoringAgent, CitationAgent, etc.      │
└─────────────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────┐
│        Data Access & AI Integration Layer           │
│  DatabaseManager + BaseAgent + Ollama Client        │
└─────────────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────┐
│           External Services Layer                   │
│  PostgreSQL + pgvector + Ollama Server              │
└─────────────────────────────────────────────────────┘
```

### Layer Responsibilities

1. **User Interface Layer**: Provides multiple interfaces (GUI, CLI, API) for user interaction
2. **Multi-Agent Orchestration Layer**: Coordinates specialized AI agents for research tasks
3. **Data Access & AI Integration Layer**: Manages database connections and LLM communication
4. **External Services Layer**: PostgreSQL database and Ollama server for LLM inference

## Core Components

### 1. Configuration System (`config.py`)

Centralized configuration management:

```python
from bmlibrarian.config import get_config, get_model, get_agent_config

# Load configuration
config = get_config()

# Get model for specific agent
model = get_model('query_agent', default='medgemma4B_it_q8:latest')

# Get agent-specific configuration
agent_config = get_agent_config('scoring')
```

**Configuration Files:**
- `~/.bmlibrarian/config.json` - Main configuration
- `~/.bmlibrarian/gui_config.json` - GUI-specific settings
- `.env` - Environment variables (database credentials)

### 2. Database Manager (`database.py`)

Singleton pattern for database access with connection pooling:

```python
from bmlibrarian.database import get_db_manager, find_abstracts

# Get singleton instance
db_manager = get_db_manager()

# Connection pooling (min 2, max 10 connections)
with db_manager.get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM document WHERE id = %s", (doc_id,))
        result = cur.fetchone()
```

**Key Features:**
- Connection pooling for efficiency
- Automatic transaction management
- Source ID caching (PubMed, medRxiv)
- Context manager support for safety

### 3. BaseAgent (`agents/base.py`)

Foundation class for all AI agents:

```python
from bmlibrarian.agents.base import BaseAgent

class CustomAgent(BaseAgent):
    def get_agent_type(self) -> str:
        return "custom_agent"

    def process(self, data):
        # Use BaseAgent methods
        response = self._generate_and_parse_json(
            prompt=self.build_prompt(data),
            max_retries=3,
            retry_context="custom processing"
        )
        return response
```

**BaseAgent Features:**
- Ollama client management
- Exponential backoff retry logic
- JSON parsing with error handling
- Progress callback system
- Queue integration
- Structured logging

## Multi-Agent System

BMLibrarian uses specialized AI agents for different research tasks:

### Agent Types

1. **QueryAgent** (`agents/query_agent.py`)
   - Converts natural language questions to PostgreSQL queries
   - Supports multi-model query generation
   - Tracks query performance

2. **DocumentScoringAgent** (`agents/scoring_agent.py`)
   - Scores document relevance (1-5 scale)
   - Batch processing with progress tracking
   - Configurable relevance thresholds

3. **CitationFinderAgent** (`agents/citation_agent.py`)
   - Extracts relevant passages from documents
   - Generates citation cards with evidence
   - Validates document IDs (prevents hallucination)

4. **ReportingAgent** (`agents/reporting_agent.py`)
   - Synthesizes citations into medical reports
   - Formats in markdown with proper references
   - Temporal precision (specific years, not "recent")

5. **CounterfactualAgent** (`agents/counterfactual_agent.py`)
   - Generates research questions for contradictory evidence
   - Searches for alternative viewpoints
   - Balances evidence in reports

6. **EditorAgent** (`agents/editor_agent.py`)
   - Creates comprehensive reports
   - Integrates all evidence types
   - Ensures balanced analysis

7. **FactCheckerAgent** (`factchecker/agent/fact_checker_agent.py`)
   - Evaluates biomedical statements (yes/no/maybe)
   - Extracts supporting/contradicting citations
   - Confidence assessment (high/medium/low)

8. **PICOAgent** (`agents/pico_agent.py`)
   - Extracts PICO components from research papers
   - Population, Intervention, Comparison, Outcome
   - For systematic reviews

9. **StudyAssessmentAgent** (`agents/study_assessment_agent.py`)
   - Evaluates research quality and bias risk
   - Assesses methodological rigor
   - Trustworthiness scoring

### Agent Orchestration

Agents work together through the **AgentOrchestrator** (`agents/orchestrator.py`):

```python
from bmlibrarian.agents import AgentOrchestrator

# Initialize orchestrator
orchestrator = AgentOrchestrator(max_workers=4)

# Agents can submit tasks to queue
task_id = orchestrator.submit_task(
    agent=query_agent,
    task_type="query_processing",
    data={"question": "What are the benefits of exercise?"}
)

# Monitor task status
status = orchestrator.get_task_status(task_id)
```

### Queue System

SQLite-based task queue for batch processing (`agents/queue_manager.py`):

- **Task Priorities**: HIGH, NORMAL, LOW
- **Persistent Storage**: Tasks survive application restart
- **Progress Tracking**: Monitor task completion
- **Memory Efficient**: Process large document sets without loading all into memory

## Database Layer

### PostgreSQL Schema

BMLibrarian uses PostgreSQL with the following schema:

**Main Tables:**
- `document` - Document metadata (title, abstract, authors, etc.)
- `abstract_embedding` - Vector embeddings for semantic search
- `source` - Data sources (PubMed, medRxiv)
- `document_file` - PDF file associations

**Fact Checker Schema:**
- `factcheck.statement` - Biomedical statements to verify
- `factcheck.evaluation` - AI evaluations
- `factcheck.citation` - Supporting/contradicting citations
- `factcheck.annotation` - Human annotations
- `factcheck.annotator` - Reviewer metadata

**Audit Schema:**
- `audit.research_session` - Research workflow sessions
- `audit.query_execution` - Query performance tracking
- `audit.model_performance` - Model comparison statistics

### Search Functions

PostgreSQL functions for full-text search:

```sql
-- Full-text search with ranking
SELECT * FROM find_abstracts(
    ts_query_str := 'covid & vaccine',
    max_rows := 100,
    use_pubmed := true,
    use_medrxiv := true,
    plain := false
);

-- Vector similarity search
SELECT * FROM search_by_embedding(
    embedding := '[0.1, 0.2, ...]'::vector,
    max_results := 100,
    use_pubmed := true
);
```

### Database Access Patterns

**Pattern 1: Simple Query**
```python
from bmlibrarian.database import find_abstracts

documents = list(find_abstracts(
    ts_query_str="aspirin & cardiovascular",
    max_rows=100
))
```

**Pattern 2: Multi-Model Query**
```python
from bmlibrarian.agents.query_generation import MultiModelQueryGenerator

generator = MultiModelQueryGenerator(models=["model1", "model2"])
result = generator.generate_queries(
    user_question="What are the benefits of exercise?",
    queries_per_model=2
)

# Automatically de-duplicates document IDs
all_documents = result.all_documents
```

**Pattern 3: Batch Processing**
```python
from bmlibrarian.database import fetch_documents_by_ids

# Fast ID-only search
doc_ids = [1, 2, 3, ...]

# Bulk fetch documents
documents = fetch_documents_by_ids(doc_ids)
```

## Qt GUI Architecture

### Plugin-Based Architecture

The Qt GUI uses a **plugin system** where each tab is a separate plugin:

```
src/bmlibrarian/gui/qt/
├── core/                   # Core GUI infrastructure
│   ├── application.py      # Main application window
│   ├── tab_registry.py     # Plugin registry
│   ├── config_manager.py   # GUI configuration
│   └── event_bus.py        # Inter-plugin communication
├── plugins/                # Plugin implementations
│   ├── base_tab.py         # Abstract base class
│   ├── research/           # Research workflow plugin
│   ├── configuration/      # Settings plugin
│   ├── query_lab/          # Query development plugin
│   ├── pico_lab/           # PICO extraction plugin
│   └── document_interrogation/  # Document Q&A plugin
├── widgets/                # Reusable UI components
│   ├── document_card.py    # Document display cards
│   ├── markdown_viewer.py  # Markdown rendering
│   └── progress_widget.py  # Progress indicators
└── resources/              # Styles and assets
    └── styles/
        ├── dpi_scale.py    # DPI-aware scaling
        └── stylesheet_generator.py  # Style generation
```

### Plugin Lifecycle

```python
# 1. Discovery: Plugin manager scans plugins/ directory
plugins = plugin_manager.discover_plugins()

# 2. Loading: Calls create_plugin() in each plugin.py
plugin = create_plugin()

# 3. Registration: Adds to registry
tab_registry.register(plugin)

# 4. Widget Creation: Creates tab widget
widget = plugin.create_widget(parent=main_window)

# 5. Tab Addition: Adds to QTabWidget
tab_widget.addTab(widget, plugin.get_metadata().display_name)

# 6. Activation: When user clicks tab
plugin.on_tab_activated()

# 7. Deactivation: When user leaves tab
plugin.on_tab_deactivated()

# 8. Cleanup: When application closes
plugin.cleanup()
```

### DPI-Aware Styling

All UI dimensions use **font-relative scaling**:

```python
from bmlibrarian.gui.qt.resources.styles.dpi_scale import FontScale

scale = FontScale()

# All dimensions scale with system font and DPI
button.setFixedHeight(scale['control_height_medium'])  # 30px scaled
layout.setSpacing(scale['spacing_medium'])  # 6-10px scaled
label.setStyleSheet(f"font-size: {scale['font_large']}pt;")  # 13pt
```

## Data Flow

### Research Workflow

```
User Question
    ↓
QueryAgent (natural language → SQL query)
    ↓
Database Search (PostgreSQL full-text search)
    ↓
DocumentScoringAgent (relevance scoring 1-5)
    ↓
High-Scoring Documents (threshold: 2.5+)
    ↓
CitationFinderAgent (extract relevant passages)
    ↓
Citations with Evidence
    ↓
ReportingAgent (synthesize citations → report)
    ↓
Optional: CounterfactualAgent (find contradictory evidence)
    ↓
Optional: EditorAgent (comprehensive balanced report)
    ↓
Final Report (Markdown with references)
```

### Fact Checker Workflow

```
Biomedical Statement
    ↓
QueryAgent (statement → search query)
    ↓
Database Search
    ↓
DocumentScoringAgent (relevance scoring)
    ↓
CitationFinderAgent (extract supporting/contradicting passages)
    ↓
FactCheckerAgent (evaluate: yes/no/maybe)
    ↓
Confidence Assessment (high/medium/low)
    ↓
Result Storage (SQLite/PostgreSQL)
    ↓
Human Review (GUI with blind mode)
    ↓
Annotated Dataset (for training data validation)
```

### Multi-Model Query Generation

```
User Question
    ↓
MultiModelQueryGenerator
    ↓
┌──────────────┬──────────────┬──────────────┐
Model 1        Model 2        Model 3
(1-3 queries)  (1-3 queries)  (1-3 queries)
    ↓              ↓              ↓
Query De-duplication
    ↓
┌──────────────┬──────────────┬──────────────┐
Search DB      Search DB      Search DB
Query 1        Query 2        Query N
    ↓              ↓              ↓
Document ID De-duplication
    ↓
Bulk Fetch Documents by IDs
    ↓
Combined Result Set (20-40% more relevant documents)
```

## Design Patterns

### 1. Singleton Pattern

**Used in**: DatabaseManager, FontScale, EventBus

```python
class DatabaseManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            # Initialize once
        return cls._instance
```

### 2. Factory Pattern

**Used in**: Document card creation, agent initialization

```python
class DocumentCardFactory:
    def create_card(self, data: DocumentCardData, context: CardContext):
        if context == CardContext.LITERATURE:
            return self._create_literature_card(data)
        elif context == CardContext.SCORING:
            return self._create_scoring_card(data)
        # ...
```

### 3. Context Manager Pattern

**Used in**: Database connections, transaction management

```python
with db_manager.get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT ...")
        # Automatic commit on success, rollback on exception
```

### 4. Observer Pattern (Signals/Slots)

**Used in**: Inter-plugin communication, event handling

```python
# Plugin emits signal
self.data_updated.emit({"source": "search", "documents": docs})

# Other plugin listens
event_bus.data_shared.connect(self._on_data_received)
```

### 5. Template Method Pattern

**Used in**: BaseAgent, BaseTabPlugin

```python
class BaseAgent:
    def process(self, data):
        # Template method
        validated_data = self.validate(data)
        prompt = self.build_prompt(validated_data)
        response = self._make_ollama_request(prompt)
        return self.parse_response(response)

    # Subclasses override these
    def validate(self, data): ...
    def build_prompt(self, data): ...
    def parse_response(self, response): ...
```

### 6. Dependency Injection

**Used in**: Agent initialization, plugin creation

```python
class ScoringAgent(BaseAgent):
    def __init__(
        self,
        model: str,
        temperature: float,
        orchestrator: Optional[AgentOrchestrator] = None
    ):
        # Dependencies injected via constructor
        super().__init__(model, temperature=temperature)
        self.orchestrator = orchestrator
```

## Performance Considerations

### Connection Pooling

- **Min connections**: 2
- **Max connections**: 10
- Reuses connections for efficiency
- Automatic cleanup on idle

### Query Optimization

- **ID-only queries**: Fast document ID retrieval (~10x faster)
- **Bulk fetching**: Single query for multiple documents
- **Indexed searches**: Full-text search with GIN indexes
- **Vector indexes**: HNSW indexes for semantic search

### Memory Management

- **Queue-based processing**: Process large datasets without loading all into memory
- **Weak references**: Shared document cache uses weak references
- **Streaming results**: Database cursors for large result sets
- **Batch processing**: Process documents in configurable batch sizes

### Multi-Model Performance

- **Serial execution**: Simple for-loops prevent resource bottlenecks
- **De-duplication**: Remove duplicate queries and document IDs
- **Overhead**: ~2-3x slower than single-model
- **Benefit**: 20-40% more relevant documents with 2-3 models

## Security Considerations

### Database Security

- **Parameterized queries**: All queries use parameters to prevent SQL injection
- **Connection pooling**: Limited number of concurrent connections
- **No raw SQL**: High-level functions instead of direct SQL

### OpenAthens Authentication

- **JSON serialization**: No pickle vulnerability
- **File permissions**: Session files with 600 permissions
- **HTTPS enforcement**: All institutional URLs must use HTTPS
- **Session validation**: Cached validation with configurable TTL

### LLM Security

- **Local models only**: No API keys, no external services
- **No data leakage**: All processing happens locally
- **Model validation**: Configuration-based model selection

## Extensibility

### Adding a New Agent

1. Inherit from `BaseAgent`
2. Implement `get_agent_type()`
3. Add agent configuration to `config.json`
4. Create agent-specific methods
5. Add to orchestrator if needed

### Adding a New Plugin

1. Create plugin directory in `src/bmlibrarian/gui/qt/plugins/`
2. Implement `plugin.py` with `create_plugin()`
3. Inherit from `BaseTabPlugin`
4. Implement required methods
5. Add to `gui_config.json` enabled plugins

### Adding a New Data Source

1. Create importer in `src/bmlibrarian/importers/`
2. Add source to `source` table
3. Implement document import logic
4. Add CLI tool for import management
5. Update search functions to include new source

## Testing Architecture

### Unit Tests

- **Agent tests**: Test each agent in isolation
- **Database tests**: Test database functions
- **GUI tests**: Test widgets with pytest-qt

### Integration Tests

- **Workflow tests**: Test complete research workflows
- **Multi-agent tests**: Test agent coordination
- **Database integration**: Test real database operations

### Test Data

- **Fixtures**: Sample documents, statements, configurations
- **Mocked LLM**: Mock Ollama responses for testing
- **Test database**: Separate test database for isolation

## Deployment

### System Requirements

- Python 3.12+
- PostgreSQL 14+ with pgvector
- Ollama for local LLM inference
- 16GB+ RAM (32GB recommended)
- 500GB+ storage for full PubMed

### Configuration

1. Database credentials in `.env`
2. Application config in `~/.bmlibrarian/config.json`
3. GUI config in `~/.bmlibrarian/gui_config.json`

### Monitoring

- **Logs**: `~/.bmlibrarian/logs/`
- **Performance tracking**: PostgreSQL audit schema
- **Error reporting**: Structured logging with levels

---

## Next Steps

- [Plugin Development Guide](Plugin-Development-Guide) - Create custom plugins
- [Agent Development](Agent-Development) - Create custom agents
- [API Reference](API-Reference) - Python API documentation
- [Database Schema](Database-Schema) - Complete schema reference

**Questions?** See [Contributing](Contributing) or ask in [GitHub Discussions](https://github.com/hherb/bmlibrarian/discussions).
