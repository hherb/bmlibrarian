# Contributing to BMLibrarian

Thank you for your interest in contributing to BMLibrarian! This guide will help you get started with development and contributing to the project.

## Development Setup

### Prerequisites

- Python 3.12 or higher
- PostgreSQL 12 or higher with pgvector extension
- Git for version control
- `uv` for dependency management (recommended) or `pip`

### Getting Started

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd bmlibrarian
   ```

2. **Set up development environment:**
   ```bash
   # Using uv (recommended)
   uv sync
   
   # Or using pip
   pip install -e .[dev]
   ```

3. **Set up test database:**
   ```bash
   createdb bmlibrarian_test
   # Set up test environment variables
   export POSTGRES_USER=your_username
   export POSTGRES_PASSWORD=your_password
   export POSTGRES_DB=bmlibrarian_test
   ```

4. **Run tests to verify setup:**
   ```bash
   uv run pytest tests/
   ```

## Development Workflow

### Code Organization

```
bmlibrarian/
├── src/bmlibrarian/          # Main package code
│   ├── __init__.py          # Package initialization
│   ├── migrations.py        # Migration management
│   ├── cli.py              # Command-line interface
│   └── app.py              # Application integration
├── tests/                   # Test suite
│   ├── test_migrations.py   # Migration tests
│   ├── test_cli.py         # CLI tests
│   ├── test_app.py         # App integration tests
│   └── conftest.py         # Test fixtures
├── doc/                    # Documentation
│   ├── users/              # End-user documentation
│   └── developers/         # Developer documentation
└── baseline_schema.sql     # Database baseline schema
```

### Coding Standards

**Python Style:**
- Follow PEP 8 style guidelines
- Use type hints for all function signatures
- Maximum line length: 88 characters (Black formatter)
- Use descriptive variable and function names

**Example:**
```python
def initialize_database(self, baseline_schema_path: Path) -> None:
    """Initialize database with baseline schema.
    
    Args:
        baseline_schema_path: Path to the baseline SQL schema file
        
    Raises:
        FileNotFoundError: If baseline schema file doesn't exist
        DatabaseError: If database initialization fails
    """
    baseline_schema_path = Path(baseline_schema_path)
    
    if not baseline_schema_path.exists():
        raise FileNotFoundError(f"Baseline schema file not found: {baseline_schema_path}")
```

**Documentation Standards:**
- Use Google-style docstrings
- Include type information in docstrings
- Document all public methods and classes
- Provide usage examples for complex functionality

### Testing Requirements

**Test Coverage:**
- Minimum 80% code coverage (current: 98%+)
- All new features must include comprehensive tests
- Test both happy path and error conditions

**Test Categories:**

1. **Unit Tests** (`test_*.py`):
   ```python
   def test_calculate_checksum(self):
       """Test checksum calculation."""
       manager = MigrationManager(...)
       content = "CREATE TABLE test (id INT);"
       expected = hashlib.sha256(content.encode('utf-8')).hexdigest()
       
       result = manager._calculate_checksum(content)
       
       assert result == expected
   ```

2. **Integration Tests** (marked with `@pytest.mark.integration`):
   ```python
   @pytest.mark.integration
   def test_full_migration_workflow(self):
       """Test complete migration workflow with real database."""
       # Tests that require actual database connection
   ```

3. **CLI Tests**:
   ```python
   def test_cli_command_parsing(self):
       """Test CLI argument parsing."""
       parser = create_parser()
       args = parser.parse_args(["migrate", "init", "--host", "localhost"])
       assert args.command == "migrate"
   ```

**Running Tests:**
```bash
# Run all tests
uv run pytest tests/

# Run with coverage
uv run pytest tests/ --cov=src/bmlibrarian --cov-report=html

# Run specific test file
uv run pytest tests/test_migrations.py

# Run tests with specific markers
uv run pytest tests/ -m "not integration"  # Skip integration tests
```

### Code Quality Tools

**Automatic Formatting:**
```bash
# Format code with Black
black src/ tests/

