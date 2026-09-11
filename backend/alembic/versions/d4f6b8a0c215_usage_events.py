"""usage_events (события пользования продуктом)

Revision ID: d4f6b8a0c215
Revises: c2e4a6b8d073
Create Date: 2026-09-11 05:10:00.000000

Не журнал: журнал отвечает клиенту «кто это сделал» и не пишет чтение, события отвечают
платформе «как пользуются» и пишут именно чтение. Участник обезличен отпечатком с солью
установки; содержимого моделей клиента здесь нет (перечень ключей контекста закрыт).

RLS здесь **не нужен и не ставится**: таблица не принадлежит арендатору — она про
пользование платформой, читает её только служебный контур, и организация в ней лишь
разрез. Политика с арендатором закрыла бы её от того единственного, кто её читает.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd4f6b8a0c215'
down_revision: Union[str, Sequence[str], None] = 'c2e4a6b8d073'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'usage_events',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('event', sa.String(length=32), nullable=False),
        sa.Column('actor', sa.String(length=32), nullable=False),
        sa.Column(
            'context',
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'),
            nullable=False,
        ),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_usage_events_organization_id'), 'usage_events',
                    ['organization_id'], unique=False)
    op.create_index(op.f('ix_usage_events_event'), 'usage_events', ['event'], unique=False)
    op.create_index(op.f('ix_usage_events_created_at'), 'usage_events',
                    ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_usage_events_created_at'), table_name='usage_events')
    op.drop_index(op.f('ix_usage_events_event'), table_name='usage_events')
    op.drop_index(op.f('ix_usage_events_organization_id'), table_name='usage_events')
    op.drop_table('usage_events')
