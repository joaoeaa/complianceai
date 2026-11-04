"""etapa e progresso da analise no proprio documento

O progresso morava no result backend do Celery, no Redis. Com a analise rodando
dentro da api, ele passa a ficar no banco, que e a unica coisa compartilhada.

Revision ID: 013
Revises: 012
Create Date: 2026-11-04
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("analysis_stage", sa.String(50), nullable=True))
    op.add_column("documents", sa.Column("analysis_progress", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "analysis_progress")
    op.drop_column("documents", "analysis_stage")