# Sort imports with isort
isort src/ tests/

# Type checking with mypy
mypy src/bmlibrarian/
```

**Linting:**
```bash
# Lint with flake8
flake8 src/ tests/

# Security check with bandit
bandit -r src/
```

**Pre-commit Hooks** (recommended):
```bash
pip install pre-commit
pre-commit install
```

## Feature Development

### Adding New Features

1. **Create Feature Branch:**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Design Phase:**
   - Document the feature requirements
   - Update architecture documentation if needed
   - Consider backward compatibility

3. **Implementation:**
   - Write code following style guidelines
   - Add comprehensive tests
   - Update documentation

4. **Testing:**
   ```bash
   # Run tests
   uv run pytest tests/
   
   # Check coverage
   uv run pytest tests/ --cov=src/bmlibrarian
   
   # Test CLI functionality
   uv run bmlibrarian --help
   ```

5. **Documentation:**
   - Update user documentation if user-facing changes
   - Update developer documentation for API changes
   - Add docstrings to new code

### Migration System Extensions

**Adding New CLI Commands:**

1. **Update CLI Parser** (`src/bmlibrarian/cli.py`):
   ```python
   # Add new subcommand
   new_parser = migrate_subparsers.add_parser("your_command", help="Description")
   new_parser.add_argument("--option", help="Option help")
   ```

2. **Implement Command Logic:**
   ```python
   elif args.migrate_action == "your_command":
       # Implementation here
       pass
   ```

3. **Add Tests:**
   ```python
   def test_your_command(self):
       """Test new command functionality."""
       # Test implementation
   ```

**Adding Migration Manager Methods:**

1. **Add Method** (`src/bmlibrarian/migrations.py`):
   ```python
   def your_new_method(self, param: Type) -> ReturnType:
       """Description of what the method does.
       
       Args:
           param: Description of parameter
           
       Returns:
           Description of return value
           
       Raises:
           ExceptionType: When this exception occurs
       """
       # Implementation
   ```

2. **Add Tests:**
   ```python
   def test_your_new_method(self):
       """Test your new method."""
       # Test implementation
   ```

## Database Changes

### Schema Modifications

**Updating Baseline Schema:**
1. Modify `baseline_schema.sql` carefully
2. Consider impact on existing installations
3. Document changes in migration files for existing users
4. Test with fresh database installations

**Adding New Extensions:**
```sql
-- In baseline_schema.sql or migration file
CREATE EXTENSION IF NOT EXISTS new_extension;
```

**Adding New Tables:**
```sql
-- Use defensive programming
CREATE TABLE IF NOT EXISTS new_table (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Migration File Guidelines

**Naming Convention:**
```
NNN_descriptive_name.sql
```
- `NNN`: Zero-padded sequential number (001, 002, etc.)
- `descriptive_name`: Clear description of what the migration does

**Migration Content:**
```sql
-- 001_add_user_preferences.sql
-- Add user preferences table and related indexes

BEGIN;

-- Create the table
CREATE TABLE IF NOT EXISTS user_preferences (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    preference_key VARCHAR(100) NOT NULL,
    preference_value TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, preference_key)
);

-- Add indexes for performance
CREATE INDEX IF NOT EXISTS idx_user_preferences_user_id 
ON user_preferences(user_id);

CREATE INDEX IF NOT EXISTS idx_user_preferences_key 
ON user_preferences(preference_key);

-- Add comments for documentation
COMMENT ON TABLE user_preferences IS 'Stores user-specific configuration preferences';
COMMENT ON COLUMN user_preferences.preference_key IS 'Key identifier for the preference';

COMMIT;
```

## Documentation

### User Documentation (`doc/users/`)

**When to Update:**
- New CLI commands or options
- Changed behavior that affects users
- New installation requirements
- New troubleshooting scenarios

**Style Guide:**
- Use clear, actionable language
- Include practical examples
- Provide troubleshooting steps
- Use consistent formatting

### Developer Documentation (`doc/developers/`)

**When to Update:**
- New APIs or significant changes to existing APIs
- Architecture changes
- New development processes
- Updated dependencies or requirements

**Content Guidelines:**
- Technical accuracy
- Code examples with explanations
- Architecture diagrams when helpful
- Clear section organization

### API Documentation

**Docstring Standards:**
```python
def complex_method(self, required_param: str, optional_param: int = 0) -> Dict[str, Any]:
    """Brief description of what the method does.
    
    Longer description with more details about the method's behavior,
    including any important side effects or assumptions.
    
    Args:
        required_param: Description of what this parameter does
        optional_param: Description with default value explanation
        
    Returns:
        Dictionary containing:
            - key1: Description of this key
            - key2: Description of this key
            
    Raises:
        ValueError: When required_param is empty or invalid
        DatabaseError: When database operation fails
        
    Example:
        >>> manager = MigrationManager(...)
        >>> result = manager.complex_method("valid_input")
        >>> print(result['key1'])
        expected_output
    """
```

## Pull Request Process

### Before Submitting

**Checklist:**
- [ ] All tests pass locally
- [ ] Code coverage meets requirements (80%+)
- [ ] Code follows style guidelines
- [ ] Documentation updated for user-facing changes
- [ ] API documentation updated for code changes
- [ ] No security vulnerabilities introduced

**Quality Checks:**
```bash
# Run full test suite
uv run pytest tests/ --cov=src/bmlibrarian

# Check code style
black --check src/ tests/
isort --check-only src/ tests/
flake8 src/ tests/

# Type checking
mypy src/bmlibrarian/

# Security check
bandit -r src/
```

### Pull Request Template

```markdown
## Description
Brief description of changes made.

## Type of Change
- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update

## Testing
- [ ] Added tests for new functionality
- [ ] All existing tests pass
- [ ] Tested manually with sample data

## Documentation
- [ ] Updated user documentation
- [ ] Updated developer documentation
- [ ] Added/updated docstrings

## Checklist
- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] No merge conflicts
- [ ] Ready for review
```

### Review Process

1. **Automated Checks:** CI/CD runs tests and quality checks
2. **Code Review:** Maintainer reviews code for:
   - Correctness and efficiency
   - Style compliance
   - Test coverage
   - Documentation completeness
   - Security considerations
3. **Feedback Integration:** Address review comments
4. **Approval and Merge:** Maintainer approves and merges

## Release Process

### Version Numbering

BMLibrarian follows Semantic Versioning (SemVer):
- `MAJOR.MINOR.PATCH`
- `MAJOR`: Breaking changes
- `MINOR`: New features (backward compatible)
- `PATCH`: Bug fixes (backward compatible)

### Release Checklist

**Pre-release:**
- [ ] All tests pass
- [ ] Documentation updated
- [ ] Version number updated in `__init__.py`
- [ ] Changelog updated
- [ ] Migration compatibility verified

**Release:**
- [ ] Create release tag
- [ ] Build and test package
- [ ] Upload to PyPI
- [ ] Update documentation site

## Community Guidelines

### Communication

- Be respectful and constructive in discussions
- Ask questions if requirements are unclear
- Provide detailed information when reporting issues
- Help other contributors when possible

### Issue Reporting

**Bug Reports:**
- Use the issue template
- Provide minimal reproduction case
- Include environment details
- Include relevant error messages

**Feature Requests:**
- Describe the use case clearly
- Explain why existing functionality doesn't work
- Consider implementation complexity
- Be open to alternative solutions

### Getting Help

- Check existing documentation first
- Search existing issues and discussions
- Ask specific questions with context
- Provide relevant code examples

Thank you for contributing to BMLibrarian! Your contributions help make biomedical literature more accessible to researchers worldwide.