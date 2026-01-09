"""
Contradictory Evidence Finder for Paper Reviewer

Searches for literature that questions or negates the paper's hypothesis.
Uses multi-strategy search: semantic, HyDE, keyword, and optional PubMed API.
"""

import json
import logging
import time
import xml.etree.ElementTree as ET
from typing import Dict, Any, Optional, Callable, List, Tuple

from ..base import BaseAgent
from ...config import get_model, get_agent_config, get_ollama_host
from ...database import get_db_manager
from .models import ContradictoryPaper, SearchMethod, SearchSource
from .constants import (
    MAX_TEXT_LENGTH,
    DEFAULT_TEMPERATURE_MODERATE,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MAX_TOKENS_SHORT,
    DEFAULT_SEMANTIC_SEARCH_LIMIT,
    DEFAULT_HYDE_SEARCH_LIMIT,
    DEFAULT_KEYWORD_SEARCH_LIMIT,
    DEFAULT_MAX_SEARCH_RESULTS,
    DEFAULT_PUBMED_SEARCH_LIMIT,
    MAX_PAPERS_TO_RERANK,
    ABSTRACT_PREVIEW_LENGTH,
    MAX_PAPERS_FOR_CITATION_EXTRACTION,
    PUBMED_ESEARCH_URL,
    PUBMED_EFETCH_URL,
    REQUEST_TIMEOUT,
    PUBMED_API_DELAY,
)

logger = logging.getLogger(__name__)


