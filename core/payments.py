"""Credit-pack config: env-driven price_id -> credits map (no Stripe calls)."""
from __future__ import annotations

import json
import os


def load_packs() -> dict[str, int]:
    """Parse STRIPE_PACKS (JSON map of price_id -> credit amount). {} if unset."""
    raw = os.getenv("STRIPE_PACKS", "").strip()
    if not raw:
        return {}
    return {str(k): int(v) for k, v in json.loads(raw).items()}


def credits_for_price(price_id: str) -> int | None:
    """Credits granted by a price_id, or None if it is not a configured pack."""
    return load_packs().get(price_id)
