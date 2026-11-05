"""Taxa de conformidade do relatório.

Regressão: uma análise com checklist 0/0 mostrava "Conformidade 100%" ao lado de
"Score de risco 92 – Alto". Sem regra avaliada a taxa é nula, não 100%.
"""
import io
import re
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app import Analysis, Document
from app.services.report_generator import generate_html_report, resumo_de_regras
from tests.conftest import TestSession

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


# ─── Cálculo ─────────────────────────────────────────────────────────────────

def test_sem_regras_a_taxa_e_nula():
    alertas = [{"rule_name": "Qualquer", "severity": "high"}]
    assert resumo_de_regras([], alertas) == {
        "rules_total": 0, "rules_passed": 0, "compliance_rate": None,
    }


def test_caso_normal_conta_regras_sem_alerta():
    regras = [{"name": n} for n in ("A", "B", "C", "D")]
    alertas = [{"rule_name": "B"}, {"rule_name": "B"}]  # dois alertas, uma regra
    assert resumo_de_regras(regras, alertas) == {
        "rules_total": 4, "rules_passed": 3, "compliance_rate": 75,
    }


def test_alerta_sem_regra_correspondente_nao_reprova_ninguem():
    regras = [{"name": "A"}, {"name": "B"}]
    alertas = [{"rule_name": "Achado da IA fora do checklist"}]
    assert resumo_de_regras(regras, alertas)["compliance_rate"] == 100


def test_todas_reprovadas_e_zero_e_nao_nulo():
    """0% é um resultado; só a ausência de regras vira nulo."""
    regras = [{"name": "A"}]
    assert resumo_de_regras(regras, [{"rule_name": "A"}])["compliance_rate"] == 0


def test_arredonda_meio_para_cima_como_a_tela_fazia():
    regras = [{"name": str(i)} for i in range(8)]
    alertas = [{"rule_name": str(i)} for i in range(7)]  # 1 de 8 = 12,5%
    assert resumo_de_regras(regras, alertas)["compliance_rate"] == 13


# ─── Endpoint do relatório ───────────────────────────────────────────────────

def _docx() -> bytes:
    from docx import Document as DocxDocument

    arquivo = DocxDocument()
    arquivo.add_paragraph("Contrato de teste da taxa de conformidade.")
    buffer = io.BytesIO()
    arquivo.save(buffer)
    return buffer.getvalue()


async def _documento_analisado(client: AsyncClient, headers: dict, alertas: list) -> str:
    resp = await client.post(
        "/api/v1/documents/upload",
        files={"file": ("contrato.docx", _docx(), DOCX_MIME)},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    doc_id = resp.json()["document_id"]
    async with TestSession() as db:
        doc = (await db.execute(
            select(Document).where(Document.id == uuid.UUID(doc_id))
        )).scalar_one()
        doc.status = "analyzed"
        db.add(Analysis(
            document_id=doc.id, risk_score=92, summary="teste",
            alerts=alertas, missing_clauses=[],
        ))
        await db.commit()
    return doc_id


def _alerta(regra: str) -> dict:
    return {
        "rule_name": regra, "severity": "high", "issue": "problema",
        "excerpt": "", "suggestion": "s",
    }


@pytest.mark.asyncio
async def test_relatorio_sem_regras_devolve_taxa_nula(
    client: AsyncClient, auth_headers: dict, setup_db
):
    doc_id = await _documento_analisado(client, auth_headers, [_alerta("Achado")])

    resp = await client.get(f"/api/v1/documents/{doc_id}/report", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()
    # Sanidade: o cenário é mesmo o de nenhuma regra avaliada.
    assert data["rules_checked"] == []
    assert data["analysis"]["risk_score"] == 92
    assert data["rules_total"] == 0
    assert data["rules_passed"] == 0
    assert data["compliance_rate"] is None


@pytest.mark.asyncio
async def test_relatorio_com_regras_devolve_a_taxa(
    client: AsyncClient, auth_headers: dict, setup_db
):
    for nome in ("Foro competente", "Confidencialidade", "Vigência", "Multa"):
        criada = await client.post(
            "/api/v1/rules", json={"name": nome, "criteria": "x"}, headers=auth_headers
        )
        assert criada.status_code == 201, criada.text
    doc_id = await _documento_analisado(client, auth_headers, [_alerta("Confidencialidade")])

    resp = await client.get(f"/api/v1/documents/{doc_id}/report", headers=auth_headers)

    data = resp.json()
    assert data["rules_total"] == 4 == len(data["rules_checked"])
    assert data["rules_passed"] == 3
    assert data["compliance_rate"] == 75


# ─── PDF ─────────────────────────────────────────────────────────────────────

def _html(rules, alerts) -> str:
    return generate_html_report(
        {"filename": "c.docx", "uploaded_at": None},
        {"risk_score": 92, "summary": "s", "alerts": alerts, "missing_clauses": []},
        rules,
    )


def test_pdf_nao_mostra_percentual_de_conformidade():
    """O PDF dá contagens, não percentual: sem regra, 'Regras verificadas 0' e sem checklist."""
    sem_regras = _html([], [_alerta("Achado")])
    assert "<b>Regras verificadas</b><span>0</span>" in sem_regras
    assert "<h2>Regras verificadas</h2>" not in sem_regras
    corpo = re.sub(r"<style.*?</style>", "", sem_regras, flags=re.S)
    assert "%" not in corpo

    com_regras = _html([{"name": "A"}, {"name": "B"}], [_alerta("B")])
    assert "1 de 2 regras" in com_regras
