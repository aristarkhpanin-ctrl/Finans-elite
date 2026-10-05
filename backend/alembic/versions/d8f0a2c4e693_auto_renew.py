"""subscriptions: автопродление + payments: срок, согласие, продлеваемый период (G5)

Revision ID: d8f0a2c4e693
Revises: c6e8b0d2f471
Create Date: 2026-09-26 09:00:00.000000

Автопродление (пакет G, G5). Деньги клиента не списываются без его явного согласия, и
согласие — это **тариф, сумма, срок и способ оплаты вместе**:

* ``subscriptions.auto_renew`` и сохранённый у провайдера способ оплаты
  (``payment_method_id`` — идентификатор у провайдера, не карта; ``payment_method_title``
  — как его назвать человеку в письме о списании);
* ``renew_months`` / ``renew_amount_rub`` — на какой срок и какую сумму дано согласие:
  выросшая цена списание останавливает, а не проходит молча;
* ``renew_attempts`` / ``renew_attempted_at`` / ``renew_error`` — не больше одной
  попытки в сутки и не больше трёх за один конец периода, причина неудачи — словами;
* ``payments.months`` — сколько месяцев оплачено (годовая оплата — 12): срок считается
  по нему, а не делением суммы на цену, которое сломалось бы на первой скидке;
* ``payments.auto_renew_consent`` — согласие дано **этим** платежом: способ, сохранённый
  провайдером без нашей отметки, автопродления не включает;
* ``payments.renews_period_end`` — какой конец периода продлевает автоматическое
  списание; по нему сверяется повтор.

Умолчания оставляют прежние строки прежними: автопродление выключено, платёж — за один
месяц и без согласия. Новых таблиц нет, RLS не меняется (обе таблицы в
``db_models.NO_RLS_POLICY`` со своими причинами).
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd8f0a2c4e693'
down_revision: Union[str, Sequence[str], None] = 'c6e8b0d2f471'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('subscriptions', sa.Column('auto_renew', sa.Boolean(), nullable=False,
                                             server_default=sa.text('false')))
    op.add_column('subscriptions', sa.Column('payment_method_id', sa.String(length=64),
                                             nullable=True))
    op.add_column('subscriptions', sa.Column('payment_method_title', sa.String(length=120),
                                             nullable=False, server_default=''))
    op.add_column('subscriptions', sa.Column('renew_months', sa.Integer(), nullable=False,
                                             server_default='1'))
    op.add_column('subscriptions', sa.Column('renew_amount_rub', sa.Integer(),
                                             nullable=False, server_default='0'))
    op.add_column('subscriptions', sa.Column('renew_attempts', sa.Integer(), nullable=False,
                                             server_default='0'))
    op.add_column('subscriptions', sa.Column('renew_attempted_at',
                                             sa.DateTime(timezone=True), nullable=True))
    op.add_column('subscriptions', sa.Column('renew_error', sa.String(length=500),
                                             nullable=False, server_default=''))
    op.add_column('payments', sa.Column('months', sa.Integer(), nullable=False,
                                        server_default='1'))
    op.add_column('payments', sa.Column('auto_renew_consent', sa.Boolean(), nullable=False,
                                        server_default=sa.text('false')))
    op.add_column('payments', sa.Column('renews_period_end', sa.DateTime(timezone=True),
                                        nullable=True))


def downgrade() -> None:
    op.drop_column('payments', 'renews_period_end')
    op.drop_column('payments', 'auto_renew_consent')
    op.drop_column('payments', 'months')
    op.drop_column('subscriptions', 'renew_error')
    op.drop_column('subscriptions', 'renew_attempted_at')
    op.drop_column('subscriptions', 'renew_attempts')
    op.drop_column('subscriptions', 'renew_amount_rub')
    op.drop_column('subscriptions', 'renew_months')
    op.drop_column('subscriptions', 'payment_method_title')
    op.drop_column('subscriptions', 'payment_method_id')
    op.drop_column('subscriptions', 'auto_renew')
