"""
Lite document interrogation agent for Q&A.

This agent enables interactive question-answering sessions with documents.
Documents are chunked, embedded, and stored for semantic retrieval.
"""

import logging
from typing import Optional

from ..storage import LiteStorage
from ..config import LiteConfig
from ..data_models import DocumentChunk
from ..chunking import chunk_document_for_interrogation
from ..chroma_embeddings import create_embedding_function, FastEmbedFunction
from .base import LiteBaseAgent

logger = logging.getLogger(__name__)

# System prompt for document Q&A
INTERROGATION_SYSTEM_PROMPT = """You are a helpful research assistant answering questions about a document.

Guidelines:
1. Answer based ONLY on the provided context from the document
2. If the context doesn't contain the answer, say so clearly
3. Quote relevant passages when appropriate
4. Be concise but thorough
5. If asked about something not in the context, acknowledge this limitation
6. Do not make up information not present in the provided context

Important: Your answers must be grounded in the document content provided. If the context is insufficient to answer the question, say "The provided context does not contain information about this topic." """


class LiteInterrogationAgent(LiteBaseAgent):
    """
    Document interrogation agent for Q&A sessions.

    Chunks documents, embeds them, and answers questions using
    semantic retrieval + LLM generation (RAG pattern).

    This agent:
    1. Loads and chunks documents
    2. Stores chunks with embeddings in ChromaDB
    3. Retrieves relevant chunks for questions
    4. Generates answers using LLM

    Attributes:
        storage: LiteStorage instance
    """

    # Collection name for document chunks
    CHUNKS_COLLECTION = "document_chunks"

    def __init__(
        self,
        storage: Optional[LiteStorage] = None,
        config: Optional[LiteConfig] = None,
        **kwargs,
    ) -> None:
        """
        Initialize the interrogation agent.

        Args:
            storage: LiteStorage instance
            config: Lite configuration
            **kwargs: Additional arguments for base agent
        """
        super().__init__(config=config, **kwargs)
        self.storage = storage or LiteStorage(self.config)

        # Embedding function (lazy initialization)
        self._embed_fn: Optional[FastEmbedFunction] = None

        # Current document being interrogated
        self._current_document_id: Optional[str] = None
        self._current_document_title: Optional[str] = None

    @property
    def embed_fn(self) -> FastEmbedFunction:
        """Get or create embedding function."""
        if self._embed_fn is None:
            self._embed_fn = create_embedding_function(
                model_name=self.config.embeddings.model
            )
        return self._embed_fn

    def load_document(
        self,
        text: str,
        document_id: Optional[str] = None,
        title: str = "Untitled Document",
    ) -> str:
        """
        Load and chunk a document for interrogation.

        Args:
            text: Document text content
            document_id: Optional document ID (generated if not provided)
            title: Document title for display

        Returns:
            Document ID

        Raises:
            ValueError: If document produces no chunks
        """
        # Chunk the document
        chunks = chunk_document_for_interrogation(
            text=text,
            document_id=document_id,
            title=title,
            chunk_size=self.config.search.chunk_size,
            chunk_overlap=self.config.search.chunk_overlap,
        )

        if not chunks:
            raise ValueError("Document produced no chunks - text may be too short")

        # Get or create chunks collection
        collection = self.storage.get_chunks_collection(self.embed_fn)

        # Upsert chunks to ChromaDB
        collection.upsert(
            ids=[c.id for c in chunks],
            documents=[c.text for c in chunks],
            metadatas=[{
                "document_id": c.document_id,
                "chunk_index": c.chunk_index,
                "title": title,
                "start_char": c.start_char,
                "end_char": c.end_char,
            } for c in chunks],
        )

        self._current_document_id = chunks[0].document_id
        self._current_document_title = title

        logger.info(f"Loaded document '{title}' with {len(chunks)} chunks")
        return self._current_document_id

    def ask(
        self,
        question: str,
        document_id: Optional[str] = None,
        n_context_chunks: int = 5,
    ) -> tuple[str, list[str]]:
        """
        Ask a question about the loaded document.

        Args:
            question: Question to ask
            document_id: Optional document ID (uses current if not provided)
            n_context_chunks: Number of context chunks to retrieve

        Returns:
            Tuple of (answer, list of source passages)

        Raises:
            ValueError: If no document is loaded
        """
        doc_id = document_id or self._current_document_id
        if not doc_id:
            raise ValueError("No document loaded. Call load_document() first.")

        # Retrieve relevant chunks
        collection = self.storage.get_chunks_collection(self.embed_fn)

        results = collection.query(
            query_texts=[question],
            n_results=n_context_chunks,
            where={"document_id": doc_id},
            include=["documents", "metadatas"],
        )

        if not results["documents"][0]:
            return "No relevant content found in the document.", []

        # Build context from retrieved chunks
        context_chunks = results["documents"][0]
        context = "\n\n---\n\n".join(context_chunks)

        # Generate answer
        user_prompt = f"""Context from the document:

{context}

---

Question: {question}

Answer the question based on the context above. If the context doesn't contain sufficient information to answer, say so clearly."""

        messages = [
            self._create_system_message(INTERROGATION_SYSTEM_PROMPT),
            self._create_user_message(user_prompt),
        ]

        answer = self._chat(messages, temperature=0.2)

        return answer, context_chunks

    def get_document_summary(
        self,
        document_id: Optional[str] = None,
        n_chunks: int = 3,
    ) -> str:
        """
        Generate a summary of the loaded document.

        Args:
            document_id: Optional document ID (uses current if not provided)
            n_chunks: Number of beginning chunks to use for summary

        Returns:
            Document summary

        Raises:
            ValueError: If no document is loaded
        """
        doc_id = document_id or self._current_document_id
        if not doc_id:
            raise ValueError("No document loaded. Call load_document() first.")

        # Get first N chunks (usually beginning of document)
        collection = self.storage.get_chunks_collection(self.embed_fn)

        results = collection.get(
            where={"document_id": doc_id},
            include=["documents", "metadatas"],
        )

        if not results["documents"]:
            return "No document content available."

        # Sort by chunk index and get first N
        chunks_with_idx = list(zip(results["documents"], results["metadatas"]))
        chunks_with_idx.sort(key=lambda x: x[1].get("chunk_index", 0))
        first_chunks = [c[0] for c in chunks_with_idx[:n_chunks]]

        context = "\n\n".join(first_chunks)

        user_prompt = f"""Document content (beginning):

{context}

Provide a brief summary of what this document appears to be about. Include the main topics or themes."""

        messages = [
            self._create_system_message(
                "You are a helpful assistant that summarizes documents concisely."
            ),
            self._create_user_message(user_prompt),
        ]

        return self._chat(messages, temperature=0.2, max_tokens=500)

    def clear_document(self, document_id: Optional[str] = None) -> None:
        """
        Clear a document's chunks from storage.

        Args:
            document_id: Document ID to clear (uses current if not provided)
        """
        doc_id = document_id or self._current_document_id
        if not doc_id:
            return

        collection = self.storage.get_chunks_collection(self.embed_fn)

        # Get all chunk IDs for this document
        results = collection.get(
            where={"document_id": doc_id},
            include=[],
        )

        if results["ids"]:
            collection.delete(ids=results["ids"])
            logger.info(f"Cleared {len(results['ids'])} chunks for document {doc_id}")

        if doc_id == self._current_document_id:
            self._current_document_id = None
            self._current_document_title = None

    def get_current_document_info(self) -> Optional[dict]:
        """
        Get information about the currently loaded document.

        Returns:
            Dictionary with document info, or None if no document loaded
        """
        if not self._current_document_id:
            return None

        collection = self.storage.get_chunks_collection(self.embed_fn)

        results = collection.get(
            where={"document_id": self._current_document_id},
            include=["metadatas"],
        )

        return {
            "document_id": self._current_document_id,
            "title": self._current_document_title,
            "chunk_count": len(results["ids"]) if results["ids"] else 0,
        }

    def list_loaded_documents(self) -> list[dict]:
        """
        List all documents that have been loaded.

        Returns:
            List of document info dictionaries
        """
        collection = self.storage.get_chunks_collection(self.embed_fn)

        # Get all unique document IDs
        results = collection.get(include=["metadatas"])

        if not results["metadatas"]:
            return []

        # Group by document_id
        documents: dict[str, dict] = {}
        for metadata in results["metadatas"]:
            doc_id = metadata.get("document_id", "unknown")
            if doc_id not in documents:
                documents[doc_id] = {
                    "document_id": doc_id,
                    "title": metadata.get("title", "Unknown"),
                    "chunk_count": 0,
                }
            documents[doc_id]["chunk_count"] += 1

        return list(documents.values())
