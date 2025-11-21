# BMLibrarian Codebase Architecture Analysis

## 1. DATABASE CONNECTIONS MANAGEMENT

### Database Manager Pattern
**File**: `/home/user/bmlibrarian/src/bmlibrarian/database.py`

#### Key Components:
- **DatabaseManager Class**: Centralized singleton-like manager for database connections
  - Connection pooling using `psycopg_pool.ConnectionPool`
  - Min/Max connection configuration (min_size=2, max_size=10, timeout=30)
  - Pool warmup on initialization to establish baseline connections
  - Source ID caching for fast source filtering (class-level cache shared across instances)

#### Connection Management Pattern:
```python
class DatabaseManager:
    def __init__(self):
        self._pool: Optional[ConnectionPool] = None
        self._init_pool()
        self._cache_source_ids()
    
    @contextmanager
    def get_connection(self):
        """Context manager for automatic transaction management"""
        with self._pool.connection() as conn:
            try:
                yield conn
                # Commit is automatic on success
            except Exception as e:
                try:
                    conn.rollback()
                except Exception as rollback_error:
                    logger.error(f"Error during rollback: {rollback_error}")
                raise e
```

#### Global Instance Pattern:
```python
_db_manager = None

def get_db_manager() -> DatabaseManager:
    """Get the global database manager instance (lazy singleton)"""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager
```

#### Configuration from Environment Variables:
- `POSTGRES_HOST`: Database host (default: "localhost")
- `POSTGRES_PORT`: Database port (default: "5432")
- `POSTGRES_USER`: Database user (required)
- `POSTGRES_PASSWORD`: Database password (required)
- `POSTGRES_DB`: Database name (default: "knowledgebase")

#### Source ID Caching:
- Class-level cache shared across all instances
- Cache is built on first access from `sources` table
- Enables fast source filtering without JOINs
- Manual refresh via `refresh_source_cache()` method

---

## 2. OLLAMA INTERACTIONS

### BaseAgent Ollama Integration
**File**: `/home/user/bmlibrarian/src/bmlibrarian/agents/base.py`

#### Ollama Client Initialization:
```python
import ollama

class BaseAgent(ABC):
    def __init__(self, model: str, host: str = "http://localhost:11434", ...):
        self.model = model
        self.host = host
        self.client = ollama.Client(host=host)  # Direct client instantiation
```

#### Configuration Source:
- Gets host from config.py's `get_ollama_config()` method
- Environment variable override: `BMLIB_OLLAMA_HOST` (e.g., "http://localhost:11434")
- Default host in config: "http://localhost:11434"

#### Ollama Request Methods:

**1. Chat-based requests** (`_make_ollama_request`):
```python
def _make_ollama_request(
    self,
    messages: list,
    system_prompt: Optional[str] = None,
    max_retries: int = 3,
    retry_delay: float = 1.0,
    **ollama_options
) -> str:
    # Automatic exponential backoff retry logic (1.0s, 2.0s, 4.0s...)
    # Structured logging with detailed event tracking
    # System prompt handling with automatic prepending
    response = self.client.chat(
        model=self.model,
        messages=request_messages,
        options=options  # temperature, top_p, num_predict
    )
```

**2. Simple generation** (`_generate_from_prompt`):
```python
def _generate_from_prompt(self, prompt: str, max_retries: int = 3, ...) -> str:
    # Similar retry logic as _make_ollama_request
    response = self.client.generate(
        model=self.model,
        prompt=prompt,
        options=options
    )
```

**3. Embedding generation** (`_generate_embedding`):
```python
def _generate_embedding(self, text: str, model: Optional[str] = None) -> list[float]:
    embedding_model = model or "snowflake-arctic-embed2:latest"
    response = self.client.embeddings(
        model=embedding_model,
        prompt=text
    )
    return response['embedding']
```

#### Ollama Options Dictionary:
```python
def _get_ollama_options(self, **overrides) -> Dict[str, Any]:
    options = {
        'temperature': self.temperature,
        'top_p': self.top_p,
        'num_predict': getattr(self, 'max_tokens', 1000)
    }
    options.update(overrides)
    return options
```

