"""Aprendizado a partir do feedback dos revisores.

Cada alerta pode ser marcado como acerto ou falso positivo, com comentário. O
agregado disso vira um trecho do prompt: quantas vezes cada regra acertou, a
taxa de falso positivo e até três comentários de exemplo. Uma regra que erra
muito faz o modelo ficar mais conservador nela.

O agregado é sempre restrito ao escopo do documento em análise. Isso não é
higiene estatística, é sigilo: os comentários entram no prompt em texto literal,
e o revisor escreve neles sobre o contrato do próprio cliente.

Mora aqui, e não no módulo do worker, porque o worker carrega o Celery junto e
por isso é substituído por mock em boa parte da suíte.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import case as sa_case
from sqlalchemy import func, select


def feedback_scope_filter(doc):
    """Condição que seleciona o feedback do mesmo escopo do documento.

    Documento de equipe aprende com o feedback da equipe; documento pessoal, com
    o de quem o enviou.
    """
    from app.models import Document

    if doc.organization_id is not None:
        return Document.organization_id == doc.organization_id
    return (Document.user_id == doc.user_id) & Document.organization_id.is_(None)


def load_feedback_learnings(db, doc) -> list[dict[str, Any]]:
    """Agrega o feedback do escopo de `doc`, por regra.

    Devolve dicts com rule_name, total, correct, incorrect, false_positive_rate e
    sample_comments.
    """
    from app.models import AlertFeedback, Analysis, Document

    # AlertFeedback não guarda escopo: ele chega pela análise e pelo documento.
    do_escopo = (
        select(AlertFeedback.id)
        .join(Analysis, Analysis.id == AlertFeedback.analysis_id)
        .join(Document, Document.id == Analysis.document_id)
        .where(feedback_scope_filter(doc))
        .scalar_subquery()
    )

    linhas = db.execute(
        select(
            AlertFeedback.rule_name,
            func.count(AlertFeedback.id).label("total"),
            func.sum(sa_case((AlertFeedback.is_correct == True, 1), else_=0)).label("correct"),  # noqa: E712
            func.sum(sa_case((AlertFeedback.is_correct == False, 1), else_=0)).label("incorrect"),  # noqa: E712
        )
        .where(AlertFeedback.id.in_(do_escopo))
        .group_by(AlertFeedback.rule_name)
        .having(func.count(AlertFeedback.id) >= 1)
    ).all()

    aprendizados = []
    for rule_name, total, correct, incorrect in linhas:
        correct = int(correct or 0)
        incorrect = int(incorrect or 0)
        fp_rate = round((incorrect / total) * 100, 1) if total > 0 else 0.0

        comentarios = db.execute(
            select(AlertFeedback.comment)
            .where(
                AlertFeedback.id.in_(do_escopo),
                AlertFeedback.rule_name == rule_name,
                AlertFeedback.is_correct == False,  # noqa: E712
                AlertFeedback.comment.isnot(None),
                AlertFeedback.comment != "",
            )
            .order_by(AlertFeedback.created_at.desc())
            .limit(3)
        ).all()

        aprendizados.append({
            "rule_name": rule_name,
            "total": total,
            "correct": correct,
            "incorrect": incorrect,
            "false_positive_rate": fp_rate,
            "sample_comments": [c for (c,) in comentarios if c],
        })

    return aprendizados
