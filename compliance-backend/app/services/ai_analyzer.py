"""
AI Analysis Service — integrates with Anthropic Claude for contract compliance analysis.

This is the core intelligence of the system:
1. Builds a dynamic prompt from active rules
2. Sends extracted document text to Claude
3. Parses and validates the structured JSON response
4. Returns a validated analysis result
"""
import json
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class AnalysisResult:
    """Validated analysis result from the LLM."""
    summary: str
    risk_score: int
    alerts: List[Dict[str, str]]
    missing_clauses: List[str]
    prompt_tokens: int
    completion_tokens: int


# ─── Prompt Template ───

# Incrementar a cada mudanca no prompt ou no formato de saida. Fica gravado em
# cada analise, para que um resultado antigo possa ser explicado depois.
PROMPT_VERSION = "1"

SYSTEM_PROMPT = """Você é um assistente especializado em análise de contratos e documentos legais.

Sua função é:
1. Analisar o documento completo fornecido
2. Verificar conformidade com CADA regra listada abaixo
3. Identificar riscos, cláusulas ausentes e problemas com base na legislação aplicável
4. Gerar alertas estruturados com trechos exatos do documento
5. Calcular um score de risco geral de 0 a 100

Você conhece profundamente a legislação brasileira (LGPD, CDC, Código Civil, CLT, Marco Civil da Internet, Lei Anticorrupção, Lei de Licitações, etc.) e também legislação internacional relevante (GDPR, CCPA, SOX, etc.).

Seja preciso e objetivo. Cite trechos EXATOS do documento quando possível.
Se uma regra não se aplica ao documento (ex: regra sobre dados pessoais em um NDA simples), indique como "não aplicável" ao invés de gerar um falso alerta.

IMPORTANTE:
- Score 0-30 = Baixo risco (documento em boa conformidade)
- Score 31-60 = Risco moderado (alguns problemas a resolver)
- Score 61-100 = Alto risco (múltiplas não-conformidades críticas)
- Responda EXCLUSIVAMENTE em JSON válido, sem markdown, sem texto antes ou depois.
"""


def _build_rules_section(rules: List[Dict[str, Any]]) -> str:
    """Build the rules section of the prompt from active rules."""
    if not rules:
        return "Nenhuma regra configurada. Faça uma análise geral de riscos contratuais."

    lines = ["REGRAS DE CONFORMIDADE A VERIFICAR:"]
    for i, rule in enumerate(rules, 1):
        severity_label = {"high": "ALTA", "medium": "MÉDIA", "low": "BAIXA"}.get(rule["severity"], "MÉDIA")
        lines.append(f"{i}. [{severity_label}] {rule['name']}: {rule['criteria']}")
    return "\n".join(lines)


def _build_legal_context_section(legal_context: List[Dict[str, str]]) -> str:
    """Build the legal context section from RAG-retrieved legislation chunks."""
    if not legal_context:
        return ""

    lines = ["\nBASE LEGAL RELEVANTE (legislação indexada):"]
    for i, ctx in enumerate(legal_context, 1):
        source = ctx.get("source", "Fonte desconhecida")
        article = ctx.get("article_ref", "")
        content = ctx.get("content", "")
        ref = f" — {article}" if article else ""
        lines.append(f"\n[{i}] {source}{ref}:")
        lines.append(content)
    lines.append(
        "\nUse a base legal acima para fundamentar seus alertas. "
        "Inclua o campo 'legal_basis' em cada alerta quando houver artigo de lei relevante.\n"
    )
    return "\n".join(lines)


