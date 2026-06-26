"""One-time backfill: seed default output formats into stored profile trees.

New profiles get the defaults from the section presets. Existing profiles carry
a persisted ``profile_tree`` whose prose fields predate output formats; this
script fills those (splitting Experience bullet-strings into arrays) in place.

Idempotent and non-destructive: only fields with no ``output_format`` on the
known preset roles are touched. TAKE A DB BACKUP FIRST. Run from the project root:

    python -m scripts.backfill_output_formats
"""

from __future__ import annotations

import json

from core.profile_tree import RootNode, backfill_output_formats
from core.user import User
from db.database import SessionLocal


def run() -> int:
    """Backfill every stored profile tree. Returns the count of rows changed."""
    db = SessionLocal()
    changed = 0
    try:
        for row in db.query(User).all():
            data = json.loads(row.data) if row.data else {}
            tree_raw = data.get("profile_tree")
            if not tree_raw:
                continue
            root = RootNode.model_validate(tree_raw)
            if backfill_output_formats(root):
                data["profile_tree"] = root.model_dump(mode="json")
                row.data = json.dumps(data)
                changed += 1
                print(f"  profile {row.id} ({row.name}): output formats seeded")
        if changed:
            db.commit()
    finally:
        db.close()
    return changed


if __name__ == "__main__":
    n = run()
    print(f"Backfill complete: {n} profile(s) updated.")
