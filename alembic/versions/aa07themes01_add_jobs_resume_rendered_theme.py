"""add jobs.resume_rendered_theme

Revision ID: aa07themes01
Revises: aa06exttoken01
Create Date: 2026-06-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "aa07themes01"
down_revision: Union[str, Sequence[str], None] = "aa06exttoken01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("resume_rendered_theme", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "resume_rendered_theme")
