"""
Documents API routes — upload, list, delete, trigger analysis, check status.
"""
import os
import uuid
from uuid import UUID
import aiofiles
import re
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Request, status, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

from app.core.database import get_db
from app.core.limiter import limiter
from app.core.config import get_settings
from app.core.security import get_current_user
from app.models import User, Document, Analysis, Rule
from app.schemas import (
    DocumentResponse, DocumentListResponse,
    AnalysisResponse, ReportResponse, RuleResponse,
    AnalysisStatusResponse,
)
from app.services.document_extractor import get_mime_type
from app.services.report_generator import generate_pdf_report, generate_html_report

settings = get_settings()
router = APIRouter(prefix="/documents", tags=["Documentos"])

ALLOWED_EXTENSIONS = {".pdf", ".docx"}


def _doc_to_response(doc: Document) -> DocumentResponse:
    """Convert a Document model to response schema, including analysis data if available."""
    resp = DocumentResponse.model_validate(doc)
    if doc.analysis:
        resp.risk_score = doc.analysis.risk_score
        resp.summary = doc.analysis.summary
    return resp


@router.post("/upload", response_model=AnalysisStatusResponse, status_code=201)
@limiter.limit("10/minute")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Upload a PDF or DOCX document and trigger async analysis.
    Returns a task ID for status polling.
    """
    # Validate extension
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Formato não suportado: {ext}. Use PDF ou DOCX.")

    # Validate file size
    content = await file.read()
    if len(content) > settings.max_file_size_bytes:
        raise HTTPException(status_code=400, detail=f"Arquivo excede o limite de {settings.MAX_FILE_SIZE_MB}MB")
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Arquivo está vazio")

    # Save file to disk
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_id = str(uuid.uuid4())
    safe_filename = f"{file_id}{ext}"
    file_path = upload_dir / safe_filename

    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)

    # Create document record
    mime_type = get_mime_type(file.filename)
    doc = Document(
        user_id=current_user.id,
        filename=file.filename,
        file_path=str(file_path),
        file_size=len(content),
        mime_type=mime_type,
        status="uploaded",
    )
    db.add(doc)
    await db.flush()
    await db.refresh(doc)

    # Trigger async analysis via Celery
    from app.workers.tasks import analyze_document_task
    task = analyze_document_task.delay(str(doc.id))

    return AnalysisStatusResponse(
        document_id=doc.id,
        status="uploaded",
        task_id=task.id,
        message=f"Documento '{file.filename}' recebido. Análise iniciada.",
    )


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    status_filter: str = Query(None, alias="status"),
    risk_min: int = Query(None, ge=0, le=100),
    risk_max: int = Query(None, ge=0, le=100),
    search: str = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List documents for the current user with optional filters."""
    query = (
        select(Document)
        .where(Document.user_id == current_user.id)
        .order_by(desc(Document.uploaded_at))
    )

    if status_filter:
        query = query.where(Document.status == status_filter)
    if search:
        query = query.where(Document.filename.ilike(f"%{search}%"))

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Fetch paginated
    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    docs = result.scalars().all()

    # Load analyses for risk filtering
    doc_responses = []
    for doc in docs:
        # Eager load analysis
        analysis_result = await db.execute(
            select(Analysis).where(Analysis.document_id == doc.id)
        )
        doc.analysis = analysis_result.scalar_one_or_none()

        resp = _doc_to_response(doc)

        # Apply risk filters
        if risk_min is not None and (resp.risk_score is None or resp.risk_score < risk_min):
            continue
        if risk_max is not None and (resp.risk_score is None or resp.risk_score > risk_max):
            continue

        doc_responses.append(resp)

    return DocumentListResponse(documents=doc_responses, total=total)


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a single document by ID."""
    result = await db.execute(
        select(Document).where(Document.id == document_id, Document.user_id == current_user.id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    analysis_result = await db.execute(select(Analysis).where(Analysis.document_id == doc.id))
    doc.analysis = analysis_result.scalar_one_or_none()
    return _doc_to_response(doc)


@router.get("/{document_id}/report", response_model=ReportResponse)
async def get_report(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the full analysis report for a document."""
    result = await db.execute(
        select(Document).where(Document.id == document_id, Document.user_id == current_user.id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    analysis_result = await db.execute(select(Analysis).where(Analysis.document_id == doc.id))
    analysis = analysis_result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Análise ainda não disponível para este documento")

    # Fetch rules for checklist
    rules_result = await db.execute(select(Rule).where(Rule.is_active == True))
    rules = rules_result.scalars().all()

    doc.analysis = analysis
    return ReportResponse(
        document=_doc_to_response(doc),
        analysis=AnalysisResponse.model_validate(analysis),
        rules_checked=[RuleResponse.model_validate(r) for r in rules],
    )


@router.get("/{document_id}/status", response_model=AnalysisStatusResponse)
async def get_analysis_status(
    document_id: uuid.UUID,
    task_id: str = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Poll the analysis status of a document."""
    result = await db.execute(
        select(Document).where(Document.id == document_id, Document.user_id == current_user.id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    # Check Celery task status if task_id provided
    message = ""
    if task_id:
        from app.workers.tasks import celery_app
        task_result = celery_app.AsyncResult(task_id)
        if task_result.state == "PROGRESS":
            meta = task_result.info or {}
            message = f"Etapa: {meta.get('stage', '...')} ({meta.get('progress', 0)}%)"
        elif task_result.state == "FAILURE":
            message = f"Erro: {str(task_result.result)}"

    # Get risk score if analyzed
    risk_score = None
    if doc.status == "analyzed":
        analysis_result = await db.execute(select(Analysis).where(Analysis.document_id == doc.id))
        analysis = analysis_result.scalar_one_or_none()
        if analysis:
            risk_score = analysis.risk_score
            message = "Análise concluída com sucesso"

    return AnalysisStatusResponse(
        document_id=doc.id,
        status=doc.status,
        task_id=task_id,
        risk_score=risk_score,
        message=message,
    )


@router.get("/{document_id}/report/html")
async def download_report_html(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Download the compliance report as HTML."""
    from fastapi.responses import HTMLResponse
    from app.services.report_generator import generate_html_report, generate_pdf_report

    result = await db.execute(
        select(Document).where(Document.id == document_id, Document.user_id == current_user.id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    analysis_result = await db.execute(select(Analysis).where(Analysis.document_id == doc.id))
    analysis = analysis_result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Análise não disponível para este documento")

    rules_result = await db.execute(select(Rule).where(Rule.is_active == True))
    rules = [{"name": r.name, "severity": r.severity} for r in rules_result.scalars().all()]

    analysis_data = {
        "risk_score": analysis.risk_score,
        "summary": analysis.summary,
        "alerts": analysis.alerts or [],
        "missing_clauses": analysis.missing_clauses or [],
    }
    doc_data = {"filename": doc.filename}

    html = generate_html_report(doc_data, analysis_data, rules)
    return HTMLResponse(content=html)


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a document and its analysis permanently."""
    result = await db.execute(
        select(Document).where(Document.id == document_id, Document.user_id == current_user.id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    # Delete file from disk
    if os.path.exists(doc.file_path):
        os.remove(doc.file_path)

    # Delete from database (cascade deletes analysis)
    await db.delete(doc)

@router.get("/{document_id}/report/pdf")
async def download_report(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Gera e retorna o PDF do relatório para o documento especificado.
    Verifica ownership e busca a análise mais recente.
    """
    # 1) Buscar documento e validar que pertence ao usuário
    doc_res = await db.execute(
        select(Document).where(Document.id == document_id, Document.user_id == current_user.id)
    )
    document = doc_res.scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=404, detail="Documento não encontrado ou sem permissão.")

    # 2) Buscar a análise mais recente deste documento
    analysis_res = await db.execute(
        select(Analysis).where(Analysis.document_id == document.id).order_by(Analysis.analyzed_at.desc())
    )
    analysis = analysis_res.scalars().first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Nenhuma análise encontrada para este documento.")

    # 3) Regras ativas para o checklist
    rules_res = await db.execute(select(Rule).where(Rule.is_active == True))
    rules = [{"name": r.name, "severity": r.severity} for r in rules_res.scalars().all()]

    # 4) Preparar dados para geração
    doc_dict = {"filename": document.filename}
    analysis_dict = {
        "risk_score": analysis.risk_score,
        "summary": analysis.summary,
        "alerts": analysis.alerts or [],
        "missing_clauses": analysis.missing_clauses or [],
    }

    # 5) Gerar HTML e converter para PDF
    try:
        html_content = generate_html_report(doc_dict, analysis_dict, rules)
        pdf_bytes = generate_pdf_report(html_content)

        # sanitizar filename para o header
        safe_name = re.sub(r'[^\w\-.]', '_', document.filename.rsplit('.', 1)[0])
        filename = f"relatorio_{safe_name}.pdf"

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao gerar PDF: {str(e)}")