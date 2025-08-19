# QueryAgent Module - Developer Documentation

## Overview

The `agent.py` module provides an intelligent interface for converting natural language questions into PostgreSQL to_tsquery format and searching biomedical literature databases. This module integrates Large Language Model (LLM) capabilities with database search functionality to create a seamless research experience.

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   User Input    │───▶│   QueryAgent    │───▶│   Database      │
│ Natural Language│    │                 │    │   Results       │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌─────────────────┐
                       │   Ollama LLM    │
                       │   (Local AI)    │
                       └─────────────────┘
```

### Core Components

1. **QueryAgent Class**: Main interface for query conversion and search
2. **LLM Integration**: Uses Ollama for local AI processing
3. **Database Integration**: Connects with BMLibrarian database module
4. **Callback System**: Provides hooks for UI updates and monitoring
5. **Human-in-the-Loop**: Allows manual query review and modification

### Dependencies

- `ollama>=0.2.1`: Python client for Ollama LLM server
- `logging`: For comprehensive logging
- Standard library modules

## Class Reference

### QueryAgent

```python
class QueryAgent:
    def __init__(self, model: str = "medgemma4B_it_q8:latest", host: str = "http://localhost:11434"):
        """
        Initialize the QueryAgent.
        
        Args:
            model: The name of the Ollama model to use
            host: The Ollama server host URL
        """
```

#### Key Methods

##### convert_question(question: str) -> str
Converts natural language to PostgreSQL to_tsquery format.

**Parameters:**
- `question` (str): Natural language question

**Returns:**
- `str`: PostgreSQL to_tsquery compatible string

**Raises:**
- `ValueError`: If question is empty
- `ConnectionError`: If unable to connect to Ollama

**Example:**
```python
agent = QueryAgent()
query = agent.convert_question("Effects of aspirin on heart disease")
# Returns: "aspirin & (heart | cardiac | cardiovascular) & (disease | disorder)"
```

##### find_abstracts(...) -> Generator[Dict, None, None]
Full-featured search combining query conversion with database search.

**Parameters:**
- `question` (str): Natural language question
- `max_rows` (int): Maximum results to return (default: 100)
- `use_pubmed` (bool): Include PubMed sources (default: True)
- `use_medrxiv` (bool): Include medRxiv sources (default: True)
- `use_others` (bool): Include other sources (default: True)
- `from_date` (Optional[date]): Earliest publication date
- `to_date` (Optional[date]): Latest publication date
- `batch_size` (int): Database fetch batch size (default: 50)
- `use_ranking` (bool): Enable relevance ranking (default: False)
- `human_in_the_loop` (bool): Enable human query review (default: False)
- `callback` (Optional[Callable]): Progress callback function
- `human_query_modifier` (Optional[Callable]): Query modification function

**Returns:**
- `Generator[Dict, None, None]`: Stream of document dictionaries

**Example:**
```python
for doc in agent.find_abstracts("COVID vaccine effectiveness", max_rows=10):
    print(f"{doc['title']} - {doc['publication_date']}")
```

### QueryAgent.test_connection()

Test connection to Ollama server and verify model availability.

**Returns:**
- `bool`: True if connection successful and model available

**Example:**
```python
if agent.test_connection():
    print("Ready to convert queries")
else:
    print("Ollama server or model not available")
```

### QueryAgent.get_available_models()

Retrieve list of available models from Ollama server.

**Returns:**
- `list[str]`: List of available model names

**Raises:**
- `ConnectionError`: If unable to connect to Ollama server

## Prompt Engineering

The system uses a carefully crafted system prompt that:

1. **Establishes Context**: Defines the agent as a biomedical literature search expert
2. **Provides Rules**: Clear guidelines for `to_tsquery` format generation
3. **Includes Examples**: Concrete examples of question-to-query conversion
4. **Focuses Domain**: Emphasizes biomedical terminology and concepts

### Key Prompt Elements

- **Operator Usage**: Proper use of `&` (AND) and `|` (OR) operators
- **Grouping**: Strategic use of parentheses for complex queries
- **Term Selection**: Focus on medical terminology, drug names, disease names
- **Synonym Handling**: Include alternative terms for comprehensive search

## Query Validation

The `_validate_tsquery()` method performs basic validation:

- **Balanced Parentheses**: Ensures proper nesting
- **Operator Validation**: Checks for invalid operator combinations
- **Empty Query Check**: Prevents empty or whitespace-only queries

## Error Handling Strategy

### Connection Errors
- Network connectivity issues to Ollama server
- Model not available or not loaded
- Server timeouts

### Input Validation
- Empty or invalid questions
- Malformed responses from LLM

### Response Validation
- Invalid `to_tsquery` format detection
- Warning logs for suspicious queries

## Integration Points

### Database Module Integration

The QueryAgent integrates with the `bmlibrarian.database` module:

```python
from .database import find_abstracts

