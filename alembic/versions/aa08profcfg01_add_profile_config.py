"""add profile_config table

Revision ID: aa08profcfg01
Revises: 866e48bc6219
Create Date: 2026-07-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'aa08profcfg01'
down_revision: Union[str, Sequence[str], None] = '866e48bc6219'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'profile_config',
        sa.Column('profile_id', sa.Integer(), nullable=False),
        sa.Column('key', sa.String(), nullable=False),
        sa.Column('value', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('profile_id', 'key'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('profile_config')
