"""
Contract Templates API — CRUD for reusable contract type definitions.

FASE 2: Templates define which rules apply to a specific type of contract
(e.g., NDA, service agreement) and can include custom AI instructions.
"""
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.core.security import get_current_user
from app.api.organizations import _get_org_or_404, _require_org_member, _require_org_admin
from app.schemas import (
    ContractTemplateCreate,
    ContractTemplateUpdate,
    ContractTemplateResponse,
    ContractTemplateListResponse,
)

router = APIRouter(prefix="/organizations/{org_id}/templates", tags=["Contract Templates"])


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _get_template_or_404(template_id: UUID, org_id: UUID, db: AsyncSession):
    from app import ContractTemplate
    result = await db.execute(
        select(ContractTemplate).where(
            ContractTemplate.id == template_id,
            ContractTemplate.organization_id == org_id,
        )
    )
    tpl = result.scalar_one_or_none()
    if not tpl:
        raise HTTPException(status_code=404, detail="Template não encontrado")
    return tpl


def _serialize_template(tpl) -> ContractTemplateResponse:
    """Convert rule_ids UUIDs to strings for JSON compatibility."""
    rule_ids = tpl.rule_ids or []
    # Ensure they are UUID objects for the schema
    from uuid import UUID as PyUUID
    parsed_ids = []
    for rid in rule_ids:
        if isinstance(rid, str):
            parsed_ids.append(PyUUID(rid))
        else:
            parsed_ids.append(rid)

    return ContractTemplateResponse(
        id=tpl.id,
        organization_id=tpl.organization_id,
        name=tpl.name,
        description=tpl.description,
        category=tpl.category,
        rule_ids=parsed_ids,
        custom_instructions=tpl.custom_instructions,
        is_active=tpl.is_active,
        created_by=tpl.created_by,
        created_at=tpl.created_at,
    )


# ─── CRUD ─────────────────────────────────────────────────────────────────────

@router.post("", response_model=ContractTemplateResponse, status_code=201)
async def create_template(
    org_id: UUID,
    body: ContractTemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Create a new contract template for the organization. Requires org admin/owner."""
    from app import ContractTemplate

    await _get_org_or_404(org_id, db)
    await _require_org_admin(org_id, current_user.id, db)

    tpl = ContractTemplate(
        organization_id=org_id,
        name=body.name,
        description=body.description,
        category=body.category,
        rule_ids=[str(rid) for rid in body.rule_ids],
        custom_instructions=body.custom_instructions,
        created_by=current_user.id,
    )
    db.add(tpl)
    await db.flush()

    return _serialize_template(tpl)


@router.get("", response_model=ContractTemplateListResponse)
async def list_templates(
    org_id: UUID,
    category: Optional[str] = Query(None),
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List contract templates for an organization. Requires membership."""
    from app import ContractTemplate

    await _get_org_or_404(org_id, db)
    await _require_org_member(org_id, current_user.id, db)

    query = select(ContractTemplate).where(ContractTemplate.organization_id == org_id)

    if active_only:
        query = query.where(ContractTemplate.is_active == True)
    if category:
        query = query.where(ContractTemplate.category == category)

    query = query.order_by(ContractTemplate.name)

    result = await db.execute(query)
    templates = result.scalars().all()

    return ContractTemplateListResponse(
        templates=[_serialize_template(t) for t in templates],
        total=len(templates),
    )


@router.get("/{template_id}", response_model=ContractTemplateResponse)
async def get_template(
    org_id: UUID,
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get a specific contract template. Requires membership."""
    await _get_org_or_404(org_id, db)
    await _require_org_member(org_id, current_user.id, db)

    tpl = await _get_template_or_404(template_id, org_id, db)
    return _serialize_template(tpl)


@router.patch("/{template_id}", response_model=ContractTemplateResponse)
async def update_template(
    org_id: UUID,
    template_id: UUID,
    body: ContractTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Update a contract template. Requires org admin/owner."""
    await _get_org_or_404(org_id, db)
    await _require_org_admin(org_id, current_user.id, db)

    tpl = await _get_template_or_404(template_id, org_id, db)

    if body.name is not None:
        tpl.name = body.name
    if body.description is not None:
        tpl.description = body.description
    if body.category is not None:
        tpl.category = body.category
    if body.rule_ids is not None:
        tpl.rule_ids = [str(rid) for rid in body.rule_ids]
    if body.custom_instructions is not None:
        tpl.custom_instructions = body.custom_instructions
    if body.is_active is not None:
        tpl.is_active = body.is_active

    await db.flush()
    return _serialize_template(tpl)


@router.delete("/{template_id}", status_code=204)
async def delete_template(
    org_id: UUID,
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Delete a contract template. Requires org admin/owner."""
    await _get_org_or_404(org_id, db)
    await _require_org_admin(org_id, current_user.id, db)

    tpl = await _get_template_or_404(template_id, org_id, db)
    await db.delete(tpl)
    await db.flush()
