"""
Backwards compatibility wrapper for card_factory.

This module has moved to bmlibrarian.gui.flet.card_factory.
This file re-exports all symbols for backwards compatibility.
"""

from .flet.card_factory import *  # noqa: F401, F403
from .flet.card_factory import CardFactory, create_document_cards_for_tab
