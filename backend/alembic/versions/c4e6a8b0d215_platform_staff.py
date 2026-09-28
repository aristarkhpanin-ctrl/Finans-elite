"""Сотрудник платформы: признак ``users.is_staff`` и служебный журнал ``staff_log``

Признак — отдельная ось власти, а не роль организации (ADMIN-DECOMPOSITION.md, B1).
Значение по умолчанию ложно, поэтому существующие пользователи ничего не получают:
сотрудника назначают скриптом ``scripts/set_staff.py``, а не запросом к API.

``staff_log`` живёт **без RLS и без внешнего ключа на организацию**. Без RLS — потому
что это платформенная таблица: у неё нет арендатора, и политика «показывать строки
своего арендатора» вернула бы пустоту. Без внешнего ключа — потому что каскад стёр бы
след визита вместе с удалённой организацией, то есть ровно тогда, когда след нужнее
всего.

Revision ID: c4e6a8b0d215
Revises: b2d4f6a8c013
Create Date: 2026-09-10
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "c4e6a8b0d215"
down_revision: Union[str, Sequence[str], None] = "b2d4f6a8c013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("is_staff", sa.Boolean(), nullable=False,
                                     server_default=sa.text("false")))
    op.create_table(
        "staff_log",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("actor_email", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False, server_default=""),
        sa.Column("organization_name", sa.String(length=255), nullable=False,
                  server_default=""),
        sa.Column("details", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_staff_log_created_at", "staff_log", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_staff_log_created_at", table_name="staff_log")
    op.drop_table("staff_log")
    op.drop_column("users", "is_staff")
