# Citation Finder System

This document describes the BMLibrarian citation finder system for extracting verifiable citations from scored documents to support evidence-based reporting.

## Overview

The Citation Finder Agent processes documents that exceed a specified relevance score threshold to extract specific passages that answer user questions. It builds a queue of verifiable citations that can be used by reporting agents to synthesize evidence-based responses with proper references.

## Architecture

### Core Components

1. **CitationFinderAgent**: Main agent class for citation extraction
2. **Citation**: Data structure representing extracted citations
3. **Queue Integration**: Memory-efficient processing via SQLite queues
4. **Document Verification**: Ensures citation integrity and prevents hallucination

### Citation Data Structure

```python
@dataclass
class Citation:
    passage: str              # Exact text from document
    summary: str              # Brief explanation of relevance
    relevance_score: float    # 0-1 confidence score
    document_id: str          # Verified database document ID
    document_title: str       # Document title
    authors: List[str]        # Author list
    publication_date: str     # Publication date
    pmid: Optional[str]       # PubMed ID if available
    created_at: datetime      # Citation creation timestamp
```

### Processing Workflow

```
Scored Documents → Threshold Filter → Citation Extraction → Verification → Citation Queue
```

1. **Input**: Documents with relevance scores from DocumentScoringAgent
2. **Filtering**: Only process documents above score threshold (e.g., >2.0)
3. **Extraction**: Use LLM to identify relevant passages and create summaries
4. **Verification**: Ensure document IDs match database records
5. **Output**: Queue of verified citations for reporting

## Key Features

### 1. Threshold-Based Processing

Only documents exceeding a configurable score threshold are processed:

```python
citations = citation_agent.process_scored_documents_for_citations(
    user_question="What is COVID-19 vaccine effectiveness?",
    scored_documents=scored_docs,
    score_threshold=2.0,      # Only process docs scoring > 2.0
    min_relevance=0.7         # Only accept citations with relevance ≥ 0.7
)
```

### 2. LLM-Based Passage Extraction

Uses structured prompts to extract relevant passages:

```python
prompt = f"""Extract the most relevant passage from this abstract that answers: "{question}"

Response format (JSON):
{{
    "relevant_passage": "exact text from abstract",
    "summary": "brief explanation of relevance", 
    "relevance_score": 0.8,
    "has_relevant_content": true
}}"""
```

### 3. Document ID Verification

Document IDs are programmatically assigned from database records to prevent:
- Hallucinated references
- Malformed citations
- Non-existent document references

### 4. Queue-Based Processing

Supports memory-efficient processing of large document sets:

```python
# Process citations via queue system
for doc, citation in citation_agent.process_citation_queue(
    user_question=question,
    scored_documents=large_document_set,
    batch_size=25
):
    if citation:
        verified_citations.append(citation)
```

## API Reference

### CitationFinderAgent Methods

#### Core Citation Extraction

```python
def extract_citation_from_document(self, user_question: str, 
                                 document: Dict[str, Any], 
                                 min_relevance: float = 0.7) -> Optional[Citation]
```
Extract citation from single document with relevance filtering.

#### Batch Processing

```python
def process_scored_documents_for_citations(self, user_question: str,
                                         scored_documents: List[Tuple[Dict, Dict]],
                                         score_threshold: float = 2.0,
                                         min_relevance: float = 0.7) -> List[Citation]
```
Process multiple scored documents to extract qualifying citations.

#### Queue Integration

```python
def submit_citation_extraction_tasks(self, user_question: str,
                                   scored_documents: List[Tuple[Dict, Dict]],
                                   score_threshold: float = 2.0,
                                   priority: TaskPriority = TaskPriority.NORMAL) -> Optional[List[str]]
```
Submit citation extraction tasks to the processing queue.

```python
def process_citation_queue(self, user_question: str,
                         scored_documents: List[Tuple[Dict, Dict]],
                         score_threshold: float = 2.0,
                         batch_size: int = 25) -> Iterator[Tuple[Dict, Optional[Citation]]]
```
Memory-efficient citation processing using queue system.

#### Statistics and Analysis

```python
def get_citation_stats(self, citations: List[Citation]) -> Dict[str, Any]
```
Generate statistics about extracted citations including:
- Total citations and unique documents
- Average, min, max relevance scores
- Publication date ranges
- Citations per document ratio

## Implementation Details

### LLM Integration

The system uses Ollama for citation extraction with:
- **Low temperature** (0.1) for consistent extraction
- **Structured JSON responses** for reliable parsing
- **Timeout handling** for robust processing
- **Error recovery** for failed extractions

