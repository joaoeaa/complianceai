"""Marcação de alertas pelo revisor: corrigir, descartar, dar por tratado."""
import sys
import uuid as _uuid
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

    return HTML(string="<p>Contrato de teste para resolucao de alertas.</p>").write_pdf()


async def _injetar_analise(doc_id: str, alertas: list[dict]):
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
            document_id=doc.id, risk_score=70, summary="teste",
            alerts=alertas, missing_clauses=[],
        ))
        await db.commit()
    await engine.dispose()


ALERTAS = [
    {"rule_name": "Foro competente", "severity": "high", "excerpt": "x",
     "issue": "i", "suggestion": "s"},
    {"rule_name": "Vigencia indeterminada", "severity": "low", "excerpt": "y",
     "issue": "i", "suggestion": "s"},
]


async def _doc_com_analise(client: AsyncClient, headers: dict, org_id: str | None = None) -> str:
    data = {"organization_id": org_id} if org_id else None
    resp = await client.post(
        "/api/v1/documents/upload",
        files={"file": ("contrato.pdf", _pdf(), "application/pdf")},
        data=data,
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    doc_id = resp.json()["document_id"]
    await _injetar_analise(doc_id, ALERTAS)
    return doc_id


@pytest.mark.asyncio
async def test_marca_alerta_e_relatorio_devolve(client: AsyncClient, auth_headers: dict):
    doc_id = await _doc_com_analise(client, auth_headers)

    resp = await client.patch(
        f"/api/v1/documents/{doc_id}/alerts/0",
        json={"resolution": "to_fix", "comment": "Negociar com o fornecedor"},
        headers=auth_headers,
    )
    assert resp.status_code == 200

    relatorio = await client.get(f"/api/v1/documents/{doc_id}/report", headers=auth_headers)
    alertas = relatorio.json()["analysis"]["alerts"]
    assert alertas[0]["resolution"] == "to_fix"
    assert alertas[0]["resolution_comment"] == "Negociar com o fornecedor"
    assert alertas[1]["resolution"] is None


@pytest.mark.asyncio
async def test_remarcar_substitui_a_marcacao(client: AsyncClient, auth_headers: dict):
    doc_id = await _doc_com_analise(client, auth_headers)

    await client.patch(f"/api/v1/documents/{doc_id}/alerts/0",
                       json={"resolution": "to_fix"}, headers=auth_headers)
    await client.patch(f"/api/v1/documents/{doc_id}/alerts/0",
                       json={"resolution": "resolved"}, headers=auth_headers)

    relatorio = await client.get(f"/api/v1/documents/{doc_id}/report", headers=auth_headers)
    assert relatorio.json()["analysis"]["alerts"][0]["resolution"] == "resolved"


@pytest.mark.asyncio
async def test_resolution_nula_limpa_a_marcacao(client: AsyncClient, auth_headers: dict):
    doc_id = await _doc_com_analise(client, auth_headers)

    await client.patch(f"/api/v1/documents/{doc_id}/alerts/0",
                       json={"resolution": "to_fix"}, headers=auth_headers)
    await client.patch(f"/api/v1/documents/{doc_id}/alerts/0",
                       json={"resolution": None}, headers=auth_headers)

    relatorio = await client.get(f"/api/v1/documents/{doc_id}/report", headers=auth_headers)
    assert relatorio.json()["analysis"]["alerts"][0]["resolution"] is None


@pytest.mark.asyncio
async def test_indice_invalido_responde_404(client: AsyncClient, auth_headers: dict):
    doc_id = await _doc_com_analise(client, auth_headers)

    resp = await client.patch(f"/api/v1/documents/{doc_id}/alerts/99",
                              json={"resolution": "to_fix"}, headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_marcacao_respeita_o_escopo(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    """Nao se marca alerta de documento de outra conta."""
    doc_id = await _doc_com_analise(client, auth_headers)

    resp = await client.patch(f"/api/v1/documents/{doc_id}/alerts/0",
                              json={"resolution": "to_fix"}, headers=admin_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_marcacao_e_por_revisor(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    """Dois membros da equipe marcam o mesmo alerta sem se sobrescrever."""
    org = await client.post("/api/v1/organizations",
                            json={"name": "Equipe R", "slug": "equipe-r"},
                            headers=auth_headers)
    org_id = org.json()["id"]
    await client.post(f"/api/v1/organizations/{org_id}/members",
                      json={"email": "admin@test.com", "role": "member"},
                      headers=auth_headers)

    doc_id = await _doc_com_analise(client, auth_headers, org_id)

    await client.patch(f"/api/v1/documents/{doc_id}/alerts/0",
                       json={"resolution": "to_fix"}, headers=auth_headers)
    await client.patch(f"/api/v1/documents/{doc_id}/alerts/0",
                       json={"resolution": "not_applicable"}, headers=admin_headers)

    r1 = await client.get(f"/api/v1/documents/{doc_id}/report", headers=auth_headers)
    r2 = await client.get(f"/api/v1/documents/{doc_id}/report", headers=admin_headers)
    assert r1.json()["analysis"]["alerts"][0]["resolution"] == "to_fix"
    assert r2.json()["analysis"]["alerts"][0]["resolution"] == "not_applicable"