#### Error Handling & Retry Strategy:
- **Retryable errors**: `ValueError`, timeout, connection errors
- **Non-retryable errors**: Application-level errors
- **Exponential backoff**: delay *= 2 after each retry
- **Structured logging**: Detailed logging with `event_type`, `attempt`, `response_time_ms`
- **Connection testing**: `test_connection()` and `get_available_models()` methods

---

## 3. GUI STYLING PATTERNS

### File Structure:
```
src/bmlibrarian/gui/qt/resources/
├── constants.py              # Color and size constants
├── styles/
│   ├── dpi_scale.py          # DPI-aware font scaling (singleton)
│   ├── stylesheet_generator.py # Dynamic stylesheet generation
│   └── theme_generator.py    # Complete theme stylesheet
```

### DPI-Aware Font Scaling
**File**: `/home/user/bmlibrarian/src/bmlibrarian/gui/qt/resources/styles/dpi_scale.py`

#### FontScale Singleton Pattern:
```python
class FontScale:
    """Singleton class for DPI-aware font-relative scaling."""
    _instance = None
    _scale_dict: Dict = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._calculate_scale()
        return cls._instance
```

#### Scale Calculation Algorithm:
1. Gets OS default font via `QApplication.font()`
2. Calculates `base_line_height` using `QFontMetrics`
3. Calculates `char_width` for proportional scaling
4. All other dimensions derived from these base measurements

#### Scale Categories:

**Font Sizes** (in points, DPI-independent):
- `font_tiny`: base_font_size * 0.85 (min 8pt)
- `font_small`: base_font_size * 1.0 (min 10pt)
- `font_normal`: base_font_size * 1.1 (min 11pt)
- `font_medium`: base_font_size * 1.2 (min 12pt)
- `font_large`: base_font_size * 1.3 (min 13pt)
- `font_xlarge`: base_font_size * 1.5 (min 15pt)
- `font_icon`: base_font_size * 2.0 (min 18pt)

**Spacing & Padding** (relative to line height):
- `spacing_tiny/small/medium/large/xlarge`
- `padding_tiny/small/medium/large/xlarge`
- All use multiples of base_line_height

**Control Heights** (relative to line height):
- `control_height_small`: 1.8x line height (min 24px)
- `control_height_medium`: 2.2x line height (min 30px)
- `control_height_large`: 2.8x line height (min 40px)
- `control_height_xlarge`: 3.5x line height (min 50px)

**Border Radius**: Derived from line height (0.15x to 0.9x)

**Chat Bubbles** (character-width based):
- `bubble_margin_large`: 3.5x char_width
- `bubble_margin_small`: 0.8x char_width
- `bubble_max_width`: 70 characters wide

#### Access Patterns:

```python
# Singleton access
scale = FontScale()
padding = scale['padding_medium']

# Dictionary access
scale_dict = get_font_scale()  # Returns full dictionary

# Single value access
padding = get_scale_value('padding_medium', default=10)

# Backwards compatibility
scaled_pixels = scale_px(10)  # Scale arbitrary pixel values
```

### Stylesheet Generator
**File**: `/home/user/bmlibrarian/src/bmlibrarian/gui/qt/resources/styles/stylesheet_generator.py`

#### StylesheetGenerator Class:
```python
class StylesheetGenerator:
    def __init__(self, scale: Optional[Dict] = None):
        self.scale = scale if scale is not None else get_font_scale()
        self._s = self.scale  # Shorthand for templates
    
    def button_stylesheet(self, bg_color="#2196F3", ...) -> str:
        # Returns complete QSS stylesheet with scaled dimensions
    
    def input_stylesheet(self, ...) -> str:
        # Text input styling with scaled padding/font
    
    def card_stylesheet(self, ...) -> str:
        # Card/panel styling with rounded corners
    
    def label_stylesheet(self, ...) -> str:
        # Label styling with optional bold
```

