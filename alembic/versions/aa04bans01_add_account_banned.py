"""add account.banned

Revision ID: aa04bans01
Revises: aa03invites01
Create Date: 2026-06-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "aa04bans01"
down_revision: Union[str, Sequence[str], None] = "aa03invites01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("account",
                  sa.Column("banned", sa.Boolean(), nullable=False,
                            server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("account", "banned")
