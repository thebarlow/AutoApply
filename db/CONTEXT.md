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

Each migration function in `database.py` is idempotent (checks `PRAGMA table_info` before altering).

| Column(s) | Table | Type | Migration fn |
|-----------|-------|------|--------------|
| `extraction_json` (renamed from `extraction_md`) | `jobs` | TEXT | — (manual, 2026-05-08) |
| `ext_salary_min`, `ext_salary_max` | `jobs` | REAL | — (manual, 2026-05-26) |
| `name` | `user_profile` | TEXT | `_migrate_profile_name` |
| `named_providers`, `latex_templates` | `config` (key-value rows) | — | `_migrate_legacy_config` |
| `ext_seniority`, `ext_role_type`, `ext_domain`, `ext_work_arrangement`, `ext_employment_type`, `ext_required_skills`, `ext_preferred_skills`, `ext_tech_stack`, `ext_key_responsibilities`, `ext_company_signals` | `jobs` | TEXT | `_migrate_ext_columns` |
| `unread_indicator`, `last_result_error` | `jobs` | TEXT | `_migrate_unread_indicator_columns` |
| `pending_review_actions` | `jobs` | TEXT (JSON list) | `_migrate_pending_review_actions` |
| `resume_generated_at`, `cover_generated_at` | `jobs` | TEXT | `_migrate_generated_at_columns` |
| `flagged` | `jobs` | BOOLEAN (default 0) | `_migrate_flagged_column` |
| `resume_eval_score`, `resume_eval_turns`, `resume_eval_log`, `cover_eval_score`, `cover_eval_turns`, `cover_eval_log` | `jobs` | REAL/INTEGER/TEXT | `_migrate_resume_eval_columns` |
