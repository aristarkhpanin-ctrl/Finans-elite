"""Приостановка организации и блокировка учётной записи платформы (B2)

Оба поля пусты у существующих строк, поэтому изменение инертно: пока оператор ничего не
приостановил, платформа работает как прежде. Статус подписки при этом уже писался — с
этой фазы он **начинает читаться**, но самой схемы это не касается.

Revision ID: d5f7a9c1e326
Revises: c4e6a8b0d215
Create Date: 2026-09-10
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "d5f7a9c1e326"
down_revision: Union[str, Sequence[str], None] = "c4e6a8b0d215"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("organizations",
                  sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("organizations", sa.Column("suspended_by", sa.String(length=255),
                                             nullable=False, server_default=""))
    op.add_column("organizations", sa.Column("suspend_reason", sa.String(length=500),
                                             nullable=False, server_default=""))
    op.add_column("users",
                  sa.Column("blocked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("blocked_by", sa.String(length=255),
                                     nullable=False, server_default=""))
    op.add_column("users", sa.Column("block_reason", sa.String(length=500),
                                     nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("users", "block_reason")
    op.drop_column("users", "blocked_by")
    op.drop_column("users", "blocked_at")
    op.drop_column("organizations", "suspend_reason")
    op.drop_column("organizations", "suspended_by")
    op.drop_column("organizations", "suspended_at")
