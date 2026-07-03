"""holding consolidation summary (B3)

Revision ID: c3f5a2b8d140
Revises: b1a7c3d9e021
Create Date: 2026-07-02 16:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c3f5a2b8d140'
down_revision: Union[str, Sequence[str], None] = 'b1a7c3d9e021'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Сводка последней консолидации на холдинге (nullable)."""
    with op.batch_alter_table('holdings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_consolidation_npv', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('last_consolidation_rate', sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column('last_consolidation_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('holdings', schema=None) as batch_op:
        batch_op.drop_column('last_consolidation_at')
        batch_op.drop_column('last_consolidation_rate')
        batch_op.drop_column('last_consolidation_npv')
