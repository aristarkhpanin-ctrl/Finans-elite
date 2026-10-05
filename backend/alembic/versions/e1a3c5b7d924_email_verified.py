"""users.email_verified_at (подтверждение адреса почты)

Revision ID: e1a3c5b7d924
Revises: d4f6b8a0c215
Create Date: 2026-09-19 09:40:00.000000

Одна колонка: когда человек доказал, что ящик его — перешёл по ссылке, которая **ушла
туда**. Все существующие записи получают ``NULL``, и это правильное значение: до
появления поля не доказывал никто, и записать им «подтверждено» значило бы выдать
догадку за факт.

Подтверждение ничего не запирает — на неподтверждённый адрес перестают уходить только
**информационные** письма (вход с нового устройства, упоминание в обсуждении). Дверные
(приглашение, ссылка администратора, восстановление пароля) уходят всегда: они
единственный способ войти.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e1a3c5b7d924'
down_revision: Union[str, Sequence[str], None] = 'd4f6b8a0c215'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users",
                  sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "email_verified_at")
