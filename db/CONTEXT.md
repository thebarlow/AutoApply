# db/ Context

## Schema Management

SQLAlchemy's `create_all` only creates tables that don't already exist — it does **not** add new columns to existing tables. When a new column is added to a model, the live `auto_apply.db` must be migrated manually:

```bash
python -c "
import sqlite3
conn = sqlite3.connect('auto_apply.db')
conn.execute('ALTER TABLE jobs ADD COLUMN <column_name> <TYPE>')
conn.commit()
conn.close()
"
```

### Migration history

| Column | Table | Type | Added |
|--------|-------|------|-------|
| `extraction_md` | `jobs` | TEXT | 2026-05-08 |
| `extraction_json` (renamed from `extraction_md`) | `jobs` | TEXT | 2026-05-08 |
