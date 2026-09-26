"""users.staff_role — два уровня сотрудника платформы (ADMIN-PHASE-F, F5)

Revision ID: b5d7f9a1c360
Revises: a3c5e7b9d146
Create Date: 2026-09-20 05:10:00.000000

``is_staff`` был всё или ничего: поддержке нужен просмотр, а приостанавливать
организации и блокировать учётные записи — нет, и раз это выдавалось вместе, промах
поддержки стоил бы клиенту работы.

Поле не заменяет признак, а дополняет его: ``is_staff`` — **дверь** (пускать ли в
контур), ``staff_role`` — **уровень** внутри (``support`` | ``operator``). Слить их в
одно строковое поле значило бы превратить снятие признака в правку значения, где
опечатка оставляет дверь открытой.

**Существующим сотрудникам ставится ``operator``.** Понизить молча тех, кто уже работает
с этими правами, хуже, чем не разделять вовсе: следующая приостановка организации
упёрлась бы в отказ без единого слова о том, что правила изменились. Кому нужен уровень
поддержки — назначается явно, тем же скриптом.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b5d7f9a1c360'
down_revision: Union[str, Sequence[str], None] = 'a3c5e7b9d146'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('staff_role', sa.String(length=20),
                                     nullable=False, server_default=''))
    # Уровень есть только у сотрудника: у остальных поле пустое и ничего не значит.
    op.execute("UPDATE users SET staff_role = 'operator' WHERE is_staff")


def downgrade() -> None:
    op.drop_column('users', 'staff_role')
