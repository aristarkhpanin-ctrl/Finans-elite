"""share_links — ссылка для инвестора или банка (пакет L, L4)

Revision ID: b8d0f2a4c6e9
Revises: a6c8e0b2d4f7
Create Date: 2026-10-04 23:00:00.000000

Просмотр снимка проекта (версии) без входа: срок обязателен, закрытие мгновенное и
строку не удаляет, секрет хранится отпечатком. RLS-политики у таблицы **нет**
(``db_models.NO_RLS_POLICY``, с причиной): ссылку предъявляет посторонний, и организация
выводится из найденной по отпечатку строки — как у ключа API. Управление ссылками идёт
внутри арендатора и фильтрует по организации явно.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b8d0f2a4c6e9'
down_revision: Union[str, Sequence[str], None] = 'a6c8e0b2d4f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'share_links',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('version_id', sa.String(length=36), nullable=False),
        sa.Column('label', sa.String(length=200), nullable=False),
        sa.Column('fingerprint', sa.String(length=64), nullable=False),
        sa.Column('created_by', sa.String(length=320), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_by', sa.String(length=320), server_default='', nullable=False),
        sa.Column('engine_version', sa.String(length=32), server_default='', nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['version_id'], ['project_versions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_share_links_organization_id', 'share_links', ['organization_id'])
    op.create_index('ix_share_links_project_id', 'share_links', ['project_id'])
    op.create_index('ix_share_links_fingerprint', 'share_links', ['fingerprint'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_share_links_fingerprint', table_name='share_links')
    op.drop_index('ix_share_links_project_id', table_name='share_links')
    op.drop_index('ix_share_links_organization_id', table_name='share_links')
    op.drop_table('share_links')
