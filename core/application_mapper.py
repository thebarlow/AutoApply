"""Build an ApplicationPlan from a job, profile, documents, and enumerated fields.

Pure orchestration over the taxonomy (application_fields), classifier
(application_classify), and static schemas (ats_schemas). No LLM here: free-text
essay drafting is injected via ``draft_essays`` so this module stays
unit-testable and the metering decision lives at the endpoint.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from core.application_classify import classify_custom, is_eeo_label, match_eligibility
from core.application_fields import (
    CANONICAL_FIELDS,
    ResolveContext,
    resolve_canonical,
)
from core.ats_schemas import schema_for
from core.schemas import ApplicationPlan, EnumeratedField, PlannedField

EssayDrafter = Callable[[list[tuple[str, str]]], dict[str, str]]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _status_for(value: str | None, kind: str) -> str:
    if value:
        return "filled"
    if kind in ("deterministic", "eligibility", "eeo"):
        return "blank"
    return "unknown"


def _plan_static_field(field, ctx: ResolveContext) -> PlannedField:
    value = resolve_canonical(field.canonical_key, ctx)
    kind = CANONICAL_FIELDS[field.canonical_key].kind
    return PlannedField(
        field_id=field.field_id,
        label=field.label,
        canonical_key=field.canonical_key,
        value=value,
        status=_status_for(value, kind),
        source="static_schema",
    )


def needs_essay_pass(job: Any, enumerated_fields: list[EnumeratedField] | None) -> bool:
    """True if any enumerated custom field routes to the essay bucket."""
    for f in enumerated_fields or []:
        if _canonical_for_enumerated(f) is not None:
            continue
        if classify_custom(f.label) == "essay":
            return True
    return False


def _canonical_for_enumerated(f: EnumeratedField) -> str | None:
    """Map an enumerated field to a canonical key by id/label, or None.

    Deliberately conservative: exact-key match on field_id, else None (custom).
    """
    if f.field_id in CANONICAL_FIELDS:
        return f.field_id
    return None


def build_plan(
    job: Any,
    user: Any,
    documents: dict[str, str],
    enumerated_fields: list[EnumeratedField] | None = None,
    draft_essays: EssayDrafter | None = None,
) -> ApplicationPlan:
    """Compute the field→value plan for a job's application form."""
    answers = getattr(user, "application_answers", {}) or {}
    ctx = ResolveContext(user=user, documents=documents, job=job, answers=answers)

    planned: list[PlannedField] = []
    seen_ids: set[str] = set()

    # 1. Static schema for the ATS.
    for sf in schema_for(getattr(job, "ats_type", None)):
        planned.append(_plan_static_field(sf, ctx))
        seen_ids.add(sf.field_id)

    # 2. Merge dynamically-enumerated fields.
    essay_pending: list[tuple[str, str]] = []
    essay_slots: dict[str, PlannedField] = {}
    for ef in enumerated_fields or []:
        if ef.field_id in seen_ids:
            continue
        seen_ids.add(ef.field_id)
        canon = _canonical_for_enumerated(ef)
        if canon is not None:
            value = resolve_canonical(canon, ctx)
            planned.append(
                PlannedField(
                    field_id=ef.field_id,
                    label=ef.label,
                    canonical_key=canon,
                    value=value,
                    status=_status_for(value, CANONICAL_FIELDS[canon].kind),
                    source="enumerated_canonical",
                )
            )
            continue

        # Custom field: EEO guard first, then eligibility, then essay.
        if is_eeo_label(ef.label):
            value = (
                resolve_canonical(_eeo_key_for(ef.label), ctx)
                if _eeo_key_for(ef.label)
                else None
            )
            planned.append(
                PlannedField(
                    field_id=ef.field_id,
                    label=ef.label,
                    canonical_key=_eeo_key_for(ef.label),
                    value=value,
                    status=_status_for(value, "eeo"),
                    source="eeo",
                )
            )
            continue
        elig = match_eligibility(ef.label)
        if elig is not None:
            value = resolve_canonical(elig, ctx)
            planned.append(
                PlannedField(
                    field_id=ef.field_id,
                    label=ef.label,
                    canonical_key=elig,
                    value=value,
                    status=_status_for(value, "eligibility"),
                    source="eligibility",
                )
            )
            continue
        # Essay.
        pf = PlannedField(
            field_id=ef.field_id,
            label=ef.label,
            canonical_key=None,
            value=None,
            status="unknown",
            source="essay",
        )
        planned.append(pf)
        essay_slots[ef.field_id] = pf
        essay_pending.append((ef.field_id, ef.label))

    # 3. Essay pass (injected drafter only; EEO fields are already excluded).
    if essay_pending and draft_essays is not None:
        drafts = draft_essays(essay_pending) or {}
        for fid, answer in drafts.items():
            slot = essay_slots.get(fid)
            if slot is not None and answer:
                slot.value = answer
                slot.status = "drafted"

    return ApplicationPlan(
        job_key=getattr(job, "job_key", ""),
        ats_type=getattr(job, "ats_type", None),
        fields=planned,
        generated_at=_now(),
    )


def _eeo_key_for(label: str) -> str | None:
    """Map an EEO label to a canonical eeo_* key, or None if only guarded."""
    text = (label or "").lower()
    if "gender" in text or "sex" in text:
        return "eeo_gender"
    if "race" in text or "ethnic" in text or "hispanic" in text or "latino" in text:
        return "eeo_race"
    if "veteran" in text:
        return "eeo_veteran"
    if "disab" in text:
        return "eeo_disability"
    return None
