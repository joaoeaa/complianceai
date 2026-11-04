"""Análise em background, dentro da api.

Substituiu o worker Celery. O que estes testes protegem é o que o Celery dava de
graça e agora é código nosso: o progresso que o front acompanha, o retry com
backoff, a recusa de insistir no que não vai passar, e a detecção da análise que
morreu junto com o processo, sem condenar a que só está demorando.

A execução roda de verdade, contra o mesmo SQLite da suíte, por uma engine
síncrona como a de produção. Só a chamada à IA e o RAG são substituídos.
"""
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, event, func, select, update
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

AGORA = datetime.now(timezone.utc)
VELHO = AGORA - timedelta(minutes=30)    # passou do prazo padrão de 12 minutos
RECENTE = AGORA - timedelta(minutes=2)   # dentro do prazo


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


def _criar_documento(
    status="uploaded", uploaded_at=None, analysis_updated_at=None, user_id=None
) -> str:
    with SyncSession() as db:
        if user_id is None:
            user = User(
                email=f"{uuid.uuid4().hex[:8]}@teste.com",
                password_hash="x",
                full_name="Teste",
            )
            db.add(user)
            db.flush()
            user_id = user.id
        doc = Document(
            user_id=user_id,
            filename="contrato.pdf",
            file_path="inexistente.pdf",
            mime_type="application/pdf",
            status=status,
            extracted_text="CLÁUSULA 1. O contratante pagará o valor combinado.",
            analysis_updated_at=analysis_updated_at,
        )
        if uploaded_at is not None:
            doc.uploaded_at = uploaded_at
        db.add(doc)
        db.commit()
        return str(doc.id)


def _documento(doc_id: str) -> Document:
    with SyncSession() as db:
        return db.execute(select(Document).where(Document.id == doc_id)).scalar_one()


def _marcar_erro_por_fora(doc_id: str) -> None:
    """O que a varredura ou o endpoint de status fazem com uma órfã."""
    with SyncSession() as db:
        db.execute(update(Document).where(Document.id == doc_id).values(status="error"))
        db.commit()


def _analises_de(doc_id: str) -> int:
    with SyncSession() as db:
        return db.execute(
            select(func.count()).select_from(Analysis).where(Analysis.document_id == doc_id)
        ).scalar()


async def _meu_id(client: AsyncClient, headers: dict) -> uuid.UUID:
    return uuid.UUID((await client.get("/api/v1/auth/me", headers=headers)).json()["id"])


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


def test_cada_etapa_renova_o_sinal_de_vida(monkeypatch, sem_rag):
    doc_id = _criar_documento(analysis_updated_at=VELHO)
    visto = []

    def ia(*_a, **_k):
        visto.append(_documento(doc_id).analysis_updated_at)
        return _resultado()

    monkeypatch.setattr("app.services.ai_analyzer.analyze_document", ia)
    analysis_runner.executar_analise(doc_id, session_factory=SyncSession)

    # SQLite devolve sem fuso; o valor gravado é UTC.
    assert visto[0].replace(tzinfo=timezone.utc) > RECENTE


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


def test_nova_tentativa_renova_o_sinal_de_vida(monkeypatch, sem_rag):
    """Durante a espera entre tentativas não há etapa nova, mas há sinal de vida."""
    doc_id = _criar_documento()
    durante_espera = []

    def ia(*_a, **_k):
        # Envelhece o sinal no momento da falha. Entre isto e a espera, só a
        # marcação da nova tentativa pode tê-lo renovado.
        with SyncSession() as db:
            db.execute(
                update(Document).where(Document.id == doc_id).values(analysis_updated_at=VELHO)
            )
            db.commit()
        raise Exception("falha qualquer")

    monkeypatch.setattr("app.services.ai_analyzer.analyze_document", ia)

    def dormir(_s):
        doc = _documento(doc_id)
        durante_espera.append(doc.analysis_updated_at.replace(tzinfo=timezone.utc) > RECENTE)

    analysis_runner.executar_analise(doc_id, session_factory=SyncSession, dormir=dormir)
    assert durante_espera == [True] * (analysis_runner.MAX_TENTATIVAS - 1)


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


# ─── Caso 3: a thread não desfaz o error ───

