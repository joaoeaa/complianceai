"""
Documents API routes — upload, list, delete, trigger analysis, check status.
"""
import asyncio
import os
import uuid
from uuid import UUID
import aiofiles
import re
from pathlib import Path
from typing import Optional
import unicodedata
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, Request, status, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

from app.core.database import get_db
from app.core.limiter import limiter
from app.core.config import get_settings
from app.core.security import get_current_user
from app.models import User, Document, Analysis, Rule, Client
from app.schemas import (
    DocumentResponse, DocumentListResponse,
    AnalysisResponse, ReportResponse, RuleResponse,
    AnalysisStatusResponse, AlertResolutionUpdate,
)
from app.services.document_extractor import get_mime_type, extract_text
from app.services.audit import record_access
from app.services.scope import (
    can_read_client,
    document_scope_filter,
    get_document_for_delete,
    get_document_for_read,
    require_org_membership,
)
from app.services.report_generator import generate_pdf_report, generate_html_report

settings = get_settings()
router = APIRouter(prefix="/documents", tags=["Documentos"])

ALLOWED_EXTENSIONS = {".pdf", ".docx"}


async def _rules_for_document(doc: Document, db: AsyncSession) -> list[dict]:
    """Regras que valem para este documento, no escopo dele.

    O checklist do relatorio precisa refletir o mesmo conjunto que o worker usou
    na analise. Buscar todas as regras da tabela vazava para o relatorio de uma
    conta os nomes das regras criadas por outras contas e equipes.
    """
    from app.services.rule_scope import apply_overrides, overrides_query, visible_rules_query

    rules = (
        await db.execute(
            visible_rules_query(user_id=doc.user_id, organization_id=doc.organization_id)
        )
    ).scalars().all()
    overrides = (
        await db.execute(
            overrides_query(user_id=doc.user_id, organization_id=doc.organization_id)
        )
    ).scalars().all()
    return [r for r in apply_overrides(rules, overrides) if r["is_active"]]


def _cabecalho_download(nome_visivel: str) -> dict:
    """Content-Disposition com o nome legível e um substituto em ASCII.

    Cabeçalho HTTP não carrega acento, então o nome bonito vai em `filename*`
    (RFC 5987), que todo navegador atual entende, e o `filename` simples fica
    como reserva. Sem isso, ou o nome chega corrompido ou a resposta quebra
    quando o arquivo tem um caractere fora do latin-1.

    O substituto translitera em vez de trocar por sublinhado: "Locação" vira
    "Locacao", e não "Loca__o".
    """
    # Windows e macOS recusam estes caracteres em nome de arquivo. Limpar aqui, e
    # nao so no substituto ascii, evita que o navegador salve um nome mutilado.
    nome_visivel = re.sub(r'[\\/:*?"<>|]+', "-", nome_visivel).strip() or "documento"

    sem_acento = unicodedata.normalize("NFKD", nome_visivel)
    sem_acento = sem_acento.encode("ascii", "ignore").decode("ascii")
    # Caracteres que o Windows e o macOS recusam em nome de arquivo.
    sem_acento = re.sub(r'[\\/:*?"<>|]+', "-", sem_acento)
    sem_acento = re.sub(r"\s+", " ", sem_acento).strip() or "documento"

    return {
        "Content-Disposition": (
            f'attachment; filename="{sem_acento}"; '
            f"filename*=UTF-8''{quote(nome_visivel)}"
        )
    }


