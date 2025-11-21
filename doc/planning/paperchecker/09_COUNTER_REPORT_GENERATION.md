# Step 9: Counter-Report Generation

## Context

Citations have been extracted (Step 8). Now we need to synthesize these citations into a coherent prose report that summarizes the counter-evidence.

## Objective

Generate professional medical-style reports that:
- Synthesize citations into coherent narrative
- Maintain factual accuracy with proper references
- Use professional medical writing style
- Provide statistics on search and scoring
- Format as markdown for easy readability

## Requirements

- LLM-based report generation
- Adaptation of ReportingAgent patterns
- Citation integration with inline references
- Statistical summary of search/scoring
- Professional medical writing style
- Markdown formatting

## Implementation Location

Update: `src/bmlibrarian/paperchecker/agent.py` (`_generate_counter_report` method)

## Design Approach

Similar to the existing ReportingAgent, but adapted for counter-evidence synthesis. The report should:
1. Summarize the counter-evidence found
2. Reference specific citations inline
3. Avoid overstating or understating the evidence
4. Maintain temporal precision (specific years, not "recent")
5. Include statistical context

## Implementation

Update `src/bmlibrarian/paperchecker/agent.py`:

```python
def _generate_counter_report(
    self,
    counter_stmt: CounterStatement,
    citations: List[ExtractedCitation],
    search_results: SearchResults,
    scored_docs: List[ScoredDocument]
) -> CounterReport:
    """
    Step 6: Generate counter-evidence report

    Synthesizes extracted citations into a coherent prose report that
    summarizes evidence supporting the counter-statement.

    Args:
        counter_stmt: CounterStatement being reported on
        citations: List of ExtractedCitation objects
        search_results: SearchResults for statistics
        scored_docs: List of ScoredDocument for statistics

    Returns:
        CounterReport with prose summary and statistics

    Raises:
        RuntimeError: If report generation fails
    """
    logger.info(
        f"Generating counter-report from {len(citations)} citations"
    )

    if not citations:
        logger.warning("No citations available for report generation")
        # Return minimal report
        return self._generate_empty_report(counter_stmt, search_results, scored_docs)

    # Build prompt for report generation
    prompt = self._build_report_prompt(counter_stmt, citations)

    try:
        # Generate report using LLM
        response = self._call_llm_for_report(prompt)

        # Parse and clean response
        report_text = self._parse_report_response(response)

        # Calculate search statistics
        search_stats = {
            "documents_found": len(search_results.deduplicated_docs),
            "documents_scored": len(scored_docs),
            "documents_cited": len(set(c.doc_id for c in citations)),
            "citations_extracted": len(citations),
            "search_strategies": {
                "semantic": len(search_results.semantic_docs),
                "hyde": len(search_results.hyde_docs),
                "keyword": len(search_results.keyword_docs)
            }
        }

        # Create CounterReport
        counter_report = CounterReport(
            summary=report_text,
            num_citations=len(citations),
            citations=citations,
            search_stats=search_stats,
            generation_metadata={
                "model": self.model,
                "temperature": self.agent_config.get("temperature", 0.3),
                "timestamp": datetime.now().isoformat()
            }
        )

        logger.info(
            f"Counter-report generated: {len(report_text)} characters, "
            f"{len(citations)} citations"
        )

        return counter_report

    except Exception as e:
        logger.error(f"Counter-report generation failed: {e}", exc_info=True)
        raise RuntimeError(f"Failed to generate counter-report: {e}") from e

def _build_report_prompt(
    self, counter_stmt: CounterStatement, citations: List[ExtractedCitation]
) -> str:
    """Build prompt for counter-report generation"""

    # Format citations for prompt
    formatted_citations = []
    for i, citation in enumerate(citations, 1):
        formatted_citations.append(
            f"[{i}] {citation.passage}\n"
            f"    Source: {citation.full_citation}"
        )

    citations_text = "\n\n".join(formatted_citations)

    return f"""You are an expert medical researcher writing a systematic review section.

**Task:**
Write a concise summary (200-300 words) of the evidence that supports or relates to the following claim:

**Claim:** {counter_stmt.negated_text}

**Context:**
This claim is the counter-position to: "{counter_stmt.original_statement.text}"
You are summarizing evidence that may contradict or provide an alternative perspective on the original statement.

**Evidence Citations:**
{citations_text}

**Instructions:**
1. Synthesize the evidence into a coherent narrative
2. Reference citations using [1], [2], etc. inline
3. Use professional medical writing style
4. Include specific findings, statistics, and years when mentioned in citations
5. Do NOT use vague temporal references ("recent study") - use specific years
6. Do NOT overstate the evidence beyond what citations support
7. Do NOT add information not present in the citations
8. Organize by themes or study types if relevant
9. Note any limitations or contradictions within the evidence

**Writing Style:**
- Professional and objective tone
- Evidence-based assertions only
- Clear and concise
- Focus on findings, not methodology (unless crucial)
- Use present tense for established findings, past tense for specific studies

**Output Format:**
Write ONLY the summary text in markdown format. Do not include headers, do not add "Summary:" prefix. Just the prose with inline citations.

**Summary:**"""

def _call_llm_for_report(self, prompt: str) -> str:
    """Call Ollama API for report generation"""
    try:
        response = requests.post(
            f"{self.ollama_url}/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "temperature": self.agent_config.get("temperature", 0.3),
                "stream": False
            },
            timeout=180  # Longer timeout for report generation
        )
        response.raise_for_status()
        data = response.json()
        return data.get("response", "").strip()

    except requests.exceptions.RequestException as e:
        logger.error(f"LLM call failed: {e}")
        raise RuntimeError(f"Report generation LLM call failed: {e}") from e

def _parse_report_response(self, response: str) -> str:
    """Parse and clean LLM report response"""
    report = response.strip()

    # Remove common prefixes
    prefixes = [
        "Summary:",
        "Report:",
        "Counter-Evidence Summary:",
        "Here is the summary:"
    ]
    for prefix in prefixes:
        if report.startswith(prefix):
            report = report[len(prefix):].strip()

    # Remove markdown code blocks if present
    if report.startswith("```markdown"):
        report = report[len("```markdown"):].strip()
        if report.endswith("```"):
            report = report[:-3].strip()
    elif report.startswith("```"):
        report = report[3:].strip()
        if report.endswith("```"):
            report = report[:-3].strip()

    if len(report) < 50:
        raise ValueError("Generated report too short or empty")

    return report

