"""add allowed_email table (runtime invite allowlist)

Revision ID: aa03invites01
Revises: aa02tiers01
Create Date: 2026-06-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "aa03invites01"
down_revision: Union[str, Sequence[str], None] = "aa02tiers01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "allowed_email",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(), nullable=False, unique=True),
        sa.Column("invited_by", sa.Integer(), sa.ForeignKey("account.id"), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("allowed_email")
