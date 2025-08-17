# Developer Documentation

Welcome to BMLibrarian developer documentation! This section provides technical information for developers working with or contributing to BMLibrarian.

## Architecture and Design

🏗️ **[Architecture Overview](architecture.md)**
- System architecture and design principles
- Core components and their responsibilities
- Database schema and migration lifecycle
- Security model and error handling
- Performance considerations

## API Reference

📚 **[API Reference](api_reference.md)**
- Complete API documentation
- Class and method references
- Usage examples and patterns
- Error handling and exceptions
- Environment configuration

## Contributing

🤝 **[Contributing Guide](contributing.md)**
- Development environment setup
- Coding standards and guidelines
- Testing requirements and procedures
- Pull request process
- Release workflow

## Development Quick Start

### Setup Development Environment

```bash
# Clone repository
git clone <repository-url>
cd bmlibrarian

# Install dependencies
uv sync

# Run tests
uv run pytest tests/
```

### Project Structure

```
bmlibrarian/
├── src/bmlibrarian/          # Main package
│   ├── __init__.py          # Package exports
│   ├── migrations.py        # Migration management
│   ├── cli.py              # CLI interface
│   └── app.py              # App integration
├── tests/                   # Test suite
├── doc/                     # Documentation
└── baseline_schema.sql     # Database schema
```

### Testing

```bash
# Run all tests with coverage
uv run pytest tests/ --cov=src/bmlibrarian

# Run specific test categories
uv run pytest tests/test_migrations.py  # Migration tests
uv run pytest tests/test_cli.py         # CLI tests
uv run pytest tests/test_app.py         # App tests
```

Current test coverage: **98.43%**

## Key Development Areas

### Migration System Core
- **File**: `src/bmlibrarian/migrations.py`
- **Purpose**: Database migration management
- **Key Classes**: `MigrationManager`

### CLI Interface
- **File**: `src/bmlibrarian/cli.py`
- **Purpose**: Command-line interface
- **Key Functions**: `create_parser()`, `main()`

### Application Integration
- **File**: `src/bmlibrarian/app.py`
- **Purpose**: Python API integration
- **Key Functions**: `initialize_app()`, `get_database_connection()`

## Development Guidelines

### Code Quality
- Follow PEP 8 style guidelines
- Use type hints for all functions
- Write comprehensive docstrings
- Maintain test coverage above 80%

### Testing Strategy
- Unit tests for all public methods
- Integration tests for database operations
- CLI tests for command-line interface
- Mock external dependencies

### Documentation
- Update user docs for user-facing changes
- Update API docs for code changes
- Include examples in docstrings
- Maintain architecture documentation

## Advanced Topics

### Extension Points
- Custom migration directories
- Environment-specific configurations
- Database connection customization
- CLI command extensions

### Performance Optimization
- Connection management patterns
- Migration performance considerations
- Memory usage optimization
- Concurrent operation handling

### Security Considerations
- Credential management best practices
- SQL injection prevention
- Database permission models
- Network security patterns

## Debugging and Maintenance

### Debugging Tools
```python
# Enable debug logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Inspect migration state
manager._get_applied_migrations()
manager._database_exists("database_name")
```

### Common Development Tasks
- Adding new CLI commands
- Extending MigrationManager functionality
- Writing integration tests
- Updating documentation

## Getting Help

- **Architecture Questions**: Review the [Architecture Guide](architecture.md)
- **API Usage**: Check the [API Reference](api_reference.md)
- **Contribution Process**: See the [Contributing Guide](contributing.md)
- **Testing Issues**: Refer to test documentation in contributing guide

---

Start with the [Architecture Overview](architecture.md) to understand the system design, then check the [API Reference](api_reference.md) for detailed technical information.