def test_thread_que_termina_depois_nao_sobrescreve_o_error(monkeypatch, sem_rag):
    """Marcado como órfão durante a chamada ao LLM: o resultado é descartado."""
    doc_id = _criar_documento()

    def ia(*_a, **_k):
        _marcar_erro_por_fora(doc_id)
        return _resultado()

    monkeypatch.setattr("app.services.ai_analyzer.analyze_document", ia)

    status = analysis_runner.executar_analise(doc_id, session_factory=SyncSession)

    assert status == "abandoned"
    assert _documento(doc_id).status == "error"
    # Nem a análise fica gravada: o documento em erro não pode ter relatório.
    assert _analises_de(doc_id) == 0


def test_marcado_no_ultimo_instante_antes_de_concluir(monkeypatch, sem_rag):
    """A janela que sobra: depois da última etapa e antes da troca para analyzed.

    É onde a thread concorre de fato com o endpoint de status. A troca precisa ser
    condicional e levar a análise junto, ou o documento volta a analisado.
    """
    doc_id = _criar_documento()
    monkeypatch.setattr("app.services.ai_analyzer.analyze_document", lambda *a, **k: _resultado())
    etapa_real = analysis_runner._etapa

    def etapa(db, document_id, stage, progress):
        etapa_real(db, document_id, stage, progress)
        if stage == "saving":
            _marcar_erro_por_fora(doc_id)

    monkeypatch.setattr(analysis_runner, "_etapa", etapa)

    status = analysis_runner.executar_analise(doc_id, session_factory=SyncSession)

    assert status == "abandoned"
    assert _documento(doc_id).status == "error"
    assert _analises_de(doc_id) == 0


def test_falha_em_documento_ja_marcado_nao_espera_nem_retenta(monkeypatch, sem_rag):
    """Marcado durante a tentativa que falhou: não há por que esperar o backoff."""
    doc_id = _criar_documento()

    def ia(*_a, **_k):
        _marcar_erro_por_fora(doc_id)
        raise Exception("falha qualquer")

    monkeypatch.setattr("app.services.ai_analyzer.analyze_document", ia)

    status = analysis_runner.executar_analise(
        doc_id, session_factory=SyncSession, dormir=lambda _s: pytest.fail("não deveria esperar")
    )

    assert status == "abandoned"
    assert _documento(doc_id).status == "error"


def test_documento_marcado_antes_de_a_thread_comecar_nao_chama_a_ia(monkeypatch, sem_rag):
    doc_id = _criar_documento(status="error")
    monkeypatch.setattr(
        "app.services.ai_analyzer.analyze_document",
        lambda *a, **k: pytest.fail("não deveria chamar a IA"),
    )

    assert analysis_runner.executar_analise(doc_id, session_factory=SyncSession) == "abandoned"
    assert _documento(doc_id).status == "error"


def test_documento_marcado_durante_a_espera_nao_e_retentado(monkeypatch, sem_rag):
    doc_id = _criar_documento()
    chamadas = {"n": 0}

    def ia(*_a, **_k):
        chamadas["n"] += 1
        raise Exception("falha qualquer")

    monkeypatch.setattr("app.services.ai_analyzer.analyze_document", ia)

    status = analysis_runner.executar_analise(
        doc_id, session_factory=SyncSession, dormir=lambda _s: _marcar_erro_por_fora(doc_id)
    )

    assert status == "abandoned"
    assert chamadas["n"] == 1
    assert _documento(doc_id).status == "error"


# ─── Endpoint de status ───

