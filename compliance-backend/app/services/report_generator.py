"""Geração do relatório de conformidade em HTML e PDF.

O PDF é o que sai do sistema: vai para o cliente, para a contraparte, para o
arquivo do caso. Se ele mostrar menos do que a tela, o trabalho de verificação
some justamente no artefato que sobrevive.

Por isso o relatório carrega, por alerta, o mesmo que a tela carrega: o trecho
citado com o resultado da conferência e a página, o dispositivo legal com o texto
da lei, e a marcação do revisor. E abre com um quadro dizendo quanto da análise
pôde ser conferido automaticamente, que é a primeira pergunta de quem recebe um
documento produzido com auxílio de IA.

Tudo que vem do modelo, do contrato ou de regra escrita pelo usuário passa por
`escape`. Um contrato com "<" ou "&" quebrava a página inteira antes disso.
"""
from __future__ import annotations

import logging
from datetime import datetime
from html import escape
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ─── Vocabulário ─────────────────────────────────────────────────────────────

SEVERITY = {
    "high": ("Alta", "#9E2323", "#FAE7E7"),
    "medium": ("Média", "#9A5216", "#FBEDE0"),
    "low": ("Baixa", "#1D6B4A", "#E3F1EA"),
}

# Rótulos do resultado da conferência do trecho. O texto diz o que foi feito, não
# um veredito: trecho não localizado pode ser paráfrase correta.
EXCERPT_CHECK = {
    "exact": ("Trecho conferido", "ok"),
    "approximate": ("Trecho aproximado", "warn"),
    "not_found": ("Trecho não localizado", "crit"),
    "empty": ("Cláusula ausente", "neutro"),
}

# "in_base" e "law_only" existem porque a busca traz os artigos mais próximos, e
# um dispositivo correto pode ficar de fora do recorte sem ser inventado.
LEGAL_CHECK = {
    "grounded": ("Artigo conferido na base", "ok"),
    "in_base": ("Artigo existe na base", "ok"),
    "law_only": ("Lei confere, artigo não localizado", "warn"),
    "ungrounded": ("Citação sem respaldo na base", "crit"),
    "no_context": ("Sem base legal recuperada", "neutro"),
    "empty": ("Sem citação legal", "neutro"),
}

RESOLUTION = {
    "to_fix": ("A corrigir", "#9A5216", "#FBEDE0"),
    "not_applicable": ("Não se aplica", "#4C5464", "#EDF0F4"),
    "resolved": ("Resolvido", "#1D6B4A", "#E3F1EA"),
}

SELO_CORES = {
    "ok": ("#1D6B4A", "#E3F1EA"),
    "warn": ("#9A5216", "#FBEDE0"),
    "crit": ("#9E2323", "#FAE7E7"),
    "neutro": ("#4C5464", "#EDF0F4"),
}


def _risk_color(score: int) -> str:
    if score >= 70:
        return "#9E2323"
    if score >= 40:
        return "#9A5216"
    return "#1D6B4A"


def _risk_label(score: int) -> str:
    if score >= 70:
        return "Alto"
    if score >= 40:
        return "Moderado"
    return "Baixo"


def _txt(valor: Any, padrao: str = "-") -> str:
    """Escapa qualquer valor vindo do modelo, do contrato ou do usuário."""
    if valor is None:
        return padrao
    texto = str(valor).strip()
    return escape(texto) if texto else padrao


def _selo(rotulo: str, tom: str) -> str:
    cor, fundo = SELO_CORES.get(tom, SELO_CORES["neutro"])
    return f'<span class="selo" style="color:{cor};background:{fundo}">{escape(rotulo)}</span>'


# ─── Blocos ──────────────────────────────────────────────────────────────────

