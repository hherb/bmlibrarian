# Contributing to BMLibrarian

**Thank you for your interest in contributing to BMLibrarian!**

This document provides guidelines for contributing to the project. All contributions are welcome, from bug reports to new features.

## Table of Contents

1. [Code of Conduct](#code-of-conduct)
2. [Getting Started](#getting-started)
3. [How to Contribute](#how-to-contribute)
4. [Development Workflow](#development-workflow)
5. [Coding Standards](#coding-standards)
6. [Testing Guidelines](#testing-guidelines)
7. [Documentation](#documentation)
8. [Pull Request Process](#pull-request-process)

## Code of Conduct

Be respectful, inclusive, and professional. We welcome contributors of all backgrounds and experience levels.

## Getting Started

### Prerequisites

- Python 3.12 or higher
- PostgreSQL 14+ with pgvector extension
- Ollama for local LLM inference
- Git for version control
- `uv` package manager (recommended)

### Development Setup

1. **Fork the repository** on GitHub

2. **Clone your fork**:
   ```bash
   git clone https://github.com/YOUR_USERNAME/bmlibrarian.git
   cd bmlibrarian
   ```

3. **Add upstream remote**:
   ```bash
   git remote add upstream https://github.com/hherb/bmlibrarian.git
   ```

4. **Install dependencies**:
   ```bash
   uv sync --dev  # Includes development dependencies
   ```

5. **Set up database**:
   ```bash
   createdb bmlibrarian_dev  # Use separate dev database
   cp test_database.env.example .env
   # Edit .env with dev database credentials
   ```

6. **Initialize database**:
   ```bash
   uv run python initial_setup_and_download.py .env --skip-medrxiv --skip-pubmed
   ```

7. **Run tests** to verify setup:
   ```bash
   uv run python -m pytest tests/ -v
   ```

## How to Contribute

### Reporting Bugs

1. **Search existing issues** to avoid duplicates
2. **Use the bug report template** on GitHub Issues
3. **Include**:
   - Clear description of the bug
   - Steps to reproduce
   - Expected vs. actual behavior
   - Python version, OS, database version
   - Error messages and stack traces
   - Screenshots if applicable

### Suggesting Features

1. **Check if feature already exists** or is planned
2. **Use the feature request template**
3. **Describe**:
   - Use case and motivation
   - Proposed solution or API
   - Alternatives considered
   - Impact on existing functionality

### Contributing Code

Areas where contributions are especially welcome:

1. **New Agents** - Create specialized AI agents
2. **Qt Plugins** - Extend the GUI with new tabs
3. **Importers** - Add support for new data sources
4. **Documentation** - Improve guides and examples
5. **Tests** - Increase test coverage
6. **Bug Fixes** - Fix reported issues

## Development Workflow

### Branch Strategy

- `main` - Stable release branch
- `develop` - Development branch (base for PRs)
- `feature/your-feature` - Feature branches
- `bugfix/issue-number` - Bug fix branches

### Creating a Feature Branch

```bash
# Update your fork
git fetch upstream
git checkout develop
git merge upstream/develop

# Create feature branch
git checkout -b feature/your-feature-name
```

### Making Changes

1. **Make small, focused commits**:
   ```bash
   git add src/bmlibrarian/agents/new_agent.py
   git commit -m "Add new agent for X functionality"
   ```

2. **Follow commit message conventions**:
   - Use present tense ("Add feature" not "Added feature")
   - Be concise but descriptive
   - Reference issues: "Fix #123: Description"

3. **Keep commits atomic** - One logical change per commit

### Testing Your Changes

```bash
# Run all tests
uv run python -m pytest tests/ -v

# Run specific test file
uv run python -m pytest tests/test_my_agent.py -v

# Run with coverage
uv run python -m pytest tests/ --cov=bmlibrarian --cov-report=html

# Test Qt GUI (requires X server or Xvfb)
uv run python -m pytest tests/gui/qt/ -v
```

### Updating Your Branch

```bash
# Fetch latest changes
git fetch upstream

# Rebase on develop
git rebase upstream/develop

# Or merge if rebasing is problematic
git merge upstream/develop
```

## Coding Standards

### Python Style

We follow **PEP 8** with some exceptions:

- **Line length**: 100 characters (not 79)
- **Imports**: Group by standard library, third-party, local
- **Docstrings**: Google style (see below)

### Type Hints (MANDATORY)

All functions and methods must include type hints:

```python
from typing import Dict, List, Optional, Tuple, Any

def process_documents(
    documents: List[Dict[str, Any]],
    min_score: float = 0.7,
    callback: Optional[Callable[[int, int], None]] = None
) -> Tuple[List[Dict], Dict[str, float]]:
    """
    Process documents and return scored results.

    Args:
        documents: List of document dictionaries
        min_score: Minimum relevance score (0.0-1.0)
        callback: Optional progress callback (current, total)

    Returns:
        Tuple of (scored_documents, statistics)
    """
    # Implementation...
```

### Docstrings (MANDATORY)

Use **Google-style docstrings** for all public functions and classes:

```python
def search_literature(
    query: str,
    max_results: int = 100
) -> List[Dict[str, Any]]:
    """
    Search biomedical literature databases.

    Performs full-text search across PubMed and medRxiv databases
    using PostgreSQL text search.

    Args:
        query: Natural language search query
        max_results: Maximum number of results to return (default: 100)

    Returns:
        List of document dictionaries with keys:
        - id: Document ID
        - title: Document title
        - abstract: Document abstract
        - publication_date: Publication date (ISO format)

    Raises:
        ValueError: If query is empty or max_results <= 0
        ConnectionError: If database is unavailable

    Examples:
        >>> docs = search_literature("COVID-19 vaccine", max_results=10)
        >>> print(f"Found {len(docs)} documents")
        Found 10 documents

    Note:
        Results are ordered by publication date (newest first).
    """
```

### No Magic Numbers

Use named constants or configuration:

```python
# BAD
if score > 0.7:
    documents = documents[:50]

# GOOD
MIN_RELEVANCE_THRESHOLD = 0.7
DEFAULT_MAX_DOCUMENTS = 50

if score > MIN_RELEVANCE_THRESHOLD:
    documents = documents[:DEFAULT_MAX_DOCUMENTS]
```

### Logging (MANDATORY)

Use Python's logging module, **never `print()`**:

```python
import logging

logger = logging.getLogger(__name__)

def process_data(data):
    logger.info(f"Processing {len(data)} items")
    try:
        result = complex_operation(data)
        logger.info("Processing completed successfully")
        return result
    except Exception as e:
        logger.error(f"Processing failed: {e}", exc_info=True)
        raise
```

### Import Order

```python
# Standard library imports
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

# Third-party imports
from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtCore import Signal
import psycopg

# BMLibrarian imports
from bmlibrarian.config import get_config
from bmlibrarian.database import get_db_manager
from bmlibrarian.agents.base import BaseAgent
```

### Code Organization

```python
"""
Module-level docstring describing purpose.
"""

# Standard library imports
# Third-party imports
# BMLibrarian imports

# Module-level constants
DEFAULT_BATCH_SIZE = 50
MIN_CONFIDENCE_THRESHOLD = 0.7

# Module-level logger
logger = logging.getLogger(__name__)


class MyClass:
    """Class definition with docstring."""

    def __init__(self, ...):
        """Constructor docstring."""
        # Implementation

    def public_method(self, ...) -> ReturnType:
        """Public method with full docstring."""
        # Implementation

    def _private_method(self, ...) -> ReturnType:
        """Private method (still needs docstring)."""
        # Implementation
```

## Testing Guidelines

### Test Structure

```python
"""
Unit tests for CustomAgent.
"""

import unittest
from unittest.mock import Mock, patch
from bmlibrarian.agents.custom_agent import CustomAgent


class TestCustomAgent(unittest.TestCase):
    """Test suite for CustomAgent."""

    def setUp(self):
        """Set up test fixtures."""
        self.agent = CustomAgent(
            model="gpt-oss:20b",
            temperature=0.1,
            show_model_info=False
        )

    def test_agent_initialization(self):
        """Test agent initializes correctly."""
        self.assertEqual(self.agent.model, "gpt-oss:20b")
        self.assertEqual(self.agent.temperature, 0.1)

    @patch('bmlibrarian.agents.base.BaseAgent._make_ollama_request')
    def test_process_data(self, mock_request):
        """Test data processing."""
        # Setup mock
        mock_request.return_value = {"result": "success"}

        # Run test
        result = self.agent.process({"data": "test"})

        # Assertions
        self.assertEqual(result["result"], "success")
        mock_request.assert_called_once()

    def tearDown(self):
        """Clean up after tests."""
        pass


if __name__ == '__main__':
    unittest.main()
```

### What to Test

1. **Unit Tests** - Test individual functions/methods in isolation
2. **Integration Tests** - Test component interactions
3. **Edge Cases** - Test boundary conditions
4. **Error Handling** - Test exception cases
5. **Mock External Dependencies** - Mock Ollama, database calls

### Test Coverage

Aim for **>80% code coverage** for new code:

```bash
uv run python -m pytest tests/ --cov=bmlibrarian --cov-report=html
open htmlcov/index.html
```

## Documentation

### When to Document

Document:
- All public APIs
- Plugin development guides
- Agent development guides
- Configuration options
- New features

### Where to Document

1. **Docstrings** - In-code documentation
2. **User Guides** - `doc/users/` directory
3. **Developer Guides** - `doc/developers/` directory
4. **Wiki** - High-level guides and tutorials
5. **README** - Project overview and quick start
6. **CHANGELOG** - Version history and changes

### Documentation Standards

- Use Markdown for all documentation
- Include code examples
- Add screenshots for GUI features
- Keep documentation up-to-date with code changes
- Use clear, concise language
- Avoid jargon (or explain it)

## Pull Request Process

### Before Submitting

1. **Update your branch** with latest develop:
   ```bash
   git fetch upstream
   git rebase upstream/develop
   ```

2. **Run tests**:
   ```bash
   uv run python -m pytest tests/ -v
   ```

3. **Check code style**:
   ```bash
   uv run python -m black src/bmlibrarian tests/
   uv run python -m flake8 src/bmlibrarian tests/
   ```

4. **Update documentation** if needed

5. **Add tests** for new functionality

### Creating the Pull Request

1. **Push your branch**:
   ```bash
   git push origin feature/your-feature-name
   ```

2. **Create PR on GitHub**:
   - Base branch: `develop`
   - Compare branch: `feature/your-feature-name`
   - Use the PR template
   - Link related issues

3. **PR Description Should Include**:
   - Summary of changes
   - Motivation and context
   - Type of change (bug fix, feature, etc.)
   - Testing performed
   - Checklist completion

### PR Template

```markdown
## Description
Brief description of changes

## Motivation
Why is this change needed?

## Type of Change
- [ ] Bug fix (non-breaking change)
- [ ] New feature (non-breaking change)
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] Tests added/updated
- [ ] All tests pass
- [ ] Manual testing performed

## Checklist
- [ ] Code follows style guidelines
- [ ] Documentation updated
- [ ] No new warnings
- [ ] Added/updated tests
- [ ] All tests pass
```

### Review Process

1. **Automated checks** must pass (CI/CD)
2. **Code review** by maintainers
3. **Address feedback** with new commits
4. **Squash and merge** when approved

### After Merge

1. **Delete your feature branch**:
   ```bash
   git branch -d feature/your-feature-name
   git push origin --delete feature/your-feature-name
   ```

2. **Update your fork**:
   ```bash
   git fetch upstream
   git checkout develop
   git merge upstream/develop
   ```

## Development Areas

### Creating a New Agent

See [Plugin Development Guide](Plugin-Development-Guide) for Qt plugins.

For a new AI agent:

1. **Inherit from BaseAgent**:
   ```python
   from bmlibrarian.agents.base import BaseAgent

   class MyAgent(BaseAgent):
       def get_agent_type(self) -> str:
           return "my_agent"

       def process(self, data):
           # Implementation
   ```

2. **Add configuration** to `config.py`
3. **Write tests** in `tests/test_my_agent.py`
4. **Add documentation** in `doc/developers/`
5. **Update README** with usage example

### Creating a Qt Plugin

See [Plugin Development Guide](Plugin-Development-Guide) for complete details.

Quick start:

1. Create directory: `src/bmlibrarian/gui/qt/plugins/my_plugin/`
2. Implement `plugin.py` with `create_plugin()` function
3. Inherit from `BaseTabPlugin`
4. Add to `gui_config.json`
5. Test in Qt GUI

### Adding a New Data Source

1. Create importer: `src/bmlibrarian/importers/new_source_importer.py`
2. Add source to database: `INSERT INTO source ...`
3. Implement import logic
4. Create CLI tool: `new_source_import_cli.py`
5. Update documentation

## Getting Help

- **Questions**: [GitHub Discussions](https://github.com/hherb/bmlibrarian/discussions)
- **Bugs**: [GitHub Issues](https://github.com/hherb/bmlibrarian/issues)
- **Chat**: Check repository for community chat links
- **Documentation**: [BMLibrarian Wiki](https://github.com/hherb/bmlibrarian/wiki)

## License

By contributing, you agree that your contributions will be licensed under the same license as the project.

---

**Thank you for contributing to BMLibrarian!** 🙏

Your contributions help make biomedical research more accessible and efficient for everyone.
