"""Сеансы входа: реестр входов и отзыв доступа (C1)

**Все входят заново один раз.** Токены, выпущенные до этой миграции, не несут ``jti`` и
не связаны ни с одним сеансом, поэтому перестают приниматься. Молчаливое исключение для
них («токен без jti считаем действительным») стало бы постоянной дырой: отозвать такой
токен было бы нечем, и жил бы он до истечения срока — то есть ровно столько, сколько
злоумышленнику и нужно.

Таблица заводится **без RLS**: сеанс принадлежит человеку, а не организации, и арендатора
у него нет. Человек состоит в нескольких организациях одним и тем же входом.

Revision ID: e7a9c3b5d148
Revises: d5f7a9c1e326
Create Date: 2026-09-10
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "e7a9c3b5d148"
down_revision: Union[str, Sequence[str], None] = "d5f7a9c1e326"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("ip", sa.String(length=45), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
    op.drop_table("user_sessions")
