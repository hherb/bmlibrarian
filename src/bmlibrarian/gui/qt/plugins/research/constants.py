"""
UI Constants and StyleSheets for the Research Tab.

This module contains DPI-aware styling constants and stylesheet generators
for consistent appearance across the research tab interface.
"""

from ...resources.styles import scale_px


class UIConstants:
    """UI layout and styling constants with DPI-aware scaling."""

    def __init__(self, scale_dict: dict):
        """Initialize constants with scale dictionary.

        Args:
            scale_dict: Dictionary from get_font_scale() with predefined scale values
        """
        s = scale_dict

        # Fonts - use predefined font size keys (in points, DPI-independent)
        self.TITLE_FONT_SIZE = s['font_xlarge']  # ~14pt
        self.SUBTITLE_FONT_SIZE = s['font_normal']  # System default
        self.TAB_HEADER_FONT_SIZE = s['font_large']  # ~12pt
        self.CARD_TITLE_FONT_SIZE = s['font_medium']  # Document/citation card titles
        self.CARD_SUBTITLE_FONT_SIZE = s['font_normal']  # Authors, publication info
        self.CARD_BODY_FONT_SIZE = s['font_normal']  # Abstract, reasoning, passages
        self.CARD_LABEL_FONT_SIZE = s['font_small']  # Section labels like "Abstract:", "Summary:"

        # Colors (not scaled)
        self.COLOR_PRIMARY_BLUE = "#1976D2"
        self.COLOR_PRIMARY_BLUE_HOVER = "#1565C0"
        self.COLOR_DISABLED_GREY = "#BDBDBD"
        self.COLOR_TEXT_GREY = "#666666"
        self.COLOR_BACKGROUND_GREY = "#F5F5F5"
        self.COLOR_BORDER_GREY = "#E0E0E0"
        self.COLOR_WHITE = "white"
        self.COLOR_TEXT_INPUT_BACKGROUND = "#FFF8F0"  # Very faint pastel sand color

        # Spacing - use predefined spacing keys (in pixels)
        self.MAIN_LAYOUT_MARGIN = s['spacing_large']
        self.MAIN_LAYOUT_SPACING = s['spacing_medium']
        self.CONTROLS_SPACING = s['spacing_medium']
        self.ROW2_SPACING = s['spacing_large']
        self.HEADER_BOTTOM_MARGIN = s['spacing_medium']
        self.HEADER_SPACING = s['spacing_small']
        self.TAB_WIDGET_MARGIN = s['spacing_large']

        # Widget Sizes - use control height keys
        self.QUESTION_INPUT_MIN_HEIGHT = s['control_height_large']
        self.QUESTION_INPUT_MAX_HEIGHT = s['control_height_xlarge']
        self.START_BUTTON_MIN_HEIGHT = s['control_height_large']
        self.START_BUTTON_MIN_WIDTH = scale_px(140)
        self.SPINBOX_WIDTH = scale_px(80)

        # Border Radii - use predefined radius keys
        self.CONTROLS_BORDER_RADIUS = s['radius_medium']
        self.BUTTON_BORDER_RADIUS = s['radius_small']

        # Spinbox Ranges (not scaled - these are value ranges)
        self.MAX_RESULTS_MIN = 10
        self.MAX_RESULTS_MAX = 1000
        self.MAX_RESULTS_DEFAULT = 100
        self.MIN_RELEVANT_MIN = 1
        self.MIN_RELEVANT_MAX = 100
        self.MIN_RELEVANT_DEFAULT = 10

        # Document Score Thresholds (not scaled - these are score values)
        self.SCORE_THRESHOLD_HIGH_RELEVANCE = 4.0
        self.SCORE_THRESHOLD_RELEVANT = 3.0
        self.SCORE_THRESHOLD_SOMEWHAT_RELEVANT = 2.0

        # Document Score Colors (not scaled)
        self.SCORE_COLOR_HIGH = "#4CAF50"  # Green
        self.SCORE_COLOR_RELEVANT = "#2196F3"  # Blue
        self.SCORE_COLOR_SOMEWHAT = "#FF9800"  # Orange
        self.SCORE_COLOR_LOW = "#9E9E9E"  # Grey


