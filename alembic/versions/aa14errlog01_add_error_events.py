"""add error_events

Revision ID: aa14errlog01
Revises: aa13applyplan01
Create Date: 2026-07-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "aa14errlog01"
down_revision: Union[str, Sequence[str], None] = "aa13applyplan01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "error_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("last_seen", sa.String(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("level", sa.String(), nullable=False),
        sa.Column("logger", sa.String(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("traceback", sa.Text(), nullable=True),
        sa.Column("route", sa.String(), nullable=True),
        sa.Column("profile_id", sa.Integer(), nullable=True),
        sa.Column("request_id", sa.String(), nullable=True),
        sa.Column("fingerprint", sa.String(), nullable=False),
    )
    op.create_index("ix_error_events_fingerprint", "error_events", ["fingerprint"])
    op.create_index("ix_error_events_created_at", "error_events", ["created_at"])
    op.create_index("ix_error_events_last_seen", "error_events", ["last_seen"])


def downgrade() -> None:
    op.drop_index("ix_error_events_last_seen", table_name="error_events")
    op.drop_index("ix_error_events_created_at", table_name="error_events")
    op.drop_index("ix_error_events_fingerprint", table_name="error_events")
    op.drop_table("error_events")