def _generate_empty_report(
    self,
    counter_stmt: CounterStatement,
    search_results: SearchResults,
    scored_docs: List[ScoredDocument]
) -> CounterReport:
    """Generate minimal report when no citations are available"""

    search_stats = {
        "documents_found": len(search_results.deduplicated_docs),
        "documents_scored": len(scored_docs),
        "documents_cited": 0,
        "citations_extracted": 0,
        "search_strategies": {
            "semantic": len(search_results.semantic_docs),
            "hyde": len(search_results.hyde_docs),
            "keyword": len(search_results.keyword_docs)
        }
    }

    summary = (
        f"No substantial evidence was found in the literature database to support "
        f"the counter-claim: \"{counter_stmt.negated_text}\". "
        f"The search identified {search_stats['documents_found']} potentially relevant "
        f"documents, but none scored above the relevance threshold of {self.score_threshold}."
    )

    return CounterReport(
        summary=summary,
        num_citations=0,
        citations=[],
        search_stats=search_stats,
        generation_metadata={
            "model": self.model,
            "timestamp": datetime.now().isoformat(),
            "empty_report": True
        }
    )
```

## Report Quality Guidelines

### Good Report Characteristics:

1. **Specific**: "In a 2023 randomized controlled trial, Smith et al. found..."
2. **Quantitative**: "...reduced HbA1c by 1.5% (95% CI 1.2-1.8)"
3. **Referenced**: Every claim has an inline citation [1], [2]
4. **Objective**: Presents evidence without bias
5. **Coherent**: Flows logically, not just a list of citations

### Bad Report Characteristics:

1. **Vague**: "Recent studies have shown..." (use specific years!)
2. **Unsupported**: Claims without citations
3. **Exaggerated**: "Overwhelming evidence suggests..." (when only 2 studies)
4. **Fragmented**: Disconnected sentences without narrative flow
5. **Methodological**: Excessive detail about study methods rather than findings

## Testing Strategy

Create `tests/test_counter_report_generation.py`:

```python
"""Tests for counter-report generation"""

import pytest
from bmlibrarian.paperchecker.agent import PaperCheckerAgent
from bmlibrarian.paperchecker.data_models import (
    Statement, CounterStatement, ExtractedCitation, SearchResults, ScoredDocument
)


@pytest.fixture
def paper_checker():
    """Initialize PaperCheckerAgent"""
    return PaperCheckerAgent()


@pytest.fixture
def counter_statement():
    """Sample counter-statement"""
    original = Statement(
        text="Metformin is superior to GLP-1",
        context="",
        statement_type="finding",
        confidence=0.9,
        statement_order=1
    )

    return CounterStatement(
        original_statement=original,
        negated_text="GLP-1 is superior or equivalent to metformin",
        hyde_abstracts=["..."],
        keywords=["GLP-1", "metformin"],
        generation_metadata={}
    )


@pytest.fixture
def citations():
    """Sample citations"""
    return [
        ExtractedCitation(
            doc_id=1,
            passage="GLP-1 agonists demonstrated superior HbA1c reduction of 1.8% compared to metformin's 1.2% (p<0.001).",
            relevance_score=5,
            full_citation="Smith J, et al. GLP-1 vs Metformin Study. Diabetes Care. 2023. doi:10.1234/example",
            metadata={"pmid": 12345678, "year": 2023},
            citation_order=1
        ),
        ExtractedCitation(
            doc_id=2,
            passage="Meta-analysis of 20 trials showed GLP-1 associated with better cardiovascular outcomes (HR 0.85, 95% CI 0.75-0.95).",
            relevance_score=4,
            full_citation="Jones A, et al. GLP-1 Meta-Analysis. JAMA. 2022. doi:10.1234/another",
            metadata={"pmid": 23456789, "year": 2022},
            citation_order=2
        )
    ]