def _build_feedback_section(feedback_learnings: Optional[List[Dict[str, Any]]] = None) -> str:
    """Build the feedback / learning loop section from past user feedback.
    This is the key to making the AI improve over time."""
    if not feedback_learnings:
        return ""

    # Only include rules with meaningful feedback
    relevant = [f for f in feedback_learnings if f.get("total", 0) >= 1]
    if not relevant:
        return ""

    lines = ["\nAPRENDIZADO COM FEEDBACK DE USUÁRIOS (use para calibrar sua análise):"]
    lines.append("Os usuários avaliaram análises anteriores. Use essas informações para melhorar sua precisão:\n")

    for f in relevant:
        rule = f["rule_name"]
        total = f["total"]
        correct = f.get("correct", 0)
        incorrect = f.get("incorrect", 0)
        fp_rate = f.get("false_positive_rate", 0)
        comments = f.get("sample_comments", [])

        if fp_rate > 50:
            lines.append(f"⚠️  REGRA '{rule}': {fp_rate}% de falso-positivo ({incorrect}/{total} marcados como incorretos).")
            lines.append(f"    → Seja mais criterioso ao gerar alertas para esta regra. Só alerte se houver evidência clara.")
        elif fp_rate > 25:
            lines.append(f"⚡ REGRA '{rule}': {fp_rate}% de falso-positivo ({incorrect}/{total} marcados como incorretos).")
            lines.append(f"    → Considere aumentar o limiar para alertas desta regra.")
        elif correct > 0 and fp_rate < 10:
            lines.append(f"✅ REGRA '{rule}': {correct}/{total} alertas confirmados como corretos. Bom trabalho!")

        if comments:
            lines.append(f"    Comentários dos usuários sobre falsos positivos:")
            for c in comments[:2]:
                lines.append(f"    - \"{c}\"")
        lines.append("")

    lines.append("INSTRUÇÕES BASEADAS NO FEEDBACK:")
    lines.append("- Se uma regra tem alto índice de falso-positivo, exija evidência mais forte antes de gerar alerta.")
    lines.append("- Se os comentários indicam um padrão (ex: 'NDA simples não precisa de LGPD'), respeite esse contexto.")
    lines.append("- Prefira não gerar alerta do que gerar falso-positivo. Precisão > recall.\n")

    return "\n".join(lines)


