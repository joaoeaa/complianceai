"""
Organizations API — CRUD + member management.

FASE 2: Multi-tenancy support. Each organization can have members with
roles (owner, admin, member) and scoped rules/templates.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.core.security import get_current_user
from app.schemas import (
    OrganizationCreate,
    OrganizationUpdate,
    OrganizationResponse,
    OrganizationDetailResponse,
    OrgMemberResponse,
    AddMemberRequest,
    UpdateMemberRoleRequest,
)

router = APIRouter(prefix="/organizations", tags=["Organizations"])


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _get_org_or_404(org_id: UUID, db: AsyncSession):
    from app import Organization
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organização não encontrada")
    return org


async def _get_membership(org_id: UUID, user_id: UUID, db: AsyncSession):
    from app import OrgMember
    result = await db.execute(
        select(OrgMember).where(OrgMember.organization_id == org_id, OrgMember.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def _require_org_admin(org_id: UUID, user_id: UUID, db: AsyncSession):
    """Raise 403 if user is not owner or admin of the org."""
    member = await _get_membership(org_id, user_id, db)
    if not member or member.role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores da organização")
    return member


async def _require_org_member(org_id: UUID, user_id: UUID, db: AsyncSession):
    """Raise 403 if user is not a member of the org."""
    member = await _get_membership(org_id, user_id, db)
    if not member:
        raise HTTPException(status_code=403, detail="Você não é membro desta organização")
    return member


# ─── CRUD ─────────────────────────────────────────────────────────────────────

@router.post("", response_model=OrganizationResponse, status_code=201)
async def create_organization(
    body: OrganizationCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Create a new organization. The creator becomes the owner."""
    from app import Organization, OrgMember

    # Check slug uniqueness
    existing = await db.execute(select(Organization).where(Organization.slug == body.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Slug já está em uso")

    org = Organization(name=body.name, slug=body.slug, cnpj=body.cnpj)
    db.add(org)
    await db.flush()

    # Creator becomes owner
    membership = OrgMember(organization_id=org.id, user_id=current_user.id, role="owner")
    db.add(membership)

    # Link user to org
    current_user.organization_id = org.id

    await db.flush()

    return OrganizationResponse(
        id=org.id, name=org.name, slug=org.slug, cnpj=org.cnpj,
        is_active=org.is_active, created_at=org.created_at, member_count=1,
    )


@router.get("", response_model=list[OrganizationResponse])
async def list_organizations(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List organizations the current user belongs to."""
    from app import Organization, OrgMember

    # O total de membros vem de uma subquery propria: contar sobre o JOIN filtrado
    # por user_id devolveria sempre 1, porque so a linha do proprio usuario sobra.
    member_count = (
        select(func.count(OrgMember.id))
        .where(OrgMember.organization_id == Organization.id)
        .correlate(Organization)
        .scalar_subquery()
    )

    result = await db.execute(
        select(Organization, member_count.label("member_count"), OrgMember.role)
        .join(OrgMember, Organization.id == OrgMember.organization_id)
        .where(OrgMember.user_id == current_user.id)
    )
    rows = result.all()

    return [
        OrganizationResponse(
            id=org.id, name=org.name, slug=org.slug, cnpj=org.cnpj,
            is_active=org.is_active, created_at=org.created_at, member_count=count,
            my_role=role,
        )
        for org, count, role in rows
    ]


@router.get("/{org_id}", response_model=OrganizationDetailResponse)
async def get_organization(
    org_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get organization details with members. Requires membership."""
    from app import OrgMember, User

    org = await _get_org_or_404(org_id, db)
    await _require_org_member(org_id, current_user.id, db)

    # Fetch members with user info
    members_result = await db.execute(
        select(OrgMember, User.email, User.full_name)
        .join(User, OrgMember.user_id == User.id)
        .where(OrgMember.organization_id == org_id)
    )
    members = [
        OrgMemberResponse(
            id=m.id, user_id=m.user_id, role=m.role, joined_at=m.joined_at,
            user_email=email, user_name=name,
        )
        for m, email, name in members_result.all()
    ]

    return OrganizationDetailResponse(
        id=org.id, name=org.name, slug=org.slug, cnpj=org.cnpj,
        is_active=org.is_active, created_at=org.created_at,
        member_count=len(members), members=members,
    )


@router.patch("/{org_id}", response_model=OrganizationResponse)
async def update_organization(
    org_id: UUID,
    body: OrganizationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Update organization details. Requires org admin/owner."""
    from app import OrgMember

    org = await _get_org_or_404(org_id, db)
    await _require_org_admin(org_id, current_user.id, db)

    if body.name is not None:
        org.name = body.name
    if body.cnpj is not None:
        org.cnpj = body.cnpj
    if body.is_active is not None:
        org.is_active = body.is_active

    await db.flush()

    count_result = await db.execute(
        select(func.count(OrgMember.id)).where(OrgMember.organization_id == org_id)
    )
    member_count = count_result.scalar()

    return OrganizationResponse(
        id=org.id, name=org.name, slug=org.slug, cnpj=org.cnpj,
        is_active=org.is_active, created_at=org.created_at, member_count=member_count,
    )


@router.delete("/{org_id}", status_code=204)
async def delete_organization(
    org_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Delete organization. Only the owner can delete."""
    org = await _get_org_or_404(org_id, db)
    member = await _get_membership(org_id, current_user.id, db)
    if not member or member.role != "owner":
        raise HTTPException(status_code=403, detail="Apenas o proprietário pode excluir a organização")

    await db.delete(org)
    await db.flush()


# ─── Member Management ───────────────────────────────────────────────────────

@router.post("/{org_id}/members", response_model=OrgMemberResponse, status_code=201)
async def add_member(
    org_id: UUID,
    body: AddMemberRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Add a user to the organization by email. Requires org admin/owner."""
    from app import User, OrgMember

    await _get_org_or_404(org_id, db)
    await _require_org_admin(org_id, current_user.id, db)

    # Find user by email
    user_result = await db.execute(select(User).where(User.email == body.email))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado com esse email")

    # Check if already member
    existing = await _get_membership(org_id, user.id, db)
    if existing:
        raise HTTPException(status_code=409, detail="Usuário já é membro desta organização")

    membership = OrgMember(organization_id=org_id, user_id=user.id, role=body.role.value)
    db.add(membership)

    # Link user to org if not already linked
    if not user.organization_id:
        user.organization_id = org_id

    await db.flush()

    return OrgMemberResponse(
        id=membership.id, user_id=user.id, role=membership.role,
        joined_at=membership.joined_at, user_email=user.email, user_name=user.full_name,
    )


@router.patch("/{org_id}/members/{user_id}", response_model=OrgMemberResponse)
async def update_member_role(
    org_id: UUID,
    user_id: UUID,
    body: UpdateMemberRoleRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Update a member's role. Requires org admin/owner."""
    from app import User

    await _get_org_or_404(org_id, db)
    await _require_org_admin(org_id, current_user.id, db)

    member = await _get_membership(org_id, user_id, db)
    if not member:
        raise HTTPException(status_code=404, detail="Membro não encontrado")

    # Cannot demote the last owner
    if member.role == "owner" and body.role.value != "owner":
        from app import OrgMember
        owners_result = await db.execute(
            select(func.count(OrgMember.id)).where(
                OrgMember.organization_id == org_id, OrgMember.role == "owner"
            )
        )
        if owners_result.scalar() <= 1:
            raise HTTPException(status_code=400, detail="Não é possível remover o último proprietário")

    member.role = body.role.value
    await db.flush()

    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one()

    return OrgMemberResponse(
        id=member.id, user_id=user_id, role=member.role,
        joined_at=member.joined_at, user_email=user.email, user_name=user.full_name,
    )


@router.delete("/{org_id}/members/{user_id}", status_code=204)
async def remove_member(
    org_id: UUID,
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Remove a member from the organization. Requires org admin/owner."""
    await _get_org_or_404(org_id, db)
    await _require_org_admin(org_id, current_user.id, db)

    member = await _get_membership(org_id, user_id, db)
    if not member:
        raise HTTPException(status_code=404, detail="Membro não encontrado")

    # Cannot remove the last owner
    if member.role == "owner":
        from app import OrgMember
        owners_result = await db.execute(
            select(func.count(OrgMember.id)).where(
                OrgMember.organization_id == org_id, OrgMember.role == "owner"
            )
        )
        if owners_result.scalar() <= 1:
            raise HTTPException(status_code=400, detail="Não é possível remover o último proprietário")

    await db.delete(member)
    await db.flush()