### Queue Processing

Citations integrate with the existing queue system:

```python
# Task submission
task_ids = citation_agent.submit_citation_extraction_tasks(
    user_question=question,
    scored_documents=qualifying_docs,
    priority=TaskPriority.HIGH
)

# Result collection
results = orchestrator.wait_for_completion(task_ids, timeout=60.0)
```

### Memory Efficiency

Large document sets are processed in configurable batches:
- **Batch processing**: Process documents in chunks (default 25)
- **Streaming results**: Yield citations as they're processed
- **Queue persistence**: Tasks persist across process restarts
- **Progress tracking**: Optional progress callbacks

## Usage Examples

### Basic Citation Extraction

```python
from bmlibrarian.agents import CitationFinderAgent

# Initialize agent
citation_agent = CitationFinderAgent(orchestrator=orchestrator)

# Process scored documents
citations = citation_agent.process_scored_documents_for_citations(
    user_question="What are the side effects of drug X?",
    scored_documents=scored_docs,
    score_threshold=2.5,
    min_relevance=0.8
)

# Display citations
for citation in citations:
    print(f"Document: {citation.document_title}")
    print(f"Passage: {citation.passage}")
    print(f"Summary: {citation.summary}")
    print(f"Relevance: {citation.relevance_score:.2f}")
    print(f"Reference: {citation.document_id}")
```

### Queue-Based Processing

```python
# Process large dataset efficiently
all_citations = []

def progress_callback(current, total):
    print(f"Progress: {current}/{total} ({current/total*100:.1f}%)")

for doc, citation in citation_agent.process_citation_queue(
    user_question=question,
    scored_documents=large_scored_dataset,
    score_threshold=2.0,
    progress_callback=progress_callback,
    batch_size=50
):
    if citation:
        all_citations.append(citation)

print(f"Extracted {len(all_citations)} citations")
```

### Integration with Scoring Workflow

```python
# Complete workflow: Query → Score → Cite
documents = query_agent.search_documents(user_query)

# Score documents for relevance
scored_docs = []
for doc in documents:
    score = scoring_agent.score_document_relevance(user_question, doc)
    if score:
        scored_docs.append((doc, score))

# Extract citations from high-scoring documents
citations = citation_agent.process_scored_documents_for_citations(
    user_question=user_question,
    scored_documents=scored_docs,
    score_threshold=3.0
)

# Generate report with verified citations
report_agent.generate_evidence_based_report(user_question, citations)
```

## Configuration

### Agent Initialization

```python
citation_agent = CitationFinderAgent(
    orchestrator=orchestrator,      # Required for queue processing
    ollama_url="http://localhost:11434",  # Ollama service URL
    model="gpt-oss:20b"            # LLM model for extraction (default)
)
```

### Processing Parameters

- **score_threshold**: Minimum document score to process (default: 2.0)
- **min_relevance**: Minimum citation relevance to accept (default: 0.7)
- **batch_size**: Queue processing batch size (default: 25)
- **timeout**: Task completion timeout (default: 60s)

## Quality Control

### Relevance Filtering

Citations undergo multiple quality checks:

1. **Document Score Filter**: Only high-scoring documents processed
2. **LLM Relevance Score**: Each citation rated 0-1 for relevance
3. **Minimum Threshold**: Only citations above threshold accepted
4. **Passage Validation**: Extracted text must exist in source document

### Passage Validation (exact source text)

`CitationFinderAgent._validate_and_extract_exact_match()` delegates to
`bmlibrarian.utils.passage_match.find_passage(passage, abstract,
CITATION_MIN_SIMILARITY)` (threshold 0.95) and returns its `PassageMatch`.
The citation stores only `PassageMatch.text`, the matched span of the
**original** abstract, so it never holds the LLM's copy of the text (the
`start`/`end` offsets are not kept on the `Citation`):

1. Both texts are normalised (typographic quotes and dashes folded to ASCII,
   ligatures and other compatibility characters decomposed, accents dropped
   but negation overlays kept so "≠" never equals "=",
   lowercase, whitespace runs collapsed) by `normalize_with_offsets()`, which
   keeps an index map back to the original.
2. Exact substring of the normalised passage → similarity 1.0 and
   `PassageMatch.exact` (counted in `exact_matches`). The span may start or
   end mid-word; the citation agent then rejects it unless it is complete
   sentences (see "Rejections and errors").
3. A passage longer than `len(text) * (2-s)/s` cannot reach threshold `s`
   against any window (`fits_text()`), so it is rejected without a search.
