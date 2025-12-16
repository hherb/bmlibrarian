# Phase 3: GUI Integration

## Overview

This phase integrates quality filtering into the BMLibrarian Lite GUI:
1. Quality filter panel (collapsible settings)
2. Quality badges on document cards
3. Workflow integration
4. Settings dialog updates

## Prerequisites

- Phase 1 and 2 complete (quality module implemented)
- Familiarity with BMLibrarian Lite's PySide6 GUI architecture

---

## Step 1: Create Quality Filter Panel

### 1.1 File: `src/bmlibrarian/lite/gui/quality_filter_panel.py`

```python
# src/bmlibrarian/lite/gui/quality_filter_panel.py
"""
Collapsible quality filter panel for systematic review workflow.

Allows users to configure quality filtering criteria before
or during document search.
"""

import logging
from typing import Optional

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QCheckBox,
    QSpinBox,
    QPushButton,
    QGroupBox,
)

from ..quality.data_models import QualityTier, QualityFilter

logger = logging.getLogger(__name__)


class QualityFilterPanel(QFrame):
    """
    Collapsible panel for configuring quality filters.

    Emits filterChanged signal when user modifies settings.
    """

    # Emitted when filter settings change
    filterChanged = Signal(QualityFilter)

    # Tier dropdown options
    TIER_OPTIONS = [
        ("No filter (include all)", QualityTier.UNCLASSIFIED),
        ("Primary research (exclude opinions)", QualityTier.TIER_2_OBSERVATIONAL),
        ("Controlled studies (cohort+)", QualityTier.TIER_3_CONTROLLED),
        ("High-quality evidence (RCT+)", QualityTier.TIER_4_EXPERIMENTAL),
        ("Systematic evidence only (SR/MA)", QualityTier.TIER_5_SYNTHESIS),
    ]

    def __init__(self, parent=None):
        """Initialize the quality filter panel."""
        super().__init__(parent)
        self._collapsed = True
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        """Set up the panel UI."""
        self.setFrameShape(QFrame.StyledPanel)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Header with toggle button
        header = QHBoxLayout()
        self.toggle_btn = QPushButton("▶ Quality Filters")
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.setFlat(True)
        self.toggle_btn.setStyleSheet("""
            QPushButton {
                text-align: left;
                font-weight: bold;
                padding: 4px;
            }
            QPushButton:checked {
                color: #2196F3;
            }
        """)
        header.addWidget(self.toggle_btn)
        header.addStretch()

        # Status label showing current filter
        self.status_label = QLabel("All studies")
        self.status_label.setStyleSheet("color: #666;")
        header.addWidget(self.status_label)

        layout.addLayout(header)

        # Collapsible content
        self.content = QFrame()
        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(0, 8, 0, 0)
        content_layout.setSpacing(12)

        # === Minimum Quality Tier ===
        tier_group = QGroupBox("Minimum Study Quality")
        tier_layout = QVBoxLayout(tier_group)

        self.tier_combo = QComboBox()
        for label, _ in self.TIER_OPTIONS:
            self.tier_combo.addItem(label)
        self.tier_combo.setToolTip(
            "Filter documents by study design quality.\n"
            "Higher tiers include only higher-quality evidence."
        )
        tier_layout.addWidget(self.tier_combo)

        content_layout.addWidget(tier_group)

        # === Specific Requirements ===
        req_group = QGroupBox("Additional Requirements")
        req_layout = QVBoxLayout(req_group)

        self.require_randomization = QCheckBox("Require randomization")
        self.require_randomization.setToolTip(
            "Only include studies with randomized allocation"
        )
        req_layout.addWidget(self.require_randomization)

        self.require_blinding = QCheckBox("Require blinding (any level)")
        self.require_blinding.setToolTip(
            "Only include studies with single, double, or triple blinding"
        )
        req_layout.addWidget(self.require_blinding)

        # Sample size requirement
        sample_layout = QHBoxLayout()
        self.require_sample_size = QCheckBox("Minimum sample size:")
        sample_layout.addWidget(self.require_sample_size)

        self.sample_size_spin = QSpinBox()
        self.sample_size_spin.setRange(1, 100000)
        self.sample_size_spin.setValue(100)
        self.sample_size_spin.setEnabled(False)
        sample_layout.addWidget(self.sample_size_spin)
        sample_layout.addStretch()

        req_layout.addLayout(sample_layout)
        content_layout.addWidget(req_group)

        # === Assessment Depth ===
        depth_group = QGroupBox("Assessment Method")
        depth_layout = QVBoxLayout(depth_group)

        self.metadata_only = QCheckBox("Metadata only (free, instant)")
        self.metadata_only.setToolTip(
            "Use only PubMed publication types.\n"
            "Fast but may miss unindexed articles."
        )
        depth_layout.addWidget(self.metadata_only)

        self.use_llm = QCheckBox("AI classification for unindexed articles")
        self.use_llm.setChecked(True)
        self.use_llm.setToolTip(
            "Use Claude Haiku for articles without publication types.\n"
            "Cost: ~$0.00025 per article"
        )
        depth_layout.addWidget(self.use_llm)

        self.detailed_assessment = QCheckBox("Detailed quality assessment")
        self.detailed_assessment.setToolTip(
            "Full assessment with bias risk analysis.\n"
            "Uses Claude Sonnet (~$0.003 per article).\n"
            "Recommended for systematic reviews."
        )
        depth_layout.addWidget(self.detailed_assessment)

        content_layout.addWidget(depth_group)

        layout.addWidget(self.content)
        self.content.setVisible(False)

    def _connect_signals(self):
        """Connect widget signals."""
        self.toggle_btn.toggled.connect(self._toggle_content)
        self.tier_combo.currentIndexChanged.connect(self._on_filter_changed)
        self.require_randomization.toggled.connect(self._on_filter_changed)
        self.require_blinding.toggled.connect(self._on_filter_changed)
        self.require_sample_size.toggled.connect(self._on_sample_size_toggled)
        self.sample_size_spin.valueChanged.connect(self._on_filter_changed)
        self.metadata_only.toggled.connect(self._on_metadata_only_toggled)
        self.use_llm.toggled.connect(self._on_filter_changed)
        self.detailed_assessment.toggled.connect(self._on_filter_changed)

    def _toggle_content(self, checked: bool):
        """Toggle content visibility."""
        self._collapsed = not checked
        self.content.setVisible(checked)
        self.toggle_btn.setText(
            "▼ Quality Filters" if checked else "▶ Quality Filters"
        )

    def _on_filter_changed(self):
        """Handle filter setting changes."""
        filter_settings = self.get_filter()
        self._update_status_label(filter_settings)
        self.filterChanged.emit(filter_settings)

    def _on_sample_size_toggled(self, checked: bool):
        """Handle sample size checkbox toggle."""
        self.sample_size_spin.setEnabled(checked)
        self._on_filter_changed()

    def _on_metadata_only_toggled(self, checked: bool):
        """Handle metadata-only toggle."""
        if checked:
            self.use_llm.setChecked(False)
            self.use_llm.setEnabled(False)
            self.detailed_assessment.setChecked(False)
            self.detailed_assessment.setEnabled(False)
        else:
            self.use_llm.setEnabled(True)
            self.detailed_assessment.setEnabled(True)
        self._on_filter_changed()

    def _update_status_label(self, filter_settings: QualityFilter):
        """Update status label with current filter summary."""
        tier_idx = self.tier_combo.currentIndex()
        tier_label = self.TIER_OPTIONS[tier_idx][0]

        parts = [tier_label.split("(")[0].strip()]

        if filter_settings.require_randomization:
            parts.append("randomized")
        if filter_settings.require_blinding:
            parts.append("blinded")
        if filter_settings.minimum_sample_size:
            parts.append(f"n≥{filter_settings.minimum_sample_size}")

        self.status_label.setText(" • ".join(parts))

    def get_filter(self) -> QualityFilter:
        """
        Get current filter settings.

        Returns:
            QualityFilter with current settings
        """
        tier_idx = self.tier_combo.currentIndex()
        minimum_tier = self.TIER_OPTIONS[tier_idx][1]

        return QualityFilter(
            minimum_tier=minimum_tier,
            require_randomization=self.require_randomization.isChecked(),
            require_blinding=self.require_blinding.isChecked(),
            minimum_sample_size=(
                self.sample_size_spin.value()
                if self.require_sample_size.isChecked()
                else None
            ),
            use_metadata_only=self.metadata_only.isChecked(),
            use_llm_classification=self.use_llm.isChecked(),
            use_detailed_assessment=self.detailed_assessment.isChecked(),
        )

    def set_filter(self, filter_settings: QualityFilter):
        """
        Set filter settings from QualityFilter object.

        Args:
            filter_settings: Settings to apply
        """
        # Find matching tier index
        for i, (_, tier) in enumerate(self.TIER_OPTIONS):
            if tier == filter_settings.minimum_tier:
                self.tier_combo.setCurrentIndex(i)
                break

        self.require_randomization.setChecked(filter_settings.require_randomization)
        self.require_blinding.setChecked(filter_settings.require_blinding)

        if filter_settings.minimum_sample_size:
            self.require_sample_size.setChecked(True)
            self.sample_size_spin.setValue(filter_settings.minimum_sample_size)
        else:
            self.require_sample_size.setChecked(False)

        self.metadata_only.setChecked(filter_settings.use_metadata_only)
        self.use_llm.setChecked(filter_settings.use_llm_classification)
        self.detailed_assessment.setChecked(filter_settings.use_detailed_assessment)

    def expand(self):
        """Expand the panel."""
        self.toggle_btn.setChecked(True)

    def collapse(self):
        """Collapse the panel."""
        self.toggle_btn.setChecked(False)
```

