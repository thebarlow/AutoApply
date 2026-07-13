"""purge legacy global prompt-picker keys (audit S1 follow-up)

Revision ID: aa09rmprompts01
Revises: aa08profcfg01
Create Date: 2026-07-13 00:00:00.000000

The removed /api/config/prompts/* CRUD endpoints stored prompt content and LaTeX
template pointers in the GLOBAL ``config`` table with no tenant scoping. The
endpoints are gone (audit S1); this deletes the rows they left behind so they
can't be read or leaked. Live generation reads per-tenant prompts from the
``prompts`` table, and per-tenant template paths live in ``profile_config`` — both
are untouched here (this only deletes from the global ``config`` table).

Irreversible data cleanup: ``downgrade`` is a no-op (the rows were dead).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'aa09rmprompts01'
down_revision: Union[str, Sequence[str], None] = 'aa08profcfg01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_STALE_GLOBAL_KEYS = [
    "resume_prompts", "cover_prompts", "description_prompts",
    "active_resume_prompt_id", "active_cover_prompt_id", "active_description_prompt_id",
    "resume_prompt_template", "cover_prompt_template", "description_prompt_template",
    "latex_templates",
]


def upgrade() -> None:
    """Delete the stale global prompt-picker rows from the config table."""
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM config WHERE key IN :keys").bindparams(
            sa.bindparam("keys", value=tuple(_STALE_GLOBAL_KEYS), expanding=True)
        )
    )


def downgrade() -> None:
    """No-op: the deleted rows were dead legacy data with nothing to restore."""
    pass
