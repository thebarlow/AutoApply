"""Shared-file merge primitives for workflows/ scripts.

Exists specifically so a dispatched subagent never performs read-modify-write
on a multi-job JSON file (resumes.json, compared.json, ats_reports.json, ...).
A subagent once wrote a literal "REPLACE_ME" placeholder over an untouched
job's entry in resumes.json while patching a different job, because it didn't
actually read the full file first — full data loss for that job (recovered
only because the content was still visible earlier in the conversation).

The convention going forward: a subagent writes its result for ONE job to a
scratch file (`scratch_path`) via the Write tool, with no knowledge of any
other job's data at all. A separate, deterministic call to `merge_job_entry`/
`merge_job_entries` then splices that single result into the real shared
file. The subagent structurally cannot clobber another job's entry, because
it never has the shared file open.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

_SCRATCH_DIR = Path("workflows/output/_scratch")
_BACKUP_ROOT = Path("backups/workflows")


class MergeValidationError(ValueError):
    """Raised when a value being merged into a shared JSON file is malformed."""


def read_json(path: Path, default: dict | None = None) -> dict:
    """Read a JSON file, returning `default` (or {}) if it doesn't exist."""
    if not path.exists():
        return {} if default is None else default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    """Write `data` to `path`, backing up any existing content first.

    The backup is the actual safety net for this module: it protects
    against `merge_utils.py` itself writing bad data (a caller bug, a
    malformed scratch file), which subagent-isolation alone can't catch.
    """
    if path.exists():
        _BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        shutil.copy2(path, _BACKUP_ROOT / f"{path.stem}.{stamp}{path.suffix}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _validate_entry(job_key: str, value: dict) -> None:
    if not isinstance(value, dict) or not value:
        raise MergeValidationError(
            f"merge_job_entry({job_key!r}): value must be a non-empty dict, got {value!r}"
        )
    declared = value.get("job_key")
    if declared is not None and declared != job_key:
        raise MergeValidationError(
            f"merge_job_entry({job_key!r}): payload declares job_key={declared!r} — mismatch"
        )


def merge_job_entry(path: Path, job_key: str, value: dict) -> dict:
    """Read `path` (dict keyed by job_key), set data[job_key] = value, write back.

    Creates the file (starting from {}) if it doesn't exist yet. This is the
    only sanctioned way to write a single job's result into a multi-job file.

    Args:
        path: Path to the shared JSON file.
        job_key: Which key to set.
        value: The new value for that key.

    Returns:
        The value that was written (for convenience/chaining).
    """
    _validate_entry(job_key, value)
    data = read_json(path)
    data[job_key] = value
    write_json(path, data)
    return value


def merge_job_entries(path: Path, values: dict[str, dict]) -> dict:
    """Same as merge_job_entry, for updating several job_keys in one call."""
    for k, v in values.items():
        _validate_entry(k, v)
    data = read_json(path)
    data.update(values)
    write_json(path, data)
    return data


def scratch_path(job_key: str, suffix: str) -> Path:
    """Path a subagent should Write its single-job output to, e.g.

    scratch_path("linkedin_123", "eval_semantic") ->
        workflows/output/_scratch/linkedin_123_eval_semantic.json

    Dispatch instructions should ask the subagent to include a top-level
    "job_key" field in the written payload matching the job it was told to
    work on — merge_job_entry cross-checks it against the caller's job_key
    when present, catching a mislabeled scratch file before it's merged.
    """
    _SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    return _SCRATCH_DIR / f"{job_key}_{suffix}.json"
