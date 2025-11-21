"""
UI Constants and StyleSheets for the Research Tab.

This module contains DPI-aware styling constants and stylesheet generators
for consistent appearance across the research tab interface.
"""

from typing import Dict, Any

from ...resources.styles import scale_px


class UIConstants:
    """UI layout and styling constants with DPI-aware scaling.

    All pixel values are scaled for DPI-awareness. Value range constants
    (like spinbox ranges and score thresholds) are not scaled as they
    represent logical values, not visual dimensions.
    """

    def __init__(self, scale_dict: Dict[str, Any]) -> None:
        """Initialize constants with scale dictionary.

        Args:
            scale_dict: Dictionary from get_font_scale() with predefined scale values
        """
        s = scale_dict

        # =====================================================================
        # Font Sizes (in points, DPI-independent)
        # =====================================================================
        self.TITLE_FONT_SIZE: int = s['font_xlarge']  # ~14pt
        self.SUBTITLE_FONT_SIZE: int = s['font_normal']  # System default
        self.TAB_HEADER_FONT_SIZE: int = s['font_large']  # ~12pt
        self.CARD_TITLE_FONT_SIZE: int = s['font_medium']  # Document/citation card titles
        self.CARD_SUBTITLE_FONT_SIZE: int = s['font_normal']  # Authors, publication info
        self.CARD_BODY_FONT_SIZE: int = s['font_normal']  # Abstract, reasoning, passages
        self.CARD_LABEL_FONT_SIZE: int = s['font_small']  # Section labels

        # =====================================================================
        # Colors (CSS color codes, not scaled)
        # =====================================================================
        # Primary colors
        self.COLOR_PRIMARY_BLUE: str = "#1976D2"
        self.COLOR_PRIMARY_BLUE_HOVER: str = "#1565C0"
        self.COLOR_PRIMARY_BLUE_PRESSED: str = "#1565C0"

        # Status colors
        self.COLOR_SUCCESS_GREEN: str = "#4CAF50"
        self.COLOR_SUCCESS_GREEN_HOVER: str = "#45a049"
        self.COLOR_SUCCESS_GREEN_PRESSED: str = "#3d8b40"
        self.COLOR_ERROR_RED: str = "#F44336"
        self.COLOR_ERROR_RED_HOVER: str = "#D32F2F"
        self.COLOR_ERROR_RED_PRESSED: str = "#C62828"
        self.COLOR_WARNING_ORANGE: str = "#FF9800"

        # Neutral colors
        self.COLOR_DISABLED_GREY: str = "#BDBDBD"
        self.COLOR_DISABLED_TEXT: str = "#757575"
        self.COLOR_TEXT_GREY: str = "#666666"
        self.COLOR_BACKGROUND_GREY: str = "#F5F5F5"
        self.COLOR_BORDER_GREY: str = "#E0E0E0"
        self.COLOR_WHITE: str = "white"
        self.COLOR_TEXT_INPUT_BACKGROUND: str = "#FFF8F0"  # Faint pastel sand

        # Highlight colors
        self.COLOR_HIGHLIGHT_YELLOW: str = "#FFF9C4"
        self.COLOR_HIGHLIGHT_YELLOW_BORDER: str = "#FFF176"
        self.COLOR_HIGHLIGHT_BLUE: str = "#E3F2FD"
        self.COLOR_HIGHLIGHT_BLUE_BORDER: str = "#BBDEFB"

        # =====================================================================
        # Spacing (scaled pixels)
        # =====================================================================
        self.MAIN_LAYOUT_MARGIN: int = s['spacing_large']
        self.MAIN_LAYOUT_SPACING: int = s['spacing_medium']
        self.CONTROLS_SPACING: int = s['spacing_medium']
        self.ROW2_SPACING: int = s['spacing_large']
        self.HEADER_BOTTOM_MARGIN: int = s['spacing_medium']
        self.HEADER_SPACING: int = s['spacing_small']
        self.TAB_WIDGET_MARGIN: int = s['spacing_large']

        # Card spacing
        self.CARD_SPACING: int = scale_px(8)
        self.CARD_INTERNAL_SPACING: int = scale_px(5)
        self.CARD_PADDING: int = scale_px(8)
        self.CARD_CONTENT_MARGIN_TOP: int = scale_px(10)

        # General layout spacing
        self.SECTION_SPACING: int = scale_px(10)
        self.BUTTON_SPACING: int = scale_px(10)

        # Padding values
        self.PADDING_SMALL: int = s['padding_small']
        self.PADDING_MEDIUM: int = s['padding_medium']
        self.PADDING_LARGE: int = scale_px(20)

        # =====================================================================
        # Widget Sizes (scaled pixels)
        # =====================================================================
        self.QUESTION_INPUT_MIN_HEIGHT: int = s['control_height_large']
        self.QUESTION_INPUT_MAX_HEIGHT: int = s['control_height_xlarge']
        self.START_BUTTON_MIN_HEIGHT: int = s['control_height_large']
        self.START_BUTTON_MIN_WIDTH: int = scale_px(140)
        self.CANCEL_BUTTON_MIN_WIDTH: int = scale_px(140)
        self.NEW_BUTTON_MIN_WIDTH: int = scale_px(80)
        self.SPINBOX_WIDTH: int = scale_px(80)
        self.QUERY_DISPLAY_MAX_HEIGHT: int = scale_px(100)
        self.PROGRESS_BAR_HEIGHT: int = scale_px(20)
        self.STATUS_BAR_HEIGHT: int = scale_px(30)
        self.HEADER_MAX_HEIGHT: int = scale_px(40)

        # =====================================================================
        # Border Radii (scaled pixels)
        # =====================================================================
        self.CONTROLS_BORDER_RADIUS: int = s['radius_medium']
        self.BUTTON_BORDER_RADIUS: int = s['radius_small']
        self.INPUT_BORDER_RADIUS: int = s['radius_small']
        self.CARD_BORDER_RADIUS: int = scale_px(6)
        self.PROGRESS_BAR_RADIUS: int = scale_px(4)
        self.PROGRESS_BAR_CHUNK_RADIUS: int = scale_px(3)

        # =====================================================================
        # Spinbox Value Ranges (logical values, not scaled)
        # =====================================================================
        self.MAX_RESULTS_MIN: int = 10
        self.MAX_RESULTS_MAX: int = 1000
        self.MAX_RESULTS_DEFAULT: int = 100
        self.MIN_RELEVANT_MIN: int = 1
        self.MIN_RELEVANT_MAX: int = 100
        self.MIN_RELEVANT_DEFAULT: int = 10

        # Display limits
        self.MAX_KEYWORDS_DISPLAY: int = 10

        # =====================================================================
        # Document Score Thresholds (logical values, not scaled)
        # =====================================================================
        self.SCORE_THRESHOLD_HIGH_RELEVANCE: float = 4.0
        self.SCORE_THRESHOLD_RELEVANT: float = 3.0
        self.SCORE_THRESHOLD_SOMEWHAT_RELEVANT: float = 2.0

        # Document Score Colors
        self.SCORE_COLOR_HIGH: str = "#4CAF50"  # Green
        self.SCORE_COLOR_RELEVANT: str = "#2196F3"  # Blue
        self.SCORE_COLOR_SOMEWHAT: str = "#FF9800"  # Orange
        self.SCORE_COLOR_LOW: str = "#9E9E9E"  # Grey

        # =====================================================================
        # Priority Colors (for counterfactual analysis)
        # =====================================================================
        self.PRIORITY_COLORS: Dict[str, str] = {
            'HIGH': '#F44336',
            'MEDIUM': '#FF9800',
            'LOW': '#9E9E9E'
        }


