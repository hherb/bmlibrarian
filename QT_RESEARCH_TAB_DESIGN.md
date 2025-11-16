# Qt Research Tab Design - Matching Flet GUI Layout

## Executive Summary

This document provides the complete design specification for the Qt Research tab to achieve **exact feature parity** with the Flet Research GUI. The goal is to replicate the Flet layout, workflow, and functionality using PySide6.

## Configuration Separation

**CRITICAL**: Qt GUI uses separate config file to avoid conflicts with Flet:
- **Qt Config**: `~/.bmlibrarian/bmlibrarian_qt_config.json`
- **Flet Config**: `~/.bmlibrarian/config.json` (agent configuration shared)
- **Status**: ✅ COMPLETED - config_manager.py updated

## Flet GUI Layout Analysis

### Overall Structure

The Flet Research GUI has this structure:

```
┌────────────────────────────────────────────────────────────┐
│ HEADER                                                      │
│ - Title: "BMLibrarian Research Assistant"                  │
│ - Subtitle: "AI-Powered Evidence-Based..."                 │
├────────────────────────────────────────────────────────────┤
│ CONTROLS SECTION (Grey background, rounded corners)        │
│                                                             │
│ Row 1: [Research Question Text Field          ] [Start]    │
│        (multi-line, 3-6 lines, expanding)                   │
│                                                             │
│ Row 2: [Max Results] [Min Relevant] [Interactive ☐]       │
│        [Comprehensive Counterfactual ☑]                     │
├────────────────────────────────────────────────────────────┤
│ TABBED INTERFACE (8 tabs)                                  │
│ ┌──────┬──────────┬─────────┬──────────┬──────────────┬───┤
│ │Search│Literature│ Scoring │Citations │ Preliminary  │...│
│ └──────┴──────────┴─────────┴──────────┴──────────────┴───┤
│                                                             │
│ [Tab Content Area - Scrollable]                            │
│                                                             │
│                                                             │
└────────────────────────────────────────────────────────────┘
```

### Tab Structure (8 Tabs)

#### Tab 1: Search
**Icon**: 🔍 Search
**Purpose**: Display research question and generated SQL query
**Components**:
- Header: "Search Query" subtitle
- Progress bar (indeterminate, visible during query generation)
- Progress text (status messages)
- Research Question display (bold, blue text)
- Generated Query display (selectable text, monospace)
- Multi-model query details (collapsible, shows all queries if multi-model enabled)
- Query performance stats (shown after scoring completes)
- **Interactive Mode Controls**:
  - "Edit Query" button (shows editable TextField)
  - "Accept & Continue" button (green, proceeds with query)
  - "Cancel" button (cancels edit)

#### Tab 2: Literature
**Icon**: 📚 Library Books
**Purpose**: List all documents found by search
**Components**:
- Header: "Literature ({count})" with subtitle
- Document count badge
- Scrollable list of document cards (ExpansionTile)
- Each card shows:
  - Title (bold, blue)
  - Authors (truncated after 3)
  - Journal, Year, DOI, PMID
  - Abstract (expandable)
  - Document type badge
  - Metadata section

#### Tab 3: Scoring
**Icon**: 📊 Analytics
**Purpose**: Score documents for relevance
**Components**:
- Header: "Document Scoring ({count})"
- Progress indicators for scoring
- **Interactive Scoring Interface** (if human_in_loop):
  - Current document card with full details
  - Score selector (1-5 stars or buttons)
  - Explanation text field
  - Navigation: Previous/Next/Skip buttons
  - Progress: "Document X of Y"
- **Auto Mode Display**:
  - List of scored documents with scores
  - Color-coded score badges (green=high, red=low)
- Statistics summary

#### Tab 4: Citations
**Icon**: 💬 Format Quote
**Purpose**: Display extracted citations
**Components**:
- Header: "Citations ({count})"
- Citation count by document
- Grouped citations (by document)
- Each citation card shows:
  - Document title (clickable to expand)
  - Relevant passage (quoted text)
  - Relevance score badge
  - Page/location info
  - Expandable full abstract
- **Interactive Mode Controls**:
  - "Request More Citations" button
  - Threshold adjustment slider

#### Tab 5: Preliminary Report
**Icon**: 📄 Article
**Purpose**: Show preliminary report before counterfactual
**Components**:
- Header: "Preliminary Report"
- Markdown-rendered report
- Word count statistics
- Citation count
- **Interactive Mode Controls**:
  - "Regenerate Report" button
  - "Edit Report" button
  - "Accept & Continue" button
- Export button (save to markdown file)

#### Tab 6: Counterfactual
**Icon**: 🧠 Psychology
**Purpose**: Display counterfactual analysis
**Components**:
- Header: "Counterfactual Analysis"
- Research questions for finding contradictory evidence
- Progressive disclosure sections:
  - Generated research questions
  - Search results for contradictory evidence
  - Contradictory document list
  - Evidence assessment
