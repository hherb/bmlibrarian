"""
Thesaurus module for medical terminology expansion.

Provides functionality for expanding medical terms using the thesaurus schema,
including synonym lookup, abbreviation expansion, and hierarchical term navigation.
"""

from .expander import ThesaurusExpander, expand_query_terms

__all__ = ['ThesaurusExpander', 'expand_query_terms']