def _nome_do_relatorio(nome_do_contrato: str) -> str:
    """Nome do relatório derivado do contrato, para os dois ficarem juntos na pasta."""
    base = nome_do_contrato.rsplit(".", 1)[0].strip() or "documento"
    return f"Relatório - {base}.pdf"


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
    organization_id: Optional[UUID] = Form(
        None, description="Envia para o escopo desta equipe; omitido usa o escopo pessoal"
    ),
    client_id: Optional[UUID] = Form(
        None, description="Cliente do escritório a que este contrato pertence"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Upload a PDF or DOCX document and trigger async analysis.
    Returns a task ID for status polling.
    """
    if organization_id is not None:
        await require_org_membership(organization_id, current_user, db)

    # Amarrar o documento a um cliente é o que define quem vai poder lê-lo, então
    # a designação precisa ser conferida na entrada, e não só na leitura.
    if client_id is not None:
        cliente = (
            await db.execute(select(Client).where(Client.id == client_id))
        ).scalar_one_or_none()
        pertence = cliente is not None and (
            cliente.organization_id == organization_id
            if organization_id is not None
            else cliente.user_id == current_user.id
        )
        if not pertence:
            raise HTTPException(status_code=404, detail="Cliente não encontrado")
        if not await can_read_client(client_id, organization_id, current_user, db):
            raise HTTPException(status_code=404, detail="Cliente não encontrado")

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

    # Extract the text here, while the uploaded file is still on this container's
    # disk. API and worker run as separate services in production and do not share
    # a filesystem, so the text travels through the database instead of the file.
    mime_type = get_mime_type(file.filename)
    try:
        extracted = await asyncio.to_thread(extract_text, str(file_path), mime_type)
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Não conseguimos ler o conteúdo deste arquivo. Verifique se ele não está protegido por senha ou corrompido.",
        )

    if not extracted or not extracted.strip():
        raise HTTPException(
            status_code=400,
            detail="Não encontramos texto neste documento. Se ele for digitalizado, envie uma versão com texto selecionável.",
        )

    # Create document record
    doc = Document(
        user_id=current_user.id,
        filename=file.filename,
        file_path=str(file_path),
        file_size=len(content),
        mime_type=mime_type,
        status="uploaded",
        extracted_text=extracted,
        organization_id=organization_id,
        client_id=client_id,
    )
    db.add(doc)
    await db.flush()
    await db.refresh(doc)

    await record_access(db, user=current_user, action="analyze", document=doc)

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
    organization_id: Optional[UUID] = Query(
        None, description="Documentos desta equipe; omitido lista os pessoais"
    ),
    client_id: Optional[UUID] = Query(
        None, description="Apenas os documentos deste cliente"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista os documentos do escopo escolhido, com filtros opcionais."""
    if organization_id is not None:
        await require_org_membership(organization_id, current_user, db)

    query = (
        select(Document)
        .where(await document_scope_filter(current_user, organization_id, db))
        .order_by(desc(Document.uploaded_at))
    )

    # Filtrar por cliente nao substitui a checagem de sigilo: o filtro de escopo
    # acima ja removeu o que este usuario nao pode ver.
    if client_id is not None:
        query = query.where(Document.client_id == client_id)

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
    doc = await get_document_for_read(document_id, current_user, db)

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
    doc = await get_document_for_read(document_id, current_user, db)
    await record_access(db, user=current_user, action="view", document=doc)

    analysis_result = await db.execute(select(Analysis).where(Analysis.document_id == doc.id))
    analysis = analysis_result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Análise ainda não disponível para este documento")

    # Regras do escopo do documento, nao da tabela inteira
    rules = await _rules_for_document(doc, db)

    # Traz o que este revisor ja marcou, para a tela abrir onde ele parou.
    from app.models import AlertFeedback

    marcacoes = (
        await db.execute(
            select(AlertFeedback).where(
                AlertFeedback.analysis_id == analysis.id,
                AlertFeedback.user_id == current_user.id,
            )
        )
    ).scalars().all()
    por_indice = {m.alert_index: m for m in marcacoes}

    resposta = AnalysisResponse.model_validate(analysis)
    for i, alerta in enumerate(resposta.alerts):
        marcacao = por_indice.get(i)
        if marcacao:
            alerta.resolution = marcacao.resolution
            alerta.resolution_comment = marcacao.comment

    doc.analysis = analysis
    return ReportResponse(
        document=_doc_to_response(doc),
        analysis=resposta,
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
    doc = await get_document_for_read(document_id, current_user, db)

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

    doc = await get_document_for_read(document_id, current_user, db)
    await record_access(db, user=current_user, action="export", document=doc)

    analysis_result = await db.execute(select(Analysis).where(Analysis.document_id == doc.id))
    analysis = analysis_result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Análise não disponível para este documento")

    rules = [
        {"name": r["name"], "severity": r["severity"]}
        for r in await _rules_for_document(doc, db)
    ]

    analysis_data = {
        "risk_score": analysis.risk_score,
        "summary": analysis.summary,
        "alerts": analysis.alerts or [],
        "missing_clauses": analysis.missing_clauses or [],
    }
    doc_data = {"filename": doc.filename}

    html = generate_html_report(doc_data, analysis_data, rules)
    return HTMLResponse(content=html)


@router.patch("/{document_id}/alerts/{alert_index}", response_model=AlertResolutionUpdate)
async def set_alert_resolution(
    document_id: uuid.UUID,
    alert_index: int,
    body: AlertResolutionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Marca o que o revisor decidiu sobre um alerta.

    E a trilha de revisao humana: percorrer 16 alertas sem poder anotar o que ja
    foi tratado obriga a recomecar do zero a cada sessao. Enviar `resolution: null`
    limpa a marcacao.
    """
    from app.models import AlertFeedback

    doc = await get_document_for_read(document_id, current_user, db)

    analysis = (
        await db.execute(select(Analysis).where(Analysis.document_id == doc.id))
    ).scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Análise não encontrada para este documento")

    alertas = analysis.alerts or []
    if not 0 <= alert_index < len(alertas):
        raise HTTPException(status_code=404, detail="Alerta não encontrado nesta análise")

    existente = (
        await db.execute(
            select(AlertFeedback).where(
                AlertFeedback.analysis_id == analysis.id,
                AlertFeedback.alert_index == alert_index,
                AlertFeedback.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()

    valor = body.resolution.value if body.resolution else None

    if existente:
        existente.resolution = valor
        if body.comment is not None:
            existente.comment = body.comment
    else:
        alerta = alertas[alert_index]
        db.add(AlertFeedback(
            analysis_id=analysis.id,
            user_id=current_user.id,
            alert_index=alert_index,
            rule_name=alerta.get("rule_name", ""),
            severity=alerta.get("severity"),
            resolution=valor,
            comment=body.comment,
        ))

    await db.flush()
    return body


@router.get("/{document_id}/download")
async def download_original(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Baixa o arquivo exatamente como foi enviado.

    Mesmo controle de acesso do relatorio: documento pessoal so para o dono,
    documento de equipe para qualquer membro.
    """
    doc = await get_document_for_read(document_id, current_user, db)
    await record_access(db, user=current_user, action="download", document=doc)

    caminho = Path(doc.file_path)
    if not caminho.is_file():
        # Acontece com documentos anteriores ao volume persistente: a analise
        # continua no banco, o arquivo nao. Dizer isso e melhor que um 404 seco.
        raise HTTPException(
            status_code=410,
            detail="O arquivo original não está mais disponível. A análise permanece acessível no relatório.",
        )

    conteudo = await asyncio.to_thread(caminho.read_bytes)

    return Response(
        content=conteudo,
        media_type=doc.mime_type or "application/octet-stream",
        headers=_cabecalho_download(doc.filename),
    )


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Exclui o documento e a análise. Em equipe: quem enviou ou os responsáveis."""
    doc = await get_document_for_delete(document_id, current_user, db)
    await record_access(db, user=current_user, action="delete", document=doc)

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
    # 1) Buscar documento respeitando o escopo (pessoal ou da equipe)
    document = await get_document_for_read(document_id, current_user, db)
    await record_access(db, user=current_user, action="export", document=document)

    # 2) Buscar a análise mais recente deste documento
    analysis_res = await db.execute(
        select(Analysis).where(Analysis.document_id == document.id).order_by(Analysis.analyzed_at.desc())
    )
    analysis = analysis_res.scalars().first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Nenhuma análise encontrada para este documento.")

    # 3) Regras do escopo do documento para o checklist
    rules = [
        {"name": r["name"], "severity": r["severity"]}
        for r in await _rules_for_document(document, db)
    ]

    # 4) Preparar dados para geração
    doc_dict = {"filename": document.filename}

    # As marcações do revisor são por pessoa: o PDF sai com as de quem o exporta,
    # porque é o relatório da revisão dele, não uma média das opiniões da equipe.
    from app.models import AlertFeedback

    alertas = list(analysis.alerts or [])
    marcacoes = {
        m.alert_index: m
        for m in (
            await db.execute(
                select(AlertFeedback).where(
                    AlertFeedback.analysis_id == analysis.id,
                    AlertFeedback.user_id == current_user.id,
                )
            )
        ).scalars().all()
    }
    for i, alerta in enumerate(alertas):
        marcacao = marcacoes.get(i)
        if marcacao and marcacao.resolution:
            alerta = {**alerta,
                      "resolution": marcacao.resolution,
                      "resolution_comment": marcacao.comment}
            alertas[i] = alerta

    analysis_dict = {
        "risk_score": analysis.risk_score,
        "summary": analysis.summary,
        "alerts": alertas,
        "missing_clauses": analysis.missing_clauses or [],
        # Rastreabilidade: sem isto não dá para saber qual redação de prompt e qual
        # modelo produziram um relatório emitido meses atrás.
        "model": analysis.model,
        "prompt_version": analysis.prompt_version,
    }

    # 5) Gerar HTML e converter para PDF
    try:
        html_content = generate_html_report(
            doc_dict, analysis_dict, rules,
            generated_by=current_user.full_name or current_user.email,
        )
        pdf_bytes = generate_pdf_report(html_content)

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers=_cabecalho_download(_nome_do_relatorio(document.filename)),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao gerar PDF: {str(e)}")