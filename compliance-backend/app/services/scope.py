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
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Client, ClientAssignment, Document, OrgMember, User

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


async def accessible_client_ids(
    user: User, organization_id: Optional[UUID], db: AsyncSession
) -> Optional[set[UUID]]:
    """Clientes que este usuário enxerga na equipe. `None` significa "todos".

    Sócio, aqui representado por owner e admin, enxerga a carteira inteira. Os
    demais enxergam apenas os clientes a que foram designados, que é o sigilo
    profissional posto em código: não basta pertencer ao escritório para ler o
    caso de outro advogado.
    """
    if organization_id is None:
        return None

    membership = await require_org_membership(organization_id, user, db)
    if membership.role in MANAGER_ROLES:
        return None

    result = await db.execute(
        select(ClientAssignment.client_id)
        .join(Client, Client.id == ClientAssignment.client_id)
        .where(
            Client.organization_id == organization_id,
            ClientAssignment.user_id == user.id,
        )
    )
    return set(result.scalars().all())


async def document_scope_filter(
    user: User, organization_id: Optional[UUID], db: AsyncSession
):
    """Condição que seleciona os documentos visíveis no escopo escolhido.

    Documento sem cliente continua visível a todo membro da equipe. Só amarrar o
    documento a um cliente é que restringe, o que mantém quem ainda não organizou
    a carteira funcionando como antes em vez de perder acesso ao próprio acervo.
    """
    if organization_id is None:
        return (Document.user_id == user.id) & Document.organization_id.is_(None)

    base = Document.organization_id == organization_id
    permitidos = await accessible_client_ids(user, organization_id, db)
    if permitidos is None:
        return base

    return base & or_(
        Document.client_id.is_(None), Document.client_id.in_(permitidos)
    )


async def can_read_client(
    client_id: Optional[UUID],
    organization_id: Optional[UUID],
    user: User,
    db: AsyncSession,
) -> bool:
    """O usuário pode ver o material deste cliente?"""
    if client_id is None or organization_id is None:
        return True
    permitidos = await accessible_client_ids(user, organization_id, db)
    return permitidos is None or client_id in permitidos


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
        if not await can_read_client(doc.client_id, doc.organization_id, user, db):
            # 404, e não 403: para quem não foi designado, o documento de outro
            # cliente não deve nem existir.
            raise HTTPException(status_code=404, detail="Documento não encontrado")
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
