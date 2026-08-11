"""Camada de escritório: clientes, designações, retenção e log de acesso.

Um escritório não organiza o trabalho por arquivo, e sim por cliente. É o cliente
que define quem pode ler o material (sigilo profissional), por quanto tempo ele
fica guardado (política de retenção) e o que a auditoria precisa conseguir
reconstruir depois (log de acesso).

Convenção de escopo, a mesma das regras:
    organization_id preenchido -> cliente do escritório, com designações
    organization_id omitido    -> carteira pessoal de quem trabalha sozinho
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models import AccessLog, Client, ClientAssignment, Document, User
from app.schemas import (
    AccessLogResponse,
    AssignClientRequest,
    ClientAssigneeResponse,
    ClientCreate,
    ClientResponse,
    ClientUpdate,
    ExpiredDocumentResponse,
    PurgeRequest,
)
from app.services.audit import record_access
from app.services.scope import (
    MANAGER_ROLES,
    accessible_client_ids,
    require_org_membership,
)

router = APIRouter(prefix="/clients", tags=["Clients"])


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _dias_de_meses(meses: int) -> timedelta:
    """Aproximação de mês usada no vencimento da guarda.

    Prazo de guarda se conta em anos, e a diferença de um ou dois dias não muda a
    decisão de expurgar. Aproximar evita depender de aritmética de data do banco e
    mantém o cálculo idêntico em Postgres e SQLite.
    """
    return timedelta(days=meses * 30.44)


def _venceu_em(doc: Document, meses: int) -> datetime:
    base = doc.uploaded_at
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    return base + _dias_de_meses(meses)


async def _get_client_or_404(
    client_id: uuid.UUID, user: User, db: AsyncSession, *, must_manage: bool = False
) -> Client:
    """Busca um cliente que o usuário tem direito de ver.

    Responde 404, e não 403, a quem não foi designado: a existência de um cliente
    do escritório já é informação sujeita a sigilo.
    """
    cliente = (
        await db.execute(select(Client).where(Client.id == client_id))
    ).scalar_one_or_none()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    if cliente.organization_id is not None:
        membership = await require_org_membership(cliente.organization_id, user, db)
        if membership.role not in MANAGER_ROLES:
            if must_manage:
                raise HTTPException(
                    status_code=403,
                    detail="Apenas responsáveis pelo escritório podem fazer esta alteração",
                )
            permitidos = await accessible_client_ids(user, cliente.organization_id, db)
            if permitidos is not None and cliente.id not in permitidos:
                raise HTTPException(status_code=404, detail="Cliente não encontrado")
        return cliente

    if cliente.user_id != user.id:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return cliente


async def _resumo(clientes: List[Client], db: AsyncSession) -> List[ClientResponse]:
    """Monta a resposta com as contagens que a tela mostra."""
    if not clientes:
        return []

    ids = [c.id for c in clientes]

    docs_por_cliente = dict(
        (
            await db.execute(
                select(Document.client_id, func.count(Document.id))
                .where(Document.client_id.in_(ids))
                .group_by(Document.client_id)
            )
        ).all()
    )
    designados_por_cliente = dict(
        (
            await db.execute(
                select(ClientAssignment.client_id, func.count(ClientAssignment.id))
                .where(ClientAssignment.client_id.in_(ids))
                .group_by(ClientAssignment.client_id)
            )
        ).all()
    )

    # Vencimento calculado em Python: somar meses a uma data em SQL amarraria a
    # consulta ao Postgres, e já tivemos esse problema com to_char no dashboard.
    com_prazo = [c for c in clientes if c.retention_months]
    vencidos: dict[uuid.UUID, int] = {}
    if com_prazo:
        prazos = {c.id: c.retention_months for c in com_prazo}
        docs = (
            await db.execute(
                select(Document).where(Document.client_id.in_(list(prazos)))
            )
        ).scalars().all()
        agora = datetime.now(timezone.utc)
        for doc in docs:
            if _venceu_em(doc, prazos[doc.client_id]) <= agora:
                vencidos[doc.client_id] = vencidos.get(doc.client_id, 0) + 1

    return [
        ClientResponse(
            id=c.id,
            name=c.name,
            document=c.document,
            notes=c.notes,
            is_active=c.is_active,
            retention_months=c.retention_months,
            scope=c.scope,
            document_count=docs_por_cliente.get(c.id, 0),
            assignee_count=designados_por_cliente.get(c.id, 0),
            expired_count=vencidos.get(c.id, 0),
            created_at=c.created_at,
        )
        for c in clientes
    ]


# ─── Clientes ────────────────────────────────────────────────────────────────

@router.get("", response_model=List[ClientResponse])
async def list_clients(
    organization_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Clientes visíveis no escopo atual.

    Na equipe, quem não é responsável vê apenas os clientes a que foi designado.
    """
    if organization_id is None:
        consulta = select(Client).where(Client.user_id == current_user.id)
    else:
        consulta = select(Client).where(Client.organization_id == organization_id)
        permitidos = await accessible_client_ids(current_user, organization_id, db)
        if permitidos is not None:
            consulta = consulta.where(Client.id.in_(permitidos))

    clientes = (await db.execute(consulta.order_by(Client.name))).scalars().all()
    return await _resumo(list(clientes), db)


