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
- Tarefa perdida num restart: a detecção de órfãs, descrita abaixo

Análise órfã
------------

Sem fila externa, a análise que morre com o processo não volta, e o documento
ficaria em `processing` para sempre. `documents.analysis_updated_at` é o sinal
de vida: muda a cada etapa, a cada tentativa e, enquanto o documento está na
fila ou rodando neste processo, a cada BATIMENTO_SEGUNDOS. O batimento é o que
cobre os trechos longos sem etapa nova: a chamada ao LLM, que com os retries do
tenacity e do próprio SDK pode passar bem de 12 minutos, e a espera entre
tentativas.

Órfã é a que está em `uploaded`/`processing` sem sinal de vida há mais de
ORPHAN_TIMEOUT_MINUTES (cai para uploaded_at se a coluna é nula). Ela vira
`error` em dois lugares: na varredura do startup e, preguiçosamente, quando
alguém consulta o status daquele documento.

Se a thread ainda estiver viva e o documento tiver sido marcado por fora, ela não
desfaz a marcação: toda escrita de status é condicional a `uploaded`/`processing`,
e a thread desiste ao perceber que perdeu o documento (AnaliseAbandonada).
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable, Optional

from sqlalchemy import and_, create_engine, func, select, update
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

# Status em que uma análise ainda pode estar a caminho. Só a partir deles a thread
# escreve, e só eles podem ser dados como órfãos.
EM_ANDAMENTO = ("uploaded", "processing")

# Intervalo do batimento. Bem abaixo de ORPHAN_TIMEOUT_MINUTES, para que um
# batimento atrasado ou uma falha passageira do banco não bastem para condenar
# uma análise viva.
BATIMENTO_SEGUNDOS = 60

SessionFactory = Callable[[], Session]


class AnaliseAbandonada(Exception):
    """O documento saiu de uploaded/processing por fora, em geral marcado como órfão."""


_engine = None
_executor: Optional[ThreadPoolExecutor] = None
_lock = threading.Lock()