class ContradictoryEvidenceFinder(BaseAgent):
    """
    Finds literature that questions or negates the paper's hypothesis.

    Search strategy:
    1. Generate counter-statement from hypothesis (semantic negation)
    2. Generate HyDE abstract for counter-position
    3. Extract keywords from counter-statement
    4. Search local database with multiple strategies
    5. Optionally search PubMed API for external papers
    6. Cross-rerank all results by relevance to counter-statement
    """

    VERSION = "1.0.0"

    def __init__(
        self,
        model: Optional[str] = None,
        host: Optional[str] = None,
        temperature: float = DEFAULT_TEMPERATURE_MODERATE,
        top_p: float = 0.9,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        callback: Optional[Callable[[str, str], None]] = None,
        orchestrator: Optional[Any] = None,
        show_model_info: bool = True,
        ncbi_email: Optional[str] = None,
        ncbi_api_key: Optional[str] = None,
    ):
        """
        Initialize the ContradictoryEvidenceFinder.

        Args:
            model: LLM model name (default: from config)
            host: Ollama server host URL (default: from config)
            temperature: Model temperature (default: 0.3)
            top_p: Model top-p sampling parameter
            max_tokens: Maximum tokens for response
            callback: Optional callback for progress updates
            orchestrator: Optional orchestrator for queue-based processing
            show_model_info: Whether to display model information
            ncbi_email: Email for NCBI API (recommended)
            ncbi_api_key: NCBI API key for higher rate limits
        """
        # Get defaults from config if not provided
        if model is None:
            model = get_model('paper_reviewer')
        if host is None:
            host = get_ollama_host()

        super().__init__(
            model=model,
            host=host,
            temperature=temperature,
            top_p=top_p,
            callback=callback,
            orchestrator=orchestrator,
            show_model_info=show_model_info,
        )

        self.max_tokens = max_tokens
        self.ncbi_email = ncbi_email
        self.ncbi_api_key = ncbi_api_key

        # Search limits
        self.semantic_limit = DEFAULT_SEMANTIC_SEARCH_LIMIT
        self.hyde_limit = DEFAULT_HYDE_SEARCH_LIMIT
        self.keyword_limit = DEFAULT_KEYWORD_SEARCH_LIMIT
        self.max_results = DEFAULT_MAX_SEARCH_RESULTS
        self.pubmed_limit = DEFAULT_PUBMED_SEARCH_LIMIT

    def get_agent_type(self) -> str:
        """Get the agent type identifier."""
        return "contradictory_evidence_finder"

    def find_contradictory_evidence(
        self,
        hypothesis: str,
        document: Dict[str, Any],
        search_external: bool = True,
        max_results: Optional[int] = None,
    ) -> Tuple[str, List[ContradictoryPaper], List[str]]:
        """
        Find papers that may contradict the given hypothesis.

        Args:
            hypothesis: The core hypothesis to find contradictions for
            document: The original document (to exclude from results)
            search_external: Whether to search PubMed for external papers
            max_results: Maximum results to return (default: 20)

        Returns:
            Tuple of (counter_statement, contradictory_papers, search_sources_used)
        """
        if max_results is None:
            max_results = self.max_results

        self._call_callback("search_started", "Generating counter-statement")

        # Step 1: Generate counter-statement
        counter_statement = self.generate_counter_statement(hypothesis)
        logger.info(f"Generated counter-statement: {counter_statement[:100]}...")

        # Step 2: Generate HyDE materials
        self._call_callback("search_progress", "Generating HyDE abstract and keywords")
        hyde_abstract, keywords = self.generate_hyde_materials(counter_statement)

        # Step 3: Search local database
        self._call_callback("search_progress", "Searching local database")
        local_papers, local_sources = self._search_local(
            counter_statement=counter_statement,
            hyde_abstract=hyde_abstract,
            keywords=keywords,
            exclude_doc_id=document.get('id'),
        )
        logger.info(f"Found {len(local_papers)} papers in local database")

        # Step 4: Optionally search PubMed
        external_papers = []
        if search_external:
            self._call_callback("search_progress", "Searching PubMed for external papers")
            external_papers = self._search_pubmed(
                counter_statement=counter_statement,
                keywords=keywords,
                exclude_pmid=document.get('pmid'),
            )
            logger.info(f"Found {len(external_papers)} papers from PubMed")

        # Combine all papers
        all_papers = local_papers + external_papers

        # Step 5: Cross-rerank by relevance
        self._call_callback("search_progress", "Ranking papers by relevance")
        ranked_papers = self._rerank_by_relevance(all_papers, counter_statement, max_results)

        # Collect search sources used
        sources_used = list(local_sources)
        if search_external and external_papers:
            sources_used.append("pubmed")

        self._call_callback(
            "search_completed",
            f"Found {len(ranked_papers)} potentially contradicting papers"
        )

        return counter_statement, ranked_papers, sources_used

    def generate_counter_statement(self, hypothesis: str) -> str:
        """
        Generate semantic negation of the hypothesis.

        Args:
            hypothesis: The original hypothesis to negate

        Returns:
            Counter-statement that contradicts the hypothesis
        """
        prompt = f"""You are a scientific debate analyst. Generate a counter-statement that negates or contradicts the following hypothesis.

Original Hypothesis:
{hypothesis}

INSTRUCTIONS:
1. Create a clear statement that contradicts the original hypothesis
2. The counter-statement should be testable and searchable
3. Keep scientific terminology accurate
4. Phrase it as a positive claim (not just "the hypothesis is wrong")

Examples:
- If hypothesis is "Drug X reduces blood pressure" → "Drug X does not reduce blood pressure" or "Drug X may increase blood pressure"
- If hypothesis is "Exercise prevents heart disease" → "Exercise does not prevent heart disease" or "Exercise provides minimal cardiovascular benefit"
- If hypothesis is "Vitamin D deficiency causes depression" → "Vitamin D deficiency is not associated with depression" or "Vitamin D supplementation does not improve depression outcomes"

Response format (JSON only):
{{
    "counter_statement": "Your counter-statement here",
    "negation_type": "direct_negation|null_effect|opposite_effect|alternative_explanation"
}}

Respond ONLY with valid JSON."""

        try:
            result = self._generate_and_parse_json(
                prompt,
                max_retries=3,
                retry_context="counter-statement generation",
                num_predict=DEFAULT_MAX_TOKENS_SHORT,
            )
            return result.get('counter_statement', f"No effect: {hypothesis}")

        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to generate counter-statement: {e}")
            # Fallback: simple negation
            return f"Studies do not support: {hypothesis}"

    def generate_hyde_materials(
        self,
        counter_statement: str,
    ) -> Tuple[str, List[str]]:
        """
        Generate HyDE abstract and keywords for search.

        Args:
            counter_statement: The counter-statement to generate materials for

        Returns:
            Tuple of (hyde_abstract, keywords)
        """
        prompt = f"""You are a medical research librarian. Generate search materials for finding papers that support this claim:

Counter-Statement:
{counter_statement}

INSTRUCTIONS:
1. Generate a hypothetical abstract (150-200 words) for a paper that would support this counter-statement
2. Generate 5-10 keywords for traditional literature search
3. Keywords should include MeSH terms where appropriate

Response format (JSON only):
{{
    "hyde_abstract": "A hypothetical abstract that would support the counter-statement...",
    "keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"]
}}

Respond ONLY with valid JSON."""

        try:
            result = self._generate_and_parse_json(
                prompt,
                max_retries=3,
                retry_context="HyDE generation",
                num_predict=self.max_tokens,
            )
            hyde_abstract = result.get('hyde_abstract', counter_statement)
            keywords = result.get('keywords', [])
            return hyde_abstract, keywords

        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to generate HyDE materials: {e}")
            # Fallback: use counter-statement and extract simple keywords
            words = counter_statement.lower().split()
            keywords = [w for w in words if len(w) > 5][:5]
            return counter_statement, keywords

    def _search_local(
        self,
        counter_statement: str,
        hyde_abstract: str,
        keywords: List[str],
        exclude_doc_id: Optional[int] = None,
    ) -> Tuple[List[ContradictoryPaper], set]:
        """
        Search local database using multiple strategies.

        Args:
            counter_statement: Counter-statement for semantic search
            hyde_abstract: HyDE abstract for HyDE search
            keywords: Keywords for keyword search
            exclude_doc_id: Document ID to exclude (the paper being reviewed)

        Returns:
            Tuple of (list of ContradictoryPaper, set of sources used)
        """
        papers = []
        sources_used = set()

        db_manager = get_db_manager()

        # Strategy 1: Semantic search
        try:
            semantic_results = self._semantic_search(
                text=counter_statement,
                limit=self.semantic_limit,
                exclude_doc_id=exclude_doc_id,
            )
            for doc in semantic_results:
                papers.append(self._doc_to_contradictory_paper(
                    doc, SearchMethod.SEMANTIC, SearchSource.LOCAL
                ))
            sources_used.add("local_semantic")
            logger.debug(f"Semantic search found {len(semantic_results)} documents")
        except Exception as e:
            logger.warning(f"Semantic search failed: {e}")

        # Strategy 2: HyDE search (semantic with HyDE abstract)
        try:
            hyde_results = self._semantic_search(
                text=hyde_abstract,
                limit=self.hyde_limit,
                exclude_doc_id=exclude_doc_id,
            )
            for doc in hyde_results:
                if not any(p.document_id == doc.get('id') for p in papers):
                    papers.append(self._doc_to_contradictory_paper(
                        doc, SearchMethod.HYDE, SearchSource.LOCAL
                    ))
            sources_used.add("local_hyde")
            logger.debug(f"HyDE search found {len(hyde_results)} documents")
        except Exception as e:
            logger.warning(f"HyDE search failed: {e}")

        # Strategy 3: Keyword search
        try:
            keyword_results = self._keyword_search(
                keywords=keywords,
                limit=self.keyword_limit,
                exclude_doc_id=exclude_doc_id,
            )
            for doc in keyword_results:
                if not any(p.document_id == doc.get('id') for p in papers):
                    papers.append(self._doc_to_contradictory_paper(
                        doc, SearchMethod.KEYWORD, SearchSource.LOCAL
                    ))
            sources_used.add("local_keyword")
            logger.debug(f"Keyword search found {len(keyword_results)} documents")
        except Exception as e:
            logger.warning(f"Keyword search failed: {e}")

        return papers, sources_used

    def _semantic_search(
        self,
        text: str,
        limit: int,
        exclude_doc_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Perform semantic search using database's semantic_docsearch function.

        Args:
            text: Text to search for
            limit: Maximum results
            exclude_doc_id: Document ID to exclude

        Returns:
            List of document dictionaries with similarity scores
        """
        from psycopg.rows import dict_row

        db_manager = get_db_manager()

        # Default similarity threshold for finding contradictory evidence
        threshold = 0.5

        # Build query with optional exclusion filter
        # semantic_docsearch returns: chunk_id, document_id, score, doi, source_id,
        # external_id, title, publication_date, authors, abstract
        if exclude_doc_id is not None:
            query = """
                SELECT DISTINCT ON (sr.document_id)
                    sr.document_id as id, sr.score as similarity, sr.doi, sr.title,
                    sr.publication_date, sr.authors, sr.abstract,
                    s.name as source_name
                FROM semantic_docsearch(%s, %s, %s) sr
                LEFT JOIN sources s ON sr.source_id = s.id
                WHERE sr.document_id != %s
                ORDER BY sr.document_id, sr.score DESC
            """
            params = (text, threshold, limit * 2, exclude_doc_id)
        else:
            query = """
                SELECT DISTINCT ON (sr.document_id)
                    sr.document_id as id, sr.score as similarity, sr.doi, sr.title,
                    sr.publication_date, sr.authors, sr.abstract,
                    s.name as source_name
                FROM semantic_docsearch(%s, %s, %s) sr
                LEFT JOIN sources s ON sr.source_id = s.id
                ORDER BY sr.document_id, sr.score DESC
            """
            params = (text, threshold, limit * 2)

        with db_manager.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(query, params)
                results = [dict(row) for row in cur.fetchall()]
                # Sort by similarity and limit
                results.sort(key=lambda x: x.get('similarity', 0), reverse=True)
                return results[:limit]

    def _keyword_search(
        self,
        keywords: List[str],
        limit: int,
        exclude_doc_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Perform keyword search using PostgreSQL full-text search.

        Args:
            keywords: Keywords to search for
            limit: Maximum results
            exclude_doc_id: Document ID to exclude

        Returns:
            List of document dictionaries with rank scores
        """
        from psycopg.rows import dict_row

        if not keywords:
            return []

        db_manager = get_db_manager()

        # Build search query with OR operator
        search_query = " | ".join(keywords)

        # Build query with optional exclusion filter
        if exclude_doc_id is not None:
            query = """
                SELECT d.*, s.name as source_name,
                       ts_rank(d.search_vector, plainto_tsquery('english', %s)) as rank
                FROM document d
                LEFT JOIN sources s ON d.source_id = s.id
                WHERE d.search_vector @@ plainto_tsquery('english', %s)
                  AND d.id != %s
                ORDER BY rank DESC
                LIMIT %s
            """
            params = (search_query, search_query, exclude_doc_id, limit)
        else:
            query = """
                SELECT d.*, s.name as source_name,
                       ts_rank(d.search_vector, plainto_tsquery('english', %s)) as rank
                FROM document d
                LEFT JOIN sources s ON d.source_id = s.id
                WHERE d.search_vector @@ plainto_tsquery('english', %s)
                ORDER BY rank DESC
                LIMIT %s
            """
            params = (search_query, search_query, limit)

        with db_manager.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(query, params)
                return [dict(row) for row in cur.fetchall()]

    def _search_pubmed(
        self,
        counter_statement: str,
        keywords: List[str],
        exclude_pmid: Optional[str] = None,
    ) -> List[ContradictoryPaper]:
        """
        Search PubMed API for external papers.

        Args:
            counter_statement: Counter-statement for query construction
            keywords: Keywords to search for
            exclude_pmid: PMID to exclude

        Returns:
            List of ContradictoryPaper from PubMed
        """
        import requests
        import xml.etree.ElementTree as ET

        papers = []

        # Build search query from keywords
        query_terms = keywords[:5] if keywords else []
        if not query_terms:
            # Extract key terms from counter-statement
            words = counter_statement.split()
            query_terms = [w for w in words if len(w) > 5][:5]

        search_query = " AND ".join(query_terms)
        if not search_query:
            logger.warning("No search terms for PubMed search")
            return []

        # Search PubMed
        params = {
            'db': 'pubmed',
            'term': search_query,
            'retmax': self.pubmed_limit,
            'retmode': 'json',
        }
        if self.ncbi_email:
            params['email'] = self.ncbi_email
        if self.ncbi_api_key:
            params['api_key'] = self.ncbi_api_key

        try:
            response = requests.get(PUBMED_ESEARCH_URL, params=params, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()

            data = response.json()
            pmids = data.get('esearchresult', {}).get('idlist', [])

            if not pmids:
                return []

            # Filter out excluded PMID
            if exclude_pmid:
                pmids = [p for p in pmids if p != exclude_pmid]

            # Fetch article details
            fetch_params = {
                'db': 'pubmed',
                'id': ','.join(pmids[:self.pubmed_limit]),
                'retmode': 'xml',
            }
            if self.ncbi_email:
                fetch_params['email'] = self.ncbi_email
            if self.ncbi_api_key:
                fetch_params['api_key'] = self.ncbi_api_key

            time.sleep(PUBMED_API_DELAY)  # Rate limiting
            fetch_response = requests.get(PUBMED_EFETCH_URL, params=fetch_params, timeout=REQUEST_TIMEOUT)
            fetch_response.raise_for_status()

            # Parse XML
            root = ET.fromstring(fetch_response.content)
            for article in root.findall('.//PubmedArticle'):
                paper = self._parse_pubmed_article_to_paper(article)
                if paper:
                    papers.append(paper)

        except Exception as e:
            logger.error(f"PubMed search failed: {e}")

        return papers

    def _parse_pubmed_article_to_paper(
        self, article: ET.Element
    ) -> Optional[ContradictoryPaper]:
        """
        Parse PubMed XML article to ContradictoryPaper.

        Args:
            article: XML Element representing a PubMed article

        Returns:
            ContradictoryPaper if parsing successful, None otherwise
        """
        try:
            # PMID
            pmid_elem = article.find('.//PMID')
            pmid = pmid_elem.text if pmid_elem is not None else None

            # Title
            title_elem = article.find('.//ArticleTitle')
            title = self._get_element_text(title_elem) if title_elem is not None else 'Untitled'

            # Authors
            authors = []
            for author in article.findall('.//Author')[:5]:
                last_name = author.findtext('LastName', '')
                fore_name = author.findtext('ForeName', '')
                if last_name:
                    authors.append(f"{last_name} {fore_name}".strip())

            # Year
            year = None
            pub_date = article.find('.//PubDate')
            if pub_date is not None:
                year_elem = pub_date.find('Year')
                if year_elem is not None and year_elem.text:
                    year = int(year_elem.text)

            # Journal
            journal = article.findtext('.//Journal/Title', '')

            # DOI
            doi = None
            for id_elem in article.findall('.//ArticleId'):
                if id_elem.get('IdType') == 'doi':
                    doi = id_elem.text
                    break

            # Abstract
            abstract_parts = []
            for abstract_text in article.findall('.//AbstractText'):
                abstract_parts.append(self._get_element_text(abstract_text))
            abstract = ' '.join(abstract_parts)

            return ContradictoryPaper(
                document_id=None,
                pmid=pmid,
                doi=doi,
                title=title,
                authors=authors,
                year=year,
                journal=journal,
                abstract=abstract,
                relevance_score=0.5,  # Will be reranked later
                search_method=SearchMethod.PUBMED,
                source=SearchSource.EXTERNAL,
            )

        except Exception as e:
            logger.warning(f"Failed to parse PubMed article: {e}")
            return None

    def _get_element_text(self, elem: Optional[ET.Element]) -> str:
        """
        Get all text content from XML element, including nested elements.

        Args:
            elem: XML Element to extract text from, or None

        Returns:
            Concatenated text content from element and all children
        """
        if elem is None:
            return ''
        if not list(elem):
            return elem.text or ''
        text = elem.text or ''
        for child in elem:
            text += self._get_element_text(child)
            if child.tail:
                text += child.tail
        return text

    def _doc_to_contradictory_paper(
        self,
        doc: Dict[str, Any],
        search_method: SearchMethod,
        source: SearchSource,
    ) -> ContradictoryPaper:
        """Convert database document to ContradictoryPaper."""
        # Extract PMID from external_id
        pmid = None
        external_id = doc.get('external_id', '')
        if external_id:
            import re
            if external_id.isdigit():
                pmid = external_id
            elif 'pmid:' in external_id.lower():
                match = re.search(r'pmid:(\d+)', external_id.lower())
                if match:
                    pmid = match.group(1)

        # Parse authors
        authors = doc.get('authors', [])
        if isinstance(authors, str):
            authors = [a.strip() for a in authors.split(',')]

        # Extract year from publication_date
        year = None
        pub_date = doc.get('publication_date')
        if pub_date:
            if hasattr(pub_date, 'year'):
                year = pub_date.year
            elif isinstance(pub_date, str):
                import re
                match = re.search(r'(\d{4})', pub_date)
                if match:
                    year = int(match.group(1))

        return ContradictoryPaper(
            document_id=doc.get('id'),
            pmid=pmid,
            doi=doc.get('doi'),
            title=doc.get('title', 'Untitled'),
            authors=authors,
            year=year,
            journal=doc.get('journal'),
            abstract=doc.get('abstract', ''),
            relevance_score=float(doc.get('similarity', 0.5)),
            search_method=search_method,
            source=source,
        )

    def _rerank_by_relevance(
        self,
        papers: List[ContradictoryPaper],
        counter_statement: str,
        max_results: int,
    ) -> List[ContradictoryPaper]:
        """
        Rerank papers by relevance to counter-statement using LLM.

        Args:
            papers: List of papers to rerank
            counter_statement: Counter-statement for relevance scoring
            max_results: Maximum results to return

        Returns:
            List of papers sorted by relevance score
        """
        if not papers:
            return []

        # Limit papers to process (LLM context limit)
        papers_to_rank = papers[:MAX_PAPERS_TO_RERANK]
        if len(papers) > MAX_PAPERS_TO_RERANK:
            logger.info(
                f"Limiting reranking to {MAX_PAPERS_TO_RERANK} papers "
                f"(from {len(papers)} total)"
            )

        # Build paper summaries for ranking
        paper_summaries = []
        for i, paper in enumerate(papers_to_rank):
            summary = f"{i+1}. {paper.title}"
            if paper.abstract:
                summary += f" - {paper.abstract[:ABSTRACT_PREVIEW_LENGTH]}..."
            paper_summaries.append(summary)

        summaries_text = "\n".join(paper_summaries)

        prompt = f"""You are a medical research analyst. Score how relevant each paper is to contradicting or questioning this statement:

Counter-Statement: {counter_statement}

Papers to evaluate:
{summaries_text}

INSTRUCTIONS:
1. For each paper, assign a relevance score from 0.0 to 1.0
2. 1.0 = Directly contradicts or questions the statement
3. 0.7-0.9 = Related evidence that may contradict
4. 0.4-0.6 = Tangentially related
5. 0.0-0.3 = Not relevant

Response format (JSON only):
{{
    "scores": [
        {{"paper_index": 1, "score": 0.85, "reason": "Brief reason"}},
        {{"paper_index": 2, "score": 0.6, "reason": "Brief reason"}}
    ]
}}

Respond ONLY with valid JSON. Include all papers."""

        try:
            result = self._generate_and_parse_json(
                prompt,
                max_retries=2,
                retry_context="relevance ranking",
                num_predict=self.max_tokens,
            )

            # Apply scores to papers
            scores = result.get('scores', [])
            score_map = {s['paper_index']: (s['score'], s.get('reason', '')) for s in scores}

            for i, paper in enumerate(papers_to_rank):
                if (i + 1) in score_map:
                    paper.relevance_score = float(score_map[i + 1][0])
                    paper.contradiction_explanation = score_map[i + 1][1]

        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to rerank papers: {e}")
            # Keep original scores

        # Sort by relevance score and return top results
        papers_to_rank.sort(key=lambda p: p.relevance_score, reverse=True)
        top_papers = papers_to_rank[:max_results]

        # Extract contradictory citations from top papers
        self._extract_contradictory_citations(top_papers, counter_statement)

        return top_papers

    def _extract_contradictory_citations(
        self,
        papers: List[ContradictoryPaper],
        counter_statement: str,
    ) -> None:
        """
        Extract specific contradictory excerpts from each paper's abstract.

        For papers where no contradictory evidence is found in the abstract,
        sets contradictory_excerpt to None and updates explanation accordingly.

        Args:
            papers: List of papers to extract citations from (modified in place)
            counter_statement: The counter-statement to find evidence for
        """
        if not papers:
            return

        # Limit to avoid excessive LLM calls
        papers_to_process = papers[:MAX_PAPERS_FOR_CITATION_EXTRACTION]

        self._call_callback(
            "citation_extraction",
            f"Extracting contradictory citations from {len(papers_to_process)} papers"
        )

        for paper in papers_to_process:
            if not paper.abstract:
                paper.contradictory_excerpt = None
                paper.contradiction_explanation = "No abstract available for citation extraction"
                continue

            prompt = f"""You are a scientific citation analyst. Your task is to find the specific part of this abstract that contradicts or questions the following statement.

Counter-Statement (what we're looking for evidence of):
{counter_statement}

Paper Title: {paper.title}

Abstract:
{paper.abstract}

INSTRUCTIONS:
1. Search the abstract for specific sentences or claims that contradict, question, or provide evidence against the counter-statement
2. If you find contradictory evidence, extract the exact quote (verbatim) from the abstract
3. If the abstract does NOT contain any contradictory evidence, clearly indicate this
4. Be conservative - only extract text that directly contradicts or questions the statement

Response format (JSON only):
{{
    "has_contradictory_evidence": true/false,
    "contradictory_excerpt": "Exact quote from abstract if found, null if not found",
    "explanation": "Brief explanation of why this excerpt contradicts the statement, or why no contradictory evidence was found"
}}

Respond ONLY with valid JSON."""

            try:
                result = self._generate_and_parse_json(
                    prompt,
                    max_retries=2,
                    retry_context="citation extraction",
                    num_predict=DEFAULT_MAX_TOKENS_SHORT,
                )

                has_evidence = result.get('has_contradictory_evidence', False)
                excerpt = result.get('contradictory_excerpt')
                explanation = result.get('explanation', '')

                if has_evidence and excerpt:
                    paper.contradictory_excerpt = excerpt
                    paper.contradiction_explanation = explanation
                else:
                    paper.contradictory_excerpt = None
                    paper.contradiction_explanation = (
                        explanation if explanation
                        else "No contradictory evidence found in this paper's abstract"
                    )

            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Failed to extract citation from {paper.title}: {e}")
                paper.contradictory_excerpt = None
                paper.contradiction_explanation = "Citation extraction failed"

        # For papers beyond the extraction limit, set a default message
        for paper in papers[MAX_PAPERS_FOR_CITATION_EXTRACTION:]:
            if not paper.contradictory_excerpt:
                paper.contradiction_explanation = (
                    paper.contradiction_explanation or
                    "Citation not extracted (paper beyond extraction limit)"
                )


__all__ = ['ContradictoryEvidenceFinder']
