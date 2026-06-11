"""Centralized on-disk data paths, rooted at an optional ``DATA_DIR`` env var.

Local dev leaves ``DATA_DIR`` unset, so paths resolve to the repo root exactly
as before. Hosted (Railway) sets ``DATA_DIR=/data`` (a mounted volume) so
generated documents and uploaded files survive redeploys.
"""
from __future__ import annotations

import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    """Return the base data directory: ``$DATA_DIR`` if set, else the repo root."""
    val = os.getenv("DATA_DIR")
    return Path(val) if val else _REPO_ROOT


OUTPUTS_DIR = data_dir() / "generator" / "outputs"
PROFILES_DIR = data_dir() / "profiles"

OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
PROFILES_DIR.mkdir(parents=True, exist_ok=True)
