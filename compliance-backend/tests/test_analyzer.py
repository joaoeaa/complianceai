"""
Unit tests for the AI analysis service (ai_analyzer.py).

All calls to the Anthropic API are mocked — no real API key or network
access is required to run this suite.
"""
import json
import pytest
from unittest.mock import MagicMock, patch


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _sample_rules(n: int = 2) -> list[dict]:
    """Return *n* realistic compliance rules as dicts."""
    pool = [
        {"name": "LGPD — Consentimento", "severity": "high", "criteria": "Documento deve conter cláusula de consentimento para tratamento de dados pessoais."},
        {"name": "Cláusula de Rescisão", "severity": "medium", "criteria": "Deve prever condições de rescisão antecipada e multas."},
        {"name": "Sigilo e Confidencialidade", "severity": "low", "criteria": "Verificar cláusula de NDA."},
    ]
    return pool[:n]


def _valid_llm_json(
    summary: str = "Documento em conformidade parcial.",
    risk_score: int = 45,
    alerts: list | None = None,
    missing: list | None = None,
) -> str:
    """Return a raw JSON string that matches the expected LLM output schema."""
    if alerts is None:
        alerts = [
            {
                "rule_name": "LGPD — Consentimento",
                "severity": "high",
                "excerpt": "Trecho do contrato…",
                "issue": "Não possui cláusula de consentimento.",
                "suggestion": "Incluir cláusula de consentimento conforme Art. 7º da LGPD.",
                "legal_basis": "Art. 7º, LGPD",
            }
        ]
    return json.dumps(
        {
            "summary": summary,
            "risk_score": risk_score,
            "alerts": alerts,
            "missing_clauses": missing or ["Cláusula de Rescisão"],
        },
        ensure_ascii=False,
    )


def _mock_anthropic_response(raw_text: str, input_tokens: int = 500, output_tokens: int = 300):
    """Return a mock object mimicking ``anthropic.Message``."""
    content_block = MagicMock()
    content_block.text = raw_text

    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens

    response = MagicMock()
    response.content = [content_block]
    response.usage = usage
    response.stop_reason = "end_turn"
    return response


# ─── _build_rules_section ────────────────────────────────────────────────────

class TestBuildRulesSection:

    def test_no_rules_returns_fallback(self):
        from app.services.ai_analyzer import _build_rules_section
        result = _build_rules_section([])
        assert "análise geral" in result.lower()

    def test_single_rule_high_severity(self):
        from app.services.ai_analyzer import _build_rules_section
        rules = [{"name": "LGPD", "severity": "high", "criteria": "Dados pessoais"}]
        result = _build_rules_section(rules)
        assert "[ALTA]" in result
        assert "LGPD" in result
        assert "Dados pessoais" in result

    def test_multiple_rules_numbered(self):
        from app.services.ai_analyzer import _build_rules_section
        rules = _sample_rules(3)
        result = _build_rules_section(rules)
        assert "1." in result
        assert "2." in result
        assert "3." in result
        assert "[ALTA]" in result
        assert "[MÉDIA]" in result
        assert "[BAIXA]" in result

    def test_unknown_severity_defaults_media(self):
        from app.services.ai_analyzer import _build_rules_section
        rules = [{"name": "Regra X", "severity": "critical", "criteria": "Alguma coisa"}]
        result = _build_rules_section(rules)
        assert "[MÉDIA]" in result


# ─── _build_legal_context_section ────────────────────────────────────────────

class TestBuildLegalContextSection:

    def test_empty_context_returns_empty_string(self):
        from app.services.ai_analyzer import _build_legal_context_section
        assert _build_legal_context_section([]) == ""

    def test_single_context_item(self):
        from app.services.ai_analyzer import _build_legal_context_section
        ctx = [{"source": "LGPD", "article_ref": "Art. 7º", "content": "Consentimento do titular."}]
        result = _build_legal_context_section(ctx)
        assert "LGPD" in result
        assert "Art. 7º" in result
        assert "Consentimento do titular." in result
        assert "BASE LEGAL" in result

    def test_context_without_article_ref(self):
        from app.services.ai_analyzer import _build_legal_context_section
        ctx = [{"source": "CDC", "content": "Direitos do consumidor."}]
        result = _build_legal_context_section(ctx)
        assert "CDC" in result
        assert "Direitos do consumidor." in result

    def test_multiple_contexts_numbered(self):
        from app.services.ai_analyzer import _build_legal_context_section
        ctx = [
            {"source": "LGPD", "article_ref": "Art. 7º", "content": "Consentimento"},
            {"source": "CC", "article_ref": "Art. 421", "content": "Liberdade contratual"},
        ]
        result = _build_legal_context_section(ctx)
        assert "[1]" in result
        assert "[2]" in result


