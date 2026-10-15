"""
GUI Module for BMLibrarian.

- qt: PySide6/Qt plugin-based GUI (``bmlibrarian_qt.py``) and standalone tools
- document_card_factory_base: framework-neutral document card data model and
  factory base class, implemented by ``qt.qt_document_card_factory``

The former Flet GUI was retired in October 2026 (flet 1.0 changed its event
model; every Flet app except the Citation lab already had a Qt equivalent —
remaining gaps: ROADMAP §1).
"""

from .document_card_factory_base import (
    CardContext,
    PDFButtonState,
    DocumentCardData,
    DocumentCardFactoryBase,
    MAX_AUTHORS_BEFORE_ET_AL,
    SCORE_THRESHOLD_EXCELLENT,
    SCORE_THRESHOLD_GOOD,
    SCORE_THRESHOLD_MODERATE,
    SCORE_COLOR_EXCELLENT,
    SCORE_COLOR_GOOD,
    SCORE_COLOR_MODERATE,
    SCORE_COLOR_POOR,
)

__all__ = [
    'CardContext',
    'PDFButtonState',
    'DocumentCardData',
    'DocumentCardFactoryBase',
    'MAX_AUTHORS_BEFORE_ET_AL',
    'SCORE_THRESHOLD_EXCELLENT',
    'SCORE_THRESHOLD_GOOD',
    'SCORE_THRESHOLD_MODERATE',
    'SCORE_COLOR_EXCELLENT',
    'SCORE_COLOR_GOOD',
    'SCORE_COLOR_MODERATE',
    'SCORE_COLOR_POOR',
]
