"""
Biomedical Query Agent for converting natural language questions to PostgreSQL to_tsquery format.

This module provides an LLM-powered agent that converts human language questions
into PostgreSQL to_tsquery compatible search queries optimized for biomedical
literature databases.
"""

import logging
import ollama


logger = logging.getLogger(__name__)


class QueryAgent:
    """
    Agent for converting natural language questions to PostgreSQL to_tsquery format.
    
    Uses Ollama to connect to a local LLM for intelligent keyword extraction
    and query composition tailored for biomedical literature searches.
    """
    
    def __init__(self, model: str = "medgemma4B_it_q8:latest", host: str = "http://localhost:11434"):
        """
        Initialize the QueryAgent.
        
        Args:
            model: The name of the Ollama model to use (default: medgemma4B_it_q8:latest)
            host: The Ollama server host URL (default: http://localhost:11434)
        """
        self.model = model
        self.host = host
        self.client = ollama.Client(host=host)
        
        # System prompt for biomedical query conversion
        self.system_prompt = """You are a biomedical literature search expert. Your task is to convert natural language questions into PostgreSQL to_tsquery format for searching biomedical publication abstracts.

Rules:
1. Extract the most relevant biomedical keywords from the user's question
2. Use '&' for AND operations (terms that should all appear)
3. Use '|' for OR operations (alternative terms)
4. Use parentheses to group related terms
5. Use multi-word phrases naturally (e.g., myocardial infarction, early diagnosis)
6. Focus on medical terminology, drug names, disease names, biological processes
7. Include both specific terms and broader category terms when relevant
8. Avoid common words like 'the', 'and', 'or', 'what', 'how'
9. Return ONLY the to_tsquery string, no explanation

Examples:
Question: "What are the effects of aspirin on cardiovascular disease?"
to_tsquery: "aspirin & (cardiovascular | cardiac | heart) & (disease | disorder | condition)"

Question: "How does diabetes affect kidney function?"
to_tsquery: "diabetes & (kidney | renal | nephro) & (function | dysfunction | disease)"

Question: "Studies on COVID-19 vaccine effectiveness"
to_tsquery: "(covid | coronavirus | sars-cov-2) & vaccine & (effectiveness | efficacy)"

Question: "Research on myocardial infarction and heart attacks"
to_tsquery: "(myocardial infarction | AMI | heart attack) & research"

Question: "Biomarkers for early Alzheimer's diagnosis"
to_tsquery: "(Alzheimer's disease | AD | early diagnosis | early detection) & (biomarker | marker | blood test | cerebrospinal fluid)"
"""

    def convert_question(self, question: str) -> str:
        """
        Convert a natural language question to PostgreSQL to_tsquery format.
        
        Args:
            question: The natural language question to convert
            
        Returns:
            A string formatted for PostgreSQL to_tsquery()
            
        Raises:
            ConnectionError: If unable to connect to Ollama
            ValueError: If the question is empty or invalid
        """
        if not question or not question.strip():
            raise ValueError("Question cannot be empty")
        
        try:
            response = self.client.chat(
                model=self.model,
                messages=[
                    {
                        'role': 'system',
                        'content': self.system_prompt
                    },
                    {
                        'role': 'user', 
                        'content': question
                    }
                ],
                options={
                    'temperature': 0.1,  # Low temperature for consistent results
                    'top_p': 0.9,
                    'num_predict': 100   # Limit response length
                }
            )
            
            query = response['message']['content'].strip()
            
            # Clean up quotation marks - convert double quotes to single quotes
            query = self._clean_quotes(query)
            
            # Basic validation of the generated query
            if not self._validate_tsquery(query):
                logger.warning(f"Generated query may be invalid: {query}")
            
            return query
            
        except ollama.ResponseError as e:
            logger.error(f"Ollama response error: {e}")
            raise ConnectionError(f"Failed to get response from Ollama: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in query conversion: {e}")
            raise
    
    def _clean_quotes(self, query: str) -> str:
        """
        Clean up and properly quote phrases in the query string.
        
        Detects multi-word phrases (words separated by spaces), escapes single quotes,
        and wraps phrases in single quotes for PostgreSQL to_tsquery compatibility.
        
        Args:
            query: The query string to clean
            
        Returns:
            The cleaned query string with properly quoted phrases
        """
        import re
        
        # First, escape all single quotes by doubling them
        query = query.replace("'", "''")
        
        # Find multi-word phrases - sequences of two or more words separated by spaces
        # that are not separated by operators (&, |) or parentheses
        def quote_phrase(match):
            phrase = match.group(0)
            return f"'{phrase}'"
        
        # Pattern to match multi-word phrases:
        # - Two or more words separated by spaces
        # - Not preceded/followed by operators or parentheses
        # - Words can contain letters, numbers, apostrophes, hyphens
        pattern = r'\b[a-zA-Z0-9\'\-]+(?:\s+[a-zA-Z0-9\'\-]+)+\b'
        
        query = re.sub(pattern, quote_phrase, query)
        
        return query
    
    def _validate_tsquery(self, query: str) -> bool:
        """
        Basic validation of to_tsquery format.
        
        Args:
            query: The query string to validate
            
        Returns:
            True if the query appears to be valid to_tsquery format
        """
        if not query:
            return False
            
        # Check for balanced parentheses
        if query.count('(') != query.count(')'):
            return False
            
        # Check for valid operators
        invalid_patterns = ['&&', '||', '&|', '|&']
        for pattern in invalid_patterns:
            if pattern in query:
                return False
        
        return True
    
    def test_connection(self) -> bool:
        """
        Test the connection to Ollama server.
        
        Returns:
            True if connection is successful, False otherwise
        """
        try:
            models = self.client.list()
            available_models = [model.model for model in models.models]
            
            if self.model not in available_models:
                logger.warning(f"Model {self.model} not found. Available models: {available_models}")
                return False
                
            logger.info(f"Successfully connected to Ollama. Model {self.model} is available.")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to Ollama: {e}")
            return False
    
    def get_available_models(self) -> list[str]:
        """
        Get list of available models from Ollama.
        
        Returns:
            List of available model names
            
        Raises:
            ConnectionError: If unable to connect to Ollama
        """
        try:
            models = self.client.list()
            return [model.model for model in models.models]
        except Exception as e:
            logger.error(f"Failed to get available models: {e}")
            raise ConnectionError(f"Failed to connect to Ollama: {e}")