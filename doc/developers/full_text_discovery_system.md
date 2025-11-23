# Full-Text Discovery System - Developer Documentation

This document describes the architecture and implementation details of the full-text PDF discovery system in BMLibrarian.

## Architecture Overview

The discovery system uses a resolver-based architecture where each source type is implemented as a separate resolver class. The `FullTextFinder` orchestrates these resolvers and manages the download process.

```
┌─────────────────────────────────────────────────────────────┐
│                      FullTextFinder                          │
│  (Orchestrates discovery and download)                       │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │   PMC    │ │Unpaywall │ │   DOI    │ │ Direct   │ ...   │
│  │ Resolver │ │ Resolver │ │ Resolver │ │   URL    │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
│        │            │            │            │              │
│        └────────────┴────────────┴────────────┘              │
│                          │                                   │
│                    BaseResolver                              │
│              (Abstract base class)                           │
└─────────────────────────────────────────────────────────────┘
```

## Module Structure

```
src/bmlibrarian/discovery/
├── __init__.py          # Module exports
├── data_types.py        # Type-safe dataclasses and enums
├── resolvers.py         # Resolver implementations
└── full_text_finder.py  # Orchestrator

tests/discovery/
├── __init__.py
├── test_data_types.py   # Data type tests
└── test_resolvers.py    # Resolver tests
```

## Data Types

### Enums

```python
class SourceType(Enum):
    """Type of PDF source."""
    DIRECT_URL = "direct_url"    # Direct PDF URL from database
    DOI_REDIRECT = "doi_redirect"  # PDF URL via DOI resolution
    PMC = "pmc"                  # PubMed Central
    UNPAYWALL = "unpaywall"      # Unpaywall API
    OPENATHENS = "openathens"    # OpenAthens institutional proxy
    BROWSER = "browser"          # Browser-based download
    UNKNOWN = "unknown"

class AccessType(Enum):
    """Type of access for the PDF."""
    OPEN = "open"                # Freely accessible (OA)
    INSTITUTIONAL = "institutional"  # Requires institutional access
    SUBSCRIPTION = "subscription"    # Requires subscription
    UNKNOWN = "unknown"

class ResolutionStatus(Enum):
    """Status of a resolution attempt."""
    SUCCESS = "success"
    NOT_FOUND = "not_found"
    ACCESS_DENIED = "access_denied"
    TIMEOUT = "timeout"
    ERROR = "error"
    SKIPPED = "skipped"
```

### Core Dataclasses

#### DocumentIdentifiers

Input for discovery operations:

```python
@dataclass
class DocumentIdentifiers:
    doc_id: Optional[int] = None    # Database ID
    doi: Optional[str] = None       # Digital Object Identifier
    pmid: Optional[str] = None      # PubMed ID
    pmcid: Optional[str] = None     # PubMed Central ID
    title: Optional[str] = None     # Document title
    pdf_url: Optional[str] = None   # Existing URL from database

    def has_identifiers(self) -> bool:
        """Check if document has any usable identifiers."""
        return any([self.doi, self.pmid, self.pmcid, self.title])

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DocumentIdentifiers":
        """Create from dictionary (e.g., database row)."""
```

#### PDFSource

Represents a discovered PDF source:

```python
@dataclass
class PDFSource:
    url: str                        # PDF URL
    source_type: SourceType         # Source type
    access_type: AccessType         # Access requirements
    priority: int = 0               # Lower = higher priority
    license: Optional[str] = None   # License URL if known
    version: Optional[str] = None   # e.g., "published", "accepted"
    is_best_oa: bool = False        # From Unpaywall
    host_type: Optional[str] = None # e.g., "publisher", "repository"
    metadata: Dict[str, Any] = field(default_factory=dict)
```

#### DiscoveryResult

Complete discovery result:

```python
@dataclass
class DiscoveryResult:
    identifiers: DocumentIdentifiers
    sources: List[PDFSource] = field(default_factory=list)
    resolution_results: List[ResolutionResult] = field(default_factory=list)
    best_source: Optional[PDFSource] = None
    total_duration_ms: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)

    def has_open_access(self) -> bool: ...
    def get_open_access_sources(self) -> List[PDFSource]: ...
    def get_sources_by_type(self, source_type: SourceType) -> List[PDFSource]: ...
    def select_best_source(self) -> Optional[PDFSource]: ...
```

## Resolver Architecture

### Base Resolver

All resolvers inherit from `BaseResolver`:

