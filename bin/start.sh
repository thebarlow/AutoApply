source .venv/bin/activate      # Windows: .venv\Scripts\activate

# Force polling instead of inotify — inotify hangs on WSL2 /mnt/c paths, causing
# 1-2 minute delays on Ctrl+C while the watcher drains pending Windows FS events.
WATCHFILES_FORCE_POLLING=true uvicorn web.main:app --reload --host 0.0.0.0 --port 8080
