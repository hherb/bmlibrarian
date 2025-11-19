"""
Centralized styling configuration for Fact Checker Review GUI.

Provides DPI-aware sizing, color schemes, and consistent styling across components.
All sizes are defined relative to base font size for proper scaling.
"""

import flet as ft
from typing import Dict, Any


class DPIScale:
    """DPI-aware scaling configuration."""

    # Base font size in pt (typical default is 12pt)
    BASE_FONT_SIZE = 12

    # Relative size multipliers
    FONT_SIZE_TINY = 0.75      # 9pt
    FONT_SIZE_SMALL = 0.92     # 11pt
    FONT_SIZE_NORMAL = 1.0     # 12pt
    FONT_SIZE_MEDIUM = 1.17    # 14pt
    FONT_SIZE_LARGE = 1.33     # 16pt
    FONT_SIZE_XLARGE = 2.0     # 24pt
    FONT_SIZE_XXLARGE = 2.33   # 28pt

    # Spacing units (relative to base font size)
    SPACE_UNIT = BASE_FONT_SIZE  # 1 unit = 12pt
    SPACE_TINY = 0.42 * SPACE_UNIT    # ~5pt
    SPACE_SMALL = 0.83 * SPACE_UNIT   # ~10pt
    SPACE_MEDIUM = 1.25 * SPACE_UNIT  # ~15pt
    SPACE_LARGE = 1.67 * SPACE_UNIT   # ~20pt

    # Container sizes (in rem/em units relative to base)
    CONTAINER_PADDING_SMALL = 0.83    # ~10pt
    CONTAINER_PADDING_MEDIUM = 1.25   # ~15pt
    CONTAINER_PADDING_LARGE = 1.67    # ~20pt

    # Specific component heights (in em units)
    CITATION_CONTAINER_HEIGHT = 25.0  # 25em (~300pt at 12pt base)
    PROGRESS_BAR_WIDTH = 33.33        # ~400pt at 12pt base
    TIMER_WIDTH = 15.0                # ~180pt at 12pt base

    @classmethod
    def to_pt(cls, em_value: float) -> float:
        """Convert em units to points."""
        return em_value * cls.BASE_FONT_SIZE

    @classmethod
    def font_size(cls, multiplier: float) -> float:
        """Get font size in points."""
        return multiplier * cls.BASE_FONT_SIZE


class Colors:
    """Color scheme for Fact Checker Review GUI."""

    # Primary colors
    PRIMARY_BLUE = ft.Colors.BLUE_900
    PRIMARY_BLUE_LIGHT = ft.Colors.BLUE_700
    PRIMARY_BLUE_PALE = ft.Colors.BLUE_50

    # Accent colors
    ACCENT_ORANGE = ft.Colors.ORANGE_700
    ACCENT_ORANGE_LIGHT = ft.Colors.ORANGE_50
    ACCENT_ORANGE_BORDER = ft.Colors.ORANGE_200

    ACCENT_GREEN = ft.Colors.GREEN_700
    ACCENT_GREEN_LIGHT = ft.Colors.GREEN_50
    ACCENT_GREEN_BORDER = ft.Colors.GREEN_300

    # Semantic colors
    SUCCESS = ft.Colors.GREEN_700
    SUCCESS_BG = ft.Colors.GREEN_50
    WARNING = ft.Colors.ORANGE_700
    WARNING_BG = ft.Colors.ORANGE_50
    ERROR = ft.Colors.RED_700
    ERROR_BG = ft.Colors.RED_50

    # Neutral colors
    GREY_DARK = ft.Colors.GREY_900
    GREY_MEDIUM = ft.Colors.GREY_700
    GREY_LIGHT = ft.Colors.GREY_600
    GREY_PALE = ft.Colors.GREY_500
    GREY_BG = ft.Colors.GREY_50
    GREY_BORDER = ft.Colors.GREY_300
    GREY_BORDER_LIGHT = ft.Colors.GREY_400

    # Annotation colors
    ANNOTATION_PURPLE = ft.Colors.PURPLE_700
    ANNOTATION_PURPLE_BG = ft.Colors.PURPLE_100
    ANNOTATION_BLUE = ft.Colors.BLUE_700
    ANNOTATION_BLUE_BG = ft.Colors.BLUE_100

    # Evaluation colors
    EVAL_YES = ft.Colors.GREEN_700
    EVAL_NO = ft.Colors.RED_700
    EVAL_MAYBE = ft.Colors.ORANGE_700
    EVAL_NA = ft.Colors.GREY_600

    # Base colors
    WHITE = ft.Colors.WHITE
    BLACK = ft.Colors.BLACK
    TRANSPARENT = ft.Colors.TRANSPARENT


