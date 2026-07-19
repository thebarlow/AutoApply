"""add ats detection columns to jobs

Revision ID: aa12atsdetect01
Revises: aa11extract01
Create Date: 2026-07-19
"""
from alembic import op
import sqlalchemy as sa

revision = "aa12atsdetect01"
down_revision = "aa11extract01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("easy_apply", sa.Boolean(), nullable=True))
    op.add_column("jobs", sa.Column("apply_url_raw", sa.String(), nullable=True))
    op.add_column("jobs", sa.Column("apply_url_resolved", sa.String(), nullable=True))
    op.add_column("jobs", sa.Column("ats_type", sa.String(), nullable=True))
    op.add_column("jobs", sa.Column("ats_domain", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "ats_domain")
    op.drop_column("jobs", "ats_type")
    op.drop_column("jobs", "apply_url_resolved")
    op.drop_column("jobs", "apply_url_raw")
    op.drop_column("jobs", "easy_apply")