# ─── _build_user_prompt ──────────────────────────────────────────────────────

class TestBuildUserPrompt:

    def test_contains_document_text(self):
        from app.services.ai_analyzer import _build_user_prompt
        result = _build_user_prompt("Texto do contrato XYZ.", _sample_rules())
        assert "Texto do contrato XYZ." in result

    def test_contains_rules_section(self):
        from app.services.ai_analyzer import _build_user_prompt
        result = _build_user_prompt("Qualquer texto.", _sample_rules())
        assert "LGPD — Consentimento" in result

    def test_contains_legal_context_when_provided(self):
        from app.services.ai_analyzer import _build_user_prompt
        ctx = [{"source": "LGPD", "article_ref": "Art. 7º", "content": "Consentimento"}]
        result = _build_user_prompt("Doc.", _sample_rules(), legal_context=ctx)
        assert "BASE LEGAL" in result
        assert "Art. 7º" in result

    def test_truncates_long_document(self):
        from app.services.ai_analyzer import _build_user_prompt
        huge_text = "A" * 200_000
        result = _build_user_prompt(huge_text, _sample_rules())
        assert "TRUNCADO" in result
        # The prompt should not contain the full 200k chars
        assert len(result) < 200_000

    def test_no_legal_context_is_fine(self):
        from app.services.ai_analyzer import _build_user_prompt
        result = _build_user_prompt("Doc.", _sample_rules(), legal_context=None)
        # The JSON template itself mentions "legal_basis" as a field name,
        # so we check for the RAG-specific header that only appears with context
        assert "BASE LEGAL RELEVANTE (legislação brasileira indexada):" not in result


# ─── _parse_llm_response ────────────────────────────────────────────────────

class TestParseLlmResponse:

    def test_valid_json(self):
        from app.services.ai_analyzer import _parse_llm_response
        raw = _valid_llm_json()
        data = _parse_llm_response(raw)
        assert data["summary"] == "Documento em conformidade parcial."
        assert data["risk_score"] == 45
        assert len(data["alerts"]) == 1
        assert data["alerts"][0]["rule_name"] == "LGPD — Consentimento"

    def test_strips_markdown_code_fence(self):
        from app.services.ai_analyzer import _parse_llm_response
        raw = "```json\n" + _valid_llm_json() + "\n```"
        data = _parse_llm_response(raw)
        assert data["risk_score"] == 45

    def test_strips_plain_code_fence(self):
        from app.services.ai_analyzer import _parse_llm_response
        raw = "```\n" + _valid_llm_json() + "\n```"
        data = _parse_llm_response(raw)
        assert data["risk_score"] == 45

    def test_clamps_score_above_100(self):
        from app.services.ai_analyzer import _parse_llm_response
        raw = _valid_llm_json(risk_score=150)
        data = _parse_llm_response(raw)
        assert data["risk_score"] == 100

    def test_clamps_score_below_0(self):
        from app.services.ai_analyzer import _parse_llm_response
        raw = _valid_llm_json(risk_score=-10)
        data = _parse_llm_response(raw)
        assert data["risk_score"] == 0

    def test_missing_required_field_raises(self):
        from app.services.ai_analyzer import _parse_llm_response
        bad = json.dumps({"summary": "Algo", "alerts": []})  # missing risk_score
        with pytest.raises(ValueError, match="risk_score"):
            _parse_llm_response(bad)

    def test_invalid_json_raises(self):
        from app.services.ai_analyzer import _parse_llm_response
        with pytest.raises(ValueError, match="(?i)inválid"):
            _parse_llm_response("this is not json at all")

    def test_empty_legal_basis_normalized_to_none(self):
        from app.services.ai_analyzer import _parse_llm_response
        raw = _valid_llm_json(alerts=[{
            "rule_name": "Regra A",
            "severity": "low",
            "excerpt": "—",
            "issue": "Problema",
            "suggestion": "Fix it",
            "legal_basis": "  ",
        }])
        data = _parse_llm_response(raw)
        assert data["alerts"][0]["legal_basis"] is None

    def test_alerts_not_list_becomes_empty(self):
        from app.services.ai_analyzer import _parse_llm_response
        raw = json.dumps({
            "summary": "Ok",
            "risk_score": 20,
            "alerts": "nenhum",
            "missing_clauses": [],
        })
        data = _parse_llm_response(raw)
        assert data["alerts"] == []

    def test_missing_clauses_not_list_becomes_empty(self):
        from app.services.ai_analyzer import _parse_llm_response
        raw = json.dumps({
            "summary": "Ok",
            "risk_score": 20,
            "alerts": [],
            "missing_clauses": "nenhuma",
        })
        data = _parse_llm_response(raw)
        assert data["missing_clauses"] == []

    def test_alert_without_rule_name_skipped(self):
        from app.services.ai_analyzer import _parse_llm_response
        raw = json.dumps({
            "summary": "Ok",
            "risk_score": 20,
            "alerts": [{"severity": "low", "issue": "sem rule_name"}],
            "missing_clauses": [],
        })
        data = _parse_llm_response(raw)
        assert data["alerts"] == []


