"""add_subscriptions

Revision ID: a1b2c3d4e5f6
Revises: 9ca484f42f2c
Create Date: 2026-04-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '9ca484f42f2c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'subscriptions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('plan', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('razorpay_order_id', sa.String(length=100), nullable=True),
        sa.Column('razorpay_payment_id', sa.String(length=100), nullable=True),
        sa.Column('razorpay_subscription_id', sa.String(length=100), nullable=True),
        sa.Column('amount_paise', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_subscriptions_user_id'), 'subscriptions', ['user_id'], unique=False)
    op.create_index(op.f('ix_subscriptions_razorpay_order_id'), 'subscriptions', ['razorpay_order_id'], unique=False)
    op.create_index(op.f('ix_subscriptions_razorpay_payment_id'), 'subscriptions', ['razorpay_payment_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_subscriptions_razorpay_payment_id'), table_name='subscriptions')
    op.drop_index(op.f('ix_subscriptions_razorpay_order_id'), table_name='subscriptions')
    op.drop_index(op.f('ix_subscriptions_user_id'), table_name='subscriptions')
    op.drop_table('subscriptions')
