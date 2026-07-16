"""redenominate credit balances to units (÷20) + tier grant top-up

Revision ID: aa10units01
Revises: aa09rmprompts01
Create Date: 2026-07-16

Converts old 1000-credits-per-dollar balances to $0.02 units (old ÷ 20),
writing a 'redenomination' ledger row per account for the delta. Accounts that
never completed a purchase and land below their tier's new signup grant
(standard 20 / friends_family 50 / beta 200 — frozen here on purpose) are
topped up with a 'redenomination_topup' row.
"""
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "aa10units01"
down_revision: Union[str, Sequence[str], None] = "aa09rmprompts01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_GRANTS = {"standard": 20, "friends_family": 50, "beta": 200}


def upgrade() -> None:
    bind = op.get_bind()
    now = datetime.now(timezone.utc).isoformat()
    accounts = bind.execute(sa.text(
        "SELECT profile_id, credit_balance, tier, is_admin FROM account"
    )).fetchall()
    for profile_id, old, tier, is_admin in accounts:
        old = old or 0
        new = round(old / 20)
        if new != old:
            bind.execute(sa.text(
                "INSERT INTO credit_ledger (profile_id, delta, reason, created_at) "
                "VALUES (:p, :d, 'redenomination', :t)"
            ), {"p": profile_id, "d": new - old, "t": now})
        purchased = bind.execute(sa.text(
            "SELECT COUNT(*) FROM purchase WHERE profile_id = :p AND status = 'completed'"
        ), {"p": profile_id}).scalar() or 0
        grant = _GRANTS.get(tier or "standard", _GRANTS["standard"])
        if not is_admin and purchased == 0 and new < grant:
            bind.execute(sa.text(
                "INSERT INTO credit_ledger (profile_id, delta, reason, created_at) "
                "VALUES (:p, :d, 'redenomination_topup', :t)"
            ), {"p": profile_id, "d": grant - new, "t": now})
            new = grant
        bind.execute(sa.text(
            "UPDATE account SET credit_balance = :b WHERE profile_id = :p"
        ), {"b": new, "p": profile_id})


def downgrade() -> None:
    # One-way by design: the pre-conversion balances are recoverable from the
    # 'redenomination'/'redenomination_topup' ledger rows if ever needed.
    pass