---

## Step 2: Create Quality Badge Widget

### 2.1 File: `src/bmlibrarian/lite/gui/quality_badge.py`

```python
# src/bmlibrarian/lite/gui/quality_badge.py
"""
Quality badge widget for document cards.

Displays a color-coded badge indicating study design quality tier.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QFrame, QHBoxLayout
from PySide6.QtGui import QFont

from ..quality.data_models import QualityTier, StudyDesign, QualityAssessment


# Color scheme for quality tiers
TIER_COLORS = {
    QualityTier.TIER_5_SYNTHESIS: ("#4CAF50", "#FFFFFF"),      # Green
    QualityTier.TIER_4_EXPERIMENTAL: ("#2196F3", "#FFFFFF"),   # Blue
    QualityTier.TIER_3_CONTROLLED: ("#FF9800", "#FFFFFF"),     # Orange
    QualityTier.TIER_2_OBSERVATIONAL: ("#9E9E9E", "#FFFFFF"),  # Gray
    QualityTier.TIER_1_ANECDOTAL: ("#F44336", "#FFFFFF"),      # Red
    QualityTier.UNCLASSIFIED: ("#BDBDBD", "#666666"),          # Light gray
}

# Short labels for badges
TIER_LABELS = {
    QualityTier.TIER_5_SYNTHESIS: "SR/MA",
    QualityTier.TIER_4_EXPERIMENTAL: "RCT",
    QualityTier.TIER_3_CONTROLLED: "Controlled",
    QualityTier.TIER_2_OBSERVATIONAL: "Observational",
    QualityTier.TIER_1_ANECDOTAL: "Case/Opinion",
    QualityTier.UNCLASSIFIED: "?",
}

# More specific labels based on study design
DESIGN_LABELS = {
    StudyDesign.SYSTEMATIC_REVIEW: "SR",
    StudyDesign.META_ANALYSIS: "MA",
    StudyDesign.RCT: "RCT",
    StudyDesign.GUIDELINE: "Guideline",
    StudyDesign.COHORT_PROSPECTIVE: "Prospective",
    StudyDesign.COHORT_RETROSPECTIVE: "Retrospective",
    StudyDesign.CASE_CONTROL: "Case-Control",
    StudyDesign.CROSS_SECTIONAL: "Cross-Sec",
    StudyDesign.CASE_SERIES: "Case Series",
    StudyDesign.CASE_REPORT: "Case Report",
    StudyDesign.EDITORIAL: "Editorial",
    StudyDesign.LETTER: "Letter",
    StudyDesign.COMMENT: "Comment",
    StudyDesign.OTHER: "Other",
    StudyDesign.UNKNOWN: "?",
}


class QualityBadge(QFrame):
    """
    Color-coded badge showing document quality tier.

    Can display either tier label (SR/MA, RCT, etc.) or
    more specific study design label.
    """

    def __init__(
        self,
        assessment: QualityAssessment,
        show_design: bool = True,
        parent=None
    ):
        """
        Initialize the quality badge.

        Args:
            assessment: Quality assessment for the document
            show_design: If True, show specific design; if False, show tier
            parent: Parent widget
        """
        super().__init__(parent)
        self.assessment = assessment
        self.show_design = show_design
        self._setup_ui()

    def _setup_ui(self):
        """Set up the badge UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(4)

        # Get colors for tier
        tier = self.assessment.quality_tier
        bg_color, text_color = TIER_COLORS.get(
            tier,
            TIER_COLORS[QualityTier.UNCLASSIFIED]
        )

        # Get label text
        if self.show_design:
            label_text = DESIGN_LABELS.get(
                self.assessment.study_design,
                "?"
            )
        else:
            label_text = TIER_LABELS.get(tier, "?")

        # Create label
        self.label = QLabel(label_text)
        self.label.setAlignment(Qt.AlignCenter)

        # Style the badge
        font = QFont()
        font.setPointSize(9)
        font.setBold(True)
        self.label.setFont(font)

        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_color};
                border-radius: 3px;
            }}
            QLabel {{
                color: {text_color};
                padding: 0px;
            }}
        """)

        layout.addWidget(self.label)

        # Set tooltip with details
        self._set_tooltip()

    def _set_tooltip(self):
        """Set informative tooltip."""
        assessment = self.assessment

        lines = [
            f"Study Design: {assessment.study_design.value.replace('_', ' ').title()}",
            f"Quality Tier: {assessment.quality_tier.name.replace('_', ' ')}",
            f"Quality Score: {assessment.quality_score:.1f}/10",
            f"Confidence: {assessment.confidence:.0%}",
        ]

        if assessment.is_randomized is not None:
            lines.append(f"Randomized: {'Yes' if assessment.is_randomized else 'No'}")

        if assessment.is_blinded:
            lines.append(f"Blinding: {assessment.is_blinded.title()}")

        if assessment.sample_size:
            lines.append(f"Sample Size: {assessment.sample_size:,}")

        lines.append(f"\nSource: Tier {assessment.assessment_tier}")
        lines.append(f"Method: {assessment.extraction_method}")

        self.setToolTip("\n".join(lines))


class QualityBadgeSmall(QLabel):
    """
    Minimal quality badge for tight spaces.

    Shows only a colored dot or single character.
    """

    def __init__(
        self,
        tier: QualityTier,
        parent=None
    ):
        """
        Initialize minimal badge.

        Args:
            tier: Quality tier to display
            parent: Parent widget
        """
        super().__init__(parent)
        bg_color, _ = TIER_COLORS.get(tier, TIER_COLORS[QualityTier.UNCLASSIFIED])

        # Show tier number
        tier_num = tier.value if tier != QualityTier.UNCLASSIFIED else "?"
        self.setText(str(tier_num))

        self.setAlignment(Qt.AlignCenter)
        self.setFixedSize(18, 18)

        self.setStyleSheet(f"""
            QLabel {{
                background-color: {bg_color};
                color: white;
                border-radius: 9px;
                font-size: 10px;
                font-weight: bold;
            }}
        """)

        self.setToolTip(TIER_LABELS.get(tier, "Unknown"))
```

