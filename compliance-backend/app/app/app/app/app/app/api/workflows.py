"""
Approval Workflows API — document review and approval flow.

FASE 3: Multi-step approval with status transitions:
  pending_review → in_review → approved / rejected / revision_requested
"""
from uuid import UUID
from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.core.security import get_current_user
from app.schemas import (
    WorkflowCreate,
    WorkflowTransition,
    WorkflowResponse,
    WorkflowListResponse,
    WorkflowCommentSchema,
)

router = APIRouter(prefix="/workflows", tags=["Approval Workflows"])

# Valid transitions: current_status → {action: new_status}
_TRANSITIONS = {
    "pending_review": {"advance": "in_review"},
    "in_review": {
        "approve": "approved",
        "reject": "rejected",
        "request_revision": "revision_requested",
    },
    "revision_requested": {"advance": "in_review"},
}

_TERMINAL = {"approved", "rejected"}


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _get_workflow_or_404(wf_id: UUID, db: AsyncSession):
    from app import ApprovalWorkflow
    result = await db.execute(select(ApprovalWorkflow).where(ApprovalWorkflow.id == wf_id))
    wf = result.scalar_one_or_none()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow não encontrado")
    return wf


def _serialize_workflow(wf) -> WorkflowResponse:
    comments = wf.comments or []
    parsed_comments = []
    for c in comments:
        if isinstance(c, dict):
            parsed_comments.append(WorkflowCommentSchema(**c))

    return WorkflowResponse(
        id=wf.id,
        document_id=wf.document_id,
        organization_id=wf.organization_id,
        status=wf.status,
        current_step=wf.current_step,
        total_steps=wf.total_steps,
        assigned_to=wf.assigned_to,
        created_by=wf.created_by,
        comments=parsed_comments,
        created_at=wf.created_at,
        updated_at=wf.updated_at,
        completed_at=wf.completed_at,
    )


# ─── CRUD ─────────────────────────────────────────────────────────────────────

@router.post("", response_model=WorkflowResponse, status_code=201)
async def create_workflow(
    body: WorkflowCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Create an approval workflow for a document."""
    from app import Document, ApprovalWorkflow

    # Verify document exists and belongs to user (or user is admin)
    result = await db.execute(select(Document).where(Document.id == body.document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    if doc.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Sem permissão para este documento")

    # Check no active workflow exists for this document
    existing = await db.execute(
        select(ApprovalWorkflow).where(
            ApprovalWorkflow.document_id == body.document_id,
            ApprovalWorkflow.status.notin_(list(_TERMINAL)),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Já existe um workflow ativo para este documento")

    wf = ApprovalWorkflow(
        document_id=body.document_id,
        organization_id=doc.organization_id,
        total_steps=body.total_steps,
        assigned_to=body.assigned_to,
        created_by=current_user.id,
    )
    db.add(wf)
    await db.flush()

    return _serialize_workflow(wf)


@router.get("", response_model=WorkflowListResponse)
async def list_workflows(
    status: Optional[str] = Query(None),
    document_id: Optional[UUID] = Query(None),
    assigned_to_me: bool = Query(False),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List workflows visible to the current user."""
    from app import ApprovalWorkflow

    query = select(ApprovalWorkflow)

    # Non-admins see only their created or assigned workflows
    if current_user.role != "admin":
        query = query.where(
            (ApprovalWorkflow.created_by == current_user.id) |
            (ApprovalWorkflow.assigned_to == current_user.id)
        )

    if status:
        query = query.where(ApprovalWorkflow.status == status)
    if document_id:
        query = query.where(ApprovalWorkflow.document_id == document_id)
    if assigned_to_me:
        query = query.where(ApprovalWorkflow.assigned_to == current_user.id)

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()

    # Paginate
    query = query.order_by(ApprovalWorkflow.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    workflows = result.scalars().all()

    return WorkflowListResponse(
        workflows=[_serialize_workflow(wf) for wf in workflows],
        total=total,
    )


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(
    workflow_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get workflow details."""
    wf = await _get_workflow_or_404(workflow_id, db)

    # Permission: creator, assignee, or admin
    if (wf.created_by != current_user.id
            and wf.assigned_to != current_user.id
            and current_user.role != "admin"):
        raise HTTPException(status_code=403, detail="Sem permissão para visualizar este workflow")

    return _serialize_workflow(wf)


@router.post("/{workflow_id}/transition", response_model=WorkflowResponse)
async def transition_workflow(
    workflow_id: UUID,
    body: WorkflowTransition,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Transition a workflow to the next state."""
    wf = await _get_workflow_or_404(workflow_id, db)

    # Permission: assignee or admin can transition
    if wf.assigned_to and wf.assigned_to != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Apenas o revisor atribuído pode transicionar este workflow")

    # Creator can also advance from pending_review
    if not wf.assigned_to and wf.created_by != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Sem permissão para transicionar este workflow")

    # Check workflow is not in terminal state
    if wf.status in _TERMINAL:
        raise HTTPException(status_code=400, detail=f"Workflow já finalizado com status '{wf.status}'")

    # Validate transition
    allowed = _TRANSITIONS.get(wf.status, {})
    new_status = allowed.get(body.action)
    if not new_status:
        raise HTTPException(
            status_code=400,
            detail=f"Ação '{body.action}' não permitida no status '{wf.status}'. "
                   f"Ações válidas: {list(allowed.keys())}",
        )

    # Apply transition
    wf.status = new_status
    wf.updated_at = datetime.now(timezone.utc)

    if body.assigned_to:
        wf.assigned_to = body.assigned_to

    # Handle multi-step: advance increments step
    if body.action == "advance" and wf.current_step < wf.total_steps:
        wf.current_step += 1

    # Terminal states
    if new_status in _TERMINAL:
        wf.completed_at = datetime.now(timezone.utc)

    # Add comment
    comment_entry = {
        "user_id": str(current_user.id),
        "user_name": current_user.full_name or current_user.email,
        "action": body.action,
        "comment": body.comment,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    comments = list(wf.comments or [])
    comments.append(comment_entry)
    wf.comments = comments

    await db.flush()

    return _serialize_workflow(wf)