async def test_status_mostra_a_etapa_no_formato_que_o_front_le(
    client: AsyncClient, auth_headers: dict
):
    """O front extrai a etapa com /Etapa: (\\w+) \\((\\d+)%\\)/ (App.jsx)."""
    async with TestSession() as db:
        doc = Document(
            user_id=await _meu_id(client, auth_headers),
            filename="contrato.pdf",
            file_path="x.pdf",
            status="processing",
            analysis_stage="legal_context",
            analysis_progress=40,
            analysis_updated_at=RECENTE,
        )
        db.add(doc)
        await db.commit()
        doc_id = str(doc.id)

    resp = await client.get(f"/api/v1/documents/{doc_id}/status", headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json()["status"] == "processing"
    assert resp.json()["message"] == "Etapa: legal_context (40%)"


# ─── Caso 2: detecção preguiçosa no status ───

async def test_status_de_documento_orfao_responde_e_grava_error(
    client: AsyncClient, auth_headers: dict
):
    doc_id = _criar_documento(
        "processing", uploaded_at=VELHO, analysis_updated_at=VELHO,
        user_id=await _meu_id(client, auth_headers),
    )

    resp = await client.get(f"/api/v1/documents/{doc_id}/status", headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json()["status"] == "error"
    assert _documento(doc_id).status == "error"


async def test_status_de_analise_longa_mas_viva_nao_e_condenado(
    client: AsyncClient, auth_headers: dict
):
    """Enviado há muito tempo, mas com sinal de vida recente: ainda está rodando."""
    doc_id = _criar_documento(
        "processing",
        uploaded_at=AGORA - timedelta(hours=2),
        analysis_updated_at=RECENTE,
        user_id=await _meu_id(client, auth_headers),
    )

    resp = await client.get(f"/api/v1/documents/{doc_id}/status", headers=auth_headers)

    assert resp.json()["status"] == "processing"
    assert _documento(doc_id).status == "processing"


async def test_status_de_orfao_alheio_nao_marca_nada(client: AsyncClient, auth_headers: dict):
    """A checagem de acesso vem antes: quem não lê o documento não escreve nele."""
    doc_id = _criar_documento("processing", uploaded_at=VELHO, analysis_updated_at=VELHO)

    resp = await client.get(f"/api/v1/documents/{doc_id}/status", headers=auth_headers)

    assert resp.status_code == 404
    assert _documento(doc_id).status == "processing"


# ─── Caso 1: varredura do startup ───

async def test_startup_marca_como_erro_so_o_que_ficou_sem_sinal_de_vida():
    sem_sinal = _criar_documento("processing", uploaded_at=VELHO, analysis_updated_at=VELHO)
    longa_e_viva = _criar_documento(
        "processing", uploaded_at=AGORA - timedelta(hours=2), analysis_updated_at=RECENTE
    )
    # Sem analysis_updated_at, vale a data do upload.
    na_fila_perdido = _criar_documento("uploaded", uploaded_at=VELHO)
    na_fila_recente = _criar_documento("uploaded", uploaded_at=RECENTE)
    concluido = _criar_documento("analyzed", uploaded_at=VELHO, analysis_updated_at=VELHO)

    async with TestSession() as db:
        marcados = await analysis_runner.marcar_analises_orfas(db, agora=AGORA)

    assert marcados == 2
    assert _documento(sem_sinal).status == "error"
    assert _documento(na_fila_perdido).status == "error"
    assert _documento(longa_e_viva).status == "processing"
    assert _documento(na_fila_recente).status == "uploaded"
    assert _documento(concluido).status == "analyzed"


async def test_prazo_de_orfa_vem_da_configuracao(monkeypatch):
    monkeypatch.setattr(analysis_runner.settings, "ORPHAN_TIMEOUT_MINUTES", 60)
    doc_id = _criar_documento("processing", uploaded_at=VELHO, analysis_updated_at=VELHO)

    async with TestSession() as db:
        assert await analysis_runner.marcar_analises_orfas(db, agora=AGORA) == 0
    assert _documento(doc_id).status == "processing"


# ─── Batimento ───

def test_batimento_renova_so_o_que_esta_em_andamento():
    vivo = _criar_documento("processing", analysis_updated_at=VELHO)
    marcado = _criar_documento("error", analysis_updated_at=VELHO)

    analysis_runner.tocar_em_andamento([vivo, marcado], SyncSession)

    assert _documento(vivo).analysis_updated_at.replace(tzinfo=timezone.utc) > RECENTE
    # Renovar um documento já em erro não o traria de volta, mas confundiria quem
    # investiga quando ele morreu.
    assert _documento(marcado).analysis_updated_at.replace(tzinfo=timezone.utc) < RECENTE


def test_batimento_roda_enquanto_ha_analise_e_para_depois(monkeypatch):
    """Sem análise em andamento, não pode sobrar thread nem consulta periódica."""
    monkeypatch.setattr(analysis_runner, "BATIMENTO_SEGUNDOS", 0.05)
    monkeypatch.setattr(analysis_runner, "_default_session", SyncSession)
    doc_id = _criar_documento("uploaded", analysis_updated_at=VELHO)

    analysis_runner._registrar(doc_id)
    thread = analysis_runner._batimento
    try:
        prazo = time.monotonic() + 5
        while time.monotonic() < prazo:
            atual = _documento(doc_id).analysis_updated_at.replace(tzinfo=timezone.utc)
            if atual > RECENTE:
                break
            time.sleep(0.05)
        else:
            pytest.fail("o batimento não renovou o sinal de vida")
    finally:
        analysis_runner._desregistrar(doc_id)

    thread.join(timeout=5)
    assert not thread.is_alive()
    assert analysis_runner._batimento is None
