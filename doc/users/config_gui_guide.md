# Configuration GUI User Guide

## Overview

The BMLibrarian Configuration GUI is a desktop application that provides a visual interface for managing all aspects of BMLibrarian configuration. It features tabbed interfaces for agent settings, model selection, parameter tuning, and system configuration.

## Getting Started

### Launching the Configuration GUI

```bash
# Start the configuration GUI (desktop mode - default)
uv run python bmlibrarian_config_gui.py

# Start in web browser mode
uv run python bmlibrarian_config_gui.py --view web

# Web mode with custom port
uv run python bmlibrarian_config_gui.py --view web --port 8080

# Debug mode with enhanced logging
uv run python bmlibrarian_config_gui.py --debug
```

### System Requirements

- **Operating System**: Windows, macOS, or Linux
- **Python**: 3.12 or higher
- **Dependencies**: Automatically installed via `uv sync`
- **External Services**:
  - Ollama server for model management and testing

## Main Interface

### Application Layout

The Configuration GUI uses a tabbed interface with the following tabs:

1. **General Settings** - System-wide configuration
2. **Query Agent** - Natural language to SQL conversion settings
3. **Scoring Agent** - Document relevance scoring configuration
4. **Citation Agent** - Citation extraction parameters
5. **Reporting Agent** - Report generation settings
6. **Counterfactual Agent** - Contradictory evidence analysis configuration
7. **Editor Agent** - Comprehensive report editing parameters

### Action Buttons

**Main Actions** (available on all tabs):
- **Save Configuration** - Save current settings to config file
- **Load Configuration** - Load settings from config file
- **Reset to Defaults** - Restore default settings
- **Test Connection** - Verify Ollama server connectivity

**Advanced Actions**:
- **Refresh Models** - Update available models from Ollama server
- **Export Configuration** - Export settings to a file
- **Import Configuration** - Import settings from a file

## Configuration Tabs

### General Settings Tab

**System Configuration**:

**Ollama Server Settings**:
- **Base URL**: Ollama server address (default: `http://localhost:11434`)
- **Connection Test**: Button to verify server connectivity
- **Model Refresh**: Update list of available models

**Database Configuration**:
- **PostgreSQL Host**: Database server address
- **PostgreSQL Port**: Database port (default: 5432)
- **Database Name**: Target database name
- **Username**: Database username
- **Password**: Database password (securely stored)

**CLI Default Settings**:
- **Max Results**: Default maximum search results
- **Score Threshold**: Default relevance threshold
- **Max Citations**: Default maximum citations to extract
- **Timeout**: Default operation timeout (seconds)
- **Show Progress**: Enable/disable progress indicators
- **Auto Mode**: Default execution mode

### Agent Configuration Tabs

Each agent has its own configuration tab with the following common elements:

#### Model Selection
- **Model Dropdown**: Select from available Ollama models
- **Refresh Models**: Update model list from server
- **Model Status**: Indicates if selected model is available

#### Core Parameters
- **Temperature**: Controls randomness in responses (0.0-2.0)
  - Lower values = more deterministic
  - Higher values = more creative/varied
- **Top-p**: Nucleus sampling parameter (0.0-1.0)
  - Controls diversity of token selection
- **Max Tokens**: Maximum response length
- **Top-k**: Top-k sampling parameter (optional)

#### Agent-Specific Settings

**Query Agent**:
- **Query Complexity**: Simple, intermediate, or advanced query generation
- **Result Limit**: Maximum documents per query
- **Query Optimization**: Enable/disable query optimization

**Scoring Agent**:
- **Scoring Method**: Relevance assessment approach
- **Threshold Sensitivity**: Fine-tuning for relevance thresholds
- **Batch Size**: Documents processed per batch

**Citation Agent**:
- **Citation Length**: Preferred length of extracted citations
- **Context Window**: Surrounding context for citations
- **Quality Filter**: Minimum citation quality threshold

