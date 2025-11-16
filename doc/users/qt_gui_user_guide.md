# BMLibrarian Qt GUI User Guide

## Table of Contents

1. [Introduction](#introduction)
2. [Installation and Setup](#installation-and-setup)
3. [Launching the Application](#launching-the-application)
4. [User Interface Overview](#user-interface-overview)
5. [Using the Tabs](#using-the-tabs)
6. [Keyboard Shortcuts](#keyboard-shortcuts)
7. [Customization](#customization)
8. [Troubleshooting](#troubleshooting)
9. [FAQ](#faq)

## Introduction

BMLibrarian Qt GUI is a modern desktop application for biomedical literature research. It provides a powerful, user-friendly interface for searching, analyzing, and reviewing biomedical literature using AI-powered agents.

### Key Features

- **Multi-Tab Interface**: Organize different research tasks in separate tabs
- **AI-Powered Search**: Natural language queries converted to database searches
- **Document Scoring**: AI relevance scoring for research questions
- **Citation Extraction**: Automatic extraction of relevant passages
- **Report Generation**: Professional research reports with citations
- **Fact-Checking**: Review and annotate biomedical statements
- **Dark Theme**: Comfortable viewing in low-light environments
- **Customizable**: Configure plugins, themes, and preferences

## Installation and Setup

### Prerequisites

- **Python**: Version 3.12 or higher
- **PostgreSQL**: Database with pgvector extension
- **Ollama**: Local AI model server (running on `http://localhost:11434`)

### Installation Steps

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/yourusername/bmlibrarian.git
   cd bmlibrarian
   ```

2. **Install Dependencies**:
   ```bash
   uv sync
   ```

3. **Configure Database**:
   - Edit `.env` file with your PostgreSQL credentials
   - Run database setup: `uv run python initial_setup_and_download.py test.env`

4. **Start Ollama** (if not already running):
   ```bash
   ollama serve
   ```

5. **Verify Installation**:
   ```bash
   uv run python bmlibrarian_qt.py
   ```

### First-Time Setup

When you first launch the application:

1. **Configuration File**: A default configuration file is created at `~/.bmlibrarian/gui_config.json`
2. **Theme**: Default light theme is applied
3. **Tabs**: Default tabs (Research, Search, Configuration) are loaded
4. **Window Size**: Window opens at 1400x900 pixels

## Launching the Application

### From Command Line

```bash
# From repository root
python bmlibrarian_qt.py

# Or using uv
uv run python bmlibrarian_qt.py
```

### From Desktop (Optional)

Create a desktop launcher:

**Linux**: Create `~/.local/share/applications/bmlibrarian.desktop`:
```ini
[Desktop Entry]
Name=BMLibrarian
Comment=Biomedical Literature Research
Exec=/path/to/bmlibrarian/bmlibrarian_qt.py
Icon=/path/to/icon.png
Terminal=false
Type=Application
Categories=Science;Education;
```

**macOS**: Create an app bundle or use Automator

**Windows**: Create a shortcut to `python bmlibrarian_qt.py`

## User Interface Overview

### Main Window Components

```
┌─────────────────────────────────────────────────────────────┐
│ File   View   Tools   Help                                  │ ← Menu Bar
├─────────────────────────────────────────────────────────────┤
│ ┌─────────┬──────────┬──────────┬────────────┬───────────┐ │
│ │Research │  Search  │  Fact    │ Query Lab  │   Config  │ │ ← Tab Bar
│ └─────────┴──────────┴──────────┴────────────┴───────────┘ │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │                                                       │ │
│  │                                                       │ │
│  │                 Active Tab Content                    │ │ ← Tab Content
│  │                                                       │ │
│  │                                                       │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                             │
│ Ready                                                       │ ← Status Bar
└─────────────────────────────────────────────────────────────┘
```

### Menu Bar

- **File**: Export, Exit
- **View**: Tab navigation, Theme selection, Reload plugins
- **Tools**: Configuration
- **Help**: About BMLibrarian, About Qt

### Tab Bar

Displays all enabled plugin tabs. Tabs can be:
- Clicked to switch
- Reordered by dragging
- Navigated with keyboard shortcuts (Alt+1, Alt+2, etc.)

### Status Bar

Shows messages from plugins:
- Operation status
- Error messages
- Progress updates

## Using the Tabs

### Research Tab

The Research tab provides a complete workflow for biomedical literature research.

#### Features:
- **Research Question Input**: Enter your medical research question
- **Workflow Steps**: Visual progress through the research process
- **Document List**: View and browse found documents
- **Citation Viewer**: Examine extracted citations
- **Report Preview**: View generated research reports
- **Export**: Save reports to markdown files

#### Workflow:

1. **Enter Research Question**:
   ```
   "What are the cardiovascular benefits of exercise?"
   ```

2. **Generate Query**: AI converts your question to a database query

3. **Search Documents**: Execute search and review results

4. **Score Documents**: AI scores relevance (1-5 scale)

5. **Extract Citations**: Get relevant passages from high-scoring documents

6. **Generate Report**: Create a professional research report

7. **Export**: Save report to file

#### Tips:
- Be specific in your research questions
- Review the generated SQL query for accuracy
- Adjust scoring threshold if too few/many documents
- Use the workflow steps to track progress

### Search Tab

Advanced document search with multiple filter criteria.

#### Features:
- **Text Search**: Search titles and abstracts
- **Year Range Filter**: Filter by publication year
- **Journal Filter**: Search specific journals
- **Source Filter**: PubMed, medRxiv, or all
- **Result Limit**: Control number of results
- **Document Cards**: Visual result display

#### How to Use:

1. **Enter Search Terms**:
   - Text field searches titles and abstracts
   - Supports partial matching

2. **Apply Filters** (optional):
   - **Year From/To**: e.g., 2020-2024
   - **Journal**: e.g., "Nature", "JAMA"
   - **Source**: Select database

3. **Set Result Limit**:
   - Default: 100 documents
   - Range: 10-1000

4. **Execute Search**:
   - Click "Search" button
   - View results as cards

5. **View Details**:
   - Click any document card
   - See full abstract and metadata

#### Tips:
- Use year range to focus on recent studies
- Combine filters for precise searches
- Start with broader searches, then refine

### Configuration Tab

Manage application settings and agent configurations.

#### Sections:

**General Settings**:
- Ollama server URL
- Database connection
- Default parameters

**Agent Configuration**:
- **Query Agent**: Model, temperature, top-p for query generation
- **Scoring Agent**: Model and parameters for document scoring
- **Citation Agent**: Settings for citation extraction
- **Reporting Agent**: Report generation configuration

**Multi-Model Query Generation**:
- Enable/disable multi-model queries
- Select models to use
- Configure query diversity

#### How to Configure:

1. **Select Model**:
   - Click "Refresh Models" to get available models from Ollama
   - Choose from dropdown

2. **Adjust Parameters**:
   - **Temperature** (0.0-2.0): Higher = more creative
   - **Top-p** (0.0-1.0): Nucleus sampling threshold

3. **Test Connection**:
   - Click "Test Connection" to verify Ollama is reachable

4. **Save Configuration**:
   - Click "Save" to persist changes
   - Configuration saved to `~/.bmlibrarian/config.json`

#### Tips:
- Lower temperature for deterministic results
- Higher temperature for diverse outputs
- Test connection if getting errors

### Fact-Checker Tab

Review and annotate biomedical statements for fact-checking.

#### Features:
- **Statement Display**: View statements to review
- **Annotation Controls**: Yes/No/Maybe with explanation
- **Citation Cards**: Supporting evidence display
- **Navigation**: Previous/Next statement
- **Confidence Timer**: Track review time
- **Auto-Save**: Annotations saved automatically

#### How to Use:

1. **Load Statements**:
   - File → Open (if needed)
   - Statements load automatically

2. **Review Statement**:
   - Read the statement carefully
   - Review AI evaluation (if present)
   - Examine supporting citations

3. **Annotate**:
   - Select: Yes / Maybe / No
   - Enter explanation for your decision
   - Annotation saves automatically

4. **Navigate**:
   - Click "Next" for next statement
   - Click "Previous" to go back
   - Use keyboard: Ctrl+→ (next), Ctrl+← (previous)

5. **Export** (optional):
   - File → Export
   - Save annotations to JSON

#### Tips:
- Take time to read citations carefully
- Explain your reasoning clearly
- Use "Maybe" when evidence is unclear
- Review the confidence timer to pace yourself

### Query Lab Tab

Experimental interface for testing QueryAgent.

#### Features:
- **Model Selection**: Choose AI model
- **Parameter Tuning**: Adjust temperature, top-p, max tokens
- **Query Input**: Enter natural language questions
- **SQL Output**: View generated PostgreSQL query
- **Query Explanation**: Understand the query logic
- **Save/Load Examples**: Store successful queries

#### How to Use:

1. **Select Model and Parameters**:
   - Choose model from dropdown
   - Adjust sliders for temperature and top-p

2. **Enter Question**:
   ```
   "Find studies about COVID-19 vaccines published in 2023"
   ```

3. **Generate Query**:
   - Click "Generate Query"
   - Wait for processing (runs in background)

4. **Review Output**:
   - **PostgreSQL Query**: SQL to execute
   - **Explanation**: How the query works

5. **Save Example** (optional):
   - Click "Save Example"
   - Choose filename (JSON format)

6. **Load Example**:
   - Click "Load Example"
   - Select previously saved query

#### Tips:
- Experiment with different models
- Compare outputs with different parameters
- Save successful queries for reuse
- Use explanations to learn SQL patterns

## Keyboard Shortcuts

### Global Shortcuts

| Shortcut | Action |
|----------|--------|
| **Ctrl+Q** | Quit application |
| **Ctrl+E** | Export (when available) |
| **Ctrl+,** | Open Configuration |
| **Ctrl+R** | Reload plugins |
| **F1** | Show Help/About |

### Tab Navigation

| Shortcut | Action |
|----------|--------|
| **Alt+1** | Go to first tab |
| **Alt+2** | Go to second tab |
| **Alt+3** | Go to third tab |
| **Alt+4-9** | Go to tabs 4-9 |
| **Ctrl+Tab** | Next tab |
| **Ctrl+Shift+Tab** | Previous tab |

### Theme

| Shortcut | Action |
|----------|--------|
| **Ctrl+Shift+T** | Toggle light/dark theme |

### Tab-Specific

| Shortcut | Action |
|----------|--------|
| **F5** | Refresh current tab |

## Customization

### Themes

BMLibrarian Qt GUI supports two built-in themes:

#### Light Theme (Default)
- Clean, professional appearance
- High contrast for readability
- Suitable for bright environments

#### Dark Theme
- Reduced eye strain in low light
- Modern VS Code-inspired colors
- Background: #1e1e1e, Accent: #0e639c

#### Changing Themes:

**Method 1: Menu**
1. View → Theme → Light Theme / Dark Theme
2. Restart application when prompted

**Method 2: Keyboard**
1. Press **Ctrl+Shift+T**
2. Restart application when prompted

**Method 3: Configuration File**
Edit `~/.bmlibrarian/gui_config.json`:
```json
{
  "gui": {
    "theme": "dark"
  }
}
```

### Enabling/Disabling Tabs

Edit `~/.bmlibrarian/gui_config.json`:

```json
{
  "gui": {
    "tabs": {
      "enabled_plugins": [
        "research",
        "search",
        "fact_checker",
        "query_lab",
        "configuration"
      ],
      "tab_order": [
        "research",
        "search",
        "fact_checker",
        "query_lab",
        "configuration"
      ],
      "default_tab": "research"
    }
  }
}
```

**Options**:
- `enabled_plugins`: List of plugin IDs to load
- `tab_order`: Order of tabs in tab bar
- `default_tab`: Which tab to show on startup

### Window Geometry

Window size and position are automatically saved on exit and restored on startup.

**Disable Auto-Save**:
```json
{
  "gui": {
    "window": {
      "remember_geometry": false
    }
  }
}
```

### Plugin-Specific Settings

Each plugin can have its own settings:

```json
{
  "gui": {
    "research_tab": {
      "show_workflow_steps": true,
      "auto_scroll_to_active": true,
      "max_documents_display": 100
    },
    "search_tab": {
      "max_results": 100,
      "show_abstracts": true
    },
    "fact_checker_tab": {
      "auto_save": true,
      "show_confidence_timer": true
    }
  }
}
```

## Troubleshooting

### Application Won't Start

**Problem**: Error on launch or immediate crash

**Solutions**:
1. Check Python version: `python --version` (must be 3.12+)
2. Verify dependencies: `uv sync`
3. Check logs: `~/.bmlibrarian/gui_qt.log`
4. Delete config and retry: `rm ~/.bmlibrarian/gui_config.json`

### No Tabs Appear

**Problem**: Main window shows but no tabs

**Solutions**:
1. Check `~/.bmlibrarian/gui_config.json` exists
2. Verify `enabled_plugins` list is not empty
3. Check logs for plugin loading errors
4. Reset configuration to defaults

### Database Connection Error

**Problem**: "Database connection failed" message

**Solutions**:
1. Verify PostgreSQL is running
2. Check `.env` file database credentials
3. Test connection manually:
   ```bash
   psql -h localhost -U your_user -d knowledgebase
   ```
4. Review database configuration in Configuration tab

### Ollama Not Available

**Problem**: "Failed to connect to Ollama" error

**Solutions**:
1. Start Ollama: `ollama serve`
2. Verify Ollama is running: `curl http://localhost:11434`
3. Check Configuration tab for correct Ollama URL
4. Install required models: `ollama pull gpt-oss:20b`

### Theme Not Changing

**Problem**: Theme doesn't apply after selection

**Solutions**:
1. Restart the application (required for theme changes)
2. Verify theme setting in `~/.bmlibrarian/gui_config.json`
3. Check stylesheet files exist:
   - `src/bmlibrarian/gui/qt/resources/styles/dark.qss`
   - `src/bmlibrarian/gui/qt/resources/styles/default.qss`

### UI Freezing

**Problem**: Application becomes unresponsive during operations

**Solutions**:
1. Wait for operation to complete (background processing)
2. Check Ollama is responding
3. Check database query performance
4. Review logs for errors
5. Restart application if completely frozen

### Missing Documents/Results

**Problem**: Search returns no results or fewer than expected

**Solutions**:
1. Verify database has documents:
   ```sql
   SELECT COUNT(*) FROM pubmed_articles;
   SELECT COUNT(*) FROM medrxiv_articles;
   ```
2. Check search filters aren't too restrictive
3. Review generated SQL query (Query Lab)
4. Adjust scoring threshold

## FAQ

### General Questions

**Q: What databases does BMLibrarian search?**
A: BMLibrarian searches PubMed and medRxiv articles stored in your local PostgreSQL database.

**Q: Do I need an internet connection?**
A: No, once the database is populated and Ollama models are downloaded, BMLibrarian works entirely offline.

**Q: How much disk space do I need?**
A: Depends on database size:
- Minimal (100K articles): ~10 GB
- Medium (1M articles): ~100 GB
- Full PubMed (38M articles): ~500 GB+

**Q: Can I use cloud AI models instead of Ollama?**
A: Currently, BMLibrarian requires Ollama for local AI processing. Cloud model support may be added in future versions.

### Performance Questions

**Q: Why is query generation slow?**
A: AI model inference time depends on:
- Model size (larger = slower)
- Hardware (CPU vs GPU)
- Ollama configuration

Try faster models like `medgemma4B_it_q8:latest` for quicker responses.

**Q: Can I speed up document scoring?**
A: Yes, several options:
- Use faster models
- Reduce number of documents to score
- Enable GPU acceleration in Ollama
- Limit search results

**Q: How do I improve search quality?**
A:
- Use more specific research questions
- Enable multi-model query generation
- Review and refine generated SQL queries
- Adjust relevance threshold

### Configuration Questions

**Q: Where are my settings stored?**
A: Two configuration files:
- GUI settings: `~/.bmlibrarian/gui_config.json`
- Agent settings: `~/.bmlibrarian/config.json`

**Q: Can I share my configuration?**
A: Yes, copy configuration files to other machines with BMLibrarian installed.

**Q: How do I reset to defaults?**
A: Delete configuration files:
```bash
rm ~/.bmlibrarian/gui_config.json
rm ~/.bmlibrarian/config.json
```
Defaults will be recreated on next launch.

### Feature Questions

**Q: Can I export reports to PDF?**
A: Currently, reports export to Markdown (.md). You can convert to PDF using tools like Pandoc:
```bash
pandoc report.md -o report.pdf
```

**Q: Can I use BMLibrarian for non-biomedical research?**
A: The system is optimized for biomedical literature but can be adapted for other domains by importing different article sources.

**Q: Is there a web interface?**
A: Currently, only desktop Qt GUI is available. The legacy Flet web-based GUI is deprecated.

## Getting Help

### Resources

- **Documentation**: See `doc/` directory
- **Logs**: Check `~/.bmlibrarian/gui_qt.log`
- **Examples**: Review example plugins in `src/bmlibrarian/gui/qt/plugins/example/`

### Reporting Issues

When reporting issues, please include:
1. BMLibrarian version
2. Python version
3. Operating system
4. Error messages from logs
5. Steps to reproduce

### Contributing

Contributions welcome! See `CONTRIBUTING.md` for guidelines.

---

**Welcome to BMLibrarian Qt GUI!**

We hope this guide helps you make the most of BMLibrarian's powerful biomedical literature research capabilities. Happy researching!
