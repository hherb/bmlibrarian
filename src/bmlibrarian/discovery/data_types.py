"""Data types for full-text discovery module.

 

Defines type-safe dataclasses for PDF discovery, resolution results,

and source metadata.

"""

 

from dataclasses import dataclass, field

from datetime import datetime

from enum import Enum

from typing import Optional, List, Dict, Any

 

 

class SourceType(Enum):

    """Type of PDF source."""

 

    DIRECT_URL = "direct_url"  # Direct PDF URL from database

    DOI_REDIRECT = "doi_redirect"  # PDF URL via DOI resolution

    PMC = "pmc"  # PubMed Central

    UNPAYWALL = "unpaywall"  # Unpaywall API

    OPENATHENS = "openathens"  # OpenAthens institutional proxy

    BROWSER = "browser"  # Browser-based download (Cloudflare bypass)

    UNKNOWN = "unknown"

 

 

class AccessType(Enum):

    """Type of access for the PDF."""

 

    OPEN = "open"  # Freely accessible (OA)

    INSTITUTIONAL = "institutional"  # Requires institutional access

    SUBSCRIPTION = "subscription"  # Requires subscription

    UNKNOWN = "unknown"

 

 

class ResolutionStatus(Enum):

    """Status of a resolution attempt."""

 

    SUCCESS = "success"

    NOT_FOUND = "not_found"

    ACCESS_DENIED = "access_denied"

    TIMEOUT = "timeout"

    ERROR = "error"

    SKIPPED = "skipped"

 

 

@dataclass

class PDFSource:

    """Represents a discovered PDF source."""

 

    url: str

    source_type: SourceType

    access_type: AccessType

    priority: int = 0  # Lower is higher priority (0 = highest)

    license: Optional[str] = None

    version: Optional[str] = None  # e.g., "published", "accepted", "submitted"

    is_best_oa: bool = False  # From Unpaywall: is this the best OA location?

    host_type: Optional[str] = None  # e.g., "publisher", "repository"

    metadata: Dict[str, Any] = field(default_factory=dict)

 

    def __lt__(self, other: "PDFSource") -> bool:

        """Compare sources by priority (for sorting)."""

        return self.priority < other.priority

 

 

@dataclass

class ResolutionResult:

    """Result of a single resolution attempt."""

 

    resolver_name: str

    status: ResolutionStatus

    sources: List[PDFSource] = field(default_factory=list)

    error_message: Optional[str] = None

    duration_ms: float = 0.0

    metadata: Dict[str, Any] = field(default_factory=dict)

 

 

@dataclass

class DocumentIdentifiers:

    """Identifiers for a document."""

 

    doc_id: Optional[int] = None

    doi: Optional[str] = None

    pmid: Optional[str] = None

    pmcid: Optional[str] = None

    title: Optional[str] = None

    pdf_url: Optional[str] = None  # Existing URL from database

 

    def has_identifiers(self) -> bool:

        """Check if document has any usable identifiers."""

        return any([self.doi, self.pmid, self.pmcid, self.title])

 

    @classmethod

    def from_dict(cls, data: Dict[str, Any]) -> "DocumentIdentifiers":

        """Create from dictionary (e.g., database row)."""

        return cls(

            doc_id=data.get('id'),

            doi=data.get('doi'),

            pmid=data.get('pmid') or data.get('pubmed_id'),

            pmcid=data.get('pmcid') or data.get('pmc_id'),

            title=data.get('title'),

            pdf_url=data.get('pdf_url')

        )

 

 

@dataclass

class DiscoveryResult:

    """Complete result of full-text discovery for a document."""

 

    identifiers: DocumentIdentifiers

    sources: List[PDFSource] = field(default_factory=list)

    resolution_results: List[ResolutionResult] = field(default_factory=list)

    best_source: Optional[PDFSource] = None

    total_duration_ms: float = 0.0

    timestamp: datetime = field(default_factory=datetime.now)

 

    def has_open_access(self) -> bool:

        """Check if any open access source was found."""

        return any(s.access_type == AccessType.OPEN for s in self.sources)

 

    def get_open_access_sources(self) -> List[PDFSource]:

        """Get all open access sources."""

        return [s for s in self.sources if s.access_type == AccessType.OPEN]

 

    def get_sources_by_type(self, source_type: SourceType) -> List[PDFSource]:

        """Get sources of a specific type."""

        return [s for s in self.sources if s.source_type == source_type]

 

    def select_best_source(self) -> Optional[PDFSource]:

        """Select the best source based on priority.

 

        Priority order:

        1. Open access sources (sorted by priority)

        2. Institutional access sources

        3. Other sources

 

        Returns:

            Best PDFSource, or None if no sources available

        """

        if not self.sources:

            return None

 

        # Separate by access type

        open_sources = sorted(

            [s for s in self.sources if s.access_type == AccessType.OPEN],

            key=lambda s: s.priority

        )

 

        institutional_sources = sorted(

            [s for s in self.sources if s.access_type == AccessType.INSTITUTIONAL],

            key=lambda s: s.priority

        )

 

        other_sources = sorted(

            [s for s in self.sources if s.access_type not in (AccessType.OPEN, AccessType.INSTITUTIONAL)],

            key=lambda s: s.priority

        )

 

        # Return first available in priority order

        if open_sources:

            return open_sources[0]

        if institutional_sources:

            return institutional_sources[0]

        if other_sources:

            return other_sources[0]

 

        return None

 

 

@dataclass

class DownloadResult:

    """Result of a PDF download attempt."""

 

    success: bool

    source: Optional[PDFSource] = None

    file_path: Optional[str] = None

    file_size: int = 0

    error_message: Optional[str] = None

    duration_ms: float = 0.0

    attempts: int = 1