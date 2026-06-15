"""add account.tier, purchase.tier; reset credit_rate margin to 1.0

Revision ID: aa02tiers01
Revises: aa01payments01
Create Date: 2026-06-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "aa02tiers01"
down_revision: Union[str, Sequence[str], None] = "aa01payments01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("account",
                  sa.Column("tier", sa.String(), nullable=False, server_default="standard"))
    op.add_column("purchase", sa.Column("tier", sa.String(), nullable=True))
    # Existing accounts are early users -> beta tier.
    op.execute("UPDATE account SET tier = 'beta'")
    # Margin moved to the purchase side; metered accounts created at the old 1.5
    # default must drop to 1.0 or they'd be charged margin twice. Admins (0.0) stay.
    op.execute("UPDATE account SET credit_rate = 1.0 WHERE credit_rate = 1.5")


def downgrade() -> None:
    op.drop_column("purchase", "tier")
    op.drop_column("account", "tier")
