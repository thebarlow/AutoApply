"""add payments

Revision ID: aa01payments01
Revises: 85e2c6aab4f8
Create Date: 2026-06-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "aa01payments01"
down_revision: Union[str, Sequence[str], None] = "85e2c6aab4f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("account", sa.Column("stripe_customer_id", sa.String(), nullable=True))
    op.create_table(
        "purchase",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("stripe_session_id", sa.String(), nullable=False),
        sa.Column("stripe_event_id", sa.String(), nullable=True),
        sa.Column("price_id", sa.String(), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False),
        sa.Column("amount_usd", sa.Float(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.UniqueConstraint("stripe_session_id", name="uq_purchase_session"),
        sa.UniqueConstraint("stripe_event_id", name="uq_purchase_event"),
    )
    op.create_index("ix_purchase_profile_id", "purchase", ["profile_id"])


def downgrade() -> None:
    op.drop_index("ix_purchase_profile_id", table_name="purchase")
    op.drop_table("purchase")
    op.drop_column("account", "stripe_customer_id")
