"""
Collapsible quality filter panel for systematic review workflow.

Allows users to configure quality filtering criteria before
or during document search. Provides tiered assessment options:
- Tier 1: Metadata-only (free, instant)
- Tier 2: LLM classification (Claude Haiku)
- Tier 3: Detailed assessment (Claude Sonnet)
"""

import logging
from typing import Optional, List, Tuple

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
    QWidget,
    QProgressBar,
)
from PySide6.QtGui import QPalette

from bmlibrarian_lite.resources.styles.dpi_scale import scaled

from ..quality.data_models import QualityTier, QualityFilter

logger = logging.getLogger(__name__)


# Tier dropdown options with labels, values, and tooltips
TIER_OPTIONS: List[Tuple[str, QualityTier, str]] = [
    (
        "No filter (include all)",
        QualityTier.UNCLASSIFIED,
        "Include all document types regardless of study design.\n"
        "Best for exploratory searches or when completeness is priority."
    ),
    (
        "Primary research (exclude opinions)",
        QualityTier.TIER_2_OBSERVATIONAL,
        "Exclude editorials, letters, comments, and case reports.\n"
        "Includes: cross-sectional studies and above.\n"
        "Use when you want empirical data only."
    ),
    (
        "Controlled studies (cohort+)",
        QualityTier.TIER_3_CONTROLLED,
        "Include only studies with comparison groups.\n"
        "Includes: cohort, case-control, RCT, and systematic reviews.\n"
        "Recommended for clinical effectiveness questions."
    ),
    (
        "High-quality evidence (RCT+)",
        QualityTier.TIER_4_EXPERIMENTAL,
        "Include only randomized trials and systematic reviews.\n"
        "Strongest evidence for interventional questions.\n"
        "May miss important observational evidence."
    ),
    (
        "Systematic evidence only (SR/MA)",
        QualityTier.TIER_5_SYNTHESIS,
        "Include only systematic reviews and meta-analyses.\n"
        "Pre-synthesized evidence from expert reviewers.\n"
        "Note: May return very few or no results."
    ),
]

# Default minimum sample size for filtering
DEFAULT_MINIMUM_SAMPLE_SIZE = 100

# Minimum and maximum sample size range
SAMPLE_SIZE_MIN = 1
SAMPLE_SIZE_MAX = 100000

# Sample size warning thresholds
SAMPLE_SIZE_LOW_WARNING = 30  # Studies < 30 subjects may be underpowered
SAMPLE_SIZE_VERY_HIGH = 10000  # Unusually large, might be unrealistic


