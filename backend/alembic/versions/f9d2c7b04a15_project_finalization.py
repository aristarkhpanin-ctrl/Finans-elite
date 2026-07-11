"""project finalization gate (review, Ф10)

Revision ID: f9d2c7b04a15
Revises: e7a9c4b2f108
Create Date: 2026-07-11 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f9d2c7b04a15'
down_revision: Union[str, Sequence[str], None] = 'e7a9c4b2f108'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Гейт финализации плана: статус draft/finalized + снимок ревью и отпечаток модели."""
    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.add_column(sa.Column('status', sa.String(length=16), nullable=False,
                                      server_default='draft'))
        batch_op.add_column(sa.Column('finalized_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('finalized_model_hash', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column(
            'finalized_review',
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'),
            nullable=True,
        ))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.drop_column('finalized_review')
        batch_op.drop_column('finalized_model_hash')
        batch_op.drop_column('finalized_at')
        batch_op.drop_column('status')
