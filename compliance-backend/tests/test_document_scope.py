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