#### Template Pattern:
All stylesheets use f-strings with scale dictionary references:
```python
return f"""
QPushButton {{
    padding: {s['padding_small']}px;
    font-size: {s['font_normal']}pt;
    border-radius: {s['radius_small']}px;
}}
"""
```

### Theme Generator
**File**: `/home/user/bmlibrarian/src/bmlibrarian/gui/qt/resources/styles/theme_generator.py`

#### Complete Theme Stylesheet:
```python
def generate_default_theme() -> str:
    """Generate default theme stylesheet with DPI-aware dimensions."""
    s = get_font_scale()
    
    return f"""
/* Complete QSS stylesheet with all widget styling */
QMainWindow {{ background-color: #f5f5f5; }}
QTabWidget::pane {{ border: 1px solid #c0c0c0; }}
QPushButton {{ ... }}
QLineEdit {{ ... }}
/* ... all widget styles ... */
"""
```

### Color Constants
**File**: `/home/user/bmlibrarian/src/bmlibrarian/gui/qt/resources/constants.py`

#### Color Schemes:

**PDF Button States**:
```python
class PDFButtonColors:
    VIEW_BG = "#1976D2"      # Blue - View existing PDF
    FETCH_BG = "#F57C00"     # Orange - Fetch from URL
    UPLOAD_BG = "#388E3C"    # Green - Upload manual
```

**Score Colors**:
```python
class ScoreColors:
    EXCELLENT = "#2E7D32"    # >= 4.5
    GOOD = "#1976D2"         # >= 3.5
    MODERATE = "#F57C00"     # >= 2.5
    POOR = "#C62828"         # < 2.5
```

#### Size Constants:
```python
class ButtonSizes:
    MIN_HEIGHT = 30
    PADDING_HORIZONTAL = 10
    PADDING_VERTICAL = 5
    BORDER_RADIUS = 4

class ScoreThresholds:
    EXCELLENT = 4.5
    GOOD = 3.5
    MODERATE = 2.5
```

#### File System Constants:
```python
class FileSystemDefaults:
    PDF_SUBDIRECTORY = "pdf"
    KNOWLEDGEBASE_DIR = "knowledgebase"
    PDF_EXTENSION = ".pdf"
```

---

## 4. AGENT BASE CLASSES AND PATTERNS

### BaseAgent Architecture
**File**: `/home/user/bmlibrarian/src/bmlibrarian/agents/base.py`

#### Abstract Base Class:
```python
class BaseAgent(ABC):
    """Base class for all BMLibrarian AI agents."""
    
    def __init__(
        self,
        model: str,
        host: str = "http://localhost:11434",
        temperature: float = 0.1,
        top_p: float = 0.9,
        callback: Optional[Callable[[str, str], None]] = None,
        orchestrator: Optional["AgentOrchestrator"] = None,
        show_model_info: bool = True
    ):
        self.model = model
        self.host = host
        self.temperature = temperature
        self.top_p = top_p
        self.callback = callback
        self.client = ollama.Client(host=host)
        self.orchestrator = orchestrator
        
        if show_model_info:
            self._display_model_info()
    
    @abstractmethod
    def get_agent_type(self) -> str:
        """Get the type/name of this agent."""
        pass
```

#### Callback System:
```python
def _call_callback(self, step: str, data: str) -> None:
    """Call the callback function if provided."""
    if self.callback:
        try:
            self.callback(step, data)
        except Exception as e:
            logger.warning(f"Callback function failed for step '{step}': {e}")
```

#### Task Submission (Queue Integration):
```python
def submit_task(self, method_name: str, data: Dict[str, Any], 
                target_agent: Optional[str] = None, 
                priority: Optional[Any] = None) -> Optional[str]:
    """Submit a task to the orchestrator queue."""
    if not self.orchestrator:
        return None
    return self.orchestrator.submit_task(
        target_agent=target_agent or self.get_agent_type(),
        method_name=method_name,
        data=data,
        source_agent=self.get_agent_type(),
        priority=priority or TaskPriority.NORMAL
    )

def submit_batch_tasks(self, method_name: str, data_list: list[Dict[str, Any]], ...) -> Optional[list[str]]:
    """Submit multiple tasks to the orchestrator queue."""
    if not self.orchestrator:
        return None
    return self.orchestrator.submit_batch_tasks(...)
```

