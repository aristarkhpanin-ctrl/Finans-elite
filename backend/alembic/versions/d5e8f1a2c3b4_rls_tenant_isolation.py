"""RLS: изоляция арендаторов на уровне БД (projects, holdings)

Revision ID: d5e8f1a2c3b4
Revises: c3f5a2b8d140
Create Date: 2026-07-03 13:30:00.000000

Только PostgreSQL. Политики сравнивают ``organization_id`` с GUC ``app.current_org_id``,
который приложение выставляет на каждый запрос (``deps.current_org_id`` → ``set_tenant``),
а пул сбрасывает при checkout. ``FORCE`` — чтобы политика действовала и на владельца
таблицы (роль приложения). Незаданный GUC → пустая строка → строк не видно (deny-by-default).

На SQLite (dev/тесты) — no-op: RLS там нет, изоляция обеспечивается фильтрами в CRUD.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd5e8f1a2c3b4'
down_revision: Union[str, Sequence[str], None] = 'c3f5a2b8d140'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("projects", "holdings")


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            "USING (organization_id = current_setting('app.current_org_id', true)) "
            "WITH CHECK (organization_id = current_setting('app.current_org_id', true))"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in _TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
