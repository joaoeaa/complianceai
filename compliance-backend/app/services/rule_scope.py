"""Resolucao de escopo das regras de conformidade.

Uma regra vive em um de tres escopos:

    global        organization_id e user_id nulos — as regras padrao do sistema,
                  compartilhadas por todos e somente leitura
    user          user_id preenchido — regras pessoais de quem trabalha sozinho
    organization  organization_id preenchido — regras da equipe

Quem consome ve sempre as globais mais as do proprio escopo. Como as globais sao
compartilhadas, "desativar para mim" nao pode ser um UPDATE nelas: vira uma linha
em `rule_overrides`, aplicada apenas dentro daquele escopo.

As funcoes aqui montam os `select(...)`, sem executa-los, para servir tanto a API
assincrona quanto o worker sincrono.
"""
from __future__ import annotations

from typing import Iterable, Optional
from uuid import UUID

from sqlalchemy import Select, or_, select

from app.models import Rule, RuleOverride


def visible_rules_query(
    *, user_id: Optional[UUID], organization_id: Optional[UUID] = None
) -> Select:
    """Regras que este escopo enxerga: as globais mais as proprias.

    Quando `organization_id` vem preenchido o escopo e a equipe, e as regras
    pessoais ficam de fora — um documento da equipe segue as regras da equipe.
    """
    if organization_id is not None:
        own = Rule.organization_id == organization_id
    else:
        own = Rule.user_id == user_id if user_id is not None else None

    is_global = Rule.organization_id.is_(None) & Rule.user_id.is_(None)
    condition = is_global if own is None else or_(is_global, own)

    return select(Rule).where(condition).order_by(Rule.created_at)


def overrides_query(
    *, user_id: Optional[UUID], organization_id: Optional[UUID] = None
) -> Select:
    """Overrides que valem neste escopo."""
    if organization_id is not None:
        scope = RuleOverride.organization_id == organization_id
    else:
        scope = RuleOverride.user_id == user_id

    return select(RuleOverride).where(scope)


def apply_overrides(
    rules: Iterable[Rule], overrides: Iterable[RuleOverride]
) -> list[dict]:
    """Combina regras e overrides no estado efetivo de cada regra.

    Devolve dicionarios em vez de mutar os objetos ORM — mutar marcaria as regras
    globais como sujas e as gravaria de volta no commit seguinte, vazando a
    preferencia de um escopo para todos os outros.
    """
    by_rule = {o.rule_id: o.is_active for o in overrides}
    resolved = []
    for rule in rules:
        resolved.append(
            {
                "id": rule.id,
                "name": rule.name,
                "description": rule.description,
                "severity": rule.severity,
                "criteria": rule.criteria,
                "category": rule.category or "geral",
                "is_active": by_rule.get(rule.id, rule.is_active),
                "created_at": rule.created_at,
                "scope": rule.scope,
                "editable": rule.scope != "global",
            }
        )
    return resolved


def active_rules_for_prompt(
    rules: Iterable[Rule], overrides: Iterable[RuleOverride]
) -> list[dict]:
    """So as regras ativas, no formato que o prompt do analisador espera."""
    return [
        {"name": r["name"], "severity": r["severity"], "criteria": r["criteria"]}
        for r in apply_overrides(rules, overrides)
        if r["is_active"]
    ]