def _quadro_verificacao(alerts: List[Dict[str, Any]]) -> str:
    """Quanto da análise pôde ser conferido contra as fontes.

    Vem antes dos alertas de propósito: quem recebe um documento produzido com
    auxílio de IA quer saber, primeiro, o que dá para checar sozinho.
    """
    total = len(alerts)
    if not total:
        return ""

    com_trecho = [a for a in alerts if a.get("excerpt_check") not in (None, "empty")]
    conferidos = sum(1 for a in com_trecho if a.get("excerpt_check") == "exact")
    a_conferir = sum(1 for a in com_trecho if a.get("excerpt_check") == "not_found")

    com_lei = [a for a in alerts if a.get("legal_basis_check") not in (None, "empty")]
    apoiados = sum(
        1 for a in com_lei if a.get("legal_basis_check") in ("grounded", "in_base")
    )
    sem_respaldo = sum(1 for a in com_lei if a.get("legal_basis_check") == "ungrounded")

    def linha(rotulo: str, valor: str, detalhe: str) -> str:
        return (
            f'<div class="ver-item"><div class="ver-valor">{valor}</div>'
            f'<div class="ver-rotulo">{escape(rotulo)}</div>'
            f'<div class="ver-detalhe">{escape(detalhe)}</div></div>'
        )

    return f"""
    <section class="bloco">
      <h2>Verificação automática</h2>
      <p class="intro">
        Antes de exibir cada alerta, o sistema procura o trecho citado dentro do
        documento e o dispositivo citado na base de legislação. O que não pôde ser
        confirmado vem assinalado no próprio alerta, para ser conferido na fonte.
      </p>
      <div class="ver-grid">
        {linha("Trechos localizados no documento", f"{conferidos}/{len(com_trecho) or 0}", "citação encontrada no texto")}
        {linha("A conferir na fonte", str(a_conferir), "trecho não localizado")}
        {linha("Citações apoiadas na base legal", f"{apoiados}/{len(com_lei) or 0}", "dispositivo localizado")}
        {linha("Citações sem respaldo", str(sem_respaldo), "não localizado na base")}
      </div>
    </section>"""


def _alerta(indice: int, alert: Dict[str, Any]) -> str:
    rotulo_sev, cor_sev, fundo_sev = SEVERITY.get(
        alert.get("severity", "medium"), SEVERITY["medium"]
    )

    selos = []
    checagem = alert.get("excerpt_check")
    if checagem in EXCERPT_CHECK:
        rotulo, tom = EXCERPT_CHECK[checagem]
        pagina = alert.get("excerpt_page")
        if pagina and checagem in ("exact", "approximate"):
            rotulo = f"{rotulo}, pág. {pagina}"
        selos.append(_selo(rotulo, tom))

    legal = alert.get("legal_basis_check")
    if legal in LEGAL_CHECK:
        rotulo, tom = LEGAL_CHECK[legal]
        selos.append(_selo(rotulo, tom))

    selos_html = f'<div class="selos">{"".join(selos)}</div>' if selos else ""

    excerpt = alert.get("excerpt")
    trecho_html = ""
    if excerpt and str(excerpt).strip() not in ("-", "—", "--", "N/A"):
        trecho_html = f'<blockquote class="trecho">{_txt(excerpt)}</blockquote>'

    base = alert.get("legal_basis")
    fonte = alert.get("legal_source") or {}
    legal_html = ""
    if base:
        corpo = ""
        if fonte.get("content"):
            origem = fonte.get("source") or ""
            ref = fonte.get("article_ref") or ""
            cabecalho = " ".join(p for p in (ref, origem) if p)
            corpo = (
                f'<div class="lei-cabecalho">{_txt(cabecalho or base, "")}</div>'
                f'<div class="lei-texto">{_txt(fonte["content"], "")}</div>'
            )
        else:
            corpo = f'<div class="lei-cabecalho">{_txt(base, "")}</div>'
        legal_html = f'<div class="lei">{corpo}</div>'

    resolucao = alert.get("resolution")
    resolucao_html = ""
    if resolucao in RESOLUTION:
        rotulo, cor, fundo = RESOLUTION[resolucao]
        comentario = alert.get("resolution_comment")
        extra = f' <span class="res-comentario">{_txt(comentario, "")}</span>' if comentario else ""
        resolucao_html = (
            f'<div class="resolucao"><span class="selo" style="color:{cor};'
            f'background:{fundo}">Revisor: {escape(rotulo)}</span>{extra}</div>'
        )

    return f"""
    <article class="alerta">
      <div class="alerta-topo">
        <span class="num">{indice}</span>
        <span class="selo" style="color:{cor_sev};background:{fundo_sev}">Severidade {escape(rotulo_sev.lower())}</span>
        <h3>{_txt(alert.get("rule_name"), "Regra")}</h3>
      </div>
      <p class="problema">{_txt(alert.get("issue"))}</p>
      {trecho_html}
      {selos_html}
      {legal_html}
      <div class="sugestao"><span class="rot">Sugestão</span>{_txt(alert.get("suggestion"))}</div>
      {resolucao_html}
    </article>"""


