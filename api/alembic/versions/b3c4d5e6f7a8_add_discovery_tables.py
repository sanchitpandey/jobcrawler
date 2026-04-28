"""add_discovery_tables

Revision ID: b3c4d5e6f7a8
Revises: a1b2c3d4e5f6
Create Date: 2026-04-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add source + discovery_batch_id columns to applications
    op.add_column('applications', sa.Column('source', sa.String(length=50), nullable=False, server_default='manual'))
    op.add_column('applications', sa.Column('discovery_batch_id', sa.String(length=36), nullable=True))

    # Create search_preferences table
    op.create_table(
        'search_preferences',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('keywords', sa.JSON(), nullable=True),
        sa.Column('location', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('experience_levels', sa.String(length=20), nullable=False, server_default=''),
        sa.Column('remote_filter', sa.String(length=10), nullable=False, server_default=''),
        sa.Column('time_range', sa.String(length=20), nullable=False, server_default='r86400'),
        sa.Column('auto_apply_threshold', sa.Integer(), nullable=False, server_default='75'),
        sa.Column('max_daily_applications', sa.Integer(), nullable=False, server_default='15'),
        sa.Column('skip_companies', sa.JSON(), nullable=True),
        sa.Column('skip_title_keywords', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id'),
    )
    op.create_index(op.f('ix_search_preferences_user_id'), 'search_preferences', ['user_id'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_search_preferences_user_id'), table_name='search_preferences')
    op.drop_table('search_preferences')
    op.drop_column('applications', 'discovery_batch_id')
    op.drop_column('applications', 'source')
