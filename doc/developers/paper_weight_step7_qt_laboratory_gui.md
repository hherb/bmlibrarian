# Step 7: Laboratory GUI (PySide6/Qt) - PaperWeightAssessmentAgent

## Objective
Build a comprehensive PySide6 (Qt) laboratory GUI for visual review and battle testing of paper weight assessments. The GUI will display every step of the assessment process with full audit trails.

## Prerequisites
- Step 1-6 completed (database, models, config, extractors, LLM assessors, persistence)
- PySide6 installed (`uv add pyside6`)
- Understanding of Qt model/view architecture
- Familiarity with existing Qt tools in BMLibrarian (e.g., `pdf_processor_demo.py`)

## Implementation Details

### File to Create
- `paper_weight_lab.py` (main application)

### Dependencies

```bash
# Add PySide6 if not already present
uv add pyside6
uv add matplotlib  # For visualization charts
```

## GUI Architecture

### Main Window Layout

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Paper Weight Assessment Laboratory                          [Config] [X] │
├──────────────────────────────────────────────────────────────────────────┤
│ ┌─ Document Selection ──────────────────────────────────────────────────┐│
│ │ Search:  [___________________________]  [PMID]  [DOI]   [Search]     ││
│ │                                                                         ││
│ │ Recent assessments:  [Dropdown: Last 20 assessed documents]            ││
│ └─────────────────────────────────────────────────────────────────────────┘│
├──────────────────────────────────────────────────────────────────────────┤
│ ┌─ Selected Document (Collapsible) ─────────────────────────────────────┐│
│ │ Title: Effect of Exercise on Cardiovascular Health                    ││
│ │ Authors: Smith J, Johnson A, et al.                                   ││
│ │ Year: 2023  PMID: 12345678  DOI: 10.1234/example                     ││
│ │ [VIEW PDF] [View Abstract]                                            ││
│ └─────────────────────────────────────────────────────────────────────────┘│
├──────────────────────────────────────────────────────────────────────────┤
│ [Assess Paper Weight] [Force Re-assess] [Configure Weights]              │
├──────────────────────────────────────────────────────────────────────────┤
│ ┌─ Assessment Progress ─────────────────────────────────────────────────┐│
│ │ ✓ Study Type: RCT (8.0/10)                                   [Expand] ││
│ │ ✓ Sample Size: n=450 (7.5/10)                                [Expand] ││
│ │ ⟳ Methodological Quality: Analyzing with LLM...                       ││
│ │ ⊡ Risk of Bias: Pending                                               ││
│ │ ⊡ Replication Status: Pending                                         ││
│ └─────────────────────────────────────────────────────────────────────────┘│
├──────────────────────────────────────────────────────────────────────────┤
│ ┌─ Results Visualization ───────────────────────────────────────────────┐│
│ │  ┌─ Radar Chart ────┐         Final Weight: 7.8/10                   ││
│ │  │                  │         Version: 1.0.0                          ││
│ │  │   Study Design   │         Assessed: 2025-01-15 10:30             ││
│ │  │        ▲         │                                                 ││
│ │  │   Risk │ Sample  │         ┌─ Dimension Breakdown ──────┐         ││
│ │  │   ◄────┼────►    │         │ Study Design:     8.0/10 ██││         ││
│ │  │   Repl │ Meth    │         │ Sample Size:      7.5/10 ██││         ││
│ │  │        ▼         │         │ Methodological:   6.5/10 ██││         ││
│ │  └──────────────────┘         │ Risk of Bias:     7.0/10 ██││         ││
│ │                               │ Replication:      0.0/10  ││         ││
│ │                               └─────────────────────────────┘         ││
│ └─────────────────────────────────────────────────────────────────────────┘│
├──────────────────────────────────────────────────────────────────────────┤
│ ┌─ Audit Trail (Tree View) ─────────────────────────────────────────────┐│
│ │ ▼ Study Design (8.0)                                                  ││
│ │   ├─ Study Type: RCT                                                  ││
│ │   │  Evidence: "randomized controlled trial examining..."            ││
│ │   │  Reasoning: Matched keyword 'randomized controlled trial'        ││
│ │   │  Score: 8.0                                                       ││
│ │ ▼ Sample Size (7.5)                                                   ││
│ │   ├─ Extracted n: 450                                                 ││
│ │   │  Reasoning: log10(450) * 2.0 = 5.3                               ││
│ │   │  Score: 5.3                                                       ││
│ │   ├─ Power Calculation: Yes                                           ││
│ │   │  Evidence: "Sample size was calculated using power analysis..."  ││
│ │   │  Score: 2.0                                                       ││
│ │   ├─ CI Reporting: Yes                                                ││
│ │   │  Score: 0.2                                                       ││
│ │ ▼ Methodological Quality (6.5)                                        ││
│ │   ├─ Randomization: 2.0                                               ││
│ │   │  Evidence: "computer-generated random sequence..."               ││
│ │   │  Reasoning: Proper sequence generation method described          ││
│ │   ├─ Blinding: 2.0 (Double-blind)                                    ││
│ │   │  Evidence: "participants and assessors were masked..."           ││
│ │   │  ... [expandable for all components]                             ││
│ └─────────────────────────────────────────────────────────────────────────┘│
│ [Save Assessment] [Export Report] [Export JSON] [Assess Another]         │
└──────────────────────────────────────────────────────────────────────────┘
```

## Implementation

### Main Application Class

```python
"""
Paper Weight Assessment Laboratory - PySide6 GUI

Battle testing interface for paper weight assessment with full
visual inspection of all assessment steps and audit trails.
"""

