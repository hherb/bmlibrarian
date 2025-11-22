# PaperChecker CLI System Documentation

## Overview

The PaperChecker CLI system provides a command-line interface for batch fact-checking of medical abstracts. It follows the modular architecture pattern used by other BMLibrarian CLI tools, separating concerns into distinct modules for maintainability and testability.

## Architecture

### Module Structure

```
src/bmlibrarian/paperchecker/cli/
├── __init__.py           # Module exports
├── app.py               # Main entry point and argument parsing
├── commands.py          # Command handlers (load, check, export)
└── formatters.py        # Output formatting and display
```

### Design Principles

1. **Separation of Concerns**: Logic is split between argument parsing, command execution, and output formatting
2. **Validation First**: All inputs are validated before processing
3. **Graceful Degradation**: Continue-on-error mode allows partial batch completion
4. **Progress Tracking**: Real-time progress via tqdm with callback support
5. **Golden Rules Compliance**: No magic numbers, type hints, docstrings, error handling

## Module Documentation

### app.py - Main Entry Point

The main application module handles:
- Command-line argument parsing
- Logging configuration
- Agent initialization
- High-level workflow orchestration

```python
from bmlibrarian.paperchecker.cli.app import main

# Entry point
exit_code = main()
```

**Key Functions:**

| Function | Description |
|----------|-------------|
| `parse_args()` | Parse command-line arguments using argparse |
| `setup_logging(verbose)` | Configure logging levels |
| `create_agent(config_path)` | Initialize PaperCheckerAgent |
| `main()` | Main entry point, returns exit code |

### commands.py - Command Handlers

Provides functions for loading abstracts, processing them, and exporting results.

**Constants:**

| Constant | Value | Description |
|----------|-------|-------------|
| `MIN_ABSTRACT_LENGTH` | 50 | Minimum abstract character count |
| `MAX_ABSTRACT_LENGTH` | 50000 | Maximum abstract character count |
| `MIN_PMID` | 1 | Minimum valid PMID |
| `MAX_PMID` | 99999999999 | Maximum valid PMID (11 digits) |

**Key Functions:**

```python
from bmlibrarian.paperchecker.cli.commands import (
    validate_abstract,
    load_abstracts_from_json,
    load_abstracts_from_pmids,
    check_abstracts,
    export_results_json,
    export_markdown_reports,
)
```

| Function | Description |
|----------|-------------|
| `validate_abstract(abstract, index)` | Validate single abstract text |
| `load_abstracts_from_json(filepath)` | Load and validate JSON file |
| `load_abstracts_from_pmids(pmids)` | Fetch abstracts from database |
| `check_abstracts(abstracts, agent, ...)` | Process abstracts with progress tracking |
| `export_results_json(results, output_file)` | Export to JSON format |
| `export_markdown_reports(results, output_dir)` | Export individual markdown reports |

### formatters.py - Output Formatting

Handles all console output formatting including statistics, summaries, and error reports.

**Display Constants:**

| Constant | Value | Description |
|----------|-------|-------------|
| `SEPARATOR_WIDTH` | 60 | Width of separator lines |
| `SEPARATOR_CHAR` | "=" | Character for major separators |
| `MAX_PREVIEW_LENGTH` | 80 | Max length for inline text previews |

**Key Functions:**

```python
from bmlibrarian.paperchecker.cli.formatters import (
    print_statistics,
    print_abstract_summary,
    format_verdict_summary,
    print_error_summary,
    print_completion_banner,
)
```

| Function | Description |
|----------|-------------|
| `print_statistics(results)` | Print comprehensive statistics |
| `print_abstract_summary(result, index, verbose)` | Print single result summary |
| `format_verdict_summary(verdicts)` | Format verdicts for inline display |
| `print_error_summary(errors)` | Print error list |
| `print_completion_banner(...)` | Print completion message |

## Data Flow

```
                    ┌─────────────────┐
                    │   Input Source  │
                    │  (JSON/PMIDs)   │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │   Validation    │
                    │ load_abstracts  │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │ PaperChecker    │
                    │    Agent        │
                    └────────┬────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│ Console Stats │   │  JSON Export  │   │ Markdown Rpts │
│  formatters   │   │   commands    │   │   commands    │
└───────────────┘   └───────────────┘   └───────────────┘
```

## Error Handling

### Validation Errors

Input validation occurs at multiple levels:

1. **File-Level**: File existence, JSON parsing
2. **Structure-Level**: List format, required keys
3. **Content-Level**: Abstract length, PMID ranges

```python
def validate_abstract(abstract: str, index: int) -> Tuple[bool, Optional[str]]:
    """
    Returns (is_valid, error_message).
    """
```

### Processing Errors

Processing errors are captured per-abstract:

```python
results, errors = check_abstracts(
    abstracts=abstracts,
    agent=agent,
    continue_on_error=True  # Don't stop on first error
)

# errors = [
#     {"index": 3, "pmid": 123, "error": "Connection timeout"},
#     {"index": 7, "pmid": None, "error": "Model unavailable"},
# ]
```

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success (all abstracts processed) |
| 1 | Error (processing failed or errors occurred) |
| 130 | Interrupted by user (Ctrl+C) |

