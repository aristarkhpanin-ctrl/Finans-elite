"""comments (обсуждение рядом с числами: комментарии к проекту и к делу)

Revision ID: a9c1e3b5d740
Revises: f8b1d3c5a729
Create Date: 2026-09-10 21:10:00.000000

Комментарий привязан к **месту** внутри проекта или дела (вкладка, строка отчёта,
продукт, этап), а не к сущности целиком: «обсуждение проекта» — это чат, из которого
через месяц не понять, о какой строке шла речь. Подпись места хранится на момент
написания — объект переименуют или удалят, а разговор обязан остаться понятным.

Одна таблица на оба продукта: обсуждение у проекта и у дела устроено одинаково, и вторая
таблица разошлась бы с первой. Изоляция арендатора — RLS-политика (как у projects и
audit_subjects); на SQLite (dev/тесты) RLS — no-op, изоляцию держат фильтры CRUD.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a9c1e3b5d740'
down_revision: Union[str, Sequence[str], None] = 'f8b1d3c5a729'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'comments',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('subject_type', sa.String(length=16), nullable=False),
        sa.Column('subject_id', sa.String(length=36), nullable=False),
        sa.Column('anchor', sa.String(length=128), nullable=False),
        sa.Column('anchor_label', sa.String(length=255), nullable=False),
        sa.Column('author_id', sa.String(length=36), nullable=True),
        sa.Column('author_email', sa.String(length=255), nullable=False),
        sa.Column('author_name', sa.String(length=255), nullable=False),
        sa.Column('body', sa.String(length=4000), nullable=False),
        sa.Column('mentions', sa.String(length=1000), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_by', sa.String(length=255), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deleted_by', sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'],
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['author_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_comments_organization_id'), 'comments',
                    ['organization_id'], unique=False)
    op.create_index(op.f('ix_comments_subject_id'), 'comments',
                    ['subject_id'], unique=False)
    op.create_index(op.f('ix_comments_created_at'), 'comments',
                    ['created_at'], unique=False)
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE comments ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE comments FORCE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY tenant_isolation ON comments "
            "USING (organization_id = current_setting('app.current_org_id', true)) "
            "WITH CHECK (organization_id = current_setting('app.current_org_id', true))"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS tenant_isolation ON comments")
        op.execute("ALTER TABLE comments DISABLE ROW LEVEL SECURITY")
    op.drop_index(op.f('ix_comments_created_at'), table_name='comments')
    op.drop_index(op.f('ix_comments_subject_id'), table_name='comments')
    op.drop_index(op.f('ix_comments_organization_id'), table_name='comments')
    op.drop_table('comments')
