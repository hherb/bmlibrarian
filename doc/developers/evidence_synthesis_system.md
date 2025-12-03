# Evidence Synthesis System - Developer Documentation

This document describes the technical architecture of the evidence synthesis system for systematic reviews in BMLibrarian.

## Overview

The Evidence Synthesis system extracts citations from included papers and synthesizes them into a narrative conclusion that directly answers the research question. It bridges the gap between paper selection and meaningful conclusions.

## Architecture

### Components

```
EvidenceSynthesizer
├── CitationFinderAgent (reused from agents/citation_agent.py)
├── ExtractedCitation (data model)
├── EvidenceSynthesis (data model)
└── LLM Synthesis (via ollama)
```

### Data Flow

```
Included Papers (AssessedPaper[])
       │
       ▼
┌─────────────────────┐
│ Citation Extraction │  ← Uses CitationFinderAgent
│ (per paper)         │
└─────────────────────┘
       │
       ▼
ExtractedCitation[]
       │
       ▼
┌─────────────────────┐
│ Narrative Synthesis │  ← LLM-based synthesis
│ (all citations)     │
└─────────────────────┘
       │
       ▼
EvidenceSynthesis
```

## Key Classes

### EvidenceSynthesizer

Location: `src/bmlibrarian/agents/systematic_review/synthesizer.py`

Main class that orchestrates citation extraction and narrative synthesis.

```python
class EvidenceSynthesizer:
    def __init__(
        self,
        model: str = DEFAULT_SYNTHESIS_MODEL,
        citation_model: Optional[str] = None,
        temperature: float = DEFAULT_SYNTHESIS_TEMPERATURE,
        citation_min_relevance: float = DEFAULT_CITATION_MIN_RELEVANCE,
        max_citations_per_paper: int = DEFAULT_MAX_CITATIONS_PER_PAPER,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ):
        ...

    def synthesize(
        self,
        research_question: str,
        included_papers: List[AssessedPaper],
    ) -> EvidenceSynthesis:
        ...
```

### ExtractedCitation

Data model for a citation extracted from a paper.

```python
@dataclass
class ExtractedCitation:
    document_id: int           # Database ID
    paper_title: str           # Paper title
    authors: List[str]         # Author list
    year: int                  # Publication year
    passage: str               # Extracted text
    summary: str               # How it addresses the question
    relevance_score: float     # Confidence (0-1)
    pmid: Optional[str] = None
    doi: Optional[str] = None
```

### EvidenceSynthesis

Data model for the complete synthesis result.

```python
@dataclass
class EvidenceSynthesis:
    research_question: str
    executive_summary: str     # 2-3 sentence answer
    evidence_narrative: str    # Full narrative
    key_findings: List[Dict[str, Any]]
    evidence_strength: str     # Strong/Moderate/Limited/Insufficient
    limitations: List[str]
    citations: List[ExtractedCitation]
    citation_count: int
    paper_count: int
```

## Constants

The module defines constants per the golden rules (no magic numbers):

```python
# Default settings
DEFAULT_SYNTHESIS_MODEL = "gpt-oss:20b"
DEFAULT_CITATION_MIN_RELEVANCE = 0.7
DEFAULT_MAX_CITATIONS_PER_PAPER = 3
DEFAULT_SYNTHESIS_TEMPERATURE = 0.3

# LLM generation
SYNTHESIS_MAX_TOKENS = 2000

# Formatting
MAX_AUTHORS_BEFORE_ET_AL = 3
FALLBACK_SUMMARY_MAX_LENGTH = 500
FALLBACK_MAX_FINDINGS = 5

# Evidence strength thresholds
EVIDENCE_STRENGTH_MODERATE_THRESHOLD = 5
EVIDENCE_STRENGTH_LIMITED_THRESHOLD = 2
```

## Configuration

Configuration is loaded from `SystematicReviewConfig`:

```python
# config.py additions
enable_evidence_synthesis: bool = True
synthesis_model: Optional[str] = None  # Defaults to main model
citation_min_relevance: float = 0.7
max_citations_per_paper: int = 3
synthesis_temperature: float = 0.3
```

