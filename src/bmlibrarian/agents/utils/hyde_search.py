"""
HyDE (Hypothetical Document Embeddings) Search Implementation

This module implements HyDE search for improved semantic retrieval.
Instead of directly embedding the user's question, HyDE:
1. Generates hypothetical documents that would answer the question
2. Embeds these hypothetical documents
3. Searches for similar real documents in the database
4. Fuses results using Reciprocal Rank Fusion (RRF)

This approach often yields better results because hypothetical documents
are more similar to the actual documents in the database than raw questions.
"""

import os
import logging
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict
import psycopg

logger = logging.getLogger(__name__)


def generate_hypothetical_documents(
    question: str,
    client: Any,  # ollama.Client
    model: str,
    num_docs: int = 3,
    temperature: float = 0.3,
    callback: Optional[callable] = None
) -> List[str]:
    """
    Generate hypothetical biomedical documents that would answer the question.

    Args:
        question: The user's research question
        client: Ollama client instance
        model: Model name for generation (e.g., medgemma-27b-text-it-Q8_0:latest)
        num_docs: Number of hypothetical documents to generate
        temperature: Temperature for generation (higher = more diversity)
        callback: Optional callback for progress updates

    Returns:
        List of hypothetical document strings (abstracts)

    Example:
        >>> docs = generate_hypothetical_documents(
        ...     "What are the effects of aspirin on cardiovascular disease?",
        ...     client, "medgemma-27b-text-it-Q8_0:latest", num_docs=3
        ... )
        >>> len(docs)
        3
    """
    if callback:
        callback("hyde_generation", f"Generating {num_docs} hypothetical documents...")

    system_prompt = """You are a medical research expert. Generate realistic biomedical research abstracts that would answer the user's question.

Write as if you are the abstract of a real published research paper. Include:
- Study design and methods
- Key findings
- Clinical implications
- Specific numerical results when appropriate

Write in the style of PubMed abstracts: concise, technical, and evidence-based.
Do NOT include titles, author names, or metadata - only the abstract text.
"""

    hypothetical_docs = []

    for i in range(num_docs):
        try:
            # Vary the prompt slightly for diversity
            if i == 0:
                prompt = f"Write a research abstract that answers this question: {question}"
            elif i == 1:
                prompt = f"Write a clinical study abstract addressing this topic: {question}"
            else:
                prompt = f"Write a scientific abstract with findings relevant to: {question}"

            response = client.generate(
                model=model,
                prompt=prompt,
                system=system_prompt,
                options={
                    'temperature': temperature,
                    'num_predict': 300  # Typical abstract length
                }
            )

            hypothetical_doc = response['response'].strip()

            if hypothetical_doc:
                hypothetical_docs.append(hypothetical_doc)
                logger.info(f"Generated hypothetical document {i+1}/{num_docs} ({len(hypothetical_doc)} chars)")
                if callback:
                    callback("hyde_generation", f"Generated document {i+1}/{num_docs}")
            else:
                logger.warning(f"Empty hypothetical document {i+1}, skipping")

        except Exception as e:
            logger.error(f"Failed to generate hypothetical document {i+1}: {e}")
            if callback:
                callback("hyde_generation", f"Error generating document {i+1}: {e}")
            # Continue with other documents

    if not hypothetical_docs:
        raise ValueError("Failed to generate any hypothetical documents")

    logger.info(f"Successfully generated {len(hypothetical_docs)} hypothetical documents")
    return hypothetical_docs


