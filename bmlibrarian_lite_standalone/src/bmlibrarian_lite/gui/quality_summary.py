"""
Widget to display quality assessment summary.

Provides an overview of quality assessment results for a document set,
including tier distribution, study design counts, and assessment sources.
"""

import logging
from typing import Optional, Dict, List, Tuple

from PySide6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QWidget,
)
from PySide6.QtCore import Qt

from bmlibrarian_lite.resources.styles.dpi_scale import scaled

from ..quality.data_models import QualityTier

logger = logging.getLogger(__name__)


# Tier display configuration: (tier, label, color)
TIER_DISPLAY_CONFIG: List[Tuple[QualityTier, str, str]] = [
    (QualityTier.TIER_5_SYNTHESIS, "SR/MA", "#4CAF50"),
    (QualityTier.TIER_4_EXPERIMENTAL, "RCT", "#2196F3"),
    (QualityTier.TIER_3_CONTROLLED, "Controlled", "#FF9800"),
    (QualityTier.TIER_2_OBSERVATIONAL, "Observational", "#9E9E9E"),
    (QualityTier.TIER_1_ANECDOTAL, "Case/Opinion", "#F44336"),
]

# Styling constants
HEADER_FONT_SIZE = 14
TIER_BADGE_PADDING_H = 8
TIER_BADGE_PADDING_V = 4
TIER_BADGE_BORDER_RADIUS = 4
TIER_BADGE_FONT_SIZE = 11
STATS_COLOR = "#666666"


class QualitySummaryWidget(QFrame):
    """
    Displays summary of quality assessments for a document set.

    Shows:
    - Tier distribution with color-coded badges
    - Total documents assessed
    - Assessment source breakdown (metadata vs AI)
    - Average confidence level

    Attributes:
        tier_layout: Layout containing tier count badges
        stats_label: Label showing summary statistics
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize the quality summary widget.

        Args:
            parent: Optional parent widget
        """
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the summary widget UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(scaled(8), scaled(8), scaled(8), scaled(8))
        layout.setSpacing(scaled(8))

        # Header
        header = QLabel("Evidence Summary")
        font = header.font()
        font.setBold(True)
        font.setPointSize(scaled(HEADER_FONT_SIZE))
        header.setFont(font)
        layout.addWidget(header)

        # Tier breakdown
        self.tier_layout = QHBoxLayout()
        self.tier_layout.setSpacing(scaled(8))
        layout.addLayout(self.tier_layout)

        # Stats line
        self.stats_label = QLabel()
        self.stats_label.setStyleSheet(f"color: {STATS_COLOR};")
        layout.addWidget(self.stats_label)

        # Initialize with empty state
        self._show_empty_state()

    def _show_empty_state(self) -> None:
        """Show empty state when no assessments are available."""
        self._clear_tier_layout()
        placeholder = QLabel("No documents assessed")
        placeholder.setStyleSheet(f"color: {STATS_COLOR}; font-style: italic;")
        self.tier_layout.addWidget(placeholder)
        self.tier_layout.addStretch()
        self.stats_label.setText("")

    def _clear_tier_layout(self) -> None:
        """Clear all widgets from the tier layout."""
        while self.tier_layout.count():
            item = self.tier_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def update_summary(self, summary: Dict) -> None:
        """
        Update display with new summary data.

        Args:
            summary: Dictionary containing summary statistics with keys:
                - total: Total number of assessments
                - by_quality_tier: Dict mapping tier names to counts
                - by_assessment_tier: Dict with metadata/haiku/sonnet counts
                - avg_confidence: Average confidence value (0-1)
        """
        self._clear_tier_layout()

        total = summary.get("total", 0)
        if total == 0:
            self._show_empty_state()
            return

        # Add tier counts as badges
        by_tier = summary.get("by_quality_tier", {})

        for tier, label, color in TIER_DISPLAY_CONFIG:
            count = by_tier.get(tier.name, 0)
            if count > 0:
                tier_badge = self._create_tier_badge(count, label, color)
                self.tier_layout.addWidget(tier_badge)

        self.tier_layout.addStretch()

        # Update stats
        avg_conf = summary.get("avg_confidence", 0)
        by_source = summary.get("by_assessment_tier", {})

        stats_parts = [f"{total} documents assessed"]

        metadata_count = by_source.get("metadata", 0)
        if metadata_count > 0:
            stats_parts.append(f"{metadata_count} from PubMed")

        haiku_count = by_source.get("haiku", 0)
        if haiku_count > 0:
            stats_parts.append(f"{haiku_count} AI-classified")

        sonnet_count = by_source.get("sonnet", 0)
        if sonnet_count > 0:
            stats_parts.append(f"{sonnet_count} detailed")

        if avg_conf > 0:
            stats_parts.append(f"Avg confidence: {avg_conf:.0%}")

        self.stats_label.setText(" • ".join(stats_parts))

    def _create_tier_badge(self, count: int, label: str, color: str) -> QLabel:
        """
        Create a styled tier count badge.

        Args:
            count: Number of documents in this tier
            label: Display label for the tier
            color: Background color for the badge

        Returns:
            Styled QLabel badge
        """
        badge = QLabel(f"{count} {label}")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

        padding_h = scaled(TIER_BADGE_PADDING_H)
        padding_v = scaled(TIER_BADGE_PADDING_V)
        border_radius = scaled(TIER_BADGE_BORDER_RADIUS)
        font_size = scaled(TIER_BADGE_FONT_SIZE)

        badge.setStyleSheet(f"""
            QLabel {{
                background-color: {color};
                color: white;
                padding: {padding_v}px {padding_h}px;
                border-radius: {border_radius}px;
                font-size: {font_size}px;
            }}
        """)

        return badge

    def clear(self) -> None:
        """Clear the summary and show empty state."""
        self._show_empty_state()