@router.post("", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
async def create_client(
    data: ClientCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if data.organization_id is not None:
        await require_org_membership(
            data.organization_id, current_user, db, must_manage=True
        )

    duplicado = (
        await db.execute(
            select(Client).where(
                Client.name == data.name,
                Client.organization_id == data.organization_id,
                Client.user_id == (None if data.organization_id else current_user.id),
            )
        )
    ).scalar_one_or_none()
    if duplicado:
        raise HTTPException(status_code=409, detail="Já existe um cliente com este nome")

    cliente = Client(
        name=data.name,
        document=data.document,
        notes=data.notes,
        retention_months=data.retention_months,
        organization_id=data.organization_id,
        user_id=None if data.organization_id else current_user.id,
    )
    db.add(cliente)
    await db.flush()

    # Quem cria um cliente do escritório já fica designado a ele. Sem isso, um
    # admin que depois perdesse o posto sairia da lista de quem enxerga o cliente.
    if data.organization_id is not None:
        db.add(ClientAssignment(client_id=cliente.id, user_id=current_user.id))
        await db.flush()

    await db.refresh(cliente)
    return (await _resumo([cliente], db))[0]


@router.patch("/{client_id}", response_model=ClientResponse)
async def update_client(
    client_id: uuid.UUID,
    data: ClientUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cliente = await _get_client_or_404(client_id, current_user, db, must_manage=True)

    for campo, valor in data.model_dump(exclude_unset=True).items():
        setattr(cliente, campo, valor)

    await db.flush()
    await db.refresh(cliente)
    return (await _resumo([cliente], db))[0]


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_client(
    client_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Exclui o cadastro do cliente. Os documentos ficam sem cliente, não somem.

    Apagar contrato junto com o cadastro seria destruir material de trabalho por
    causa de uma reorganização administrativa.
    """
    cliente = await _get_client_or_404(client_id, current_user, db, must_manage=True)
    await record_access(
        db,
        user=current_user,
        action="delete",
        client_id=cliente.id,
        organization_id=cliente.organization_id,
        detail="cliente: " + cliente.name,
    )
    await db.delete(cliente)
    return None


# ─── Designações ─────────────────────────────────────────────────────────────

@router.get("/{client_id}/assignees", response_model=List[ClientAssigneeResponse])
async def list_assignees(
    client_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cliente = await _get_client_or_404(client_id, current_user, db)
    linhas = (
        await db.execute(
            select(ClientAssignment, User)
            .join(User, User.id == ClientAssignment.user_id)
            .where(ClientAssignment.client_id == cliente.id)
        )
    ).all()
    return [
        ClientAssigneeResponse(
            user_id=u.id, email=u.email, full_name=u.full_name, assigned_at=a.assigned_at
        )
        for a, u in linhas
    ]


@router.post(
    "/{client_id}/assignees",
    response_model=ClientAssigneeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def assign_user(
    client_id: uuid.UUID,
    data: AssignClientRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Dá a um membro do escritório acesso ao material deste cliente."""
    cliente = await _get_client_or_404(client_id, current_user, db, must_manage=True)
    if cliente.organization_id is None:
        raise HTTPException(status_code=400, detail="Cliente pessoal não tem designações")

    alvo = (
        await db.execute(select(User).where(User.email == data.email))
    ).scalar_one_or_none()
    if not alvo:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    # Designar quem não pertence ao escritório abriria acesso por fora da equipe.
    await require_org_membership(cliente.organization_id, alvo, db)

    ja = (
        await db.execute(
            select(ClientAssignment).where(
                ClientAssignment.client_id == cliente.id,
                ClientAssignment.user_id == alvo.id,
            )
        )
    ).scalar_one_or_none()
    if ja:
        raise HTTPException(status_code=409, detail="Já designado a este cliente")

    designacao = ClientAssignment(client_id=cliente.id, user_id=alvo.id)
    db.add(designacao)
    await record_access(
        db,
        user=current_user,
        action="assign",
        client_id=cliente.id,
        organization_id=cliente.organization_id,
        detail="cliente: " + cliente.name,
    )
    await db.flush()
    return ClientAssigneeResponse(
        user_id=alvo.id,
        email=alvo.email,
        full_name=alvo.full_name,
        assigned_at=designacao.assigned_at,
    )


@router.delete("/{client_id}/assignees/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unassign_user(
    client_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cliente = await _get_client_or_404(client_id, current_user, db, must_manage=True)
    designacao = (
        await db.execute(
            select(ClientAssignment).where(
                ClientAssignment.client_id == cliente.id,
                ClientAssignment.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if not designacao:
        raise HTTPException(status_code=404, detail="Designação não encontrada")

    await db.delete(designacao)
    await record_access(
        db,
        user=current_user,
        action="unassign",
        client_id=cliente.id,
        organization_id=cliente.organization_id,
        detail="cliente: " + cliente.name,
    )
    return None


# ─── Retenção ────────────────────────────────────────────────────────────────

@router.get("/retencao/vencidos", response_model=List[ExpiredDocumentResponse])
async def list_expired(
    organization_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Documentos que passaram do prazo de guarda do cliente.

    Só lista. A exclusão é um segundo passo, deliberado: um contrato pode estar
    vencido para a política de guarda e ainda ser prova em processo em curso.
    """
    consulta = select(Client).where(Client.retention_months.is_not(None))
    if organization_id is None:
        consulta = consulta.where(Client.user_id == current_user.id)
    else:
        consulta = consulta.where(Client.organization_id == organization_id)
        permitidos = await accessible_client_ids(current_user, organization_id, db)
        if permitidos is not None:
            consulta = consulta.where(Client.id.in_(permitidos))

    clientes = (await db.execute(consulta)).scalars().all()
    if not clientes:
        return []

    por_id = {c.id: c for c in clientes}
    docs = (
        await db.execute(select(Document).where(Document.client_id.in_(list(por_id))))
    ).scalars().all()

    agora = datetime.now(timezone.utc)
    vencidos = []
    for doc in docs:
        cliente = por_id[doc.client_id]
        venceu = _venceu_em(doc, cliente.retention_months)
        if venceu > agora:
            continue
        vencidos.append(
            ExpiredDocumentResponse(
                document_id=doc.id,
                filename=doc.filename,
                client_id=cliente.id,
                client_name=cliente.name,
                uploaded_at=doc.uploaded_at,
                retention_months=cliente.retention_months,
                expired_on=venceu,
                days_overdue=(agora - venceu).days,
            )
        )

    vencidos.sort(key=lambda v: v.days_overdue, reverse=True)
    return vencidos


@router.post("/retencao/expurgar")
async def purge_documents(
    body: PurgeRequest,
    organization_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Exclui os documentos escolhidos na fila de retenção.

    Reconfere aqui que cada documento está de fato vencido: receber um id não pode
    virar um caminho paralelo para apagar documento dentro do prazo.
    """
    vencidos = {
        v.document_id
        for v in await list_expired(organization_id, db, current_user)
    }

    apagados = 0
    for doc_id in body.document_ids:
        if doc_id not in vencidos:
            continue
        doc = (
            await db.execute(select(Document).where(Document.id == doc_id))
        ).scalar_one_or_none()
        if not doc:
            continue
        await record_access(
            db,
            user=current_user,
            action="delete",
            document=doc,
            detail="expurgo por retenção: " + doc.filename,
        )
        await db.delete(doc)
        apagados += 1

    return {"deleted": apagados, "skipped": len(body.document_ids) - apagados}


# ─── Log de acesso ───────────────────────────────────────────────────────────

@router.get("/auditoria/acessos", response_model=List[AccessLogResponse])
async def list_access_logs(
    organization_id: Optional[uuid.UUID] = Query(None),
    client_id: Optional[uuid.UUID] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Histórico de acessos.

    No escritório, restrito a owner e admin: o log diz quem leu o quê, e abri-lo a
    todo mundo criaria uma segunda via de vazamento do que ele existe para
    proteger. No escopo pessoal, cada um vê o próprio.
    """
    consulta = (
        select(AccessLog, User.email, Client.name)
        .outerjoin(User, User.id == AccessLog.user_id)
        .outerjoin(Client, Client.id == AccessLog.client_id)
    )

    if organization_id is None:
        consulta = consulta.where(
            AccessLog.user_id == current_user.id,
            AccessLog.organization_id.is_(None),
        )
    else:
        await require_org_membership(organization_id, current_user, db, must_manage=True)
        consulta = consulta.where(AccessLog.organization_id == organization_id)

    if client_id is not None:
        consulta = consulta.where(AccessLog.client_id == client_id)

    linhas = (
        await db.execute(consulta.order_by(AccessLog.created_at.desc()).limit(limit))
    ).all()

    return [
        AccessLogResponse(
            id=log.id,
            action=log.action,
            detail=log.detail,
            created_at=log.created_at,
            user_id=log.user_id,
            user_email=email,
            document_id=log.document_id,
            client_id=log.client_id,
            client_name=nome_cliente,
        )
        for log, email, nome_cliente in linhas
    ]
