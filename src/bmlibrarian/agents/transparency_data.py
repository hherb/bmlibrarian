"""
Transparency Assessment Data Models and Constants

Data models for the TransparencyAgent that evaluates research publications for
disclosure completeness, funding transparency, conflict of interest declarations,
data availability, and potential undisclosed bias risk.

These models support offline analysis using local LLMs (Ollama) to assess transparency
from full-text articles already stored in the database, with optional enrichment from
bulk-imported metadata (PubMed grants, ClinicalTrials.gov sponsors, Retraction Watch).
"""

import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

# Maximum characters to analyze (fits within context window)
MAX_TEXT_LENGTH = 12000

# Confidence thresholds
DEFAULT_MIN_CONFIDENCE = 0.4
DEFAULT_CONFIDENCE_FALLBACK = 0.5

# Formatting
SUMMARY_SEPARATOR_WIDTH = 80

# Transparency score thresholds (0-10 scale)
SCORE_THRESHOLD_HIGH_RISK = 3.0      # Below this = high risk
SCORE_THRESHOLD_MEDIUM_RISK = 6.0    # Below this = medium risk
# Above 6.0 = low risk

# Scoring component weights (max points per category)
MAX_FUNDING_SCORE = 3.0       # 0-3: funding disclosure quality
MAX_COI_SCORE = 3.0           # 0-3: COI disclosure quality
MAX_DATA_AVAILABILITY_SCORE = 2.0  # 0-2: data availability
MAX_TRIAL_REGISTRATION_SCORE = 1.0  # 0-1: trial registration (if applicable)
MAX_AUTHOR_CONTRIBUTIONS_SCORE = 1.0  # 0-1: author contributions
MAX_TOTAL_SCORE = 10.0

# LLM response max tokens
DEFAULT_MAX_TOKENS = 3000

# Retry configuration
DEFAULT_MAX_RETRIES = 3


