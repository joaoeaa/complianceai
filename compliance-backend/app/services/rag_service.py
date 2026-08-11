"""
RAG Service — Retrieval-Augmented Generation for legislation and legal documents.

Handles:
1. Text chunking with article-boundary awareness
2. Legal document ingestion with embedding generation
3. Semantic similarity search against legislation chunks
4. Context building for prompt enrichment
"""
import asyncio
import re
import logging
from typing import List, Dict, Any, Optional

from sqlalchemy import select, func, text as sa_text
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.embedding_service import generate_embedding, generate_embeddings_batch

logger = logging.getLogger(__name__)

# ─── Article Reference Extraction ───

# Acima de 999 a numeracao usa ponto de milhar ("Art. 1.337"). Sem o grupo
# (?:\.\d{3})* o Codigo Civil inteiro acima do artigo 999 era lido como "Art. 1".
_NUM_ARTIGO = r"\d+(?:\.\d{3})*"

ARTICLE_PATTERN = re.compile(
    rf"(Art\.\s*{_NUM_ARTIGO}[\w°ºª]*(?:\s*,?\s*§\s*\d+[\w°ºª]*)?)"
    r"|"
    r"(§\s*\d+[\w°ºª]*)"
    r"|"
    r"(Parágrafo\s+[Úú]nico)",
    re.IGNORECASE,
)

# O \s* inicial e necessario: o texto oficial vem com espaco depois da quebra de
# linha (" Art. 7o"), e sem ele nenhum artigo era reconhecido como inicio de
# segmento. A lei inteira virava um bloco unico, cortado por tamanho.
ARTICLE_START_PATTERN = re.compile(
    rf"^[ 	]*(Art\.\s*{_NUM_ARTIGO}[\w°ºª]*\.?\s)",
    re.IGNORECASE | re.MULTILINE,
)


def _extract_article_ref(text: str) -> Optional[str]:
    """Extract the first article reference from a text chunk."""
    match = ARTICLE_PATTERN.search(text)
    if match:
        return (match.group(1) or match.group(2) or match.group(3)).strip()
    return None


def _split_by_articles(text: str) -> List[str]:
    """Split legal text into segments at article boundaries.

    Returns:
        List of text segments, each starting at an article boundary.
        Preamble text (before first article) is returned as the first segment.
    """
    positions = [m.start() for m in ARTICLE_START_PATTERN.finditer(text)]

    if not positions:
        return [text]

    segments = []
    if positions[0] > 0:
        preamble = text[:positions[0]].strip()
        if preamble:
            segments.append(preamble)

    for i, pos in enumerate(positions):
        end = positions[i + 1] if i + 1 < len(positions) else len(text)
        segment = text[pos:end].strip()
        if segment:
            segments.append(segment)

    return segments


def chunk_text(
    text: str,
    chunk_size: int = 800,
    overlap: int = 100,
) -> List[Dict[str, Any]]:
    """Chunk legal text respecting article boundaries where possible.

    Strategy:
    1. Split by article boundaries (Art. X patterns)
    2. If a segment is <= chunk_size, keep as single chunk
    3. If a segment is > chunk_size, split with overlap within that segment

    Args:
        text: Full legal text.
        chunk_size: Target chunk size in characters.
        overlap: Character overlap between chunks within same article.

    Returns:
        List of dicts with keys: content, article_ref, chunk_index.
    """
    segments = _split_by_articles(text)
    chunks: List[Dict[str, Any]] = []
    chunk_index = 0

    for segment in segments:
        # So conta como artigo o segmento que comeca com "Art. N". O preambulo
        # institucional mencionava artigos no meio do texto e acabava rotulado
        # com uma referencia que nao era a dele.
        article_ref = (
            _extract_article_ref(segment)
            if ARTICLE_START_PATTERN.match(segment)
            else None
        )

        if len(segment) <= chunk_size:
            chunks.append({
                "content": segment,
                "article_ref": article_ref,
                "chunk_index": chunk_index,
            })
            chunk_index += 1
        else:
            start = 0
            while start < len(segment):
                end = start + chunk_size

                # Try to break at sentence boundary near the end
                if end < len(segment):
                    boundary_start = max(end - 80, start)
                    boundary_zone = segment[boundary_start:end + 20]
                    best_break = -1
                    for punct in [". ", ".\n", ";\n"]:
                        idx = boundary_zone.rfind(punct)
                        if idx > best_break:
                            best_break = idx
                    if best_break > 0:
                        end = boundary_start + best_break + 1

                chunk_content = segment[start:end].strip()
                if chunk_content:
                    # A referencia do artigo vale para todos os seus pedacos. Sem isto
                    # um pedaco iniciado por "§ 3o" ficava rotulado com o paragrafo, e
                    # uma citacao a "Art. 52" nao casava com o trecho recuperado.
                    sub_ref = article_ref or _extract_article_ref(chunk_content)
                    chunks.append({
                        "content": chunk_content,
                        "article_ref": sub_ref,
                        "chunk_index": chunk_index,
                    })
                    chunk_index += 1

                start = end - overlap if end < len(segment) else len(segment)

    return chunks


