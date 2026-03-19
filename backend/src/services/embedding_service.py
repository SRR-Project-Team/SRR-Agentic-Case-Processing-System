from src.core.embedding import embed_text, embed_texts

def generate_embedding(text_chunks: list[str]) -> list[list[float]]:
    """
    Generate embeddings for many chunks in batches (fewer HTTP requests to Ollama).
    Uses embed_texts() with configurable batch size (env EMBEDDING_BATCH_SIZE, default 16).
    """
    if not text_chunks:
        return []
    return embed_texts(text_chunks)