**Reporting Agent**:
- **Report Style**: Medical, academic, or general format
- **Citation Format**: Reference formatting style
- **Section Organization**: Report structure preferences

**Counterfactual Agent**:
- **Analysis Depth**: Shallow, moderate, or deep analysis
- **Question Generation**: Number of research questions to generate
- **Priority Weighting**: How to prioritize contradictory evidence

**Editor Agent**:
- **Integration Style**: How to combine evidence types
- **Balance Approach**: Handling conflicting evidence
- **Editing Depth**: Comprehensive or focused editing

## Configuration Management

### Saving and Loading Configuration

**Save Configuration**:
1. Adjust settings in any tab
2. Click **"Save Configuration"** button
3. Settings are saved to `~/.bmlibrarian/config.json`
4. Confirmation message displayed

**Load Configuration**:
1. Click **"Load Configuration"** button
2. Existing saved settings are loaded
3. All tabs are updated with loaded values
4. Any unsaved changes are discarded

**Reset to Defaults**:
1. Click **"Reset to Defaults"** button
2. Confirmation dialog appears
3. All settings return to default values
4. Changes are not automatically saved

### Configuration File Location

**Primary Location** (recommended):
```
~/.bmlibrarian/config.json
```

**Platform-Specific Paths**:
- **Windows**: `C:\Users\username\.bmlibrarian\config.json`
- **macOS**: `/Users/username/.bmlibrarian/config.json`
- **Linux**: `/home/username/.bmlibrarian/config.json`

**Legacy Fallback** (current directory):
```
bmlibrarian_config.json
```

### Configuration File Structure

The configuration file uses JSON format:

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
      "auto_mode": false
    }
  },
  "agents": {
    "query_agent": {
      "model": "gpt-oss:20b",
      "temperature": 0.1,
      "top_p": 0.9,
      "max_tokens": 2048
    },
    "scoring_agent": {
      "model": "medgemma4B_it_q8:latest",
      "temperature": 0.2,
      "top_p": 0.8
    }
    // ... other agents
  }
}
```

## Model Management

### Available Models

The Configuration GUI displays models available on your Ollama server:

**Recommended Models**:
- **gpt-oss:20b** - High-quality model for complex reasoning tasks
- **medgemma4B_it_q8:latest** - Fast model optimized for medical content
- **llama3.1:8b** - General-purpose model with good performance
- **mistral:7b** - Efficient model for quick responses

**Model Selection Guidelines**:
- **Complex Reasoning** (Query, Reporting, Editor): Use larger models (20b+)
- **Fast Processing** (Scoring, Citation): Use smaller, specialized models
- **Resource Constraints**: Choose models based on available GPU/CPU

### Model Installation

If needed models aren't available, install them via Ollama:

```bash
# Install recommended models
ollama pull gpt-oss:20b
ollama pull medgemma4B_it_q8:latest

# List installed models
ollama list

# Check model details
ollama show gpt-oss:20b
```

### Connection Testing

**Test Ollama Connection**:
1. Click **"Test Connection"** button on General Settings tab
2. GUI attempts to connect to configured Ollama server
3. Results displayed in status message:
   - **Success**: "✓ Connected to Ollama server"
   - **Failure**: "✗ Cannot connect to Ollama server at [URL]"

**Troubleshooting Connection Issues**:
- Verify Ollama server is running: `ollama serve`
- Check server URL in configuration
- Test manually: `curl http://localhost:11434/api/tags`
- Verify network connectivity and firewall settings

## Parameter Tuning Guide

### Temperature Settings

**Low Temperature (0.0-0.3)**:
- More deterministic and consistent responses
- Best for: Query generation, citation extraction
- Use when consistency is important

**Medium Temperature (0.3-0.7)**:
- Balanced creativity and consistency
- Best for: Report writing, general analysis
- Good default for most applications