class ButtonStyles:
    """Button styling configurations."""

    @staticmethod
    def primary_button() -> Dict[str, Any]:
        """Primary action button style."""
        return {
            'bgcolor': Colors.PRIMARY_BLUE_LIGHT,
            'color': Colors.WHITE
        }

    @staticmethod
    def toggle_button() -> Dict[str, Any]:
        """Toggle button style (hide/show)."""
        return {
            'bgcolor': Colors.ACCENT_ORANGE,
            'color': Colors.WHITE
        }

    @staticmethod
    def secondary_button() -> Dict[str, Any]:
        """Secondary action button style."""
        return {
            'bgcolor': Colors.GREY_MEDIUM,
            'color': Colors.WHITE
        }


class ContainerStyles:
    """Container styling configurations."""

    @staticmethod
    def card_container() -> Dict[str, Any]:
        """Standard card container style."""
        return {
            'padding': ft.padding.all(DPIScale.to_pt(DPIScale.CONTAINER_PADDING_LARGE)),
            'bgcolor': Colors.WHITE,
            'border_radius': DPIScale.to_pt(DPIScale.CONTAINER_PADDING_SMALL),
            'border': ft.border.all(1, Colors.GREY_BORDER)
        }

    @staticmethod
    def section_container(bg_color: str, border_color: str) -> Dict[str, Any]:
        """Section container with custom colors."""
        return {
            'padding': ft.padding.all(DPIScale.to_pt(DPIScale.CONTAINER_PADDING_MEDIUM)),
            'bgcolor': bg_color,
            'border_radius': DPIScale.to_pt(DPIScale.CONTAINER_PADDING_SMALL * 0.8),
            'border': ft.border.all(1, border_color)
        }

    @staticmethod
    def statement_container() -> Dict[str, Any]:
        """Statement display container style."""
        return {
            'padding': ft.padding.all(DPIScale.to_pt(DPIScale.CONTAINER_PADDING_MEDIUM)),
            'bgcolor': Colors.GREY_BG,
            'border_radius': DPIScale.to_pt(DPIScale.CONTAINER_PADDING_SMALL * 0.8),
            'border': ft.border.all(1, Colors.GREY_BORDER)
        }

    @staticmethod
    def citation_container() -> Dict[str, Any]:
        """Citation list container with fixed height."""
        return {
            'height': DPIScale.to_pt(DPIScale.CITATION_CONTAINER_HEIGHT),
            'bgcolor': Colors.GREY_BG,
            'border_radius': DPIScale.to_pt(DPIScale.CONTAINER_PADDING_SMALL * 0.8),
            'padding': ft.padding.all(DPIScale.to_pt(DPIScale.CONTAINER_PADDING_SMALL))
        }

    @staticmethod
    def annotation_section(bg_color: str, border_color: str, border_width: int = 1) -> Dict[str, Any]:
        """Annotation section container."""
        return {
            'padding': ft.padding.all(DPIScale.to_pt(DPIScale.CONTAINER_PADDING_MEDIUM)),
            'bgcolor': bg_color,
            'border_radius': DPIScale.to_pt(DPIScale.CONTAINER_PADDING_SMALL * 0.8),
            'border': ft.border.all(border_width, border_color)
        }

    @staticmethod
    def timer_container() -> Dict[str, Any]:
        """Timer component container."""
        return {
            'padding': ft.padding.all(DPIScale.to_pt(DPIScale.CONTAINER_PADDING_SMALL)),
            'bgcolor': Colors.PRIMARY_BLUE_PALE,
            'border_radius': DPIScale.to_pt(DPIScale.CONTAINER_PADDING_SMALL * 0.8),
            'border': ft.border.all(1, ft.Colors.BLUE_200),
            'width': DPIScale.to_pt(DPIScale.TIMER_WIDTH)
        }


