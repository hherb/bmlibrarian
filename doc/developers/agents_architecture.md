# Agents Architecture - Developer Documentation

## Overview

The BMLibrarian agents module provides a modular, extensible architecture for AI-powered biomedical literature tasks. The system is built around a common `BaseAgent` class with specialized agents for specific tasks.

## Architecture Principles

### 1. Separation of Concerns
Each agent has a single, well-defined responsibility:
- **QueryAgent**: Natural language to PostgreSQL query conversion
- **DocumentScoringAgent**: Document relevance assessment
- **Future agents**: Research summarization, citation analysis, etc.

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
└── scoring_agent.py         # Document relevance scoring

tests/
├── test_agents.py           # Comprehensive unit tests
└── test_agent.py            # Legacy QueryAgent tests

examples/
├── agents_demo.py           # Modern architecture demo
├── enhanced_agent_demo.py   # QueryAgent demo
└── agent_demo.py            # Simple QueryAgent demo

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

Agents can be composed for complex workflows:

```python
# Intelligent search with relevance scoring
query_agent = QueryAgent()
scoring_agent = DocumentScoringAgent()

# 1. Search for documents
documents = list(query_agent.find_abstracts("diabetes treatment"))

# 2. Score documents for relevance
scored_docs = scoring_agent.batch_evaluate_documents("diabetes treatment", documents)

# 3. Get top-ranked results
top_docs = scoring_agent.get_top_documents("diabetes treatment", documents, top_k=10)
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
uv run pytest tests/test_agents.py::TestQueryAgent
uv run pytest tests/test_agents.py::TestDocumentScoringAgent
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