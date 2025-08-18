# Agent Module Developer Documentation

## Overview

The `agent.py` module provides intelligent query conversion capabilities for the bmlibrarian system. It uses the Ollama library to connect to local Large Language Models (LLMs) for converting natural language questions into PostgreSQL `to_tsquery` format, optimized for biomedical literature searches.

## Architecture

### QueryAgent Class

The core component is the `QueryAgent` class which encapsulates:

- **LLM Connection**: Manages connection to Ollama server
- **Prompt Engineering**: Specialized prompts for biomedical keyword extraction
- **Query Validation**: Basic validation of generated `to_tsquery` strings
- **Error Handling**: Robust error handling for network and LLM failures

### Dependencies

- `ollama>=0.2.1`: Python client for Ollama LLM server
- `logging`: For comprehensive logging
- Standard library modules

## API Reference

### QueryAgent.__init__(model, host)

Initialize a new QueryAgent instance.

**Parameters:**
- `model` (str, optional): Ollama model name (default: "llama3.2")
- `host` (str, optional): Ollama server URL (default: "http://localhost:11434")

**Example:**
```python
agent = QueryAgent(model="mistral", host="http://localhost:11434")
```

### QueryAgent.convert_question(question)

Convert natural language question to PostgreSQL `to_tsquery` format.

**Parameters:**
- `question` (str): Natural language question about biomedical topics

**Returns:**
- `str`: PostgreSQL `to_tsquery` compatible string

**Raises:**
- `ValueError`: If question is empty or invalid
- `ConnectionError`: If unable to connect to Ollama server

**Example:**
```python
query = agent.convert_question("What are the effects of aspirin on cardiovascular disease?")
# Returns: "aspirin & (cardiovascular | cardiac | heart) & (disease | disorder | condition)"
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

## Integration Guidelines

### Database Integration
```python
from bmlibrarian.agent import QueryAgent
from bmlibrarian.database import DatabaseManager

agent = QueryAgent()
db = DatabaseManager()

# Convert question to query
question = "Effects of metformin on diabetes"
tsquery = agent.convert_question(question)

# Use in database search
results = db.search_abstracts(tsquery)
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