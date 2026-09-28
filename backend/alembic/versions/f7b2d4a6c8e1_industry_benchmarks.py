"""industry benchmarks (свои отраслевые ориентиры организации)

Revision ID: f7b2d4a6c8e1
Revises: e6a1b3c5d7f9
Create Date: 2026-09-07 15:00:00.000000

Ориентиры мультипликаторов, которые ведёт сама организация. Платформа рыночных медиан
не знает, поэтому у каждого ориентира есть подпись: источник и дата. Изоляция арендатора
— RLS-политика (как остальные таблицы продукта); на SQLite (dev/тесты) RLS — no-op,
изоляцию обеспечивают фильтры CRUD.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f7b2d4a6c8e1'
down_revision: Union[str, Sequence[str], None] = 'e6a1b3c5d7f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'industry_benchmarks',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('industry', sa.String(length=120), nullable=False),
        sa.Column('metric', sa.String(length=32), nullable=False),
        sa.Column('value', sa.String(length=64), nullable=False),
        sa.Column('source', sa.String(length=255), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'industry', 'metric',
                            name='uq_org_industry_metric'),
    )
    op.create_index(op.f('ix_industry_benchmarks_organization_id'), 'industry_benchmarks',
                    ['organization_id'], unique=False)
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE industry_benchmarks ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE industry_benchmarks FORCE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY tenant_isolation ON industry_benchmarks "
            "USING (organization_id = current_setting('app.current_org_id', true)) "
            "WITH CHECK (organization_id = current_setting('app.current_org_id', true))"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS tenant_isolation ON industry_benchmarks")
        op.execute("ALTER TABLE industry_benchmarks DISABLE ROW LEVEL SECURITY")
    op.drop_index(op.f('ix_industry_benchmarks_organization_id'),
                  table_name='industry_benchmarks')
    op.drop_table('industry_benchmarks')