**High Temperature (0.7-2.0)**:
- More creative and varied responses
- Best for: Brainstorming, counterfactual analysis
- Use when diversity is desired

### Top-p Settings

**Low Top-p (0.1-0.5)**:
- More focused on high-probability tokens
- More consistent outputs
- Best for factual, precise tasks

**High Top-p (0.5-1.0)**:
- Considers wider range of tokens
- More diverse outputs
- Best for creative tasks

### Agent-Specific Recommendations

**Query Agent**:
- Temperature: 0.1-0.2 (consistency important)
- Top-p: 0.8-0.9
- Max Tokens: 1024-2048

**Scoring Agent**:
- Temperature: 0.0-0.1 (numerical consistency)
- Top-p: 0.8
- Max Tokens: 512-1024

**Citation Agent**:
- Temperature: 0.1-0.3
- Top-p: 0.9
- Max Tokens: 1024-2048

**Reporting Agent**:
- Temperature: 0.3-0.5 (balanced)
- Top-p: 0.9
- Max Tokens: 4096-8192

**Counterfactual Agent**:
- Temperature: 0.5-0.7 (creativity for questions)
- Top-p: 0.9
- Max Tokens: 2048-4096

**Editor Agent**:
- Temperature: 0.2-0.4 (balanced editing)
- Top-p: 0.9
- Max Tokens: 4096-8192

## Cross-Platform Features

### Desktop Mode (Default)

**Features**:
- Native window management
- Platform-specific file dialogs
- System integration
- Keyboard shortcuts
- Offline operation

**Advantages**:
- Better performance
- Native look and feel
- Full file system access
- No browser dependencies

### Web Mode

**Features**:
- Browser-based interface
- Remote access capability
- No installation required
- Cross-platform consistency

**Usage**:
```bash
# Start web interface
uv run python bmlibrarian_config_gui.py --view web

# Custom port
uv run python bmlibrarian_config_gui.py --view web --port 8080
```

**Access**: Open `http://localhost:8080` in your web browser

## Best Practices

### Configuration Management

**Regular Backups**:
- Export configuration periodically
- Keep backups of working configurations
- Document changes for team environments

**Testing Changes**:
- Test configuration changes with small workflows first
- Use the Research GUI's quick mode for testing
- Verify model availability before deploying

**Version Control**:
- Track configuration changes
- Use meaningful commit messages for config updates
- Consider separate configs for development/production

### Model Selection

**Performance vs. Quality Trade-offs**:
- Use fast models for development and testing
- Use high-quality models for production research
- Consider hybrid approaches (fast for scoring, quality for reporting)

**Resource Management**:
- Monitor GPU/CPU usage with different models
- Consider model switching based on workload
- Plan for concurrent usage in team environments

### Security Considerations

**Database Credentials**:
- Use environment variables for sensitive data
- Avoid storing passwords in version control
- Consider using connection strings or credential files

**Network Security**:
- Secure Ollama server access in production
- Use HTTPS for web mode in production environments
- Consider VPN access for remote configuration

## Troubleshooting

### Common Issues

**Configuration Not Saving**:
- Check file permissions on config directory
- Verify disk space availability
- Try running with elevated permissions if necessary

**Models Not Loading**:
- Refresh models list
- Check Ollama server connection
- Verify models are installed: `ollama list`

**GUI Not Responding**:
- Check for error messages in console
- Restart the application
- Clear any corrupted configuration files

**Web Mode Issues**:
- Check port availability
- Verify firewall settings
- Try different port numbers

### Performance Issues

**Slow Model Refresh**:
- Large number of models can slow refresh
- Check Ollama server performance
- Consider local vs. remote Ollama server

**Memory Usage**:
- Close unused browser tabs in web mode
- Monitor system resources
- Consider using lighter models for configuration

---

The Configuration GUI provides comprehensive control over all BMLibrarian settings with an intuitive visual interface, making it easy to optimize your research workflows and manage complex multi-agent configurations.