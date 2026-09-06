"""audit subjects (Финанс-Аудит, продукт №2: субъекты анализа факт. отчётности)

Revision ID: b2c4d6e8f0a1
Revises: a1b2c3d4e5f6
Create Date: 2026-07-31 12:00:00.000000

Таблица субъектов анализа. Изоляция арендатора — RLS-политика (как projects/holdings):
``organization_id`` сравнивается с GUC ``app.current_org_id``. На SQLite (dev/тесты)
RLS — no-op, изоляция обеспечивается фильтрами CRUD.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b2c4d6e8f0a1'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'audit_subjects',
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
    op.create_index(op.f('ix_audit_subjects_organization_id'), 'audit_subjects',
                    ['organization_id'], unique=False)
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE audit_subjects ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE audit_subjects FORCE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY tenant_isolation ON audit_subjects "
            "USING (organization_id = current_setting('app.current_org_id', true)) "
            "WITH CHECK (organization_id = current_setting('app.current_org_id', true))"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS tenant_isolation ON audit_subjects")
        op.execute("ALTER TABLE audit_subjects DISABLE ROW LEVEL SECURITY")
    op.drop_index(op.f('ix_audit_subjects_organization_id'), table_name='audit_subjects')
    op.drop_table('audit_subjects')
