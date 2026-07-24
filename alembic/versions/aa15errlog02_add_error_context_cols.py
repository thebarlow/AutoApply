"""add method and account_email to error_events

Revision ID: aa15errlog02
Revises: aa14errlog01
Create Date: 2026-07-24
"""
from alembic import op
import sqlalchemy as sa

revision = "aa15errlog02"
down_revision = "aa14errlog01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add nullable ``method`` and ``account_email`` columns to ``error_events``."""
    op.add_column("error_events", sa.Column("method", sa.String(), nullable=True))
    op.add_column(
        "error_events", sa.Column("account_email", sa.String(), nullable=True)
    )


def downgrade() -> None:
    """Drop ``method`` and ``account_email`` from ``error_events``."""
    op.drop_column("error_events", "account_email")
    op.drop_column("error_events", "method")