class RiskLevel(str, Enum):
    """Risk levels for transparency assessment."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class DataAvailability(str, Enum):
    """Data availability levels."""
    OPEN = "open"                  # Full open: data in public repositories
    ON_REQUEST = "on_request"      # Available upon reasonable request
    RESTRICTED = "restricted"      # IRB, ethics, confidentiality restrictions
    NOT_AVAILABLE = "not_available"  # Explicitly not shared or proprietary
    NOT_STATED = "not_stated"      # No data availability statement found


# ──────────────────────────────────────────────────────────────────────────────
# Industry Funder Detection
# ──────────────────────────────────────────────────────────────────────────────

# Major pharmaceutical and biotech companies for pattern matching.
# This list covers the top companies by market cap and R&D spending.
# Names are lowercase for case-insensitive matching.
KNOWN_PHARMA_COMPANIES: tuple[str, ...] = (
    # Big Pharma
    "pfizer", "johnson & johnson", "roche", "novartis", "merck",
    "abbvie", "astrazeneca", "bristol-myers squibb", "eli lilly",
    "sanofi", "gsk", "glaxosmithkline", "bayer", "novo nordisk",
    "takeda", "boehringer ingelheim", "amgen", "gilead",
    "regeneron", "moderna", "biogen", "vertex",
    "astellas", "daiichi sankyo", "eisai", "otsuka",
    "teva", "viatris", "bausch", "allergan",
    "shire", "celgene", "alexion", "jazz pharmaceuticals",
    "incyte", "biomarin", "sarepta", "neurocrine",
    "exact sciences", "seagen", "argenx", "alnylam",
    # Medtech / devices
    "medtronic", "abbott laboratories", "boston scientific",
    "edwards lifesciences", "stryker", "becton dickinson",
    "zimmer biomet", "smith & nephew", "baxter",
    # CROs
    "iqvia", "covance", "parexel", "ppd", "icon plc",
    "syneos health", "medpace", "wuxi apptec",
    # Tobacco / controversial
    "philip morris", "altria", "british american tobacco",
    "reynolds american", "japan tobacco",
    # Food / supplements industry
    "nestle health science", "danone", "herbalife",
    # Diagnostics
    "roche diagnostics", "siemens healthineers", "thermo fisher",
    "illumina", "qiagen", "biorad", "agilent",
)

# Regex patterns that indicate corporate/industry entities
CORPORATE_INDICATOR_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r'\b(?:inc|corp|ltd|llc|plc|gmbh|ag|sa|nv|bv)\b', re.IGNORECASE),
    re.compile(r'\bpharmaceutical[s]?\b', re.IGNORECASE),
    re.compile(r'\bpharma\b', re.IGNORECASE),
    re.compile(r'\bbiotech(?:nology)?\b', re.IGNORECASE),
    re.compile(r'\btherapeutics?\b', re.IGNORECASE),
    re.compile(r'\bbioscience[s]?\b', re.IGNORECASE),
    re.compile(r'\blife\s+sciences?\b', re.IGNORECASE),
    re.compile(r'\bmedical\s+devices?\b', re.IGNORECASE),
    re.compile(r'\bdiagnostics?\b', re.IGNORECASE),
)

# Trial registry ID patterns for extraction from text
TRIAL_REGISTRY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r'NCT\d{8}'),                           # ClinicalTrials.gov
    re.compile(r'ISRCTN\d{8,}'),                        # ISRCTN
    re.compile(r'EudraCT\s*\d{4}-\d{6}-\d{2}'),        # EudraCT
    re.compile(r'ACTRN\d{14}'),                          # ANZCTR
    re.compile(r'ChiCTR[\w-]+'),                         # Chinese Clinical Trial Registry
    re.compile(r'CTRI/\d{4}/\d+/\d+'),                  # CTRI India
    re.compile(r'DRKS\d{8}'),                            # DRKS Germany
    re.compile(r'JPRN-[A-Z]+\d+'),                      # JPRN Japan
    re.compile(r'KCT\d{7}'),                             # KCTR Korea
    re.compile(r'PACTR\d{15}'),                          # PACTR Africa
    re.compile(r'SLCTR/\d{4}/\d+'),                     # SLCTR Sri Lanka
    re.compile(r'TCTR\d{11}'),                           # TCTR Thailand
    re.compile(r'UMIN\d{9}'),                            # UMIN Japan
    re.compile(r'NTR\d{4,}'),                            # NTR Netherlands
    re.compile(r'PROSPERO\s*(?:CRD)?\d+', re.IGNORECASE),  # PROSPERO systematic reviews
)


# ──────────────────────────────────────────────────────────────────────────────
# Data Models
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class TransparencyAssessment:
    """Represents a comprehensive transparency assessment of a research publication.

    Evaluates disclosure completeness across multiple dimensions:
    funding, conflicts of interest, data availability, author contributions,
    and trial registration. Produces a composite transparency score (0-10)
    and risk classification (low/medium/high/unknown).
    """

    # Document identification
    document_id: str
    document_title: str
    pmid: Optional[str] = None
    doi: Optional[str] = None

    # Funding disclosure
    has_funding_disclosure: bool = False
    funding_statement: Optional[str] = None
    funding_sources: List[str] = field(default_factory=list)
    is_industry_funded: Optional[bool] = None
    industry_funding_confidence: float = 0.0
    funding_disclosure_quality: float = 0.0

    # Conflict of interest
    has_coi_disclosure: bool = False
    coi_statement: Optional[str] = None
    conflicts_identified: List[str] = field(default_factory=list)
    coi_disclosure_quality: float = 0.0

    # Data availability
    data_availability: str = DataAvailability.NOT_STATED.value
    data_availability_statement: Optional[str] = None

    # Author contributions
    has_author_contributions: bool = False
    contributions_statement: Optional[str] = None

    # Trial registration
    has_trial_registration: bool = False
    trial_registry_ids: List[str] = field(default_factory=list)

    # Overall assessment
    transparency_score: float = 0.0
    overall_confidence: float = 0.0
    risk_level: str = RiskLevel.UNKNOWN.value
    risk_indicators: List[str] = field(default_factory=list)
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)

    # Metadata from bulk imports (optional enrichment)
    is_retracted: Optional[bool] = None
    retraction_reason: Optional[str] = None
    trial_sponsor_class: Optional[str] = None  # NIH/Industry/Other from ClinicalTrials.gov

    # Audit metadata
    created_at: Optional[datetime] = None
    model_used: Optional[str] = None
    agent_version: Optional[str] = None

    def __post_init__(self) -> None:
        """Set creation timestamp if not provided."""
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Returns:
            Dictionary with all fields, datetime converted to ISO format.
        """
        data = asdict(self)
        if self.created_at:
            data['created_at'] = self.created_at.isoformat()
        return data

    def classify_risk(self) -> str:
        """Classify risk level based on transparency score and indicators.

        Returns:
            Risk level string: 'low', 'medium', 'high', or 'unknown'.
        """
        if self.transparency_score < SCORE_THRESHOLD_HIGH_RISK:
            return RiskLevel.HIGH.value
        elif self.transparency_score < SCORE_THRESHOLD_MEDIUM_RISK:
            return RiskLevel.MEDIUM.value
        else:
            return RiskLevel.LOW.value


def is_likely_industry_funder(funder_name: str) -> bool:
    """Check if a funder name matches known pharmaceutical/biotech companies.

    Uses exact name matching against KNOWN_PHARMA_COMPANIES and regex
    pattern matching against CORPORATE_INDICATOR_PATTERNS.

    Args:
        funder_name: Name of the funding organization to check.

    Returns:
        True if the funder name matches a known industry entity.
    """
    name_lower = funder_name.lower().strip()

    # Check against known companies
    for company in KNOWN_PHARMA_COMPANIES:
        if company in name_lower:
            return True

    # Check corporate indicator patterns
    for pattern in CORPORATE_INDICATOR_PATTERNS:
        if pattern.search(funder_name):
            return True

    return False


def extract_trial_registry_ids(text: str) -> List[str]:
    """Extract clinical trial registry IDs from text.

    Searches for known registry ID patterns (NCT, ISRCTN, EudraCT, etc.)
    in the provided text.

    Args:
        text: Text to search for registry IDs.

    Returns:
        List of unique registry IDs found.
    """
    found_ids: List[str] = []
    for pattern in TRIAL_REGISTRY_PATTERNS:
        matches = pattern.findall(text)
        for match in matches:
            cleaned = match.strip()
            if cleaned not in found_ids:
                found_ids.append(cleaned)
    return found_ids
