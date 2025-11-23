# Discovering Full-Text PDFs for Biomedical Literature: An Architectural Essay

## Introduction

The challenge of programmatically obtaining full-text PDFs of biomedical literature is deceptively complex. While it might seem straightforward—find a URL, download a file—the reality involves navigating a fragmented landscape of repositories, access controls, anti-bot protections, and constantly evolving publisher policies. BMLibrarian's PDF discovery system addresses this challenge through a carefully designed architecture that prioritizes reliability, extensibility, and respect for legal access channels.

This essay explores the design philosophy, technical implementation, and practical considerations behind our approach to full-text PDF discovery.

## The Problem Space

Academic publishing exists in a state of productive tension. Publishers maintain paywalls to fund peer review and editorial processes. Open access initiatives push for unrestricted knowledge sharing. Institutional subscriptions create archipelagos of access rights. The result is that obtaining a PDF of a given paper may require navigating any of several pathways:

1. **Open Access Repositories**: PubMed Central (PMC) hosts millions of freely accessible biomedical papers, either through open access mandates or author submissions.

2. **Open Access Aggregators**: Services like Unpaywall index open access versions scattered across institutional repositories, preprint servers, and publisher websites.

3. **Publisher Websites**: Direct access through DOI resolution, sometimes freely available, sometimes paywalled.

4. **Institutional Proxies**: OpenAthens, Shibboleth, and similar systems authenticate users against institutional subscriptions.

Each pathway has its own API conventions, rate limits, response formats, and failure modes. A robust discovery system must orchestrate these diverse sources while handling the inevitable failures gracefully.

## Architectural Philosophy: The Resolver Pattern

The core architectural insight driving our system is that each PDF source should be encapsulated as an independent "resolver"—a self-contained unit that knows how to query a specific source and interpret its responses. This pattern provides several benefits:

**Isolation of Concerns**: Each resolver manages its own API interactions, error handling, and response parsing. When PubMed Central changes their API format, only the PMC resolver needs updating.

**Graceful Degradation**: If one resolver fails—whether due to network issues, API changes, or rate limiting—the system continues with remaining resolvers. No single point of failure.

**Extensibility**: Adding a new source requires implementing a single class with a well-defined interface. The orchestrator automatically incorporates new resolvers.

**Testability**: Each resolver can be unit tested in isolation with mocked responses, enabling confident refactoring.

The abstract base class defines the contract:

```python
class BaseResolver(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Resolver name for logging and identification."""

    @abstractmethod
    def resolve(self, identifiers: DocumentIdentifiers) -> ResolutionResult:
        """Resolve document identifiers to PDF sources."""
```

Every resolver returns a `ResolutionResult` that encapsulates not just the found sources, but metadata about the resolution attempt itself—timing information, error messages, and status codes. This instrumentation proves invaluable for debugging and optimization.

## The Multi-Source Approach

Our system implements five primary resolvers, each targeting a different segment of the academic publishing landscape:

### PMCResolver: The Gold Standard for Open Access

PubMed Central represents the most reliable source for biomedical PDFs. As a government-mandated repository, it maintains stable APIs and guarantees open access. The PMC resolver:

- Queries the PMC OA web service API
- Converts PMIDs to PMCIDs when necessary (many papers have both identifiers)
- Falls back to constructed URLs when the API is unavailable
- Assigns high priority (5-6) to its sources, as PMC PDFs are consistently accessible

### UnpaywallResolver: Aggregating Open Access

Unpaywall maintains an index of legal open access versions across the web. This is particularly valuable for finding:

- Author-deposited versions in institutional repositories
- Green open access copies on personal websites
- Publisher-provided open access versions

The resolver extracts rich metadata from Unpaywall responses, including license information, version type (published, accepted, submitted), and Unpaywall's own "best OA location" recommendation. Sources from Unpaywall receive the highest priority (1-3) when marked as the best available.

### DOIResolver: Direct Publisher Access

When open access sources aren't available, DOI resolution provides a pathway to publisher websites. The resolver employs two strategies:

1. **CrossRef API**: Queries structured metadata that may include PDF links
2. **Content Negotiation**: Requests `application/pdf` directly from doi.org

This resolver handles the complexity of DOI normalization—the same paper might be referenced as `10.1038/nature12373`, `doi:10.1038/nature12373`, or `https://doi.org/10.1038/nature12373`.

### DirectURLResolver: Database Knowledge

When our database already contains a PDF URL (perhaps from a previous import or manual entry), this simple resolver validates the URL format and passes it through. No external requests needed—just URL validation.

### OpenAthensResolver: Institutional Gateway

For paywalled content, institutional access via OpenAthens provides a final option. This resolver:

