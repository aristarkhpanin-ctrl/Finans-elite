"""comment_subscriptions + users.comment_emails (письма об обсуждениях)

Revision ID: f2c4a6e8b135
Revises: e1a3c5b7d924
Create Date: 2026-09-19 11:20:00.000000

Подписка на ветку обсуждения вместо дайджеста (OPEN-DECISIONS §5). В таблице лежит **не
список подписчиков**, а исключения из него: подписан тот, кто участвует (написал реплику
или упомянут), и это выводится из самих реплик. Хранится то, чего из реплик не вывести, —
отписка от ветки (``muted_at``) и время последнего письма о ней (``last_notified_at``,
отсюда пауза между письмами).

Организации у строки нет намеренно: это личная настройка человека, как и реестр входов
(``user_sessions``), — поэтому ни ``organization_id``, ни RLS-политики здесь нет, а
ссылка «отписаться» из письма работает без входа.

``users.comment_emails`` — единственный выключатель «не пишите мне об обсуждениях вовсе».
Значение по умолчанию **истинно**: до этой миграции письма об упоминаниях приходили всем,
и выключить их задним числом значило бы молча отменить то, на что люди рассчитывают.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f2c4a6e8b135'
down_revision: Union[str, Sequence[str], None] = 'e1a3c5b7d924'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('comment_emails', sa.Boolean(), nullable=False,
                                     server_default=sa.text('true')))
    op.create_table(
        'comment_subscriptions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('subject_type', sa.String(length=16), nullable=False),
        sa.Column('subject_id', sa.String(length=36), nullable=False),
        sa.Column('anchor', sa.String(length=128), nullable=False),
        sa.Column('muted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_notified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'subject_type', 'subject_id', 'anchor',
                            name='uq_comment_subscription_thread'),
    )
    op.create_index(op.f('ix_comment_subscriptions_user_id'), 'comment_subscriptions',
                    ['user_id'], unique=False)
    op.create_index(op.f('ix_comment_subscriptions_subject_id'), 'comment_subscriptions',
                    ['subject_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_comment_subscriptions_subject_id'),
                  table_name='comment_subscriptions')
    op.drop_index(op.f('ix_comment_subscriptions_user_id'),
                  table_name='comment_subscriptions')
    op.drop_table('comment_subscriptions')
    op.drop_column('users', 'comment_emails')
