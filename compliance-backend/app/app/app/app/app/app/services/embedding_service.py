"""
Embedding Service — generates vector embeddings via OpenAI API.

Uses text-embedding-3-small (1536 dimensions) for cost-efficiency.
Works in both sync (Celery worker) and async (FastAPI) contexts.
"""
import logging
from typing import List

from openai import OpenAI

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    """Get or create the singleton OpenAI client."""
    global _client
    if _client is None:
        settings = get_settings()
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY não configurada.")
        _client = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


def generate_embedding(text: str) -> List[float]:
    """Generate a single embedding vector for the given text.

    Args:
        text: Input text to embed.

    Returns:
        List of floats with 1536 dimensions.
    """
    settings = get_settings()
    max_chars = 30_000
    if len(text) > max_chars:
        text = text[:max_chars]
        logger.warning(f"Texto truncado para {max_chars} caracteres para embedding")

    client = _get_client()
    response = client.embeddings.create(
        model=settings.OPENAI_EMBEDDING_MODEL,
        input=text,
        dimensions=settings.OPENAI_EMBEDDING_DIMENSIONS,
    )
    return response.data[0].embedding

def generate_embeddings_batch(texts: List[str], batch_size: int = 100) -> List[List[float]]:
    """Generate embeddings for multiple texts in batches via OpenAI API.

    Args:
        texts: List of input texts.
        batch_size: Number of texts per API call.

    Returns:
        List of embedding vectors in the same order as input.
    """
    settings = get_settings()
    max_chars = 30_000
    client = _get_client()
    all_embeddings: List[List[float]] = []

    for i in range(0, len(texts), batch_size):
        batch = [t[:max_chars] for t in texts[i:i + batch_size]]
        logger.info(f"Gerando embeddings batch {i // batch_size + 1} ({len(batch)} textos)")

        response = client.embeddings.create(
            model=settings.OPENAI_EMBEDDING_MODEL,
            input=batch,
            dimensions=settings.OPENAI_EMBEDDING_DIMENSIONS,
        )
        batch_embeddings = [item.embedding for item in sorted(response.data, key=lambda x: x.index)]
        all_embeddings.extend(batch_embeddings)

    return all_embeddings
