"""
Report generation service — HTML and PDF compliance reports.

Uses WeasyPrint for PDF rendering with professional styling.
"""
import logging
from datetime import datetime
from typing import Dict, Any, List
from html import escape

logger = logging.getLogger(__name__)

# WeasyPrint requires native GTK/GLib libraries that may not be present on all
# platforms (notably Windows without a GTK runtime). We import it lazily inside
# generate_pdf_report() so the rest of the module — and HTML generation — works
# fine even when those libraries are unavailable.


def _severity_color(severity: str) -> str:
    """Return color hex for severity level."""
    return {"high": "#dc3545", "medium": "#f59e0b", "low": "#10b981"}.get(severity, "#6b7280")


def _severity_label(severity: str) -> str:
    """Return Portuguese label for severity."""
    return {"high": "Alta", "medium": "Média", "low": "Baixa"}.get(severity, severity)


def _risk_color(score: int) -> str:
    """Return color hex for risk score."""
    if score <= 30:
        return "#10b981"
    if score <= 60:
        return "#f59e0b"
    return "#dc3545"


def _risk_label(score: int) -> str:
    """Return Portuguese risk label."""
    if score <= 30:
        return "Baixo"
    if score <= 60:
        return "Moderado"
    return "Alto"


def _traceability(analysis: dict) -> str:
    """Modelo e versao dos criterios, para que o relatorio possa ser auditado depois."""
    partes = []
    if analysis.get("model"):
        partes.append(f"modelo {analysis['model']}")
    if analysis.get("prompt_version"):
        partes.append(f"critérios v{analysis['prompt_version']}")
    return (" | " + " | ".join(partes)) if partes else ""