class QualityFilterSummary(QFrame):
    """
    Compact summary showing filtered vs total documents.

    Displays a simple "X of Y documents passed quality filter" message
    with tier breakdown on hover.

    Attributes:
        passed_count: Number of documents that passed the filter
        total_count: Total number of documents assessed
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize the filter summary widget.

        Args:
            parent: Optional parent widget
        """
        super().__init__(parent)
        self.passed_count = 0
        self.total_count = 0
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the compact summary UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(scaled(8), scaled(4), scaled(8), scaled(4))
        layout.setSpacing(scaled(8))

        self.summary_label = QLabel("No documents filtered")
        layout.addWidget(self.summary_label)
        layout.addStretch()

    def update_counts(
        self,
        passed: int,
        total: int,
        tier_breakdown: Optional[Dict[str, int]] = None,
    ) -> None:
        """
        Update the summary with filter results.

        Args:
            passed: Number of documents that passed the filter
            total: Total number of documents assessed
            tier_breakdown: Optional dict mapping tier names to counts
        """
        self.passed_count = passed
        self.total_count = total

        if total == 0:
            self.summary_label.setText("No documents to filter")
            self.setToolTip("")
            return

        percent = (passed / total) * 100 if total > 0 else 0
        self.summary_label.setText(
            f"{passed} of {total} documents passed quality filter ({percent:.0f}%)"
        )

        # Build tooltip with tier breakdown
        if tier_breakdown:
            tooltip_lines = ["Quality Tier Breakdown:"]
            for tier, label, _ in TIER_DISPLAY_CONFIG:
                count = tier_breakdown.get(tier.name, 0)
                if count > 0:
                    tooltip_lines.append(f"  {label}: {count}")
            self.setToolTip("\n".join(tooltip_lines))

    def clear(self) -> None:
        """Reset the summary to empty state."""
        self.passed_count = 0
        self.total_count = 0
        self.summary_label.setText("No documents filtered")
        self.setToolTip("")
