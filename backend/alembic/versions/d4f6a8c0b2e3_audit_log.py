"""audit_log (журнал действий: 152-ФЗ, ARCHITECTURE §4)

Revision ID: d4f6a8c0b2e3
Revises: c3d5e7f9a1b2
Create Date: 2026-08-27 12:00:00.000000

Журнал действий в организации: кто, что и когда. Пробел был обратный — журнал доступа
показан на макете «Экран 11» и предписан ARCHITECTURE §4, но таблицы в коде не было.

``user_id`` обнуляется при удалении пользователя (SET NULL), а ``actor_email`` остаётся
текстом: журнал обязан отвечать «кто это сделал» и через год после увольнения.

Изоляция арендатора — RLS-политика (как projects/audit_subjects/audit_groups); на SQLite
(dev/тесты) RLS — no-op, изоляцию обеспечивают фильтры CRUD.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd4f6a8c0b2e3'
down_revision: Union[str, Sequence[str], None] = 'c3d5e7f9a1b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'audit_log',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=True),
        sa.Column('actor_email', sa.String(length=255), nullable=False),
        sa.Column('action', sa.String(length=64), nullable=False),
        sa.Column('entity_type', sa.String(length=32), nullable=False),
        sa.Column('entity_id', sa.String(length=36), nullable=False),
        sa.Column('entity_name', sa.String(length=255), nullable=False),
        sa.Column('details', sa.String(length=500), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_audit_log_organization_id'), 'audit_log',
                    ['organization_id'], unique=False)
    # Журнал читают «последние сверху» — индекс по времени нужен с первого дня.
    op.create_index(op.f('ix_audit_log_created_at'), 'audit_log',
                    ['created_at'], unique=False)
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE audit_log FORCE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY tenant_isolation ON audit_log "
            "USING (organization_id = current_setting('app.current_org_id', true)) "
            "WITH CHECK (organization_id = current_setting('app.current_org_id', true))"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS tenant_isolation ON audit_log")
        op.execute("ALTER TABLE audit_log DISABLE ROW LEVEL SECURITY")
    op.drop_index(op.f('ix_audit_log_created_at'), table_name='audit_log')
    op.drop_index(op.f('ix_audit_log_organization_id'), table_name='audit_log')
    op.drop_table('audit_log')
