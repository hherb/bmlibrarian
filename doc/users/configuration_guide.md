# Configuration Management Guide

## Overview

BMLibrarian uses a comprehensive configuration system that manages agent settings, database connections, API parameters, and user preferences. This guide covers all aspects of configuration management from initial setup to advanced customization.

## Configuration Architecture

### Configuration Hierarchy

BMLibrarian follows a hierarchical configuration approach:

1. **Default Configuration** - Built-in defaults for all settings
2. **User Configuration File** - Primary configuration at `~/.bmlibrarian/config.json`
3. **Legacy Configuration** - Fallback configuration in current directory
4. **Command Line Arguments** - Runtime overrides for specific operations
5. **Environment Variables** - System-level configuration for sensitive data

### Configuration File Locations

**Primary Location** (OS-agnostic):
```
~/.bmlibrarian/config.json
```

**Platform-Specific Paths**:
- **Windows**: `C:\Users\[username]\.bmlibrarian\config.json`
- **macOS**: `/Users/[username]/.bmlibrarian/config.json`
- **Linux**: `/home/[username]/.bmlibrarian/config.json`

**Legacy Fallback**:
```
bmlibrarian_config.json  # In current working directory
```

**Priority**: Primary location takes precedence over legacy fallback.

## Initial Configuration Setup

### Prerequisites

Before configuring BMLibrarian, ensure you have:

1. **PostgreSQL Database** with pgvector extension
2. **Ollama Server** running locally or remotely
3. **Required AI Models** installed in Ollama

### Quick Setup

```bash
# 1. Install dependencies
uv sync

# 2. Copy environment template
cp .env.example .env

# 3. Edit environment variables
# Edit .env with your database credentials

# 4. Launch configuration GUI (easiest method)
uv run python bmlibrarian_config_gui.py

# OR create configuration file manually
mkdir -p ~/.bmlibrarian
cp config_template.json ~/.bmlibrarian/config.json
```

### Environment Variables

Create a `.env` file in the project root:

```bash
# Database Configuration
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=knowledgebase
POSTGRES_USER=your_username
POSTGRES_PASSWORD=your_password

# Optional: PDF file storage
PDF_BASE_DIR=~/knowledgebase/pdf

# Optional: Ollama server (if not localhost:11434)
OLLAMA_BASE_URL=http://localhost:11434
```

## Configuration Structure

### Complete Configuration Schema

```json
{
  "general": {
    "ollama_base_url": "http://localhost:11434",
    "database_params": {
      "host": "localhost",
      "port": 5432,
      "database": "knowledgebase",
      "user": "username",
      "password": "password"
    },
    "cli_defaults": {
      "max_results": 100,
      "score_threshold": 2.5,
      "max_citations": 30,
      "timeout": 120,
      "show_progress": true,
      "auto_mode": false,
      "comprehensive_counterfactual": false
    }
  },
  "agents": {
    "query_agent": {
      "model": "gpt-oss:20b",
      "temperature": 0.1,
      "top_p": 0.9,
      "max_tokens": 2048,
      "query_complexity": "intermediate",
      "result_limit": 1000
    },
    "scoring_agent": {
      "model": "medgemma4B_it_q8:latest",
      "temperature": 0.0,
      "top_p": 0.8,
      "max_tokens": 512,
      "batch_size": 50
    },
    "citation_agent": {
      "model": "gpt-oss:20b",
      "temperature": 0.2,
      "top_p": 0.9,
      "max_tokens": 2048,
      "citation_length": "medium",
      "context_window": 200
    },
    "reporting_agent": {
      "model": "gpt-oss:20b",
      "temperature": 0.3,
      "top_p": 0.9,
      "max_tokens": 8192,
      "report_style": "medical",
      "citation_format": "numbered"
    },
    "counterfactual_agent": {
      "model": "gpt-oss:20b",
      "temperature": 0.5,
      "top_p": 0.9,
      "max_tokens": 4096,
      "analysis_depth": "moderate",
      "question_count": 10
    },
    "editor_agent": {
      "model": "gpt-oss:20b",
      "temperature": 0.3,
      "top_p": 0.9,
      "max_tokens": 8192,
      "integration_style": "comprehensive",
      "balance_approach": "evidence_based"
    }
  }
}
```

## Configuration Sections

### General Settings