def generate_html_report(
    document: Dict[str, Any],
    analysis: Dict[str, Any],
    rules: List[Dict[str, Any]],
) -> str:
    """Generate a styled HTML compliance report.

    Args:
        document: Dict with filename key.
        analysis: Dict with risk_score, summary, alerts, missing_clauses.
        rules: List of dicts with name and severity.

    Returns:
        Complete HTML string ready for rendering or PDF conversion.
    """
    risk_score = analysis["risk_score"]
    r_color = _risk_color(risk_score)
    r_label = _risk_label(risk_score)
    alerts = analysis.get("alerts", [])
    missing = analysis.get("missing_clauses", [])
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")

    # Build alerts HTML
    alerts_html = ""
    for alert in alerts:
        sev_color = _severity_color(alert.get("severity", "medium"))
        sev_label = _severity_label(alert.get("severity", "medium"))
        excerpt = alert.get("excerpt", "—")
        excerpt_html = f'<p class="excerpt">"{excerpt}"</p>' if excerpt and excerpt != "—" else ""

        # Normalizar possíveis nomes de campo para a base legal
        legal_basis = alert.get("legal_basis") or alert.get("legal_base") or alert.get("base_legal")
        if isinstance(legal_basis, str):
            legal_basis = legal_basis.strip() or None
        
        # Escapar e formatar a base legal se existir
        legal_basis_html = ""
        if legal_basis:
            # exibe em itálico e negrito o rótulo, e o texto da base legal
            legal_basis_html = (
                f'<p class="base-legal"><strong>Base legal:</strong> {escape(legal_basis)}</p>'
            )
        
        alerts_html += f"""
        <div class="alert-card" style="border-left-color: {sev_color};">
            <div class="alert-header">
                <span class="badge" style="background: {sev_color};">{sev_label}</span>
                <strong>{alert.get('rule_name', 'Regra')}</strong>
            </div>
            <p><strong>Problema:</strong> {alert.get('issue', '—')}</p>
            {excerpt_html}
            <p class="suggestion">💡 <strong>Sugestão:</strong> {escape(alert.get('suggestion', '—'))}</p>
        </div>"""

    # Build missing clauses HTML
    missing_html = ""
    if missing:
        items = "".join(f"<li>{clause}</li>" for clause in missing)
        missing_html = f"<ul>{items}</ul>"
    else:
        missing_html = '<p class="ok">Nenhuma cláusula ausente detectada.</p>'

    # Build checklist HTML
    alerted_names = {a.get("rule_name") for a in alerts}
    checklist_html = ""
    for rule in rules:
        name = rule.get("name", "")
        is_ok = name not in alerted_names
        icon = "✅" if is_ok else "❌"
        color = "#166534" if is_ok else "#991b1b"
        bg = "#f0fdf4" if is_ok else "#fef2f2"
        checklist_html += f'<div class="check-item" style="color: {color}; background: {bg};">{icon} {name}</div>'

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <style>
        @page {{
            size: A4;
            margin: 2cm;
            @bottom-center {{
                content: "ComplianceAI — Relatório de Compliance — Página " counter(page) " de " counter(pages);
                font-size: 8px;
                color: #94a3b8;
            }}
        }}
        body {{
            font-family: 'Helvetica Neue', Arial, sans-serif;
            color: #1e293b;
            line-height: 1.6;
            font-size: 11px;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 3px solid #6366f1;
            padding-bottom: 12px;
            margin-bottom: 20px;
        }}
        .header h1 {{
            color: #6366f1;
            font-size: 22px;
            margin: 0;
        }}
        .header .meta {{
            text-align: right;
            color: #64748b;
            font-size: 10px;
        }}
        h2 {{
            color: #0f172a;
            font-size: 15px;
            border-bottom: 1px solid #e2e8f0;
            padding-bottom: 5px;
            margin-top: 24px;
            margin-bottom: 10px;
        }}
        .score-box {{
            text-align: center;
            padding: 20px;
            background: #f8fafc;
            border-radius: 10px;
            border: 1px solid #e2e8f0;
            margin-bottom: 16px;
        }}
        .score-value {{
            font-size: 48px;
            font-weight: 800;
            color: {r_color};
            line-height: 1;
        }}
        .score-label {{
            font-size: 14px;
            color: {r_color};
            font-weight: 600;
            margin-top: 4px;
        }}
        .score-bar {{
            width: 200px;
            height: 8px;
            background: #e5e7eb;
            border-radius: 4px;
            margin: 10px auto 0;
            overflow: hidden;
        }}
        .score-bar-fill {{
            height: 100%;
            width: {risk_score}%;
            background: {r_color};
            border-radius: 4px;
        }}
        .summary {{
            background: #f8fafc;
            border-radius: 8px;
            padding: 14px;
            font-size: 12px;
            line-height: 1.7;
        }}
        .alert-card {{
            border-left: 4px solid #6b7280;
            padding: 10px 14px;
            margin: 8px 0;
            background: #f8fafc;
            border-radius: 0 6px 6px 0;
            page-break-inside: avoid;
        }}
        .alert-header {{
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 6px;
        }}
        .badge {{
            color: white;
            padding: 2px 8px;
            border-radius: 10px;
            font-size: 9px;
            font-weight: 700;
            text-transform: uppercase;
        }}
        .excerpt {{
            font-style: italic;
            color: #64748b;
            font-size: 10px;
            margin: 4px 0;
        }}
        .suggestion {{
            color: #4338ca;
            background: #eef2ff;
            padding: 6px 10px;
            border-radius: 4px;
            font-size: 10px;
            margin-top: 6px;
        }}
        .base-legal {{
            font-style: italic;
            color: #475569;
            font-size: 12px;
            margin-top: 8px;
            padding-left: 5px;
            border-left: 2px solid #cbd5e1;
        }}
        .check-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 4px;
        }}
        .check-item {{
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 10px;
            font-weight: 500;
        }}
        .ok {{
            color: #16a34a;
            font-weight: 600;
        }}
        .footer {{
            margin-top: 30px;
            padding-top: 10px;
            border-top: 1px solid #e2e8f0;
            text-align: center;
            color: #94a3b8;
            font-size: 9px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🛡️ Relatório de Compliance</h1>
        <div class="meta">
            <strong>{document.get('filename', 'documento')}</strong><br>
            Gerado em: {now_str}
        </div>
    </div>

    <h2>Score de Risco</h2>
    <div class="score-box">
        <div class="score-value">{risk_score}</div>
        <div class="score-label">Risco {r_label}</div>
        <div class="score-bar"><div class="score-bar-fill"></div></div>
    </div>

    <h2>Resumo Executivo</h2>
    <div class="summary">{analysis.get('summary', '—')}</div>

    <h2>Checklist de Conformidade</h2>
    <div class="check-grid">{checklist_html}</div>

    <h2>Alertas ({len(alerts)} encontrados)</h2>
    {alerts_html if alerts_html else '<p class="ok">Nenhum alerta — documento em conformidade.</p>'}

    <h2>Cláusulas Ausentes</h2>
    {missing_html}

    <h2>Regras Verificadas ({len(rules)})</h2>
    <ul>
        {"".join(f'<li><strong>{r.get("name", "")}</strong>: severidade {_severity_label(r.get("severity", "medium"))}</li>' for r in rules)}
    </ul>

    <div class="footer">
        <strong>ComplianceAI</strong> | Análise automatizada de contratos com IA<br><br>
        Esta análise é gerada por inteligência artificial e serve como apoio à revisão contratual.
        <strong>Não substitui parecer jurídico.</strong> Confira os trechos citados no documento
        original e os dispositivos legais antes de tomar qualquer decisão.<br><br>
        Gerado em {now_str}{_traceability(analysis)}
    </div>
</body>
</html>"""

    return html


def generate_pdf_report(html_content: str) -> bytes:
    """Convert HTML report to PDF bytes using WeasyPrint.

    Args:
        html_content: Complete HTML string.

    Returns:
        PDF file as bytes.

    Raises:
        OSError: If WeasyPrint's native GTK libraries are not installed.
            On Windows, follow https://doc.courtbouillon.org/weasyprint/stable/first_steps.html
    """
    from weasyprint import HTML  # lazy import — requires GTK runtime

    logger.info("Gerando PDF do relatório...")
    pdf_bytes = HTML(string=html_content).write_pdf()
    logger.info(f"PDF gerado: {len(pdf_bytes)} bytes")
    return pdf_bytes
