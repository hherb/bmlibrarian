# BMLibrarian Architecture - Quick Reference Guide

## File Locations at a Glance

### Database Management
- **Main Implementation**: `/home/user/bmlibrarian/src/bmlibrarian/database.py`
- **Global Access**: `get_db_manager()` function
- **Context Manager**: `with db_manager.get_connection() as conn:`
- **Database Functions**: `find_abstracts()`, `search_hybrid()`

### Ollama Integration
- **Base Class**: `/home/user/bmlibrarian/src/bmlibrarian/agents/base.py`
- **Implemented by**: All agent subclasses (QueryAgent, ScoringAgent, etc.)
- **Client Creation**: `self.client = ollama.Client(host=host)`
- **Request Methods**: `_make_ollama_request()`, `_generate_from_prompt()`, `_generate_embedding()`

### GUI Styling
- **DPI Scaling**: `/home/user/bmlibrarian/src/bmlibrarian/gui/qt/resources/styles/dpi_scale.py`
- **Stylesheet Generator**: `/home/user/bmlibrarian/src/bmlibrarian/gui/qt/resources/styles/stylesheet_generator.py`
- **Theme Generator**: `/home/user/bmlibrarian/src/bmlibrarian/gui/qt/resources/styles/theme_generator.py`
- **Color Constants**: `/home/user/bmlibrarian/src/bmlibrarian/gui/qt/resources/constants.py`

### Agent Base Classes
- **BaseAgent**: `/home/user/bmlibrarian/src/bmlibrarian/agents/base.py`
- **Agent Factory**: `/home/user/bmlibrarian/src/bmlibrarian/agents/factory.py`
- **Orchestrator**: `/home/user/bmlibrarian/src/bmlibrarian/agents/orchestrator.py`
- **Queue Manager**: `/home/user/bmlibrarian/src/bmlibrarian/agents/queue_manager.py`

### Configuration Management
- **Main Config**: `/home/user/bmlibrarian/src/bmlibrarian/config.py`
- **Config Loader**: `/home/user/bmlibrarian/src/bmlibrarian/utils/config_loader.py`
- **Path Utilities**: `/home/user/bmlibrarian/src/bmlibrarian/utils/path_utils.py`

---

## Common Usage Patterns

### 1. Database Connection
```python
from bmlibrarian.database import get_db_manager

# Get connection
db_manager = get_db_manager()

# Use with context manager (automatic commit/rollback)
with db_manager.get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT id, title FROM documents LIMIT 10")
        results = cur.fetchall()

# Search for documents
from bmlibrarian.database import find_abstracts

for doc in find_abstracts("covid vaccine", max_rows=100):
    print(doc['title'], doc['publication_date'])
```

### 2. Configuration Access
```python
from bmlibrarian.config import get_config, get_model, get_agent_config

# Get config instance
config = get_config()

# Get model for agent
model = get_model('query_agent')  # Returns configured model string

# Get agent-specific config
agent_config = get_agent_config('query')  # Returns {'temperature': 0.1, 'top_p': 0.9, ...}

# Get Ollama host
ollama_host = config.get_ollama_config()['host']  # "http://localhost:11434"

# Dot-notation access
max_results = config.get('search.max_results', default=100)
```

### 3. Creating Agents
```python
from bmlibrarian.agents import AgentFactory

# Create all agents at once (recommended)
agents = AgentFactory.create_all_agents()
query_agent = agents['query_agent']
scoring_agent = agents['scoring_agent']

# Or create single agent
from bmlibrarian.agents import QueryAgent
from bmlibrarian.config import get_model, get_agent_config

model = get_model('query_agent')
agent_config = get_agent_config('query')
query_agent = QueryAgent(model=model, **agent_config)

# Test connection
if query_agent.test_connection():
    print("Connected to Ollama")
else:
    print("Failed to connect")
```

