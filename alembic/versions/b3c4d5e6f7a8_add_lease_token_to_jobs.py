"""add_lease_token_to_jobs

Revision ID: b3c4d5e6f7a8
Revises: 92c3f8194b12
Create Date: 2026-08-22 22:05:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, Sequence[str], None] = '92c3f8194b12'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('jobs', sa.Column('lease_token', sa.UUID(), nullable=True))
    op.create_index(op.f('ix_jobs_lease_token'), 'jobs', ['lease_token'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_jobs_lease_token'), table_name='jobs')
    op.drop_column('jobs', 'lease_token')
