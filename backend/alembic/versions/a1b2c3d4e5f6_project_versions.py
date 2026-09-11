"""project versions (снимки модели + анализ изменений, gap 4.4)

Revision ID: a1b2c3d4e5f6
Revises: f9d2c7b04a15
Create Date: 2026-07-16 10:00:00.000000

Таблица именованных снимков модели проекта. Изоляция арендатора — RLS-политика
(как projects/holdings): ``organization_id`` сравнивается с GUC ``app.current_org_id``.
На SQLite (dev/тесты) RLS — no-op, изоляция обеспечивается фильтрами CRUD.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f9d2c7b04a15'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'project_versions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('label', sa.String(length=255), nullable=False),
        sa.Column(
            'model',
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'),
            nullable=False,
        ),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('npv', sa.String(length=64), nullable=True),
        sa.Column('irr_annual', sa.String(length=64), nullable=True),
        sa.Column('engine_version', sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_project_versions_organization_id'), 'project_versions',
                    ['organization_id'], unique=False)
    op.create_index(op.f('ix_project_versions_project_id'), 'project_versions',
                    ['project_id'], unique=False)
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE project_versions ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE project_versions FORCE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY tenant_isolation ON project_versions "
            "USING (organization_id = current_setting('app.current_org_id', true)) "
            "WITH CHECK (organization_id = current_setting('app.current_org_id', true))"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS tenant_isolation ON project_versions")
        op.execute("ALTER TABLE project_versions DISABLE ROW LEVEL SECURITY")
    op.drop_index(op.f('ix_project_versions_project_id'), table_name='project_versions')
    op.drop_index(op.f('ix_project_versions_organization_id'), table_name='project_versions')
    op.drop_table('project_versions')