class StyleSheets:
    """Centralized stylesheet definitions with DPI-aware scaling."""

    @staticmethod
    def controls_frame(c: UIConstants) -> str:
        """Stylesheet for controls section frame."""
        return f"""
            QFrame {{
                background-color: {c.COLOR_BACKGROUND_GREY};
                border: 1px solid {c.COLOR_BORDER_GREY};
                border-radius: {c.CONTROLS_BORDER_RADIUS}px;
                padding: {c.CONTROLS_SPACING}px;
            }}
        """

    @staticmethod
    def start_button(c: UIConstants, scale_dict: dict) -> str:
        """Stylesheet for Start Research button.

        Args:
            c: UI constants
            scale_dict: Scale dictionary from get_font_scale()
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
    def text_input(c: UIConstants, scale_dict: dict) -> str:
        """Stylesheet for all text input widgets (QTextEdit, QLineEdit, QSpinBox).

        Args:
            c: UI constants
            scale_dict: Scale dictionary from get_font_scale()
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
    def cancel_button() -> str:
        """Stylesheet for Cancel button."""
        return """
            QPushButton {
                background-color: #F44336;
                color: white;
                border: none;
                border-radius: 4px;
                font-weight: bold;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #D32F2F;
            }
            QPushButton:pressed {
                background-color: #C62828;
            }
            QPushButton:disabled {
                background-color: #BDBDBD;
                color: #757575;
            }
        """

    @staticmethod
    def new_button() -> str:
        """Stylesheet for New button."""
        return """
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 4px;
                font-weight: bold;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
        """

    @staticmethod
    def save_button() -> str:
        """Stylesheet for Save/Export buttons (green variant)."""
        return """
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
            QPushButton:disabled {
                background-color: #BDBDBD;
                color: #757575;
            }
        """

    @staticmethod
    def export_button() -> str:
        """Stylesheet for Export buttons (blue variant)."""
        return """
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:pressed {
                background-color: #1565C0;
            }
            QPushButton:disabled {
                background-color: #BDBDBD;
                color: #757575;
            }
        """

    @staticmethod
    def status_bar(c: UIConstants) -> str:
        """Stylesheet for status bar."""
        return f"""
            QWidget {{
                background-color: {c.COLOR_BACKGROUND_GREY};
                border-top: 1px solid {c.COLOR_BORDER_GREY};
            }}
        """

    @staticmethod
    def query_display() -> str:
        """Stylesheet for query text display."""
        return """
            QTextEdit {
                background-color: #F5F5F5;
                border: 1px solid #E0E0E0;
                border-radius: 4px;
                padding: 8px;
                font-family: 'Courier New', monospace;
            }
        """

    @staticmethod
    def progress_bar() -> str:
        """Stylesheet for progress bar."""
        return """
            QProgressBar {
                border: 1px solid #E0E0E0;
                border-radius: 4px;
                text-align: center;
                height: 20px;
            }
            QProgressBar::chunk {
                background-color: #2196F3;
                border-radius: 3px;
            }
        """

    @staticmethod
    def counterfactual_card() -> str:
        """Stylesheet for counterfactual question cards."""
        return """
            QFrame {
                background-color: white;
                border: 1px solid #E0E0E0;
                border-radius: 6px;
                padding: 12px;
            }
        """

    @staticmethod
    def counterfactual_info_box() -> str:
        """Stylesheet for counterfactual info boxes (yellow highlight)."""
        return """
            QFrame {
                background-color: #FFF9C4;
                border: 1px solid #FFF176;
                border-radius: 3px;
                padding: 8px;
            }
        """

    @staticmethod
    def reasoning_box() -> str:
        """Stylesheet for AI reasoning boxes (blue highlight)."""
        return """
            QFrame {
                background-color: #E3F2FD;
                border: 1px solid #BBDEFB;
                border-radius: 3px;
                padding: 8px;
            }
        """
