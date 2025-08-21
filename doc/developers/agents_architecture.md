# Agents Architecture - Developer Documentation

## Overview

The BMLibrarian agents module provides a modular, extensible architecture for AI-powered biomedical literature tasks. The system is built around a common `BaseAgent` class with specialized agents for specific tasks.

## Architecture Principles

### 1. Separation of Concerns
Each agent has a single, well-defined responsibility:
- **QueryAgent**: Natural language to PostgreSQL query conversion
- **DocumentScoringAgent**: Document relevance assessment (1-5 scale)
- **CitationFinderAgent**: Extracts relevant passages and citations from documents
- **ReportingAgent**: Synthesizes citations into medical publication-style reports
- **CounterfactualAgent**: Analyzes documents to generate contradictory evidence questions

### 2. Common Foundation
All agents inherit from `BaseAgent` which provides:
- Ollama client management and connection handling
- Standardized error handling patterns
- Callback system for progress updates and UI integration
- Model configuration and parameter management
- Connection testing utilities

### 3. Maintainability
- Each agent class is kept under 500 lines for maintainability
- Clear separation between core functionality and specialized features
- Comprehensive unit testing with mocked dependencies
- Backward compatibility layer for existing code

## Directory Structure

```
src/bmlibrarian/agents/
├── __init__.py              # Public API exports
├── base.py                  # BaseAgent abstract class
├── query_agent.py           # Natural language query conversion
├── scoring_agent.py         # Document relevance scoring
├── citation_agent.py        # Citation extraction from documents
├── reporting_agent.py       # Report synthesis and formatting
├── counterfactual_agent.py  # Counterfactual analysis for contradictory evidence
├── queue_manager.py         # SQLite-based task queue system
└── orchestrator.py          # Multi-agent workflow coordination

src/bmlibrarian/cli/         # Modular CLI architecture
├── __init__.py              # CLI module exports
├── config.py                # Configuration management
├── ui.py                    # User interface components
├── query_processing.py      # Query editing and search
├── formatting.py            # Report formatting and export
└── workflow.py              # Workflow orchestration

tests/
├── test_agents.py           # Comprehensive unit tests
├── test_query_agent.py      # Query processing tests
├── test_scoring_agent.py    # Document scoring tests
├── test_citation_agent.py   # Citation extraction tests
├── test_reporting_agent.py  # Report generation tests
└── test_counterfactual_agent.py # Counterfactual analysis tests

examples/
├── agent_demo.py            # Multi-agent workflow demo
├── citation_demo.py         # Citation extraction demo
├── reporting_demo.py        # Report generation demo
└── counterfactual_demo.py   # Counterfactual analysis demo

doc/
├── developers/
│   └── agents_architecture.md   # This document
└── users/
    └── agents_guide.md           # User-facing documentation
```

## Base Agent Class

### Abstract Base Class Design

```python
from abc import ABC, abstractmethod
from typing import Optional, Callable

class BaseAgent(ABC):
    def __init__(self, model: str, host: str, temperature: float, top_p: float, callback: Optional[Callable]):
        # Common initialization
    
    @abstractmethod
    def get_agent_type(self) -> str:
        """Must be implemented by subclasses"""
        pass
    
    # Common functionality
    def test_connection(self) -> bool: ...
    def get_available_models(self) -> list[str]: ...
    def _make_ollama_request(self, messages: list, **options) -> str: ...
    def _call_callback(self, step: str, data: str) -> None: ...
```

### Key Features

1. **Standardized Ollama Integration**
   - Consistent client initialization and configuration
   - Error handling for connection issues and response errors
   - Model availability checking

2. **Callback System**
   - Progress updates for UI integration
   - Error-tolerant callback execution
   - Step-based progress tracking

3. **Configuration Management**
   - Model parameters with sensible defaults
   - Option overrides for specific requests
   - Host and model configurability

## Specialized Agents

### QueryAgent

**Purpose**: Convert natural language questions to PostgreSQL `to_tsquery` format

**Key Methods**:
- `convert_question(question: str) -> str`: Core conversion functionality
- `find_abstracts(...)`: Integrated search with database
- `_clean_quotes(query: str) -> str`: Quote handling and phrase detection
- `_validate_tsquery(query: str) -> bool`: Basic query validation

**System Prompt Strategy**:
- Domain-specific biomedical expertise
- Clear formatting rules and examples
- Focus on medical terminology and synonyms
- Consistent output format requirements

**Error Handling**:
- Input validation (empty questions)
- Ollama connection errors
- Query format validation with warnings

### DocumentScoringAgent