- Constructs proxy URLs that route through the institution's authentication system
- Integrates with the OpenAthens authentication module for session management
- Receives the lowest priority (50), ensuring free sources are always preferred

## The Two-Phase Download Strategy

Discovery alone doesn't guarantee successful downloads. Web servers employ various protection mechanisms, and PDF delivery varies widely across publishers. Our download strategy addresses this through a two-phase approach:

### Phase 1: Direct HTTP Download

For most sources, simple HTTP requests suffice. The system:

1. Iterates through discovered sources in priority order
2. Issues GET requests with streaming enabled (efficient for large PDFs)
3. Implements exponential backoff retry (2s, 4s, 8s delays)
4. Validates content type (rejecting HTML login pages)
5. Verifies PDF magic bytes (`%PDF-` at file start)

OpenAthens-authenticated downloads inject session cookies and the authenticated user agent string, enabling access to institutionally-licensed content.

### Phase 2: Browser Fallback

When HTTP downloads fail—typically due to Cloudflare protection, JavaScript-required pages, or embedded PDF viewers—the system falls back to browser automation via Playwright. This phase:

- Launches a headless Chromium instance with anti-detection measures
- Handles Cloudflare's "checking your browser" interstitials
- Extracts PDFs from embedded viewers (`<embed>`, `<object>`, `<iframe>`)
- Clicks download buttons when PDFs aren't directly accessible
- Maintains realistic browser fingerprints to avoid bot detection

The browser fallback is intentionally positioned as a last resort. It's slower, more resource-intensive, and more fragile than direct HTTP. But for the subset of sources that require it, browser automation makes the difference between success and failure.

## Type Safety and Data Modeling

The discovery system employs rigorous type safety through dataclasses and enums. This isn't merely aesthetic—it prevents entire categories of bugs and makes the code self-documenting.

### Enums for Categorical Data

```python
class SourceType(Enum):
    DIRECT_URL = "direct_url"
    DOI_REDIRECT = "doi_redirect"
    PMC = "pmc"
    UNPAYWALL = "unpaywall"
    OPENATHENS = "openathens"
    BROWSER = "browser"
    UNKNOWN = "unknown"

class AccessType(Enum):
    OPEN = "open"
    INSTITUTIONAL = "institutional"
    SUBSCRIPTION = "subscription"
    UNKNOWN = "unknown"
```

These enums ensure that source types and access requirements are always valid values. A typo in a string literal might propagate silently; an invalid enum value raises an immediate error.

### Dataclasses for Structured Data

The `PDFSource` dataclass captures everything known about a potential PDF location:

```python
@dataclass
class PDFSource:
    url: str
    source_type: SourceType
    access_type: AccessType
    priority: int = 0
    license: Optional[str] = None
    version: Optional[str] = None
    is_best_oa: bool = False
    host_type: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
```

The `DiscoveryResult` aggregates sources with helper methods for common queries:

```python
def has_open_access(self) -> bool:
    """Check if any open access source was found."""

def get_open_access_sources(self) -> List[PDFSource]:
    """Get all open access sources."""

def select_best_source(self) -> Optional[PDFSource]:
    """Select the best source based on priority and access type."""
```

This design enables fluent, readable client code while ensuring consistency across the codebase.

## Priority-Based Source Selection

Not all PDF sources are created equal. A PMC PDF is essentially guaranteed to work; a publisher link might lead to a paywall. Our priority system encodes this knowledge:

| Priority | Source Type | Rationale |
|----------|-------------|-----------|
| 1-3 | Unpaywall "best" | Curated selection, proven accessible |
| 5-6 | PMC | Government repository, always free |
| 10 | Direct URL | Known URL, but accessibility varies |
| 15-20 | DOI/CrossRef | May be paywalled |
| 50 | OpenAthens | Requires authentication, last resort |

Lower priority values indicate more desirable sources. The system sorts discovered sources by priority and attempts downloads in order, stopping at the first success.

The `prefer_open_access` flag enables an early exit optimization: when an open access source is found, remaining resolvers are skipped entirely. For batch processing, this can dramatically reduce total query time.

## Error Handling and Resilience

Real-world systems fail in creative ways. Our error handling philosophy embraces this reality:

**Resolver Independence**: Each resolver catches its own exceptions and returns structured error information. A timeout in the DOI resolver doesn't prevent the PMC resolver from trying.

**Detailed Status Tracking**: The `ResolutionStatus` enum captures the full taxonomy of outcomes:

```python
class ResolutionStatus(Enum):
    SUCCESS = "success"
    NOT_FOUND = "not_found"
    ACCESS_DENIED = "access_denied"
    TIMEOUT = "timeout"
    ERROR = "error"
    SKIPPED = "skipped"
```

