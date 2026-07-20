"""Canonical application-form field taxonomy and value resolvers.

Pure, no LLM, no network. Maps a stable canonical key (e.g. ``first_name``,
``work_authorized``, ``eeo_gender``) to how its value is produced from the user
profile, generated documents, and stored application answers. Consumed by
``core/application_mapper.py``.
"""
from __future__ import annotations

import dataclasses
from typing import Any, Callable, Literal

FieldKind = Literal["deterministic", "eligibility", "eeo", "essay", "unknown"]


@dataclasses.dataclass
class ResolveContext:
    """Everything a resolver may read to produce a field value."""

    user: Any
    documents: dict[str, str]
    job: Any
    answers: dict[str, Any]


@dataclasses.dataclass
class CanonicalField:
    """A canonical form field and how to resolve its value."""

    key: str
    kind: FieldKind
    resolve: Callable[[ResolveContext], str | None]


def _u(attr: str) -> Callable[[ResolveContext], str | None]:
    def r(ctx: ResolveContext) -> str | None:
        val = getattr(ctx.user, attr, "") or ""
        return val or None
    return r


def _full_name(ctx: ResolveContext) -> str | None:
    fn = getattr(ctx.user, "full_name", None)
    return (fn() if callable(fn) else None) or None


def _doc(key: str) -> Callable[[ResolveContext], str | None]:
    def r(ctx: ResolveContext) -> str | None:
        return ctx.documents.get(key) or None
    return r


def _answer(group: str, name: str) -> Callable[[ResolveContext], str | None]:
    def r(ctx: ResolveContext) -> str | None:
        val = (ctx.answers.get(group) or {}).get(name)
        return val or None
    return r


def _field(key: str, kind: FieldKind, resolve: Callable[[ResolveContext], str | None]) -> CanonicalField:
    return CanonicalField(key=key, kind=kind, resolve=resolve)


CANONICAL_FIELDS: dict[str, CanonicalField] = {
    f.key: f
    for f in [
        _field("first_name", "deterministic", _u("first_name")),
        _field("last_name", "deterministic", _u("last_name")),
        _field("full_name", "deterministic", _full_name),
        _field("email", "deterministic", _u("email")),
        _field("phone", "deterministic", _u("phone")),
        _field("linkedin_url", "deterministic", _u("linkedin")),
        _field("github_url", "deterministic", _u("github")),
        _field("portfolio_url", "deterministic", _u("website")),
        _field("location", "deterministic", _u("location")),
        _field("resume_file", "deterministic", _doc("resume_file")),
        _field("cover_letter_text", "deterministic", _doc("cover_letter_text")),
        _field("work_authorized", "eligibility", _answer("eligibility", "work_authorized")),
        _field("requires_sponsorship", "eligibility", _answer("eligibility", "requires_sponsorship")),
        _field("willing_to_relocate", "eligibility", _answer("eligibility", "willing_to_relocate")),
        _field("start_date", "eligibility", _answer("eligibility", "start_date")),
        _field("years_experience", "eligibility", _answer("eligibility", "years_experience")),
        _field("eeo_gender", "eeo", _answer("eeo", "gender")),
        _field("eeo_race", "eeo", _answer("eeo", "race_ethnicity")),
        _field("eeo_veteran", "eeo", _answer("eeo", "veteran_status")),
        _field("eeo_disability", "eeo", _answer("eeo", "disability_status")),
    ]
}


def resolve_canonical(key: str, ctx: ResolveContext) -> str | None:
    """Resolve a canonical field's value, or None if unknown/unset."""
    field = CANONICAL_FIELDS.get(key)
    if field is None:
        return None
    return field.resolve(ctx)