```python
class BaseResolver(ABC):
    """Abstract base class for PDF source resolvers."""

    def __init__(self, timeout: int = DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': USER_AGENT,
            'Accept': 'application/json, text/html, application/pdf, */*'
        })

    @property
    @abstractmethod
    def name(self) -> str:
        """Resolver name for logging and identification."""
        pass

    @abstractmethod
    def resolve(self, identifiers: DocumentIdentifiers) -> ResolutionResult:
        """Resolve document identifiers to PDF sources."""
        pass

    def _create_result(
        self,
        status: ResolutionStatus,
        sources: Optional[List[PDFSource]] = None,
        error_message: Optional[str] = None,
        duration_ms: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ResolutionResult:
        """Helper to create ResolutionResult."""
```

### Implementing a New Resolver

```python
class MyResolver(BaseResolver):
    """Custom resolver implementation."""

    @property
    def name(self) -> str:
        return "my_resolver"

    def resolve(self, identifiers: DocumentIdentifiers) -> ResolutionResult:
        start_time = time.time()

        # Check if we have required identifiers
        if not identifiers.doi:
            return self._create_result(
                ResolutionStatus.SKIPPED,
                duration_ms=(time.time() - start_time) * 1000
            )

        # Perform resolution logic
        try:
            sources = self._find_sources(identifiers.doi)

            if not sources:
                return self._create_result(
                    ResolutionStatus.NOT_FOUND,
                    duration_ms=(time.time() - start_time) * 1000
                )

            return self._create_result(
                ResolutionStatus.SUCCESS,
                sources=sources,
                duration_ms=(time.time() - start_time) * 1000
            )

        except Exception as e:
            return self._create_result(
                ResolutionStatus.ERROR,
                error_message=str(e),
                duration_ms=(time.time() - start_time) * 1000
            )
```

## Built-in Resolvers

### PMCResolver

Queries PubMed Central for open access PDFs:

- Uses PMC OA web service API
- Converts PMID → PMCID if needed
- Falls back to constructed URLs

**Priority**: 5-6 (highest priority for OA)

### UnpaywallResolver

Queries Unpaywall API for open access versions:

- Requires email address
- Returns best OA location and alternatives
- Rich metadata (license, version, evidence)

**Priority**: 1-3 (best source)

### DOIResolver

Resolves DOIs via CrossRef and doi.org:

- CrossRef API for structured metadata
- Content negotiation for direct PDF links
- Detects Creative Commons licenses

**Priority**: 15-20 (medium)

### DirectURLResolver

Uses existing PDF URLs from database:

- Simple URL validation
- No external requests
- Good for known working URLs

**Priority**: 10 (medium)

### OpenAthensResolver

Constructs proxy URLs for institutional access:

- Works with OpenAthensAuth for authentication
- Last resort for paywalled content
- Requires institutional subscription

**Priority**: 50 (lowest - only when OA unavailable)

## FullTextFinder

The orchestrator coordinates resolvers and manages downloads:

```python
class FullTextFinder:
    def __init__(
        self,
        unpaywall_email: Optional[str] = None,
        openathens_proxy_url: Optional[str] = None,
        openathens_auth: Optional[Any] = None,
        timeout: int = DEFAULT_TIMEOUT,
        prefer_open_access: bool = True,
        skip_resolvers: Optional[List[str]] = None
    ): ...

    def discover(
        self,
        identifiers: DocumentIdentifiers,
        stop_on_first_oa: bool = True,
        progress_callback: Optional[Callable[[str, str], None]] = None
    ) -> DiscoveryResult: ...

    def discover_and_download(
        self,
        identifiers: DocumentIdentifiers,
        output_path: Path,
        max_attempts: int = 3,
        progress_callback: Optional[Callable[[str, str], None]] = None
    ) -> DownloadResult: ...

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "FullTextFinder": ...
```

### Discovery Flow

1. Validate identifiers
2. Iterate through resolvers in priority order
3. For each resolver:
   - Call `resolve()` method
   - Add unique sources to result
   - If OA source found and `prefer_open_access=True`, stop early
4. Sort sources by priority
5. Select best source

### Download Flow

1. Call `discover()` to find sources
2. Try downloading from each source in priority order
3. For each source:
   - Add OpenAthens cookies if needed
   - Download with exponential backoff retry
   - Verify content type (reject HTML)
   - Verify PDF magic bytes
4. Return first successful download or failure

## Configuration

### JSON Configuration

```json
{
  "unpaywall_email": "your@email.com",
  "discovery": {
    "timeout": 30,
    "prefer_open_access": true,
    "skip_resolvers": []
  },
  "openathens": {
    "enabled": true,
    "institution_url": "https://institution.openathens.net"
  }
}
```

