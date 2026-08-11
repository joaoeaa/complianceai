"""categoria (area do direito) nas regras

Revision ID: 010
Revises: 009
Create Date: 2026-08-11
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "rules",
        sa.Column("category", sa.String(length=40), nullable=False, server_default="geral"),
    )
    op.create_index("ix_rules_category", "rules", ["category"])


def downgrade() -> None:
    op.drop_index("ix_rules_category", table_name="rules")
    op.drop_column("rules", "category")
