"""billing_documents + реквизиты покупателя + период платежа (закрывающие документы, G6)

Revision ID: e9a1b3c5d704
Revises: d8f0a2c4e693
Create Date: 2026-09-26 15:00:00.000000

Счета и акты (пакет G, G6). Три изменения:

* ``organizations``: реквизиты покупателя — полное наименование, ИНН, КПП, адрес.
  Отдельно от ``name``: имя в продукте — как организацию зовут свои, наименование —
  как её зовёт налоговая;
* ``payments``: какой период оплатил платёж (``period_start``/``period_end``) — по нему
  датируется акт. У прежних платежей периода нет, и угадывать его по дате платежа
  нельзя: акт по ним автоматически не формируется, и это названо;
* ``billing_documents``: первичные документы **платформы как продавца**. Внешних ключей
  нет намеренно — ни на организацию, ни на платёж: оба уходят вместе с клиентом (F6),
  а документ по ст. 29 402-ФЗ хранится пять лет и обязан читаться без них. Реквизиты
  сторон — снимком на дату документа.

RLS-политики у ``billing_documents`` нет (``db_models.NO_RLS_POLICY``, с причиной):
документ читает платформа, в том числе когда арендатора уже не существует. Изоляцию
для клиента держит фильтр CRUD по ``organization_id``.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e9a1b3c5d704'
down_revision: Union[str, Sequence[str], None] = 'd8f0a2c4e693'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.add_column('organizations', sa.Column('legal_name', sa.String(length=500),
                                             nullable=False, server_default=''))
    op.add_column('organizations', sa.Column('inn', sa.String(length=12), nullable=False,
                                             server_default=''))
    op.add_column('organizations', sa.Column('kpp', sa.String(length=9), nullable=False,
                                             server_default=''))
    op.add_column('organizations', sa.Column('legal_address', sa.String(length=500),
                                             nullable=False, server_default=''))
    op.add_column('payments', sa.Column('period_start', sa.DateTime(timezone=True),
                                        nullable=True))
    op.add_column('payments', sa.Column('period_end', sa.DateTime(timezone=True),
                                        nullable=True))
    op.create_table(
        'billing_documents',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('doc_date', sa.Date(), nullable=False),
        sa.Column('plan_code', sa.String(length=32), nullable=False),
        sa.Column('plan_name', sa.String(length=120), nullable=False),
        sa.Column('product', sa.String(length=16), nullable=False),
        sa.Column('months', sa.Integer(), nullable=False),
        sa.Column('amount_rub', sa.Integer(), nullable=False),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=True),
        sa.Column('period_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('payment_id', sa.String(length=36), nullable=True),
        sa.Column('seller', _JSON, nullable=False),
        sa.Column('buyer', _JSON, nullable=False),
        sa.Column('created_by', sa.String(length=320), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('kind', 'year', 'number', name='uq_billing_doc_number'),
        sa.UniqueConstraint('payment_id'),
    )
    op.create_index(op.f('ix_billing_documents_organization_id'), 'billing_documents',
                    ['organization_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_billing_documents_organization_id'),
                  table_name='billing_documents')
    op.drop_table('billing_documents')
    op.drop_column('payments', 'period_end')
    op.drop_column('payments', 'period_start')
    op.drop_column('organizations', 'legal_address')
    op.drop_column('organizations', 'kpp')
    op.drop_column('organizations', 'inn')
    op.drop_column('organizations', 'legal_name')
