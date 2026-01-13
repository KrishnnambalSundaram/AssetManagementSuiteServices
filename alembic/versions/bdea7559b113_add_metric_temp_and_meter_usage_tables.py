"""Add metric_temp and meter_usage tables

Revision ID: bdea7559b113
Revises: 
Create Date: 2025-12-20 14:28:24.990086

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'bdea7559b113'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create metric_temp table
    op.create_table(
        'metric_temp',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('internal_job_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('export_job_id', sa.String(255), nullable=True),
        sa.Column('frequency', sa.String(20), nullable=False),
        sa.Column('change_threshold', sa.Numeric(10, 2), nullable=False),
        sa.Column('start_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(20), server_default='pending'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['internal_job_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.CheckConstraint("frequency IN ('daily', 'weekly', 'monthly')", name='valid_frequency'),
        sa.CheckConstraint("status IN ('pending', 'processing', 'completed', 'failed')", name='valid_metric_status'),
    )

    # Create meter_usage table
    op.create_table(
        'meter_usage',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('org_id', sa.String(255), nullable=False),
        sa.Column('meter_id', sa.String(255), nullable=False),
        sa.Column('meter_name', sa.String(255), nullable=True),
        sa.Column('usage_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('billing_period_start', sa.DateTime(timezone=True), nullable=True),
        sa.Column('billing_period_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('meter_usage', sa.Numeric(20, 10), nullable=True),
        sa.Column('ipu', sa.Numeric(20, 10), nullable=True),
        sa.Column('scalar', sa.String(100), nullable=True),
        sa.Column('metric_category', sa.String(100), nullable=True),
        sa.Column('org_name', sa.String(255), nullable=True),
        sa.Column('org_type', sa.String(100), nullable=True),
        sa.Column('ipu_rate', sa.Numeric(20, 10), nullable=True),
        sa.Column('job_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['job_id'], ['metric_temp.id'], ondelete='SET NULL'),
        sa.UniqueConstraint('meter_id', 'usage_date', name='uq_meter_usage_meter_date'),
    )

    # Create indexes for metric_temp
    op.create_index('idx_metric_temp_internal_job_id', 'metric_temp', ['internal_job_id'])
    op.create_index('idx_metric_temp_export_job_id', 'metric_temp', ['export_job_id'])
    op.create_index('idx_metric_temp_status', 'metric_temp', ['status'])
    op.create_index('idx_metric_temp_frequency', 'metric_temp', ['frequency'])

    # Create indexes for meter_usage
    op.create_index('idx_meter_usage_org_id', 'meter_usage', ['org_id'])
    op.create_index('idx_meter_usage_meter_id', 'meter_usage', ['meter_id'])
    op.create_index('idx_meter_usage_usage_date', 'meter_usage', ['usage_date'])
    op.create_index('idx_meter_usage_job_id', 'meter_usage', ['job_id'])
    op.create_index('idx_meter_usage_meter_date', 'meter_usage', ['meter_id', 'usage_date'])


def downgrade() -> None:
    # Drop indexes for meter_usage
    op.drop_index('idx_meter_usage_meter_date', table_name='meter_usage')
    op.drop_index('idx_meter_usage_job_id', table_name='meter_usage')
    op.drop_index('idx_meter_usage_usage_date', table_name='meter_usage')
    op.drop_index('idx_meter_usage_meter_id', table_name='meter_usage')
    op.drop_index('idx_meter_usage_org_id', table_name='meter_usage')

    # Drop indexes for metric_temp
    op.drop_index('idx_metric_temp_frequency', table_name='metric_temp')
    op.drop_index('idx_metric_temp_status', table_name='metric_temp')
    op.drop_index('idx_metric_temp_export_job_id', table_name='metric_temp')
    op.drop_index('idx_metric_temp_internal_job_id', table_name='metric_temp')

    # Drop tables
    op.drop_table('meter_usage')
    op.drop_table('metric_temp')