# In find_abstracts method:
yield from find_abstracts(
    ts_query_str=ts_query_str,
    max_rows=max_rows,
    # ... other parameters
    plain=False  # Important: Use to_tsquery format, not plain text
)
```

### Ollama Integration

The agent uses Ollama for local LLM processing:

```python
import ollama

self.client = ollama.Client(host=host)
response = self.client.chat(
    model=self.model,
    messages=[
        {'role': 'system', 'content': self.system_prompt},
        {'role': 'user', 'content': question}
    ],
    options={
        'temperature': 0.1,  # Low temperature for consistent results
        'top_p': 0.9,
        'num_predict': 100   # Limit response length
    }
)
```

### Error Handling in Applications
```python
try:
    query = agent.convert_question(user_question)
    results = search_database(query)
except ValueError as e:
    # Handle invalid input
    return {"error": "Invalid question format"}
except ConnectionError as e:
    # Handle Ollama connection issues
    return {"error": "LLM service unavailable"}
```

## Testing

### Unit Tests
- Mock Ollama client for isolated testing
- Validate query format generation
- Error condition handling
- Input validation

### Integration Tests
- Real Ollama server connection (optional)
- End-to-end query conversion
- Performance testing with various question types

### Running Tests
```bash
# Run unit tests only
uv run pytest tests/test_agent.py -m "not integration"

# Run all tests (requires Ollama server)
uv run pytest tests/test_agent.py
```

## Configuration

### Environment Variables
The agent module doesn't directly use environment variables, but applications may configure:

- `OLLAMA_HOST`: Override default Ollama server URL
- `OLLAMA_MODEL`: Override default model name

### Model Selection
Choose models based on:
- **Performance**: Response time requirements
- **Accuracy**: Quality of biomedical keyword extraction
- **Availability**: Local vs remote model hosting

### Recommended Models
- `llama3.2`: Good balance of performance and accuracy
- `mistral`: Fast responses, good for simple queries
- `codellama`: If incorporating code-like syntax parsing

## Performance Considerations

### Response Time
- Model size affects response time
- Network latency to Ollama server
- Query complexity influences processing time

### Caching Strategies
Consider implementing caching for:
- Common question patterns
- Frequently requested queries
- Model responses for identical inputs

### Optimization
- Use low temperature (0.1) for consistent results
- Limit response length with `num_predict`
- Implement connection pooling for high-volume applications

## Security Considerations

### Input Validation
- Sanitize user input before sending to LLM
- Prevent injection attacks through malformed questions
- Validate generated queries before database execution

### Network Security
- Use HTTPS for remote Ollama connections
- Implement authentication if required
- Monitor for unusual query patterns

## Troubleshooting

### Common Issues

1. **"Import ollama could not be resolved"**
   - Run `uv sync` to install dependencies
   - Verify ollama package is in virtual environment

2. **Connection timeouts**
   - Check Ollama server status
   - Verify host URL and port
   - Ensure model is downloaded and loaded

3. **Poor query quality**
   - Try different models
   - Adjust temperature settings
   - Refine system prompt for specific use cases

### Debugging
Enable debug logging:
```python
import logging
logging.getLogger('bmlibrarian.agent').setLevel(logging.DEBUG)
```

## Future Enhancements

### Planned Features
- Query result ranking based on relevance scores
- Multi-model ensemble for improved accuracy
- Custom prompt templates for different domains
- Query optimization based on database schema
- Automatic model fallback for reliability

### Extension Points
- Custom validation rules
- Domain-specific prompt engineering
- Integration with other LLM providers
- Query performance analytics