**Ollama Configuration**:
```json
{
  "ollama_base_url": "http://localhost:11434"
}
```
- **Purpose**: Ollama server endpoint for AI model access
- **Default**: `http://localhost:11434`
- **Options**: Any valid HTTP/HTTPS URL

**Database Parameters**:
```json
{
  "database_params": {
    "host": "localhost",
    "port": 5432,
    "database": "knowledgebase", 
    "user": "username",
    "password": "password"
  }
}
```
- **host**: PostgreSQL server hostname or IP
- **port**: Database port (default: 5432)
- **database**: Target database name
- **user**: Database username
- **password**: Database password

**CLI Defaults**:
```json
{
  "cli_defaults": {
    "max_results": 100,
    "score_threshold": 2.5,
    "max_citations": 30,
    "timeout": 120,
    "show_progress": true,
    "auto_mode": false,
    "comprehensive_counterfactual": false
  }
}
```
- **max_results**: Maximum search results to process
- **score_threshold**: Minimum relevance score (1.0-5.0)
- **max_citations**: Maximum citations to extract
- **timeout**: Operation timeout in seconds
- **show_progress**: Display progress indicators
- **auto_mode**: Enable automated execution
- **comprehensive_counterfactual**: Enable extended counterfactual analysis

### Agent Configuration

Each agent supports common parameters plus agent-specific settings:

**Common Parameters**:
- **model**: Ollama model name
- **temperature**: Response randomness (0.0-2.0)
- **top_p**: Nucleus sampling parameter (0.0-1.0)
- **max_tokens**: Maximum response length
- **top_k**: Top-k sampling (optional)

**Agent-Specific Parameters**:

**Query Agent**:
- **query_complexity**: "simple", "intermediate", "advanced"
- **result_limit**: Maximum documents per query

**Scoring Agent**:
- **batch_size**: Documents processed per batch

**Citation Agent**:
- **citation_length**: "short", "medium", "long"
- **context_window**: Surrounding context size

**Reporting Agent**:
- **report_style**: "medical", "academic", "general"
- **citation_format**: "numbered", "apa", "vancouver"

**Counterfactual Agent**:
- **analysis_depth**: "shallow", "moderate", "deep"
- **question_count**: Number of research questions to generate

**Editor Agent**:
- **integration_style**: "comprehensive", "focused", "balanced"
- **balance_approach**: "evidence_based", "neutral", "critical"

## Configuration Methods

### 1. Configuration GUI (Recommended)

**Advantages**:
- Visual interface with validation
- Real-time model availability checking
- Connection testing
- Parameter explanations

**Usage**:
```bash
uv run python bmlibrarian_config_gui.py
```

**Features**:
- Tabbed interface for each agent
- Model selection with live refresh
- Parameter sliders and inputs
- Save/load/reset functionality

### 2. Manual File Editing

**Advantages**:
- Full control over configuration
- Easy to version control
- Scriptable for automation

**Usage**:
```bash
# Edit with your preferred editor
nano ~/.bmlibrarian/config.json
vim ~/.bmlibrarian/config.json
code ~/.bmlibrarian/config.json
```

**Validation**: Use the Configuration GUI to validate manual changes.

### 3. Command Line Arguments

**Advantages**:
- Runtime overrides
- Testing different settings
- Automation and scripting

**Usage**:
```bash
# Override specific settings
uv run python bmlibrarian_cli.py --max-results 50 --score-threshold 3.0

# Quick mode with overrides
uv run python bmlibrarian_research_gui.py --quick --max-citations 20
```

## Model Configuration

### Available Models

**Recommended Models**:

**High-Quality Models** (complex reasoning):
- **gpt-oss:20b**: Best overall performance
- **llama3.1:70b**: Excellent reasoning capabilities
- **mixtral:8x7b**: Good balance of speed and quality

**Fast Models** (quick processing):
- **medgemma4B_it_q8:latest**: Medical domain optimized
- **llama3.1:8b**: General purpose, fast
- **mistral:7b**: Efficient processing

**Specialized Models**:
- **meditron:7b**: Medical literature focused
- **biogpt**: Biomedical text generation
- **clinical-bert**: Clinical text understanding

### Model Installation

```bash
# Install recommended models
ollama pull gpt-oss:20b
ollama pull medgemma4B_it_q8:latest
ollama pull llama3.1:8b

# List installed models
ollama list

# Check model information
ollama show gpt-oss:20b
```