# ─── Ingestion ───

def ingest_legal_document_sync(
    title: str,
    full_text: str,
    source: str,
    category: str,
    db: Session,
    chunk_size: int = 800,
    overlap: int = 100,
) -> Any:
    """Ingest a legal document: chunk, embed, and store. SYNC version for Celery.

    Args:
        title: Display title of the legislation.
        full_text: Full text of the legislation.
        source: Legal reference (e.g. "Lei 13.709/2018 (LGPD)").
        category: Category for filtering (e.g. "proteção_de_dados").
        db: Sync SQLAlchemy session.
        chunk_size: Target chunk size in characters.
        overlap: Character overlap between chunks.

    Returns:
        The created LegalDocument instance.
    """
    from app.models import LegalDocument, LegalChunk

    legal_doc = LegalDocument(
        title=title,
        source=source,
        category=category,
        full_text=full_text,
    )
    db.add(legal_doc)
    db.flush()

    chunks_data = chunk_text(full_text, chunk_size=chunk_size, overlap=overlap)
    logger.info(f"Documento '{title}' dividido em {len(chunks_data)} chunks")

    texts = [c["content"] for c in chunks_data]
    embeddings = generate_embeddings_batch(texts)

    for chunk_data, embedding in zip(chunks_data, embeddings):
        chunk = LegalChunk(
            document_id=legal_doc.id,
            chunk_index=chunk_data["chunk_index"],
            content=chunk_data["content"],
            article_ref=chunk_data["article_ref"],
            embedding=embedding,
            metadata_={
                "source": source,
                "category": category,
                "char_count": len(chunk_data["content"]),
            },
        )
        db.add(chunk)

    db.commit()
    logger.info(f"Documento legal '{title}' ingerido: {len(chunks_data)} chunks com embeddings")
    return legal_doc


async def ingest_legal_document_async(
    title: str,
    full_text: str,
    source: str,
    category: str,
    db: AsyncSession,
    chunk_size: int = 800,
    overlap: int = 100,
) -> Any:
    """Ingest a legal document: chunk, embed, and store. ASYNC version for API.

    Args:
        title: Display title of the legislation.
        full_text: Full text of the legislation.
        source: Legal reference (e.g. "Lei 13.709/2018 (LGPD)").
        category: Category for filtering (e.g. "proteção_de_dados").
        db: Async SQLAlchemy session.
        chunk_size: Target chunk size in characters.
        overlap: Character overlap between chunks.

    Returns:
        The created LegalDocument instance.
    """
    from app.models import LegalDocument, LegalChunk

    legal_doc = LegalDocument(
        title=title,
        source=source,
        category=category,
        full_text=full_text,
    )
    db.add(legal_doc)
    await db.flush()

    chunks_data = chunk_text(full_text, chunk_size=chunk_size, overlap=overlap)
    logger.info(f"Documento '{title}' dividido em {len(chunks_data)} chunks")

    texts = [c["content"] for c in chunks_data]
    embeddings = await asyncio.to_thread(generate_embeddings_batch, texts)

    for chunk_data, embedding in zip(chunks_data, embeddings):
        chunk = LegalChunk(
            document_id=legal_doc.id,
            chunk_index=chunk_data["chunk_index"],
            content=chunk_data["content"],
            article_ref=chunk_data["article_ref"],
            embedding=embedding,
            metadata_={
                "source": source,
                "category": category,
                "char_count": len(chunk_data["content"]),
            },
        )
        db.add(chunk)

    await db.flush()
    logger.info(f"Documento legal '{title}' ingerido: {len(chunks_data)} chunks com embeddings")
    return legal_doc


