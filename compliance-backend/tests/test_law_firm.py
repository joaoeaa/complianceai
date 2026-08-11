"""Camada de escritório: sigilo por cliente, log de acesso e retenção.

O que estes testes protegem é o motivo de a ferramenta poder entrar num
escritório: um advogado não designado a um caso não pode ler o caso, quem leu
fica registrado, e nada é apagado sem alguém mandar.
"""
import sys
import uuid as _uuid
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient

_fake = MagicMock()
_fake.id = "fake-task"
_mock = MagicMock()
_mock.analyze_document_task.delay.return_value = _fake
sys.modules.setdefault("app.workers.tasks", _mock)


@lru_cache(maxsize=1)
def _pdf() -> bytes:
    from weasyprint import HTML

    return HTML(string="<p>Contrato de teste da camada de escritorio.</p>").write_pdf()


async def _equipe_com_membro(client: AsyncClient, dono: dict, membro: dict) -> str:
    """Cria uma equipe e adiciona o segundo usuário como membro comum."""
    org = await client.post(
        "/api/v1/organizations",
        json={"name": "Escritório Aurora", "slug": "aurora"},
        headers=dono,
    )
    org_id = org.json()["id"]
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/members",
        json={"email": "admin@test.com", "role": "member"},
        headers=dono,
    )
    assert resp.status_code in (200, 201), resp.text
    return org_id


