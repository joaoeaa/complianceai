"""Análise em background, dentro da api.

Substituiu o worker Celery. O que estes testes protegem é o que o Celery dava de
graça e agora é código nosso: o progresso que o front acompanha, o retry com
backoff, a recusa de insistir no que não vai passar, e a recuperação de uma
análise que morreu junto com o processo.

A execução roda de verdade, contra o mesmo SQLite da suíte, por uma engine
síncrona como a de produção. Só a chamada à IA e o RAG são substituídos.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from app import Analysis, Document, User
from app.services import analysis_runner
from app.services.ai_analyzer import AnalysisResult
from tests.conftest import TestSession

sync_engine = create_engine("sqlite:///./test.db")


@event.listens_for(sync_engine, "connect")
def _fks(dbapi_connection, _record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SyncSession = sessionmaker(bind=sync_engine, class_=Session, expire_on_commit=False)


def _resultado() -> AnalysisResult:
    return AnalysisResult(
        summary="Contrato com uma cláusula a revisar.",
        risk_score=42,
        alerts=[],
        missing_clauses=[],
        prompt_tokens=100,
        completion_tokens=50,
        duration_ms=10,
    )


def _criar_documento(status="uploaded", uploaded_at=None) -> str:
    with SyncSession() as db:
        user = User(
            email=f"{uuid.uuid4().hex[:8]}@teste.com",
            password_hash="x",
            full_name="Teste",
        )
        db.add(user)
        db.flush()
        doc = Document(
            user_id=user.id,
            filename="contrato.pdf",
            file_path="inexistente.pdf",
            mime_type="application/pdf",
            status=status,
            extracted_text="CLÁUSULA 1. O contratante pagará o valor combinado.",
        )
        if uploaded_at is not None:
            doc.uploaded_at = uploaded_at
        db.add(doc)
        db.commit()
        return str(doc.id)


def _documento(doc_id: str) -> Document:
    with SyncSession() as db:
        return db.execute(select(Document).where(Document.id == doc_id)).scalar_one()


@pytest.fixture
def sem_rag(monkeypatch):
    monkeypatch.setattr(
        "app.services.rag_service.build_legal_context_sync", lambda *a, **k: []
    )


# ─── Execução ───

def test_analise_grava_resultado_e_passa_pelas_etapas(monkeypatch, sem_rag):
    doc_id = _criar_documento()
    etapas_vistas = []

    def ia(*_a, **_k):
        # No meio da chamada à IA, o progresso já tem que estar no banco, que é
        # de onde o endpoint de status lê.
        doc = _documento(doc_id)
        etapas_vistas.append((doc.status, doc.analysis_stage, doc.analysis_progress))
        return _resultado()

    monkeypatch.setattr("app.services.ai_analyzer.analyze_document", ia)

    status = analysis_runner.executar_analise(doc_id, session_factory=SyncSession)

    assert status == "analyzed"
    assert etapas_vistas == [("processing", "analyzing", 55)]
    doc = _documento(doc_id)
    assert doc.status == "analyzed"
    assert doc.analysis_stage is None
    assert doc.analysis_progress == 100
    with SyncSession() as db:
        analise = db.execute(
            select(Analysis).where(Analysis.document_id == doc_id)
        ).scalar_one()
    assert analise.risk_score == 42


def test_falha_temporaria_e_retentada_com_espera(monkeypatch, sem_rag):
    doc_id = _criar_documento()
    chamadas = {"n": 0}
    esperas = []

    def ia(*_a, **_k):
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            raise Exception("Error code: 529 - overloaded_error")
        return _resultado()

    monkeypatch.setattr("app.services.ai_analyzer.analyze_document", ia)

    status = analysis_runner.executar_analise(
        doc_id, session_factory=SyncSession, dormir=esperas.append
    )

    assert status == "analyzed"
    assert chamadas["n"] == 2
    # Sobrecarga do provedor espera mais que uma falha comum.
    assert esperas == [analysis_runner.ESPERA_SOBRECARGA[0]]


def test_documento_fica_em_processing_entre_tentativas(monkeypatch, sem_rag):
    """Marcar erro antes da última tentativa fazia a tela piscar 'Erro na análise'."""
    doc_id = _criar_documento()
    status_durante_espera = []

    def ia(*_a, **_k):
        raise Exception("falha qualquer")

    monkeypatch.setattr("app.services.ai_analyzer.analyze_document", ia)

    status = analysis_runner.executar_analise(
        doc_id,
        session_factory=SyncSession,
        dormir=lambda _s: status_durante_espera.append(_documento(doc_id).status),
    )

    assert status == "error"
    assert status_durante_espera == ["processing"] * (analysis_runner.MAX_TENTATIVAS - 1)
    assert _documento(doc_id).status == "error"


def test_desiste_depois_de_tres_tentativas(monkeypatch, sem_rag):
    doc_id = _criar_documento()
    chamadas = {"n": 0}
    esperas = []

    def ia(*_a, **_k):
        chamadas["n"] += 1
        raise Exception("falha qualquer")

    monkeypatch.setattr("app.services.ai_analyzer.analyze_document", ia)

    analysis_runner.executar_analise(doc_id, session_factory=SyncSession, dormir=esperas.append)

    assert chamadas["n"] == 3
    assert esperas == list(analysis_runner.ESPERA_PADRAO)


def test_falha_que_nao_passa_com_insistencia_nao_e_retentada(monkeypatch, sem_rag):
    doc_id = _criar_documento()
    chamadas = {"n": 0}

    def ia(*_a, **_k):
        chamadas["n"] += 1
        raise ValueError("A análise excedeu o limite de resposta do modelo (16384 tokens).")

    monkeypatch.setattr("app.services.ai_analyzer.analyze_document", ia)

    status = analysis_runner.executar_analise(
        doc_id, session_factory=SyncSession, dormir=lambda _s: pytest.fail("não deveria esperar")
    )

    assert status == "error"
    assert chamadas["n"] == 1
    assert _documento(doc_id).status == "error"


def test_documento_excluido_antes_de_comecar(sem_rag):
    status = analysis_runner.executar_analise(str(uuid.uuid4()), session_factory=SyncSession)
    assert status == "missing"


# ─── Endpoint de status ───

async def test_status_mostra_a_etapa_no_formato_que_o_front_le(
    client: AsyncClient, auth_headers: dict
):
    """O front extrai a etapa com /Etapa: (\\w+) \\((\\d+)%\\)/ (App.jsx)."""
    me = (await client.get("/api/v1/auth/me", headers=auth_headers)).json()
    async with TestSession() as db:
        doc = Document(
            user_id=uuid.UUID(me["id"]),
            filename="contrato.pdf",
            file_path="x.pdf",
            status="processing",
            analysis_stage="legal_context",
            analysis_progress=40,
        )
        db.add(doc)
        await db.commit()
        doc_id = str(doc.id)

    resp = await client.get(f"/api/v1/documents/{doc_id}/status", headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json()["status"] == "processing"
    assert resp.json()["message"] == "Etapa: legal_context (40%)"


# ─── Recuperação no startup ───

async def test_startup_marca_como_erro_so_o_que_ficou_preso():
    agora = datetime.now(timezone.utc)
    antigo = agora - timedelta(minutes=30)
    recente = agora - timedelta(minutes=2)

    preso = _criar_documento("processing", uploaded_at=antigo)
    na_fila_perdido = _criar_documento("uploaded", uploaded_at=antigo)
    ainda_rodando = _criar_documento("processing", uploaded_at=recente)
    concluido = _criar_documento("analyzed", uploaded_at=antigo)

    async with TestSession() as db:
        marcados = await analysis_runner.marcar_analises_orfas(db, agora=agora)

    assert marcados == 2
    assert _documento(preso).status == "error"
    assert _documento(na_fila_perdido).status == "error"
    # Pode ser a análise que a instância antiga ainda termina durante um deploy.
    assert _documento(ainda_rodando).status == "processing"
    assert _documento(concluido).status == "analyzed"