### 4. Ollama Requests (from agent)
```python
# Chat request
response = agent._make_ollama_request(
    messages=[{'role': 'user', 'content': 'Question here'}],
    system_prompt="You are a helpful assistant",
    max_retries=3,
    retry_delay=1.0
)

# Simple generation
response = agent._generate_from_prompt(
    "Tell me about cardiovascular disease",
    max_retries=3
)

# Generate embedding
embedding = agent._generate_embedding(
    "What is heart disease?",
    model="snowflake-arctic-embed2:latest"
)

# JSON response (with auto-retry on parse failure)
result = agent._generate_and_parse_json(
    prompt="Return JSON with field 'answer'",
    max_retries=3,
    retry_context="question answering"
)
```

### 5. GUI Styling with DPI Scaling
```python
from bmlibrarian.gui.qt.resources.styles.dpi_scale import get_font_scale, get_scale_value, FontScale
from bmlibrarian.gui.qt.resources.styles.stylesheet_generator import StylesheetGenerator
from bmlibrarian.gui.qt.resources.styles.theme_generator import generate_default_theme
from bmlibrarian.gui.qt.resources.constants import ScoreColors, PDFButtonColors

# Get scale dictionary
scale = get_font_scale()
padding = scale['padding_medium']

# Get single value
font_size = get_scale_value('font_large', default=16)

# Use singleton directly
font_scale = FontScale()
control_height = font_scale['control_height_medium']

# Generate stylesheet for button
generator = StylesheetGenerator()
button_style = generator.button_stylesheet(
    bg_color="#2196F3",
    hover_color="#1976D2",
    font_size_key='font_medium'
)

# Apply theme
theme_stylesheet = generate_default_theme()
app.setStyleSheet(theme_stylesheet)

# Use color constants
excellent_color = ScoreColors.EXCELLENT  # "#2E7D32"
view_button_color = PDFButtonColors.VIEW_BG  # "#1976D2"
```

### 6. Environment Variable Configuration
```bash
# Set Ollama host
export BMLIB_OLLAMA_HOST="http://localhost:11434"

# Set model for specific agent
export BMLIB_QUERY_MODEL="gpt-oss:20b"
export BMLIB_SCORING_MODEL="medgemma-27b-text-it-Q8_0:latest"

# Set Ollama timeout
export BMLIB_OLLAMA_TIMEOUT="120"

# Database configuration
export POSTGRES_HOST="localhost"
export POSTGRES_PORT="5432"
export POSTGRES_USER="username"
export POSTGRES_PASSWORD="password"
export POSTGRES_DB="knowledgebase"
```

---

## Configuration File Format

### Location
- **Recommended**: `~/.bmlibrarian/config.json`
- **Legacy**: `./bmlibrarian_config.json`

### Example Configuration
```json
{
  "models": {
    "query_agent": "medgemma-27b-text-it-Q8_0:latest",
    "scoring_agent": "medgemma-27b-text-it-Q8_0:latest",
    "citation_agent": "medgemma-27b-text-it-Q8_0:latest",
    "reporting_agent": "gpt-oss:20b",
    "counterfactual_agent": "medgemma-27b-text-it-Q8_0:latest",
    "editor_agent": "gpt-oss:20b"
  },
  "ollama": {
    "host": "http://localhost:11434",
    "timeout": 120,
    "max_retries": 3
  },
  "agents": {
    "query": {
      "temperature": 0.1,
      "top_p": 0.9,
      "max_tokens": 500
    },
    "scoring": {
      "temperature": 0.1,
      "top_p": 0.9,
      "min_relevance_score": 3
    }
  },
  "search": {
    "max_results": 100,
    "score_threshold": 2.5
  }
}
```

---

## Key Design Patterns

### Pattern: Singleton with Lazy Initialization
Used for: DatabaseManager, BMLibrarianConfig, FontScale

```python
_instance = None

def get_instance():
    global _instance
    if _instance is None:
        _instance = MyClass()
    return _instance
```

### Pattern: Context Manager for Resource Management
Used for: Database connections

```python
@contextmanager
def get_connection(self):
    with self._pool.connection() as conn:
        try:
            yield conn
        except Exception as e:
            conn.rollback()
            raise e
```

