"""
Celery worker for asynchronous document analysis.

Flow:
1. Backend receives upload → creates Celery task
2. Worker extracts text from PDF/DOCX
3. Worker fetches active rules from DB
4. Worker loads feedback learnings (AI learning loop)
5. Worker calls Claude AI for analysis
6. Worker saves results to DB
7. Frontend polls for status
"""
import logging
from celery import Celery
from sqlalchemy import create_engine, select, func, case as sa_case
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.feedback_learning import load_feedback_learnings

settings = get_settings()
logger = logging.getLogger(__name__)

# ─── Celery App ───
celery_app = Celery(
    "compliance_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="America/Recife",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # A geração cresce com o tamanho do contrato e o número de alertas. Com o teto
    # de saída em 16k, uma análise longa passa dos 150s antigos, e o worker matava
    # a tarefa no meio.
    task_soft_time_limit=420,  # seconds
    task_time_limit=480,
)

# Sync engine for Celery (Celery doesn't support asyncio natively)
sync_engine = create_engine(settings.DATABASE_URL_SYNC, pool_pre_ping=True)


@celery_app.task(bind=True, name="analyze_document_task", max_retries=2)
def analyze_document_task(self, document_id: str):
    """
    Main Celery task: extract text → fetch rules → load feedback → analyze with AI → save results.
    """
    from app.models import Document, Rule, Analysis
    from app.services.document_extractor import extract_text
    from app.services.ai_analyzer import analyze_document

    logger.info(f"[Task {self.request.id}] Iniciando análise do documento {document_id}")

    with Session(sync_engine) as db:
        try:
            # 1. Fetch document
            doc = db.execute(select(Document).where(Document.id == document_id)).scalar_one_or_none()
            if not doc:
                logger.error(f"Documento {document_id} não encontrado")
                return {"status": "error", "message": "Documento não encontrado"}

            # Update status to processing
            doc.status = "processing"
            db.commit()
            logger.info(f"Status atualizado para 'processing': {doc.filename}")

            # 2. Get the document text. The API extracts it at upload time and stores
            # it on the record, since API and worker do not share a filesystem in
            # production. Falling back to the file covers local runs and older records.
            self.update_state(state="PROGRESS", meta={"stage": "extracting", "progress": 15})

            extracted_text = doc.extracted_text
            if extracted_text and extracted_text.strip():
                logger.info(f"Texto obtido do registro: {len(extracted_text)} caracteres")
            else:
                logger.info(f"Extraindo texto de {doc.file_path}...")
                extracted_text = extract_text(doc.file_path, doc.mime_type)
                doc.extracted_text = extracted_text
                db.commit()
                logger.info(f"Texto extraído: {len(extracted_text)} caracteres")

            # 3. Fetch active rules for this document's scope: a document that belongs
            # to an organization follows the team's rules, otherwise the owner's own.
            self.update_state(state="PROGRESS", meta={"stage": "loading_rules", "progress": 30})
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
            logger.info(f"Regras ativas carregadas ({scope_label}): {len(rules_data)}")

            # 3.5 Build legal context via RAG (graceful degradation)
            self.update_state(state="PROGRESS", meta={"stage": "legal_context", "progress": 40})
            legal_context = []
            try:
                from app.services.rag_service import build_legal_context_sync
                legal_context = build_legal_context_sync(extracted_text, rules_data, db)
                logger.info(f"Contexto legal RAG: {len(legal_context)} chunks relevantes")
            except Exception as rag_err:
                # Postgres aborts the whole transaction on a failed statement, so the
                # rollback is what lets the analysis still be saved further down.
                db.rollback()
                logger.warning(f"RAG context failed (continuing without): {rag_err}")

            # 3.6 Load feedback learnings for AI calibration (learning loop)
            self.update_state(state="PROGRESS", meta={"stage": "loading_feedback", "progress": 50})
            feedback_learnings = []
            try:
                feedback_learnings = load_feedback_learnings(db, doc)
                if feedback_learnings:
                    logger.info(f"Feedback learnings carregados: {len(feedback_learnings)} regras com feedback")
            except Exception as fb_err:
                db.rollback()
                logger.warning(f"Feedback loading failed (continuing without): {fb_err}")

            # 4. Call AI for analysis
            self.update_state(state="PROGRESS", meta={"stage": "analyzing", "progress": 55})
            logger.info("Enviando para análise com IA...")

            result = analyze_document(
                extracted_text, rules_data,
                legal_context=legal_context,
                feedback_learnings=feedback_learnings,
            )
            logger.info(f"Análise concluída: score={result.risk_score}, alertas={len(result.alerts)}")

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
                "Verificação: %d/%d trechos localizados no contrato, "
                "%d/%d citações apoiadas na base legal",
                resumo["excerpt_exact"], resumo["total"],
                resumo["legal_grounded"], resumo["total"],
            )
            if resumo["excerpt_unverified"] or resumo["legal_ungrounded"]:
                logger.warning(
                    "Alertas a conferir: %d com trecho não localizado, %d sem respaldo legal",
                    resumo["excerpt_unverified"], resumo["legal_ungrounded"],
                )

            # 5. Save analysis
            self.update_state(state="PROGRESS", meta={"stage": "saving", "progress": 90})

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
            )
            db.add(analysis)
            doc.status = "analyzed"
            db.commit()

            logger.info(f"✅ Análise salva com sucesso para {doc.filename}")

            return {
                "status": "completed",
                "document_id": str(doc.id),
                "risk_score": result.risk_score,
                "alerts_count": len(result.alerts),
            }

        except Exception as e:
            logger.error(f"❌ Erro na análise do documento {document_id}: {e}", exc_info=True)

            # Update document status to error
            try:
                doc = db.execute(select(Document).where(Document.id == document_id)).scalar_one_or_none()
                if doc:
                    doc.status = "error"
                    db.commit()
            except Exception:
                pass

            # Retry if attempts remain
            if self.request.retries < self.max_retries:
                logger.info(f"Retentando ({self.request.retries + 1}/{self.max_retries})...")
                raise self.retry(exc=e, countdown=10 * (self.request.retries + 1))

            return {"status": "error", "message": str(e)}