---

## Step 3: Integrate with Document Cards

### 3.1 Modify existing document card to include badge

Add quality badge to document cards in the systematic review tab.

```python
# In src/bmlibrarian/lite/gui/document_card.py (or equivalent)
# Add to the document card layout

from .quality_badge import QualityBadge

class LiteDocumentCard(QFrame):
    """Document card with quality badge support."""

    def __init__(
        self,
        document: LiteDocument,
        assessment: Optional[QualityAssessment] = None,
        parent=None
    ):
        super().__init__(parent)
        self.document = document
        self.assessment = assessment
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Header row with title and quality badge
        header = QHBoxLayout()

        # Title
        title_label = QLabel(self.document.title or "Untitled")
        title_label.setWordWrap(True)
        title_label.setStyleSheet("font-weight: bold;")
        header.addWidget(title_label, stretch=1)

        # Quality badge (if assessment available)
        if self.assessment:
            badge = QualityBadge(self.assessment)
            header.addWidget(badge)

        layout.addLayout(header)

        # ... rest of card UI ...

    def set_assessment(self, assessment: QualityAssessment):
        """Update the quality assessment and refresh badge."""
        self.assessment = assessment
        # Trigger UI update
        self._refresh_badge()
```

---

## Step 4: Integrate with Workflow

