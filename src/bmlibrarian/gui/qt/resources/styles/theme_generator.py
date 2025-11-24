"""
DPI-aware theme generator for BMLibrarian Qt GUI.

Generates complete application stylesheets with all dimensions calculated
dynamically from system font metrics to ensure proper scaling across all DPIs.
"""

from typing import Dict
from .dpi_scale import get_font_scale


def generate_default_theme() -> str:
    """
    Generate default theme stylesheet with DPI-aware dimensions.

    All font sizes, padding, margins, and border radii are calculated
    relative to the system default font to ensure consistent appearance
    across different DPI settings (96-384 DPI).

    Returns:
        Complete QSS stylesheet string
    """
    s = get_font_scale()

    return f"""
/* Default Theme for BMLibrarian Qt GUI - DPI-Aware */

/* Main Window */
QMainWindow {{
    background-color: #f5f5f5;
}}

/* Tab Widget */
QTabWidget::pane {{
    border: 1px solid #c0c0c0;
    background-color: white;
}}

QTabBar::tab {{
    background-color: #e0e0e0;
    border: 1px solid #c0c0c0;
    border-bottom-color: #c0c0c0;
    min-width: {s['control_height_large'] * 2}px;
    padding: {s['padding_small']}px {s['padding_medium']}px;
    font-size: {s['font_normal']}pt;
}}

QTabBar::tab:selected {{
    background-color: white;
    border-bottom-color: white;
}}

QTabBar::tab:hover {{
    background-color: #f0f0f0;
}}

/* Buttons */
QPushButton {{
    background-color: #0078d4;
    color: white;
    border: none;
    border-radius: {s['radius_small']}px;
    padding: {s['padding_small']}px {s['padding_medium']}px;
    min-height: {s['control_height_small']}px;
    font-size: {s['font_normal']}pt;
}}

QPushButton:hover {{
    background-color: #106ebe;
}}

QPushButton:pressed {{
    background-color: #005a9e;
}}

QPushButton:disabled {{
    background-color: #cccccc;
    color: #666666;
}}

/* Input Fields */
QLineEdit, QTextEdit, QPlainTextEdit {{
    border: 1px solid #c0c0c0;
    border-radius: {s['radius_small']}px;
    padding: {s['padding_small']}px;
    background-color: white;
    font-size: {s['font_normal']}pt;
}}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: #0078d4;
}}

/* Spin Boxes */
QSpinBox {{
    border: 1px solid #c0c0c0;
    border-radius: {s['radius_small']}px;
    padding: {s['padding_small']}px;
    background-color: white;
    font-size: {s['font_normal']}pt;
    min-height: {s['control_height_small']}px;
}}

QSpinBox:focus {{
    border-color: #0078d4;
}}

/* Labels */
QLabel {{
    color: #333333;
    font-size: {s['font_normal']}pt;
}}

/* Status Bar */
QStatusBar {{
    background-color: #f0f0f0;
    border-top: 1px solid #c0c0c0;
    font-size: {s['font_small']}pt;
    padding: {s['padding_tiny']}px;
}}

/* Menu Bar */
QMenuBar {{
    background-color: #f0f0f0;
    border-bottom: 1px solid #c0c0c0;
    font-size: {s['font_normal']}pt;
}}

QMenuBar::item {{
    padding: {s['padding_small']}px;
    background-color: transparent;
}}

QMenuBar::item:selected {{
    background-color: #e0e0e0;
}}

/* Menus */
QMenu {{
    background-color: white;
    border: 1px solid #c0c0c0;
    font-size: {s['font_normal']}pt;
}}

QMenu::item {{
    padding: {s['padding_small']}px {s['padding_large']}px {s['padding_small']}px {s['padding_small']}px;
}}

QMenu::item:selected {{
    background-color: #e0e0e0;
}}

/* Progress Bar */
QProgressBar {{
    border: 1px solid #c0c0c0;
    border-radius: {s['radius_small']}px;
    text-align: center;
    background-color: white;
    font-size: {s['font_small']}pt;
    min-height: {s['control_height_small']}px;
}}

QProgressBar::chunk {{
    background-color: #0078d4;
    border-radius: {s['radius_tiny']}px;
}}

/* Scroll Bars */
QScrollBar:vertical {{
    background-color: #f0f0f0;
    width: {s['padding_medium']}px;
    margin: 0px;
}}

QScrollBar::handle:vertical {{
    background-color: #c0c0c0;
    min-height: {s['spacing_xlarge']}px;
    border-radius: {s['radius_small']}px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: #a0a0a0;
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar:horizontal {{
    background-color: #f0f0f0;
    height: {s['padding_medium']}px;
    margin: 0px;
}}

QScrollBar::handle:horizontal {{
    background-color: #c0c0c0;
    min-width: {s['spacing_xlarge']}px;
    border-radius: {s['radius_small']}px;
}}

QScrollBar::handle:horizontal:hover {{
    background-color: #a0a0a0;
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

/* Tables */
QTableWidget {{
    gridline-color: #e0e0e0;
    border: 1px solid #c0c0c0;
    font-size: {s['font_normal']}pt;
}}

QTableWidget::item {{
    padding: {s['padding_small']}px;
}}

QTableWidget::item:selected {{
    background-color: #0078d4;
    color: white;
}}

QHeaderView::section {{
    background-color: #f0f0f0;
    padding: {s['padding_small']}px;
    border: none;
    border-bottom: 1px solid #c0c0c0;
    border-right: 1px solid #e0e0e0;
    font-size: {s['font_normal']}pt;
}}

/* Combo Box */
QComboBox {{
    border: 1px solid #c0c0c0;
    border-radius: {s['radius_small']}px;
    padding: {s['padding_small']}px;
    min-height: {s['control_height_small']}px;
    font-size: {s['font_normal']}pt;
}}

QComboBox:focus {{
    border-color: #0078d4;
}}

QComboBox::drop-down {{
    border: none;
    width: {s['control_height_small']}px;
}}

/* Check Box */
QCheckBox {{
    font-size: {s['font_normal']}pt;
    spacing: {s['spacing_small']}px;
}}

QCheckBox::indicator {{
    width: {s['icon_small']}px;
    height: {s['icon_small']}px;
}}

/* Group Box */
QGroupBox {{
    border: 1px solid #c0c0c0;
    border-radius: {s['radius_small']}px;
    margin-top: {s['spacing_medium']}px;
    padding-top: {s['spacing_medium']}px;
    font-size: {s['font_medium']}pt;
    font-weight: bold;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 {s['padding_small']}px;
    background-color: #f5f5f5;
}}

/* Document Cards */
QFrame#DocumentCard {{
    background-color: white;
    border: 1px solid #ddd;
    border-radius: {s['radius_small']}px;
    padding: {s['padding_medium']}px;
}}

QFrame#DocumentCard:hover {{
    border: 1px solid #3498db;
    background-color: #f8f9fa;
}}

QFrame#DocumentCard QLabel#title {{
    font-weight: bold;
    color: #333333;
    font-size: {s['font_medium']}pt;
}}

QFrame#DocumentCard QLabel#authors {{
    font-style: italic;
    color: #666666;
    font-size: {s['font_small']}pt;
}}

QFrame#DocumentCard QLabel#journal {{
    color: #555555;
    font-size: {s['font_small']}pt;
}}

QFrame#DocumentCard QLabel#score {{
    color: #3498db;
    font-weight: bold;
    font-size: {s['font_medium']}pt;
}}

QFrame#DocumentCard QLabel#metadata {{
    font-size: {s['font_tiny']}pt;
    color: #666666;
}}

/* Citation Cards */
QFrame#CitationCard {{
    background-color: #f8f9fa;
    border: 1px solid #dee2e6;
    border-left: {s['padding_small']}px solid #3498db;
    border-radius: {s['radius_small']}px;
    padding: {s['padding_medium']}px;
}}

QFrame#CitationCard:hover {{
    background-color: #e9ecef;
    border-left: {s['padding_small']}px solid #2980b9;
}}

QFrame#CitationCard QLabel#title {{
    font-weight: bold;
    color: #333333;
    font-size: {s['font_medium']}pt;
}}

QFrame#CitationCard QLabel#authors {{
    font-style: italic;
    color: #666666;
    font-size: {s['font_small']}pt;
}}

QFrame#CitationCard QLabel#metadata {{
    font-size: {s['font_tiny']}pt;
    color: #888888;
}}

QFrame#CitationCard QTextEdit {{
    background-color: white;
    border: 1px solid #ddd;
    border-radius: {s['radius_tiny']}px;
    padding: {s['padding_small']}px;
    font-size: {s['font_small']}pt;
}}

/* PDF Buttons - compact sizing to match Find PDF button */
/* All dimensions are DPI-scaled via get_font_scale() */
QPushButton#pdf_view_button {{
    background-color: #1976D2;
    color: white;
    border: none;
    padding: {s['padding_tiny']}px {s['padding_small']}px;
    border-radius: {s['radius_small']}px;
    font-weight: bold;
    min-height: {s['control_height_small']}px;
    max-height: {s['control_height_small']}px;
    font-size: {s['font_normal']}pt;
}}

QPushButton#pdf_view_button:hover {{
    background-color: #1565C0;
}}

QPushButton#pdf_fetch_button {{
    background-color: #F57C00;
    color: white;
    border: none;
    padding: {s['padding_tiny']}px {s['padding_small']}px;
    border-radius: {s['radius_small']}px;
    font-weight: bold;
    min-height: {s['control_height_small']}px;
    max-height: {s['control_height_small']}px;
    font-size: {s['font_normal']}pt;
}}

QPushButton#pdf_fetch_button:hover {{
    background-color: #EF6C00;
}}

QPushButton#pdf_upload_button {{
    background-color: #388E3C;
    color: white;
    border: none;
    padding: {s['padding_tiny']}px {s['padding_small']}px;
    border-radius: {s['radius_small']}px;
    font-weight: bold;
    min-height: {s['control_height_small']}px;
    max-height: {s['control_height_small']}px;
    font-size: {s['font_normal']}pt;
}}

QPushButton#pdf_upload_button:hover {{
    background-color: #2E7D32;
}}
"""


