"""add application_plan column to jobs

Revision ID: aa13applyplan01
Revises: aa12atsdetect01
Create Date: 2026-07-20
"""

from alembic import op
import sqlalchemy as sa

revision = "aa13applyplan01"
down_revision = "aa12atsdetect01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("application_plan", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "application_plan")