class TextStyles:
    """Text styling configurations."""

    @staticmethod
    def title_large() -> Dict[str, Any]:
        """Large title text style."""
        return {
            'size': DPIScale.font_size(DPIScale.FONT_SIZE_XXLARGE),
            'weight': ft.FontWeight.BOLD,
            'color': Colors.PRIMARY_BLUE
        }

    @staticmethod
    def title_medium() -> Dict[str, Any]:
        """Medium title text style."""
        return {
            'size': DPIScale.font_size(DPIScale.FONT_SIZE_LARGE),
            'weight': ft.FontWeight.BOLD,
            'color': Colors.GREY_DARK
        }

    @staticmethod
    def subtitle() -> Dict[str, Any]:
        """Subtitle text style."""
        return {
            'size': DPIScale.font_size(DPIScale.FONT_SIZE_MEDIUM),
            'color': Colors.GREY_MEDIUM
        }

    @staticmethod
    def label_bold() -> Dict[str, Any]:
        """Bold label text style."""
        return {
            'size': DPIScale.font_size(DPIScale.FONT_SIZE_NORMAL),
            'weight': ft.FontWeight.BOLD,
            'color': Colors.GREY_MEDIUM
        }

    @staticmethod
    def label_small() -> Dict[str, Any]:
        """Small label text style."""
        return {
            'size': DPIScale.font_size(DPIScale.FONT_SIZE_SMALL),
            'weight': ft.FontWeight.BOLD,
            'color': Colors.GREY_MEDIUM
        }

    @staticmethod
    def body() -> Dict[str, Any]:
        """Body text style."""
        return {
            'size': DPIScale.font_size(DPIScale.FONT_SIZE_NORMAL),
            'color': Colors.GREY_DARK
        }

    @staticmethod
    def body_small() -> Dict[str, Any]:
        """Small body text style."""
        return {
            'size': DPIScale.font_size(DPIScale.FONT_SIZE_NORMAL),
            'color': Colors.GREY_LIGHT
        }

    @staticmethod
    def status_text() -> Dict[str, Any]:
        """Status text style."""
        return {
            'size': DPIScale.font_size(DPIScale.FONT_SIZE_NORMAL),
            'color': Colors.GREY_LIGHT,
            'italic': True
        }

    @staticmethod
    def timer_display() -> Dict[str, Any]:
        """Timer display text style."""
        return {
            'size': DPIScale.font_size(DPIScale.FONT_SIZE_XLARGE),
            'weight': ft.FontWeight.BOLD,
            'color': Colors.PRIMARY_BLUE
        }

    @staticmethod
    def progress_counter() -> Dict[str, Any]:
        """Progress counter text style."""
        return {
            'size': DPIScale.font_size(DPIScale.FONT_SIZE_MEDIUM),
            'weight': ft.FontWeight.BOLD,
            'color': Colors.PRIMARY_BLUE
        }


class LayoutConfig:
    """Layout spacing and sizing configurations."""

    # Spacing values (in pt)
    SPACING_NONE = 0
    SPACING_TINY = DPIScale.SPACE_TINY
    SPACING_SMALL = DPIScale.SPACE_SMALL
    SPACING_MEDIUM = DPIScale.SPACE_MEDIUM
    SPACING_LARGE = DPIScale.SPACE_LARGE

    # Progress bar
    PROGRESS_BAR_WIDTH = DPIScale.to_pt(DPIScale.PROGRESS_BAR_WIDTH)
    PROGRESS_BAR_COLOR = ft.Colors.BLUE_600
    PROGRESS_BAR_BG = ft.Colors.BLUE_100

    # Window sizing
    WINDOW_WIDTH = 1400
    WINDOW_HEIGHT = 900
    WINDOW_MIN_WIDTH = 1200
    WINDOW_MIN_HEIGHT = 700

    # Page padding
    PAGE_PADDING = DPIScale.to_pt(DPIScale.CONTAINER_PADDING_LARGE)


class AnnotationBadgeStyles:
    """Annotation badge styling."""

    @staticmethod
    def badge_padding() -> ft.Padding:
        """Badge padding."""
        return ft.padding.symmetric(
            horizontal=DPIScale.to_pt(DPIScale.CONTAINER_PADDING_LARGE),
            vertical=DPIScale.to_pt(DPIScale.CONTAINER_PADDING_SMALL * 0.8)
        )

    @staticmethod
    def badge_border_radius() -> float:
        """Badge border radius."""
        return DPIScale.to_pt(DPIScale.CONTAINER_PADDING_LARGE)

    @staticmethod
    def badge_font_size() -> float:
        """Badge text font size."""
        return DPIScale.font_size(DPIScale.FONT_SIZE_MEDIUM)


# Export convenience classes
__all__ = [
    'DPIScale',
    'Colors',
    'ButtonStyles',
    'ContainerStyles',
    'TextStyles',
    'LayoutConfig',
    'AnnotationBadgeStyles'
]
