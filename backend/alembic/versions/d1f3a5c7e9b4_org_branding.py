"""org branding (логотип организации в документах, L9)

Revision ID: d1f3a5c7e9b4
Revises: c9e1f3a5b7d2
Create Date: 2026-10-05 09:00:00.000000

Одна картинка на организацию — в базе, строкой организации: это не файловое хранилище
(OPEN-DECISIONS §6, узкий случай). Изоляция арендатора — RLS-политика, как у остальных
таблиц продукта; на SQLite (dev/тесты) RLS — no-op, изоляцию обеспечивают фильтры CRUD.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd1f3a5c7e9b4'
down_revision: Union[str, Sequence[str], None] = 'c9e1f3a5b7d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'org_branding',
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('logo', sa.LargeBinary(), nullable=False),
        sa.Column('logo_mime', sa.String(length=32), nullable=False),
        sa.Column('logo_width', sa.Integer(), nullable=False),
        sa.Column('logo_height', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_by', sa.String(length=320), nullable=False, server_default=''),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('organization_id'),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE org_branding ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE org_branding FORCE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY tenant_isolation ON org_branding "
            "USING (organization_id = current_setting('app.current_org_id', true)) "
            "WITH CHECK (organization_id = current_setting('app.current_org_id', true))"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS tenant_isolation ON org_branding")
        op.execute("ALTER TABLE org_branding DISABLE ROW LEVEL SECURITY")
    op.drop_table('org_branding')
