"""
Query Processing Module

Handles query validation, editing, database search orchestration, and result processing.
"""

from typing import List, Dict, Any, Optional, Generator
from bmlibrarian.agents import QueryAgent


class QueryProcessor:
    """Handles query generation, validation, editing, and search execution."""
    
    def __init__(self, config, ui):
        self.config = config
        self.ui = ui
        self.query_agent: Optional[QueryAgent] = None
        self.current_question: Optional[str] = None
        self.current_query: Optional[str] = None
    
    def set_query_agent(self, query_agent: QueryAgent) -> None:
        """Set the query agent for database operations."""
        self.query_agent = query_agent
    
    def search_documents_with_review(self, question: str) -> List[Dict[str, Any]]:
        """Use QueryAgent to search documents with human-in-the-loop query editing."""
        self.ui.show_step_header(2, "Database Query Generation & Search")
        
        try:
            # Step 2a: Generate initial to_tsquery string
            self.ui.show_progress_message(f'Generating database query for: "{question}"')
            self.ui.show_info_message("Converting natural language to PostgreSQL to_tsquery format...")
            
            initial_query = self.query_agent.convert_question(question)
            
            if not initial_query:
                self.ui.show_error_message("Failed to generate database query.")
                return []
            
            # Step 2b: Show generated query and allow editing
            current_query = initial_query
            
            while True:
                choice = self.ui.display_query_review(question, current_query)
                
                if choice == '1':
                    # Proceed with current query
                    self.current_query = current_query
                    self.current_question = question
                    break
                    
                elif choice == '2':
                    # Manual editing
                    new_query = self.ui.get_manual_query_edit(current_query)
                    
                    if new_query != current_query:
                        # Basic validation
                        if self._validate_tsquery(new_query):
                            current_query = new_query
                            self.ui.show_success_message("Query updated successfully")
                        else:
                            self.ui.show_warning_message("Query format may be invalid, but proceeding...")
                            current_query = new_query
                    else:
                        self.ui.show_info_message("No changes made - keeping original query")
                    continue
                    
                elif choice == '3':
                    # Regenerate with different approach
                    self.ui.show_progress_message("Regenerating query...")
                    self.ui.show_info_message("Trying different keyword extraction approach...")
                    
                    # You could implement different generation strategies here
                    # For now, we'll just regenerate with the same method
                    regenerated_query = self.query_agent.convert_question(question)
                    
                    if regenerated_query and regenerated_query != current_query:
                        current_query = regenerated_query
                        self.ui.show_success_message("New query generated")
                    else:
                        self.ui.show_warning_message("Generated same query - no change")
                    continue
                    
                elif choice == '4':
                    # Go back to question entry
                    return []
                    
                else:
                    self.ui.show_error_message("Invalid option. Please choose 1-4.")
                    continue
            
            # Step 2c: Execute the search with the final query
            self.ui.show_progress_message(f"Executing search with query: {current_query}")
            self.ui.show_info_message("Searching database...")
            
            # Use the raw database search with the validated query
            documents = self._execute_database_search(current_query)
            
            if not documents:
                self.ui.show_error_message("No documents found with this query.")
                self.ui.show_info_message("Suggestions:")
                print("• Try broader search terms")
                print("• Use fewer AND (&) operators")
                print("• Add more OR (|) alternatives")
                print("• Check spelling of medical terms")
                
                retry = input("\nWould you like to modify the query and try again? (y/n): ").strip().lower()
                if retry in ['y', 'yes']:
                    return self.search_documents_with_review(question)
                else:
                    return []
            
            self.ui.show_success_message(f"Found {len(documents)} documents")
            return documents
            
        except Exception as e:
            self.ui.show_error_message(f"Error in query generation/search: {e}")
            print("\nPossible issues:")
            print("• Database connection problem")
            print("• Invalid query syntax")
            print("• Ollama service unavailable")
            
            return []
    
    def _execute_database_search(self, query: str) -> List[Dict[str, Any]]:
        """Execute database search with the given query."""
        try:
            from bmlibrarian.database import find_abstracts
            
            documents = []
            results_generator = find_abstracts(
                query,
                max_rows=self.config.max_search_results,
                plain=False  # Use to_tsquery format
            )
            
            for doc in results_generator:
                documents.append(doc)
            
            return documents
            
        except Exception as e:
            raise Exception(f"Database search failed: {e}")
    
    def _validate_tsquery(self, query: str) -> bool:
        """Basic validation of to_tsquery format."""
        try:
            # Simple validation checks
            if not query.strip():
                return False
            
            # Check for balanced parentheses
            if query.count('(') != query.count(')'):
                return False
            
            # Check for valid operators (basic check)
            invalid_patterns = ['&&', '||', '&|', '|&', '& &', '| |']
            for pattern in invalid_patterns:
                if pattern in query:
                    return False
            
            # Check for empty parentheses
            if '()' in query:
                return False
            
            # Check for operators at start/end
            stripped = query.strip()
            if stripped.startswith(('&', '|')) or stripped.endswith(('&', '|')):
                return False
            
            return True
        except:
            return False
    
    def test_database_connection(self) -> bool:
        """Test database connection."""
        try:
            from bmlibrarian.database import get_db_manager
            
            db_manager = get_db_manager()
            with db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    result = cur.fetchone()
                    return result is not None
        except Exception as e:
            self.ui.show_error_message(f"Database connection error: {e}")
            return False
    
    def get_current_query(self) -> Optional[str]:
        """Get the current validated query."""
        return self.current_query
    
    def get_current_question(self) -> Optional[str]:
        """Get the current research question."""
        return self.current_question


