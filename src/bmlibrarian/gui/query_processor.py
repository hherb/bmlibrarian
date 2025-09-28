"""
Query Processing Utilities for BMLibrarian Research GUI

Handles query cleaning, validation, and transformation operations.
"""

import re
from typing import Optional


class QueryProcessor:
    """Handles query processing operations including cleaning and validation."""
    
    @staticmethod
    def clean_user_query(query: str) -> str:
        """Clean user-edited query by removing markdown formatting and other issues.
        
        Args:
            query: Raw query string that may contain markdown formatting
            
        Returns:
            Cleaned query string suitable for database search
        """
        if not query:
            return query
        
        # Remove markdown code block backticks
        # Handle both single backticks and triple backticks
        query = re.sub(r'^```.*?\n?', '', query, flags=re.MULTILINE)  # Remove opening ```
        query = re.sub(r'\n?```$', '', query, flags=re.MULTILINE)    # Remove closing ```
        query = re.sub(r'^`+', '', query)                            # Remove leading backticks
        query = re.sub(r'`+$', '', query)                            # Remove trailing backticks
        query = re.sub(r'`([^`]*)`', r'\1', query)                   # Remove inline backticks
        
        # Remove common markdown formatting
        query = re.sub(r'\*\*([^*]*)\*\*', r'\1', query)            # Remove **bold**
        query = re.sub(r'\*([^*]*)\*', r'\1', query)                # Remove *italic*
        query = re.sub(r'_([^_]*)_', r'\1', query)                  # Remove _underline_
        
        # Clean up whitespace
        query = query.strip()
        query = re.sub(r'\n+', ' ', query)                          # Replace newlines with spaces
        query = re.sub(r'\s+', ' ', query)                          # Collapse multiple spaces
        
        print(f"Query cleaned: '{query}'")
        return query
    
    @staticmethod
    def validate_query_syntax(query: str) -> tuple[bool, Optional[str]]:
        """Validate PostgreSQL tsquery syntax.
        
        Args:
            query: Query string to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not query or not query.strip():
            return False, "Query cannot be empty"
        
        # Basic validation for common tsquery syntax issues
        cleaned_query = query.strip()
        
        # Check for unmatched parentheses
        if cleaned_query.count('(') != cleaned_query.count(')'):
            return False, "Unmatched parentheses in query"
        
        # Check for invalid characters that could cause tsquery errors
        invalid_chars = ['```', '**', '__', '~~']
        for char_seq in invalid_chars:
            if char_seq in cleaned_query:
                return False, f"Invalid character sequence '{char_seq}' found in query"
        
        # Check for empty operators (e.g., "& &" or "| |")
        if re.search(r'[&|]\s*[&|]', cleaned_query):
            return False, "Invalid operator sequence found in query"
        
        # Check for operators at start/end
        if re.match(r'^\s*[&|]', cleaned_query) or re.search(r'[&|]\s*$', cleaned_query):
            return False, "Query cannot start or end with operators"
        
        return True, None
    
    @staticmethod
    def format_query_for_display(query: str, max_length: int = 100) -> str:
        """Format query for display in UI components.
        
        Args:
            query: Query string to format
            max_length: Maximum length before truncation
            
        Returns:
            Formatted query string
        """
        if not query:
            return "No query generated"
        
        # Clean whitespace and format
        formatted = re.sub(r'\s+', ' ', query.strip())
        
        # Truncate if necessary
        if len(formatted) > max_length:
            formatted = formatted[:max_length-3] + "..."
        
        return formatted
    
    @staticmethod
    def extract_search_terms(query: str) -> list[str]:
        """Extract individual search terms from a PostgreSQL tsquery.
        
        Args:
            query: PostgreSQL tsquery string
            
        Returns:
            List of individual search terms
        """
        if not query:
            return []
        
        # Remove operators and parentheses, split by whitespace
        clean_query = re.sub(r'[&|()\']', ' ', query)
        terms = [term.strip() for term in clean_query.split() if term.strip()]
        
        # Remove duplicates while preserving order
        seen = set()
        unique_terms = []
        for term in terms:
            if term.lower() not in seen:
                seen.add(term.lower())
                unique_terms.append(term)
        
        return unique_terms
    
    @staticmethod
    def suggest_query_improvements(query: str) -> list[str]:
        """Suggest improvements for a query.
        
        Args:
            query: Query string to analyze
            
        Returns:
            List of improvement suggestions
        """
        suggestions = []
        
        if not query or not query.strip():
            suggestions.append("Add search terms to your query")
            return suggestions
        
        # Check for common issues
        if '&' not in query and '|' not in query and len(query.split()) > 1:
            suggestions.append("Consider using & (AND) or | (OR) to combine terms")
        
        if len(query.split()) == 1:
            suggestions.append("Consider adding related terms with | (OR) for broader results")
        
        if query.count('(') > 3:
            suggestions.append("Consider simplifying nested parentheses for better readability")
        
        # Check for very long terms that might not match
        long_terms = [term for term in query.split() if len(term) > 20]
        if long_terms:
            suggestions.append("Very long terms may not match - consider shorter alternatives")
        
        return suggestions