"""
Rules API routes — CRUD das regras de conformidade, com escopo por usuário ou equipe.

Cada pessoa enxerga as regras globais do sistema mais as do próprio escopo, e só
edita as que são suas. As globais são compartilhadas: quem quiser desligá-las usa
o endpoint de toggle, que grava um override válido apenas naquele escopo.
"""
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models import Rule, RuleOverride, User
from app.schemas import RuleCreate, RuleResponse, RuleUpdate
from app.services.scope import require_org_membership as _require_org_membership
from app.services.rule_scope import apply_overrides, overrides_query, visible_rules_query

router = APIRouter(prefix="/rules", tags=["Regras de Conformidade"])


# ─── Helpers de escopo ────────────────────────────────────────────────────────

async def _get_rule_or_404(rule_id: uuid.UUID, db: AsyncSession) -> Rule:
    result = await db.execute(select(Rule).where(Rule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Regra não encontrada")
    return rule


async def _require_can_edit(rule: Rule, user: User, db: AsyncSession) -> None:
    """Define quem pode alterar esta regra."""
    if rule.scope == "global":
        raise HTTPException(
            status_code=403,
            detail="Regras padrão do sistema não podem ser editadas. Desative-a para você ou crie uma regra própria.",
        )
    if rule.scope == "user":
        if rule.user_id != user.id:
            raise HTTPException(status_code=404, detail="Regra não encontrada")
        return
    await _require_org_membership(rule.organization_id, user, db, must_manage=True)


async def _resolve(
    rules, user: User, organization_id: Optional[uuid.UUID], db: AsyncSession
) -> list[dict]:
    overrides = (
        await db.execute(overrides_query(user_id=user.id, organization_id=organization_id))
    ).scalars().all()
    return apply_overrides(rules, overrides)


# ─── Leitura ──────────────────────────────────────────────────────────────────

@router.get("", response_model=List[RuleResponse])
async def list_rules(
    active_only: bool = Query(False),
    organization_id: Optional[uuid.UUID] = Query(
        None, description="Regras desta equipe; omitido lista as regras pessoais"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista as regras globais do sistema mais as do escopo escolhido."""
    if organization_id is not None:
        await _require_org_membership(organization_id, current_user, db)

    rules = (
        await db.execute(
            visible_rules_query(user_id=current_user.id, organization_id=organization_id)
        )
    ).scalars().all()

    resolved = await _resolve(rules, current_user, organization_id, db)
    if active_only:
        resolved = [r for r in resolved if r["is_active"]]
    return resolved


@router.get("/{rule_id}", response_model=RuleResponse)
async def get_rule(
    rule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Detalha uma regra visível ao usuário."""
    rule = await _get_rule_or_404(rule_id, db)

    if rule.scope == "user" and rule.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Regra não encontrada")
    if rule.scope == "organization":
        await _require_org_membership(rule.organization_id, current_user, db)

    resolved = await _resolve([rule], current_user, rule.organization_id, db)
    return resolved[0]


# ─── Escrita ──────────────────────────────────────────────────────────────────

@router.post("", response_model=RuleResponse, status_code=201)
async def create_rule(
    data: RuleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cria uma regra pessoal, ou da equipe quando `organization_id` é informado."""
    if data.organization_id is not None:
        await _require_org_membership(data.organization_id, current_user, db, must_manage=True)

    rule = Rule(
        name=data.name,
        description=data.description,
        severity=data.severity,
        criteria=data.criteria,
        organization_id=data.organization_id,
        user_id=None if data.organization_id else current_user.id,
    )
    db.add(rule)
    await db.flush()
    await db.refresh(rule)
    return apply_overrides([rule], [])[0]


@router.patch("/{rule_id}", response_model=RuleResponse)
async def update_rule(
    rule_id: uuid.UUID,
    data: RuleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Edita uma regra própria ou da equipe."""
    rule = await _get_rule_or_404(rule_id, db)
    await _require_can_edit(rule, current_user, db)

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(rule, key, value)

    await db.flush()
    await db.refresh(rule)
    return apply_overrides([rule], [])[0]


@router.delete("/{rule_id}", status_code=204)
async def delete_rule(
    rule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Exclui uma regra própria ou da equipe."""
    rule = await _get_rule_or_404(rule_id, db)
    await _require_can_edit(rule, current_user, db)
    await db.delete(rule)


@router.patch("/{rule_id}/toggle", response_model=RuleResponse)
async def toggle_rule(
    rule_id: uuid.UUID,
    organization_id: Optional[uuid.UUID] = Query(
        None, description="Alterna no escopo desta equipe; omitido usa o escopo pessoal"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Ativa ou desativa uma regra.

    Regras próprias mudam direto. Regras globais não são alteradas: grava-se um
    override que vale só para este usuário ou equipe.
    """
    rule = await _get_rule_or_404(rule_id, db)

    if rule.scope != "global":
        await _require_can_edit(rule, current_user, db)
        rule.is_active = not rule.is_active
        await db.flush()
        await db.refresh(rule)
        return apply_overrides([rule], [])[0]

    # Regra global: o estado efetivo vive no override deste escopo.
    if organization_id is not None:
        await _require_org_membership(organization_id, current_user, db, must_manage=True)

    scope_user_id = None if organization_id else current_user.id
    existing = (
        await db.execute(
            select(RuleOverride).where(
                RuleOverride.rule_id == rule.id,
                RuleOverride.user_id == scope_user_id,
                RuleOverride.organization_id == organization_id,
            )
        )
    ).scalar_one_or_none()

    if existing:
        existing.is_active = not existing.is_active
        override = existing
    else:
        override = RuleOverride(
            rule_id=rule.id,
            user_id=scope_user_id,
            organization_id=organization_id,
            is_active=not rule.is_active,
        )
        db.add(override)

    await db.flush()
    await db.refresh(override)
    return apply_overrides([rule], [override])[0]