async def _upload(
    client: AsyncClient, headers: dict, org_id=None, client_id=None, nome="contrato.pdf"
) -> str:
    data = {}
    if org_id:
        data["organization_id"] = org_id
    if client_id:
        data["client_id"] = client_id
    resp = await client.post(
        "/api/v1/documents/upload",
        files={"file": (nome, _pdf(), "application/pdf")},
        data=data or None,
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["document_id"]


async def _com_analise(doc_id: str):
    """Dá uma análise ao documento, para o relatório existir e poder ser lido.

    Sem isso, `GET /report` responde 404, e a transação revertida leva junto a
    linha do log de acesso: por design, só entra no log o acesso que se concluiu.
    """
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app import Analysis, Document

    engine = create_async_engine("sqlite+aiosqlite:///./test.db")
    Session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as db:
        doc = (
            await db.execute(select(Document).where(Document.id == _uuid.UUID(doc_id)))
        ).scalar_one()
        doc.status = "analyzed"
        db.add(Analysis(
            document_id=doc.id, risk_score=40, summary="teste",
            alerts=[], missing_clauses=[],
        ))
        await db.commit()
    await engine.dispose()


async def _envelhecer(doc_id: str, dias: int):
    """Recua a data de upload, para o documento vencer o prazo de guarda."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app import Document

    engine = create_async_engine("sqlite+aiosqlite:///./test.db")
    Session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as db:
        doc = (
            await db.execute(select(Document).where(Document.id == _uuid.UUID(doc_id)))
        ).scalar_one()
        doc.uploaded_at = datetime.now(timezone.utc) - timedelta(days=dias)
        await db.commit()
    await engine.dispose()


# ─── Sigilo: quem enxerga o cliente ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_membro_nao_designado_nao_ve_o_cliente(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    org_id = await _equipe_com_membro(client, auth_headers, admin_headers)
    await client.post(
        "/api/v1/clients",
        json={"name": "Construtora Aurora", "organization_id": org_id},
        headers=auth_headers,
    )

    do_membro = await client.get(
        f"/api/v1/clients?organization_id={org_id}", headers=admin_headers
    )
    assert do_membro.status_code == 200
    assert do_membro.json() == []


@pytest.mark.asyncio
async def test_designado_passa_a_ver_o_cliente(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    org_id = await _equipe_com_membro(client, auth_headers, admin_headers)
    criado = await client.post(
        "/api/v1/clients",
        json={"name": "Construtora Aurora", "organization_id": org_id},
        headers=auth_headers,
    )
    cid = criado.json()["id"]

    resp = await client.post(
        f"/api/v1/clients/{cid}/assignees",
        json={"email": "admin@test.com"},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text

    vistos = await client.get(
        f"/api/v1/clients?organization_id={org_id}", headers=admin_headers
    )
    assert [c["name"] for c in vistos.json()] == ["Construtora Aurora"]


@pytest.mark.asyncio
async def test_socio_ve_todos_os_clientes_sem_designacao(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    """Owner enxerga a carteira inteira, como sócio de escritório."""
    org_id = await _equipe_com_membro(client, auth_headers, admin_headers)
    for nome in ("Cliente A", "Cliente B"):
        await client.post(
            "/api/v1/clients",
            json={"name": nome, "organization_id": org_id},
            headers=auth_headers,
        )

    vistos = await client.get(
        f"/api/v1/clients?organization_id={org_id}", headers=auth_headers
    )
    assert sorted(c["name"] for c in vistos.json()) == ["Cliente A", "Cliente B"]


@pytest.mark.asyncio
async def test_membro_comum_nao_cria_cliente(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    org_id = await _equipe_com_membro(client, auth_headers, admin_headers)
    resp = await client.post(
        "/api/v1/clients",
        json={"name": "Cliente do membro", "organization_id": org_id},
        headers=admin_headers,
    )
    assert resp.status_code == 403


# ─── Sigilo: quem enxerga o documento ────────────────────────────────────────

@pytest.mark.asyncio
async def test_documento_de_cliente_alheio_nao_e_lido(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    """O coração da camada: sem designação, o documento não existe para o membro."""
    org_id = await _equipe_com_membro(client, auth_headers, admin_headers)
    cid = (
        await client.post(
            "/api/v1/clients",
            json={"name": "Construtora Aurora", "organization_id": org_id},
            headers=auth_headers,
        )
    ).json()["id"]
    doc_id = await _upload(client, auth_headers, org_id=org_id, client_id=cid)

    detalhe = await client.get(f"/api/v1/documents/{doc_id}", headers=admin_headers)
    assert detalhe.status_code == 404

    listagem = await client.get(
        f"/api/v1/documents?organization_id={org_id}", headers=admin_headers
    )
    assert listagem.json()["total"] == 0


@pytest.mark.asyncio
async def test_documento_sem_cliente_segue_visivel_a_equipe(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    """Sem regressão para quem ainda não organizou a carteira."""
    org_id = await _equipe_com_membro(client, auth_headers, admin_headers)
    doc_id = await _upload(client, auth_headers, org_id=org_id)

    detalhe = await client.get(f"/api/v1/documents/{doc_id}", headers=admin_headers)
    assert detalhe.status_code == 200


@pytest.mark.asyncio
async def test_designacao_libera_o_documento(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    org_id = await _equipe_com_membro(client, auth_headers, admin_headers)
    cid = (
        await client.post(
            "/api/v1/clients",
            json={"name": "Construtora Aurora", "organization_id": org_id},
            headers=auth_headers,
        )
    ).json()["id"]
    doc_id = await _upload(client, auth_headers, org_id=org_id, client_id=cid)

    await client.post(
        f"/api/v1/clients/{cid}/assignees",
        json={"email": "admin@test.com"},
        headers=auth_headers,
    )
    assert (
        await client.get(f"/api/v1/documents/{doc_id}", headers=admin_headers)
    ).status_code == 200

    # Retirada a designação, o acesso se fecha de novo.
    membro_id = (
        await client.get(f"/api/v1/clients/{cid}/assignees", headers=auth_headers)
    ).json()
    alvo = next(a["user_id"] for a in membro_id if a["email"] == "admin@test.com")
    await client.delete(
        f"/api/v1/clients/{cid}/assignees/{alvo}", headers=auth_headers
    )
    assert (
        await client.get(f"/api/v1/documents/{doc_id}", headers=admin_headers)
    ).status_code == 404


@pytest.mark.asyncio
async def test_upload_em_cliente_alheio_e_recusado(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    """A checagem é na entrada também, não só na leitura."""
    org_id = await _equipe_com_membro(client, auth_headers, admin_headers)
    cid = (
        await client.post(
            "/api/v1/clients",
            json={"name": "Construtora Aurora", "organization_id": org_id},
            headers=auth_headers,
        )
    ).json()["id"]

    resp = await client.post(
        "/api/v1/documents/upload",
        files={"file": ("c.pdf", _pdf(), "application/pdf")},
        data={"organization_id": org_id, "client_id": cid},
        headers=admin_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cliente_pessoal_nao_vaza_entre_contas(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    await client.post(
        "/api/v1/clients", json={"name": "Meu cliente"}, headers=auth_headers
    )
    assert (await client.get("/api/v1/clients", headers=admin_headers)).json() == []


@pytest.mark.asyncio
async def test_designar_quem_nao_e_da_equipe_falha(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    org = await client.post(
        "/api/v1/organizations",
        json={"name": "Escritório Só Meu", "slug": "so-meu"},
        headers=auth_headers,
    )
    org_id = org.json()["id"]
    cid = (
        await client.post(
            "/api/v1/clients",
            json={"name": "Cliente X", "organization_id": org_id},
            headers=auth_headers,
        )
    ).json()["id"]

    resp = await client.post(
        f"/api/v1/clients/{cid}/assignees",
        json={"email": "admin@test.com"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


# ─── Retenção ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_documento_no_prazo_nao_entra_na_fila(
    client: AsyncClient, auth_headers: dict
):
    cid = (
        await client.post(
            "/api/v1/clients",
            json={"name": "Cliente com guarda", "retention_months": 12},
            headers=auth_headers,
        )
    ).json()["id"]
    await _upload(client, auth_headers, client_id=cid)

    fila = await client.get("/api/v1/clients/retencao/vencidos", headers=auth_headers)
    assert fila.json() == []


@pytest.mark.asyncio
async def test_documento_vencido_entra_na_fila(client: AsyncClient, auth_headers: dict):
    cid = (
        await client.post(
            "/api/v1/clients",
            json={"name": "Cliente com guarda", "retention_months": 12},
            headers=auth_headers,
        )
    ).json()["id"]
    doc_id = await _upload(client, auth_headers, client_id=cid, nome="antigo.pdf")
    await _envelhecer(doc_id, 400)

    fila = (
        await client.get("/api/v1/clients/retencao/vencidos", headers=auth_headers)
    ).json()
    assert len(fila) == 1
    assert fila[0]["filename"] == "antigo.pdf"
    assert fila[0]["days_overdue"] > 0


@pytest.mark.asyncio
async def test_cliente_sem_prazo_nunca_vence(client: AsyncClient, auth_headers: dict):
    """Nulo em retention_months guarda por tempo indeterminado, de propósito."""
    cid = (
        await client.post(
            "/api/v1/clients", json={"name": "Sem prazo"}, headers=auth_headers
        )
    ).json()["id"]
    doc_id = await _upload(client, auth_headers, client_id=cid)
    await _envelhecer(doc_id, 5000)

    fila = await client.get("/api/v1/clients/retencao/vencidos", headers=auth_headers)
    assert fila.json() == []


@pytest.mark.asyncio
async def test_expurgo_recusa_documento_dentro_do_prazo(
    client: AsyncClient, auth_headers: dict
):
    """Receber um id não pode virar caminho paralelo para apagar."""
    cid = (
        await client.post(
            "/api/v1/clients",
            json={"name": "Cliente com guarda", "retention_months": 12},
            headers=auth_headers,
        )
    ).json()["id"]
    novo = await _upload(client, auth_headers, client_id=cid, nome="novo.pdf")

    resp = await client.post(
        "/api/v1/clients/retencao/expurgar",
        json={"document_ids": [novo]},
        headers=auth_headers,
    )
    assert resp.json() == {"deleted": 0, "skipped": 1}
    assert (
        await client.get(f"/api/v1/documents/{novo}", headers=auth_headers)
    ).status_code == 200


@pytest.mark.asyncio
async def test_expurgo_apaga_o_que_venceu(client: AsyncClient, auth_headers: dict):
    cid = (
        await client.post(
            "/api/v1/clients",
            json={"name": "Cliente com guarda", "retention_months": 12},
            headers=auth_headers,
        )
    ).json()["id"]
    velho = await _upload(client, auth_headers, client_id=cid, nome="velho.pdf")
    novo = await _upload(client, auth_headers, client_id=cid, nome="novo.pdf")
    await _envelhecer(velho, 400)

    resp = await client.post(
        "/api/v1/clients/retencao/expurgar",
        json={"document_ids": [velho, novo]},
        headers=auth_headers,
    )
    assert resp.json() == {"deleted": 1, "skipped": 1}
    assert (
        await client.get(f"/api/v1/documents/{velho}", headers=auth_headers)
    ).status_code == 404
    assert (
        await client.get(f"/api/v1/documents/{novo}", headers=auth_headers)
    ).status_code == 200


@pytest.mark.asyncio
async def test_excluir_cliente_nao_apaga_documento(
    client: AsyncClient, auth_headers: dict
):
    cid = (
        await client.post(
            "/api/v1/clients", json={"name": "Cliente que sai"}, headers=auth_headers
        )
    ).json()["id"]
    doc_id = await _upload(client, auth_headers, client_id=cid)

    assert (
        await client.delete(f"/api/v1/clients/{cid}", headers=auth_headers)
    ).status_code == 204
    assert (
        await client.get(f"/api/v1/documents/{doc_id}", headers=auth_headers)
    ).status_code == 200


# ─── Log de acesso ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_leitura_de_relatorio_fica_registrada(
    client: AsyncClient, auth_headers: dict
):
    doc_id = await _upload(client, auth_headers, nome="registrado.pdf")
    await _com_analise(doc_id)
    await client.get(f"/api/v1/documents/{doc_id}/report", headers=auth_headers)

    log = (
        await client.get("/api/v1/clients/auditoria/acessos", headers=auth_headers)
    ).json()
    acoes = [linha["action"] for linha in log]
    assert "view" in acoes
    assert any(linha["detail"] == "registrado.pdf" for linha in log)


@pytest.mark.asyncio
async def test_log_sobrevive_a_exclusao_do_documento(
    client: AsyncClient, auth_headers: dict
):
    """Saber que alguém leu um documento hoje apagado é o que a auditoria quer."""
    doc_id = await _upload(client, auth_headers, nome="some.pdf")
    await _com_analise(doc_id)
    await client.get(f"/api/v1/documents/{doc_id}/report", headers=auth_headers)
    await client.delete(f"/api/v1/documents/{doc_id}", headers=auth_headers)

    log = (
        await client.get("/api/v1/clients/auditoria/acessos", headers=auth_headers)
    ).json()
    assert any(linha["detail"] == "some.pdf" for linha in log)


@pytest.mark.asyncio
async def test_membro_comum_nao_le_o_log_da_equipe(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    """O log diz quem leu o quê; abri-lo a todos seria uma segunda via de vazamento."""
    org_id = await _equipe_com_membro(client, auth_headers, admin_headers)

    resp = await client.get(
        f"/api/v1/clients/auditoria/acessos?organization_id={org_id}",
        headers=admin_headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_log_pessoal_nao_mostra_acesso_de_outra_conta(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    doc_id = await _upload(client, auth_headers, nome="privado.pdf")
    await _com_analise(doc_id)
    await client.get(f"/api/v1/documents/{doc_id}/report", headers=auth_headers)

    log = (
        await client.get("/api/v1/clients/auditoria/acessos", headers=admin_headers)
    ).json()
    assert all(linha["detail"] != "privado.pdf" for linha in log)


@pytest.mark.asyncio
async def test_designacao_fica_registrada(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    org_id = await _equipe_com_membro(client, auth_headers, admin_headers)
    cid = (
        await client.post(
            "/api/v1/clients",
            json={"name": "Construtora Aurora", "organization_id": org_id},
            headers=auth_headers,
        )
    ).json()["id"]
    await client.post(
        f"/api/v1/clients/{cid}/assignees",
        json={"email": "admin@test.com"},
        headers=auth_headers,
    )

    log = (
        await client.get(
            f"/api/v1/clients/auditoria/acessos?organization_id={org_id}",
            headers=auth_headers,
        )
    ).json()
    assert any(
        linha["action"] == "assign" and linha["client_name"] == "Construtora Aurora"
        for linha in log
    )
