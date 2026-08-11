"""Escopo de trabalho: pessoal ou de uma equipe.

O usuário escolhe em qual escopo está trabalhando, e essa escolha vale para tudo —
regras, documentos, histórico e dashboard. Aqui ficam as checagens de acesso que
as três camadas de API compartilham, para a autorização não divergir entre elas.

Convenção do escopo:
    organization_id = None  -> pessoal; documentos do próprio usuário
    organization_id = <id>  -> equipe; exige que o usuário seja membro
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, OrgMember, User

MANAGER_ROLES = ("owner", "admin")


async def require_org_membership(
    org_id: UUID, user: User, db: AsyncSession, *, must_manage: bool = False
) -> OrgMember:
    """Garante que o usuário pertence à organização e, se pedido, que a administra.

    Responde 404 para quem não é membro: confirmar a existência de uma organização
    a quem não participa dela já é informação demais.
    """
    result = await db.execute(
        select(OrgMember).where(
            OrgMember.organization_id == org_id, OrgMember.user_id == user.id
        )
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=404, detail="Organização não encontrada")
    if must_manage and membership.role not in MANAGER_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Apenas responsáveis pela organização podem fazer esta alteração",
        )
    return membership


def document_scope_filter(user: User, organization_id: Optional[UUID]):
    """Condição que seleciona os documentos visíveis no escopo escolhido.

    Chame `require_org_membership` antes quando `organization_id` vier preenchido —
    esta função assume que o acesso já foi autorizado.
    """
    if organization_id is not None:
        return Document.organization_id == organization_id
    return (Document.user_id == user.id) & Document.organization_id.is_(None)


async def get_document_for_read(
    document_id: UUID, user: User, db: AsyncSession
) -> Document:
    """Busca um documento que o usuário tem direito de ler.

    Documento pessoal: só o dono. Documento de equipe: qualquer membro — é o que
    permite revisar o contrato enviado por um colega.
    """
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    if doc.organization_id is not None:
        await require_org_membership(doc.organization_id, user, db)
        return doc

    if doc.user_id != user.id:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    return doc


async def get_document_for_delete(
    document_id: UUID, user: User, db: AsyncSession
) -> Document:
    """Busca um documento que o usuário tem direito de excluir.

    Mais restrito que a leitura: num documento de equipe, apagam quem enviou e os
    responsáveis pela organização.
    """
    doc = await get_document_for_read(document_id, user, db)

    if doc.organization_id is None or doc.user_id == user.id:
        return doc

    membership = await require_org_membership(doc.organization_id, user, db)
    if membership.role not in MANAGER_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Apenas quem enviou o documento ou os responsáveis pela equipe podem excluí-lo",
        )
    return doc