# ─── analyze_document ────────────────────────────────────────────────────────

class TestAnalyzeDocument:

    def test_missing_api_key_raises(self):
        from app.services.ai_analyzer import analyze_document
        mock_settings = MagicMock()
        mock_settings.ANTHROPIC_API_KEY = ""
        with patch("app.services.ai_analyzer.settings", mock_settings):
            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
                analyze_document("Texto qualquer.", _sample_rules())

    def test_placeholder_api_key_raises(self):
        from app.services.ai_analyzer import analyze_document
        mock_settings = MagicMock()
        mock_settings.ANTHROPIC_API_KEY = "sk-ant-your-key-here"
        with patch("app.services.ai_analyzer.settings", mock_settings):
            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
                analyze_document("Texto qualquer.", _sample_rules())

    def test_successful_analysis(self):
        from app.services.ai_analyzer import analyze_document, AnalysisResult

        raw_json = _valid_llm_json(
            summary="Contrato com risco moderado.",
            risk_score=55,
        )
        mock_response = _mock_anthropic_response(raw_json, input_tokens=800, output_tokens=400)

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        mock_settings = MagicMock()
        mock_settings.ANTHROPIC_API_KEY = "sk-ant-real-key-for-testing"
        mock_settings.ANTHROPIC_TIMEOUT = 120
        mock_settings.ANTHROPIC_MODEL = "claude-sonnet-4-20250514"
        mock_settings.ANTHROPIC_MAX_TOKENS = 4096

        with patch("app.services.ai_analyzer.settings", mock_settings), \
             patch("app.services.ai_analyzer.anthropic") as mock_anthropic_mod:
            mock_anthropic_mod.Anthropic.return_value = mock_client

            result = analyze_document("Texto do contrato.", _sample_rules())

        assert isinstance(result, AnalysisResult)
        assert result.summary == "Contrato com risco moderado."
        assert result.risk_score == 55
        assert result.prompt_tokens == 800
        assert result.completion_tokens == 400
        assert len(result.alerts) == 1

    def test_analysis_with_legal_context(self):
        from app.services.ai_analyzer import analyze_document

        raw_json = _valid_llm_json(risk_score=30)
        mock_response = _mock_anthropic_response(raw_json)

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        mock_settings = MagicMock()
        mock_settings.ANTHROPIC_API_KEY = "sk-ant-real-key-for-testing"
        mock_settings.ANTHROPIC_TIMEOUT = 120
        mock_settings.ANTHROPIC_MODEL = "claude-sonnet-4-20250514"
        mock_settings.ANTHROPIC_MAX_TOKENS = 4096

        legal_ctx = [
            {"source": "LGPD", "article_ref": "Art. 7º", "content": "Consentimento"},
        ]

        with patch("app.services.ai_analyzer.settings", mock_settings), \
             patch("app.services.ai_analyzer.anthropic") as mock_anthropic_mod:
            mock_anthropic_mod.Anthropic.return_value = mock_client

            result = analyze_document("Texto.", _sample_rules(), legal_context=legal_ctx)

        # Verify legal context was included in the prompt sent to Claude
        call_args = mock_client.messages.create.call_args
        user_message = call_args.kwargs["messages"][0]["content"]
        assert "BASE LEGAL" in user_message
        assert "Art. 7º" in user_message
        assert result.risk_score == 30

    def test_invalid_llm_response_raises(self):
        from app.services.ai_analyzer import analyze_document

        mock_response = _mock_anthropic_response("not json at all")

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        mock_settings = MagicMock()
        mock_settings.ANTHROPIC_API_KEY = "sk-ant-real-key-for-testing"
        mock_settings.ANTHROPIC_TIMEOUT = 120
        mock_settings.ANTHROPIC_MODEL = "claude-sonnet-4-20250514"
        mock_settings.ANTHROPIC_MAX_TOKENS = 4096

        with patch("app.services.ai_analyzer.settings", mock_settings), \
             patch("app.services.ai_analyzer.anthropic") as mock_anthropic_mod:
            mock_anthropic_mod.Anthropic.return_value = mock_client

            with pytest.raises(ValueError, match="(?i)inválid"):
                analyze_document("Texto.", _sample_rules())