@pytest.fixture
def search_results():
    """Sample search results"""
    return SearchResults(
        semantic_docs=[1, 2, 3],
        hyde_docs=[2, 3, 4],
        keyword_docs=[3, 4, 5],
        deduplicated_docs=[1, 2, 3, 4, 5],
        provenance={
            1: ["semantic"], 2: ["semantic", "hyde"],
            3: ["semantic", "hyde", "keyword"],
            4: ["hyde", "keyword"], 5: ["keyword"]
        },
        search_metadata={}
    )


@pytest.fixture
def scored_docs():
    """Sample scored documents"""
    return [
        ScoredDocument(doc_id=1, document={}, score=5, explanation="", supports_counter=True, found_by=["semantic"]),
        ScoredDocument(doc_id=2, document={}, score=4, explanation="", supports_counter=True, found_by=["hyde"])
    ]


def test_build_report_prompt(paper_checker, counter_statement, citations):
    """Test report prompt construction"""
    prompt = paper_checker._build_report_prompt(counter_statement, citations)

    # Should contain counter-statement
    assert "GLP-1 is superior or equivalent to metformin" in prompt

    # Should contain original statement for context
    assert "Metformin is superior to GLP-1" in prompt

    # Should contain all citations
    for citation in citations:
        assert citation.passage in prompt

    # Should contain instructions
    assert "inline" in prompt.lower()
    assert "citation" in prompt.lower()


def test_generate_counter_report(
    paper_checker, counter_statement, citations, search_results, scored_docs
):
    """Test counter-report generation"""
    report = paper_checker._generate_counter_report(
        counter_statement, citations, search_results, scored_docs
    )

    # Verify structure
    assert isinstance(report.summary, str)
    assert len(report.summary) > 50
    assert report.num_citations == len(citations)
    assert len(report.citations) == len(citations)
    assert isinstance(report.search_stats, dict)

    # Verify search stats
    assert report.search_stats["documents_found"] == 5
    assert report.search_stats["documents_scored"] == 2
    assert report.search_stats["citations_extracted"] == 2

    # Verify citations are included
    assert all(c in report.citations for c in citations)


def test_report_contains_citations(
    paper_checker, counter_statement, citations, search_results, scored_docs
):
    """Test that report contains inline citations"""
    report = paper_checker._generate_counter_report(
        counter_statement, citations, search_results, scored_docs
    )

    summary = report.summary

    # Should contain inline citations [1], [2], etc.
    assert "[1]" in summary or "[2]" in summary


def test_generate_empty_report(
    paper_checker, counter_statement, search_results, scored_docs
):
    """Test generation of empty report when no citations"""
    report = paper_checker._generate_empty_report(
        counter_statement, search_results, scored_docs
    )

    assert report.num_citations == 0
    assert len(report.citations) == 0
    assert len(report.summary) > 0
    assert "no substantial evidence" in report.summary.lower()
    assert report.generation_metadata.get("empty_report") is True


def test_report_markdown_format(
    paper_checker, counter_statement, citations, search_results, scored_docs
):
    """Test that report can be converted to markdown"""
    report = paper_checker._generate_counter_report(
        counter_statement, citations, search_results, scored_docs
    )

    markdown = report.to_markdown()

    # Should contain summary
    assert report.summary in markdown

    # Should contain references section
    assert "References" in markdown or "references" in markdown

    # Should contain all citations
    for citation in citations:
        assert citation.full_citation in markdown


def test_parse_report_response(paper_checker):
    """Test parsing of LLM report responses"""
    # Test clean response
    clean = "This is a clean report with [1] citation."
    assert paper_checker._parse_report_response(clean) == clean

    # Test response with prefix
    prefixed = "Summary: This is a report with prefix."
    expected = "This is a report with prefix."
    assert paper_checker._parse_report_response(prefixed) == expected

    # Test response with code blocks
    code_blocked = "```markdown\nThis is in code block.\n```"
    expected = "This is in code block."
    assert paper_checker._parse_report_response(code_blocked) == expected

    # Test too-short response
    with pytest.raises(ValueError, match="too short"):
        paper_checker._parse_report_response("Short")
```

## Success Criteria

- [ ] Counter-report generation implemented
- [ ] Report prompt comprehensive and clear
- [ ] Professional medical writing style achieved
- [ ] Inline citations properly formatted
- [ ] Search statistics calculated correctly
- [ ] Empty report handling working
- [ ] Markdown formatting correct
- [ ] All unit tests passing
- [ ] Reports are coherent and factually accurate

## Next Steps

After completing this step, proceed to:
- **Step 10**: Verdict Analysis (10_VERDICT_ANALYSIS.md)
- Analyze counter-reports to determine if they support/contradict/undecided
