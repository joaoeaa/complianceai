"""Tests for rules CRUD endpoints.

Regras vivem em três escopos: global (padrão do sistema, somente leitura),
pessoal e de equipe. Cada escopo enxerga as globais mais as suas.
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _seed_global_rule(name: str = "Regra Global") -> str:
    """Insere uma regra global (sem dono) direto no banco, como faz o seed."""
    from tests.conftest import TestSession
    from app.models import Rule

    async with TestSession() as db:
        rule = Rule(
            name=name,
            description="Regra padrão do sistema",
            severity="high",
            criteria="Critério padrão",
            is_active=True,
        )
        db.add(rule)
        await db.commit()
        await db.refresh(rule)
        return str(rule.id)


async def _create_org(client: AsyncClient, headers: dict, name: str = "Equipe Teste") -> str:
    resp = await client.post(
        "/api/v1/organizations",
        json={"name": name, "slug": name.lower().replace(" ", "-")},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ─── Regras pessoais ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_user_can_create_own_rule(client: AsyncClient, auth_headers: dict):
    """Qualquer usuário autenticado cria regras para a própria conta."""
    resp = await client.post("/api/v1/rules", json={
        "name": "Minha Regra",
        "description": "Critério próprio",
        "severity": "high",
        "criteria": "Verificar algo específico",
    }, headers=auth_headers)

    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Minha Regra"
    assert data["scope"] == "user"
    assert data["editable"] is True


@pytest.mark.asyncio
async def test_own_rule_is_not_visible_to_others(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    """Regra pessoal de um usuário não aparece para outro."""
    await client.post("/api/v1/rules", json={
        "name": "Regra Privada", "criteria": "Só minha",
    }, headers=auth_headers)

    resp = await client.get("/api/v1/rules", headers=admin_headers)
    assert resp.status_code == 200
    assert not any(r["name"] == "Regra Privada" for r in resp.json())


@pytest.mark.asyncio
async def test_cannot_edit_someone_elses_rule(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    """Editar regra alheia responde 404 — nem confirma que ela existe."""
    created = await client.post("/api/v1/rules", json={
        "name": "Alheia", "criteria": "Critério",
    }, headers=auth_headers)
    rule_id = created.json()["id"]

    resp = await client.patch(
        f"/api/v1/rules/{rule_id}", json={"name": "Invadida"}, headers=admin_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_and_delete_own_rule(client: AsyncClient, auth_headers: dict):
    created = await client.post("/api/v1/rules", json={
        "name": "Editável", "criteria": "Critério original",
    }, headers=auth_headers)
    rule_id = created.json()["id"]

    resp = await client.patch(
        f"/api/v1/rules/{rule_id}",
        json={"name": "Editada", "severity": "low"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Editada"
    assert resp.json()["severity"] == "low"

    resp = await client.delete(f"/api/v1/rules/{rule_id}", headers=auth_headers)
    assert resp.status_code == 204


# ─── Regras globais ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_global_rule_visible_to_everyone(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    await _seed_global_rule("Foro Competente")

    for headers in (auth_headers, admin_headers):
        resp = await client.get("/api/v1/rules", headers=headers)
        assert resp.status_code == 200
        matching = [r for r in resp.json() if r["name"] == "Foro Competente"]
        assert len(matching) == 1
        assert matching[0]["scope"] == "global"
        assert matching[0]["editable"] is False


@pytest.mark.asyncio
async def test_global_rule_cannot_be_edited(client: AsyncClient, auth_headers: dict):
    rule_id = await _seed_global_rule("Confidencialidade")

    resp = await client.patch(
        f"/api/v1/rules/{rule_id}", json={"name": "Alterada"}, headers=auth_headers
    )
    assert resp.status_code == 403

    resp = await client.delete(f"/api/v1/rules/{rule_id}", headers=auth_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_toggling_global_rule_only_affects_own_scope(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    """Desativar uma regra global vale só para quem desativou."""
    rule_id = await _seed_global_rule("Prazo de Pagamento")

    resp = await client.patch(f"/api/v1/rules/{rule_id}/toggle", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    # Quem desativou vê desativada...
    mine = await client.get("/api/v1/rules", headers=auth_headers)
    assert next(r for r in mine.json() if r["id"] == rule_id)["is_active"] is False

    # ...e o outro usuário continua vendo ativa.
    theirs = await client.get("/api/v1/rules", headers=admin_headers)
    assert next(r for r in theirs.json() if r["id"] == rule_id)["is_active"] is True


@pytest.mark.asyncio
async def test_toggling_global_rule_twice_restores_it(
    client: AsyncClient, auth_headers: dict
):
    rule_id = await _seed_global_rule("Vigência Definida")

    await client.patch(f"/api/v1/rules/{rule_id}/toggle", headers=auth_headers)
    resp = await client.patch(f"/api/v1/rules/{rule_id}/toggle", headers=auth_headers)
    assert resp.json()["is_active"] is True


# ─── Regras de equipe ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_team_rule_shared_with_members(client: AsyncClient, auth_headers: dict):
    """Quem cria a organização é owner e pode criar regras para a equipe."""
    org_id = await _create_org(client, auth_headers)

    resp = await client.post("/api/v1/rules", json={
        "name": "Regra da Equipe",
        "criteria": "Critério da equipe",
        "organization_id": org_id,
    }, headers=auth_headers)
    assert resp.status_code == 201
    assert resp.json()["scope"] == "organization"

    resp = await client.get(
        "/api/v1/rules", params={"organization_id": org_id}, headers=auth_headers
    )
    assert any(r["name"] == "Regra da Equipe" for r in resp.json())


@pytest.mark.asyncio
async def test_team_rules_hidden_from_non_members(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    org_id = await _create_org(client, auth_headers)
    await client.post("/api/v1/rules", json={
        "name": "Interna", "criteria": "Critério", "organization_id": org_id,
    }, headers=auth_headers)

    resp = await client.get(
        "/api/v1/rules", params={"organization_id": org_id}, headers=admin_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_personal_rules_excluded_from_team_scope(
    client: AsyncClient, auth_headers: dict
):
    """Documento de equipe segue as regras da equipe, não as pessoais do membro."""
    org_id = await _create_org(client, auth_headers)
    await client.post("/api/v1/rules", json={
        "name": "Pessoal", "criteria": "Critério",
    }, headers=auth_headers)

    resp = await client.get(
        "/api/v1/rules", params={"organization_id": org_id}, headers=auth_headers
    )
    assert not any(r["name"] == "Pessoal" for r in resp.json())


# ─── Filtros e leitura ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_active_only_filter(client: AsyncClient, auth_headers: dict):
    created = await client.post("/api/v1/rules", json={
        "name": "Será desativada", "criteria": "Critério",
    }, headers=auth_headers)
    rule_id = created.json()["id"]
    await client.patch(f"/api/v1/rules/{rule_id}/toggle", headers=auth_headers)

    resp = await client.get(
        "/api/v1/rules", params={"active_only": True}, headers=auth_headers
    )
    assert not any(r["id"] == rule_id for r in resp.json())


@pytest.mark.asyncio
async def test_get_rule_not_found(client: AsyncClient, auth_headers: dict):
    resp = await client.get(
        "/api/v1/rules/00000000-0000-0000-0000-000000000000", headers=auth_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_rules_require_authentication(client: AsyncClient):
    resp = await client.get("/api/v1/rules")
    assert resp.status_code == 403