# ─── Semantic Search ───

def _fmt_embedding(emb: List[float]) -> str:
    """Format embedding list as pgvector-compatible string."""
    return "[" + ",".join(str(float(x)) for x in emb) + "]"


def _build_search_results(rows: Any) -> List[Dict[str, Any]]:
    """Convert raw DB rows to search result dicts."""
    return [
        {
            "id": str(row.id),
            "content": row.content,
            "article_ref": row.article_ref,
            "document_title": row.document_title,
            "document_source": row.document_source,
            "similarity": round(float(row.similarity), 4),
        }
        for row in rows
    ]


def _build_search_sql(category: Optional[str] = None) -> str:
    """Build the full search SQL with optional category filter."""
    sql = """
        SELECT
            lc.id,
            lc.content,
            lc.article_ref,
            ld.title AS document_title,
            ld.source AS document_source,
            1 - (lc.embedding <=> CAST(:embedding AS vector)) AS similarity
        FROM legal_chunks lc
        JOIN legal_documents ld ON ld.id = lc.document_id
        WHERE lc.embedding IS NOT NULL
    """
    if category:
        sql += " AND ld.category = :category"
    sql += " ORDER BY lc.embedding <=> CAST(:embedding AS vector) LIMIT :top_k"
    return sql


def search_relevant_chunks_sync(
    query: str,
    db: Session,
    top_k: int = 5,
    category: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Search for relevant legal chunks using cosine similarity. SYNC version."""
    query_embedding = generate_embedding(query)
    emb_str = _fmt_embedding(query_embedding)

    sql = _build_search_sql(category)
    params: Dict[str, Any] = {"embedding": emb_str, "top_k": top_k}
    if category:
        params["category"] = category

    result = db.execute(sa_text(sql), params)
    return _build_search_results(result.fetchall())


async def search_relevant_chunks_async(
    query: str,
    db: AsyncSession,
    top_k: int = 5,
    category: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Search for relevant legal chunks using cosine similarity. ASYNC version."""
    query_embedding = await asyncio.to_thread(generate_embedding, query)
    emb_str = _fmt_embedding(query_embedding)

    sql = _build_search_sql(category)
    params: Dict[str, Any] = {"embedding": emb_str, "top_k": top_k}
    if category:
        params["category"] = category

    result = await db.execute(sa_text(sql), params)
    return _build_search_results(result.fetchall())


# ─── Context Building for Prompt Enrichment ───

def build_legal_context_sync(
    document_text: str,
    rules: List[Dict[str, Any]],
    db: Session,
    top_k: int = 5,
    similarity_threshold: float = 0.3,
) -> List[Dict[str, str]]:
    """Build legal context for prompt enrichment. SYNC version for Celery worker.

    Builds a composite query from a document excerpt + rule criteria,
    then searches for relevant legislation chunks.

    Args:
        document_text: The extracted document text.
        rules: List of active rule dicts (with 'criteria' key).
        db: Sync SQLAlchemy session.
        top_k: Maximum number of chunks to retrieve.
        similarity_threshold: Minimum similarity to include a result.

    Returns:
        List of context dicts with source, article_ref, and content.
    """
    # Check if any legislation is indexed WITH embeddings
    from app.models import LegalChunk
    count = db.execute(
        select(func.count()).select_from(LegalChunk).where(LegalChunk.embedding.isnot(None))
    ).scalar()
    if not count:
        logger.info("Nenhuma legislação indexada — pulando contexto legal")
        return []

    doc_excerpt = document_text[:500]
    rule_keywords = " ".join([r.get("criteria", "")[:100] for r in rules[:5]])
    composite_query = f"{doc_excerpt} {rule_keywords}"

    chunks = search_relevant_chunks_sync(composite_query, db, top_k=top_k)

    relevant = [c for c in chunks if c["similarity"] >= similarity_threshold]

    if not relevant:
        logger.info("Nenhum contexto legal relevante acima do threshold")
        return []

    logger.info(f"Contexto legal: {len(relevant)} chunks relevantes (threshold={similarity_threshold})")

    return [
        {
            "source": c["document_source"],
            "article_ref": c["article_ref"] or "Sem referência",
            "content": c["content"],
        }
        for c in relevant
    ]
