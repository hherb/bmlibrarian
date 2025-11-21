"""
Backwards compatibility wrapper for document_card_factory_base.

This module has moved to bmlibrarian.gui.flet.document_card_factory_base.
This file re-exports all symbols for backwards compatibility.
"""

from .flet.document_card_factory_base import *  # noqa: F401, F403
from .flet.document_card_factory_base import (
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
