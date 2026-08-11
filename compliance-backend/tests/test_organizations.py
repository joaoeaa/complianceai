"""
Integration tests for the Organizations API (FASE 2).

Tests cover CRUD operations, member management, and permission checks.
"""
import sys
from unittest.mock import MagicMock

# ─── Mock Celery/Redis (same pattern as test_documents.py) ───
_fake_task_result = MagicMock()
_fake_task_result.id = "fake-celery-task-id"
_mock_tasks = MagicMock()
_mock_tasks.analyze_document_task.delay.return_value = _fake_task_result
sys.modules.setdefault("app.workers.tasks", _mock_tasks)

import pytest
from httpx import AsyncClient


# ─── Organization CRUD ────────────────────────────────────────────────────────

async def test_create_organization(client: AsyncClient, auth_headers: dict):
    resp = await client.post("/api/v1/organizations", json={
        "name": "CESAR School",
        "slug": "cesar-school",
        "cnpj": "12.345.678/0001-90",
    }, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "CESAR School"
    assert data["slug"] == "cesar-school"
    assert data["member_count"] == 1
    assert data["is_active"] is True


async def test_create_organization_duplicate_slug(client: AsyncClient, auth_headers: dict):
    await client.post("/api/v1/organizations", json={
        "name": "Org 1", "slug": "my-org",
    }, headers=auth_headers)
    resp = await client.post("/api/v1/organizations", json={
        "name": "Org 2", "slug": "my-org",
    }, headers=auth_headers)
    assert resp.status_code == 409


async def test_create_organization_unauthenticated(client: AsyncClient):
    resp = await client.post("/api/v1/organizations", json={
        "name": "Org", "slug": "org",
    })
    assert resp.status_code == 403


async def test_list_organizations_empty(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/v1/organizations", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_organizations_after_create(client: AsyncClient, auth_headers: dict):
    await client.post("/api/v1/organizations", json={
        "name": "Org A", "slug": "org-a",
    }, headers=auth_headers)
    resp = await client.get("/api/v1/organizations", headers=auth_headers)
    assert resp.status_code == 200
    orgs = resp.json()
    assert len(orgs) == 1
    assert orgs[0]["slug"] == "org-a"


async def test_get_organization_detail(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post("/api/v1/organizations", json={
        "name": "Detail Org", "slug": "detail-org",
    }, headers=auth_headers)
    org_id = create_resp.json()["id"]

    resp = await client.get(f"/api/v1/organizations/{org_id}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Detail Org"
    assert len(data["members"]) == 1
    assert data["members"][0]["role"] == "owner"
    assert data["members"][0]["user_email"] == "test@test.com"


async def test_get_organization_non_member_forbidden(client: AsyncClient, auth_headers: dict, admin_headers: dict):
    # Create org as regular user
    create_resp = await client.post("/api/v1/organizations", json={
        "name": "Private Org", "slug": "private-org",
    }, headers=auth_headers)
    org_id = create_resp.json()["id"]

    # Admin is not a member → 403
    resp = await client.get(f"/api/v1/organizations/{org_id}", headers=admin_headers)
    assert resp.status_code == 403


async def test_update_organization(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post("/api/v1/organizations", json={
        "name": "Old Name", "slug": "update-org",
    }, headers=auth_headers)
    org_id = create_resp.json()["id"]

    resp = await client.patch(f"/api/v1/organizations/{org_id}", json={
        "name": "New Name",
        "cnpj": "99.999.999/0001-99",
    }, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Name"
    assert resp.json()["cnpj"] == "99.999.999/0001-99"


async def test_delete_organization(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post("/api/v1/organizations", json={
        "name": "To Delete", "slug": "delete-org",
    }, headers=auth_headers)
    org_id = create_resp.json()["id"]

    resp = await client.delete(f"/api/v1/organizations/{org_id}", headers=auth_headers)
    assert resp.status_code == 204

    # Verify it's gone
    resp = await client.get(f"/api/v1/organizations/{org_id}", headers=auth_headers)
    assert resp.status_code == 404


async def test_delete_organization_not_owner_forbidden(client: AsyncClient, auth_headers: dict, admin_headers: dict):
    # Create org
    create_resp = await client.post("/api/v1/organizations", json={
        "name": "Owned Org", "slug": "owned-org",
    }, headers=auth_headers)
    org_id = create_resp.json()["id"]

    # Add admin as member (not owner)
    await client.post(f"/api/v1/organizations/{org_id}/members", json={
        "email": "admin@test.com", "role": "admin",
    }, headers=auth_headers)

    # Admin tries to delete → 403
    resp = await client.delete(f"/api/v1/organizations/{org_id}", headers=admin_headers)
    assert resp.status_code == 403


# ─── Member Management ────────────────────────────────────────────────────────

async def test_add_member(client: AsyncClient, auth_headers: dict, admin_headers: dict):
    create_resp = await client.post("/api/v1/organizations", json={
        "name": "Team Org", "slug": "team-org",
    }, headers=auth_headers)
    org_id = create_resp.json()["id"]

    resp = await client.post(f"/api/v1/organizations/{org_id}/members", json={
        "email": "admin@test.com", "role": "member",
    }, headers=auth_headers)
    assert resp.status_code == 201
    assert resp.json()["user_email"] == "admin@test.com"
    assert resp.json()["role"] == "member"


async def test_add_member_already_exists(client: AsyncClient, auth_headers: dict, admin_headers: dict):
    create_resp = await client.post("/api/v1/organizations", json={
        "name": "Dup Org", "slug": "dup-org",
    }, headers=auth_headers)
    org_id = create_resp.json()["id"]

    await client.post(f"/api/v1/organizations/{org_id}/members", json={
        "email": "admin@test.com", "role": "member",
    }, headers=auth_headers)

    resp = await client.post(f"/api/v1/organizations/{org_id}/members", json={
        "email": "admin@test.com", "role": "admin",
    }, headers=auth_headers)
    assert resp.status_code == 409


async def test_add_member_user_not_found(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post("/api/v1/organizations", json={
        "name": "No User Org", "slug": "no-user-org",
    }, headers=auth_headers)
    org_id = create_resp.json()["id"]

    resp = await client.post(f"/api/v1/organizations/{org_id}/members", json={
        "email": "nonexistent@test.com", "role": "member",
    }, headers=auth_headers)
    assert resp.status_code == 404


async def test_add_member_non_admin_forbidden(client: AsyncClient, auth_headers: dict, admin_headers: dict):
    # Create org as regular user
    create_resp = await client.post("/api/v1/organizations", json={
        "name": "Restricted Org", "slug": "restricted-org",
    }, headers=auth_headers)
    org_id = create_resp.json()["id"]

    # Add admin as regular member
    await client.post(f"/api/v1/organizations/{org_id}/members", json={
        "email": "admin@test.com", "role": "member",
    }, headers=auth_headers)

    # Register another user
    await client.post("/api/v1/auth/register", json={
        "email": "third@test.com", "password": "third123456",
    })

    # Admin (member role) tries to add someone → 403
    resp = await client.post(f"/api/v1/organizations/{org_id}/members", json={
        "email": "third@test.com", "role": "member",
    }, headers=admin_headers)
    assert resp.status_code == 403


async def test_update_member_role(client: AsyncClient, auth_headers: dict, admin_headers: dict):
    create_resp = await client.post("/api/v1/organizations", json={
        "name": "Role Org", "slug": "role-org",
    }, headers=auth_headers)
    org_id = create_resp.json()["id"]

    add_resp = await client.post(f"/api/v1/organizations/{org_id}/members", json={
        "email": "admin@test.com", "role": "member",
    }, headers=auth_headers)
    member_user_id = add_resp.json()["user_id"]

    resp = await client.patch(f"/api/v1/organizations/{org_id}/members/{member_user_id}", json={
        "role": "admin",
    }, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"


async def test_remove_member(client: AsyncClient, auth_headers: dict, admin_headers: dict):
    create_resp = await client.post("/api/v1/organizations", json={
        "name": "Remove Org", "slug": "remove-org",
    }, headers=auth_headers)
    org_id = create_resp.json()["id"]

    add_resp = await client.post(f"/api/v1/organizations/{org_id}/members", json={
        "email": "admin@test.com", "role": "member",
    }, headers=auth_headers)
    member_user_id = add_resp.json()["user_id"]

    resp = await client.delete(f"/api/v1/organizations/{org_id}/members/{member_user_id}", headers=auth_headers)
    assert resp.status_code == 204


async def test_cannot_remove_last_owner(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post("/api/v1/organizations", json={
        "name": "Last Owner Org", "slug": "last-owner-org",
    }, headers=auth_headers)
    org_id = create_resp.json()["id"]

    # Get owner's user_id from org detail
    detail = await client.get(f"/api/v1/organizations/{org_id}", headers=auth_headers)
    owner_user_id = detail.json()["members"][0]["user_id"]

    resp = await client.delete(f"/api/v1/organizations/{org_id}/members/{owner_user_id}", headers=auth_headers)
    assert resp.status_code == 400
    assert "proprietário" in resp.json()["detail"].lower()


async def test_list_organizations_counts_all_members(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    """member_count conta a equipe inteira, nao so quem esta consultando."""
    created = await client.post(
        "/api/v1/organizations",
        json={"name": "Contagem", "slug": "contagem"},
        headers=auth_headers,
    )
    org_id = created.json()["id"]

    await client.post(
        f"/api/v1/organizations/{org_id}/members",
        json={"email": "admin@test.com", "role": "member"},
        headers=auth_headers,
    )

    for headers in (auth_headers, admin_headers):
        resp = await client.get("/api/v1/organizations", headers=headers)
        org = next(o for o in resp.json() if o["id"] == org_id)
        assert org["member_count"] == 2


async def test_only_owner_deletes_organization(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    """Membro comum recebe 403; o dono exclui."""
    created = await client.post(
        "/api/v1/organizations",
        json={"name": "Descartavel", "slug": "descartavel"},
        headers=auth_headers,
    )
    org_id = created.json()["id"]
    await client.post(
        f"/api/v1/organizations/{org_id}/members",
        json={"email": "admin@test.com", "role": "admin"},
        headers=auth_headers,
    )

    # Nem admin da organizacao pode excluir: so o owner.
    resp = await client.delete(f"/api/v1/organizations/{org_id}", headers=admin_headers)
    assert resp.status_code == 403

    resp = await client.delete(f"/api/v1/organizations/{org_id}", headers=auth_headers)
    assert resp.status_code == 204

    resp = await client.get("/api/v1/organizations", headers=auth_headers)
    assert not any(o["id"] == org_id for o in resp.json())


async def test_deleting_org_keeps_documents_as_personal(
    client: AsyncClient, auth_headers: dict
):
    """Documentos sobrevivem a exclusao da equipe e voltam ao escopo pessoal."""
    from functools import lru_cache

    @lru_cache(maxsize=1)
    def pdf():
        from weasyprint import HTML
        return HTML(string="<p>Contrato da equipe.</p>").write_pdf()

    created = await client.post(
        "/api/v1/organizations",
        json={"name": "Temporaria", "slug": "temporaria"},
        headers=auth_headers,
    )
    org_id = created.json()["id"]

    up = await client.post(
        "/api/v1/documents/upload",
        files={"file": ("contrato.pdf", pdf(), "application/pdf")},
        data={"organization_id": org_id},
        headers=auth_headers,
    )
    doc_id = up.json()["document_id"]

    await client.delete(f"/api/v1/organizations/{org_id}", headers=auth_headers)

    resp = await client.get("/api/v1/documents", headers=auth_headers)
    assert any(d["id"] == doc_id for d in resp.json()["documents"])