4. Otherwise **seed voting**: the passage is cut into seeds of length
   `len(P) // (max_edit_points + 1)` (minimum 4). A window scoring ≥ s can
   hold at most `2P(1-s)/s` edit points, so at least one seed survives
   intact and votes (via `str.find`) for the true alignment offset. Seeds
   occurring more than 64 times are ignored, and only the five best-supported
   offsets are examined, so very repetitive text can hide the true location.
5. For each offset, one `SequenceMatcher(autojunk=False)` alignment against
   the surrounding text estimates where the passage starts and ends. Offsets
   whose alignment matches too few characters to reach `s` are not refined.
   The others are refined by moving the window start, then the end, over
   the word boundaries near those estimates. Fuzzy matches therefore start
   and end on word boundaries: a quote of "3% per year" is not matched
   inside "2.13% per year", which would misquote the number. The search is
   local, so the result is the best window found, not a proven optimum.

Measured on prose at threshold 0.95, a fuzzy quote of one or two sentences
takes 2–10 ms, a 1 kB quote about 0.1 s and a 2 kB quote up to about 2 s.
A quote that does not match costs about the same or less. The cost hardly
depends on the abstract length. The previous sliding-window search took 31 s
on a 1 kB abstract, mapped the match start back with a per-word drift, and
appended whole extra sentences to the result.

`tests/test_passage_match.py` compares `find_passage()` with an exhaustive
search over every word-boundary window on 60 seeded random edits
(`test_matches_exhaustive_search_on_random_edits`).

#### Rejections and errors

Each LLM response goes through `_check_response()`. A response that cannot
be verified is retried (up to `max_retries` times) and, on the final attempt,
recorded in `get_validation_stats()['failed_citations']` with a `reason`
(`REJECT_*` constants in `citation_agent.py`):

| Reason | Cause |
|---|---|
| `response is not a JSON object` | The parsed JSON is a list, string, … |
| `relevance_score is not a number` | Missing numbers default to 0.0 (not relevant); text such as `"high"` is rejected |
| `passage is missing or not text` | `relevant_passage` is absent, null or not a string |
| `passage is empty` | Only whitespace |
| `passage not found in abstract` | No candidate span at all (similarity 0.0), including a passage too long for the abstract |
| `passage similarity below threshold` | A paraphrase or near miss |
| `passage is not one or more complete sentences` | The matched span is a term, a clause, or starts/ends mid-sentence, and cannot be widened to its sentence (see below) |
| `passage is a fragment that occurs more than once in the abstract; quote the complete sentence` | A fragment that could be widened, but its text occurs more than once, so which sentence the model meant is a guess |
| `summary is missing or not text` | The passage matched but `summary` is unusable |

