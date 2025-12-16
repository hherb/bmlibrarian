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
)

from bmlibrarian.gui.qt.resources.styles.dpi_scale import scaled

from ..quality.data_models import QualityTier, QualityFilter

logger = logging.getLogger(__name__)


# Tier dropdown options with labels and values
TIER_OPTIONS: List[Tuple[str, QualityTier]] = [
    ("No filter (include all)", QualityTier.UNCLASSIFIED),
    ("Primary research (exclude opinions)", QualityTier.TIER_2_OBSERVATIONAL),
    ("Controlled studies (cohort+)", QualityTier.TIER_3_CONTROLLED),
    ("High-quality evidence (RCT+)", QualityTier.TIER_4_EXPERIMENTAL),
    ("Systematic evidence only (SR/MA)", QualityTier.TIER_5_SYNTHESIS),
]

# Default minimum sample size for filtering
DEFAULT_MINIMUM_SAMPLE_SIZE = 100

# Minimum and maximum sample size range
SAMPLE_SIZE_MIN = 1
SAMPLE_SIZE_MAX = 100000


class QualityFilterPanel(QFrame):
    """
    Collapsible panel for configuring quality filters.

    Provides a user interface for setting quality filtering criteria
    including minimum quality tier, randomization/blinding requirements,
    sample size thresholds, and assessment depth.

    Signals:
        filterChanged: Emitted when filter settings change with new QualityFilter

    Attributes:
        _collapsed: Whether the panel is collapsed
    """

    # Emitted when filter settings change
    filterChanged = Signal(object)  # QualityFilter

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

        # Collapsible content
        self.content = QFrame()
        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(0, scaled(8), 0, 0)
        content_layout.setSpacing(scaled(12))

        # === Minimum Quality Tier ===
        tier_group = QGroupBox("Minimum Study Quality")
        tier_layout = QVBoxLayout(tier_group)

        self.tier_combo = QComboBox()
        for label, _ in TIER_OPTIONS:
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
        self.sample_size_spin.setRange(SAMPLE_SIZE_MIN, SAMPLE_SIZE_MAX)
        self.sample_size_spin.setValue(DEFAULT_MINIMUM_SAMPLE_SIZE)
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

    def _connect_signals(self) -> None:
        """Connect widget signals to handlers."""
        self.toggle_btn.toggled.connect(self._toggle_content)
        self.tier_combo.currentIndexChanged.connect(self._on_filter_changed)
        self.require_randomization.toggled.connect(self._on_filter_changed)
        self.require_blinding.toggled.connect(self._on_filter_changed)
        self.require_sample_size.toggled.connect(self._on_sample_size_toggled)
        self.sample_size_spin.valueChanged.connect(self._on_filter_changed)
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
        self._on_filter_changed()

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
        for i, (_, tier) in enumerate(TIER_OPTIONS):
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
