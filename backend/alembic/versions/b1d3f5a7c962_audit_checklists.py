"""audit_checklists (свои чек-листы организации для дел «Финанс-Аудита»)

Revision ID: b1d3f5a7c962
Revises: a9c1e3b5d740
Create Date: 2026-09-10 21:40:00.000000

Отраслевого каталога процедур у платформы нет и не будет: он утверждал бы, что именно
проверяют в конкретной отрасли, а такой методики у платформы нет. Чек-лист принадлежит
организации и написан её аналитиками — тот же приём, что с отраслевыми ориентирами.
Изоляция арендатора — RLS-политика (как industry_benchmarks); на SQLite — no-op.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b1d3f5a7c962'
down_revision: Union[str, Sequence[str], None] = 'a9c1e3b5d740'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'audit_checklists',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('scope', sa.String(length=200), nullable=False),
        sa.Column(
            'items',
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'),
            nullable=False,
        ),
        sa.Column('author_email', sa.String(length=255), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'],
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'name', name='uq_org_checklist_name'),
    )
    op.create_index(op.f('ix_audit_checklists_organization_id'), 'audit_checklists',
                    ['organization_id'], unique=False)
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE audit_checklists ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE audit_checklists FORCE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY tenant_isolation ON audit_checklists "
            "USING (organization_id = current_setting('app.current_org_id', true)) "
            "WITH CHECK (organization_id = current_setting('app.current_org_id', true))"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS tenant_isolation ON audit_checklists")
        op.execute("ALTER TABLE audit_checklists DISABLE ROW LEVEL SECURITY")
    op.drop_index(op.f('ix_audit_checklists_organization_id'),
                  table_name='audit_checklists')
    op.drop_table('audit_checklists')
