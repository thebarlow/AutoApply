"""One-time backfill: seed default section prompts into stored profile trees.

New profiles get the role-keyed defaults from the section factories. Existing
profiles already carry a persisted ``profile_tree`` (with blank section prompts),
which the factories never touch — this script fills those blanks in place.

Idempotent and non-destructive: only blank section prompts on known roles are
filled; user-authored prompts are preserved. Run from the project root:

    python -m scripts.backfill_section_prompts
"""

from __future__ import annotations

import json

from core.profile_tree import RootNode, backfill_section_prompts
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
                continue  # no persisted tree → factory defaults apply on next load
            root = RootNode.model_validate(tree_raw)
            if backfill_section_prompts(root):
                data["profile_tree"] = root.model_dump(mode="json")
                row.data = json.dumps(data)
                changed += 1
                print(f"  profile {row.id} ({row.name}): section prompts seeded")
        if changed:
            db.commit()
    finally:
        db.close()
    return changed


if __name__ == "__main__":
    n = run()
    print(f"Backfill complete: {n} profile(s) updated.")
