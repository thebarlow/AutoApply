from __future__ import annotations

from sqlalchemy.orm import Session

from db.models import Config

DEFAULT_CONFIG: dict[str, str] = {
    "w1": "0.5",
    "w2": "0.5",
    "auto_reject_threshold": "0.3",
    "auto_approve_threshold": "0.8",
    "keywords_whitelist": "[]",
    "keywords_blacklist": "[]",
    "location": "",
    "remote_only": "true",
    "full_time_only": "true",
    "target_salary_min": "0",
    "benefits_priorities": "[]",
}


def seed_default_config(db: Session) -> None:
    """Insert default config entries if they do not already exist."""
    for key, value in DEFAULT_CONFIG.items():
        if not db.query(Config).filter_by(key=key).first():
            db.add(Config(key=key, value=value))
    db.commit()