def test_exemplo_de_json_no_prompt_e_valido():
    """O exemplo de saída dentro do prompt precisa ser JSON que parseia.

    Ele já esteve malformado: faltava vírgula depois de "legal_basis" e havia uma
    chave "OBS" solta no meio do objeto. Mandar um exemplo inválido e pedir JSON
    puro de volta é trabalhar contra o próprio pedido.
    """
    import json

    from app.services.ai_analyzer import _build_user_prompt

    prompt = _build_user_prompt(
        "CONTRATO", [{"name": "R", "severity": "high", "criteria": "c"}], [], None
    )
    inicio = prompt.index('{\n  "summary"')
    exemplo = prompt[inicio:prompt.index("\n\nEXIGÊNCIAS", inicio)]

    carregado = json.loads(exemplo)
    assert set(carregado) == {"summary", "risk_score", "alerts", "missing_clauses"}
    assert set(carregado["alerts"][0]) == {
        "rule_name", "severity", "excerpt", "issue", "suggestion", "legal_basis",
    }


def test_prompt_exige_copia_literal_no_excerpt():
    """É o campo que a verificação confere contra o documento."""
    from app.services.ai_analyzer import _build_user_prompt

    prompt = _build_user_prompt("CONTRATO", [], [], None)
    assert "cópia literal" in prompt
    assert "[...]" in prompt


class TestRespostaTruncada:
    """Resposta cortada no teto de saída precisa dizer que foi cortada.

    Foi assim que um estatuto social quebrou em produção: a geração bateu exatos
    8192 tokens, o JSON veio partido no meio de uma string, e o erro registrado
    foi "JSON inválido", que manda investigar o parser em vez do limite. O
    diagnóstico custou mais do que a correção.
    """

    def test_truncamento_e_reportado_como_tal(self):
        from unittest.mock import patch

        from app.services.ai_analyzer import analyze_document

        resposta = _mock_anthropic_response('{\n  "summary": "come')
        resposta.stop_reason = "max_tokens"

        cliente = MagicMock()
        cliente.messages.create.return_value = resposta

        settings_mock = MagicMock()
        settings_mock.ANTHROPIC_API_KEY = "sk-ant-valida"
        settings_mock.ANTHROPIC_MODEL = "claude-sonnet-5"
        settings_mock.ANTHROPIC_MAX_TOKENS = 16384
        settings_mock.ANTHROPIC_TIMEOUT = 300

        with patch("app.services.ai_analyzer.anthropic.Anthropic", return_value=cliente), \
             patch("app.services.ai_analyzer.settings", settings_mock):
            with pytest.raises(ValueError) as erro:
                analyze_document("texto do contrato", [])

        mensagem = str(erro.value)
        assert "limite de resposta" in mensagem
        assert "16384" in mensagem
        assert "JSON" not in mensagem

    def test_resposta_completa_nao_dispara_o_aviso(self):
        from unittest.mock import patch

        from app.services.ai_analyzer import analyze_document

        valido = (
            '{"summary": "ok", "risk_score": 10, "alerts": [], "missing_clauses": []}'
        )
        resposta = _mock_anthropic_response(valido)
        resposta.stop_reason = "end_turn"

        cliente = MagicMock()
        cliente.messages.create.return_value = resposta

        settings_mock = MagicMock()
        settings_mock.ANTHROPIC_API_KEY = "sk-ant-valida"
        settings_mock.ANTHROPIC_MODEL = "claude-sonnet-5"
        settings_mock.ANTHROPIC_MAX_TOKENS = 16384
        settings_mock.ANTHROPIC_TIMEOUT = 300

        with patch("app.services.ai_analyzer.anthropic.Anthropic", return_value=cliente), \
             patch("app.services.ai_analyzer.settings", settings_mock):
            resultado = analyze_document("texto do contrato", [])

        assert resultado.summary == "ok"
        assert resultado.risk_score == 10