#### JSON Parsing Utilities:
```python
def _parse_json_response(self, response: str) -> Dict:
    """Parse JSON response with robust error handling."""
    # Handles markdown wrappers (```json ... ```)
    # Extracts JSON from text with extra content
    # Attempts to fix incomplete JSON

def _generate_and_parse_json(self, prompt: str, max_retries: int = 3, 
                            retry_context: str = "LLM generation") -> Dict:
    """Generate LLM response and parse as JSON with automatic retry."""
    # Regenerates on parse failure (not just retry parsing same bad response)
    # Detailed logging for debugging

def _chat_and_parse_json(self, messages: list, system_prompt: Optional[str] = None, 
                        max_retries: int = 3, retry_context: str = "LLM chat") -> Dict:
    """Send chat messages and parse response as JSON with auto-retry."""
```

#### Embedding Support:
```python
def _generate_embedding(self, text: str, model: Optional[str] = None) -> list[float]:
    """Generate embedding vector for text using Ollama."""
    # Default model: "snowflake-arctic-embed2:latest"
    # Returns float array (embedding dimension varies by model)
```

#### Connection Testing:
```python
def test_connection(self) -> bool:
    """Test the connection to Ollama server and verify model availability."""
    models = self.client.list()
    available_models = [model.model for model in models.models]
    return self.model in available_models

def get_available_models(self) -> list[str]:
    """Get list of available models from Ollama."""
    models = self.client.list()
    return [model.model for model in models.models]
```

### Agent Implementation Example
**File**: `/home/user/bmlibrarian/src/bmlibrarian/agents/query_agent.py`

```python
class QueryAgent(BaseAgent):
    def __init__(self, model: str = "medgemma4B_it_q8:latest", ..., max_tokens: int = 500, ...):
        super().__init__(model, host, temperature, top_p, callback, orchestrator, show_model_info)
        self.max_tokens = max(400, max_tokens)  # Enforce minimum
        self.last_search_metadata: Optional[Dict[str, Any]] = None
        self.system_prompt = """..."""
    
    def get_agent_type(self) -> str:
        return "query_agent"
    
    def convert_question(self, question: str) -> str:
        messages = [{'role': 'user', 'content': question}]
        query = self._make_ollama_request(messages, system_prompt=self.system_prompt)
        return query.strip()
```

---

## 5. CONFIGURATION MANAGEMENT

### Configuration System Architecture
**File**: `/home/user/bmlibrarian/src/bmlibrarian/config.py`

#### BMLibrarianConfig Class:
```python
class BMLibrarianConfig:
    """Configuration manager for BMLibrarian."""
    
    def __init__(self):
        self._config = DEFAULT_CONFIG.copy()
        self._config_loaded = False
        self._load_config()
    
    def _load_config(self):
        """Load configuration from various sources in priority order."""
        # 1. Load from config file (uses fallback search)
        file_config = load_config_with_fallback()
        if file_config:
            self._merge_config(file_config)
        
        # 2. Override with environment variables
        self._load_env_overrides()
```

#### Priority Order:
1. **In-memory defaults** (DEFAULT_CONFIG)
2. **JSON config file** (~/.bmlibrarian/config.json or ./bmlibrarian_config.json)
3. **Environment variables** (BMLIB_* variables)

#### Environment Variable Mappings:
```python
{
    "BMLIB_COUNTERFACTUAL_MODEL": ["models", "counterfactual_agent"],
    "BMLIB_QUERY_MODEL": ["models", "query_agent"],
    "BMLIB_SCORING_MODEL": ["models", "scoring_agent"],
    "BMLIB_CITATION_MODEL": ["models", "citation_agent"],
    "BMLIB_REPORTING_MODEL": ["models", "reporting_agent"],
    "BMLIB_OLLAMA_HOST": ["ollama", "host"],
    "BMLIB_OLLAMA_TIMEOUT": ["ollama", "timeout"],
}
```