def _checklist(rules: List[Dict[str, Any]], alerts: List[Dict[str, Any]]) -> str:
    """O que foi verificado, e não só o que deu problema.

    Uma regra sem alerta é informação: significa que aquele ponto foi olhado e
    passou. Sem esta lista, o relatório não distingue "está correto" de "não foi
    verificado", que é a diferença entre um parecer e uma lista de reclamações.
    """
    if not rules:
        return ""

    com_alerta = {a.get("rule_name") for a in alerts}
    linhas = []
    for regra in rules:
        nome = regra.get("name", "")
        apontada = nome in com_alerta
        cor, fundo = ("#9E2323", "#FAE7E7") if apontada else ("#1D6B4A", "#E3F1EA")
        marca = "apontada" if apontada else "conforme"
        linhas.append(
            f'<tr><td class="chk-nome">{_txt(nome)}</td>'
            f'<td class="chk-estado"><span class="selo" style="color:{cor};'
            f'background:{fundo}">{marca}</span></td></tr>'
        )

    conformes = len(rules) - len([r for r in rules if r.get("name") in com_alerta])
    return f"""
    <section class="bloco">
      <h2>Regras verificadas</h2>
      <p class="intro">
        {conformes} de {len(rules)} regras não geraram apontamento neste documento.
        A lista completa registra o que foi efetivamente checado.
      </p>
      <table class="checklist">{"".join(linhas)}</table>
    </section>"""


# ─── Documento ───────────────────────────────────────────────────────────────