### 4.1 Modify systematic review workflow

Update the systematic review workflow to include quality filtering step.

```python
# In src/bmlibrarian/lite/gui/systematic_review_tab.py

from .quality_filter_panel import QualityFilterPanel
from ..quality import QualityManager, QualityFilter

class SystematicReviewTab(QWidget):
    """Main tab for systematic review workflow."""

    def __init__(self, config: LiteConfig, parent=None):
        super().__init__(parent)
        self.config = config
        self.quality_manager = QualityManager(config)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # ... existing search UI ...

        # Add quality filter panel after search input
        self.quality_filter_panel = QualityFilterPanel()
        self.quality_filter_panel.filterChanged.connect(self._on_filter_changed)
        layout.addWidget(self.quality_filter_panel)

        # ... rest of UI ...

    def _on_search_complete(self, documents: list[LiteDocument]):
        """Handle search completion - apply quality filtering."""
        filter_settings = self.quality_filter_panel.get_filter()

        # Show progress
        self._show_progress("Assessing document quality...")

        # Run quality filtering in background
        self.quality_worker = QualityFilterWorker(
            self.quality_manager,
            documents,
            filter_settings
        )
        self.quality_worker.finished.connect(self._on_quality_filter_complete)
        self.quality_worker.progress.connect(self._on_quality_progress)
        self.quality_worker.start()

    def _on_quality_filter_complete(
        self,
        filtered: list[LiteDocument],
        assessments: list[QualityAssessment]
    ):
        """Handle quality filtering completion."""
        # Store assessments for later use
        self.assessments = {
            doc.id: assessment
            for doc, assessment in zip(filtered, assessments)
        }

        # Update document list with filtered results
        self._display_documents(filtered, assessments)

        # Show summary
        summary = self.quality_manager.get_assessment_summary(assessments)
        self._show_quality_summary(summary)

    def _display_documents(
        self,
        documents: list[LiteDocument],
        assessments: list[QualityAssessment]
    ):
        """Display documents with quality badges."""
        # Clear existing cards
        self._clear_document_list()

        for doc, assessment in zip(documents, assessments):
            card = LiteDocumentCard(doc, assessment=assessment)
            self.document_list.addWidget(card)
```

