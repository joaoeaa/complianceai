"""
Legislation API routes — ingest, list, detail, and semantic search for Brazilian legislation.
"""
import uuid
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.core.security import get_current_user, get_current_admin
from app.models import User, LegalDocument, LegalChunk
from app.schemas import (
    LegislationIngestRequest,
    LegislationResponse,
    LegislationDetailResponse,
    LegalChunkResponse,
    LegislationSearchRequest,
    LegislationSearchResponse,
)
from app.services.rag_service import ingest_legal_document_async, search_relevant_chunks_async

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/legislation", tags=["Legislação (RAG)"])


@router.post("/ingest", response_model=LegislationResponse, status_code=201)
async def ingest_legislation(
    data: LegislationIngestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """Ingest a legislation text: chunk, embed, and store (admin only)."""
    # Duplicate check on source
    existing = await db.execute(
        select(LegalDocument).where(LegalDocument.source == data.source)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"Legislação com source '{data.source}' já foi indexada.",
        )

    legal_doc = await ingest_legal_document_async(
        title=data.title,
        full_text=data.full_text,
        source=data.source,
        category=data.category,
        db=db,
        chunk_size=data.chunk_size,
        overlap=data.overlap,
    )

    # Get chunk count
    count_result = await db.execute(
        select(func.count()).select_from(LegalChunk).where(LegalChunk.document_id == legal_doc.id)
    )
    chunk_count = count_result.scalar() or 0

    return LegislationResponse(
        id=legal_doc.id,
        title=legal_doc.title,
        source=legal_doc.source,
        category=legal_doc.category,
        created_at=legal_doc.created_at,
        chunk_count=chunk_count,
    )


@router.get("", response_model=list[LegislationResponse])
async def list_legislation(
    category: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all indexed legislation with chunk counts."""
    # Duas contagens diferentes, e confundi-las gerava numeros divergentes na
    # interface: um artigo longo e fatiado em varios trechos, entao somar trechos
    # e chamar de "artigos" inflava o numero.
    query = (
        select(
            LegalDocument,
            func.count(LegalChunk.id).label("chunk_count"),
            func.count(func.distinct(LegalChunk.article_ref)).label("article_count"),
        )
        .outerjoin(LegalChunk, LegalChunk.document_id == LegalDocument.id)
        .group_by(LegalDocument.id)
        .order_by(LegalDocument.created_at.desc())
    )

    if category:
        query = query.where(LegalDocument.category == category)

    result = await db.execute(query)
    rows = result.all()

    return [
        LegislationResponse(
            id=doc.id,
            title=doc.title,
            source=doc.source,
            category=doc.category,
            created_at=doc.created_at,
            chunk_count=count,
            article_count=artigos,
        )
        for doc, count, artigos in rows
    ]


@router.get("/{legislation_id}", response_model=LegislationDetailResponse)
async def get_legislation(
    legislation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get legislation detail with all chunks."""
    result = await db.execute(
        select(LegalDocument).where(LegalDocument.id == legislation_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Legislação não encontrada")

    chunks_result = await db.execute(
        select(LegalChunk)
        .where(LegalChunk.document_id == legislation_id)
        .order_by(LegalChunk.chunk_index)
    )
    chunks = chunks_result.scalars().all()

    return LegislationDetailResponse(
        id=doc.id,
        title=doc.title,
        source=doc.source,
        category=doc.category,
        full_text=doc.full_text,
        created_at=doc.created_at,
        chunks=[
            LegalChunkResponse(
                id=c.id,
                chunk_index=c.chunk_index,
                content=c.content,
                article_ref=c.article_ref,
            )
            for c in chunks
        ],
    )


@router.post("/search", response_model=LegislationSearchResponse)
async def search_legislation(
    data: LegislationSearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Semantic search across indexed legislation."""
    results = await search_relevant_chunks_async(
        query=data.query,
        db=db,
        top_k=data.top_k,
        category=data.category,
    )

    return LegislationSearchResponse(
        results=results,
        total=len(results),
    )
