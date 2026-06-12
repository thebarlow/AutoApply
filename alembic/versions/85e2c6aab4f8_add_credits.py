"""add credits

Revision ID: 85e2c6aab4f8
Revises: 5285bd395643
Create Date: 2026-06-12 12:03:15.418338

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '85e2c6aab4f8'
down_revision: Union[str, Sequence[str], None] = '5285bd395643'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("account", sa.Column("credit_balance", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("account", sa.Column("credit_rate", sa.Float(), nullable=False, server_default="1.5"))
    op.create_table(
        "credit_ledger",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=True),
        sa.Column("job_key", sa.String(), nullable=True),
        sa.Column("raw_cost_usd", sa.Float(), nullable=True),
        sa.Column("meta", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
    )
    op.create_index("ix_credit_ledger_profile_id", "credit_ledger", ["profile_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_credit_ledger_profile_id", table_name="credit_ledger")
    op.drop_table("credit_ledger")
    op.drop_column("account", "credit_rate")
    op.drop_column("account", "credit_balance")