### 4.2 Create background worker for quality filtering

```python
# In src/bmlibrarian/lite/gui/workers.py

from PySide6.QtCore import QThread, Signal

class QualityFilterWorker(QThread):
    """Background worker for quality filtering."""

    progress = Signal(int, int, object)  # current, total, assessment
    finished = Signal(list, list)  # filtered docs, all assessments
    error = Signal(str)

    def __init__(
        self,
        quality_manager: QualityManager,
        documents: list,
        filter_settings: QualityFilter
    ):
        super().__init__()
        self.quality_manager = quality_manager
        self.documents = documents
        self.filter_settings = filter_settings

    def run(self):
        """Run quality filtering in background."""
        try:
            filtered, assessments = self.quality_manager.filter_documents(
                self.documents,
                self.filter_settings,
                progress_callback=self._on_progress
            )
            self.finished.emit(filtered, assessments)
        except Exception as e:
            self.error.emit(str(e))

    def _on_progress(self, current: int, total: int, assessment):
        """Emit progress signal."""
        self.progress.emit(current, total, assessment)
```

---

## Step 5: Add Quality Summary Display

### 5.1 Create quality summary widget

```python
# src/bmlibrarian/lite/gui/quality_summary.py
"""Widget to display quality assessment summary."""

from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtCore import Qt

from ..quality.data_models import QualityTier


class QualitySummaryWidget(QFrame):
    """Displays summary of quality assessments for a document set."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Header
        header = QLabel("Evidence Summary")
        header.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(header)

        # Tier breakdown
        self.tier_layout = QHBoxLayout()
        layout.addLayout(self.tier_layout)

        # Stats line
        self.stats_label = QLabel()
        self.stats_label.setStyleSheet("color: #666;")
        layout.addWidget(self.stats_label)

    def update_summary(self, summary: dict):
        """Update display with new summary data."""
        # Clear tier breakdown
        while self.tier_layout.count():
            item = self.tier_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Add tier counts
        tier_order = [
            (QualityTier.TIER_5_SYNTHESIS, "SR/MA", "#4CAF50"),
            (QualityTier.TIER_4_EXPERIMENTAL, "RCT", "#2196F3"),
            (QualityTier.TIER_3_CONTROLLED, "Controlled", "#FF9800"),
            (QualityTier.TIER_2_OBSERVATIONAL, "Observational", "#9E9E9E"),
            (QualityTier.TIER_1_ANECDOTAL, "Case/Opinion", "#F44336"),
        ]

        by_tier = summary.get("by_quality_tier", {})

        for tier, label, color in tier_order:
            count = by_tier.get(tier.name, 0)
            if count > 0:
                tier_label = QLabel(f"{count} {label}")
                tier_label.setStyleSheet(f"""
                    background-color: {color};
                    color: white;
                    padding: 4px 8px;
                    border-radius: 4px;
                    font-size: 11px;
                """)
                self.tier_layout.addWidget(tier_label)

        self.tier_layout.addStretch()

        # Update stats
        total = summary.get("total", 0)
        avg_conf = summary.get("avg_confidence", 0)
        by_source = summary.get("by_assessment_tier", {})

        stats_parts = [f"{total} documents assessed"]
        if by_source.get("metadata", 0) > 0:
            stats_parts.append(f"{by_source['metadata']} from PubMed")
        if by_source.get("haiku", 0) > 0:
            stats_parts.append(f"{by_source['haiku']} AI-classified")

        self.stats_label.setText(" • ".join(stats_parts))
```

