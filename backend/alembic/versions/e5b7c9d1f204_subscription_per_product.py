"""подписка на каждый продукт отдельно (свой каталог тарифов у «Элит» и «Аудита»)

Revision ID: e5b7c9d1f204
Revises: d4f6a8c0b2e3
Create Date: 2026-08-27 14:00:00.000000

Продукты продаются порознь, поэтому у организации своя подписка на каждый: уникальной
становится пара «организация + продукт» вместо одной организации.

Существующие подписки — это подписки на «Финанс-Элит»: ``server_default='business'``
проставляет продукт всем уже существующим строкам, и прежние тарифы остаются в силе.
Подписку на «Аудит» никому не заводим: её отсутствие означает тариф по умолчанию
(``audit_trial``), а выдумывать организациям платный тариф за них нельзя.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e5b7c9d1f204'
down_revision: Union[str, Sequence[str], None] = 'd4f6a8c0b2e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # batch_alter_table: на SQLite ограничения меняются пересозданием таблицы.
    with op.batch_alter_table('subscriptions') as batch:
        batch.add_column(sa.Column('product', sa.String(length=16), nullable=False,
                                   server_default='business'))
    # Старый уникальный индекс по organization_id мешает второй подписке той же
    # организации. Имя зависит от диалекта, поэтому снимаем его по факту наличия.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for ix in inspector.get_indexes('subscriptions'):
        if ix.get('unique') and ix['column_names'] == ['organization_id']:
            op.drop_index(ix['name'], table_name='subscriptions')
    for uq in inspector.get_unique_constraints('subscriptions'):
        if uq['column_names'] == ['organization_id']:
            with op.batch_alter_table('subscriptions') as batch:
                batch.drop_constraint(uq['name'], type_='unique')

    op.create_index(op.f('ix_subscriptions_organization_id'), 'subscriptions',
                    ['organization_id'], unique=False)
    with op.batch_alter_table('subscriptions') as batch:
        batch.create_unique_constraint('uq_org_product', ['organization_id', 'product'])


def downgrade() -> None:
    # Возврат к одной подписке на организацию: подписки не-основного продукта удаляются,
    # иначе уникальность по organization_id не восстановить.
    op.execute("DELETE FROM subscriptions WHERE product <> 'business'")
    with op.batch_alter_table('subscriptions') as batch:
        batch.drop_constraint('uq_org_product', type_='unique')
        batch.drop_column('product')
    op.drop_index(op.f('ix_subscriptions_organization_id'), table_name='subscriptions')
    op.create_index(op.f('ix_subscriptions_organization_id'), 'subscriptions',
                    ['organization_id'], unique=True)
