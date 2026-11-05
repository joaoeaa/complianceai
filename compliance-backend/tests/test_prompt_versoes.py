"""Versões do prompt de análise: v4 (padrão) e v5 (método de revisão).

A versão vem de ANALYSIS_PROMPT_VERSION e fica gravada em cada análise. O v4
precisa continuar com o texto com que foi usado, e o v5 não pode depender de
exemplos de problema: o que ele traz é um método, não uma lista.
"""
import json
import re
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app import Analysis
from app.core.config import Settings
from app.services import ai_analyzer, analysis_runner
from app.services.ai_analyzer import (
    MAX_ACHADOS_LIVRES,
    PROMPT_VERSION_PADRAO,
    PROMPT_VERSIONS,
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_V5,
    AnalysisResult,
    _build_legal_context_section,
    _build_user_prompt,
    analyze_document,
    versao_do_prompt,
)
from tests.test_analysis_runner import SyncSession, _criar_documento, sem_rag  # noqa: F401

REGRAS = [{"name": "Foro competente", "severity": "high", "criteria": "c"}]
CONTEXTO = [{"source": "Lei 13.709/2018", "article_ref": "Art. 16", "content": "x"}]


def _prompt(versao, regras=REGRAS, contexto=CONTEXTO):
    return _build_user_prompt("CONTRATO", regras, contexto, None, versao=versao)


# ─── Seleção da versão ───────────────────────────────────────────────────────

def test_padrao_continua_v4_e_v5_esta_disponivel():
    assert PROMPT_VERSION_PADRAO == "4"
    assert PROMPT_VERSIONS == ("4", "4.1", "5")
    assert Settings().ANALYSIS_PROMPT_VERSION == "4"


def test_configuracao_aceita_exatamente_as_versoes_do_analisador():
    """A lista da configuração é duplicada; as duas não podem divergir."""
    for v in PROMPT_VERSIONS:
        assert Settings(ANALYSIS_PROMPT_VERSION=v).ANALYSIS_PROMPT_VERSION == v
    with pytest.raises(ValidationError, match="ANALYSIS_PROMPT_VERSION"):
        Settings(ANALYSIS_PROMPT_VERSION="6")


def test_versao_pedida_vence_a_configurada_e_desconhecida_falha():
    with patch.object(ai_analyzer, "settings", MagicMock(ANALYSIS_PROMPT_VERSION="5")):
        assert versao_do_prompt() == "5"
        assert versao_do_prompt("4") == "4"
        with pytest.raises(ValueError, match="desconhecida"):
            versao_do_prompt("3")
    with pytest.raises(ValueError):
        _build_user_prompt("C", [], [], None, versao="9")


def _chamar(prompt_version=None, configurada="4"):
    raw = json.dumps({"summary": "s", "risk_score": 10, "alerts": [], "missing_clauses": []})
    resposta = MagicMock(content=[MagicMock(text=raw)], stop_reason="end_turn",
                         usage=MagicMock(input_tokens=1, output_tokens=1))
    cliente = MagicMock()
    cliente.messages.create.return_value = resposta
    s = MagicMock(ANTHROPIC_API_KEY="sk-ant-valida", ANTHROPIC_TIMEOUT=60, ANTHROPIC_MODEL="m",
                  ANTHROPIC_MAX_TOKENS=1000, ANALYSIS_PROMPT_VERSION=configurada)
    with patch.object(ai_analyzer, "settings", s), patch.object(ai_analyzer, "anthropic") as mod:
        mod.Anthropic.return_value = cliente
        resultado = analyze_document("CONTRATO", REGRAS, legal_context=CONTEXTO,
                                     prompt_version=prompt_version)
    return resultado, cliente.messages.create.call_args.kwargs


@pytest.mark.parametrize("pedida, configurada, esperada", [
    (None, "4", "4"), (None, "5", "5"), ("5", "4", "5"), ("4", "5", "4"),
])
def test_analise_envia_e_devolve_a_versao_usada(pedida, configurada, esperada):
    resultado, enviado = _chamar(pedida, configurada)
    assert resultado.prompt_version == esperada
    assert enviado["system"] == (SYSTEM_PROMPT if esperada == "4" else SYSTEM_PROMPT_V5)
    assert enviado["messages"][0]["content"] == _prompt(esperada)


def test_runner_grava_a_versao_que_produziu_a_analise(monkeypatch, sem_rag):  # noqa: F811
    doc_id = _criar_documento()
    monkeypatch.setattr(
        "app.services.ai_analyzer.analyze_document",
        lambda *a, **k: AnalysisResult(
            summary="s", risk_score=1, alerts=[], missing_clauses=[],
            prompt_tokens=1, completion_tokens=1, prompt_version="5",
        ),
    )
    assert analysis_runner.executar_analise(doc_id, session_factory=SyncSession) == "analyzed"
    with SyncSession() as db:
        analise = db.execute(select(Analysis).where(Analysis.document_id == doc_id)).scalar_one()
    assert analise.prompt_version == "5"