class QualityFilterPanel(QFrame):
    """
    Collapsible panel for configuring quality filters.

    Provides a user interface for setting quality filtering criteria
    including minimum quality tier, randomization/blinding requirements,
    sample size thresholds, and assessment depth.

    Signals:
        filterChanged: Emitted when filter settings change with new QualityFilter
        classificationStarted: Emitted when LLM classification begins
        classificationProgress: Emitted with (current, total) during classification
        classificationFinished: Emitted when LLM classification completes

    Attributes:
        _collapsed: Whether the panel is collapsed
    """

    # Emitted when filter settings change
    filterChanged = Signal(object)  # QualityFilter

    # Signals for LLM classification progress indication
    classificationStarted = Signal()
    classificationProgress = Signal(int, int)  # (current, total)
    classificationFinished = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize the quality filter panel.

        Args:
            parent: Optional parent widget
        """
        super().__init__(parent)
        self._collapsed = True
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Set up the panel UI with all filter controls."""
        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(scaled(8), scaled(8), scaled(8), scaled(8))
        layout.setSpacing(scaled(8))

        # Header with toggle button
        header = QHBoxLayout()
        self.toggle_btn = QPushButton("▶ Quality Filters")
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.setFlat(True)
        header.addWidget(self.toggle_btn)
        header.addStretch()

        # Status label showing current filter summary
        self.status_label = QLabel("All studies")
        header.addWidget(self.status_label)

        layout.addLayout(header)

        # Progress bar for LLM classification (hidden by default)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("Classifying: %v/%m documents")
        layout.addWidget(self.progress_bar)

        # Collapsible content
        self.content = QFrame()
        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(0, scaled(8), 0, 0)
        content_layout.setSpacing(scaled(12))

        # === Minimum Quality Tier ===
        tier_group = QGroupBox("Minimum Study Quality")
        tier_layout = QVBoxLayout(tier_group)

        self.tier_combo = QComboBox()
        for label, _, _ in TIER_OPTIONS:
            self.tier_combo.addItem(label)

        # Set initial tooltip based on first option
        self._update_tier_tooltip(0)

        tier_layout.addWidget(self.tier_combo)

        # Tier description label (shows contextual help for selected tier)
        self.tier_description = QLabel()
        self.tier_description.setWordWrap(True)
        self.tier_description.setStyleSheet("color: gray; font-size: small;")
        self._update_tier_description(0)
        tier_layout.addWidget(self.tier_description)

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
        self.require_sample_size.setToolTip(
            "Filter out studies with fewer participants than specified.\n"
            "Smaller studies may lack statistical power to detect effects."
        )
        sample_layout.addWidget(self.require_sample_size)

        self.sample_size_spin = QSpinBox()
        self.sample_size_spin.setRange(SAMPLE_SIZE_MIN, SAMPLE_SIZE_MAX)
        self.sample_size_spin.setValue(DEFAULT_MINIMUM_SAMPLE_SIZE)
        self.sample_size_spin.setEnabled(False)
        self.sample_size_spin.setToolTip(
            f"Typical values:\n"
            f"• {SAMPLE_SIZE_LOW_WARNING}+ for pilot studies\n"
            f"• 100+ for most research questions\n"
            f"• 1000+ for rare event detection"
        )
        sample_layout.addWidget(self.sample_size_spin)
        sample_layout.addStretch()

        req_layout.addLayout(sample_layout)

        # Sample size validation feedback label
        self.sample_size_warning = QLabel()
        self.sample_size_warning.setWordWrap(True)
        self.sample_size_warning.setStyleSheet("color: #B8860B; font-size: small;")  # Dark goldenrod
        self.sample_size_warning.setVisible(False)
        req_layout.addWidget(self.sample_size_warning)

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

    def _connect_signals(self) -> None:
        """Connect widget signals to handlers."""
        self.toggle_btn.toggled.connect(self._toggle_content)
        self.tier_combo.currentIndexChanged.connect(self._on_tier_changed)
        self.require_randomization.toggled.connect(self._on_filter_changed)
        self.require_blinding.toggled.connect(self._on_filter_changed)
        self.require_sample_size.toggled.connect(self._on_sample_size_toggled)
        self.sample_size_spin.valueChanged.connect(self._on_sample_size_value_changed)
        self.metadata_only.toggled.connect(self._on_metadata_only_toggled)
        self.use_llm.toggled.connect(self._on_filter_changed)
        self.detailed_assessment.toggled.connect(self._on_filter_changed)

    def _toggle_content(self, checked: bool) -> None:
        """
        Toggle content visibility.

        Args:
            checked: Whether toggle button is checked
        """
        self._collapsed = not checked
        self.content.setVisible(checked)
        self.toggle_btn.setText(
            "▼ Quality Filters" if checked else "▶ Quality Filters"
        )

    def _on_filter_changed(self) -> None:
        """Handle filter setting changes and emit signal."""
        filter_settings = self.get_filter()
        self._update_status_label(filter_settings)
        self.filterChanged.emit(filter_settings)

    def _on_sample_size_toggled(self, checked: bool) -> None:
        """
        Handle sample size checkbox toggle.

        Args:
            checked: Whether checkbox is checked
        """
        self.sample_size_spin.setEnabled(checked)
        self._validate_sample_size()
        self._on_filter_changed()

    def _on_sample_size_value_changed(self, value: int) -> None:
        """
        Handle sample size value change with validation feedback.

        Args:
            value: New sample size value
        """
        self._validate_sample_size()
        self._on_filter_changed()

    def _on_tier_changed(self, index: int) -> None:
        """
        Handle tier selection change.

        Args:
            index: Selected tier index
        """
        self._update_tier_tooltip(index)
        self._update_tier_description(index)
        self._on_filter_changed()

    def _update_tier_tooltip(self, index: int) -> None:
        """
        Update combo box tooltip based on selected tier.

        Args:
            index: Selected tier index
        """
        if 0 <= index < len(TIER_OPTIONS):
            _, _, tooltip = TIER_OPTIONS[index]
            self.tier_combo.setToolTip(tooltip)

    def _update_tier_description(self, index: int) -> None:
        """
        Update tier description label based on selected tier.

        Args:
            index: Selected tier index
        """
        if 0 <= index < len(TIER_OPTIONS):
            _, _, tooltip = TIER_OPTIONS[index]
            # Show abbreviated description
            first_line = tooltip.split("\n")[0]
            self.tier_description.setText(first_line)

    def _validate_sample_size(self) -> None:
        """Validate sample size and show appropriate feedback."""
        if not self.require_sample_size.isChecked():
            self.sample_size_warning.setVisible(False)
            return

        value = self.sample_size_spin.value()

        if value < SAMPLE_SIZE_LOW_WARNING:
            self.sample_size_warning.setText(
                f"⚠ Studies with n<{SAMPLE_SIZE_LOW_WARNING} may be underpowered "
                "for detecting meaningful effects."
            )
            self.sample_size_warning.setStyleSheet(
                "color: #B8860B; font-size: small;"  # Dark goldenrod (warning)
            )
            self.sample_size_warning.setVisible(True)
        elif value > SAMPLE_SIZE_VERY_HIGH:
            self.sample_size_warning.setText(
                f"ℹ Very high threshold (n≥{value:,}) may exclude most studies. "
                "This is appropriate for common conditions but may miss rare disease research."
            )
            self.sample_size_warning.setStyleSheet(
                "color: #4682B4; font-size: small;"  # Steel blue (info)
            )
            self.sample_size_warning.setVisible(True)
        else:
            self.sample_size_warning.setVisible(False)

    def _on_metadata_only_toggled(self, checked: bool) -> None:
        """
        Handle metadata-only toggle.

        When metadata-only is enabled, disable LLM options.

        Args:
            checked: Whether metadata-only is checked
        """
        if checked:
            self.use_llm.setChecked(False)
            self.use_llm.setEnabled(False)
            self.detailed_assessment.setChecked(False)
            self.detailed_assessment.setEnabled(False)
        else:
            self.use_llm.setEnabled(True)
            self.detailed_assessment.setEnabled(True)
        self._on_filter_changed()

    def _update_status_label(self, filter_settings: QualityFilter) -> None:
        """
        Update status label with current filter summary.

        Args:
            filter_settings: Current filter settings
        """
        tier_idx = self.tier_combo.currentIndex()
        tier_label = TIER_OPTIONS[tier_idx][0]

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
            QualityFilter with current UI settings
        """
        tier_idx = self.tier_combo.currentIndex()
        minimum_tier = TIER_OPTIONS[tier_idx][1]

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

    def set_filter(self, filter_settings: QualityFilter) -> None:
        """
        Set filter settings from QualityFilter object.

        Args:
            filter_settings: Settings to apply to UI
        """
        # Find matching tier index
        for i, (_, tier, _) in enumerate(TIER_OPTIONS):
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

        # Update validation feedback
        self._validate_sample_size()

    def expand(self) -> None:
        """Expand the panel to show content."""
        self.toggle_btn.setChecked(True)

    def collapse(self) -> None:
        """Collapse the panel to hide content."""
        self.toggle_btn.setChecked(False)

    def is_collapsed(self) -> bool:
        """
        Check if panel is collapsed.

        Returns:
            True if panel is collapsed
        """
        return self._collapsed

    # === Progress Bar Control Methods ===

    def start_classification_progress(self, total: int) -> None:
        """
        Start showing classification progress.

        Call this when beginning LLM classification of documents.

        Args:
            total: Total number of documents to classify
        """
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.classificationStarted.emit()

    def update_classification_progress(self, current: int, total: int) -> None:
        """
        Update classification progress.

        Call this during LLM classification to update the progress bar.

        Args:
            current: Number of documents classified so far
            total: Total number of documents
        """
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.classificationProgress.emit(current, total)

    def finish_classification_progress(self) -> None:
        """
        Hide classification progress.

        Call this when LLM classification is complete.
        """
        self.progress_bar.setVisible(False)
        self.classificationFinished.emit()
