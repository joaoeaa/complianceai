"""Regras agrupadas por área do direito.

Uma revisão de contrato de locação precisa das cinco regras de locação ligadas e,
ao terminar, desligadas. Ligar uma a uma é o atrito que faz o usuário deixar tudo
ligado e conviver com falso positivo, então a área inteira liga de uma vez.
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_regra_criada_guarda_a_area(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/v1/rules",
        json={
            "name": "Renúncia à renovatória",
            "severity": "high",
            "criteria": "Verificar renúncia ao direito de renovação",
            "category": "locacao",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["category"] == "locacao"


@pytest.mark.asyncio
async def test_area_omitida_cai_em_geral(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/v1/rules",
        json={"name": "Foro", "severity": "low", "criteria": "Verificar foro"},
        headers=auth_headers,
    )
    assert resp.json()["category"] == "geral"


async def _tres_de_locacao(client: AsyncClient, headers: dict) -> list[str]:
    ids = []
    for i in range(3):
        resp = await client.post(
            "/api/v1/rules",
            json={
                "name": f"Locação {i}",
                "severity": "medium",
                "criteria": "c",
                "category": "locacao",
            },
            headers=headers,
        )
        ids.append(resp.json()["id"])
    return ids


@pytest.mark.asyncio
async def test_desliga_a_area_inteira(client: AsyncClient, auth_headers: dict):
    ids = await _tres_de_locacao(client, auth_headers)

    resp = await client.patch(
        "/api/v1/rules/categoria/locacao",
        json={"is_active": False},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert {r["id"] for r in resp.json()} == set(ids)
    assert all(r["is_active"] is False for r in resp.json())

    regras = (await client.get("/api/v1/rules", headers=auth_headers)).json()
    por_id = {r["id"]: r for r in regras}
    assert all(por_id[i]["is_active"] is False for i in ids)


@pytest.mark.asyncio
async def test_ligar_area_nao_toca_nas_outras(client: AsyncClient, auth_headers: dict):
    await _tres_de_locacao(client, auth_headers)
    outra = await client.post(
        "/api/v1/rules",
        json={"name": "LGPD", "severity": "high", "criteria": "c",
              "category": "protecao_de_dados"},
        headers=auth_headers,
    )
    outra_id = outra.json()["id"]

    await client.patch("/api/v1/rules/categoria/locacao",
                       json={"is_active": False}, headers=auth_headers)

    regras = (await client.get("/api/v1/rules", headers=auth_headers)).json()
    por_id = {r["id"]: r for r in regras}
    assert por_id[outra_id]["is_active"] is True


@pytest.mark.asyncio
async def test_area_inexistente_responde_404(client: AsyncClient, auth_headers: dict):
    resp = await client.patch(
        "/api/v1/rules/categoria/direito_espacial",
        json={"is_active": False},
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_area_de_uma_conta_nao_afeta_a_outra(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    """Desligar uma área é preferência de escopo, não mudança global."""
    ids = await _tres_de_locacao(client, auth_headers)

    await client.patch("/api/v1/rules/categoria/locacao",
                       json={"is_active": False}, headers=auth_headers)

    # A outra conta nem enxerga essas regras, e as suas continuam intactas.
    regras = (await client.get("/api/v1/rules", headers=admin_headers)).json()
    assert not ({r["id"] for r in regras} & set(ids))


@pytest.mark.asyncio
async def test_todas_as_regras_padrao_tem_area_conhecida():
    from app.scripts.seed_rules import DEFAULT_RULES

    conhecidas = {
        "geral", "protecao_de_dados", "civil", "trabalhista", "consumidor",
        "anticorrupcao", "internet", "licitacoes", "locacao", "societario",
        "propriedade_industrial",
    }
    for regra in DEFAULT_RULES:
        assert regra.get("category") in conhecidas, regra["name"]


@pytest.mark.asyncio
async def test_areas_especificas_vem_desligadas():
    """Regra de locação não deve alertar num contrato de TI."""
    from app.scripts.seed_rules import DEFAULT_RULES

    especificas = {"locacao", "societario", "propriedade_industrial"}
    for regra in DEFAULT_RULES:
        if regra["category"] in especificas:
            assert regra["is_active"] is False, regra["name"]