### Constants

```python
# resolvers.py
DEFAULT_TIMEOUT = 30  # seconds
USER_AGENT = "Mozilla/5.0 ..."

# full_text_finder.py
DEFAULT_UNPAYWALL_EMAIL = "bmlibrarian@example.com"
```

## Testing

### Unit Tests

Tests are in `tests/discovery/`:

```bash
# Run all discovery tests
uv run pytest tests/discovery/ -v

# Run specific test
uv run pytest tests/discovery/test_resolvers.py::TestPMCResolver -v
```

### Test Structure

```python
class TestMyResolver:
    """Tests for MyResolver."""

    def test_resolve_with_identifier(self):
        """Test successful resolution."""
        resolver = MyResolver()
        identifiers = DocumentIdentifiers(doi="10.1234/test")

        result = resolver.resolve(identifiers)

        assert result.status == ResolutionStatus.SUCCESS
        assert len(result.sources) >= 1

    def test_resolve_without_identifier(self):
        """Test when required identifier is missing."""
        resolver = MyResolver()
        identifiers = DocumentIdentifiers(pmid="12345")

        result = resolver.resolve(identifiers)

        assert result.status == ResolutionStatus.SKIPPED

    @patch('bmlibrarian.discovery.resolvers.requests.Session.get')
    def test_resolve_api_response(self, mock_get):
        """Test parsing API responses."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {...}
        mock_get.return_value = mock_response

        resolver = MyResolver()
        result = resolver.resolve(DocumentIdentifiers(doi="10.1234/test"))

        assert result.status == ResolutionStatus.SUCCESS
```

## Integration with BMLibrarian

### With PDF Manager

```python
from bmlibrarian.utils.pdf_manager import PDFManager
from bmlibrarian.discovery import FullTextFinder, DocumentIdentifiers

finder = FullTextFinder(unpaywall_email="your@email.com")
pdf_manager = PDFManager()

# Discover and download
identifiers = DocumentIdentifiers.from_dict(document)
result = finder.discover(identifiers)

if result.best_source:
    # Use PDF manager for storage
    pdf_path = pdf_manager.get_pdf_path(document['id'])
    download = finder.discover_and_download(identifiers, pdf_path)
```

### With Database

```python
from bmlibrarian.database import DatabaseManager

db = DatabaseManager()
finder = FullTextFinder(unpaywall_email="your@email.com")

# Get documents needing PDFs
documents = db.execute_query("""
    SELECT id, doi, pmid, pmcid, title, pdf_url
    FROM documents
    WHERE local_pdf_path IS NULL
    LIMIT 100
""")

for doc in documents:
    identifiers = DocumentIdentifiers.from_dict(doc)
    result = finder.discover_and_download(
        identifiers,
        output_path=Path(f"pdfs/{doc['id']}.pdf")
    )

    if result.success:
        db.execute_query(
            "UPDATE documents SET local_pdf_path = %s WHERE id = %s",
            [result.file_path, doc['id']]
        )
```

## Error Handling

### Resolution Errors

Each resolver handles its own errors and returns appropriate `ResolutionStatus`:

- `SUCCESS` - Sources found
- `NOT_FOUND` - No sources found
- `SKIPPED` - Missing required identifiers
- `ERROR` - API/network error
- `ACCESS_DENIED` - Authentication required
- `TIMEOUT` - Request timed out

### Download Errors

The download system handles:

- HTTP errors (401, 403, 404, etc.)
- Content type validation (reject HTML)
- PDF validation (magic bytes check)
- Connection errors with retry
- Timeouts with retry

## Performance Considerations

### Early Exit

When `prefer_open_access=True` and `stop_on_first_oa=True`, the system stops searching after finding an OA source:

```python
result = finder.discover(
    identifiers,
    stop_on_first_oa=True  # Stop after PMC/Unpaywall finds OA
)
```

### Skip Resolvers

Skip slow or unnecessary resolvers:

```python
finder = FullTextFinder(
    skip_resolvers=['doi']  # Skip DOI resolution
)
```

### Timeout Configuration

```python
finder = FullTextFinder(timeout=15)  # Faster failures
```

## Future Improvements

1. **Caching** - Add response caching for repeated lookups
2. **Rate Limiting** - Implement per-source rate limiting
3. **Browser Resolver** - Playwright-based resolver for Cloudflare-protected sites
4. **Title Search** - Resolver based on title matching
5. **Async Support** - Async resolver execution for parallel queries
6. **Metrics** - Success rate tracking per resolver
