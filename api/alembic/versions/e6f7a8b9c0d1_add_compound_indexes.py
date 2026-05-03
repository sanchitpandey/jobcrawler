"""add_compound_indexes

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-04-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "e6f7a8b9c0d1"
down_revision: Union[str, None] = "d5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Weekly apply count: WHERE user_id = ? AND scored_at >= ?
    op.create_index(
        "ix_applications_user_id_scored_at",
        "applications",
        ["user_id", "scored_at"],
    )
    # Review queue / discovery queue: WHERE user_id = ? AND status = ?
    op.create_index(
        "ix_applications_user_id_status",
        "applications",
        ["user_id", "status"],
    )
    # Daily LLM limit: WHERE user_id = ? AND created_at >= ?
    op.create_index(
        "ix_llm_usage_logs_user_id_created_at",
        "llm_usage_logs",
        ["user_id", "created_at"],
    )
    # Billing status: WHERE user_id = ? AND status = 'active'
    op.create_index(
        "ix_subscriptions_user_id_status",
        "subscriptions",
        ["user_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_subscriptions_user_id_status", table_name="subscriptions")
    op.drop_index("ix_llm_usage_logs_user_id_created_at", table_name="llm_usage_logs")
    op.drop_index("ix_applications_user_id_status", table_name="applications")
    op.drop_index("ix_applications_user_id_scored_at", table_name="applications")
