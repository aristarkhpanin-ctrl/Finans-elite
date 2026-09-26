"""Второй фактор: секрет, резервные коды и защита от подбора (C2)

Поля пусты у всех существующих пользователей, поэтому изменение инертно: пока человек не
включил второй фактор, вход работает как прежде.

``totp_recovery`` — список отпечатков (SHA-256), а не самих кодов: код показывается один
раз, как пароль. Быстрый хэш здесь достаточен и выбран осознанно — медленный нужен там,
где секрет угадывают по словарю, а резервный код несёт 100 бит случайности.

Revision ID: f8b1d3c5a729
Revises: e7a9c3b5d148
Create Date: 2026-09-10
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "f8b1d3c5a729"
down_revision: Union[str, Sequence[str], None] = "e7a9c3b5d148"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JSON = sa.JSON().with_variant(JSONB, "postgresql")


def upgrade() -> None:
    op.add_column("users", sa.Column("totp_secret", sa.String(length=64), nullable=False,
                                     server_default=""))
    op.add_column("users", sa.Column("totp_enabled_at", sa.DateTime(timezone=True),
                                     nullable=True))
    op.add_column("users", sa.Column("totp_recovery", _JSON, nullable=True))
    op.add_column("users", sa.Column("totp_failures", sa.Integer(), nullable=False,
                                     server_default="0"))
    op.add_column("users", sa.Column("totp_locked_until", sa.DateTime(timezone=True),
                                     nullable=True))


def downgrade() -> None:
    for column in ("totp_locked_until", "totp_failures", "totp_recovery",
                   "totp_enabled_at", "totp_secret"):
        op.drop_column("users", column)
