"""
Integration tests for the Contract Templates API (FASE 2).

Templates are scoped to organizations. Tests cover CRUD operations
and permission checks.
"""
import sys
from unittest.mock import MagicMock

# ─── Mock Celery/Redis ───
_fake_task_result = MagicMock()
_fake_task_result.id = "fake-celery-task-id"
_mock_tasks = MagicMock()
_mock_tasks.analyze_document_task.delay.return_value = _fake_task_result
sys.modules.setdefault("app.workers.tasks", _mock_tasks)

import pytest
import pytest_asyncio
from httpx import AsyncClient


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _create_org(client: AsyncClient, headers: dict, slug: str = "tpl-org") -> str:
    """Create an org and return its id."""
    resp = await client.post("/api/v1/organizations", json={
        "name": "Template Test Org",
        "slug": slug,
    }, headers=headers)
    assert resp.status_code == 201
    return resp.json()["id"]


def _tpl_url(org_id: str, tpl_id: str = "") -> str:
    base = f"/api/v1/organizations/{org_id}/templates"
    return f"{base}/{tpl_id}" if tpl_id else base


# ─── Template CRUD ────────────────────────────────────────────────────────────

async def test_create_template(client: AsyncClient, auth_headers: dict):
    org_id = await _create_org(client, auth_headers)
    resp = await client.post(_tpl_url(org_id), json={
        "name": "NDA Padrão",
        "description": "Template para NDAs",
        "category": "nda",
        "rule_ids": [],
        "custom_instructions": "Verificar cláusula de não-competição.",
    }, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "NDA Padrão"
    assert data["category"] == "nda"
    assert data["organization_id"] == org_id
    assert data["is_active"] is True


async def test_create_template_non_admin_forbidden(client: AsyncClient, auth_headers: dict, admin_headers: dict):
    org_id = await _create_org(client, auth_headers)

    # Add admin as regular member
    await client.post(f"/api/v1/organizations/{org_id}/members", json={
        "email": "admin@test.com", "role": "member",
    }, headers=auth_headers)

    # Member tries to create template → 403
    resp = await client.post(_tpl_url(org_id), json={
        "name": "Forbidden", "category": "geral",
    }, headers=admin_headers)
    assert resp.status_code == 403


async def test_create_template_unauthenticated(client: AsyncClient, auth_headers: dict):
    org_id = await _create_org(client, auth_headers)
    resp = await client.post(_tpl_url(org_id), json={
        "name": "Unauth", "category": "geral",
    })
    assert resp.status_code == 403


async def test_list_templates_empty(client: AsyncClient, auth_headers: dict):
    org_id = await _create_org(client, auth_headers)
    resp = await client.get(_tpl_url(org_id), headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["templates"] == []
    assert resp.json()["total"] == 0


async def test_list_templates_after_create(client: AsyncClient, auth_headers: dict):
    org_id = await _create_org(client, auth_headers)

    await client.post(_tpl_url(org_id), json={
        "name": "Template A", "category": "nda",
    }, headers=auth_headers)
    await client.post(_tpl_url(org_id), json={
        "name": "Template B", "category": "servico",
    }, headers=auth_headers)

    resp = await client.get(_tpl_url(org_id), headers=auth_headers)
    data = resp.json()
    assert data["total"] == 2


async def test_list_templates_filter_by_category(client: AsyncClient, auth_headers: dict):
    org_id = await _create_org(client, auth_headers)

    await client.post(_tpl_url(org_id), json={
        "name": "NDA 1", "category": "nda",
    }, headers=auth_headers)
    await client.post(_tpl_url(org_id), json={
        "name": "Serviço 1", "category": "servico",
    }, headers=auth_headers)

    resp = await client.get(_tpl_url(org_id), params={"category": "nda"}, headers=auth_headers)
    data = resp.json()
    assert data["total"] == 1
    assert data["templates"][0]["category"] == "nda"


async def test_list_templates_non_member_forbidden(client: AsyncClient, auth_headers: dict, admin_headers: dict):
    org_id = await _create_org(client, auth_headers)

    resp = await client.get(_tpl_url(org_id), headers=admin_headers)
    assert resp.status_code == 403


async def test_get_template(client: AsyncClient, auth_headers: dict):
    org_id = await _create_org(client, auth_headers)
    create_resp = await client.post(_tpl_url(org_id), json={
        "name": "Get Test", "category": "geral",
    }, headers=auth_headers)
    tpl_id = create_resp.json()["id"]

    resp = await client.get(_tpl_url(org_id, tpl_id), headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Get Test"


async def test_get_template_not_found(client: AsyncClient, auth_headers: dict):
    org_id = await _create_org(client, auth_headers)
    resp = await client.get(
        _tpl_url(org_id, "00000000-0000-0000-0000-000000000000"),
        headers=auth_headers,
    )
    assert resp.status_code == 404


async def test_update_template(client: AsyncClient, auth_headers: dict):
    org_id = await _create_org(client, auth_headers)
    create_resp = await client.post(_tpl_url(org_id), json={
        "name": "Old Name", "category": "geral",
    }, headers=auth_headers)
    tpl_id = create_resp.json()["id"]

    resp = await client.patch(_tpl_url(org_id, tpl_id), json={
        "name": "New Name",
        "category": "nda",
        "custom_instructions": "Novas instruções.",
    }, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "New Name"
    assert data["category"] == "nda"
    assert data["custom_instructions"] == "Novas instruções."


async def test_update_template_toggle_active(client: AsyncClient, auth_headers: dict):
    org_id = await _create_org(client, auth_headers)
    create_resp = await client.post(_tpl_url(org_id), json={
        "name": "Toggle", "category": "geral",
    }, headers=auth_headers)
    tpl_id = create_resp.json()["id"]

    resp = await client.patch(_tpl_url(org_id, tpl_id), json={
        "is_active": False,
    }, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    # Inactive templates filtered out by default
    list_resp = await client.get(_tpl_url(org_id), headers=auth_headers)
    assert list_resp.json()["total"] == 0

    # But visible with active_only=false
    list_resp = await client.get(_tpl_url(org_id), params={"active_only": "false"}, headers=auth_headers)
    assert list_resp.json()["total"] == 1


async def test_delete_template(client: AsyncClient, auth_headers: dict):
    org_id = await _create_org(client, auth_headers)
    create_resp = await client.post(_tpl_url(org_id), json={
        "name": "To Delete", "category": "geral",
    }, headers=auth_headers)
    tpl_id = create_resp.json()["id"]

    resp = await client.delete(_tpl_url(org_id, tpl_id), headers=auth_headers)
    assert resp.status_code == 204

    # Verify it's gone
    resp = await client.get(_tpl_url(org_id, tpl_id), headers=auth_headers)
    assert resp.status_code == 404


async def test_delete_template_non_admin_forbidden(client: AsyncClient, auth_headers: dict, admin_headers: dict):
    org_id = await _create_org(client, auth_headers)

    # Add admin as member
    await client.post(f"/api/v1/organizations/{org_id}/members", json={
        "email": "admin@test.com", "role": "member",
    }, headers=auth_headers)

    create_resp = await client.post(_tpl_url(org_id), json={
        "name": "Protected", "category": "geral",
    }, headers=auth_headers)
    tpl_id = create_resp.json()["id"]

    # Member tries to delete → 403
    resp = await client.delete(_tpl_url(org_id, tpl_id), headers=admin_headers)
    assert resp.status_code == 403


async def test_template_with_rule_ids(client: AsyncClient, auth_headers: dict, admin_headers: dict):
    """Create a template referencing rule IDs and verify they persist."""
    org_id = await _create_org(client, auth_headers)

    # Create a rule first (need admin)
    # Add admin to org
    await client.post(f"/api/v1/organizations/{org_id}/members", json={
        "email": "admin@test.com", "role": "admin",
    }, headers=auth_headers)

    rule_resp = await client.post("/api/v1/rules", json={
        "name": "Regra Teste",
        "severity": "high",
        "criteria": "Critério teste",
    }, headers=admin_headers)
    rule_id = rule_resp.json()["id"]

    resp = await client.post(_tpl_url(org_id), json={
        "name": "Template com Regras",
        "category": "compliance",
        "rule_ids": [rule_id],
    }, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert len(data["rule_ids"]) == 1
    assert data["rule_ids"][0] == rule_id
