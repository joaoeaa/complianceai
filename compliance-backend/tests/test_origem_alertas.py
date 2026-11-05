"""Alertas de regra e achados livres (prompt v4).

Regressão: com regras ativas, o modelo passava a apontar só as regras
reprovadas, e juros abusivos, retenção indefinida de dados e cessão da base de
dados sumiam do relatório. O prompt agora pede as duas coisas, e cada alerta sai
com "origin". A origem é conferida em código contra os nomes das regras, porque
o checklist conta como reprovada a regra que tem alerta com o nome dela.
"""
import json
import re
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient

from app.schemas import AlertSchema
from app.services.ai_analyzer import (
    MAX_ACHADOS_LIVRES,
    PROMPT_VERSION,
    _build_legal_context_section,
    _build_user_prompt,
    _parse_llm_response,
    analyze_document,
)
from app.services.report_generator import generate_html_report, resumo_de_regras
from tests.test_compliance_rate import _documento_analisado

REGRAS = ["LGPD: retenção e eliminação", "Foro competente"]


def _resposta(*alertas) -> str:
    return json.dumps({
        "summary": "s", "risk_score": 80, "missing_clauses": [],
        "alerts": [
            {"severity": "high", "excerpt": "-", "issue": "i", "suggestion": "s",
             "legal_basis": None, **a}
            for a in alertas
        ],
    }, ensure_ascii=False)


def _origens(raw, regras=REGRAS):
    return [(a["origin"], a["rule_name"]) for a in _parse_llm_response(raw, regras)["alerts"]]


# ─── Origem conferida no parser ──────────────────────────────────────────────

def test_regra_e_achado_livre_saem_com_a_origem():
    raw = _resposta(
        {"origin": "rule", "rule_name": "Foro competente"},
        {"origin": "finding", "rule_name": "Juros de 5% ao mês"},
    )
    assert _origens(raw) == [("rule", "Foro competente"), ("finding", "Juros de 5% ao mês")]


def test_nome_de_regra_com_caixa_ou_espaco_diferente_volta_ao_nome_configurado():
    """Senão o checklist marcaria a regra como aprovada, com alerta dela na tela."""
    raw = _resposta({"origin": "rule", "rule_name": "  foro   COMPETENTE "})
    assert _origens(raw) == [("rule", "Foro competente")]


def test_regra_que_nao_existe_vira_achado_livre():
    raw = _resposta({"origin": "rule", "rule_name": "Cláusula penal excessiva"})
    assert _origens(raw) == [("finding", "Cláusula penal excessiva")]


def test_achado_com_nome_de_regra_conta_como_regra():
    raw = _resposta({"origin": "finding", "rule_name": "Foro competente"})
    assert _origens(raw) == [("rule", "Foro competente")]


def test_sem_origem_informada_decide_pelo_nome():
    raw = _resposta({"rule_name": "Foro competente"}, {"rule_name": "Multa abusiva"})
    assert _origens(raw) == [("rule", "Foro competente"), ("finding", "Multa abusiva")]


def test_sem_regras_tudo_e_achado_livre():
    raw = _resposta({"origin": "rule", "rule_name": "Foro competente"})
    assert _origens(raw, []) == [("finding", "Foro competente")]
    assert _parse_llm_response(raw)["alerts"][0]["origin"] == "finding"


def test_analyze_document_confere_a_origem_com_as_regras_do_prompt():
    raw = _resposta(
        {"origin": "rule", "rule_name": "foro competente"},
        {"origin": "finding", "rule_name": "Retenção indefinida de dados"},
    )
    bloco = MagicMock(text=raw)
    resposta = MagicMock(content=[bloco], stop_reason="end_turn",
                         usage=MagicMock(input_tokens=1, output_tokens=1))
    cliente = MagicMock()
    cliente.messages.create.return_value = resposta
    s = MagicMock(ANTHROPIC_API_KEY="sk-ant-valida", ANTHROPIC_TIMEOUT=60,
                  ANTHROPIC_MODEL="m", ANTHROPIC_MAX_TOKENS=1000)
    regras = [{"name": "Foro competente", "severity": "high", "criteria": "c"}]

    with patch("app.services.ai_analyzer.settings", s), \
         patch("app.services.ai_analyzer.anthropic") as mod:
        mod.Anthropic.return_value = cliente
        resultado = analyze_document("Contrato.", regras)

    assert [(a["origin"], a["rule_name"]) for a in resultado.alerts] == [
        ("rule", "Foro competente"), ("finding", "Retenção indefinida de dados"),
    ]


# ─── O que o prompt pede ─────────────────────────────────────────────────────

def _prompt(regras=None, contexto=None):
    regras = regras if regras is not None else [
        {"name": n, "severity": "high", "criteria": "c"} for n in REGRAS
    ]
    return _build_user_prompt("CONTRATO", regras, contexto or [], None)


