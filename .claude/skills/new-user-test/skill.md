---
name: new-user-test
description: Use when testing the new-user onboarding experience in the auto-apply project — simulates a fresh install with no database or config by overriding DATABASE_URL before server start, then cleans up after.
---

# New-User Test Environment

Spin up a clean-slate environment to test the new-user onboarding flow without touching the real database.

## How It Works

`load_dotenv()` in `db/database.py` does **not** override existing env vars. Setting `DATABASE_URL` in the shell before launching the server takes precedence over `.env`.

## Session Lifecycle

**Start:** Run setup commands below, then work on dashboard changes normally.

**End:** When the user says they're done testing (e.g. "done", "end test session", "clean up"), run the cleanup commands. Do not clean up mid-session unless asked.

## Setup

```powershell
# 0. Start from a clean slate — a stale test DB from a prior run silently skips
#    onboarding (it already has a profile). Back it up rather than delete.
if (Test-Path C:\Users\barlo\Projects\auto_apply\test_new_user.db) {
    $ts = Get-Date -Format "yyyyMMdd-HHmmss"
    Move-Item C:\Users\barlo\Projects\auto_apply\test_new_user.db* `
      ("C:\Users\barlo\Projects\auto_apply\test_new_user.db.stale-$ts") -Force
}

# 1. Override the database
$env:DATABASE_URL = "sqlite:///test_new_user.db"

# 2. Activate venv
C:\Users\barlo\Projects\auto_apply\.venv\Scripts\Activate.ps1

# 3. Start API server in background (port 8080)
Start-Process cmd -ArgumentList '/k', 'uvicorn web.main:app --host 0.0.0.0 --port 8080 --reload'

# 4. Start React dev server (port 5173, enables hot reload for dashboard changes)
Start-Process cmd -ArgumentList '/k', 'cd react-dashboard && npm run dev'
```

A fresh `test_new_user.db` is created on first request — no existing users, profiles, or config.

Dashboard is available at http://localhost:5173.

## Cleanup

Run when the user signals the test session is over.

```powershell
# Delete test database
Remove-Item C:\Users\barlo\Projects\auto_apply\test_new_user.db -ErrorAction SilentlyContinue

# Unset the env override
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
```

Then delete orphaned profile files — any file in `profiles/` not referenced by the real database:

```powershell
python -c "
import sqlite3, os
from pathlib import Path

con = sqlite3.connect('auto_apply.db')
rows = con.execute(\"SELECT data FROM user_profile\").fetchall()
con.close()

import json
referenced = set()
for (data,) in rows:
    d = json.loads(data)
    for key in ('md_path', 'resume_path', 'cover_letter_path'):
        path = d.get(key, '')
        if path:
            referenced.add(Path(path).name)

profiles_dir = Path('profiles')
deleted = []
for f in profiles_dir.iterdir():
    if f.name not in referenced:
        f.unlink()
        deleted.append(f.name)

print(f'Deleted {len(deleted)} orphaned profile file(s)')
"
```

Also close the two server console windows manually (Auto Apply Server, React dev server).

## Notes

- The real `auto_apply.db` is never touched.
- No `.env` changes needed.
- All onboarding data (config, profile) lands in `test_new_user.db` and is wiped on cleanup.
- Any profile files written to `profiles/` during the test are deleted on cleanup (cross-referenced against the real DB).
- To test with a blank `.env` (no API keys), copy `.env` to `.env.bak`, clear relevant keys, restore after.
