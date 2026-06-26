"""Curated, ATS-safe résumé theme registry.

A theme names a self-contained résumé stylesheet. ``classic`` maps to the
existing ``generator/resume.css`` (the default; byte-identical to legacy);
``modern`` and ``compact`` live under ``generator/themes/``. ``css_filename``
is relative to the ``generator/`` directory.
"""
from __future__ import annotations

import dataclasses


@dataclasses.dataclass(frozen=True)
class Theme:
    """A selectable résumé theme.

    Attributes:
        id: Stable identifier stored on the profile and the rendered job row.
        label: Human-facing name shown in the picker.
        css_filename: Stylesheet path relative to the ``generator/`` directory.
    """

    id: str
    label: str
    css_filename: str


CLASSIC = Theme(id="classic", label="Classic", css_filename="resume.css")
MODERN = Theme(id="modern", label="Modern", css_filename="themes/resume_modern.css")
COMPACT = Theme(id="compact", label="Compact", css_filename="themes/resume_compact.css")

THEMES: list[Theme] = [CLASSIC, MODERN, COMPACT]
DEFAULT_THEME_ID = "classic"

_BY_ID = {t.id: t for t in THEMES}


def get_theme(theme_id: str) -> Theme | None:
    """Return the theme with ``theme_id``, or ``None`` if unknown."""
    return _BY_ID.get(theme_id)


def all_themes() -> list[Theme]:
    """Return the themes in display order."""
    return list(THEMES)


def resolve_theme(theme_id: str | None) -> Theme:
    """Return the named theme, falling back to ``CLASSIC`` for None/""/unknown."""
    if not theme_id:
        return CLASSIC
    return _BY_ID.get(theme_id, CLASSIC)
