"""support_grants — доступ поддержки к моделям по гранту клиента (ADMIN-PHASE-F, F4)

Revision ID: c6e8b0d2f471
Revises: b5d7f9a1c360
Create Date: 2026-09-20 06:00:00.000000

Правило «оператор платформы не видит содержимого моделей клиентов» не отменяется —
у него появляется дверь, ключ от которой **у клиента**. Форма принята целиком: выдаёт
организация (право ``org.manage``), срок ограничен сверху (72 ч), каждое чтение пишется
в журнал самой организации.

Строка **не удаляется при закрытии доступа** — проставляется ``revoked_at``: «нам никто
не открывал» должно быть проверяемым утверждением, а не отсутствием записи.

Изоляция арендатора — RLS-политика, как у остальных таблиц организации; на SQLite
(dev/тесты) RLS — no-op, изоляцию обеспечивают фильтры CRUD.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c6e8b0d2f471'
down_revision: Union[str, Sequence[str], None] = 'b5d7f9a1c360'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'support_grants',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('granted_by', sa.String(length=36), nullable=False, server_default=''),
        sa.Column('granted_by_email', sa.String(length=320), nullable=False,
                  server_default=''),
        sa.Column('reason', sa.String(length=500), nullable=False, server_default=''),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'],
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_support_grants_organization_id'), 'support_grants',
                    ['organization_id'], unique=False)
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE support_grants ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE support_grants FORCE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY tenant_isolation ON support_grants "
            "USING (organization_id = current_setting('app.current_org_id', true)) "
            "WITH CHECK (organization_id = current_setting('app.current_org_id', true))"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS tenant_isolation ON support_grants")
        op.execute("ALTER TABLE support_grants DISABLE ROW LEVEL SECURITY")
    op.drop_index(op.f('ix_support_grants_organization_id'), table_name='support_grants')
    op.drop_table('support_grants')