# ─── O que o v5 pede ─────────────────────────────────────────────────────────

def test_v5_troca_a_lista_de_exemplos_pelo_metodo():
    v4, v5 = _prompt("4"), _prompt("5")
    exemplos_do_v4 = "multa ou juros acima do limite legal"
    assert exemplos_do_v4 in v4 and exemplos_do_v4 not in v5
    metodo = v5.split("MÉTODO DE REVISÃO")[1].split("QUAIS ALERTAS GERAR")[0]
    for dimensao in ("Equilíbrio entre as partes", "Valores e encargos", "Responsabilidade",
                     "Dados e informações", "Saída do contrato", "Ausências"):
        assert dimensao in metodo, dimensao
    for termo in ("multas, juros, prazos, percentuais e reajustes", "limite legal",
                  "exclusões, limitações e renúncias", "retenção", "sobrevive ao fim"):
        assert termo in metodo, termo


def test_v5_usa_cada_trecho_de_lei_como_item_de_verificacao():
    metodo = _prompt("5").split("MÉTODO DE REVISÃO")[1]
    assert '"o contrato respeita isto?"' in metodo
    assert "item de verificação" in _build_legal_context_section(CONTEXTO, "5")
    assert "item de verificação" not in _build_legal_context_section(CONTEXTO, "4")


def test_v5_tem_revisao_final_e_pede_para_nao_apontar_o_usual():
    v5 = _prompt("5")
    assert "Revisão final" in v5 and "não geraram alerta" in v5
    assert "usual e equilibrada" in v5
    assert "severidade alta" in v5.split("QUAIS ALERTAS GERAR")[1]
    assert "MÉTODO DE REVISÃO" in SYSTEM_PROMPT_V5 and "MÉTODO" not in SYSTEM_PROMPT


def test_v5_mantem_origem_teto_citacao_e_formato_do_v4():
    v4, v5 = _prompt("4"), _prompt("5")
    secao = v5.split("QUAIS ALERTAS GERAR")[1].split("EXIGÊNCIAS")[0]
    assert '"origin": "rule"' in secao and '"origin": "finding"' in secao
    assert f"Até {MAX_ACHADOS_LIVRES} achados livres" in secao
    # Exigências sobre excerpt e legal_basis, sem mudança.
    assert v4.split("EXIGÊNCIAS")[1].split("TAMANHO")[0] == v5.split("EXIGÊNCIAS")[1].split("TAMANHO")[0]
    assert "Não invente" in v5

    def exemplo(p):
        return json.loads(re.search(r"\{\s*\"summary\".*?\n\}", p, re.S).group(0))
    assert exemplo(v4) == exemplo(v5)


# ─── v4.1: o v4 com dois itens do v5 e a régua de responsabilidade e renúncia ──

def _secao(p):
    return p.split("QUAIS ALERTAS GERAR")[1].split("EXIGÊNCIAS")[0]


def test_v41_e_o_v4_mais_os_itens_novos():
    v4, v41 = _secao(_prompt("4")), _secao(_prompt("4.1"))
    assert v41.startswith(v4.rstrip("\n"))
    novos = v41[len(v4.rstrip("\n")):]
    assert [linha[:3] for linha in novos.splitlines() if linha[:1].isdigit()] == ["4. ", "5. ", "6. ", "7. "]
    # Fora dessa seção, o prompt é o do v4.
    assert _prompt("4").replace(v4, "") == _prompt("4.1").replace(v41, "")
    assert ai_analyzer._SYSTEM_PROMPTS["4.1"] == SYSTEM_PROMPT
    assert _build_legal_context_section(CONTEXTO, "4.1") == _build_legal_context_section(CONTEXTO, "4")


def test_v41_traz_do_v5_so_o_usual_e_as_ausencias():
    v41 = _prompt("4.1")
    assert "usual e equilibrada" in v41
    assert "Ausências" in v41 and "normalmente precisa ter" in v41
    for so_do_v5 in ("MÉTODO DE REVISÃO", "Revisão final", "Equilíbrio entre as partes",
                     "item de verificação", "Profundidade"):
        assert so_do_v5 not in v41, so_do_v5


def test_v41_separa_limitacao_proporcional_de_exclusao_e_renuncia_usual_de_grave():
    item6 = _secao(_prompt("4.1")).split("6. Responsabilidade")[1].split("7. ")[0]
    assert "recíproca e proporcional" in item6 and "severidade baixa" in item6
    assert "dolo ou culpa grave" in item6 and "severidade alta" in item6
    item7 = _secao(_prompt("4.1")).split("7. Renúncias")[1]
    assert "benfeitorias na locação" in item7 and "não é problema" in item7
    assert "irrenunciável" in item7 and "problema grave" in item7


def test_v41_mantem_origem_teto_citacao_e_formato():
    v4, v41 = _prompt("4"), _prompt("4.1")
    assert f"Até {MAX_ACHADOS_LIVRES} achados livres" in v41
    assert v4.split("EXIGÊNCIAS")[1] == v41.split("EXIGÊNCIAS")[1]