---

## Step 6: Update Settings Dialog

### 6.1 Add quality filtering settings

Add a new section to the settings dialog for quality filtering defaults.

```python
# In src/bmlibrarian/lite/gui/settings_dialog.py

class QualitySettingsTab(QWidget):
    """Settings tab for quality filtering configuration."""

    def __init__(self, config: LiteConfig, parent=None):
        super().__init__(parent)
        self.config = config
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Default filter settings
        defaults_group = QGroupBox("Default Quality Filter")
        defaults_layout = QVBoxLayout(defaults_group)

        # Default minimum tier
        tier_layout = QHBoxLayout()
        tier_layout.addWidget(QLabel("Default minimum tier:"))
        self.default_tier_combo = QComboBox()
        for label, _ in QualityFilterPanel.TIER_OPTIONS:
            self.default_tier_combo.addItem(label)
        tier_layout.addWidget(self.default_tier_combo)
        defaults_layout.addLayout(tier_layout)

        # Default assessment method
        self.default_llm = QCheckBox("Enable AI classification by default")
        self.default_llm.setChecked(True)
        defaults_layout.addWidget(self.default_llm)

        layout.addWidget(defaults_group)

        # Model selection
        models_group = QGroupBox("AI Models")
        models_layout = QVBoxLayout(models_group)

        # Classification model
        class_layout = QHBoxLayout()
        class_layout.addWidget(QLabel("Classification model:"))
        self.class_model_edit = QLineEdit()
        self.class_model_edit.setText("claude-3-haiku-20240307")
        class_layout.addWidget(self.class_model_edit)
        models_layout.addLayout(class_layout)

        # Assessment model
        assess_layout = QHBoxLayout()
        assess_layout.addWidget(QLabel("Detailed assessment model:"))
        self.assess_model_edit = QLineEdit()
        self.assess_model_edit.setText("claude-sonnet-4-20250514")
        assess_layout.addWidget(self.assess_model_edit)
        models_layout.addLayout(assess_layout)

        layout.addWidget(models_group)

        # Display options
        display_group = QGroupBox("Display Options")
        display_layout = QVBoxLayout(display_group)

        self.show_badges = QCheckBox("Show quality badges on document cards")
        self.show_badges.setChecked(True)
        display_layout.addWidget(self.show_badges)

        self.include_in_reports = QCheckBox("Include quality info in reports")
        self.include_in_reports.setChecked(True)
        display_layout.addWidget(self.include_in_reports)

        layout.addWidget(display_group)
        layout.addStretch()

    def get_settings(self) -> dict:
        """Get current settings as dict."""
        tier_idx = self.default_tier_combo.currentIndex()
        return {
            "quality_filtering": {
                "default_minimum_tier": tier_idx,
                "use_llm_classification": self.default_llm.isChecked(),
                "classification_model": self.class_model_edit.text(),
                "assessment_model": self.assess_model_edit.text(),
                "show_quality_badges": self.show_badges.isChecked(),
                "include_quality_in_reports": self.include_in_reports.isChecked(),
            }
        }
```

---

## Verification Checklist

After implementing Phase 3, verify:

- [ ] QualityFilterPanel displays and collapses correctly
- [ ] Filter changes emit filterChanged signal
- [ ] QualityBadge displays correct colors for each tier
- [ ] Badges show correct tooltips with assessment details
- [ ] Document cards display quality badges
- [ ] Workflow integrates quality filtering step
- [ ] Quality summary displays tier breakdown
- [ ] Settings dialog includes quality options
- [ ] Background worker handles filtering without blocking UI

---

## Next Steps

After Phase 3 is complete, proceed to **Phase 4: Report Enhancement** which implements:
- Quality information in generated reports
- Evidence summary section
- Study characteristics in citations