**Complete sentences (#289).** After `find_passage()` locates the span,
`utils/sentence_bounds.complete_sentence_span(abstract, start, end)` must
confirm that the span runs from a sentence start to a sentence end. Without
that check, verbatim matches such as `"a"`, `"Aspirin"` or `"spirin reduces"`
(exact matches may start mid-word) were stored as verified citations; such
fragments are now widened to their sentence when that is certain (see
below). Only
surrounding whitespace is trimmed and closing punctuation the model omitted
is appended from the abstract: closing brackets and quotes, `.`/`!`/`?`, and
Markdown `*`. A trailing closing mark without its opening mark inside the
span is dropped again, so no unbalanced bracket, quote or `**` is stored.
The stored passage is that span of the abstract, so it can be a few
characters longer than `PassageMatch.text` (or, when widened, up to
`MAX_WIDENING_CHARS` longer) (whose offsets `_ResponseCheck`
keeps unchanged in `match`). Ambiguous boundaries count as non-boundaries,
so a doubtful passage is rejected rather than accepted: a line break or the
end of the text without punctuation never ends a sentence, a full stop after
an initial ("U.S.", "J. M. Smith") is not an end, and label-only or one-word
spans are rejected. Five exceptions accept real sentences the conservative
rules lost (#303): single-capital designators ("type B."), all-caps tokens
that spell an abbreviation, before a capitalised word ("clinical CA. The"),
"et al." before a capitalised word, time units ("3 min. Then"), and
sentences or labels glued without a space ("DAPT.The",
"Conclusion:Pre-operative", but not "p.Val600Glu" or
"www.ClinicalTrials.gov"); invisible format characters count as whitespace
(#302). The rules are in `doc/llm/sentence_bounds.md`. Measured
on 500 random PubMed abstracts with the first version of the rules: 0 of
6,768 mid-sentence fragments were accepted, and 0.6% of naively split
sentences were rejected, most of them correctly (splits at "vs." or "i.e.").
The PR #298 review tightened the rules (line breaks, initials, single words)
and relaxed one (gene/molecule names such as "p53" or "mRNA" may start a
sentence); the figures were not re-measured. After the #303 changes, on a
different 500-abstract sample, no fragment was accepted that the previous
rules rejected, and naive sentences were accepted 94.9% of the time (94.3%
before).

**Widening fragments (owner decision, 2026-10-19).** When the matched span
is not complete sentences, `_check_response` widens it with
`sentence_bounds.enclosing_sentence_span()`: back to the nearest sentence
start, forward to the nearest sentence end, then `complete_sentence_span()`
again. The citation stores the abstract's enclosing sentence(s);
`Citation.widened_from` keeps the matched fragment (`PassageMatch.text`),
`get_validation_stats()['widened_passages']` counts them, each one is
logged, and the batch summary reports them ("2 widened from a fragment to
complete sentences"). The model's `summary` and `relevance_score` are kept
as they are. The log line gives the match kind, similarity, matched
fragment and the model's own text. `widened_from` also survives the queue
path (`extract_citation_from_queue` / `process_citation_queue`). A fragment is rejected with
`REJECT_AMBIGUOUS_FRAGMENT` when its text occurs more than once in the
abstract (`passage_match.occurs_once`, which compares the way `find_passage`
does: case, whitespace, invisible characters and typography are ignored; the
intended sentence would be a guess), and with `REJECT_INCOMPLETE_SENTENCE`
when no
sentence boundary lies within `MAX_WIDENING_CHARS` (400) added characters,
when its sentence is broken off (a new sentence starts before it ends:
lost text, a heading without punctuation), or when the widened span is not
citable (a label, too few words). Measured on 2,229 comma-cut fragments of
500 random PubMed abstracts: 2,206 widen to exactly the sentence they were cut from, 22 are rejected, 1 also
takes in a neighbouring sentence. An LLM re-run (`gpt-oss:20b`) of the 106
(statement, document) pairs of #303 accepted 96 (64 before), with no
fragment rejections left (31 before) and 10 below the similarity threshold.
Six of the 96 are verbatim multi-sentence quotes that contain a
sentence broken off by lost text; they are accepted as they are (owner
decision, #307: rejecting them would lose evidence). The fact-checker does not add a
degradation note for widened passages (`degradation_notes` mean evidence
that could not be examined); the widening is in the log and the stats.

**Stored and shown (migration 035, #310).** `widened_from` is persisted in
`audit.extracted_citations.widened_from` (`CitationTracker.record_citation`)
and `factcheck.evidence.widened_from` (`EvidenceReference` → `Evidence`),
both nullable TEXT (NULL = quoted whole, or stored before 035). It travels
into SQLite review packages (`export_review_package.py`; older packages
without the column read as NULL), fact-checker JSON (the agent's results
JSON via `EvidenceReference.to_dict` omits the key when NULL; the DB's
`export_to_json` always writes it, `null` when not widened; both import) and the CLI citation CSV/JSON
exports. Where a passage is displayed, `card_utils.widened_note()` marks it:
the research tab's citation cards and the audit validation GUI. The
fact-checker review GUI does not show cited passages at all, so it has
nothing to mark yet.

Two sentence-start rules were added with it for damaged source text: a
section label fused onto the next word ("unclear.ObjectiveThis study",
#304) and text the source lost, which leaves a double space or "( " before a
capitalised word ("…(all  Women with…"). On the 500-abstract sample this
accepted no fragment the previous rules rejected.

On a retry after a rejection, the prompt names the reason, with the
similarity for a below-threshold passage, and quotes the rejected passage,
cut at 200 characters and marked with "…" (`_retry_note`, #290; a non-text
answer is not quoted), so the model is not sent the identical request again.

A response with `has_relevant_content: false`, or a relevance score below
`min_relevance`, ends extraction for that document without a retry. A
document whose abstract is missing or only whitespace is skipped before any
LLM call. An unreachable or timed-out LLM server (the connection check, or a
request raising `ConnectionError`/`TimeoutError`) is retried with
exponential backoff (`transient_retry_attempts`, `transient_retry_base_delay`;
see `doc/developers/transient_retry.md`) before it counts as an error.

Unexpected exceptions are logged with their traceback (`logger.exception`),
counted in `get_validation_stats()['errors']`, and not retried. The `errors`
count also includes a connection check or LLM request that still failed
after the backoff retries, a request that raised `ValueError`, and output
that could not be parsed as JSON after the retries. Each counted document is
also listed in `get_validation_stats()['errored_documents']`
(`{'document_id', 'error'}`). Callers use these to tell "this document has
no relevant passage" from "this document could not be examined". The
fact-checker treats a document that errored, or whose passages were all
rejected, as a failure rather than as missing evidence (see
`fact_checker_system.md`, "Failure handling").

Both batch methods (`process_scored_documents_for_citations` and
`extract_citations_with_audit`) end with a `citation_extraction_completed`
callback whose message gives the widened passages, the rejections broken
down by reason and the number of errors, e.g. `Extracted 1 citations from 3
documents (1 widened from a fragment to complete sentences; 2 rejected:
passage not found in abstract ×1, passage is not one or more complete
sentences ×1)`. The message comes from the public `extraction_summary()`.
Callers that extract one document at a time call it themselves with the
`failed_citations` length and `errors` count taken before the batch: the Qt
research tab's `WorkflowThread._extract_citations_progressive` (shown in the
Citations tab via its `citation_summary` signal and in the progress line,
prefixed ⚠️ instead of ✓ when passages were rejected or documents failed; a
failure in the thread's own per-document code is counted with the public
`record_error()`),
and the CLI's `WorkflowExecutionManager.execute_citation_extraction` prints
it after `process_scored_documents_for_citations`.

Tests: `tests/test_passage_match.py`, `tests/test_citation_validation.py`,
`tests/test_qt_workflow_thread.py` (`test_citation_summary_*`, `test_run_*`),
`tests/test_qt_research_signal_wiring.py::test_citation_summary_reaches_citations_tab`.

### Document Verification

Document IDs are verified to ensure:
- **Database Existence**: ID exists in literature database
- **Proper Format**: ID follows expected format patterns
- **No Hallucination**: Prevents fabricated document references

### Error Handling

Robust error handling for:
- **Network Failures**: Ollama service unavailable
- **Malformed Responses**: Invalid JSON from LLM
- **Missing Data**: Documents without abstracts
- **Processing Timeouts**: Long-running extractions

## Performance Considerations

### Scaling Factors

Processing time depends on:
- **Document Count**: Linear scaling with queue batching
- **Abstract Length**: Longer abstracts take more processing
- **Model Performance**: Faster models reduce latency
- **Network Latency**: Local Ollama faster than remote

### Optimization Strategies

1. **Batch Processing**: Process documents in parallel batches
2. **Score Pre-filtering**: Only process high-scoring documents
3. **Model Selection**: Use faster models like `medgemma4B_it_q8:latest` for speed
4. **Caching**: Cache similar extractions (not currently implemented)
5. **Queue Persistence**: Resume processing after interruptions

### Monitoring

Track key metrics:
- **Processing Rate**: Documents per second
- **Citation Yield**: Citations per processed document
- **Quality Scores**: Average relevance scores
- **Error Rates**: Failed extractions per batch

## Integration Points

### Upstream Dependencies

- **QueryAgent**: Provides initial document search
- **DocumentScoringAgent**: Provides relevance scores
- **PostgreSQL Database**: Source of truth for document metadata

### Downstream Consumers

- **ReportingAgent**: Uses citations to generate evidence-based reports
- **SummaryAgent**: Creates summaries with proper citations
- **ExportAgent**: Formats citations for external systems

### Queue System Integration

- **QueueManager**: Handles task persistence and scheduling
- **AgentOrchestrator**: Coordinates multi-agent workflows
- **Recovery System**: Handles process interruptions and failures

## Security Considerations

### Data Integrity

- **Document ID Verification**: Prevents citation of non-existent documents
- **Source Attribution**: All citations traceable to database records
- **Audit Trail**: Citation creation timestamps and process tracking

### Privacy

- **No Data Logging**: Citations not logged to external systems
- **Local Processing**: All LLM processing happens locally via Ollama
- **Secure Storage**: Queue database uses SQLite with proper permissions

## Future Enhancements

### Planned Improvements

1. **Semantic Similarity**: Use embeddings for better passage matching
2. **Multi-language Support**: Extract citations from non-English papers
3. **Citation Clustering**: Group similar citations from different papers
4. **Quality Learning**: Improve extraction based on user feedback
5. **Export Formats**: Support multiple citation formats (APA, MLA, etc.)

### Advanced Features

1. **Citation Networks**: Build citation relationship graphs
2. **Temporal Analysis**: Track how findings evolve over time
3. **Contradiction Detection**: Identify conflicting findings
4. **Evidence Synthesis**: Automatically synthesize multiple citations
5. **Interactive Refinement**: Allow users to refine extraction criteria