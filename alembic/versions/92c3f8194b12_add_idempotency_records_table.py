"""add_idempotency_records_table

Revision ID: 92c3f8194b12
Revises: 76fae743c6be
Create Date: 2026-08-22 20:29:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '92c3f8194b12'
down_revision: Union[str, Sequence[str], None] = '76fae743c6be'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'idempotency_records',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('job_id', sa.UUID(), nullable=True),
        sa.Column('key', sa.String(length=255), nullable=False),
        sa.Column('scope', sa.String(length=100), nullable=False, server_default='external_side_effect'),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='completed'),
        sa.Column('response_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key', name='uq_idempotency_records_key')
    )
    op.create_index(op.f('ix_idempotency_records_id'), 'idempotency_records', ['id'], unique=False)
    op.create_index(op.f('ix_idempotency_records_job_id'), 'idempotency_records', ['job_id'], unique=False)
    op.create_index(op.f('ix_idempotency_records_key'), 'idempotency_records', ['key'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_idempotency_records_key'), table_name='idempotency_records')
    op.drop_index(op.f('ix_idempotency_records_job_id'), table_name='idempotency_records')
    op.drop_index(op.f('ix_idempotency_records_id'), table_name='idempotency_records')
    op.drop_table('idempotency_records')
