# Research GUI User Guide

## Overview

The BMLibrarian Research GUI is a desktop application that provides a visual interface for conducting AI-powered biomedical literature research. It features real-time workflow progress, interactive research question input, and comprehensive report generation with preview capabilities.

## Getting Started

### Launching the Research GUI

```bash
# Start the research GUI (desktop mode)
uv run python bmlibrarian_research_gui.py

# Start with a specific research question (auto mode)
uv run python bmlibrarian_research_gui.py --auto "What are the effects of exercise on cardiovascular health?"

# Start in quick mode with limited results for faster processing
uv run python bmlibrarian_research_gui.py --quick

# Combine options
uv run python bmlibrarian_research_gui.py --auto "research question" --quick --max-results 50
```

### System Requirements

- **Operating System**: Windows, macOS, or Linux
- **Python**: 3.12 or higher
- **Dependencies**: Automatically installed via `uv sync`
- **External Services**:
  - PostgreSQL database with pgvector extension
  - Ollama server running locally (`http://localhost:11434`)

## Main Interface

### Research Question Input

The main interface includes a multi-line text field for entering your research question:

1. **Research Question Field**: Large text input area for detailed research questions
2. **Workflow Options**:
   - **Interactive Mode Toggle**: Enable/disable human-in-the-loop interaction
   - **Counterfactual Analysis**: Optional contradictory evidence analysis
3. **Start Research Button**: Begin the research workflow

### Workflow Progress Display

The GUI shows real-time progress through 11 research workflow steps:

#### Core Workflow Steps
1. **Research Question Collection** - Validate and process your question
2. **Query Generation and Editing** - Convert to database queries
3. **Document Search** - Search the biomedical literature database
4. **Search Results Review** - Review and filter search results
5. **Document Scoring** - AI-powered relevance assessment
6. **Citation Extraction** - Extract relevant passages
7. **Report Generation** - Synthesize findings into a report
8. **Counterfactual Analysis** - Analyze for contradictory evidence (optional)
9. **Contradictory Evidence Search** - Search for opposing views (optional)
10. **Comprehensive Report Editing** - Integrate all evidence
11. **Report Export** - Save final report

#### Visual Status Indicators
- **Gray**: Step pending/not started
- **Blue with spinner**: Step currently running
- **Green**: Step completed successfully
- **Red**: Step failed with error
- **Yellow**: Step was skipped

### Workflow Controls

- **Collapsible Workflow Section**: Click to expand/collapse the workflow progress display
- **Status Updates**: Real-time status messages for each step
- **Progress Tracking**: Visual indication of current step and completion status

## Research Process

### 1. Enter Research Question

Type your biomedical research question in the text field. Examples:
- "What are the cardiovascular benefits of regular exercise?"
- "How effective is metformin in treating type 2 diabetes?"
- "What are the side effects of long-term statin use?"

### 2. Configure Options

**Interactive Mode** (Default: On):
- **On**: Allows you to review and edit queries, adjust parameters, and make decisions during the workflow
- **Off**: Runs automatically with minimal user intervention

**Counterfactual Analysis** (Default: Off):
- **On**: Performs additional analysis to find contradictory evidence
- **Off**: Generates standard research report only

### 3. Start Research

Click **"Start Research"** to begin the workflow. The GUI will:
1. Initialize AI agents with your configured settings
2. Process your research question through each workflow step
3. Display real-time progress and status updates
4. Generate a comprehensive research report

### 4. Monitor Progress

Watch the workflow cards update in real-time:
- Each step card shows current status
- Click cards to expand/collapse for space efficiency
- Status messages provide detailed information about each step
- Any errors will be displayed with clear error messages

## Report Preview and Export

### Report Preview

Once the research workflow completes:
1. **Preview Button**: Click to open the report preview dialog
2. **Full-Screen Display**: Report shown in a scrollable overlay
3. **Markdown Formatting**: Professional formatting with proper citations
4. **Navigation**: Scroll through the complete report

### Report Export

**Direct File Save**:
1. **Save Button**: Click to open the file save dialog
2. **File Path Input**: Enter the full path where you want to save the report
3. **Automatic Extension**: `.md` extension added automatically if not specified
4. **Cross-Platform**: Works on Windows, macOS, and Linux

**Example Save Paths**:
- **Windows**: `C:\Users\username\Documents\research_report.md`
- **macOS**: `/Users/username/Documents/research_report.md`
- **Linux**: `/home/username/Documents/research_report.md`

