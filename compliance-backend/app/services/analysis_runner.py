"""
Análise de documento em background, dentro do processo da api.

Substitui o worker Celery. O fluxo é o mesmo de antes:

1. O upload grava o documento, com o texto já extraído, e agenda a análise
2. Uma thread do pool carrega as regras do escopo, o contexto legal (RAG) e o
   aprendizado de feedback
3. Chama o Claude, verifica trechos e citações e grava a análise
4. O front acompanha pelo endpoint de status, que lê etapa e progresso do banco

O código é síncrono de ponta a ponta (engine psycopg2 e cliente Anthropic
síncrono), por isso roda numa thread e não no event loop. As threads são de um
pool próprio, e não do threadpool compartilhado do Starlette: uma análise leva
minutos e pode esperar até minutos entre tentativas, e não deve ocupar a vaga que
o upload e a geração de PDF usam via `asyncio.to_thread`. O tamanho do pool é o
limite de análises simultâneas, o equivalente ao `--concurrency` do worker.

O que o Celery dava e este módulo refaz:

- Retry com backoff: até MAX_TENTATIVAS, com as esperas de analysis_errors
- Progresso: colunas analysis_stage e analysis_progress em documents
- Tarefa perdida num restart: `marcar_analises_orfas`, chamada no startup
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.analysis_errors import (
    ESPERA_PADRAO,
    ESPERA_SOBRECARGA,
    classificar_falha,
)
from app.services.feedback_learning import load_feedback_learnings

settings = get_settings()
logger = logging.getLogger(__name__)

# Três tentativas no total: a primeira e duas novas, uma para cada espera de
# ESPERA_PADRAO. Uma falha não retentável (resposta longa demais) para na primeira.
MAX_TENTATIVAS = 3

# Uma análise que passa disto sem terminar foi interrompida: o processo que a
# rodava caiu ou foi substituído num deploy. A margem cobre a análise mais longa
# já vista e deixa terminar a que ainda roda na instância antiga durante um deploy.
ANALISE_ORFA_APOS = timedelta(minutes=10)

SessionFactory = Callable[[], Session]

_engine = None
_executor: Optional[ThreadPoolExecutor] = None
_lock = threading.Lock()


def _sync_engine():
    """Engine síncrona, criada no primeiro uso para não conectar no import."""
    global _engine
    with _lock:
        if _engine is None:
            _engine = create_engine(settings.DATABASE_URL_SYNC, pool_pre_ping=True)
        return _engine


def _default_session() -> Session:
    return Session(_sync_engine())


def _pool() -> ThreadPoolExecutor:
    global _executor
    with _lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(
                max_workers=settings.ANALYSIS_MAX_CONCURRENT,
                thread_name_prefix="analise",
            )
        return _executor


# ─── Agendamento ───

def agendar_analise(document_id) -> None:
    """Coloca a análise na fila do pool e volta na hora.

    O documento precisa estar commitado antes: a thread abre outra sessão e não
    enxergaria uma linha ainda dentro da transação do request.
    """
    _pool().submit(_executar_sem_propagar, str(document_id))


def _executar_sem_propagar(document_id: str) -> None:
    # Exceção que escapa de uma Future some sem log. executar_analise já trata
    # tudo, isto é só a rede de baixo.
    try:
        executar_analise(document_id)
    except Exception:
        logger.exception("Falha inesperada fora da análise do documento %s", document_id)


# ─── Execução com retry ───

def executar_analise(
    document_id: str,
    *,
    session_factory: SessionFactory = _default_session,
    dormir: Callable[[float], None] = time.sleep,
) -> str:
    """Roda a análise com retry e devolve o status final do documento.

    Cada tentativa abre uma sessão nova: depois de uma falha no meio, a sessão
    anterior pode estar com a transação abortada.
    """
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        try:
            with session_factory() as db:
                encontrado = _analisar(db, document_id)
            return "analyzed" if encontrado else "missing"
        except Exception as e:
            categoria, _mensagem, retentavel = classificar_falha(e)
            vai_retentar = retentavel and tentativa < MAX_TENTATIVAS

            logger.error(
                "Erro na análise do documento %s [%s], tentativa %d/%d: %s",
                document_id, categoria, tentativa, MAX_TENTATIVAS, e,
                exc_info=not vai_retentar,
            )

            # Só marca erro quando não há mais tentativa pela frente. Marcar antes
            # fazia a tela dizer "Erro na análise" para um documento que ainda seria
            # reprocessado, e depois voltar sozinho para analisado.
            _marcar_status(
                session_factory, document_id, "processing" if vai_retentar else "error"
            )
            if not vai_retentar:
                return "error"

            espera = ESPERA_SOBRECARGA if categoria == "sobrecarga" else ESPERA_PADRAO
            segundos = espera[min(tentativa - 1, len(espera) - 1)]
            logger.info(
                "Retentando em %ds (%d/%d), motivo: %s",
                segundos, tentativa + 1, MAX_TENTATIVAS, categoria,
            )
            dormir(segundos)

    return "error"  # inalcançável: a última tentativa sempre retorna acima


def _marcar_status(session_factory: SessionFactory, document_id: str, status: str) -> None:
    from app.models import Document

    try:
        with session_factory() as db:
            db.execute(
                update(Document).where(Document.id == document_id).values(status=status)
            )
            db.commit()
    except Exception:
        logger.exception("Não foi possível marcar o documento %s como %s", document_id, status)


def _etapa(db: Session, doc, stage: str, progress: int) -> None:
    doc.analysis_stage = stage
    doc.analysis_progress = progress
    db.commit()


# ─── Pipeline ───

def _analisar(db: Session, document_id: str) -> bool:
    """Extrai, monta o contexto, chama a IA e grava. Devolve False se o documento sumiu."""
    from app.models import Document, Analysis
    from app.services.document_extractor import extract_text
    from app.services.ai_analyzer import analyze_document

    logger.info("Iniciando análise do documento %s", document_id)

    # 1. Fetch document
    doc = db.execute(select(Document).where(Document.id == document_id)).scalar_one_or_none()
    if not doc:
        logger.error("Documento %s não encontrado", document_id)
        return False

    doc.status = "processing"
    _etapa(db, doc, "extracting", 15)
    logger.info("Status atualizado para 'processing': %s", doc.filename)

    # 2. Get the document text. The upload extracts it and stores it on the record.
    # Falling back to the file covers older records.
    extracted_text = doc.extracted_text
    if extracted_text and extracted_text.strip():
        logger.info("Texto obtido do registro: %d caracteres", len(extracted_text))
    else:
        logger.info("Extraindo texto de %s...", doc.file_path)
        extracted_text = extract_text(doc.file_path, doc.mime_type)
        doc.extracted_text = extracted_text
        db.commit()
        logger.info("Texto extraído: %d caracteres", len(extracted_text))

    # 3. Fetch active rules for this document's scope: a document that belongs
    # to an organization follows the team's rules, otherwise the owner's own.
    _etapa(db, doc, "loading_rules", 30)
    from app.services.rule_scope import (
        active_rules_for_prompt,
        overrides_query,
        visible_rules_query,
    )

    scope_org_id = doc.organization_id
    scope_user_id = doc.user_id
    rules = db.execute(
        visible_rules_query(user_id=scope_user_id, organization_id=scope_org_id)
    ).scalars().all()
    overrides = db.execute(
        overrides_query(user_id=scope_user_id, organization_id=scope_org_id)
    ).scalars().all()
    rules_data = active_rules_for_prompt(rules, overrides)

    scope_label = "equipe" if scope_org_id else "pessoal"
    logger.info("Regras ativas carregadas (%s): %d", scope_label, len(rules_data))

    # 3.5 Build legal context via RAG (graceful degradation)
    _etapa(db, doc, "legal_context", 40)
    legal_context = []
    try:
        from app.services.rag_service import build_legal_context_sync
        legal_context = build_legal_context_sync(extracted_text, rules_data, db)
        logger.info("Contexto legal RAG: %d chunks relevantes", len(legal_context))
    except Exception as rag_err:
        # Postgres aborts the whole transaction on a failed statement, so the
        # rollback is what lets the analysis still be saved further down.
        db.rollback()
        logger.warning("RAG context failed (continuing without): %s", rag_err)

    # 3.6 Load feedback learnings for AI calibration (learning loop)
    _etapa(db, doc, "loading_feedback", 50)
    feedback_learnings = []
    try:
        feedback_learnings = load_feedback_learnings(db, doc)
        if feedback_learnings:
            logger.info("Feedback learnings carregados: %d regras com feedback", len(feedback_learnings))
    except Exception as fb_err:
        db.rollback()
        logger.warning("Feedback loading failed (continuing without): %s", fb_err)

    # 4. Call AI for analysis
    _etapa(db, doc, "analyzing", 55)
    logger.info("Enviando para análise com IA...")

    result = analyze_document(
        extracted_text, rules_data,
        legal_context=legal_context,
        feedback_learnings=feedback_learnings,
    )
    logger.info("Análise concluída: score=%s, alertas=%d", result.risk_score, len(result.alerts))

    # 4.5 Verifica o que o modelo afirmou. O trecho citado tem que existir no
    # contrato e o artigo citado tem que estar entre os recuperados pelo RAG.
    # Quem revisa precisa saber onde confiar e onde conferir na fonte.
    from app.services.ai_analyzer import PROMPT_VERSION
    from app.services.verification import annotate_alerts, verification_summary
    from app.services.rag_service import make_base_lookup

    verified_alerts = annotate_alerts(
        result.alerts, extracted_text, legal_context, make_base_lookup(db)
    )
    resumo = verification_summary(verified_alerts)
    logger.info(
        "Verificação: %d/%d trechos localizados, %d/%d citações apoiadas "
        "(%d alertas sem trecho e %d sem citação a conferir)",
        resumo["excerpt_exact"], resumo["excerpt_checkable"],
        resumo["legal_grounded"], resumo["legal_checkable"],
        resumo["total"] - resumo["excerpt_checkable"],
        resumo["total"] - resumo["legal_checkable"],
    )
    if resumo["excerpt_unverified"] or resumo["legal_ungrounded"]:
        logger.warning(
            "Alertas a conferir: %d com trecho não localizado, %d sem respaldo legal",
            resumo["excerpt_unverified"], resumo["legal_ungrounded"],
        )

    # 5. Save analysis
    _etapa(db, doc, "saving", 90)

    # Remove existing analysis if re-analyzing
    existing = db.execute(
        select(Analysis).where(Analysis.document_id == document_id)
    ).scalar_one_or_none()
    if existing:
        db.delete(existing)
        db.flush()

    analysis = Analysis(
        document_id=doc.id,
        risk_score=result.risk_score,
        summary=result.summary,
        alerts=verified_alerts,
        missing_clauses=result.missing_clauses,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        model=settings.ANTHROPIC_MODEL,
        prompt_version=PROMPT_VERSION,
        duration_ms=result.duration_ms,
    )
    db.add(analysis)
    doc.status = "analyzed"
    doc.analysis_stage = None
    doc.analysis_progress = 100
    db.commit()

    logger.info("Análise salva com sucesso para %s", doc.filename)
    return True


# ─── Recuperação no startup ───

async def marcar_analises_orfas(db, agora: Optional[datetime] = None) -> int:
    """Marca como erro as análises que nenhum processo vai terminar.

    Sem fila externa, uma análise que estava rodando quando o processo caiu
    simplesmente deixa de existir, e o documento ficaria em `processing` para
    sempre. Entram também os `uploaded` antigos: são os que esperavam vaga no pool
    e não chegaram a começar.

    `db` é uma AsyncSession. Devolve quantos documentos foram marcados.
    """
    from app.models import Document

    limite = (agora or datetime.now(timezone.utc)) - ANALISE_ORFA_APOS
    resultado = await db.execute(
        update(Document)
        .where(
            Document.status.in_(("uploaded", "processing")),
            Document.uploaded_at < limite,
        )
        .values(status="error")
    )
    await db.commit()
    return resultado.rowcount or 0