def generate_html_report(
    document: Dict[str, Any],
    analysis: Dict[str, Any],
    rules: List[Dict[str, Any]],
    *,
    generated_by: Optional[str] = None,
) -> str:
    """Monta o relatório completo em HTML, pronto para virar PDF."""
    risco = analysis.get("risk_score") or 0
    cor_risco = _risk_color(risco)
    alerts = analysis.get("alerts") or []
    missing = analysis.get("missing_clauses") or []
    agora = datetime.now().strftime("%d/%m/%Y às %H:%M")

    por_severidade = {"high": 0, "medium": 0, "low": 0}
    for a in alerts:
        chave = a.get("severity", "medium")
        if chave in por_severidade:
            por_severidade[chave] += 1

    alertas_html = "".join(_alerta(i + 1, a) for i, a in enumerate(alerts)) or (
        '<p class="vazio">Nenhum apontamento nas regras verificadas.</p>'
    )

    ausentes_html = (
        "<ul class='ausentes'>" + "".join(f"<li>{_txt(c)}</li>" for c in missing) + "</ul>"
        if missing
        else '<p class="vazio">Nenhuma cláusula esperada foi identificada como ausente.</p>'
    )

    rodape_tecnico = []
    if analysis.get("model"):
        rodape_tecnico.append(f"Modelo {_txt(analysis['model'], '')}")
    if analysis.get("prompt_version"):
        rodape_tecnico.append(f"prompt v{_txt(analysis['prompt_version'], '')}")
    tecnico = " · ".join(rodape_tecnico)

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<title>Relatório de conformidade</title>
<style>
  @page {{
    size: A4;
    margin: 2.2cm 1.9cm 2.4cm;
    @bottom-left {{
      content: "ComplianceAI · {escape(document.get('filename', 'documento'))}";
      font-family: Georgia, serif; font-size: 7.5pt; color: #7C8496;
    }}
    @bottom-right {{
      content: "Página " counter(page) " de " counter(pages);
      font-family: Georgia, serif; font-size: 7.5pt; color: #7C8496;
    }}
  }}

  * {{ box-sizing: border-box; }}
  body {{
    font-family: Georgia, 'Times New Roman', serif;
    font-size: 9.8pt; line-height: 1.55; color: #15171C; margin: 0;
  }}

  h1, h2, h3 {{ margin: 0; font-weight: normal; }}

  .capa {{ border-bottom: 2px solid #15171C; padding-bottom: 14pt; margin-bottom: 20pt; }}
  .marca {{
    font-size: 7.5pt; letter-spacing: 1.6pt; text-transform: uppercase;
    color: #5B3A8E; margin-bottom: 8pt;
  }}
  h1 {{ font-size: 19pt; letter-spacing: -0.4pt; margin-bottom: 6pt; }}
  .arquivo {{ font-size: 10pt; color: #4C5464; }}
  .emissao {{ font-size: 8pt; color: #7C8496; margin-top: 8pt; }}

  .resumo-grid {{ display: flex; gap: 14pt; margin-bottom: 20pt; }}
  .risco {{
    border: 1px solid #D9DDE5; border-left: 3px solid {cor_risco};
    padding: 11pt 14pt; min-width: 150pt;
  }}
  .risco-valor {{ font-size: 27pt; color: {cor_risco}; line-height: 1; }}
  .risco-rotulo {{ font-size: 8pt; text-transform: uppercase; letter-spacing: 0.7pt; color: #4C5464; margin-top: 5pt; }}
  .contagem {{ flex: 1; border: 1px solid #D9DDE5; padding: 11pt 14pt; }}
  .contagem-linha {{ display: flex; justify-content: space-between; font-size: 9pt; padding: 2pt 0; }}
  .contagem-linha b {{ font-weight: normal; color: #4C5464; }}

  .bloco {{ margin-bottom: 20pt; }}
  h2 {{
    font-size: 8pt; text-transform: uppercase; letter-spacing: 1.1pt;
    color: #5B3A8E; padding-bottom: 4pt; border-bottom: 1px solid #D9DDE5;
    margin-bottom: 10pt;
  }}
  .intro {{ font-size: 8.6pt; color: #4C5464; margin: 0 0 10pt; }}
  .sumario {{ font-size: 10pt; margin: 0; }}

  .ver-grid {{ display: flex; gap: 9pt; }}
  .ver-item {{ flex: 1; border: 1px solid #D9DDE5; padding: 8pt 10pt; }}
  .ver-valor {{ font-size: 15pt; color: #15171C; line-height: 1.1; }}
  .ver-rotulo {{ font-size: 7.6pt; color: #15171C; margin-top: 3pt; }}
  .ver-detalhe {{ font-size: 7pt; color: #7C8496; }}

  .alerta {{
    border: 1px solid #D9DDE5; padding: 11pt 13pt 12pt;
    margin-bottom: 10pt; break-inside: avoid;
  }}
  .alerta-topo {{ margin-bottom: 7pt; }}
  .num {{
    font-size: 7.5pt; color: #7C8496; border: 1px solid #D9DDE5;
    padding: 1pt 5pt; margin-right: 6pt;
  }}
  .alerta-topo h3 {{ font-size: 11pt; margin-top: 6pt; }}
  .selo {{
    font-size: 7.2pt; padding: 1.5pt 6pt; margin-right: 4pt;
    letter-spacing: 0.3pt; white-space: nowrap;
  }}
  .problema {{ margin: 0 0 8pt; font-size: 9.4pt; }}
  .trecho {{
    margin: 0 0 7pt; padding: 7pt 10pt; background: #F4F6F8;
    border-left: 2px solid #D9DDE5; font-size: 9pt; color: #4C5464; font-style: italic;
  }}
  .selos {{ margin-bottom: 8pt; }}
  .lei {{ border-top: 1px solid #E7EAF0; padding-top: 7pt; margin-bottom: 8pt; }}
  .lei-cabecalho {{
    font-size: 7.6pt; text-transform: uppercase; letter-spacing: 0.5pt;
    color: #15171C; margin-bottom: 3pt;
  }}
  .lei-texto {{ font-size: 8.6pt; color: #4C5464; }}
  .sugestao {{ font-size: 9pt; }}
  .sugestao .rot {{
    font-size: 7.4pt; text-transform: uppercase; letter-spacing: 0.6pt;
    color: #5B3A8E; margin-right: 6pt;
  }}
  .resolucao {{ margin-top: 8pt; padding-top: 7pt; border-top: 1px solid #E7EAF0; }}
  .res-comentario {{ font-size: 8.4pt; color: #4C5464; }}

  .checklist {{ width: 100%; border-collapse: collapse; }}
  .checklist td {{ padding: 4pt 0; border-bottom: 1px solid #E7EAF0; font-size: 8.8pt; }}
  .chk-estado {{ text-align: right; width: 80pt; }}

  .ausentes {{ margin: 0; padding-left: 14pt; font-size: 9.2pt; }}
  .ausentes li {{ margin-bottom: 3pt; }}
  .vazio {{ font-size: 9pt; color: #4C5464; margin: 0; }}

  h2 {{ break-after: avoid; }}
  .ver-grid, .checklist, .aviso {{ break-inside: avoid; }}

  .aviso {{
    border: 1px solid #D9DDE5; border-left: 3px solid #9A5216;
    padding: 10pt 13pt; margin-top: 20pt; font-size: 8.4pt; color: #4C5464;
  }}
  .aviso b {{ color: #15171C; font-weight: normal; }}
</style>
</head>
<body>

<header class="capa">
  <div class="marca">ComplianceAI</div>
  <h1>Relatório de conformidade contratual</h1>
  <div class="arquivo">{_txt(document.get("filename"), "documento")}</div>
  <div class="emissao">
    Emitido em {escape(agora)}{f" por {_txt(generated_by, '')}" if generated_by else ""}
  </div>
</header>

<div class="resumo-grid">
  <div class="risco">
    <div class="risco-valor">{risco}</div>
    <div class="risco-rotulo">Risco {escape(_risk_label(risco).lower())}</div>
  </div>
  <div class="contagem">
    <div class="contagem-linha"><b>Apontamentos</b><span>{len(alerts)}</span></div>
    <div class="contagem-linha"><b>Severidade alta</b><span>{por_severidade["high"]}</span></div>
    <div class="contagem-linha"><b>Severidade média</b><span>{por_severidade["medium"]}</span></div>
    <div class="contagem-linha"><b>Severidade baixa</b><span>{por_severidade["low"]}</span></div>
    <div class="contagem-linha"><b>Regras verificadas</b><span>{len(rules)}</span></div>
  </div>
</div>

<section class="bloco">
  <h2>Resumo</h2>
  <p class="sumario">{_txt(analysis.get("summary"))}</p>
</section>

{_quadro_verificacao(alerts)}

<section class="bloco">
  <h2>Apontamentos</h2>
  {alertas_html}
</section>

<section class="bloco">
  <h2>Cláusulas ausentes</h2>
  {ausentes_html}
</section>

{_checklist(rules, alerts)}

<div class="aviso">
  <b>Sobre este relatório.</b> Foi produzido com auxílio de inteligência artificial
  sobre a legislação brasileira e as regras configuradas pelo escritório. Os selos
  indicam o que o sistema conferiu automaticamente: se o trecho citado consta do
  documento e se o dispositivo citado consta da base de legislação. A conferência
  atesta procedência, não interpretação jurídica, e o documento não constitui
  parecer nem dispensa a análise do advogado responsável.
  {f"<br>{escape(tecnico)}" if tecnico else ""}
</div>

</body>
</html>"""


def generate_pdf_report(html_content: str) -> bytes:
    """Converte o HTML do relatório em PDF."""
    from weasyprint import HTML

    try:
        return HTML(string=html_content).write_pdf()
    except Exception as exc:
        logger.error("Falha ao gerar PDF do relatório: %s", exc)
        raise