- **Interactive Mode Controls**:
  - "Skip Counterfactual" button
  - "Regenerate Questions" button

#### Tab 7: Report
**Icon**: 📋 Description
**Purpose**: Final comprehensive report
**Components**:
- Header: "Final Report"
- Markdown-rendered comprehensive report
- Includes both supporting and contradictory evidence
- Word count and citation statistics
- Report metadata (generation time, model used, etc.)
- **Export Controls**:
  - "Export as Markdown" button
  - "Export as PDF" button (future)
  - File path input dialog
- Print button

#### Tab 8: Settings
**Icon**: ⚙️ Settings
**Purpose**: Configuration and preferences
**Components**:
- Agent configuration selector
- Model selection dropdown
- Parameter sliders (temperature, top_p, etc.)
- Quick toggles:
  - Interactive mode
  - Comprehensive counterfactual
  - Multi-model query generation
- Database status indicator
- Ollama connection test button
- Reset to defaults button

## Component Hierarchy

### Main Window Structure

```
BMLibrarianMainWindow (QMainWindow)
├─ Central Widget (QWidget)
│  └─ Main Layout (QVBoxLayout)
│     ├─ Tab Widget (QTabWidget)
│     │  ├─ Research Tab (ResearchTabWidget) ← WE ARE HERE
│     │  ├─ Search Tab
│     │  ├─ Configuration Tab
│     │  ├─ Fact Checker Tab
│     │  └─ Query Lab Tab
│     └─ Status Bar (QStatusBar)
```

### Research Tab Structure

```
ResearchTabWidget (QWidget)
├─ Main Layout (QVBoxLayout)
│  ├─ Header Section (QWidget)
│  │  ├─ Title Label (QLabel) "BMLibrarian Research Assistant"
│  │  └─ Subtitle Label (QLabel) "AI-Powered..."
│  │
│  ├─ Controls Section (QWidget with background)
│  │  ├─ Row 1 (QHBoxLayout)
│  │  │  ├─ Question Input (QTextEdit, 3-6 lines)
│  │  │  └─ Start Button (QPushButton, blue, icon)
│  │  │
│  │  └─ Row 2 (QHBoxLayout)
│  │     ├─ Max Results (QSpinBox, 120px width)
│  │     ├─ Min Relevant (QSpinBox, 120px width)
│  │     ├─ Interactive Toggle (QCheckBox)
│  │     └─ Counterfactual Toggle (QCheckBox)
│  │
│  └─ Research Tabs (QTabWidget) ← 8 TABS
│     ├─ Search Tab (QWidget)
│     ├─ Literature Tab (QWidget)
│     ├─ Scoring Tab (QWidget)
│     ├─ Citations Tab (QWidget)
│     ├─ Preliminary Tab (QWidget)
│     ├─ Counterfactual Tab (QWidget)
│     ├─ Report Tab (QWidget)
│     └─ Settings Tab (QWidget)
```

## Qt Widget Equivalents

### Flet → Qt Mapping

| Flet Component | Qt Widget | Notes |
|----------------|-----------|-------|
| ft.TextField (multiline) | QTextEdit | For question input |
| ft.TextField (single) | QLineEdit or QSpinBox | For numbers |
| ft.Switch | QCheckBox | For toggles |
| ft.ElevatedButton | QPushButton | Styled with QPalette |
| ft.Text | QLabel | With word wrap, selectable |
| ft.Tabs | QTabWidget | Nested tab widget |
| ft.Tab | QWidget | Each tab is a widget |
| ft.ExpansionTile | QTreeWidget or Custom CollapsibleSection | Already implemented! |
| ft.ProgressBar | QProgressBar | With indeterminate mode |
| ft.Markdown | QTextBrowser or MarkdownViewer | Already implemented! |
| ft.Container | QWidget with QFrame | For sections/boxes |
| ft.Column | QVBoxLayout | Vertical layout |
| ft.Row | QHBoxLayout | Horizontal layout |
| ft.Divider | QFrame with HLine | Separator line |

## Workflow Integration

### Agent Connection

The Qt Research tab MUST connect to real agents (not mocks):

```python
# Already available in bmlibrarian/agents:
from bmlibrarian.agents import (
    QueryAgent,
    DocumentScoringAgent,
    CitationFinderAgent,
    ReportingAgent,
    CounterfactualAgent,
    EditorAgent,
    AgentOrchestrator
)

# Already available in bmlibrarian/cli:
from bmlibrarian.cli import CLIConfig, WorkflowOrchestrator
from bmlibrarian.cli.workflow_steps import WorkflowStep
```

### Workflow Steps Execution

Flet GUI uses a `WorkflowExecutor` that:
1. Initializes agents in main thread
2. Runs workflow steps in background threads
3. Updates UI via signals/callbacks
4. Supports both interactive and auto modes

**Qt Must Replicate This**:
- Use `QThreadPool` and `QRunnable` for background execution
- Use Qt Signals for progress updates
- Wire to existing `WorkflowOrchestrator` from CLI
- Support same interactive/auto mode logic

