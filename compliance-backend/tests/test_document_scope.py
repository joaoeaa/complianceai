"""Escopo dos documentos: pessoal ou de equipe.

Regra combinada: dentro de uma equipe todos os membros leem os documentos uns dos
outros, mas só quem enviou e os responsáveis pela equipe podem excluir.
"""
import sys
from functools import lru_cache
from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient

# ─── Mock Celery/Redis ───
_fake_task_result = MagicMock()
_fake_task_result.id = "fake-celery-task-id"
_mock_tasks = MagicMock()
_mock_tasks.analyze_document_task.delay.return_value = _fake_task_result
sys.modules.setdefault("app.workers.tasks", _mock_tasks)


@lru_cache(maxsize=1)
def _pdf_bytes() -> bytes:
    """PDF real com texto — o upload extrai o conteúdo do arquivo."""
    from weasyprint import HTML

    return HTML(string="<p>Contrato de teste para escopo de documentos.</p>").write_pdf()


async def _upload(client: AsyncClient, headers: dict, org_id: str | None = None) -> str:
    data = {"organization_id": org_id} if org_id else None
    resp = await client.post(
        "/api/v1/documents/upload",
        files={"file": ("contrato.pdf", _pdf_bytes(), "application/pdf")},
        data=data,
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["document_id"]


async def _create_org(client: AsyncClient, headers: dict) -> str:
    resp = await client.post(
        "/api/v1/organizations",
        json={"name": "Equipe Escopo", "slug": "equipe-escopo"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _add_member(client: AsyncClient, owner_headers: dict, org_id: str, email: str, role: str):
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/members",
        json={"email": email, "role": role},
        headers=owner_headers,
    )
    assert resp.status_code == 201, resp.text


# ─── Escopo pessoal ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_personal_document_hidden_from_others(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    doc_id = await _upload(client, auth_headers)

    resp = await client.get(f"/api/v1/documents/{doc_id}", headers=admin_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_personal_list_excludes_team_documents(
    client: AsyncClient, auth_headers: dict
):
    org_id = await _create_org(client, auth_headers)
    await _upload(client, auth_headers, org_id)
    personal_id = await _upload(client, auth_headers)

    resp = await client.get("/api/v1/documents", headers=auth_headers)
    ids = [d["id"] for d in resp.json()["documents"]]
    assert personal_id in ids
    assert len(ids) == 1  # o da equipe nao aparece no escopo pessoal


# ─── Escopo de equipe ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_team_member_reads_colleague_document(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    """Quem envia é o owner; o colega adicionado consegue abrir o documento."""
    org_id = await _create_org(client, auth_headers)
    await _add_member(client, auth_headers, org_id, "admin@test.com", "member")

    doc_id = await _upload(client, auth_headers, org_id)

    resp = await client.get(f"/api/v1/documents/{doc_id}", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == doc_id


@pytest.mark.asyncio
async def test_team_list_shows_all_members_documents(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    org_id = await _create_org(client, auth_headers)
    await _add_member(client, auth_headers, org_id, "admin@test.com", "member")

    owner_doc = await _upload(client, auth_headers, org_id)
    member_doc = await _upload(client, admin_headers, org_id)

    resp = await client.get(
        "/api/v1/documents", params={"organization_id": org_id}, headers=admin_headers
    )
    ids = [d["id"] for d in resp.json()["documents"]]
    assert owner_doc in ids and member_doc in ids


@pytest.mark.asyncio
async def test_non_member_cannot_reach_team_scope(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    org_id = await _create_org(client, auth_headers)
    doc_id = await _upload(client, auth_headers, org_id)

    resp = await client.get(
        "/api/v1/documents", params={"organization_id": org_id}, headers=admin_headers
    )
    assert resp.status_code == 404

    resp = await client.get(f"/api/v1/documents/{doc_id}", headers=admin_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_upload_to_team_requires_membership(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    org_id = await _create_org(client, auth_headers)

    resp = await client.post(
        "/api/v1/documents/upload",
        files={"file": ("contrato.pdf", _pdf_bytes(), "application/pdf")},
        data={"organization_id": org_id},
        headers=admin_headers,
    )
    assert resp.status_code == 404


# ─── Exclusão ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_member_cannot_delete_colleague_document(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    """Membro comum lê, mas não exclui o documento de outra pessoa."""
    org_id = await _create_org(client, auth_headers)
    await _add_member(client, auth_headers, org_id, "admin@test.com", "member")

    doc_id = await _upload(client, auth_headers, org_id)

    resp = await client.delete(f"/api/v1/documents/{doc_id}", headers=admin_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_author_deletes_own_team_document(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    org_id = await _create_org(client, auth_headers)
    await _add_member(client, auth_headers, org_id, "admin@test.com", "member")

    doc_id = await _upload(client, admin_headers, org_id)

    resp = await client.delete(f"/api/v1/documents/{doc_id}", headers=admin_headers)
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_org_admin_deletes_any_team_document(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    """Responsável pela equipe exclui o documento enviado por um membro."""
    org_id = await _create_org(client, auth_headers)
    await _add_member(client, auth_headers, org_id, "admin@test.com", "member")

    doc_id = await _upload(client, admin_headers, org_id)

    resp = await client.delete(f"/api/v1/documents/{doc_id}", headers=auth_headers)
    assert resp.status_code == 204


# ─── Checklist do relatorio ───────────────────────────────────────────────────

async def _inject_analysis(doc_id: str):
    """Cria uma analise minima para o documento poder gerar relatorio."""
    import uuid as _uuid

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app import Analysis, Document

    engine = create_async_engine("sqlite+aiosqlite:///./test.db")
    Session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as db:
        doc = (await db.execute(
            select(Document).where(Document.id == _uuid.UUID(doc_id))
        )).scalar_one()
        doc.status = "analyzed"
        db.add(Analysis(
            document_id=doc.id, risk_score=50, summary="teste",
            alerts=[], missing_clauses=[],
        ))
        await db.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_checklist_nao_vaza_regras_de_outra_conta(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    """O checklist do relatorio mostra so as regras do escopo do documento.

    Regressao: os endpoints de relatorio buscavam a tabela inteira, entao o
    relatorio de uma conta listava as regras criadas por outras contas.
    """
    # A outra conta cria uma regra pessoal dela.
    criada = await client.post("/api/v1/rules", json={
        "name": "Regra da outra conta", "criteria": "Criterio alheio",
    }, headers=admin_headers)
    assert criada.status_code == 201
    # Sanidade: a regra existe e esta ativa, entao uma busca sem escopo a traria.
    # Sem esta checagem, o teste passaria mesmo que o checklist viesse vazio.
    assert criada.json()["is_active"] is True

    # Esta conta envia um documento e recebe o relatorio.
    doc_id = await _upload(client, auth_headers)
    await _inject_analysis(doc_id)

    resp = await client.get(f"/api/v1/documents/{doc_id}/report", headers=auth_headers)
    assert resp.status_code == 200

    nomes = [r["name"] for r in resp.json()["rules_checked"]]
    assert "Regra da outra conta" not in nomes


@pytest.mark.asyncio
async def test_checklist_de_documento_pessoal_ignora_regra_de_equipe(
    client: AsyncClient, auth_headers: dict
):
    """Documento pessoal segue as regras pessoais, mesmo que o dono tenha equipe."""
    org_id = await _create_org(client, auth_headers)
    criada = await client.post("/api/v1/rules", json={
        "name": "Regra so da equipe", "criteria": "x", "organization_id": org_id,
    }, headers=auth_headers)
    assert criada.status_code == 201 and criada.json()["is_active"] is True

    doc_id = await _upload(client, auth_headers)  # pessoal
    await _inject_analysis(doc_id)

    resp = await client.get(f"/api/v1/documents/{doc_id}/report", headers=auth_headers)
    nomes = [r["name"] for r in resp.json()["rules_checked"]]
    assert "Regra so da equipe" not in nomes
