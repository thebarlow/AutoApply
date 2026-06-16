"""add allowed_email.tier and allowed_email.is_admin (invite-time user type)

Revision ID: aa05invitetype01
Revises: aa04bans01
Create Date: 2026-06-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "aa05invitetype01"
down_revision: Union[str, Sequence[str], None] = "aa04bans01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("allowed_email",
                  sa.Column("tier", sa.String(), nullable=False,
                            server_default="standard"))
    op.add_column("allowed_email",
                  sa.Column("is_admin", sa.Boolean(), nullable=False,
                            server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("allowed_email", "is_admin")
    op.drop_column("allowed_email", "tier")
