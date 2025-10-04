"""
Display Utilities Module for Research GUI

Facade module that provides backward compatibility by importing from specialized modules.
For new code, prefer importing directly from the specialized modules:
- document_card_utils: Document display cards
- citation_card_utils: Citation display cards
- counterfactual_display_utils: Counterfactual analysis displays
"""

# Import document card functionality
from .document_card_utils import (
    DocumentCardCreator,
    create_document_card,
    create_document_cards_list,
    create_scored_document_cards_list
)

# Import citation card functionality
from .citation_card_utils import (
    CitationCardCreator,
    create_citation_card,
    create_citation_cards_list,
    extract_citation_data
)

# Import counterfactual display functionality
from .counterfactual_display_utils import (
    CounterfactualDisplayCreator,
    create_counterfactual_display
)

# Export all classes and functions for backward compatibility
__all__ = [
    # Classes
    'DocumentCardCreator',
    'CitationCardCreator',
    'CounterfactualDisplayCreator',
    # Document functions
    'create_document_card',
    'create_document_cards_list',
    'create_scored_document_cards_list',
    # Citation functions
    'create_citation_card',
    'create_citation_cards_list',
    'extract_citation_data',
    # Counterfactual functions
    'create_counterfactual_display',
]