#### Accessor Methods:
```python
def get_model(self, agent_type: str, default: Optional[str] = None) -> str:
    """Get the model name for a specific agent type."""

def get_agent_config(self, agent_type: str) -> Dict[str, Any]:
    """Get configuration for a specific agent type."""

def get_ollama_config(self) -> Dict[str, Any]:
    """Get Ollama server configuration."""

def get_search_config(self) -> Dict[str, Any]:
    """Get search configuration."""

def get(self, key_path: str, default=None):
    """Get a configuration value using dot notation (e.g., "models.query_agent")."""

def set(self, key_path: str, value: Any):
    """Set a configuration value using dot notation."""
```

#### Global Instance Pattern:
```python
_config_instance = None

def get_config() -> BMLibrarianConfig:
    """Get the global configuration instance."""
    global _config_instance
    if _config_instance is None:
        _config_instance = BMLibrarianConfig()
    return _config_instance

def reload_config():
    """Reload configuration from files."""
    global _config_instance
    _config_instance = BMLibrarianConfig()
```

#### Convenience Functions:
```python
def get_model(agent_type: str, default: Optional[str] = None) -> str:
    return get_config().get_model(agent_type, default=default)

def get_agent_config(agent_type: str) -> Dict[str, Any]:
    return get_config().get_agent_config(agent_type)

def get_ollama_host() -> str:
    return get_config().get_ollama_config()["host"]
```

### Configuration File Loader
**File**: `/home/user/bmlibrarian/src/bmlibrarian/utils/config_loader.py`

#### File Search Pattern:
```python
def get_standard_config_paths() -> List[Path]:
    """Standard config file search paths in priority order:
    1. ~/.bmlibrarian/config.json (primary/recommended)
    2. ./bmlibrarian_config.json (legacy fallback)
    """
    return [
        get_default_config_path(),  # ~/.bmlibrarian/config.json
        get_legacy_config_path(),   # ./bmlibrarian_config.json
    ]

def find_config_file(custom_path: Optional[Path] = None) -> Optional[Path]:
    """Search for config file in standard locations."""
    search_paths = []
    if custom_path:
        search_paths.append(expand_path(custom_path))
    search_paths.extend(get_standard_config_paths())
    
    for config_path in search_paths:
        if config_path.exists():
            return config_path
    return None

def load_config_with_fallback(custom_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Load configuration with automatic fallback to standard locations."""
    config_path = find_config_file(custom_path)
    if not config_path:
        return None
    return load_json_config(config_path)
```

### Path Utilities
**File**: `/home/user/bmlibrarian/src/bmlibrarian/utils/path_utils.py`

#### Path Helper Functions:
```python
def expand_path(path: Union[str, Path]) -> Path:
    """Expand ~ and environment variables in path."""
    expanded = os.path.expanduser(os.path.expandvars(path))
    return Path(expanded)

def ensure_directory(file_path: Union[str, Path]) -> Path:
    """Ensure parent directory exists for file path."""
    expanded_path = expand_path(file_path)
    parent_dir = expanded_path.parent
    if not parent_dir.exists():
        parent_dir.mkdir(parents=True, exist_ok=True)
    return expanded_path

def get_config_dir() -> Path:
    """Get standard configuration directory (~/.bmlibrarian)."""
    return Path.home() / ".bmlibrarian"

def get_default_config_path() -> Path:
    """Get default configuration file path (~/.bmlibrarian/config.json)."""
    return get_config_dir() / "config.json"

def get_legacy_config_path() -> Path:
    """Get legacy configuration file path (./bmlibrarian_config.json)."""
    return Path.cwd() / "bmlibrarian_config.json"
```

### Agent Factory Pattern
**File**: `/home/user/bmlibrarian/src/bmlibrarian/agents/factory.py`

#### Parameter Filtering:
```python
class AgentFactory:
    SUPPORTED_PARAMS = {
        'query': {'model', 'host', 'temperature', 'top_p', 'max_tokens', ...},
        'scoring': {'model', 'host', 'temperature', 'top_p', 'callback', ...},
        # ... other agent types
    }
    
    @staticmethod
    def filter_agent_config(agent_config: Dict[str, Any], agent_type: str) -> Dict[str, Any]:
        """Filter agent configuration to only include supported parameters."""
        allowed_params = AgentFactory.SUPPORTED_PARAMS.get(agent_type, set())
        return {k: v for k, v in agent_config.items() if k in allowed_params}
```