def embed_documents(
    documents: List[str],
    client: Any,  # ollama.Client
    embedding_model: str,
    callback: Optional[callable] = None
) -> List[List[float]]:
    """
    Generate embeddings for multiple documents.

    Args:
        documents: List of text documents to embed
        client: Ollama client instance
        embedding_model: Embedding model name (e.g., nomic-embed-text:latest)
        callback: Optional callback for progress updates

    Returns:
        List of embedding vectors (one per document)

    Raises:
        ConnectionError: If unable to connect to Ollama
        ValueError: If embedding fails
    """
    if callback:
        callback("hyde_embedding", f"Generating embeddings for {len(documents)} documents...")

    embeddings = []

    for i, doc in enumerate(documents):
        try:
            response = client.embeddings(
                model=embedding_model,
                prompt=doc
            )

            embedding = response['embedding']
            if not embedding:
                raise ValueError(f"Empty embedding for document {i+1}")

            embeddings.append(embedding)
            logger.info(f"Generated embedding {i+1}/{len(documents)} (dim={len(embedding)})")

            if callback:
                callback("hyde_embedding", f"Embedded document {i+1}/{len(documents)}")

        except Exception as e:
            logger.error(f"Failed to embed document {i+1}: {e}")
            raise ConnectionError(f"Failed to generate embedding: {e}")

    return embeddings


def search_with_embedding(
    embedding: List[float],
    max_results: int,
    db_params: Dict[str, Any]
) -> List[Tuple[int, str, float]]:
    """
    Search database using a single embedding vector.

    Args:
        embedding: The query embedding vector
        max_results: Maximum number of results to return
        db_params: Database connection parameters

    Returns:
        List of (document_id, title, similarity_score) tuples

    Example:
        >>> results = search_with_embedding(
        ...     embedding=[0.1, 0.2, ...],
        ...     max_results=100,
        ...     db_params={'dbname': 'knowledgebase', ...}
        ... )
    """
    with psycopg.connect(**db_params) as conn:
        with conn.cursor() as cur:
            # Cosine similarity search using pgvector
            # <=> is cosine distance operator, so 1 - distance = similarity
            sql = """
                SELECT DISTINCT c.document_id,
                       d.title,
                       1 - (e.embedding <=> %s::vector) AS similarity
                FROM emb_1024 e
                JOIN chunks c ON e.chunk_id = c.id
                JOIN document d ON c.document_id = d.id
                WHERE e.model_id = 1
                ORDER BY e.embedding <=> %s::vector
                LIMIT %s
            """

            cur.execute(sql, (embedding, embedding, max_results))
            results = cur.fetchall()

    return results


def reciprocal_rank_fusion(
    ranked_lists: List[List[Tuple[int, str, float]]],
    k: int = 60
) -> List[Tuple[int, str, float]]:
    """
    Fuse multiple ranked result lists using Reciprocal Rank Fusion (RRF).

    RRF is a simple but effective ranking algorithm that combines multiple
    ranked lists by assigning scores based on rank position:
    score(doc) = sum(1 / (k + rank_i)) for all lists where doc appears

    Args:
        ranked_lists: List of ranked result lists, each containing
                     (document_id, title, similarity_score) tuples
        k: Constant for RRF formula (default: 60, as used in literature)

    Returns:
        Fused and re-ranked list of (document_id, title, rrf_score) tuples

    Reference:
        Cormack, G. V., Clarke, C. L., & Buettcher, S. (2009).
        "Reciprocal rank fusion outperforms condorcet and individual rank
        learning methods." SIGIR 2009.
    """
    rrf_scores = defaultdict(float)
    doc_titles = {}  # Track document titles

    for result_list in ranked_lists:
        for rank, (doc_id, title, _similarity) in enumerate(result_list, start=1):
            rrf_scores[doc_id] += 1.0 / (k + rank)
            doc_titles[doc_id] = title  # Keep title for final results

    # Sort by RRF score (descending)
    fused_results = [
        (doc_id, doc_titles[doc_id], score)
        for doc_id, score in sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    ]

    return fused_results


