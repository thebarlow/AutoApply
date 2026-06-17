"""Serve the browser extension as a downloadable .zip for load-unpacked install.

Hosted users have no repo checkout, so they can't load the extension from disk.
This zips the ``browser-extension/`` source on the fly (dev notes excluded) and
streams it; the Getting Started doc walks them through load-unpacked install.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

router = APIRouter(tags=["extension"])

_EXT_DIR = Path(__file__).parent.parent.parent / "browser-extension"
# Repo-only files that shouldn't ship to end users.
_EXCLUDE_NAMES = {"CONTEXT.md"}


@router.get("/extension/download")
def download_extension() -> StreamingResponse:
    if not _EXT_DIR.is_dir():
        raise HTTPException(status_code=404, detail="extension not available")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(_EXT_DIR.rglob("*")):
            if not path.is_file() or path.name in _EXCLUDE_NAMES:
                continue
            zf.write(path, path.relative_to(_EXT_DIR).as_posix())
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="autoapply-extension.zip"'},
    )
