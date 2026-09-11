"""audit groups (Финанс-Аудит v2: сохранённые группы предприятий)

Revision ID: c3d5e7f9a1b2
Revises: b2c4d6e8f0a1
Create Date: 2026-08-01 10:00:00.000000

Таблица сохранённых групп: состав свода (участники + внутригрупповые обороты). Результат
не хранится — свод пересчитывается по текущей отчётности участников. Изоляция арендатора —
RLS-политика (как audit_subjects/projects); на SQLite (dev/тесты) RLS — no-op, изоляцию
обеспечивают фильтры CRUD.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c3d5e7f9a1b2'
down_revision: Union[str, Sequence[str], None] = 'b2c4d6e8f0a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'audit_groups',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column(
            'model',
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'),
            nullable=False,
        ),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_audit_groups_organization_id'), 'audit_groups',
                    ['organization_id'], unique=False)
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE audit_groups ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE audit_groups FORCE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY tenant_isolation ON audit_groups "
            "USING (organization_id = current_setting('app.current_org_id', true)) "
            "WITH CHECK (organization_id = current_setting('app.current_org_id', true))"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS tenant_isolation ON audit_groups")
        op.execute("ALTER TABLE audit_groups DISABLE ROW LEVEL SECURITY")
    op.drop_index(op.f('ix_audit_groups_organization_id'), table_name='audit_groups')
    op.drop_table('audit_groups')