**Purpose**: Evaluate document relevance to user questions with scores and reasoning

**Key Methods**:
- `evaluate_document(question: str, document: Dict) -> ScoringResult`: Single document evaluation
- `batch_evaluate_documents(...)`: Efficient multi-document scoring
- `get_top_documents(...)`: Ranked selection with filtering

**Scoring System**:
- 0-5 integer scale for consistent evaluation
- Structured JSON output with score and reasoning
- Comprehensive document metadata consideration

**Response Structure**:
```python
class ScoringResult(TypedDict):
    score: int      # 0-5 relevance score
    reasoning: str  # Explanation for the score
```

### CitationFinderAgent

**Purpose**: Extract relevant passages and citations from documents that answer research questions

**Key Methods**:
- `extract_citation(question: str, document: Dict) -> Citation`: Extract single citation
- `process_scored_documents_for_citations(...)`: Batch processing with progress tracking
- `_assess_passage_relevance(...)`: Evaluate passage relevance with scoring

**Citation Structure**:
- Document metadata (title, authors, publication date)
- Specific passage text that answers the question
- Relevance score for the extracted passage
- Reasoning for why the passage is relevant

### ReportingAgent

**Purpose**: Synthesize multiple citations into cohesive medical publication-style reports

**Key Methods**:
- `synthesize_report(question: str, citations: List[Citation]) -> Report`: Generate full report
- `generate_citation_based_report(...)`: Create formatted report with references
- `format_report_output(report: Report) -> str`: Format for display or export

**Report Features**:
- Professional medical writing style
- Evidence strength assessment (Strong/Moderate/Limited/Insufficient)
- Vancouver-style reference formatting
- Methodology notes and quality controls
- Structured markdown output

### CounterfactualAgent

**Purpose**: Analyze documents and reports to generate research questions for finding contradictory evidence

**Key Methods**:
- `analyze_document(content: str, title: str) -> CounterfactualAnalysis`: Identify claims and generate questions
- `find_contradictory_literature(...)`: Search for studies that contradict findings
- `_prioritize_questions(...)`: Rank questions by importance (High/Medium/Low)

**Analysis Features**:
- Identifies main claims in documents/reports
- Generates targeted research questions to find contradictory evidence
- Prioritizes questions by potential impact on conclusions
- Optionally searches database for opposing studies
- Provides confidence level recommendations

**Response Structure**:
```python
class CounterfactualAnalysis(TypedDict):
    document_title: str
    main_claims: List[str]
    counterfactual_questions: List[CounterfactualQuestion]
    overall_assessment: str
    confidence_level: str
```

## Integration Patterns

### Database Integration

Agents integrate seamlessly with the database layer:

```python
from bmlibrarian.agents import QueryAgent
from bmlibrarian.database import find_abstracts

# QueryAgent calls database functions directly
query_agent = QueryAgent()
for doc in query_agent.find_abstracts("COVID vaccines"):
    print(doc['title'])
```

### Combined Workflows

Agents can be composed for complete research workflows:

```python
# Complete research workflow with all agents
from bmlibrarian.agents import (
    QueryAgent, DocumentScoringAgent, CitationFinderAgent, 
    ReportingAgent, CounterfactualAgent
)

query_agent = QueryAgent()
scoring_agent = DocumentScoringAgent()
citation_agent = CitationFinderAgent()
reporting_agent = ReportingAgent()
counterfactual_agent = CounterfactualAgent()

question = "What are the cardiovascular benefits of exercise?"

# 1. Search for documents
documents = list(query_agent.find_abstracts(question))

# 2. Score documents for relevance
scored_docs = scoring_agent.batch_evaluate_documents(question, documents)

# 3. Extract citations from high-scoring documents
high_scoring = [(doc, result) for doc, result in scored_docs if result['score'] > 3]
citations = citation_agent.process_scored_documents_for_citations(
    user_question=question,
    scored_documents=high_scoring
)

# 4. Generate comprehensive report
report = reporting_agent.synthesize_report(question, citations)

# 5. Optional: Analyze for contradictory evidence
formatted_report = reporting_agent.format_report_output(report)
counterfactual_analysis = counterfactual_agent.analyze_document(
    document_content=formatted_report,
    document_title=f"Research Report: {question}"
)

# 6. Optionally search for contradictory studies
if counterfactual_analysis:
    contradictory_results = counterfactual_agent.find_contradictory_literature(
        document_content=formatted_report,
        document_title=f"Research Report: {question}",
        query_agent=query_agent,
        scoring_agent=scoring_agent,
        citation_agent=citation_agent
    )
```

### Callback Integration

