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


# ─── Voltar ao padrão ────────────────────────────────────────────────────────
# Ninguém deveria precisar decorar quais eram as 14 regras ativas de fábrica para
# desfazer um ajuste feito durante um teste.

async def _semear_globais() -> None:
    """Insere regras globais no banco de teste.

    O seed do conjunto canônico não roda na suíte, e sem regra global não há o
    que restaurar: o que um escopo desliga numa global vira override, e é o
    override que a restauração apaga.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app import Rule

    engine = create_async_engine("sqlite+aiosqlite:///./test.db")
    Session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as db:
        db.add_all([
            Rule(name="Foro competente", severity="high", criteria="c",
                 category="geral", is_active=True),
            Rule(name="LGPD: base legal", severity="high", criteria="c",
                 category="protecao_de_dados", is_active=True),
            Rule(name="CDC: cláusulas abusivas", severity="medium", criteria="c",
                 category="consumidor", is_active=False),
            Rule(name="Locação: garantias cumuladas", severity="high", criteria="c",
                 category="locacao", is_active=False),
        ])
        await db.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_restaurar_desfaz_o_que_o_escopo_desligou(
    client: AsyncClient, auth_headers: dict
):
    await _semear_globais()

    regras = (await client.get("/api/v1/rules", headers=auth_headers)).json()
    globais = [r for r in regras if r["scope"] == "global"]
    assert globais, "esperava regras globais no conjunto"

    ativas_de_fabrica = {r["id"] for r in globais if r["is_active"]}
    alvo = next(r for r in globais if r["is_active"])

    await client.patch(f"/api/v1/rules/{alvo['id']}/toggle", headers=auth_headers)
    depois = (await client.get("/api/v1/rules", headers=auth_headers)).json()
    assert not next(r for r in depois if r["id"] == alvo["id"])["is_active"]

    resp = await client.post("/api/v1/rules/restaurar-padrao", headers=auth_headers)
    assert resp.status_code == 200

    restaurado = (await client.get("/api/v1/rules", headers=auth_headers)).json()
    assert {
        r["id"] for r in restaurado if r["scope"] == "global" and r["is_active"]
    } == ativas_de_fabrica


@pytest.mark.asyncio
async def test_restaurar_desliga_area_ligada_no_teste(
    client: AsyncClient, auth_headers: dict
):
    """O caso real: ligar Locação para um contrato e voltar atrás depois."""
    await _semear_globais()

    await client.patch("/api/v1/rules/categoria/locacao",
                       json={"is_active": True}, headers=auth_headers)
    ligadas = (await client.get("/api/v1/rules", headers=auth_headers)).json()
    assert any(r["category"] == "locacao" and r["is_active"] for r in ligadas)

    await client.post("/api/v1/rules/restaurar-padrao", headers=auth_headers)

    final = (await client.get("/api/v1/rules", headers=auth_headers)).json()
    assert not any(r["category"] == "locacao" and r["is_active"] for r in final)


@pytest.mark.asyncio
async def test_restaurar_nao_apaga_regra_propria(client: AsyncClient, auth_headers: dict):
    """Regra criada pelo usuário não tem padrão de sistema para o qual voltar."""
    await _semear_globais()

    minha = await client.post(
        "/api/v1/rules",
        json={"name": "Foro em Recife", "severity": "high",
              "criteria": "Verificar foro", "category": "geral"},
        headers=auth_headers,
    )
    minha_id = minha.json()["id"]
    await client.patch(f"/api/v1/rules/{minha_id}/toggle", headers=auth_headers)

    await client.post("/api/v1/rules/restaurar-padrao", headers=auth_headers)

    regras = (await client.get("/api/v1/rules", headers=auth_headers)).json()
    ainda = next((r for r in regras if r["id"] == minha_id), None)
    assert ainda is not None, "a regra própria foi removida"
    assert ainda["is_active"] is False, "a escolha do usuário na própria regra foi desfeita"


@pytest.mark.asyncio
async def test_restaurar_de_um_escopo_nao_afeta_o_outro(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    await _semear_globais()

    alvo = next(
        r for r in (await client.get("/api/v1/rules", headers=admin_headers)).json()
        if r["scope"] == "global" and r["is_active"]
    )
    await client.patch(f"/api/v1/rules/{alvo['id']}/toggle", headers=admin_headers)

    await client.post("/api/v1/rules/restaurar-padrao", headers=auth_headers)

    da_outra = (await client.get("/api/v1/rules", headers=admin_headers)).json()
    assert not next(r for r in da_outra if r["id"] == alvo["id"])["is_active"]