### Model Assignment Strategy

**Performance-Critical Tasks**:
- **Query Agent**: High-quality model (20b+ parameters)
- **Reporting Agent**: High-quality model for coherent reports
- **Editor Agent**: High-quality model for comprehensive editing

**Speed-Critical Tasks**:
- **Scoring Agent**: Fast model for numerical scoring
- **Citation Agent**: Balanced model for extraction speed

**Specialized Tasks**:
- **Counterfactual Agent**: Creative model for question generation

### Model Configuration Examples

**High-Performance Setup**:
```json
{
  "query_agent": {"model": "gpt-oss:20b"},
  "scoring_agent": {"model": "medgemma4B_it_q8:latest"},
  "citation_agent": {"model": "llama3.1:8b"},
  "reporting_agent": {"model": "gpt-oss:20b"},
  "counterfactual_agent": {"model": "mixtral:8x7b"},
  "editor_agent": {"model": "gpt-oss:20b"}
}
```

**Balanced Setup**:
```json
{
  "query_agent": {"model": "llama3.1:8b"},
  "scoring_agent": {"model": "medgemma4B_it_q8:latest"},
  "citation_agent": {"model": "llama3.1:8b"},
  "reporting_agent": {"model": "mixtral:8x7b"},
  "counterfactual_agent": {"model": "llama3.1:8b"},
  "editor_agent": {"model": "mixtral:8x7b"}
}
```

**Fast Setup** (testing/development):
```json
{
  "query_agent": {"model": "medgemma4B_it_q8:latest"},
  "scoring_agent": {"model": "medgemma4B_it_q8:latest"},
  "citation_agent": {"model": "medgemma4B_it_q8:latest"},
  "reporting_agent": {"model": "llama3.1:8b"},
  "counterfactual_agent": {"model": "llama3.1:8b"},
  "editor_agent": {"model": "llama3.1:8b"}
}
```

## Parameter Optimization

### Temperature Guidelines

**Deterministic Tasks** (0.0-0.2):
- Query generation
- Document scoring
- Citation extraction

**Balanced Tasks** (0.2-0.5):
- Report writing
- Comprehensive editing
- Standard analysis

**Creative Tasks** (0.5-0.8):
- Counterfactual analysis
- Research question generation
- Alternative perspective generation

### Top-p Guidelines

**Focused Responses** (0.1-0.6):
- Factual queries
- Numerical scoring
- Structured outputs

**Balanced Responses** (0.6-0.9):
- Report writing
- Citation extraction
- General analysis

**Diverse Responses** (0.9-1.0):
- Creative tasks
- Brainstorming
- Alternative viewpoints

### Max Tokens Guidelines

**Short Responses** (256-512):
- Document scores
- Simple classifications
- Brief summaries

**Medium Responses** (1024-2048):
- Query generation
- Citation extraction
- Analysis snippets

**Long Responses** (4096-8192):
- Full reports
- Comprehensive analysis
- Detailed explanations

## Advanced Configuration

### Environment-Specific Configurations

**Development Configuration**:
```json
{
  "general": {
    "cli_defaults": {
      "max_results": 20,
      "timeout": 30,
      "show_progress": true
    }
  },
  "agents": {
    "query_agent": {"model": "medgemma4B_it_q8:latest"},
    "scoring_agent": {"model": "medgemma4B_it_q8:latest"}
  }
}
```

**Production Configuration**:
```json
{
  "general": {
    "cli_defaults": {
      "max_results": 200,
      "timeout": 300,
      "show_progress": false
    }
  },
  "agents": {
    "query_agent": {"model": "gpt-oss:20b"},
    "reporting_agent": {"model": "gpt-oss:20b"}
  }
}
```

### Performance Optimization

**Memory-Constrained Systems**:
- Use smaller models (7b-8b parameters)
- Reduce max_tokens for all agents
- Lower batch_size for scoring agent
- Reduce max_results for queries

**High-Performance Systems**:
- Use largest available models
- Increase max_tokens for detailed outputs
- Increase batch_size for faster processing
- Higher max_results for comprehensive searches

**Network-Optimized**:
- Use local Ollama installation
- Configure appropriate timeouts
- Consider model loading times

## Configuration Validation

### Automatic Validation

