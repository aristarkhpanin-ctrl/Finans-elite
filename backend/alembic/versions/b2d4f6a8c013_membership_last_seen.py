"""membership last_seen (когда участник последний раз работал в организации)

Пустое поле у существующих участников означает «неизвестно», а не «никогда»: до этой
миграции присутствие не записывалось вовсе, и выдавать молчание за отсутствие нельзя.

Revision ID: b2d4f6a8c013
Revises: a1c3e5f7b902
Create Date: 2026-09-10
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "b2d4f6a8c013"
down_revision: Union[str, Sequence[str], None] = "a1c3e5f7b902"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("memberships",
                  sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("memberships", "last_seen_at")