def test_versao_do_prompt_e_a_4():
    assert PROMPT_VERSION == "4"


def test_prompt_pede_regras_reprovadas_e_achados_livres_com_origem():
    prompt = _prompt()
    secao = prompt.split("QUAIS ALERTAS GERAR")[1].split("EXIGÊNCIAS")[0]
    assert '"origin": "rule"' in secao and '"origin": "finding"' in secao
    assert "nenhuma regra" in secao
    assert f"Até {MAX_ACHADOS_LIVRES} achados livres" in secao
    assert "Não repita como" in secao
    # O exemplo de JSON continua válido e traz o campo.
    exemplo = re.search(r"\{\s*\"summary\".*?\n\}", prompt, re.S).group(0)
    assert "origin" in json.loads(exemplo)["alerts"][0]


def test_prompt_pede_citacao_legal_em_todo_alerta_sem_liberar_invencao():
    secao = _prompt().split('2. "legal_basis"')[1].split("TAMANHO DA RESPOSTA")[0]
    assert "todo alerta, de regra ou achado livre" in secao
    assert "BASE LEGAL RELEVANTE" in secao
    assert "mais de um alerta" in secao
    assert "use null" in secao and "Não invente" in secao


def test_secao_da_base_legal_vale_para_achados_livres():
    secao = _build_legal_context_section(
        [{"source": "Lei 13.709/2018", "article_ref": "Art. 16", "content": "x"}]
    )
    assert "achados livres" in secao
    assert "'legal_basis'" in secao


def test_system_prompt_nao_limita_a_analise_as_regras():
    from app.services.ai_analyzer import SYSTEM_PROMPT

    assert "checklist mínimo" in SYSTEM_PROMPT
    assert "não aplicável" not in SYSTEM_PROMPT   # pedia um rótulo que não tinha campo


# ─── Checklist, schema e endpoint ────────────────────────────────────────────

def test_achado_livre_nao_reprova_regra_e_nome_corrigido_reprova():
    raw = _resposta(
        {"origin": "rule", "rule_name": "FORO COMPETENTE"},
        {"origin": "finding", "rule_name": "Juros de 5% ao mês"},
    )
    alertas = _parse_llm_response(raw, REGRAS)["alerts"]
    resumo = resumo_de_regras([{"name": n} for n in REGRAS], alertas)
    assert resumo["rules_passed"] == 1 and resumo["rules_total"] == 2


def test_schema_aceita_alerta_antigo_sem_origem():
    antigo = AlertSchema(rule_name="x", severity="high", excerpt="-", issue="i", suggestion="s")
    novo = AlertSchema(rule_name="x", severity="high", excerpt="-", issue="i",
                       suggestion="s", origin="finding")
    assert antigo.origin is None and novo.origin == "finding"


@pytest.mark.asyncio
async def test_relatorio_devolve_a_origem_do_alerta(
    client: AsyncClient, auth_headers: dict, setup_db
):
    alertas = [
        {"rule_name": "Juros", "origin": "finding", "severity": "high",
         "issue": "i", "excerpt": "", "suggestion": "s"},
        {"rule_name": "Antigo", "severity": "low", "issue": "i", "excerpt": "", "suggestion": "s"},
    ]
    doc_id = await _documento_analisado(client, auth_headers, alertas)

    resp = await client.get(f"/api/v1/documents/{doc_id}/report", headers=auth_headers)

    assert [a["origin"] for a in resp.json()["analysis"]["alerts"]] == ["finding", None]


# ─── PDF ─────────────────────────────────────────────────────────────────────

def _html(alertas):
    html = generate_html_report(
        {"filename": "c.docx"},
        {"risk_score": 80, "summary": "s", "alerts": alertas, "missing_clauses": []},
        [{"name": "Foro competente"}],
    )
    return re.sub(r"<style.*?</style>", "", html, flags=re.S)


def _alerta(nome, origem=None):
    a = {"rule_name": nome, "severity": "high", "issue": "i", "excerpt": "-", "suggestion": "s"}
    if origem:
        a["origin"] = origem
    return a


def test_pdf_marca_a_origem_de_cada_alerta_e_conta_as_duas():
    html = _html([_alerta("Foro competente", "rule"), _alerta("Juros", "finding"),
                  _alerta("Retenção", "finding")])
    assert html.count(">Regra do checklist<") == 1
    assert html.count(">Achado livre<") == 2
    assert "<b>De regras do checklist</b><span>1</span>" in html
    assert "<b>Achados livres</b><span>2</span>" in html


def test_pdf_de_analise_antiga_nao_inventa_origem():
    html = _html([_alerta("Foro competente"), _alerta("Juros")])
    assert "Achado livre" not in html and "Regra do checklist" not in html
    assert "Achados livres" not in html