BMLibrarian automatically validates configuration on startup:
- **Model availability**: Checks if configured models exist
- **Connection parameters**: Validates database connectivity
- **Parameter ranges**: Ensures values are within valid ranges
- **Required fields**: Verifies all mandatory settings are present

### Manual Validation

**Test Configuration**:
```bash
# Test with Configuration GUI
uv run python bmlibrarian_config_gui.py
# Click "Test Connection" button

# Test with CLI quick mode
uv run python bmlibrarian_cli.py --quick

# Test with Research GUI
uv run python bmlibrarian_research_gui.py --quick
```

**Validation Checklist**:
- [ ] Ollama server accessible at configured URL
- [ ] All configured models are installed and available
- [ ] Database connection parameters are correct
- [ ] Temperature values are between 0.0 and 2.0
- [ ] Top-p values are between 0.0 and 1.0
- [ ] Max tokens values are positive integers
- [ ] Threshold values are within valid ranges

## Configuration Backup and Migration

### Backup Strategies

**Manual Backup**:
```bash
# Create backup
cp ~/.bmlibrarian/config.json ~/.bmlibrarian/config_backup_$(date +%Y%m%d).json

# Restore backup
cp ~/.bmlibrarian/config_backup_20240315.json ~/.bmlibrarian/config.json
```

**Version Control**:
```bash
# Initialize git repo for config
cd ~/.bmlibrarian
git init
git add config.json
git commit -m "Initial configuration"

# Track changes
git add config.json
git commit -m "Updated agent models"
```

### Configuration Migration

**From Legacy Format**:
BMLibrarian automatically migrates old configuration formats to the new structure.

**Between Systems**:
```bash
# Export from source system
cp ~/.bmlibrarian/config.json /backup/bmlibrarian_config.json

# Import to target system
mkdir -p ~/.bmlibrarian
cp /backup/bmlibrarian_config.json ~/.bmlibrarian/config.json
```

**Team Sharing**:
```bash
# Create template (remove sensitive data)
jq 'del(.general.database_params.password)' ~/.bmlibrarian/config.json > config_template.json

# Share template
git add config_template.json
git commit -m "Add configuration template"
```

## Troubleshooting Configuration Issues

### Common Problems

**Configuration Not Loading**:
- Check file permissions: `ls -la ~/.bmlibrarian/config.json`
- Validate JSON syntax: `python -m json.tool ~/.bmlibrarian/config.json`
- Check file location and spelling

**Model Not Found Errors**:
- Verify Ollama server is running: `ollama list`
- Check model names match exactly
- Pull missing models: `ollama pull model_name`

**Database Connection Failures**:
- Test connection parameters
- Check PostgreSQL server status
- Verify network connectivity
- Validate credentials

**Parameter Validation Errors**:
- Check value ranges (temperature: 0.0-2.0, top_p: 0.0-1.0)
- Ensure positive integers for tokens and batch sizes
- Validate enum values (e.g., report_style options)

### Debug Configuration

**Enable Debug Logging**:
```bash
# CLI with debug output
uv run python bmlibrarian_cli.py --debug

# GUI with debug output  
uv run python bmlibrarian_config_gui.py --debug
```

**Configuration Inspection**:
```python
from bmlibrarian.config import get_config
config = get_config()
print(config)  # Display current configuration
```

## Best Practices

### Security

**Sensitive Data**:
- Use environment variables for passwords
- Avoid committing credentials to version control
- Use secure file permissions: `chmod 600 ~/.bmlibrarian/config.json`

**Network Security**:
- Use HTTPS for remote Ollama servers
- Configure firewall rules appropriately
- Consider VPN for remote database access

### Performance

**Model Selection**:
- Use appropriate model sizes for available resources
- Consider task-specific optimized models
- Balance quality vs. speed based on use case

**Resource Management**:
- Monitor GPU/CPU usage with different models
- Adjust batch sizes based on available memory
- Consider concurrent usage patterns

### Maintenance

**Regular Updates**:
- Keep models updated: `ollama pull model_name`
- Review and optimize configuration periodically
- Monitor performance and adjust settings

**Documentation**:
- Document configuration changes
- Maintain configuration templates for different environments
- Share best practices with team members

---

This configuration guide provides comprehensive coverage of BMLibrarian's configuration system, enabling users to optimize their setup for their specific research needs and system capabilities.