"""One-time setup script: create tables and seed default config."""
from db.database import init_db, SessionLocal
from db.seed import seed_default_config

if __name__ == "__main__":
    init_db()
    db = SessionLocal()
    try:
        seed_default_config(db)
        print("Database initialised and default config seeded.")
    finally:
        db.close()
