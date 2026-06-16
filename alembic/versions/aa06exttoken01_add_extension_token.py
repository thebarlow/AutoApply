"""add extension_token

Revision ID: aa06exttoken01
Revises: aa05invitetype01
Create Date: 2026-06-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "aa06exttoken01"
down_revision: Union[str, Sequence[str], None] = "aa05invitetype01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "extension_token",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("account.id"), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("last_used_at", sa.String(), nullable=True),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_extension_token_token_hash", "extension_token", ["token_hash"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_extension_token_token_hash", table_name="extension_token")
    op.drop_table("extension_token")
