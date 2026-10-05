"""api_keys.created_by_id + api_keys.scopes + audit_log.via_key (запись через ключ)

Revision ID: a3c5e7b9d146
Revises: f2c4a6e8b135
Create Date: 2026-09-19 15:05:00.000000

Запись через ключ доступа (OPEN-DECISIONS §3). Возражение «у записи в журнале есть автор,
а ключ не автор» снято не отменой, а тем, что автор нашёлся: автор записи — **человек,
выпустивший ключ**, сам ключ идёт пометкой в той же записи (`audit_log.via_key`), и в
журнале видно обоих.

Отсюда три поля:

* ``api_keys.created_by_id`` — ссылка на выпустившего. Почта рядом (``created_by``)
  остаётся «надгробием» для списка; ссылка нужна для другого — по ней ключ и получает
  автора, и **гаснет**, когда автор уходит из организации;
* ``api_keys.scopes`` — права, выбранные при выпуске. Пустой список у прежних ключей
  значит «только чтение»: молча дописать запись ключам, которые уже лежат в чужих
  серверах, значило бы расширить доступ, которого никто не просил;
* ``audit_log.via_key`` — имя и открытая часть ключа в записи журнала.

**Ссылка проставляется задним числом по почте** (она уникальна в ``users``). Ключ,
выпущенный тем, кого в базе уже нет, останется без автора — и перестанет работать. Это
не побочный ущерб, а ровно то свойство, ради которого поле и заводится: доверенность без
доверителя не бывает. Отказ называет причину, и ключ выпускают заново.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a3c5e7b9d146'
down_revision: Union[str, Sequence[str], None] = 'f2c4a6e8b135'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('api_keys', sa.Column('created_by_id', sa.String(length=36),
                                        nullable=True))
    op.add_column('api_keys', sa.Column('scopes', sa.JSON(), nullable=True))
    op.add_column('audit_log', sa.Column('via_key', sa.String(length=255),
                                         nullable=False, server_default=''))
    # Внешний ключ ставится там, где он работает. На SQLite добавить ограничение в
    # существующую таблицу можно только пересозданием её целиком, а проверяются внешние
    # ключи там всё равно не по умолчанию — цена пересоздания была бы уплачена ни за что.
    if op.get_bind().dialect.name == "postgresql":
        op.create_foreign_key('fk_api_keys_created_by_id', 'api_keys', 'users',
                              ['created_by_id'], ['id'], ondelete='SET NULL')
    # Автор прежних ключей — по почте выпустившего: она уникальна в `users`. Кого в базе
    # уже нет, автора не получит, и его ключ перестанет работать (см. заголовок).
    op.execute(
        "UPDATE api_keys SET created_by_id = ("
        "  SELECT u.id FROM users u WHERE u.email = api_keys.created_by"
        ") WHERE created_by_id IS NULL AND created_by <> ''"
    )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint('fk_api_keys_created_by_id', 'api_keys', type_='foreignkey')
    op.drop_column('audit_log', 'via_key')
    op.drop_column('api_keys', 'scopes')
    op.drop_column('api_keys', 'created_by_id')
