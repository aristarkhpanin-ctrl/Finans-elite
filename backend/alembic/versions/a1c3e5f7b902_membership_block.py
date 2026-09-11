"""membership block (приостановка доступа участника: кто, когда и почему)

Блокируется **членство**, а не учётная запись: человек может состоять в нескольких
организациях, и администратор одной не отключает его в другой.

Поля пустые у всех существующих участников (`blocked_at IS NULL`), поэтому накат
инертен: до первой блокировки поведение платформы не меняется.

Revision ID: a1c3e5f7b902
Revises: f7b2d4a6c8e1
Create Date: 2026-09-10
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1c3e5f7b902"
down_revision: Union[str, Sequence[str], None] = "f7b2d4a6c8e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("memberships",
                  sa.Column("blocked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("memberships",
                  sa.Column("blocked_by", sa.String(length=255),
                            nullable=False, server_default=""))
    op.add_column("memberships",
                  sa.Column("block_reason", sa.String(length=500),
                            nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("memberships", "block_reason")
    op.drop_column("memberships", "blocked_by")
    op.drop_column("memberships", "blocked_at")
