"""Verificação dos alertas contra as fontes.

O modelo produz dois campos que afirmam fatos verificáveis: `excerpt`, que diz citar
um trecho do contrato, e `legal_basis`, que diz apontar um artigo de lei. Nenhum dos
dois é confiável por construção: um modelo pode parafrasear o contrato ou citar um
dispositivo de memória.

Como o texto do contrato e os artigos recuperados pelo RAG estão à mão, dá para
conferir ambos em código e informar ao leitor o que foi confirmado. Quem revisa um
contrato precisa saber onde confiar e onde ir checar na fonte.

Nada aqui descarta alertas. Um trecho não localizado pode ser uma paráfrase correta,
e um artigo fora do contexto recuperado pode estar certo assim mesmo. O objetivo é
rotular, não censurar.
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Iterable, Optional

# Marcador de página inserido pelo extrator, irrelevante para a comparação.
_PAGE_MARKER = re.compile(r"---\s*Página\s+\d+\s*---", re.IGNORECASE)
_WHITESPACE = re.compile(r"\s+")

# "Art. 7º", "art 7", "Artigo 7-A", "Art. 5º, § 2º"
_ARTICLE = re.compile(
    r"\bart(?:igo)?\.?\s*(\d+)\s*(?:[ºo°]|-?[A-Z]\b)?",
    re.IGNORECASE,
)

# Similaridade a partir da qual um trecho conta como paráfrase próxima, e não
# como invenção. Abaixo disso, o leitor precisa conferir no documento.
_APPROXIMATE_THRESHOLD = 0.82


def _normalize(text: str) -> str:
    """Deixa o texto comparável: sem acento, sem marcador de página, espaço único."""
    text = _PAGE_MARKER.sub(" ", text)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.replace("“", '"').replace("”", '"').replace("’", "'")
    text = _WHITESPACE.sub(" ", text)
    return text.strip().lower()


def _strip_quotes(text: str) -> str:
    return text.strip().strip('"“”\'').strip()


def verify_excerpt(excerpt: Optional[str], document_text: str) -> str:
    """Confere se o trecho citado existe no contrato.

    Devolve:
        "exact"        o trecho aparece no documento
        "approximate"  há passagem muito parecida (provável paráfrase)
        "not_found"    nada semelhante foi localizado
        "empty"        não houve citação (cláusula ausente, por exemplo)
    """
    if not excerpt or not document_text:
        return "empty"

    cleaned = _strip_quotes(excerpt)
    # O prompt usa travessão ou hífen para indicar "cláusula ausente".
    if not cleaned or cleaned in {"-", "—", "--", "N/A", "n/a"}:
        return "empty"

    needle = _normalize(cleaned)
    haystack = _normalize(document_text)

    if not needle:
        return "empty"
    if needle in haystack:
        return "exact"

    # Trechos muito curtos casam por acaso; não vale medir similaridade neles.
    if len(needle) < 25:
        return "not_found"

    # Procura a janela mais parecida, do tamanho do trecho citado.
    matcher = SequenceMatcher(None, needle, haystack, autojunk=False)
    match = matcher.find_longest_match(0, len(needle), 0, len(haystack))
    if match.size and match.size / len(needle) >= _APPROXIMATE_THRESHOLD:
        return "approximate"

    return "not_found"


def _article_numbers(text: str) -> set[str]:
    return {m.group(1) for m in _ARTICLE.finditer(text or "")}


# O alerta costuma citar a sigla ("LGPD") enquanto a base legal guarda o número
# ("Lei 13.709/2018"). Sem esta tradução, a mesma lei não se reconhece.
_LAW_ALIASES = {
    "lgpd": "137092018",
    "cdc": "80781990",
    "clt": "clt",
    "marco civil": "129652014",
    "anticorrupcao": "128462013",
    "licitacoes": "141332021",
    "codigo civil": "104062002",
}

_LAW_NUMBER = re.compile(r"\d{1,2}\.?\d{3}[./]\d{2,4}")


def _law_tokens(text: str) -> set[str]:
    """Identificadores de lei, normalizados para que sigla e número se equivalham."""
    if not text:
        return set()

    # "13.709/2018" e "13709/2018" viram a mesma chave: "137092018".
    tokens = {
        m.group(0).replace(".", "").replace("/", "")
        for m in _LAW_NUMBER.finditer(text)
    }

    plain = _normalize(text)
    for alias, canonical in _LAW_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", plain):
            tokens.add(canonical)

    return tokens


def verify_legal_basis(
    legal_basis: Optional[str], legal_context: Iterable[dict[str, Any]]
) -> str:
    """Confere se o artigo citado está entre os recuperados da base legal.

    Devolve:
        "grounded"     o artigo consta do contexto usado na análise
        "law_only"     a lei confere, mas o artigo específico não foi recuperado
        "ungrounded"   nada no contexto sustenta a citação
        "empty"        o alerta não citou base legal
        "no_context"   a busca na base legal não retornou nada nesta análise
    """
    if not legal_basis or not str(legal_basis).strip():
        return "empty"

    context = list(legal_context or [])
    if not context:
        return "no_context"

    cited_articles = _article_numbers(legal_basis)
    cited_laws = _law_tokens(legal_basis)

    context_articles: set[str] = set()
    context_laws: set[str] = set()
    for chunk in context:
        ref = str(chunk.get("article_ref") or "")
        src = str(chunk.get("source") or "")
        context_articles |= _article_numbers(ref)
        context_laws |= _law_tokens(f"{src} {ref}")

    if cited_articles and cited_articles & context_articles:
        return "grounded"
    if cited_laws and cited_laws & context_laws:
        return "law_only"
    return "ungrounded"


def find_legal_source(
    legal_basis: Optional[str], legal_context: Iterable[dict[str, Any]]
) -> Optional[dict[str, str]]:
    """Devolve o dispositivo citado, com o texto da lei, quando ele foi recuperado.

    Sem isto o alerta exibe "Art. 7º, LGPD" como texto morto, e conferir exige sair
    da tela. Com o texto à mão, o revisor lê o artigo e julga na hora.
    """
    if not legal_basis:
        return None

    cited = _article_numbers(legal_basis)
    if not cited:
        return None

    for chunk in legal_context or []:
        ref = str(chunk.get("article_ref") or "")
        if _article_numbers(ref) & cited:
            content = str(chunk.get("content") or "").strip()
            if not content:
                return None
            return {
                "source": str(chunk.get("source") or ""),
                "article_ref": ref,
                "content": content,
            }
    return None


def annotate_alerts(
    alerts: list[dict[str, Any]],
    document_text: str,
    legal_context: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Anota cada alerta com o resultado das verificações e o texto da lei citada."""
    context = list(legal_context or [])
    annotated = []
    for alert in alerts:
        annotated.append(
            {
                **alert,
                "excerpt_check": verify_excerpt(alert.get("excerpt"), document_text),
                "legal_basis_check": verify_legal_basis(
                    alert.get("legal_basis"), context
                ),
                "legal_source": find_legal_source(alert.get("legal_basis"), context),
            }
        )
    return annotated


def verification_summary(alerts: Iterable[dict[str, Any]]) -> dict[str, int]:
    """Contagem para exibir no topo do relatório."""
    alerts = list(alerts)
    return {
        "total": len(alerts),
        "excerpt_exact": sum(1 for a in alerts if a.get("excerpt_check") == "exact"),
        "excerpt_unverified": sum(
            1 for a in alerts if a.get("excerpt_check") == "not_found"
        ),
        "legal_grounded": sum(
            1 for a in alerts if a.get("legal_basis_check") == "grounded"
        ),
        "legal_ungrounded": sum(
            1 for a in alerts if a.get("legal_basis_check") == "ungrounded"
        ),
    }