def _build_user_prompt(
    document_text: str,
    rules: List[Dict[str, Any]],
    legal_context: Optional[List[Dict[str, str]]] = None,
    feedback_learnings: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Build the complete user prompt with rules, legal context, feedback learnings, and document text."""
    rules_section = _build_rules_section(rules)
    legal_section = _build_legal_context_section(legal_context or [])
    feedback_section = _build_feedback_section(feedback_learnings)

    # Truncate document if too long (Claude supports 200k tokens but we limit for cost)
    max_chars = 150_000  # ~37.5k tokens
    if len(document_text) > max_chars:
        document_text = document_text[:max_chars] + "\n\n[... DOCUMENTO TRUNCADO POR LIMITE DE TAMANHO ...]"
        logger.warning(f"Documento truncado de {len(document_text)} para {max_chars} caracteres")

    rule_names = [r["name"] for r in rules] if rules else []

    return f"""{rules_section}
{legal_section}
{feedback_section}
DOCUMENTO A ANALISAR:
\"\"\"
{document_text}
\"\"\"

Responda EXCLUSIVAMENTE com o seguinte JSON (sem markdown, sem ```json, apenas o JSON puro):
{{
  "summary": "Resumo executivo de 2-3 frases sobre a conformidade geral do documento",
  "risk_score": 0,
  "alerts": [
    {{
      "rule_name": "Nome da regra violada",
      "severity": "high|medium|low",
      "excerpt": "Trecho exato do documento que evidencia o problema (ou '—' se cláusula ausente)",
      "issue": "Descrição clara do problema encontrado",
      "suggestion": "Sugestão prática de como resolver",
      "legal_basis": "Artigo de lei relevante (ex: 'Art. 7º, LGPD', 'Art. 51, CDC', 'Art. 422, CC') ou null se não aplicável"
      "OBS: Se houver base legal aplicável, coloque a referência exata no campo \"legal_basis\". Não invente referências; use as fornecidas em BASE LEGAL RELEVANTE quando possível."
    }}
  ],
  "missing_clauses": ["Lista de cláusulas/regras ausentes no documento"]
}}

REGRAS CONFIGURADAS PARA REFERÊNCIA DE NOMES: {json.dumps(rule_names, ensure_ascii=False)}
"""


def _parse_llm_response(raw_text: str) -> Dict[str, Any]:
    """Parse and validate the LLM JSON response."""
    # Clean up common issues
    text = raw_text.strip()

    # Remove markdown code fences if present
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"Falha ao parsear JSON da IA: {e}\nResposta bruta: {text[:500]}")
        raise ValueError(f"A IA retornou uma resposta inválida (não é JSON válido): {e}")

    # Validate required fields
    required = ["summary", "risk_score", "alerts"]
    for field in required:
        if field not in data:
            raise ValueError(f"Campo obrigatório ausente na resposta da IA: {field}")

    # Validate and clamp risk_score
    score = data["risk_score"]
    if not isinstance(score, (int, float)):
        raise ValueError(f"risk_score deve ser numérico, recebido: {type(score)}")
    data["risk_score"] = max(0, min(100, int(score)))

    # Validate alerts structure
    if not isinstance(data["alerts"], list):
        data["alerts"] = []

    valid_alerts = []
    for alert in data["alerts"]:
        if isinstance(alert, dict) and "rule_name" in alert:
            legal_basis = alert.get("legal_basis")
            # normalizar strings vazias
            if isinstance(legal_basis, str) and legal_basis.strip() == "":
                legal_basis = None
            valid_alerts.append({
                "rule_name": alert.get("rule_name", "Regra desconhecida"),
                "severity": alert.get("severity", "medium"),
                "excerpt": alert.get("excerpt", "—"),
                "issue": alert.get("issue", "Problema não especificado"),
                "suggestion": alert.get("suggestion", "Verificar manualmente"),
                "legal_basis": legal_basis,
            })
    data["alerts"] = valid_alerts

    # Ensure missing_clauses is a list
    if not isinstance(data.get("missing_clauses"), list):
        data["missing_clauses"] = []

    return data


# ─── Main Analysis Function ───

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=4, max=30),
    retry=retry_if_exception_type((anthropic.APIConnectionError, anthropic.RateLimitError, anthropic.InternalServerError)),
    before_sleep=lambda retry_state: logger.warning(f"Retry {retry_state.attempt_number}/3 da chamada à IA..."),
)
def analyze_document(
    document_text: str,
    rules: List[Dict[str, Any]],
    legal_context: Optional[List[Dict[str, str]]] = None,
    feedback_learnings: Optional[List[Dict[str, Any]]] = None,
) -> AnalysisResult:
    """
    Analyze a document using Claude AI.

    Args:
        document_text: The extracted text from the PDF/DOCX
        rules: List of active rules as dicts with keys: name, severity, criteria
        legal_context: Optional list of RAG-retrieved legislation chunks
        feedback_learnings: Optional aggregated user feedback for learning loop

    Returns:
        AnalysisResult with structured analysis data

    Raises:
        ValueError: If the AI response can't be parsed
        anthropic.APIError: If all retries fail
    """
    if not settings.ANTHROPIC_API_KEY or settings.ANTHROPIC_API_KEY.startswith("sk-ant-your"):
        raise ValueError(
            "ANTHROPIC_API_KEY não configurada. "
            "Defina a variável de ambiente com sua chave da Anthropic."
        )

    client = anthropic.Anthropic(
        api_key=settings.ANTHROPIC_API_KEY,
        timeout=settings.ANTHROPIC_TIMEOUT,
    )

    user_prompt = _build_user_prompt(
        document_text, rules,
        legal_context=legal_context,
        feedback_learnings=feedback_learnings,
    )

    logger.info(f"Enviando análise para Claude ({settings.ANTHROPIC_MODEL})...")
    logger.debug(f"Prompt: {len(user_prompt)} caracteres, {len(rules)} regras")

    response = client.messages.create(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=settings.ANTHROPIC_MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    # O modelo pode emitir blocos de thinking antes do texto. Blocos de thinking não
    # carregam `text`, então basta pegar o primeiro bloco que traga texto de verdade.
    raw_text = next(
        (block.text for block in response.content if isinstance(getattr(block, "text", None), str)),
        None,
    )
    if raw_text is None:
        raise ValueError("A resposta do modelo não trouxe nenhum bloco de texto")
    logger.info(f"Resposta recebida: {response.usage.input_tokens} input, {response.usage.output_tokens} output tokens")

    parsed = _parse_llm_response(raw_text)

    return AnalysisResult(
        summary=parsed["summary"],
        risk_score=parsed["risk_score"],
        alerts=parsed["alerts"],
        missing_clauses=parsed.get("missing_clauses", []),
        prompt_tokens=response.usage.input_tokens,
        completion_tokens=response.usage.output_tokens,
    )
