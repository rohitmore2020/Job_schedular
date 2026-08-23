"""add_job_batches_table

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-08-23 13:45:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, Sequence[str], None] = 'b3c4d5e6f7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create batch_status enum type if it does not exist
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'batch_status') THEN
                CREATE TYPE batch_status AS ENUM ('pending', 'processing', 'completed', 'partially_failed', 'failed', 'cancelled');
            END IF;
        END$$;
    """)

    # 2. Create job_batches table
    op.create_table(
        'job_batches',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('queue_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column(
            'status',
            postgresql.ENUM('pending', 'processing', 'completed', 'partially_failed', 'failed', 'cancelled', name='batch_status', create_type=False),
            nullable=False,
            server_default='processing',
        ),
        sa.Column('total_jobs', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('completed_jobs', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed_jobs', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('cancelled_jobs', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['queue_id'], ['queues.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_job_batches_id'), 'job_batches', ['id'], unique=False)
    op.create_index(op.f('ix_job_batches_project_id'), 'job_batches', ['project_id'], unique=False)
    op.create_index(op.f('ix_job_batches_queue_id'), 'job_batches', ['queue_id'], unique=False)
    op.create_index(op.f('ix_job_batches_status'), 'job_batches', ['status'], unique=False)

    # 3. Add batch_id to jobs table
    op.add_column('jobs', sa.Column('batch_id', sa.UUID(), nullable=True))
    op.create_index(op.f('ix_jobs_batch_id'), 'jobs', ['batch_id'], unique=False)
    op.create_foreign_key(
        'fk_jobs_batch_id_job_batches',
        'jobs',
        'job_batches',
        ['batch_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_jobs_batch_id_job_batches', 'jobs', type_='foreignkey')
    op.drop_index(op.f('ix_jobs_batch_id'), table_name='jobs')
    op.drop_column('jobs', 'batch_id')

    op.drop_index(op.f('ix_job_batches_status'), table_name='job_batches')
    op.drop_index(op.f('ix_job_batches_queue_id'), table_name='job_batches')
    op.drop_index(op.f('ix_job_batches_project_id'), table_name='job_batches')
    op.drop_index(op.f('ix_job_batches_id'), table_name='job_batches')
    op.drop_table('job_batches')

    batch_status_enum = postgresql.ENUM(
        'pending', 'processing', 'completed', 'partially_failed', 'failed', 'cancelled',
        name='batch_status'
    )
    batch_status_enum.drop(op.get_bind(), checkfirst=True)
