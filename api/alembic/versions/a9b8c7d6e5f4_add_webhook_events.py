"""add_webhook_events

Revision ID: a9b8c7d6e5f4
Revises: f7a8b9c0d1e2
Create Date: 2026-05-20 12:00:00.000000

Audit fix #19: Razorpay-event replay protection. Persists processed event IDs
so a captured webhook payload can't be re-posted to re-trigger activation.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "a9b8c7d6e5f4"
down_revision: Union[str, None] = "f7a8b9c0d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(insp, name: str) -> bool:
    return name in insp.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if not _has_table(insp, "webhook_events"):
        op.create_table(
            "webhook_events",
            sa.Column("event_id", sa.String(length=100), primary_key=True),
            sa.Column("event_type", sa.String(length=100), nullable=False),
            sa.Column(
                "processed_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if _has_table(insp, "webhook_events"):
        op.drop_table("webhook_events")