### Pattern: Exponential Backoff Retry Logic
Used for: Ollama requests

```python
current_delay = retry_delay
for attempt in range(max_retries):
    try:
        # Attempt operation
        response = self.client.chat(...)
        return response
    except Exception as e:
        if attempt < max_retries - 1:
            time.sleep(current_delay)
            current_delay *= 2  # Exponential backoff
        else:
            raise
```

### Pattern: Factory with Parameter Filtering
Used for: AgentFactory

```python
SUPPORTED_PARAMS = {
    'query': {'model', 'host', 'temperature', 'top_p', 'max_tokens', ...}
}

def filter_agent_config(config, agent_type):
    allowed = SUPPORTED_PARAMS.get(agent_type, set())
    return {k: v for k, v in config.items() if k in allowed}
```

### Pattern: Font-Relative DPI Scaling
Used for: GUI styling

```python
# Calculate base measurements from system font
base_font_size = QApplication.font().pointSize()
metrics = QFontMetrics(QApplication.font())
base_line_height = metrics.lineSpacing()

# All other dimensions derived from these
padding_medium = max(6, int(base_line_height * 0.4))
```

---

## Error Handling Strategy

### Connection Errors
- **Location**: BaseAgent retry logic
- **Strategy**: Retryable errors get exponential backoff, non-retryable errors fail immediately
- **Logging**: Structured logging with event_type, attempt count, response_time_ms

### JSON Parse Failures
- **Location**: BaseAgent._generate_and_parse_json()
- **Strategy**: Regenerate response (don't just retry parsing)
- **Logging**: Detailed logging of all parse attempts and successes

### Database Connection Failures
- **Location**: DatabaseManager
- **Strategy**: Connection pool with warmup, automatic rollback on error
- **Logging**: Logger warnings for pool warmup failures

### Configuration Loading
- **Location**: BMLibrarianConfig._load_config()
- **Strategy**: Fallback chain (defaults → file → env vars)
- **Logging**: Info logs for loaded sources, warning logs for missing files

---

## Important Constants and Defaults

### Database Pooling
- `min_size`: 2 connections
- `max_size`: 10 connections
- `timeout`: 30 seconds

### Ollama Defaults
- `host`: "http://localhost:11434"
- `timeout`: 120 seconds
- `max_retries`: 3

### Agent Defaults
- `temperature`: 0.1 (deterministic)
- `top_p`: 0.9 (mostly deterministic, some variety)
- `max_tokens`: Agent-specific (300-6000 depending on agent)

### GUI Fonts (DPI-Aware)
- `font_small`: base_size * 1.0 (min 10pt)
- `font_normal`: base_size * 1.1 (min 11pt)
- `font_medium`: base_size * 1.2 (min 12pt)
- `font_large`: base_size * 1.3 (min 13pt)

### Score Thresholds
- `EXCELLENT`: >= 4.5
- `GOOD`: >= 3.5
- `MODERATE`: >= 2.5
- `POOR`: < 2.5

---

## Debugging Tips

### Enable Structured Logging
```python
import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('bmlibrarian')
```

### Check Ollama Connection
```python
from bmlibrarian.agents import AgentFactory

agents = AgentFactory.create_all_agents()
results = AgentFactory.test_all_connections(agents)
AgentFactory.print_connection_status(results)
```

### Check Configuration
```python
from bmlibrarian.config import get_config

config = get_config()
print("Ollama Host:", config.get_ollama_config()['host'])
print("Query Agent Model:", config.get_model('query_agent'))
print("Search Max Results:", config.get('search.max_results'))
```

### Check Database Connection
```python
from bmlibrarian.database import get_db_manager

db = get_db_manager()
with db.get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT 1")
        print("Database connected!")
```

### Check GUI Scaling
```python
from bmlibrarian.gui.qt.resources.styles.dpi_scale import FontScale

scale = FontScale()
print("Base Font Size:", scale['base_font_size'])
print("Base Line Height:", scale['base_line_height'])
print("Padding Medium:", scale['padding_medium'])
```
