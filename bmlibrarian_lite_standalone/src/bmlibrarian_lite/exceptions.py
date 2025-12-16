"""
Custom exceptions for BMLibrarian Lite.

Provides a hierarchy of specific exception types for different failure modes,
enabling precise error handling and meaningful error messages.

Exception Hierarchy:
    LiteError (base)
    ├── LiteStorageError
    │   ├── ChromaDBError
    │   └── SQLiteError
    ├── EmbeddingError
    ├── ConfigurationError
    ├── NetworkError
    └── LLMError

Usage:
    from bmlibrarian_lite.exceptions import ChromaDBError, SQLiteError

    try:
        storage.add_document(doc)
    except ChromaDBError as e:
        logger.error(f"Vector storage failed: {e}")
    except SQLiteError as e:
        logger.error(f"Metadata storage failed: {e}")
"""


class LiteError(Exception):
    """
    Base exception for BMLibrarian Lite.

    All Lite-specific exceptions inherit from this class,
    allowing catch-all handling when needed.

    Example:
        try:
            do_something()
        except LiteError as e:
            logger.error(f"Lite operation failed: {e}")
    """

    pass


class LiteStorageError(LiteError):
    """
    Base exception for storage operations.

    Covers both ChromaDB and SQLite failures.
    Use more specific subclasses when the storage type is known.

    Example:
        try:
            storage.add_document(doc)
        except LiteStorageError as e:
            logger.error(f"Storage operation failed: {e}")
    """

    pass


class ChromaDBError(LiteStorageError):
    """
    ChromaDB-specific storage error.

    Raised when ChromaDB operations fail, including:
    - Collection creation/access
    - Document upsert/query/delete
    - Embedding storage

    Example:
        try:
            collection.upsert(ids=[doc_id], documents=[text])
        except chromadb.errors.ChromaError as e:
            raise ChromaDBError(f"Failed to upsert document: {e}") from e
    """

    pass


class SQLiteError(LiteStorageError):
    """
    SQLite-specific storage error.

    Raised when SQLite operations fail, including:
    - Connection errors
    - Query execution failures
    - Schema issues

    Example:
        try:
            conn.execute("INSERT INTO ...", values)
        except sqlite3.Error as e:
            raise SQLiteError(f"Database insert failed: {e}") from e
    """

    pass


class EmbeddingError(LiteError):
    """
    Embedding generation error.

    Raised when FastEmbed operations fail, including:
    - Model loading failures
    - Embedding generation timeouts
    - Out-of-memory errors

    Example:
        try:
            embeddings = embedder.embed(texts)
        except Exception as e:
            raise EmbeddingError(f"Embedding generation failed: {e}") from e
    """

    pass


class ConfigurationError(LiteError):
    """
    Configuration validation or loading error.

    Raised when configuration is invalid or cannot be loaded:
    - Invalid parameter values
    - Missing required fields
    - File read/write errors

    Example:
        errors = config.validate()
        if errors:
            raise ConfigurationError(f"Invalid configuration: {', '.join(errors)}")
    """

    pass


class NetworkError(LiteError):
    """
    Network operation error.

    Raised when network requests fail, including:
    - PubMed API errors
    - Connection timeouts
    - HTTP errors

    Example:
        try:
            response = client.search(query)
        except (ConnectionError, TimeoutError) as e:
            raise NetworkError(f"PubMed search failed: {e}") from e
    """

    pass


class LLMError(LiteError):
    """
    LLM API error.

    Raised when LLM operations fail, including:
    - API authentication errors
    - Rate limiting
    - Model errors
    - Response parsing failures

    Example:
        try:
            response = llm_client.chat(messages)
        except Exception as e:
            raise LLMError(f"LLM request failed: {e}") from e
    """

    pass


class RetryExhaustedError(NetworkError):
    """
    All retry attempts exhausted.

    Raised when an operation fails after all retry attempts.
    Contains information about the number of attempts and last error.

    Example:
        raise RetryExhaustedError(
            f"Operation failed after {max_retries} attempts",
            attempts=max_retries,
            last_error=last_exception
        )
    """

    def __init__(
        self,
        message: str,
        attempts: int = 0,
        last_error: Exception | None = None,
    ) -> None:
        """
        Initialize retry exhausted error.

        Args:
            message: Error message
            attempts: Number of retry attempts made
            last_error: The last exception that occurred
        """
        super().__init__(message)
        self.attempts = attempts
        self.last_error = last_error
