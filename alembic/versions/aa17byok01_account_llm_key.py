"""add bring-your-own-key LLM columns to account

Revision ID: aa17byok01
Revises: aa16errdedup01
Create Date: 2026-11-16
"""
from alembic import op
import sqlalchemy as sa

revision = "aa17byok01"
down_revision = "aa16errdedup01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add nullable BYOK columns (provider, encrypted key, last4, default model)."""
    op.add_column("account", sa.Column("llm_provider", sa.String(), nullable=True))
    op.add_column("account", sa.Column("llm_api_key_enc", sa.Text(), nullable=True))
    op.add_column("account", sa.Column("llm_key_last4", sa.String(), nullable=True))
    op.add_column("account", sa.Column("llm_default_model", sa.String(), nullable=True))


def downgrade() -> None:
    """Drop the BYOK columns."""
    with op.batch_alter_table("account") as batch:
        batch.drop_column("llm_default_model")
        batch.drop_column("llm_key_last4")
        batch.drop_column("llm_api_key_enc")
        batch.drop_column("llm_provider")