## Progress Tracking

### tqdm Integration

Progress is tracked using tqdm with custom formatting:

```python
PROGRESS_BAR_FORMAT = "{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]"

pbar = tqdm(abstracts, desc="Checking abstracts", unit="abstract")
for item in pbar:
    pbar.set_postfix({"ok": len(results), "errors": len(errors)})
```

### Progress Callback

Optional callback for external progress tracking:

```python
def progress_callback(completed: int, total: int, error: Optional[str]) -> None:
    if error:
        log.warning(f"Error at {completed}/{total}: {error}")
    else:
        log.info(f"Progress: {completed}/{total}")

results, errors = check_abstracts(
    abstracts,
    agent,
    progress_callback=progress_callback
)
```

## Testing

### Unit Tests

Create tests in `tests/test_paperchecker_cli.py`:

```python
import pytest
from bmlibrarian.paperchecker.cli.commands import (
    validate_abstract,
    load_abstracts_from_json,
)

def test_validate_abstract_too_short():
    """Test validation rejects short abstracts."""
    is_valid, error = validate_abstract("Too short", 0)
    assert not is_valid
    assert "too short" in error.lower()

def test_validate_abstract_valid():
    """Test validation accepts valid abstracts."""
    abstract = "A" * 100  # 100 characters
    is_valid, error = validate_abstract(abstract, 0)
    assert is_valid
    assert error is None
```

### Integration Tests

```python
@pytest.mark.integration
@pytest.mark.requires_ollama
@pytest.mark.requires_database
def test_cli_end_to_end(tmp_path):
    """Test full CLI workflow."""
    # Create test input
    input_file = tmp_path / "test_input.json"
    input_file.write_text(json.dumps([{
        "abstract": "Test abstract " * 20,
        "metadata": {"pmid": 12345}
    }]))

    # Run CLI
    from bmlibrarian.paperchecker.cli.app import main
    import sys
    sys.argv = ["paper_checker_cli.py", str(input_file), "--quick"]

    exit_code = main()
    assert exit_code == 0
```

## Extension Points

### Custom Input Sources

Add new input sources by creating loader functions:

```python
def load_abstracts_from_csv(filepath: str) -> List[Dict[str, Any]]:
    """Load abstracts from CSV file."""
    import csv
    abstracts = []
    with open(filepath) as f:
        reader = csv.DictReader(f)
        for row in reader:
            is_valid, error = validate_abstract(row["abstract"], len(abstracts))
            if is_valid:
                abstracts.append({
                    "abstract": row["abstract"],
                    "metadata": {"pmid": int(row.get("pmid", 0))}
                })
    return abstracts
```

### Custom Output Formats

Add new export formats:

```python
def export_results_csv(
    results: List[PaperCheckResult],
    output_file: str
) -> None:
    """Export results to CSV format."""
    import csv
    with open(output_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["pmid", "statement", "verdict", "confidence"])
        for result in results:
            pmid = result.source_metadata.get("pmid", "")
            for stmt, verdict in zip(result.statements, result.verdicts):
                writer.writerow([
                    pmid,
                    stmt.text,
                    verdict.verdict,
                    verdict.confidence
                ])
```

### Custom Formatters

Add new display formats:

```python
def print_json_statistics(results: List[PaperCheckResult]) -> None:
    """Print statistics as JSON."""
    import json
    stats = {
        "total_abstracts": len(results),
        "total_statements": sum(len(r.statements) for r in results),
        "verdicts": {"supports": 0, "contradicts": 0, "undecided": 0}
    }
    for result in results:
        for v in result.verdicts:
            stats["verdicts"][v.verdict] += 1
    print(json.dumps(stats, indent=2))
```

## Configuration

### Config Integration

The CLI uses BMLibrarian's configuration system:

```python
from bmlibrarian.config import get_config, get_agent_config

config = get_config()
paper_checker_config = get_agent_config("paper_checker")
```

### CLI-Specific Settings

Settings that affect only CLI behavior:

| Setting | Default | Description |
|---------|---------|-------------|
| `QUICK_MODE_MAX_ABSTRACTS` | 5 | Max abstracts in quick mode |
| `LOG_FORMAT` | Standard format | Logging format string |

## Dependencies

### Required Packages

- `tqdm>=4.66.0` - Progress bars
- `argparse` - Command-line parsing (stdlib)
- `json` - JSON handling (stdlib)
- `logging` - Logging (stdlib)
- `pathlib` - Path handling (stdlib)

### Internal Dependencies

- `bmlibrarian.paperchecker.agent` - PaperCheckerAgent
- `bmlibrarian.paperchecker.data_models` - Data classes
- `bmlibrarian.database` - Database access
- `bmlibrarian.config` - Configuration

## See Also

- [PaperChecker CLI User Guide](../users/paper_checker_cli_guide.md)
- [PaperChecker Architecture Overview](../../doc/planning/paperchecker/00_ARCHITECTURE_OVERVIEW.md)
- [PaperChecker Database System](papercheck_database_system.md)