**Progressive Fallback**: Download attempts proceed through multiple sources with retries at each level:
- Try source 1 with 3 retry attempts
- If all fail, try source 2 with 3 retry attempts
- Continue through all sources
- If HTTP fails entirely, try browser fallback

**Content Validation**: Downloaded content is validated before being written to disk:
- Content-Type header must indicate PDF (or be absent)
- First bytes must match PDF magic bytes (`%PDF-`)
- File size must be non-zero

This prevents the common failure mode of successfully downloading an HTML login page and saving it as a "PDF."

## OpenAthens Integration: Secure Institutional Access

Institutional subscriptions unlock vast swaths of the biomedical literature, but accessing them programmatically requires careful security engineering. Our OpenAthens integration:

**Session-Based Authentication**: Users authenticate interactively through their institution's login page. The system captures session cookies for subsequent programmatic access.

**Secure Session Storage**: Session data is stored as JSON (not pickle, avoiding code execution vulnerabilities) with restrictive file permissions (mode 600, owner read/write only).

**Cookie Injection**: When downloading from institutional sources, the system injects authenticated cookies and maintains consistent user agent strings.

**Session Validation**: Before assuming a session is valid, the system performs lightweight validation with configurable caching TTL to reduce overhead.

**HTTPS Enforcement**: All institutional URLs must use HTTPS. The system refuses to transmit credentials over unencrypted connections.

This architecture separates the interactive authentication flow (which requires a browser and user interaction) from the programmatic download flow (which uses captured credentials).

## Configuration and Extensibility

The system supports configuration at multiple levels:

**Constructor Parameters**: For programmatic configuration in code:

```python
finder = FullTextFinder(
    unpaywall_email="researcher@institution.edu",
    timeout=30,
    prefer_open_access=True,
    skip_resolvers=['doi']
)
```

**Configuration File**: For deployment configuration:

```json
{
  "unpaywall_email": "researcher@institution.edu",
  "discovery": {
    "timeout": 30,
    "prefer_open_access": true,
    "skip_resolvers": [],
    "use_browser_fallback": true
  }
}
```

**Factory Method**: For configuration-driven instantiation:

```python
finder = FullTextFinder.from_config(config)
```

Adding a new resolver requires implementing the `BaseResolver` interface and registering with the orchestrator. The resolver pattern ensures new sources integrate seamlessly with existing infrastructure.

## Performance Characteristics

Understanding performance is crucial for planning batch operations:

- **Discovery Phase**: Typically 5-15 seconds, depending on resolver count and network latency. Early exit on OA discovery can reduce this significantly.

- **HTTP Download**: Sub-second for small PDFs, 5-30 seconds for large files (20+ MB common in supplementary materials).

- **Browser Fallback**: 30-120 seconds including Cloudflare wait times and browser startup overhead.

For batch processing of thousands of papers, the system's ability to skip browser fallback when HTTP succeeds provides substantial time savings. Configuring aggressive timeouts and enabling early exit further optimizes throughput.

## Ethical Considerations

Our system is designed with ethical access in mind:

**Legal Channels Only**: We query legitimate APIs and respect access controls. The system never circumvents paywalls or authentication requirements.

**Rate Limiting**: Exponential backoff and reasonable timeouts prevent overwhelming servers. Users are encouraged to add delays in batch operations.

**Terms of Service**: Unpaywall requires a contact email; we prominently document this requirement. Users authenticate through their institutions' legitimate proxy systems.

**Open Access Priority**: By prioritizing free sources, we minimize load on subscription services and support the open access ecosystem.

## Conclusion

The full-text PDF discovery system in BMLibrarian represents a pragmatic response to the complexity of academic publishing infrastructure. By encapsulating diverse sources as independent resolvers, implementing robust fallback strategies, and maintaining rigorous type safety, we've created a system that reliably delivers PDFs while remaining adaptable to the evolving publishing landscape.

The architecture balances several competing concerns: reliability through redundancy, performance through optimization, security through careful authentication handling, and extensibility through clean abstractions. The result is a system that just works—whether you're downloading a single paper or processing thousands in batch.

For biomedical researchers, this means more time analyzing literature and less time wrestling with download failures. For developers extending the system, it means clear patterns and well-defined interfaces. And for the broader ecosystem, it means supporting legal access channels and open access initiatives.

The fragments are united; the PDFs flow.

---

*This essay documents the PDF discovery system as implemented in BMLibrarian v1.0. For technical implementation details, see the [developer documentation](/doc/developers/full_text_discovery_system.md). For usage instructions, see the [user guide](/doc/users/full_text_discovery_guide.md).*
