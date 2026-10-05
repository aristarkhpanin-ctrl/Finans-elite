"""audit subject versions (версии дела: снимки модели + анализ изменений)

Revision ID: e6a1b3c5d7f9
Revises: e5b7c9d1f204
Create Date: 2026-09-07 12:00:00.000000

Именованные снимки модели дела. Проверка идёт итерациями (пришли документы — вердикт
уехал), и вопрос «что изменилось с прошлой недели» без версий остаётся без ответа.
Хранится модель на момент снимка + сводка того, что тогда показывал экран. Изоляция
арендатора — RLS-политика (как audit_subjects/project_versions); на SQLite (dev/тесты)
RLS — no-op, изоляцию обеспечивают фильтры CRUD.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e6a1b3c5d7f9'
down_revision: Union[str, Sequence[str], None] = 'e5b7c9d1f204'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'audit_subject_versions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('subject_id', sa.String(length=36), nullable=False),
        sa.Column('label', sa.String(length=255), nullable=False),
        sa.Column(
            'model',
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'),
            nullable=False,
        ),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('verdict', sa.String(length=32), nullable=True),
        sa.Column('risk_flags', sa.Integer(), nullable=True),
        sa.Column('equity_value', sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['subject_id'], ['audit_subjects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_audit_subject_versions_organization_id'),
                    'audit_subject_versions', ['organization_id'], unique=False)
    op.create_index(op.f('ix_audit_subject_versions_subject_id'),
                    'audit_subject_versions', ['subject_id'], unique=False)
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE audit_subject_versions ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE audit_subject_versions FORCE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY tenant_isolation ON audit_subject_versions "
            "USING (organization_id = current_setting('app.current_org_id', true)) "
            "WITH CHECK (organization_id = current_setting('app.current_org_id', true))"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS tenant_isolation ON audit_subject_versions")
        op.execute("ALTER TABLE audit_subject_versions DISABLE ROW LEVEL SECURITY")
    op.drop_index(op.f('ix_audit_subject_versions_subject_id'),
                  table_name='audit_subject_versions')
    op.drop_index(op.f('ix_audit_subject_versions_organization_id'),
                  table_name='audit_subject_versions')
    op.drop_table('audit_subject_versions')
