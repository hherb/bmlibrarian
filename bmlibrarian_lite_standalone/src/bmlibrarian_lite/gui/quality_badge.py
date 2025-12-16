"""
Quality badge widget for document cards.

Displays a color-coded badge indicating study design quality tier.
Provides tooltip with detailed assessment information.
"""

from typing import Optional, Dict, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QFrame, QHBoxLayout, QWidget
from PySide6.QtGui import QFont

from bmlibrarian_lite.resources.styles.dpi_scale import scaled

from ..quality.data_models import QualityTier, StudyDesign, QualityAssessment


# Color scheme for quality tiers: (background_color, text_color)
TIER_COLORS: Dict[QualityTier, Tuple[str, str]] = {
    QualityTier.TIER_5_SYNTHESIS: ("#4CAF50", "#FFFFFF"),      # Green
    QualityTier.TIER_4_EXPERIMENTAL: ("#2196F3", "#FFFFFF"),   # Blue
    QualityTier.TIER_3_CONTROLLED: ("#FF9800", "#FFFFFF"),     # Orange
    QualityTier.TIER_2_OBSERVATIONAL: ("#9E9E9E", "#FFFFFF"),  # Gray
    QualityTier.TIER_1_ANECDOTAL: ("#F44336", "#FFFFFF"),      # Red
    QualityTier.UNCLASSIFIED: ("#BDBDBD", "#666666"),          # Light gray
}

# Short labels for badges based on tier
TIER_BADGE_LABELS: Dict[QualityTier, str] = {
    QualityTier.TIER_5_SYNTHESIS: "SR/MA",
    QualityTier.TIER_4_EXPERIMENTAL: "RCT",
    QualityTier.TIER_3_CONTROLLED: "Controlled",
    QualityTier.TIER_2_OBSERVATIONAL: "Observational",
    QualityTier.TIER_1_ANECDOTAL: "Case/Opinion",
    QualityTier.UNCLASSIFIED: "?",
}

# More specific labels based on study design
DESIGN_BADGE_LABELS: Dict[StudyDesign, str] = {
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

# Badge styling constants
BADGE_PADDING_H = 6
BADGE_PADDING_V = 2
BADGE_BORDER_RADIUS = 3
BADGE_FONT_SIZE = 9

# Small badge constants
SMALL_BADGE_SIZE = 18
SMALL_BADGE_FONT_SIZE = 10


class QualityBadge(QFrame):
    """
    Color-coded badge showing document quality tier.

    Can display either tier label (SR/MA, RCT, etc.) or
    more specific study design label based on configuration.

    Attributes:
        assessment: The quality assessment for this badge
        show_design: Whether to show specific design instead of tier
    """

    def __init__(
        self,
        assessment: QualityAssessment,
        show_design: bool = True,
        parent: Optional[QWidget] = None,
    ) -> None:
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

    def _setup_ui(self) -> None:
        """Set up the badge UI with appropriate colors and label."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            scaled(BADGE_PADDING_H),
            scaled(BADGE_PADDING_V),
            scaled(BADGE_PADDING_H),
            scaled(BADGE_PADDING_V),
        )
        layout.setSpacing(scaled(4))

        # Get colors for tier
        tier = self.assessment.quality_tier
        bg_color, text_color = TIER_COLORS.get(
            tier,
            TIER_COLORS[QualityTier.UNCLASSIFIED]
        )

        # Get label text
        if self.show_design:
            label_text = DESIGN_BADGE_LABELS.get(
                self.assessment.study_design,
                "?"
            )
        else:
            label_text = TIER_BADGE_LABELS.get(tier, "?")

        # Create label
        self.label = QLabel(label_text)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Style the badge
        font = QFont()
        font.setPointSize(scaled(BADGE_FONT_SIZE))
        font.setBold(True)
        self.label.setFont(font)

        # Apply styling
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_color};
                border-radius: {scaled(BADGE_BORDER_RADIUS)}px;
            }}
        """)
        self.label.setStyleSheet(f"""
            QLabel {{
                color: {text_color};
                padding: 0px;
            }}
        """)

        layout.addWidget(self.label)

        # Set tooltip with details
        self._set_tooltip()

    def _set_tooltip(self) -> None:
        """Set informative tooltip with assessment details."""
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

    def update_assessment(self, assessment: QualityAssessment) -> None:
        """
        Update the badge with a new assessment.

        Args:
            assessment: New quality assessment
        """
        self.assessment = assessment
        # Clear layout and recreate
        while self.layout().count():
            item = self.layout().takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._setup_ui()


class QualityBadgeSmall(QLabel):
    """
    Minimal quality badge for tight spaces.

    Shows only a colored circle with tier number.

    Attributes:
        tier: The quality tier displayed
    """

    def __init__(
        self,
        tier: QualityTier,
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Initialize minimal badge.

        Args:
            tier: Quality tier to display
            parent: Parent widget
        """
        super().__init__(parent)
        self.tier = tier
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the small badge UI."""
        bg_color, _ = TIER_COLORS.get(
            self.tier,
            TIER_COLORS[QualityTier.UNCLASSIFIED]
        )

        # Show tier number or ? for unclassified
        tier_num = self.tier.value if self.tier != QualityTier.UNCLASSIFIED else "?"
        self.setText(str(tier_num))

        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(scaled(SMALL_BADGE_SIZE), scaled(SMALL_BADGE_SIZE))

        border_radius = scaled(SMALL_BADGE_SIZE) // 2
        font_size = scaled(SMALL_BADGE_FONT_SIZE)

        self.setStyleSheet(f"""
            QLabel {{
                background-color: {bg_color};
                color: white;
                border-radius: {border_radius}px;
                font-size: {font_size}px;
                font-weight: bold;
            }}
        """)

        self.setToolTip(TIER_BADGE_LABELS.get(self.tier, "Unknown"))

    def set_tier(self, tier: QualityTier) -> None:
        """
        Update the badge tier.

        Args:
            tier: New quality tier
        """
        self.tier = tier
        self._setup_ui()
