"""project last-calc summary (B1)

Revision ID: b1a7c3d9e021
Revises: f415e1d417d3
Create Date: 2026-07-02 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1a7c3d9e021'
down_revision: Union[str, Sequence[str], None] = 'f415e1d417d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Сводка последнего расчёта на проекте (nullable — расчёта могло не быть)."""
    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_npv', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('last_irr', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('last_pb_months', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('last_engine_version', sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column('last_calculated_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.drop_column('last_calculated_at')
        batch_op.drop_column('last_engine_version')
        batch_op.drop_column('last_pb_months')
        batch_op.drop_column('last_irr')
        batch_op.drop_column('last_npv')
