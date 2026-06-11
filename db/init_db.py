"""One-time setup script: create tables and seed default config."""
import sys

from sqlalchemy.exc import OperationalError

from db.database import init_db, SessionLocal
from db.seed import seed_default_config, seed_field_help, seed_user_profile_field_help, seed_skill_aliases

if __name__ == "__main__":
    try:
        init_db()
    except OperationalError as e:
        print(f"[init_db] Failed to create tables: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[init_db] Unexpected error during table creation: {e}", file=sys.stderr)
        sys.exit(1)

    db = SessionLocal()
    try:
        seed_default_config(db)
        seed_field_help(db)
        seed_user_profile_field_help(db)
        seed_skill_aliases(db)
        print("Database initialised and default config seeded.")
    except OperationalError as e:
        print(f"[init_db] Failed to seed config: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[init_db] Unexpected error during config seeding: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()
