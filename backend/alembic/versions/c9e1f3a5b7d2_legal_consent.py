"""users: согласие на обработку ПД и принятие оферты — время и редакция (пакет L, L5)

Revision ID: c9e1f3a5b7d2
Revises: b8d0f2a4c6e9
Create Date: 2026-10-04 23:30:00.000000

С 1 сентября 2025 года согласие на обработку персональных данных оформляется
**отдельно** от других документов (ч. 1 ст. 9 152-ФЗ в ред. 156-ФЗ): при регистрации это
своя отметка, а не строка под кнопкой. Сохраняются **время** и **редакция** — иначе
«на что именно человек согласился» не проверить, когда текст сменится.

Оферта принимается регистрацией (для оплаты — оплатой), и её редакция пишется рядом.
У учётных записей, заведённых раньше, поля пусты: это **неизвестно**, а не «отказ», и
профиль предлагает дать согласие, а не делает вид, что оно было.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c9e1f3a5b7d2'
down_revision: Union[str, Sequence[str], None] = 'b8d0f2a4c6e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('pd_consent_at', sa.DateTime(timezone=True),
                                     nullable=True))
    op.add_column('users', sa.Column('pd_consent_edition', sa.String(length=64),
                                     nullable=False, server_default=''))
    op.add_column('users', sa.Column('terms_accepted_at', sa.DateTime(timezone=True),
                                     nullable=True))
    op.add_column('users', sa.Column('terms_edition', sa.String(length=64),
                                     nullable=False, server_default=''))


def downgrade() -> None:
    op.drop_column('users', 'terms_edition')
    op.drop_column('users', 'terms_accepted_at')
    op.drop_column('users', 'pd_consent_edition')
    op.drop_column('users', 'pd_consent_at')
