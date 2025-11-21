"""
Backwards compatibility wrapper for unified_document_card.

This module has moved to bmlibrarian.gui.flet.unified_document_card.
This file re-exports all symbols for backwards compatibility.
"""

from .flet.unified_document_card import *  # noqa: F401, F403
from .flet.unified_document_card import (
    UnifiedDocumentCard,
    DocumentCardContext,
    create_literature_card,
    create_scored_card,
    create_citation_card,
)
