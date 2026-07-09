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

_MOVED_KEYS = [
    "w1", "w2", "auto_reject_threshold", "auto_approve_threshold",
    "resume_github", "resume_linkedin", "resume_website",
    "resume_template_path", "cover_template_path",
    "resume_prompt_template", "cover_prompt_template",
    "source_remotive", "source_remoteok",
    "keywords_whitelist", "keywords_blacklist",
    "max_jobs_per_source", "job_searches",
]


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'profile_config',
        sa.Column('profile_id', sa.Integer(), nullable=False),
        sa.Column('key', sa.String(), nullable=False),
        sa.Column('value', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('profile_id', 'key'),
    )

    conn = op.get_bind()
    profile_ids = [r[0] for r in conn.execute(sa.text("SELECT id FROM user_profile")).all()]
    for key in _MOVED_KEYS:
        row = conn.execute(
            sa.text("SELECT value FROM config WHERE key = :k"), {"k": key}
        ).first()
        if row is None:
            continue
        value = row[0]
        for pid in profile_ids:
            conn.execute(
                sa.text(
                    "INSERT INTO profile_config (profile_id, key, value) "
                    "VALUES (:pid, :k, :v)"
                ),
                {"pid": pid, "k": key, "v": value},
            )
        conn.execute(sa.text("DELETE FROM config WHERE key = :k"), {"k": key})


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    for key in _MOVED_KEYS:
        row = conn.execute(
            sa.text("SELECT value FROM profile_config WHERE key = :k AND profile_id = 1"),
            {"k": key},
        ).first()
        if row is not None:
            conn.execute(
                sa.text("INSERT INTO config (key, value) VALUES (:k, :v)"),
                {"k": key, "v": row[0]},
            )
    op.drop_table('profile_config')
