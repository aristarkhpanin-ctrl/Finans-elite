"""organizations.is_demo + users.is_demo — демо без регистрации (пакет L, L2)

Revision ID: a6c8e0b2d4f7
Revises: e9a1b3c5d704
Create Date: 2026-10-04 22:00:00.000000

Посетитель сайта смотрит настоящую модель одной кнопкой, до регистрации. Для этого
нужны два признака:

* ``organizations.is_demo`` — организация, которую смотрят посетители: она под
  ограничением вида ``demo`` (смотреть, считать, выгружать — да, менять — нет), её
  события пользования не пишутся, а сводка платформы её не считает;
* ``users.is_demo`` — общий демо-вход. Любой изменяющий запрос от него отклоняется,
  кроме перечня расчётов (``deps.DEMO_ALLOWED``): учётную запись делят все посетители,
  и правка одного досталась бы следующему.

Признаки ставит ``scripts/seed_demo.py --public`` записью в базу (как ``set_staff.py``):
маршрута, превращающего организацию или человека в демо, у платформы нет.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a6c8e0b2d4f7'
down_revision: Union[str, Sequence[str], None] = 'e9a1b3c5d704'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('organizations', sa.Column('is_demo', sa.Boolean(), nullable=False,
                                             server_default=sa.false()))
    op.add_column('users', sa.Column('is_demo', sa.Boolean(), nullable=False,
                                     server_default=sa.false()))


def downgrade() -> None:
    op.drop_column('users', 'is_demo')
    op.drop_column('organizations', 'is_demo')
