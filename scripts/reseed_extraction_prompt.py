"""One-off: refresh the active `extraction` prompt to the shipped default.

Updates the `prompt_defaults` seed row and each per-profile `prompts` row whose
content still matches a *previous* default (i.e. unedited by the user), so the
credential/title exclusion cleanup takes effect. User-customized extraction
prompts are left untouched. Prints what it changed.
"""
from __future__ import annotations

from pathlib import Path

from db.database import Prompt, PromptDefault, SessionLocal

_NEW = (
    Path(__file__).parent.parent / "prompts" / "defaults" / "extraction.md"
).read_text(encoding="utf-8")


def main() -> None:
    db = SessionLocal()
    try:
        default = db.query(PromptDefault).filter_by(type_key="extraction").first()
        old_default = default.content if default else None

        # Refresh the seed row.
        if default is None:
            db.add(PromptDefault(type_key="extraction", content=_NEW))
            print("prompt_defaults: inserted extraction")
        elif old_default != _NEW:
            default.content = _NEW
            print("prompt_defaults: updated extraction")
        else:
            print("prompt_defaults: already current")

        # Update per-profile active rows that still match the old default.
        rows = db.query(Prompt).filter_by(type_key="extraction").all()
        updated, skipped = [], []
        for r in rows:
            if r.content == _NEW:
                continue
            if old_default is None or r.content == old_default:
                r.content = _NEW
                updated.append(r.profile_id)
            else:
                skipped.append(r.profile_id)

        db.commit()
        print(f"prompts updated (matched old default): {updated}")
        print(f"prompts skipped (user-customized): {skipped}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