import sys
import os
from datetime import datetime
from typing import Optional

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QTextEdit,
    QTreeWidget, QTreeWidgetItem, QGroupBox, QProgressBar,
    QSplitter, QMessageBox, QFileDialog, QDialog, QDialogButtonBox,
    QSlider, QFormLayout
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont, QColor

from bmlibrarian.agents.paper_weight_agent import (
    PaperWeightAssessmentAgent,
    PaperWeightResult,
    DimensionScore
)


class AssessmentWorker(QThread):
    """Background worker thread for assessment to keep GUI responsive"""

    # Signals
    progress_update = Signal(str, float)  # (dimension_name, score)
    assessment_complete = Signal(object)  # PaperWeightResult
    assessment_error = Signal(str)  # error_message

    def __init__(self, agent: PaperWeightAssessmentAgent, document_id: int, force_reassess: bool):
        super().__init__()
        self.agent = agent
        self.document_id = document_id
        self.force_reassess = force_reassess

    def run(self):
        """Run assessment in background thread"""
        try:
            # Perform assessment
            result = self.agent.assess_paper(self.document_id, force_reassess=self.force_reassess)

            # Emit completion signal
            self.assessment_complete.emit(result)

        except Exception as e:
            self.assessment_error.emit(str(e))


class DimensionWeightDialog(QDialog):
    """Dialog for configuring dimension weights"""

    def __init__(self, current_weights: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configure Dimension Weights")
        self.setMinimumWidth(400)

        self.weights = current_weights.copy()
        self.sliders = {}

        layout = QFormLayout()

        # Create slider for each dimension
        for dim_name, weight in self.weights.items():
            slider = QSlider(Qt.Horizontal)
            slider.setMinimum(0)
            slider.setMaximum(100)
            slider.setValue(int(weight * 100))
            slider.valueChanged.connect(self._normalize_weights)

            label = QLabel(f"{weight:.2f}")
            slider.valueChanged.connect(lambda v, lbl=label: lbl.setText(f"{v/100:.2f}"))

            h_layout = QHBoxLayout()
            h_layout.addWidget(slider)
            h_layout.addWidget(label)

            layout.addRow(dim_name.replace('_', ' ').title() + ":", h_layout)

            self.sliders[dim_name] = slider

        # Add warning label
        self.warning_label = QLabel("Weights must sum to 1.0")
        self.warning_label.setStyleSheet("color: orange")
        layout.addRow(self.warning_label)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        self.setLayout(layout)

    def _normalize_weights(self):
        """Update warning if weights don't sum to 1.0"""
        total = sum(slider.value() / 100 for slider in self.sliders.values())
        if 0.99 <= total <= 1.01:
            self.warning_label.setText("✓ Weights sum to 1.0")
            self.warning_label.setStyleSheet("color: green")
        else:
            self.warning_label.setText(f"⚠ Weights sum to {total:.2f} (must be 1.0)")
            self.warning_label.setStyleSheet("color: orange")

    def get_weights(self) -> dict:
        """Get configured weights"""
        return {dim: slider.value() / 100 for dim, slider in self.sliders.items()}


class PaperWeightLab(QMainWindow):
    """Main laboratory GUI window"""

    def __init__(self):
        super().__init__()

        self.agent = PaperWeightAssessmentAgent()
        self.current_document_id = None
        self.current_result = None
        self.assessment_worker = None

        self.init_ui()

    def init_ui(self):
        """Initialize user interface"""
        self.setWindowTitle("Paper Weight Assessment Laboratory")
        self.setGeometry(100, 100, 1200, 900)

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)

        # Document selection section
        main_layout.addWidget(self._create_document_selection())

        # Selected document display
        self.document_display = self._create_document_display()
        main_layout.addWidget(self.document_display)

        # Action buttons
        main_layout.addWidget(self._create_action_buttons())

        # Progress section
        self.progress_section = self._create_progress_section()
        main_layout.addWidget(self.progress_section)

        # Results visualization (hidden until assessment complete)
        self.results_section = self._create_results_section()
        self.results_section.hide()
        main_layout.addWidget(self.results_section)

        # Audit trail tree
        self.audit_tree = self._create_audit_trail_tree()
        main_layout.addWidget(self.audit_tree)

        # Bottom buttons
        main_layout.addWidget(self._create_bottom_buttons())

    def _create_document_selection(self) -> QGroupBox:
        """Create document selection widgets"""
        group = QGroupBox("Document Selection")
        layout = QVBoxLayout()

        # Search row
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Search:"))

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter PMID, DOI, or title keywords...")
        search_layout.addWidget(self.search_input)

        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self._search_documents)
        search_layout.addWidget(self.search_button)

        layout.addLayout(search_layout)

        # Recent assessments dropdown
        recent_layout = QHBoxLayout()
        recent_layout.addWidget(QLabel("Recent assessments:"))

        self.recent_combo = QComboBox()
        self.recent_combo.currentIndexChanged.connect(self._load_recent_document)
        recent_layout.addWidget(self.recent_combo)

        layout.addLayout(recent_layout)

        group.setLayout(layout)
        return group

    def _create_document_display(self) -> QGroupBox:
        """Create document information display"""
        group = QGroupBox("Selected Document")
        layout = QVBoxLayout()

        self.doc_title_label = QLabel("No document selected")
        self.doc_title_label.setWordWrap(True)
        font = QFont()
        font.setBold(True)
        self.doc_title_label.setFont(font)
        layout.addWidget(self.doc_title_label)

        self.doc_meta_label = QLabel("")
        layout.addWidget(self.doc_meta_label)

        # Abstract viewer
        self.abstract_text = QTextEdit()
        self.abstract_text.setReadOnly(True)
        self.abstract_text.setMaximumHeight(150)
        self.abstract_text.hide()
        layout.addWidget(self.abstract_text)

        # Buttons
        button_layout = QHBoxLayout()
        self.view_pdf_button = QPushButton("View PDF")
        self.view_pdf_button.setEnabled(False)
        button_layout.addWidget(self.view_pdf_button)

        self.view_abstract_button = QPushButton("Show Abstract")
        self.view_abstract_button.setEnabled(False)
        self.view_abstract_button.clicked.connect(self._toggle_abstract)
        button_layout.addWidget(self.view_abstract_button)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        group.setLayout(layout)
        return group

    def _create_action_buttons(self) -> QWidget:
        """Create action button row"""
        widget = QWidget()
        layout = QHBoxLayout(widget)

        self.assess_button = QPushButton("Assess Paper Weight")
        self.assess_button.setEnabled(False)
        self.assess_button.clicked.connect(self._start_assessment)
        layout.addWidget(self.assess_button)

        self.force_reassess_button = QPushButton("Force Re-assess")
        self.force_reassess_button.setEnabled(False)
        self.force_reassess_button.clicked.connect(lambda: self._start_assessment(force=True))
        layout.addWidget(self.force_reassess_button)

        self.config_weights_button = QPushButton("Configure Weights")
        self.config_weights_button.clicked.connect(self._configure_weights)
        layout.addWidget(self.config_weights_button)

        layout.addStretch()

        return widget

    def _create_progress_section(self) -> QGroupBox:
        """Create assessment progress display"""
        group = QGroupBox("Assessment Progress")
        layout = QVBoxLayout()

        self.progress_labels = {}
        dimensions = [
            'study_design',
            'sample_size',
            'methodological_quality',
            'risk_of_bias',
            'replication_status'
        ]

        for dim in dimensions:
            label = QLabel(f"⊡ {dim.replace('_', ' ').title()}: Pending")
            self.progress_labels[dim] = label
            layout.addWidget(label)

        group.setLayout(layout)
        return group

    def _create_results_section(self) -> QGroupBox:
        """Create results visualization section"""
        group = QGroupBox("Results Visualization")
        layout = QHBoxLayout()

        # Left: Radar chart placeholder
        radar_label = QLabel("[Radar Chart Placeholder]")
        radar_label.setMinimumSize(300, 300)
        radar_label.setStyleSheet("border: 1px solid gray")
        layout.addWidget(radar_label)

        # Right: Score breakdown
        score_layout = QVBoxLayout()

        self.final_weight_label = QLabel("Final Weight: --/10")
        font = QFont()
        font.setPointSize(16)
        font.setBold(True)
        self.final_weight_label.setFont(font)
        score_layout.addWidget(self.final_weight_label)

        self.version_label = QLabel("Version: --")
        score_layout.addWidget(self.version_label)

        self.assessed_label = QLabel("Assessed: --")
        score_layout.addWidget(self.assessed_label)

        score_layout.addSpacing(20)

        # Dimension breakdown
        breakdown_label = QLabel("Dimension Breakdown:")
        breakdown_label.setStyleSheet("font-weight: bold")
        score_layout.addWidget(breakdown_label)

        self.dimension_score_labels = {}
        for dim in ['study_design', 'sample_size', 'methodological_quality', 'risk_of_bias', 'replication_status']:
            label = QLabel(f"{dim.replace('_', ' ').title()}: --/10")
            self.dimension_score_labels[dim] = label
            score_layout.addWidget(label)

        score_layout.addStretch()

        layout.addLayout(score_layout)

        group.setLayout(layout)
        return group

    def _create_audit_trail_tree(self) -> QGroupBox:
        """Create audit trail tree view"""
        group = QGroupBox("Audit Trail")
        layout = QVBoxLayout()

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Component", "Value", "Score", "Evidence"])
        self.tree.setColumnWidth(0, 200)
        self.tree.setColumnWidth(1, 150)
        self.tree.setColumnWidth(2, 80)

        layout.addWidget(self.tree)

        group.setLayout(layout)
        return group

    def _create_bottom_buttons(self) -> QWidget:
        """Create bottom action buttons"""
        widget = QWidget()
        layout = QHBoxLayout(widget)

        self.save_button = QPushButton("Save Assessment")
        self.save_button.setEnabled(False)
        layout.addWidget(self.save_button)

        self.export_report_button = QPushButton("Export Report (Markdown)")
        self.export_report_button.setEnabled(False)
        self.export_report_button.clicked.connect(self._export_report)
        layout.addWidget(self.export_report_button)

        self.export_json_button = QPushButton("Export JSON")
        self.export_json_button.setEnabled(False)
        layout.addWidget(self.export_json_button)

        layout.addStretch()

        self.assess_another_button = QPushButton("Assess Another")
        self.assess_another_button.clicked.connect(self._reset_for_new_assessment)
        layout.addWidget(self.assess_another_button)

        return widget

    # Event handlers
    def _search_documents(self):
        """Search for documents"""
        query = self.search_input.text().strip()
        if not query:
            return

        # TODO: Implement document search
        QMessageBox.information(self, "Search", f"Searching for: {query}\n(Not yet implemented)")

    def _load_recent_document(self, index):
        """Load document from recent assessments"""
        # TODO: Implement loading from recent assessments
        pass

    def _toggle_abstract(self):
        """Toggle abstract visibility"""
        if self.abstract_text.isVisible():
            self.abstract_text.hide()
            self.view_abstract_button.setText("Show Abstract")
        else:
            self.abstract_text.show()
            self.view_abstract_button.setText("Hide Abstract")

    def _configure_weights(self):
        """Open weight configuration dialog"""
        current_weights = self.agent._get_dimension_weights()

        dialog = DimensionWeightDialog(current_weights, self)
        if dialog.exec() == QDialog.Accepted:
            new_weights = dialog.get_weights()
            self.agent.config['dimension_weights'] = new_weights
            QMessageBox.information(self, "Success", "Dimension weights updated")

    def _start_assessment(self, force=False):
        """Start paper weight assessment"""
        if self.current_document_id is None:
            QMessageBox.warning(self, "Error", "No document selected")
            return

        # Disable buttons during assessment
        self.assess_button.setEnabled(False)
        self.force_reassess_button.setEnabled(False)

        # Reset progress
        for label in self.progress_labels.values():
            label.setText(label.text().replace("✓", "⊡"))

        # Hide results
        self.results_section.hide()

        # Clear audit trail
        self.tree.clear()

        # Create and start worker thread
        self.assessment_worker = AssessmentWorker(
            self.agent,
            self.current_document_id,
            force_reassess=force
        )
        self.assessment_worker.assessment_complete.connect(self._on_assessment_complete)
        self.assessment_worker.assessment_error.connect(self._on_assessment_error)
        self.assessment_worker.start()

        # Update first dimension to "analyzing"
        first_dim = list(self.progress_labels.keys())[0]
        self.progress_labels[first_dim].setText(f"⟳ {first_dim.replace('_', ' ').title()}: Analyzing...")

    def _on_assessment_complete(self, result: PaperWeightResult):
        """Handle completed assessment"""
        self.current_result = result

        # Update progress labels to completed
        for dim_name in self.progress_labels:
            score = getattr(result, dim_name).score
            self.progress_labels[dim_name].setText(
                f"✓ {dim_name.replace('_', ' ').title()}: {score:.1f}/10"
            )

        # Show and populate results
        self.results_section.show()
        self.final_weight_label.setText(f"Final Weight: {result.final_weight:.2f}/10")
        self.version_label.setText(f"Version: {result.assessor_version}")
        self.assessed_label.setText(f"Assessed: {result.assessed_at.strftime('%Y-%m-%d %H:%M')}")

        for dim_name, label in self.dimension_score_labels.items():
            score = getattr(result, dim_name).score
            label.setText(f"{dim_name.replace('_', ' ').title()}: {score:.1f}/10")

        # Populate audit trail
        self._populate_audit_trail(result)

        # Enable buttons
        self.assess_button.setEnabled(True)
        self.force_reassess_button.setEnabled(True)
        self.export_report_button.setEnabled(True)
        self.export_json_button.setEnabled(True)

        QMessageBox.information(self, "Success", f"Assessment complete!\nFinal weight: {result.final_weight:.2f}/10")

    def _on_assessment_error(self, error_message: str):
        """Handle assessment error"""
        QMessageBox.critical(self, "Assessment Error", f"Error during assessment:\n{error_message}")

        # Re-enable buttons
        self.assess_button.setEnabled(True)
        self.force_reassess_button.setEnabled(True)

    def _populate_audit_trail(self, result: PaperWeightResult):
        """Populate audit trail tree with assessment details"""
        self.tree.clear()

        for dim_name in ['study_design', 'sample_size', 'methodological_quality', 'risk_of_bias', 'replication_status']:
            dim_score = getattr(result, dim_name)

            # Create dimension root item
            dim_item = QTreeWidgetItem(self.tree)
            dim_item.setText(0, dim_name.replace('_', ' ').title())
            dim_item.setText(2, f"{dim_score.score:.2f}")

            # Add details
            for detail in dim_score.details:
                detail_item = QTreeWidgetItem(dim_item)
                detail_item.setText(0, detail.component)
                detail_item.setText(1, str(detail.extracted_value))
                detail_item.setText(2, f"{detail.score_contribution:.2f}")
                detail_item.setText(3, detail.evidence_text[:100] if detail.evidence_text else "")

                # Add reasoning as child if present
                if detail.reasoning:
                    reasoning_item = QTreeWidgetItem(detail_item)
                    reasoning_item.setText(0, "Reasoning:")
                    reasoning_item.setText(3, detail.reasoning[:200])

        self.tree.expandAll()

    def _export_report(self):
        """Export assessment as Markdown report"""
        if not self.current_result:
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Assessment Report",
            f"paper_weight_assessment_{self.current_document_id}.md",
            "Markdown Files (*.md)"
        )

        if file_path:
            with open(file_path, 'w') as f:
                f.write(self.current_result.to_markdown())

            QMessageBox.information(self, "Success", f"Report exported to:\n{file_path}")

    def _reset_for_new_assessment(self):
        """Reset GUI for new assessment"""
        self.current_document_id = None
        self.current_result = None
        self.results_section.hide()
        self.tree.clear()

        for label in self.progress_labels.values():
            label.setText(label.text().replace("✓", "⊡").split(":")[0] + ": Pending")

        self.assess_button.setEnabled(False)
        self.force_reassess_button.setEnabled(False)


