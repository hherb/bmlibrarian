# Embeddings Configuration Guide

This guide explains how to configure the embedding system in BMLibrarian for generating document embeddings used in semantic search and document chunking.

## Overview

BMLibrarian supports multiple backends for generating text embeddings:

| Backend | Description | Stability | Speed | Setup |
|---------|-------------|-----------|-------|-------|
| `sentence_transformers` | Uses HuggingFace sentence-transformers | **Excellent** | Fast | Easy |
| `ollama` | Uses Ollama Python library | Variable | Fast | Requires Ollama |
| `ollama_http` | Raw HTTP requests to Ollama | Good | Fast | Requires Ollama |
| `llama_cpp` | Direct GGUF model inference | Excellent | Medium | Requires model file |

**Recommendation**: Use `sentence_transformers` for production workloads. It handles larger text chunks reliably and doesn't depend on external services.

## Configuration

### Configuration File Location

Settings are stored in `~/.bmlibrarian/config.json` under the `embeddings` section.

### Default Configuration

```json
{
  "embeddings": {
    "backend": "sentence_transformers",
    "model": "snowflake-arctic-embed2:latest",
    "huggingface_model": "Snowflake/snowflake-arctic-embed-l-v2.0",
    "batch_size": 32,
    "n_ctx": 8192,
    "device": "auto"
  }
}
```

### Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `backend` | string | `"sentence_transformers"` | Embedding backend to use |
| `model` | string | `"snowflake-arctic-embed2:latest"` | Model name (Ollama-style) |
| `huggingface_model` | string | `"Snowflake/snowflake-arctic-embed-l-v2.0"` | HuggingFace model ID |
| `batch_size` | int | `32` | Batch size for embedding generation |
| `n_ctx` | int | `8192` | Context window size (llama_cpp only) |
| `device` | string | `"auto"` | Device for sentence_transformers |

### Device Options (sentence_transformers)

- `"auto"` - Automatically select best available device
- `"cpu"` - Force CPU usage
- `"cuda"` - Use NVIDIA GPU (requires CUDA)
- `"mps"` - Use Apple Silicon GPU (macOS)

## Backend-Specific Configuration

### sentence_transformers (Recommended)

Best for stability and handling larger text chunks.

```json
{
  "embeddings": {
    "backend": "sentence_transformers",
    "huggingface_model": "Snowflake/snowflake-arctic-embed-l-v2.0",
    "device": "auto"
  }
}
```

**Supported Models**:
- `Snowflake/snowflake-arctic-embed-l-v2.0` (recommended, 1024 dimensions)
- `sentence-transformers/all-MiniLM-L6-v2` (smaller, 384 dimensions)
- Any HuggingFace sentence-transformers compatible model

### ollama

Uses the Ollama Python library. Can be unstable with larger text chunks.

```json
{
  "embeddings": {
    "backend": "ollama",
    "model": "snowflake-arctic-embed2:latest"
  }
}
```

**Requirements**: Ollama server running on `http://localhost:11434`

### ollama_http

Uses raw HTTP requests to Ollama. More stable than the Python library.

```json
{
  "embeddings": {
    "backend": "ollama_http",
    "model": "snowflake-arctic-embed2:latest"
  }
}
```

### llama_cpp

Direct GGUF model inference without external dependencies.

```json
{
  "embeddings": {
    "backend": "llama_cpp",
    "model": "snowflake-arctic-embed2:latest",
    "n_ctx": 8192
  }
}
```

**Note**: Will automatically find Ollama's cached model file, or you can specify `model_path` programmatically.

## Troubleshooting

### Ollama EOF Errors

If you see errors like:
```
do embedding request: Post "http://127.0.0.1:58048/embedding": EOF (status code: 500)
```

This indicates Ollama is crashing when processing larger text chunks. **Solution**: Switch to `sentence_transformers` backend.

### Model Download

For `sentence_transformers`, models are automatically downloaded from HuggingFace on first use. This may take a few minutes for larger models.

### Memory Issues

If you encounter out-of-memory errors:

1. Reduce `batch_size` to `16` or `8`
2. Use a smaller model
3. Set `device` to `"cpu"` to avoid GPU memory limits

### Verifying Configuration

Test your configuration:

```bash
uv run python -c "
from bmlibrarian.embeddings.chunk_embedder import ChunkEmbedder
from bmlibrarian.config import get_embeddings_config

config = get_embeddings_config()
print(f'Backend: {config[\"backend\"]}')

embedder = ChunkEmbedder()
result = embedder.create_embedding('Test sentence.')
print(f'Embedding dimension: {len(result)}')
print('Configuration working!')
"
```

## Migration from Ollama

If you were using Ollama and want to switch to sentence_transformers:

1. Edit `~/.bmlibrarian/config.json`
2. Add or modify the `embeddings` section:

```json
{
  "embeddings": {
    "backend": "sentence_transformers",
    "huggingface_model": "Snowflake/snowflake-arctic-embed-l-v2.0"
  }
}
```

3. Restart any running BMLibrarian applications

**Note**: Embeddings generated with different backends/models may have different dimensions and are not directly comparable. If you change models, you may need to regenerate embeddings for existing documents.

## See Also

- [Document Embedding Guide](document_embedding_guide.md) - Guide to embedding documents
- [Search Configuration](search_configuration_guide.md) - Semantic search settings