def hyde_search(
    question: str,
    client: Any,  # ollama.Client
    generation_model: str,
    embedding_model: str,
    max_results: int = 100,
    num_hypothetical_docs: int = 3,
    similarity_threshold: float = 0.7,
    callback: Optional[callable] = None
) -> List[Dict[str, Any]]:
    """
    Perform HyDE (Hypothetical Document Embeddings) search.

    Main entry point for HyDE search. Orchestrates the full pipeline:
    1. Generate hypothetical documents
    2. Embed hypothetical documents
    3. Search with each embedding
    4. Fuse results using RRF
    5. Filter by similarity threshold

    Args:
        question: The user's research question
        client: Ollama client instance
        generation_model: Model for generating hypothetical docs
        embedding_model: Model for generating embeddings
        max_results: Maximum documents to return
        num_hypothetical_docs: Number of hypothetical documents to generate
        similarity_threshold: Minimum RRF score threshold (0-1)
        callback: Optional callback for progress updates

    Returns:
        List of document dictionaries with keys: id, title, score

    Example:
        >>> import ollama
        >>> client = ollama.Client(host="http://localhost:11434")
        >>> results = hyde_search(
        ...     "What are the cardiovascular benefits of exercise?",
        ...     client=client,
        ...     generation_model="medgemma-27b-text-it-Q8_0:latest",
        ...     embedding_model="nomic-embed-text:latest",
        ...     max_results=100,
        ...     num_hypothetical_docs=3
        ... )
    """
    # Database connection parameters
    db_params = {
        "dbname": os.getenv("POSTGRES_DB", "knowledgebase"),
        "user": os.getenv("POSTGRES_USER"),
        "password": os.getenv("POSTGRES_PASSWORD"),
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": os.getenv("POSTGRES_PORT", "5432")
    }

    if callback:
        callback("hyde_search", f"Starting HyDE search with {num_hypothetical_docs} hypothetical documents")

    # Step 1: Generate hypothetical documents
    logger.info(f"Generating {num_hypothetical_docs} hypothetical documents...")
    hypothetical_docs = generate_hypothetical_documents(
        question=question,
        client=client,
        model=generation_model,
        num_docs=num_hypothetical_docs,
        temperature=0.3,
        callback=callback
    )

    # Step 2: Generate embeddings for hypothetical documents
    logger.info(f"Generating embeddings for {len(hypothetical_docs)} documents...")
    embeddings = embed_documents(
        documents=hypothetical_docs,
        client=client,
        embedding_model=embedding_model,
        callback=callback
    )

    # Step 3: Search with each embedding
    logger.info(f"Searching database with {len(embeddings)} embeddings...")
    if callback:
        callback("hyde_search", f"Searching with {len(embeddings)} embeddings...")

    all_results = []
    for i, embedding in enumerate(embeddings):
        results = search_with_embedding(
            embedding=embedding,
            max_results=max_results,
            db_params=db_params
        )
        all_results.append(results)
        logger.info(f"Search {i+1}/{len(embeddings)}: found {len(results)} documents")

    # Step 4: Fuse results using RRF
    logger.info("Fusing results with Reciprocal Rank Fusion...")
    if callback:
        callback("hyde_search", "Fusing results with RRF...")

    fused_results = reciprocal_rank_fusion(all_results, k=60)

    # Step 5: Filter and format results
    # Normalize RRF scores to 0-1 range for threshold filtering
    if fused_results:
        max_score = fused_results[0][2]  # Highest RRF score
        min_score = fused_results[-1][2]  # Lowest RRF score
        score_range = max_score - min_score if max_score > min_score else 1.0

        filtered_results = []
        for doc_id, title, rrf_score in fused_results[:max_results]:
            # Normalize score to 0-1
            normalized_score = (rrf_score - min_score) / score_range if score_range > 0 else 1.0

            if normalized_score >= similarity_threshold:
                filtered_results.append({
                    'id': doc_id,
                    'title': title,
                    'score': normalized_score,
                    'rrf_score': rrf_score
                })

        logger.info(f"HyDE search complete: {len(filtered_results)} results above threshold {similarity_threshold}")
        if callback:
            callback("hyde_search", f"Found {len(filtered_results)} documents above threshold")

        return filtered_results
    else:
        logger.warning("No results from HyDE search")
        return []