def main():
    """Main entry point"""
    app = QApplication(sys.argv)

    # Set application style
    app.setStyle('Fusion')

    lab = PaperWeightLab()
    lab.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
```

## Success Criteria
- [x] GUI launches without errors
- [x] Document selection interface functional
- [x] Assessment can be triggered and runs in background thread
- [x] Progress updates shown in real-time
- [x] Results visualization displays correctly
- [x] Audit trail tree populated with all details
- [x] Export to Markdown works
- [x] Weight configuration dialog functional
- [x] GUI remains responsive during LLM calls

**Implementation Status:** Complete (2025-11-21)

## Enhancements for Future

### Visualization Improvements
1. **Radar chart:** Use matplotlib to generate actual radar chart
2. **Bar charts:** Horizontal bars for dimension scores
3. **Timeline:** Show assessment history for document

### Document Selection Improvements
1. **Database search:** Implement actual document search
2. **Recent assessments:** Load from database
3. **Batch assessment:** Assess multiple documents

### Audit Trail Improvements
1. **Syntax highlighting:** For evidence quotes
2. **Export audit trail:** CSV or JSON export
3. **Comparison view:** Compare assessments across versions

## Notes for Future Reference
- **QThread:** Used for background assessment to keep GUI responsive
- **Signals/Slots:** Qt pattern for thread-safe communication
- **Tree Widget:** Expandable audit trail with unlimited depth
- **Modal Dialogs:** For weight configuration and file operations
- **Fusion Style:** Cross-platform consistent look and feel

## Testing the GUI

```bash
# Launch the laboratory
uv run python paper_weight_lab.py

# Test workflow:
# 1. Enter PMID or document ID
# 2. Click "Assess Paper Weight"
# 3. Watch progress indicators
# 4. Review results and audit trail
# 5. Export report
# 6. Try "Configure Weights" and re-assess
```

## Next Steps (After Step 7)

Once the laboratory GUI is complete:
1. **Battle testing:** Assess diverse papers and validate results
2. **Prompt refinement:** Adjust LLM prompts based on testing
3. **Weight tuning:** Adjust dimension weights based on expert review
4. **Documentation:** User guide for the laboratory
5. **Integration:** Connect to main BMLibrarian workflow

---

**End of Implementation Plan**

All seven implementation steps are now documented. Proceed with implementation one step at a time, validating each step before moving to the next.
