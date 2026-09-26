"""api_keys (ключи доступа к API организации)

Revision ID: c2e4a6b8d073
Revises: b1d3f5a7c962
Create Date: 2026-09-10 21:55:00.000000

Ключ принадлежит организации и читает её данные: выгрузка в BI, 1С, скрипт отчётности.
Хранится только отпечаток секрета — самого ключа платформа не знает. Отзыв мгновенный:
состояние читается из базы на каждом запросе. RLS здесь **не нужен**: ключ ищется по
префиксу до того, как арендатор известен, — он-то арендатора и называет.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c2e4a6b8d073'
down_revision: Union[str, Sequence[str], None] = 'b1d3f5a7c962'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'api_keys',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('prefix', sa.String(length=32), nullable=False),
        sa.Column('fingerprint', sa.String(length=64), nullable=False),
        sa.Column('created_by', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_by', sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'],
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_api_keys_organization_id'), 'api_keys',
                    ['organization_id'], unique=False)
    op.create_index(op.f('ix_api_keys_prefix'), 'api_keys', ['prefix'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_api_keys_prefix'), table_name='api_keys')
    op.drop_index(op.f('ix_api_keys_organization_id'), table_name='api_keys')
    op.drop_table('api_keys')