Progress callbacks enable UI integration:

```python
def progress_callback(step: str, data: str):
    print(f"[{step}] {data}")

agent = QueryAgent(callback=progress_callback)
results = agent.find_abstracts("heart disease")  # Prints progress updates
```

## Testing Strategy

### Unit Testing Approach

1. **Mock Ollama Dependencies**
   - All tests use mocked Ollama clients
   - No external dependencies required for testing
   - Consistent, predictable responses for validation

2. **Comprehensive Coverage**
   - All public methods tested
   - Error conditions and edge cases covered
   - Backward compatibility layer tested

3. **Integration Testing**
   - Database integration tests (optional with real DB)
   - End-to-end workflow testing
   - Performance benchmarks

### Running Tests

```bash
# Run all agent tests
uv run pytest tests/test_agents.py

# Run with coverage
uv run pytest tests/test_agents.py --cov=bmlibrarian.agents

# Run specific test classes
uv run pytest tests/test_query_agent.py::TestQueryAgent
uv run pytest tests/test_scoring_agent.py::TestDocumentScoringAgent
uv run pytest tests/test_citation_agent.py::TestCitationFinderAgent
uv run pytest tests/test_reporting_agent.py::TestReportingAgent
uv run pytest tests/test_counterfactual_agent.py::TestCounterfactualAgent
```

## Import Structure

All agents are imported from the `bmlibrarian.agents` module:

```python
from bmlibrarian.agents import QueryAgent, DocumentScoringAgent, BaseAgent
```

This provides a clean, modular structure where each agent has a specific responsibility.

## Extending the Architecture

### Adding New Agents

To create a new agent:

1. **Inherit from BaseAgent**:
```python
from bmlibrarian.agents.base import BaseAgent

class ResearchAgent(BaseAgent):
    def get_agent_type(self) -> str:
        return "research_agent"
    
    def summarize_documents(self, documents: list) -> str:
        # Implementation here
        pass
```

2. **Add to __init__.py**:
```python
from .research_agent import ResearchAgent
__all__.append("ResearchAgent")
```

3. **Write Tests**:
```python
class TestResearchAgent:
    def test_summarize_documents(self):
        # Test implementation
        pass
```

### Extension Points

The architecture provides several extension points:

1. **Custom System Prompts**: Each agent can define domain-specific prompts
2. **Specialized Error Handling**: Agent-specific error types and handling
3. **Custom Callbacks**: Agent-specific progress steps and data
4. **Model Optimization**: Agent-specific model parameters and options

## Performance Considerations

### Model Selection

Choose models based on agent requirements:

- **QueryAgent**: Fast, consistent models (e.g., `llama3.2`)
- **DocumentScoringAgent**: Larger models for nuanced evaluation (e.g., `gpt-oss:20b`)
- **Future agents**: Task-specific model optimization

### Caching Strategies

Consider caching for:
- Frequent query conversions (QueryAgent)
- Document scores for identical questions (DocumentScoringAgent)
- Model responses for repeated inputs

### Batch Processing

Agents support efficient batch operations:
- `DocumentScoringAgent.batch_evaluate_documents()`
- Database streaming with configurable batch sizes
- Progress callbacks for long-running operations

## Security and Privacy

### Input Validation

All agents implement robust input validation:
- Non-empty input requirements
- Type checking for complex parameters
- SQL injection prevention through parameterized queries

### Local Processing

- All AI processing happens locally through Ollama
- No data sent to external services
- User questions and document content remain private

### Error Information

Agents are designed to avoid leaking sensitive information in error messages:
- Generic error messages for user-facing errors
- Detailed logging for debugging (with appropriate log levels)
- No raw model responses in production error outputs

## Future Roadmap

### Planned Agents

1. **ResearchAgent**: Multi-document research synthesis
2. **CitationAgent**: Citation network analysis and recommendations  
3. **SummaryAgent**: Abstract and paper summarization
4. **TrendAgent**: Research trend analysis and prediction

### Architecture Improvements

1. **Agent Orchestration**: Workflow engine for multi-agent tasks
2. **Result Caching**: Intelligent caching layer for performance
3. **Model Fallbacks**: Automatic failover between models
4. **Metrics Collection**: Usage analytics and performance monitoring

### Integration Enhancements

1. **Streaming Responses**: Real-time result streaming for UI
2. **Parallel Processing**: Concurrent agent execution
3. **Configuration Management**: Centralized agent configuration
4. **Plugin Architecture**: Third-party agent integration

This modular architecture provides a solid foundation for expanding BMLibrarian's AI capabilities while maintaining code quality, testability, and user experience.