"""
Webhook Configs API — CRUD for outbound webhook notification endpoints.

FASE 3: Allows organizations to register URLs that receive POST
notifications when specific events occur (e.g., document.analyzed,
workflow.approved).
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import get_current_user, get_current_admin
from app.schemas import (
    WebhookConfigCreate,
    WebhookConfigUpdate,
    WebhookConfigResponse,
    WebhookConfigListResponse,
)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

VALID_EVENTS = {
    "document.uploaded",
    "document.analyzed",
    "workflow.created",
    "workflow.approved",
    "workflow.rejected",
}


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _get_webhook_or_404(wh_id: UUID, db: AsyncSession):
    from app import WebhookConfig
    result = await db.execute(select(WebhookConfig).where(WebhookConfig.id == wh_id))
    wh = result.scalar_one_or_none()
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook não encontrado")
    return wh


def _serialize(wh) -> WebhookConfigResponse:
    return WebhookConfigResponse(
        id=wh.id,
        organization_id=wh.organization_id,
        name=wh.name,
        url=wh.url,
        events=wh.events or [],
        is_active=wh.is_active,
        created_by=wh.created_by,
        created_at=wh.created_at,
    )


# ─── CRUD ─────────────────────────────────────────────────────────────────────

@router.post("", response_model=WebhookConfigResponse, status_code=201)
async def create_webhook(
    body: WebhookConfigCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_admin),
):
    """Create a webhook config. Admin only."""
    from app import WebhookConfig

    # Validate events
    invalid = set(body.events) - VALID_EVENTS
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Eventos inválidos: {invalid}. Válidos: {sorted(VALID_EVENTS)}",
        )

    wh = WebhookConfig(
        organization_id=body.organization_id,
        name=body.name,
        url=body.url,
        secret=body.secret,
        events=body.events,
        created_by=current_user.id,
    )
    db.add(wh)
    await db.flush()

    return _serialize(wh)


@router.get("", response_model=WebhookConfigListResponse)
async def list_webhooks(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_admin),
):
    """List all webhook configs. Admin only."""
    from app import WebhookConfig

    result = await db.execute(select(WebhookConfig).order_by(WebhookConfig.name))
    webhooks = result.scalars().all()

    return WebhookConfigListResponse(
        webhooks=[_serialize(wh) for wh in webhooks],
        total=len(webhooks),
    )


@router.get("/{webhook_id}", response_model=WebhookConfigResponse)
async def get_webhook(
    webhook_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_admin),
):
    """Get webhook details. Admin only."""
    wh = await _get_webhook_or_404(webhook_id, db)
    return _serialize(wh)


@router.patch("/{webhook_id}", response_model=WebhookConfigResponse)
async def update_webhook(
    webhook_id: UUID,
    body: WebhookConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_admin),
):
    """Update a webhook config. Admin only."""
    wh = await _get_webhook_or_404(webhook_id, db)

    if body.name is not None:
        wh.name = body.name
    if body.url is not None:
        wh.url = body.url
    if body.secret is not None:
        wh.secret = body.secret
    if body.events is not None:
        invalid = set(body.events) - VALID_EVENTS
        if invalid:
            raise HTTPException(
                status_code=400,
                detail=f"Eventos inválidos: {invalid}. Válidos: {sorted(VALID_EVENTS)}",
            )
        wh.events = body.events
    if body.is_active is not None:
        wh.is_active = body.is_active

    await db.flush()
    return _serialize(wh)


@router.delete("/{webhook_id}", status_code=204)
async def delete_webhook(
    webhook_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_admin),
):
    """Delete a webhook config. Admin only."""
    wh = await _get_webhook_or_404(webhook_id, db)
    await db.delete(wh)
    await db.flush()