#### Unified Agent Creation:
```python
@staticmethod
def create_all_agents(orchestrator: Optional[AgentOrchestrator] = None,
                     config: Optional[Dict[str, Any]] = None,
                     callback: Optional[Callable] = None,
                     auto_register: bool = True,
                     audit_conn: Optional[Any] = None) -> Dict[str, Any]:
    """Create all BMLibrarian agents with unified configuration."""
    
    # 1. Create or use provided orchestrator
    if orchestrator is None:
        orchestrator = AgentOrchestrator(max_workers=2)
    
    # 2. Load config if not provided
    if config is None:
        config_obj = get_config()
        config = {
            'ollama': config_obj.get_ollama_config(),
            'models': {
                'query_agent': get_model('query_agent'),
                'scoring_agent': get_model('scoring_agent'),
                # ... other agents
            },
            'agents': {
                'query': get_agent_config('query'),
                'scoring': get_agent_config('scoring'),
                # ... other agents
            }
        }
    
    # 3. Build agent kwargs with filtered config
    def build_agent_kwargs(agent_type: str, model_key: str) -> Dict[str, Any]:
        kwargs = {'orchestrator': orchestrator, 'host': host}
        if model_key in models:
            kwargs['model'] = models[model_key]
        if agent_type in agent_configs:
            kwargs.update(agent_configs[agent_type])
        if callback:
            kwargs['callback'] = callback
        return kwargs
    
    # 4. Create agents with filtered kwargs
    agents = {}
    agents['query_agent'] = AgentFactory.create_agent('query', **build_agent_kwargs('query', 'query_agent'))
    agents['scoring_agent'] = AgentFactory.create_agent('scoring', **build_agent_kwargs('scoring', 'scoring_agent'))
    # ... other agents
    
    # 5. Register agents with orchestrator
    if auto_register:
        for agent_type, agent_name in AgentFactory.AGENT_REGISTRY_NAMES.items():
            orchestrator.register_agent(agent_name, agents[agent_key])
    
    return agents
```

---

## Summary of Key Patterns

### Database
- **Pattern**: Connection pooling with context managers
- **Singleton**: Global lazy-loaded DatabaseManager instance
- **Caching**: Source ID cache to avoid expensive JOINs
- **Configuration**: Environment variables for connection parameters

### Ollama
- **Client Library**: Direct `ollama.Client(host=...)` initialization
- **Retry Logic**: Exponential backoff with configurable max_retries
- **Error Handling**: Distinguishes retryable vs non-retryable errors
- **Logging**: Structured logging with event types and timing data
- **Request Types**: Chat (messages), Generation (prompt), Embeddings (semantic)

### GUI Styling
- **DPI Scaling**: Singleton FontScale calculates all dimensions from system font
- **Font-Relative**: All UI dimensions scaled as multiples of line height or char width
- **Dynamic Generation**: Stylesheets generated at runtime with current scale
- **Color Constants**: Centralized color definitions in constants.py
- **Backwards Compatibility**: Legacy pixel-based scaling with `scale_px()` function

### Agents
- **Base Class**: Abstract BaseAgent with common Ollama integration
- **Configuration**: Model and parameters loaded via config system
- **Callbacks**: Progress tracking via optional callback functions
- **Queue Integration**: Support for orchestrator-based task submission
- **JSON Handling**: Built-in JSON parsing with robustness to formatting issues

### Configuration
- **Priority Order**: Defaults → File → Environment Variables
- **Singleton**: Global config instance with lazy initialization
- **File Search**: Standard paths with fallback (~/.bmlibrarian/config.json → ./bmlibrarian_config.json)
- **Dot Notation**: Easy nested config access via get("models.query_agent")
- **Factory**: AgentFactory filters and validates config before agent creation