class StyleSheets:
    """Centralized stylesheet definitions with DPI-aware scaling.

    All methods return CSS stylesheet strings. Methods that need dynamic
    values take UIConstants and/or scale_dict as parameters.
    """

    @staticmethod
    def controls_frame(c: UIConstants) -> str:
        """Stylesheet for controls section frame.

        Args:
            c: UI constants for styling values

        Returns:
            CSS stylesheet string
        """
        return f"""
            QFrame {{
                background-color: {c.COLOR_BACKGROUND_GREY};
                border: 1px solid {c.COLOR_BORDER_GREY};
                border-radius: {c.CONTROLS_BORDER_RADIUS}px;
                padding: {c.CONTROLS_SPACING}px;
            }}
        """

    @staticmethod
    def start_button(c: UIConstants, scale_dict: Dict[str, Any]) -> str:
        """Stylesheet for Start Research button.

        Args:
            c: UI constants
            scale_dict: Scale dictionary from get_font_scale()

        Returns:
            CSS stylesheet string
        """
        s = scale_dict
        return f"""
            QPushButton {{
                background-color: {c.COLOR_PRIMARY_BLUE};
                color: {c.COLOR_WHITE};
                font-weight: bold;
                border-radius: {c.BUTTON_BORDER_RADIUS}px;
                padding: {s['padding_small']}px {s['padding_medium']}px;
            }}
            QPushButton:hover {{
                background-color: {c.COLOR_PRIMARY_BLUE_HOVER};
            }}
            QPushButton:disabled {{
                background-color: {c.COLOR_DISABLED_GREY};
            }}
        """

    @staticmethod
    def text_input(c: UIConstants, scale_dict: Dict[str, Any]) -> str:
        """Stylesheet for all text input widgets (QTextEdit, QLineEdit, QSpinBox).

        Args:
            c: UI constants
            scale_dict: Scale dictionary from get_font_scale()

        Returns:
            CSS stylesheet string
        """
        s = scale_dict
        return f"""
            QTextEdit, QLineEdit, QSpinBox {{
                background-color: {c.COLOR_TEXT_INPUT_BACKGROUND};
                border: 1px solid {c.COLOR_BORDER_GREY};
                border-radius: {s['radius_small']}px;
                padding: {s['padding_small']}px;
            }}
            QTextEdit:focus, QLineEdit:focus, QSpinBox:focus {{
                border: 2px solid {c.COLOR_PRIMARY_BLUE};
            }}
        """

    @staticmethod
    def cancel_button(c: UIConstants) -> str:
        """Stylesheet for Cancel button.

        Args:
            c: UI constants for styling values

        Returns:
            CSS stylesheet string
        """
        return f"""
            QPushButton {{
                background-color: {c.COLOR_ERROR_RED};
                color: {c.COLOR_WHITE};
                border: none;
                border-radius: {c.BUTTON_BORDER_RADIUS}px;
                font-weight: bold;
                padding: {c.CARD_PADDING}px {c.PADDING_MEDIUM}px;
            }}
            QPushButton:hover {{
                background-color: {c.COLOR_ERROR_RED_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {c.COLOR_ERROR_RED_PRESSED};
            }}
            QPushButton:disabled {{
                background-color: {c.COLOR_DISABLED_GREY};
                color: {c.COLOR_DISABLED_TEXT};
            }}
        """

    @staticmethod
    def new_button(c: UIConstants) -> str:
        """Stylesheet for New button.

        Args:
            c: UI constants for styling values

        Returns:
            CSS stylesheet string
        """
        return f"""
            QPushButton {{
                background-color: {c.COLOR_SUCCESS_GREEN};
                color: {c.COLOR_WHITE};
                border: none;
                border-radius: {c.BUTTON_BORDER_RADIUS}px;
                font-weight: bold;
                padding: {c.CARD_PADDING}px {c.PADDING_MEDIUM}px;
            }}
            QPushButton:hover {{
                background-color: {c.COLOR_SUCCESS_GREEN_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {c.COLOR_SUCCESS_GREEN_PRESSED};
            }}
        """

    @staticmethod
    def save_button(c: UIConstants) -> str:
        """Stylesheet for Save/Export buttons (green variant).

        Args:
            c: UI constants for styling values

        Returns:
            CSS stylesheet string
        """
        return f"""
            QPushButton {{
                background-color: {c.COLOR_SUCCESS_GREEN};
                color: {c.COLOR_WHITE};
                border: none;
                border-radius: {c.BUTTON_BORDER_RADIUS}px;
                padding: {c.CARD_PADDING}px {c.PADDING_MEDIUM}px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {c.COLOR_SUCCESS_GREEN_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {c.COLOR_SUCCESS_GREEN_PRESSED};
            }}
            QPushButton:disabled {{
                background-color: {c.COLOR_DISABLED_GREY};
                color: {c.COLOR_DISABLED_TEXT};
            }}
        """

    @staticmethod
    def export_button(c: UIConstants) -> str:
        """Stylesheet for Export buttons (blue variant).

        Args:
            c: UI constants for styling values

        Returns:
            CSS stylesheet string
        """
        return f"""
            QPushButton {{
                background-color: {c.COLOR_PRIMARY_BLUE};
                color: {c.COLOR_WHITE};
                border: none;
                border-radius: {c.BUTTON_BORDER_RADIUS}px;
                padding: {c.CARD_PADDING}px {c.PADDING_MEDIUM}px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {c.COLOR_PRIMARY_BLUE_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {c.COLOR_PRIMARY_BLUE_PRESSED};
            }}
            QPushButton:disabled {{
                background-color: {c.COLOR_DISABLED_GREY};
                color: {c.COLOR_DISABLED_TEXT};
            }}
        """

    @staticmethod
    def status_bar(c: UIConstants) -> str:
        """Stylesheet for status bar.

        Args:
            c: UI constants for styling values

        Returns:
            CSS stylesheet string
        """
        return f"""
            QWidget {{
                background-color: {c.COLOR_BACKGROUND_GREY};
                border-top: 1px solid {c.COLOR_BORDER_GREY};
            }}
        """

    @staticmethod
    def query_display(c: UIConstants) -> str:
        """Stylesheet for query text display.

        Args:
            c: UI constants for styling values

        Returns:
            CSS stylesheet string
        """
        return f"""
            QTextEdit {{
                background-color: {c.COLOR_BACKGROUND_GREY};
                border: 1px solid {c.COLOR_BORDER_GREY};
                border-radius: {c.BUTTON_BORDER_RADIUS}px;
                padding: {c.CARD_PADDING}px;
                font-family: 'Courier New', monospace;
            }}
        """

    @staticmethod
    def progress_bar(c: UIConstants) -> str:
        """Stylesheet for progress bar.

        Args:
            c: UI constants for styling values

        Returns:
            CSS stylesheet string
        """
        return f"""
            QProgressBar {{
                border: 1px solid {c.COLOR_BORDER_GREY};
                border-radius: {c.PROGRESS_BAR_RADIUS}px;
                text-align: center;
                height: {c.PROGRESS_BAR_HEIGHT}px;
            }}
            QProgressBar::chunk {{
                background-color: {c.COLOR_PRIMARY_BLUE};
                border-radius: {c.PROGRESS_BAR_CHUNK_RADIUS}px;
            }}
        """

    @staticmethod
    def counterfactual_card(c: UIConstants) -> str:
        """Stylesheet for counterfactual question cards.

        Args:
            c: UI constants for styling values

        Returns:
            CSS stylesheet string
        """
        return f"""
            QFrame {{
                background-color: {c.COLOR_WHITE};
                border: 1px solid {c.COLOR_BORDER_GREY};
                border-radius: {c.CARD_BORDER_RADIUS}px;
                padding: {c.SECTION_SPACING + 2}px;
            }}
        """

    @staticmethod
    def counterfactual_info_box(c: UIConstants) -> str:
        """Stylesheet for counterfactual info boxes (yellow highlight).

        Args:
            c: UI constants for styling values

        Returns:
            CSS stylesheet string
        """
        return f"""
            QFrame {{
                background-color: {c.COLOR_HIGHLIGHT_YELLOW};
                border: 1px solid {c.COLOR_HIGHLIGHT_YELLOW_BORDER};
                border-radius: {c.PROGRESS_BAR_CHUNK_RADIUS}px;
                padding: {c.CARD_PADDING}px;
            }}
        """

    @staticmethod
    def reasoning_box(c: UIConstants) -> str:
        """Stylesheet for AI reasoning boxes (blue highlight).

        Args:
            c: UI constants for styling values

        Returns:
            CSS stylesheet string
        """
        return f"""
            QFrame {{
                background-color: {c.COLOR_HIGHLIGHT_BLUE};
                border: 1px solid {c.COLOR_HIGHLIGHT_BLUE_BORDER};
                border-radius: {c.PROGRESS_BAR_CHUNK_RADIUS}px;
                padding: {c.CARD_PADDING}px;
            }}
        """

    @staticmethod
    def empty_state_label(c: UIConstants) -> str:
        """Stylesheet for empty state labels.

        Args:
            c: UI constants for styling values

        Returns:
            CSS stylesheet string
        """
        return f"color: {c.COLOR_TEXT_GREY}; padding: {c.PADDING_LARGE}px;"

    @staticmethod
    def error_label() -> str:
        """Stylesheet for error labels.

        Returns:
            CSS stylesheet string
        """
        return "color: red; padding: 10px;"

    @staticmethod
    def card_label_padding(c: UIConstants) -> str:
        """Stylesheet for card internal labels with padding.

        Args:
            c: UI constants for styling values

        Returns:
            CSS stylesheet string
        """
        return f"padding: {c.CARD_INTERNAL_SPACING - 1}px;"
