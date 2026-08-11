"""add approval workflows and webhook configs

Revision ID: 004
Revises: 003
Create Date: 2026-02-24

FASE 3 — Workflow e Integrações:
- approval_workflows: multi-step document approval flow
- webhook_configs: outbound webhook notifications for events
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Enum types ──
    op.execute(
        "CREATE TYPE workflow_status AS ENUM "
        "('pending_review', 'in_review', 'approved', 'rejected', 'revision_requested')"
    )

    # ── Approval Workflows ──
    op.create_table(
        "approval_workflows",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=True),
        sa.Column("status", postgresql.ENUM(
            "pending_review", "in_review", "approved", "rejected", "revision_requested",
            name="workflow_status", create_type=False,
        ), nullable=False, server_default=sa.text("'pending_review'")),
        sa.Column("current_step", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("total_steps", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("assigned_to", sa.UUID(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("comments", postgresql.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assigned_to"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workflows_document", "approval_workflows", ["document_id"])
    op.create_index("ix_workflows_status", "approval_workflows", ["status"])
    op.create_index("ix_workflows_assigned", "approval_workflows", ["assigned_to"])

    # ── Webhook Configs ──
    op.create_table(
        "webhook_configs",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("url", sa.String(2000), nullable=False),
        sa.Column("secret", sa.String(255), nullable=True),
        sa.Column("events", postgresql.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_webhook_configs_org", "webhook_configs", ["organization_id"])


def downgrade() -> None:
    op.drop_table("webhook_configs")
    op.drop_table("approval_workflows")
    op.execute("DROP TYPE IF EXISTS workflow_status")
