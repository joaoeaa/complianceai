"""
Embedding Service — generates vector embeddings via OpenAI API.

Uses text-embedding-3-small (1536 dimensions) for cost-efficiency.
Works in both sync (background analysis thread) and async (FastAPI) contexts.
"""
import logging
from typing import List

import httpx
from openai import OpenAI

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_client: OpenAI | None = None

# Limites da busca de um embedding só, a consulta do RAG que roda dentro de cada
# tentativa da análise. Os padrões do SDK (600s de leitura, 2 retries) bastavam
# para a análise passar de meia hora só esperando o embedding, e o RAG tem
# degradação: sem contexto legal, a análise segue. Os lotes da ingestão ficam com
# os padrões, porque rodam fora da análise.
EMBEDDING_TIMEOUT = 30.0
EMBEDDING_CONNECT_TIMEOUT = 10.0
EMBEDDING_MAX_RETRIES = 1
# Maior espera do SDK da OpenAI entre retries (openai._constants.MAX_RETRY_DELAY).
EMBEDDING_ESPERA_MAX = 8.0


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

    client = _get_client().with_options(
        timeout=httpx.Timeout(EMBEDDING_TIMEOUT, connect=EMBEDDING_CONNECT_TIMEOUT),
        max_retries=EMBEDDING_MAX_RETRIES,
    )
    response = client.embeddings.create(
        model=settings.OPENAI_EMBEDDING_MODEL,
        input=text,
        dimensions=settings.OPENAI_EMBEDDING_DIMENSIONS,
    )
    return response.data[0].embedding

def generate_query_embeddings(texts: List[str]) -> List[List[float]]:
    """Embeddings de todas as consultas do RAG de uma análise, numa requisição só.

    Os limites são os da consulta única (EMBEDDING_TIMEOUT, EMBEDDING_MAX_RETRIES),
    e não os da ingestão: é uma requisição por tentativa da análise, e é assim que
    pior_caso_da_analise a conta. Quem chama limita quantos textos e de que
    tamanho, para caber no limite de tokens de uma requisição.
    """
    if not texts:
        return []
    settings = get_settings()
    client = _get_client().with_options(
        timeout=httpx.Timeout(EMBEDDING_TIMEOUT, connect=EMBEDDING_CONNECT_TIMEOUT),
        max_retries=EMBEDDING_MAX_RETRIES,
    )
    response = client.embeddings.create(
        model=settings.OPENAI_EMBEDDING_MODEL,
        input=list(texts),
        dimensions=settings.OPENAI_EMBEDDING_DIMENSIONS,
    )
    vetores = [item.embedding for item in sorted(response.data, key=lambda x: x.index)]
    if len(vetores) != len(texts):
        raise ValueError(f"Embedding em lote devolveu {len(vetores)} vetores para {len(texts)} textos")
    return vetores


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