## Report Structure

### Standard Report Sections

1. **Research Question** - Your original research question
2. **Evidence Assessment** - Overall strength and quality of evidence
3. **Findings** - Key findings organized by topic
4. **References** - All citations with document IDs and relevance scores
5. **Methodology** - Research approach and limitations
6. **Technical Details** - Execution metrics and system information

### Enhanced Report (with Counterfactual Analysis)

When counterfactual analysis is enabled, reports include additional sections:

7. **Counterfactual Analysis**
   - **Main Claims Analyzed** - Key statements examined for contradictions
   - **Research Questions for Contradictory Evidence** - Organized by priority
   - **Overall Assessment** - Evidence strength evaluation

## Command Line Options

### Research Parameters

```bash
# Set maximum number of search results
uv run python bmlibrarian_research_gui.py --max-results 100

# Set document relevance threshold
uv run python bmlibrarian_research_gui.py --score-threshold 3.0

# Set maximum citations to extract
uv run python bmlibrarian_research_gui.py --max-citations 50

# Set timeout for operations (seconds)
uv run python bmlibrarian_research_gui.py --timeout 30
```

### Execution Modes

```bash
# Quick mode (faster processing, limited results)
uv run python bmlibrarian_research_gui.py --quick

# Auto mode (automated execution with specific question)
uv run python bmlibrarian_research_gui.py --auto "research question"

# Debug mode (enhanced logging)
uv run python bmlibrarian_research_gui.py --debug
```

## Configuration Integration

The Research GUI automatically uses your BMLibrarian configuration:

### Agent Configuration
- **Models**: Uses configured models from `~/.bmlibrarian/config.json`
- **Parameters**: Respects temperature, top-p, and other agent settings
- **Thresholds**: Uses configured relevance and citation thresholds

### Database Settings
- **Connection**: Uses configured PostgreSQL connection parameters
- **Performance**: Optimized queries based on your database configuration

### Ollama Integration
- **Server**: Connects to configured Ollama server URL
- **Models**: Uses your configured models for each agent type
- **Fallbacks**: Handles model unavailability gracefully

## Troubleshooting

### Common Issues

**Application Won't Start**:
- Verify Python 3.12+ is installed: `python --version`
- Check dependencies are installed: `uv sync`
- Ensure Ollama server is running: `curl http://localhost:11434/api/tags`

**Database Connection Errors**:
- Verify PostgreSQL is running
- Check connection parameters in configuration
- Ensure pgvector extension is installed
- Test connection: `psql -h localhost -U username -d database_name`

**Model Not Found Errors**:
- Check Ollama server is accessible
- Verify models are installed: `ollama list`
- Update configuration with available models

**Workflow Execution Errors**:
- Check step-specific error messages in the GUI
- Review logs for detailed error information
- Verify all required services are running
- Check network connectivity for API calls

### Performance Optimization

**Faster Processing**:
- Use `--quick` mode for testing
- Reduce `--max-results` for smaller searches
- Increase `--score-threshold` for fewer citations
- Use faster models in agent configuration

**Memory Management**:
- Close other applications to free memory
- Use smaller batch sizes for document processing
- Monitor system resources during large workflows

## Best Practices

### Research Questions

**Effective Questions**:
- Be specific about the medical condition or intervention
- Include relevant population if important (e.g., "in elderly patients")
- Focus on measurable outcomes when possible
- Use standard medical terminology

**Example Good Questions**:
- "What is the efficacy of ACE inhibitors in reducing cardiovascular mortality in diabetic patients?"
- "How does the Mediterranean diet affect inflammatory markers in adults?"
- "What are the long-term neurological effects of COVID-19 infection?"

### Workflow Configuration

**Interactive Mode Best Use**:
- Enable for complex or nuanced research questions
- Use when you want to refine queries based on initial results
- Enable when you need to adjust relevance thresholds

**Automated Mode Best Use**:
- Use for straightforward research questions
- Enable for batch processing multiple questions
- Use when you trust your default configuration settings

### Report Management

**File Organization**:
- Use descriptive filenames: `cardiovascular_exercise_benefits_2024.md`
- Organize by research topic or project
- Include date in filename for version tracking
- Consider creating folders by research area

**Report Review**:
- Always preview reports before saving
- Check citation quality and relevance
- Review methodology section for limitations
- Verify technical details are appropriate

---

The Research GUI provides a powerful, visual interface for conducting comprehensive biomedical literature research with real-time feedback and professional-quality report generation.