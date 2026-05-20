"""add_refresh_tokens_and_auth_throttle

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-05-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, None] = "e6f7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(insp, name: str) -> bool:
    return name in insp.get_table_names()


def _has_column(insp, table: str, col: str) -> bool:
    return any(c["name"] == col for c in insp.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    # Brute-force counters on users — idempotent for dev DBs that may have
    # been created via Base.metadata.create_all (and thus already have these
    # columns) or via fresh alembic on prod.
    if not _has_column(insp, "users", "verification_attempts"):
        op.add_column(
            "users",
            sa.Column("verification_attempts", sa.Integer(), nullable=False, server_default="0"),
        )
    if not _has_column(insp, "users", "failed_login_attempts"):
        op.add_column(
            "users",
            sa.Column("failed_login_attempts", sa.Integer(), nullable=False, server_default="0"),
        )
    if not _has_column(insp, "users", "lockout_until"):
        op.add_column(
            "users",
            sa.Column("lockout_until", sa.DateTime(timezone=True), nullable=True),
        )

    if _has_table(insp, "refresh_tokens"):
        return  # Table + indexes + uq constraint were already provisioned.

    # Refresh token table — supports rotation + reuse detection + revocation
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("jti", sa.String(length=64), nullable=False, unique=True),
        sa.Column("family_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("family_revoked", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_jti", "refresh_tokens", ["jti"])
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"])
    op.create_index(
        "ix_refresh_tokens_user_id_revoked",
        "refresh_tokens",
        ["user_id", "revoked"],
    )

    # Unique constraint on Subscription.razorpay_payment_id (fix #7 race) — best-effort.
    # SQLite can't ALTER ... ADD CONSTRAINT, so we wrap in batch mode.
    with op.batch_alter_table("subscriptions") as batch_op:
        batch_op.create_unique_constraint(
            "uq_subscriptions_razorpay_payment_id",
            ["razorpay_payment_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("subscriptions") as batch_op:
        batch_op.drop_constraint(
            "uq_subscriptions_razorpay_payment_id", type_="unique"
        )
    op.drop_index("ix_refresh_tokens_user_id_revoked", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_family_id", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_jti", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_column("users", "lockout_until")
    op.drop_column("users", "failed_login_attempts")
    op.drop_column("users", "verification_attempts")
