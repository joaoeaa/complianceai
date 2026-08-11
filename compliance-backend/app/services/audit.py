"""Registro de acesso.

Num escritório o dano de sigilo está na leitura, não na alteração. Um log que só
registra o que mudou não responde à pergunta que a auditoria faz, que é quem viu
o quê. Por isso a leitura de um relatório entra aqui, junto do download, da
exclusão e das designações.

O registro guarda UUIDs, nunca nome ou email, seguindo o mesmo critério dos logs
da aplicação. O `detail` guarda o nome do arquivo no momento do acesso, para a
linha continuar legível depois que o documento for apagado.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AccessLog, Document, User


async def record_access(
    db: AsyncSession,
    *,
    user: Optional[User],
    action: str,
    document: Optional[Document] = None,
    client_id: Optional[UUID] = None,
    organization_id: Optional[UUID] = None,
    detail: Optional[str] = None,
) -> AccessLog:
    """Grava uma linha no log de acesso.

    Não faz commit: a linha entra na mesma transação da ação que a originou, para
    não existir registro de um acesso que acabou revertido, nem acesso sem
    registro.
    """
    entrada = AccessLog(
        user_id=user.id if user else None,
        organization_id=organization_id
        or (document.organization_id if document is not None else None),
        document_id=document.id if document is not None else None,
        client_id=client_id or (document.client_id if document is not None else None),
        action=action,
        detail=detail or (document.filename if document is not None else None),
    )
    db.add(entrada)
    return entrada
