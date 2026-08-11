"""add organizations and contract templates

Revision ID: 003
Revises: 002
Create Date: 2026-02-24

FASE 2 — Contexto Organizacional:
- organizations: multi-tenancy support
- org_members: membership with roles (owner, admin, member)
- contract_templates: reusable contract type definitions with custom rules
- Adds organization_id FK on users, documents, and rules tables
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Enum types ──
    op.execute("CREATE TYPE org_role AS ENUM ('owner', 'admin', 'member')")

    # ── Organizations ──
    op.create_table(
        "organizations",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("cnpj", sa.String(18), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"], unique=True)

    # ── Org Members (join table with role) ──
    op.create_table(
        "org_members",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("role", postgresql.ENUM("owner", "admin", "member", name="org_role", create_type=False), nullable=False, server_default=sa.text("'member'")),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_org_member"),
    )

    # ── Contract Templates ──
    op.create_table(
        "contract_templates",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(100), nullable=False, server_default=sa.text("'geral'")),
        sa.Column("rule_ids", postgresql.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("custom_instructions", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_contract_templates_org", "contract_templates", ["organization_id"])
    op.create_index("ix_contract_templates_category", "contract_templates", ["category"])

    # ── Add organization_id to existing tables ──
    # Users can optionally belong to an organization
    op.add_column("users", sa.Column("organization_id", sa.UUID(), nullable=True))
    op.create_foreign_key("fk_users_organization", "users", "organizations", ["organization_id"], ["id"], ondelete="SET NULL")

    # Documents belong to an organization (nullable for backward compatibility)
    op.add_column("documents", sa.Column("organization_id", sa.UUID(), nullable=True))
    op.create_foreign_key("fk_documents_organization", "documents", "organizations", ["organization_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_documents_organization", "documents", ["organization_id"])

    # Documents can reference a template
    op.add_column("documents", sa.Column("template_id", sa.UUID(), nullable=True))
    op.create_foreign_key("fk_documents_template", "documents", "contract_templates", ["template_id"], ["id"], ondelete="SET NULL")

    # Rules can be scoped to an organization (null = global)
    op.add_column("rules", sa.Column("organization_id", sa.UUID(), nullable=True))
    op.create_foreign_key("fk_rules_organization", "rules", "organizations", ["organization_id"], ["id"], ondelete="CASCADE")
    op.create_index("ix_rules_organization", "rules", ["organization_id"])


def downgrade() -> None:
    # ── Remove FKs and columns from existing tables ──
    op.drop_constraint("fk_rules_organization", "rules", type_="foreignkey")
    op.drop_index("ix_rules_organization", table_name="rules")
    op.drop_column("rules", "organization_id")

    op.drop_constraint("fk_documents_template", "documents", type_="foreignkey")
    op.drop_column("documents", "template_id")
    op.drop_constraint("fk_documents_organization", "documents", type_="foreignkey")
    op.drop_index("ix_documents_organization", table_name="documents")
    op.drop_column("documents", "organization_id")

    op.drop_constraint("fk_users_organization", "users", type_="foreignkey")
    op.drop_column("users", "organization_id")

    # ── Drop new tables ──
    op.drop_table("contract_templates")
    op.drop_table("org_members")
    op.drop_table("organizations")

    op.execute("DROP TYPE IF EXISTS org_role")
