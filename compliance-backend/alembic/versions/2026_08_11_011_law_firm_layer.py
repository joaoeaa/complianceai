"""camada de escritorio: clientes, designacoes e log de acesso

Revision ID: 011
Revises: 010
Create Date: 2026-08-11
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "clients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("document", sa.String(length=18), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("retention_months", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("organization_id", "name", name="uq_client_org_name"),
    )
    op.create_index("ix_clients_organization_id", "clients", ["organization_id"])
    op.create_index("ix_clients_user_id", "clients", ["user_id"])

    op.create_table(
        "client_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("client_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("client_id", "user_id", name="uq_client_assignment"),
    )
    op.create_index("ix_client_assignments_client_id", "client_assignments", ["client_id"])
    op.create_index("ix_client_assignments_user_id", "client_assignments", ["user_id"])

    op.create_table(
        "access_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True),
        # SET NULL para o registro sobreviver ao expurgo do documento: saber que
        # alguem leu um documento hoje apagado e o que a auditoria quer.
        sa.Column("document_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("clients.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "action",
            sa.Enum("view", "download", "export", "analyze", "delete",
                    "assign", "unassign", "denied", name="access_action"),
            nullable=False,
        ),
        sa.Column("detail", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_access_logs_created_at", "access_logs", ["created_at"])
    op.create_index("ix_access_logs_organization_id", "access_logs", ["organization_id"])
    op.create_index("ix_access_logs_document_id", "access_logs", ["document_id"])

    op.add_column(
        "documents",
        sa.Column("client_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("clients.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_documents_client_id", "documents", ["client_id"])


def downgrade() -> None:
    op.drop_index("ix_documents_client_id", table_name="documents")
    op.drop_column("documents", "client_id")

    op.drop_index("ix_access_logs_document_id", table_name="access_logs")
    op.drop_index("ix_access_logs_organization_id", table_name="access_logs")
    op.drop_index("ix_access_logs_created_at", table_name="access_logs")
    op.drop_table("access_logs")
    sa.Enum(name="access_action").drop(op.get_bind(), checkfirst=True)

    op.drop_index("ix_client_assignments_user_id", table_name="client_assignments")
    op.drop_index("ix_client_assignments_client_id", table_name="client_assignments")
    op.drop_table("client_assignments")

    op.drop_index("ix_clients_user_id", table_name="clients")
    op.drop_index("ix_clients_organization_id", table_name="clients")
    op.drop_table("clients")