def _agora() -> datetime:
    return datetime.now(timezone.utc)


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
    enxergaria uma linha ainda dentro da transação do request. Ele entra no
    batimento já aqui, e não quando a thread começa: com o pool cheio, esperar a
    vez não pode parecer abandono.
    """
    doc_id = str(document_id)
    _registrar(doc_id)
    try:
        _pool().submit(_executar_sem_propagar, doc_id)
    except Exception:
        _desregistrar(doc_id)
        raise


def _executar_sem_propagar(document_id: str) -> None:
    # A primeira tentativa começa aqui, quando a thread do pool pega o documento.
    # É daqui que conta o teto do batimento, e não do agendamento: a espera na
    # fila não é tempo da análise.
    with _cond:
        _inicio[document_id] = _relogio()
    # Exceção que escapa de uma Future some sem log. executar_analise já trata
    # tudo, isto é só a rede de baixo.
    try:
        executar_analise(document_id)
    except Exception:
        logger.exception("Falha inesperada fora da análise do documento %s", document_id)
    finally:
        _desregistrar(document_id)


# ─── Batimento ───
# Uma thread só para o processo inteiro, viva apenas enquanto houver documento na
# fila ou rodando. Sem análise em andamento, não há thread nem consulta periódica,
# e o serviço pode dormir.

#
# O batimento tem teto: passado ANALYSIS_MAX_DURATION_MINUTES do início da
# primeira tentativa, o documento deixa de ser renovado. Uma thread travada (uma
# chamada que não volta, um laço) não pode manter o documento vivo para sempre:
# sem batimento, ele vira órfão no prazo normal e o usuário recebe o erro. A
# thread em si não tem como ser interrompida em Python e segue ocupando a vaga
# no pool até terminar, se terminar.

_em_execucao: set[str] = set()
_inicio: dict[str, float] = {}      # documento -> início da primeira tentativa
_estourados: set[str] = set()       # já passaram do teto; só para logar uma vez
_batimento: Optional[threading.Thread] = None
_cond = threading.Condition()
_relogio: Callable[[], float] = time.monotonic


def _registrar(document_id: str) -> None:
    global _batimento
    with _cond:
        _em_execucao.add(document_id)
        if _batimento is None:
            _batimento = threading.Thread(target=_bater, name="analise-batimento", daemon=True)
            _batimento.start()


def _desregistrar(document_id: str) -> None:
    with _cond:
        _em_execucao.discard(document_id)
        _inicio.pop(document_id, None)
        _estourados.discard(document_id)
        _cond.notify_all()


def _renovaveis() -> list[str]:
    """Documentos que o batimento ainda deve renovar. Chamar com `_cond` em mãos.

    Quem ainda espera na fila não tem início e é sempre renovado.
    """
    teto = settings.ANALYSIS_MAX_DURATION_MINUTES * 60
    agora = _relogio()
    ids = []
    for doc_id in _em_execucao:
        inicio = _inicio.get(doc_id)
        if inicio is not None and agora - inicio > teto:
            if doc_id not in _estourados:
                _estourados.add(doc_id)
                logger.error(
                    "Análise do documento %s passou de %s minutos; o batimento parou "
                    "e ele será dado como órfão",
                    doc_id, settings.ANALYSIS_MAX_DURATION_MINUTES,
                )
            continue
        ids.append(doc_id)
    return ids


def _bater() -> None:
    global _batimento
    while True:
        with _cond:
            if not _em_execucao:
                _batimento = None
                return
            ids = _renovaveis()
        tocar_em_andamento(ids, _default_session)
        with _cond:
            _cond.wait_for(lambda: not _em_execucao, timeout=BATIMENTO_SEGUNDOS)


def tocar_em_andamento(ids: Iterable[str], session_factory: SessionFactory) -> None:
    """Renova o sinal de vida dos documentos que este processo ainda tem nas mãos."""
    from app.models import Document

    ids = list(ids)
    if not ids:
        return
    try:
        with session_factory() as db:
            db.execute(
                update(Document)
                .where(Document.id.in_(ids), Document.status.in_(EM_ANDAMENTO))
                .values(analysis_updated_at=_agora())
                .execution_options(synchronize_session=False)
            )
            db.commit()
    except Exception as e:
        # Um batimento perdido não é grave: o próximo vem em BATIMENTO_SEGUNDOS, e o
        # prazo de órfã é muitas vezes maior.
        logger.warning("Batimento das análises em andamento falhou: %s", e)


# ─── Execução com retry ───

def executar_analise(
    document_id: str,
    *,
    session_factory: SessionFactory = _default_session,
    dormir: Callable[[float], None] = time.sleep,
) -> str:
    """Roda a análise com retry e devolve o desfecho.

    "analyzed", "error", "missing" (o documento sumiu) ou "abandoned" (foi marcado
    como erro por fora enquanto rodava, e o resultado foi descartado).

    Cada tentativa abre uma sessão nova: depois de uma falha no meio, a sessão
    anterior pode estar com a transação abortada.
    """
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        try:
            with session_factory() as db:
                encontrado = _analisar(db, document_id)
            return "analyzed" if encontrado else "missing"
        except AnaliseAbandonada:
            logger.warning(
                "Documento %s saiu de processing por fora (órfão?); análise descartada",
                document_id,
            )
            return "abandoned"
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
            marcado = _marcar_status(
                session_factory, document_id, "processing" if vai_retentar else "error"
            )
            if not vai_retentar:
                return "error"
            if not marcado:
                return "abandoned"

            espera = ESPERA_SOBRECARGA if categoria == "sobrecarga" else ESPERA_PADRAO
            segundos = espera[min(tentativa - 1, len(espera) - 1)]
            logger.info(
                "Retentando em %ds (%d/%d), motivo: %s",
                segundos, tentativa + 1, MAX_TENTATIVAS, categoria,
            )
            dormir(segundos)

    return "error"  # inalcançável: a última tentativa sempre retorna acima


def _marcar_status(session_factory: SessionFactory, document_id: str, status: str) -> bool:
    """Grava o status se o documento ainda está em andamento. Devolve se gravou."""
    from app.models import Document

    try:
        with session_factory() as db:
            resultado = db.execute(
                update(Document)
                .where(Document.id == document_id, Document.status.in_(EM_ANDAMENTO))
                .values(status=status, analysis_updated_at=_agora())
                .execution_options(synchronize_session=False)
            )
            db.commit()
            return bool(resultado.rowcount)
    except Exception:
        logger.exception("Não foi possível marcar o documento %s como %s", document_id, status)
        return False


def _avancar(db: Session, document_id: str, **valores) -> None:
    """Grava etapa, progresso e sinal de vida, só se o documento ainda é nosso.

    É condicional para que uma thread atrasada não ressuscite um documento já
    marcado como órfão. Se ele saiu de andamento, a análise para aqui, sem
    gastar a chamada ao LLM.
    """
    from app.models import Document

    resultado = db.execute(
        update(Document)
        .where(Document.id == document_id, Document.status.in_(EM_ANDAMENTO))
        .values(analysis_updated_at=_agora(), **valores)
        .execution_options(synchronize_session=False)
    )
    db.commit()
    if not resultado.rowcount:
        raise AnaliseAbandonada(document_id)


def _etapa(db: Session, document_id: str, stage: str, progress: int) -> None:
    _avancar(db, document_id, analysis_stage=stage, analysis_progress=progress)


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

    # Cada tentativa começa aqui, e é aqui que o documento vira processing.
    _avancar(
        db, document_id,
        status="processing", analysis_stage="extracting", analysis_progress=15,
    )
    logger.info("Status atualizado para 'processing': %s", doc.filename)

    # 2. Get the document text. The upload extracts it and stores it on the record.
    # Falling back to the file covers older records.
    extracted_text = doc.extracted_text
    if extracted_text and extracted_text.strip():
        logger.info("Texto obtido do registro: %d caracteres", len(extracted_text))
    else:
        from pathlib import Path
        from app.services.storage import arquivo_temporario, get_storage

        logger.info("Extraindo texto de %s...", doc.file_path)
        conteudo = get_storage().read(doc.file_path)
        if conteudo is None:
            raise FileNotFoundError(f"Arquivo original não encontrado: {doc.file_path}")
        with arquivo_temporario(conteudo, suffix=Path(doc.file_path).suffix) as caminho:
            extracted_text = extract_text(caminho, doc.mime_type)
        doc.extracted_text = extracted_text
        db.commit()
        logger.info("Texto extraído: %d caracteres", len(extracted_text))

    # 3. Fetch active rules for this document's scope: a document that belongs
    # to an organization follows the team's rules, otherwise the owner's own.
    _etapa(db, document_id, "loading_rules", 30)
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
    _etapa(db, document_id, "legal_context", 40)
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
    _etapa(db, document_id, "loading_feedback", 50)
    feedback_learnings = []
    try:
        feedback_learnings = load_feedback_learnings(db, doc)
        if feedback_learnings:
            logger.info("Feedback learnings carregados: %d regras com feedback", len(feedback_learnings))
    except Exception as fb_err:
        db.rollback()
        logger.warning("Feedback loading failed (continuing without): %s", fb_err)

    # 4. Call AI for analysis
    _etapa(db, document_id, "analyzing", 55)
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
    _etapa(db, document_id, "saving", 90)

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

    # A troca para analyzed é condicional e vai na mesma transação da análise. Se o
    # documento foi marcado como órfão durante a chamada ao LLM, nada é gravado: o
    # erro que o usuário já viu continua valendo, em vez de o documento voltar
    # sozinho para analisado sem que ninguém o tenha reenviado.
    concluido = db.execute(
        update(Document)
        .where(Document.id == document_id, Document.status.in_(EM_ANDAMENTO))
        .values(
            status="analyzed",
            analysis_stage=None,
            analysis_progress=100,
            analysis_updated_at=_agora(),
        )
        .execution_options(synchronize_session=False)
    )
    if not concluido.rowcount:
        db.rollback()
        raise AnaliseAbandonada(document_id)
    db.commit()

    logger.info("Análise salva com sucesso para %s", doc.filename)
    return True


# ─── Detecção de órfãs ───

def criterio_orfao(agora: Optional[datetime] = None):
    """Condição SQL de análise órfã: em andamento e sem sinal de vida no prazo."""
    from app.models import Document

    limite = (agora or _agora()) - timedelta(minutes=settings.ORPHAN_TIMEOUT_MINUTES)
    return and_(
        Document.status.in_(EM_ANDAMENTO),
        func.coalesce(Document.analysis_updated_at, Document.uploaded_at) < limite,
    )


async def marcar_analises_orfas(db, agora: Optional[datetime] = None) -> int:
    """Varredura do startup: marca como erro todas as órfãs. `db` é uma AsyncSession."""
    from app.models import Document

    resultado = await db.execute(
        update(Document)
        .where(criterio_orfao(agora))
        .values(status="error")
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    return resultado.rowcount or 0


async def marcar_se_orfao(db, document_id, agora: Optional[datetime] = None) -> bool:
    """Versão preguiçosa, para um documento só. Devolve se ele foi marcado agora.

    O UPDATE é condicional, e não um SELECT seguido de UPDATE, para que a
    decisão e a escrita sejam uma coisa só: se a thread concluir no mesmo
    instante, só um dos dois lados vence.
    """
    from app.models import Document

    resultado = await db.execute(
        update(Document)
        .where(Document.id == document_id, criterio_orfao(agora))
        .values(status="error")
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    return bool(resultado.rowcount)