def generate_dark_theme() -> str:
    """
    Generate dark theme stylesheet with DPI-aware dimensions.

    Returns:
        Complete QSS stylesheet string for dark theme
    """
    s = get_font_scale()

    return f"""
/* Dark Theme for BMLibrarian Qt GUI - DPI-Aware */

/* Main Window */
QMainWindow {{
    background-color: #1e1e1e;
    color: #e0e0e0;
}}

/* All widgets default text color */
QWidget {{
    color: #e0e0e0;
    font-size: {s['font_normal']}pt;
}}

/* Tab Widget */
QTabWidget::pane {{
    border: 1px solid #3c3c3c;
    background-color: #2d2d2d;
}}

QTabBar::tab {{
    background-color: #252525;
    color: #b0b0b0;
    border: 1px solid #3c3c3c;
    border-bottom-color: #3c3c3c;
    min-width: {s['control_height_large'] * 2}px;
    padding: {s['padding_small']}px {s['padding_medium']}px;
    font-size: {s['font_normal']}pt;
}}

QTabBar::tab:selected {{
    background-color: #2d2d2d;
    color: #ffffff;
    border-bottom-color: #2d2d2d;
}}

QTabBar::tab:hover {{
    background-color: #353535;
}}

/* Buttons */
QPushButton {{
    background-color: #0078d4;
    color: white;
    border: none;
    border-radius: {s['radius_small']}px;
    padding: {s['padding_small']}px {s['padding_medium']}px;
    min-height: {s['control_height_small']}px;
    font-size: {s['font_normal']}pt;
}}

QPushButton:hover {{
    background-color: #1984d8;
}}

QPushButton:pressed {{
    background-color: #006cbd;
}}

QPushButton:disabled {{
    background-color: #3c3c3c;
    color: #666666;
}}

/* Input Fields */
QLineEdit, QTextEdit, QPlainTextEdit {{
    border: 1px solid #3c3c3c;
    border-radius: {s['radius_small']}px;
    padding: {s['padding_small']}px;
    background-color: #252525;
    color: #e0e0e0;
    font-size: {s['font_normal']}pt;
}}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: #0078d4;
}}

/* Spin Boxes */
QSpinBox {{
    border: 1px solid #3c3c3c;
    border-radius: {s['radius_small']}px;
    padding: {s['padding_small']}px;
    background-color: #252525;
    color: #e0e0e0;
    font-size: {s['font_normal']}pt;
    min-height: {s['control_height_small']}px;
}}

QSpinBox:focus {{
    border-color: #0078d4;
}}

/* Labels */
QLabel {{
    color: #e0e0e0;
    font-size: {s['font_normal']}pt;
}}

/* Status Bar */
QStatusBar {{
    background-color: #252525;
    border-top: 1px solid #3c3c3c;
    color: #b0b0b0;
    font-size: {s['font_small']}pt;
    padding: {s['padding_tiny']}px;
}}

/* Scroll Bars */
QScrollBar:vertical {{
    background-color: #252525;
    width: {s['padding_medium']}px;
    margin: 0px;
}}

QScrollBar::handle:vertical {{
    background-color: #3c3c3c;
    min-height: {s['spacing_xlarge']}px;
    border-radius: {s['radius_small']}px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: #4c4c4c;
}}

QScrollBar:horizontal {{
    background-color: #252525;
    height: {s['padding_medium']}px;
    margin: 0px;
}}

QScrollBar::handle:horizontal {{
    background-color: #3c3c3c;
    min-width: {s['spacing_xlarge']}px;
    border-radius: {s['radius_small']}px;
}}

QScrollBar::handle:horizontal:hover {{
    background-color: #4c4c4c;
}}

/* Combo Box */
QComboBox {{
    border: 1px solid #3c3c3c;
    border-radius: {s['radius_small']}px;
    padding: {s['padding_small']}px;
    min-height: {s['control_height_small']}px;
    background-color: #252525;
    color: #e0e0e0;
    font-size: {s['font_normal']}pt;
}}

/* Check Box */
QCheckBox {{
    color: #e0e0e0;
    font-size: {s['font_normal']}pt;
    spacing: {s['spacing_small']}px;
}}

/* Group Box */
QGroupBox {{
    border: 1px solid #3c3c3c;
    border-radius: {s['radius_small']}px;
    margin-top: {s['spacing_medium']}px;
    padding-top: {s['spacing_medium']}px;
    color: #e0e0e0;
    font-size: {s['font_medium']}pt;
    font-weight: bold;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 {s['padding_small']}px;
    background-color: #1e1e1e;
}}
"""
