"""
Rules API routes — CRUD for compliance rules (admin only for create/edit/delete).
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List

from app.core.database import get_db
from app.core.limiter import limiter

from app.core.security import get_current_user, get_current_admin
from app.models import User, Rule
from app.schemas import RuleCreate, RuleUpdate, RuleResponse

router = APIRouter(prefix="/rules", tags=["Regras de Conformidade"])


@router.get("", response_model=List[RuleResponse])
async def list_rules(
    active_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all compliance rules."""
    query = select(Rule).order_by(Rule.created_at)
    if active_only:
        query = query.where(Rule.is_active == True)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{rule_id}", response_model=RuleResponse)
async def get_rule(
    rule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a single rule by ID."""
    result = await db.execute(select(Rule).where(Rule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Regra não encontrada")
    return rule


@router.post("", response_model=RuleResponse, status_code=201)
async def create_rule(
    data: RuleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """Create a new compliance rule (admin only)."""
    rule = Rule(
        name=data.name,
        description=data.description,
        severity=data.severity,
        criteria=data.criteria,
    )
    db.add(rule)
    await db.flush()
    await db.refresh(rule)
    return rule


@router.patch("/{rule_id}", response_model=RuleResponse)
async def update_rule(
    rule_id: uuid.UUID,
    data: RuleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """Update an existing rule (admin only)."""
    result = await db.execute(select(Rule).where(Rule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Regra não encontrada")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(rule, key, value)

    await db.flush()
    await db.refresh(rule)
    return rule


@router.delete("/{rule_id}", status_code=204)
async def delete_rule(
    rule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """Delete a compliance rule (admin only)."""
    result = await db.execute(select(Rule).where(Rule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Regra não encontrada")
    await db.delete(rule)


@router.patch("/{rule_id}/toggle", response_model=RuleResponse)
async def toggle_rule(
    rule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """Toggle a rule active/inactive (admin only)."""
    result = await db.execute(select(Rule).where(Rule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Regra não encontrada")

    rule.is_active = not rule.is_active
    await db.flush()
    await db.refresh(rule)
    return rule