class DocumentProcessor:
    """Handles document filtering, pagination, and display logic."""
    
    def __init__(self, config, ui):
        self.config = config
        self.ui = ui
    
    def process_search_results(self, documents: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
        """Process and display search results with user interaction."""
        while True:
            choice = self.ui.display_search_results(documents)
            
            if choice == '1':
                # Proceed with results
                return documents
            
            elif choice == '2':
                # Search again - return None to signal need for new search
                return None
            
            elif choice == '3':
                # Show detailed view
                self.ui.show_detailed_documents(documents)
                continue
            
            elif choice == 'empty':
                # No documents found
                return []
            
            else:
                self.ui.show_error_message("Invalid option. Please choose 1-3.")
    
    def filter_documents_by_criteria(self, documents: List[Dict[str, Any]], 
                                   criteria: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Filter documents based on specified criteria."""
        filtered = documents.copy()
        
        # Filter by date range if specified
        if 'min_year' in criteria and criteria['min_year']:
            filtered = [doc for doc in filtered 
                       if self._extract_year(doc.get('publication_date', '')) >= criteria['min_year']]
        
        if 'max_year' in criteria and criteria['max_year']:
            filtered = [doc for doc in filtered 
                       if self._extract_year(doc.get('publication_date', '')) <= criteria['max_year']]
        
        # Filter by document type if specified
        if 'document_types' in criteria and criteria['document_types']:
            filtered = [doc for doc in filtered 
                       if doc.get('document_type', '').lower() in 
                       [dt.lower() for dt in criteria['document_types']]]
        
        # Filter by minimum abstract length if specified
        if 'min_abstract_length' in criteria and criteria['min_abstract_length']:
            filtered = [doc for doc in filtered 
                       if len(doc.get('abstract', '')) >= criteria['min_abstract_length']]
        
        return filtered
    
    def _extract_year(self, date_str: str) -> int:
        """Extract year from date string."""
        try:
            if not date_str:
                return 0
            
            # Try to extract year from various date formats
            import re
            year_match = re.search(r'\b(19|20)\d{2}\b', str(date_str))
            if year_match:
                return int(year_match.group())
            
            return 0
        except:
            return 0
    
    def paginate_documents(self, documents: List[Dict[str, Any]], 
                          page_size: int = None) -> Generator[List[Dict[str, Any]], None, None]:
        """Paginate documents for display."""
        if page_size is None:
            page_size = self.config.max_documents_display
        
        for i in range(0, len(documents), page_size):
            yield documents[i:i + page_size]
    
    def sort_documents(self, documents: List[Dict[str, Any]], 
                      sort_by: str = 'relevance') -> List[Dict[str, Any]]:
        """Sort documents by specified criteria."""
        if sort_by == 'date':
            return sorted(documents, 
                         key=lambda x: self._extract_year(x.get('publication_date', '')), 
                         reverse=True)
        elif sort_by == 'title':
            return sorted(documents, 
                         key=lambda x: x.get('title', '').lower())
        elif sort_by == 'authors':
            return sorted(documents, 
                         key=lambda x: ', '.join(x.get('authors', [])).lower())
        else:
            # Default to original order (relevance from search)
            return documents
    
    def get_document_statistics(self, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Get statistics about the document set."""
        if not documents:
            return {}
        
        stats = {
            'total_count': len(documents),
            'with_abstracts': len([d for d in documents if d.get('abstract')]),
            'with_pmid': len([d for d in documents if d.get('pmid')]),
            'unique_years': len(set(self._extract_year(d.get('publication_date', '')) 
                                  for d in documents if self._extract_year(d.get('publication_date', '')) > 0)),
            'year_range': self._get_year_range(documents),
            'avg_abstract_length': self._get_average_abstract_length(documents)
        }
        
        return stats
    
    def _get_year_range(self, documents: List[Dict[str, Any]]) -> tuple:
        """Get the year range of documents."""
        years = [self._extract_year(d.get('publication_date', '')) 
                for d in documents if self._extract_year(d.get('publication_date', '')) > 0]
        
        if years:
            return (min(years), max(years))
        return (None, None)
    
    def _get_average_abstract_length(self, documents: List[Dict[str, Any]]) -> float:
        """Get average abstract length."""
        abstracts = [d.get('abstract', '') for d in documents if d.get('abstract')]
        if abstracts:
            return sum(len(abstract) for abstract in abstracts) / len(abstracts)
        return 0.0