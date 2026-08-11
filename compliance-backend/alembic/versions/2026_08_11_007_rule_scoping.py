"""rule scoping: regras pessoais, de equipe e overrides de globais

Revision ID: 007
Revises: 006
Create Date: 2026-08-11
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "rules",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_rules_user_id", "rules", "users", ["user_id"], ["id"], ondelete="CASCADE"
    )
    op.create_index("ix_rules_user_id", "rules", ["user_id"])
    op.create_index("ix_rules_organization_id", "rules", ["organization_id"])

    op.create_table(
        "rule_overrides",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["rule_id"], ["rules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rule_id", "user_id", "organization_id", name="uq_rule_override_scope"),
    )
    op.create_index("ix_rule_overrides_user_id", "rule_overrides", ["user_id"])
    op.create_index("ix_rule_overrides_organization_id", "rule_overrides", ["organization_id"])


def downgrade() -> None:
    op.drop_index("ix_rule_overrides_organization_id", table_name="rule_overrides")
    op.drop_index("ix_rule_overrides_user_id", table_name="rule_overrides")
    op.drop_table("rule_overrides")
    op.drop_index("ix_rules_organization_id", table_name="rules")
    op.drop_index("ix_rules_user_id", table_name="rules")
    op.drop_constraint("fk_rules_user_id", "rules", type_="foreignkey")
    op.drop_column("rules", "user_id")