### Threading Model

**Flet Approach**:
```python
# Background thread for workflow
def execute_workflow():
    for step in workflow_steps:
        result = execute_step(step)
        emit_progress(step, result)

# UI updates via page.update()
```

**Qt Approach**:
```python
# QRunnable worker
class WorkflowWorker(QRunnable):
    def __init__(self, signals):
        self.signals = signals

    def run(self):
        for step in workflow_steps:
            result = execute_step(step)
            self.signals.progress.emit(step, result)

# Connect signals to UI slots
worker.signals.progress.connect(self.on_workflow_progress)
```

## Implementation Plan

### Phase 1: Layout Structure (No Functionality)
✅ **COMPLETED**: Config file separation

🔲 **Next Tasks**:
1. Create header section (title + subtitle)
2. Create controls section (question input, toggles, buttons)
3. Create 8 empty tab widgets
4. Wire up basic UI interactions (button clicks, tab changes)
5. Apply styling to match Flet colors/spacing

### Phase 2: Connect to Real Agents
1. Import agent modules
2. Initialize agents (in main thread)
3. Create WorkflowExecutor adapter for Qt
4. Test agent connectivity (without full workflow)

### Phase 3: Implement Workflow Execution
1. Implement background workflow execution (QThreadPool)
2. Connect progress signals to UI updates
3. Implement each workflow step handler
4. Update appropriate tab content for each step

### Phase 4: Interactive Mode
1. Implement query editing in Search tab
2. Implement interactive scoring in Scoring tab
3. Implement citation requests in Citations tab
4. Implement report revision in Report tab

### Phase 5: Tab Content Population
1. Populate Literature tab with documents
2. Populate Scoring tab with scoring results
3. Populate Citations tab with extracted citations
4. Populate Report tabs with markdown rendering

### Phase 6: Testing & Polish
1. Test complete workflow end-to-end
2. Test with 100+ documents
3. Test interactive vs auto modes
4. Fix any UI glitches
5. Match Flet styling exactly

## Critical Requirements

### Must-Haves for Feature Parity

✅ All 8 tabs functional
✅ Real agent integration (no mocks)
✅ Background workflow execution
✅ Progress indicators during long operations
✅ Interactive mode support (query editing, manual scoring)
✅ Auto mode support (non-interactive)
✅ Markdown rendering for reports
✅ Document cards with expandable abstracts
✅ Citation cards with relevance scores
✅ Export functionality (save reports)
✅ Settings tab for configuration
✅ Process ALL documents (no artificial limits unless configured)

### Nice-to-Haves (Post-Feature-Parity)

- Dark theme support
- Keyboard shortcuts
- Search within tabs
- Document filtering/sorting
- Copy to clipboard buttons
- Printing support
- Multi-window support

## File Structure

```
src/bmlibrarian/gui/qt/plugins/research/
├── __init__.py
├── plugin.py                  # Plugin entry point
├── research_tab.py            # Main tab widget (REPLACE CURRENT)
├── workflow_executor.py       # Qt workflow orchestrator (NEW)
├── tabs/                      # Sub-tabs (NEW)
│   ├── __init__.py
│   ├── search_tab.py         # Search query display
│   ├── literature_tab.py     # Document list
│   ├── scoring_tab.py        # Interactive scoring
│   ├── citations_tab.py      # Citations display
│   ├── preliminary_tab.py    # Preliminary report
│   ├── counterfactual_tab.py # Counterfactual analysis
│   ├── report_tab.py         # Final report
│   └── settings_tab.py       # Configuration
└── widgets/                   # Reusable components (NEW)
    ├── __init__.py
    ├── document_list.py      # Document cards list
    ├── citation_list.py      # Citation cards list
    ├── scoring_widget.py     # Interactive scoring UI
    └── report_viewer.py      # Markdown report display
```

## Next Steps

1. ✅ Separate config files (DONE)
2. 📝 Review this design document with user
3. 🔨 Implement Phase 1: Layout structure
4. 🔨 Implement Phase 2: Agent connection
5. 🔨 Implement Phase 3: Workflow execution
6. 🔨 Implement Phase 4: Interactive mode
7. 🔨 Implement Phase 5: Tab content
8. ✅ Test and polish

## Success Criteria

The Qt Research tab will be considered complete when:

1. ✅ Layout matches Flet pixel-perfect (or as close as Qt allows)
2. ✅ All 8 tabs are functional
3. ✅ Complete workflow executes from start to finish
4. ✅ Interactive mode works (query editing, manual scoring)
5. ✅ Auto mode works (non-interactive execution)
6. ✅ Real agents are used (no mocks)
7. ✅ Reports are properly rendered in markdown
8. ✅ Export functionality works
9. ✅ Can run alongside Flet GUI without conflicts
10. ✅ User can complete a research workflow successfully

---

**Status**: Design Phase Complete, Ready for Implementation
**Last Updated**: 2025-11-16
**Next Action**: Implement Phase 1 - Layout Structure
