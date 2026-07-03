"""analysis jobs (фоновые задачи анализа)

Revision ID: e7a9c4b2f108
Revises: d5e8f1a2c3b4
Create Date: 2026-07-03 14:40:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e7a9c4b2f108'
down_revision: Union[str, Sequence[str], None] = 'd5e8f1a2c3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'analysis_jobs',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('kind', sa.String(length=32), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_analysis_jobs_organization_id', 'analysis_jobs', ['organization_id'])


def downgrade() -> None:
    op.drop_index('ix_analysis_jobs_organization_id', table_name='analysis_jobs')
    op.drop_table('analysis_jobs')