## Integration with Agent

The evidence synthesis phase is integrated into `SystematicReviewAgent.run_review()`:

```python
# Phase 7a: Evidence Synthesis (Optional)
evidence_synthesis = None
if self.config.enable_evidence_synthesis and included_papers:
    from .synthesizer import EvidenceSynthesizer

    synthesizer = EvidenceSynthesizer(
        model=self.config.synthesis_model or self.config.model,
        citation_model=self.config.model,
        temperature=self.config.synthesis_temperature,
        citation_min_relevance=self.config.citation_min_relevance,
        max_citations_per_paper=self.config.max_citations_per_paper,
        progress_callback=self.callback,
    )

    evidence_synthesis = synthesizer.synthesize(
        research_question=criteria.research_question,
        included_papers=included_papers,
    )
```

## Report Output

The Reporter formats evidence synthesis in markdown:

```python
def _format_evidence_synthesis_section(
    self, evidence_synthesis: Dict[str, Any]
) -> List[str]:
    """Format evidence synthesis section."""
    # Returns markdown with:
    # - Answer to Research Question (blockquote)
    # - Evidence Strength
    # - Citation statistics
    # - Synthesized Evidence narrative
    # - Key Findings (numbered with supporting studies)
    # - Limitations
    # - Supporting Citations (detailed)
```

## LLM Prompts

### System Prompt

```
You are an expert medical researcher synthesizing evidence from a systematic review.
Your task is to analyze extracted citations and produce a cohesive narrative that directly answers the research question.

Guidelines:
1. Focus on what the evidence actually shows, not speculation
2. Note the strength and consistency of findings across studies
3. Identify any contradictory findings and explain possible reasons
4. Be specific about effect sizes, outcomes, and population characteristics
5. Acknowledge limitations and gaps in the evidence
6. Use clear, academic language suitable for medical publication
7. Reference studies using [author, year] format inline
```

### Synthesis Prompt Template

The synthesis prompt includes:
- Research question
- Formatted evidence from all citations
- JSON response format specification

## Error Handling

The system has multiple fallback mechanisms:

1. **Citation Extraction Failures**: Logged as warnings, processing continues
2. **JSON Parse Failures**: Fallback to extracting raw text as summary
3. **Synthesis Failures**: Creates fallback synthesis from raw citations

```python
def _create_fallback_synthesis(
    self,
    research_question: str,
    citations: List[ExtractedCitation],
) -> EvidenceSynthesis:
    """Create a fallback synthesis when LLM synthesis fails."""
    # Creates basic findings from first N citations
    # Assesses strength based on citation count
```

## Testing

Test the evidence synthesis with:

```python
from src.bmlibrarian.agents.systematic_review.synthesizer import (
    EvidenceSynthesizer, ExtractedCitation, EvidenceSynthesis
)

# Create test synthesis
synthesis = EvidenceSynthesis(
    research_question='Test question?',
    executive_summary='Test summary',
    evidence_narrative='Test narrative',
    key_findings=[],
    evidence_strength='Moderate',
    limitations=[],
    citations=[],
    citation_count=0,
    paper_count=0
)

# Verify serialization
d = synthesis.to_dict()
assert 'executive_summary' in d
```

## Future Enhancements

Potential improvements:

1. **Map-Reduce for Large Citation Sets**: Split citations into chunks for parallel synthesis
2. **Citation Clustering**: Group citations by theme before synthesis
3. **Confidence Calibration**: Improve evidence strength assessment
4. **Multi-language Support**: Handle non-English papers
5. **Full-text Support**: Extract citations from full paper text when available

## Related Files

- `src/bmlibrarian/agents/systematic_review/synthesizer.py` - Main implementation
- `src/bmlibrarian/agents/systematic_review/config.py` - Configuration
- `src/bmlibrarian/agents/systematic_review/agent.py` - Agent integration
- `src/bmlibrarian/agents/systematic_review/reporter.py` - Report formatting
- `src/bmlibrarian/agents/systematic_review/data_models.py` - Data models
- `src/bmlibrarian/agents/citation_agent.py` - CitationFinderAgent (reused)
