from types import SimpleNamespace

from core.application_mapper import build_plan, needs_essay_pass
from core.schemas import EnumeratedField


def _user(answers=None):
    u = SimpleNamespace(
        first_name="Ada",
        last_name="Lovelace",
        email="ada@x.com",
        phone="",
        linkedin="https://li/ada",
        github="",
        website="",
        location="London",
        application_answers=answers or {"eligibility": {}, "eeo": {}},
    )
    u.full_name = lambda: "Ada Lovelace"
    return u


def _job(ats="greenhouse"):
    return SimpleNamespace(job_key="j1", ats_type=ats, company="Acme")


DOCS = {"resume_file": "/tmp/r.pdf", "cover_letter_text": "Dear Acme"}


def test_static_schema_fields_are_filled_or_blank():
    plan = build_plan(_job(), _user(), DOCS)
    by_key = {f.canonical_key: f for f in plan.fields}
    assert by_key["email"].value == "ada@x.com" and by_key["email"].status == "filled"
    assert by_key["phone"].status == "blank"  # empty profile phone
    assert by_key["resume_file"].value == "/tmp/r.pdf"


def test_eeo_enumerated_field_never_drafted():
    fields = [EnumeratedField(field_id="q_gender", label="What is your gender?")]
    called = {"n": 0}

    def drafter(pairs):
        called["n"] += 1
        return {fid: "SHOULD NOT HAPPEN" for fid, _ in pairs}

    plan = build_plan(
        _job("other"), _user(), DOCS, enumerated_fields=fields, draft_essays=drafter
    )
    gender = next(f for f in plan.fields if f.field_id == "q_gender")
    assert gender.status == "blank"  # no stored eeo answer
    assert gender.value is None
    assert called["n"] == 0  # EEO guard kept it out of the drafter entirely


def test_objective_custom_resolves_from_answers():
    fields = [
        EnumeratedField(
            field_id="q_auth", label="Are you authorized to work in the US?"
        )
    ]
    user = _user({"eligibility": {"work_authorized": "Yes"}, "eeo": {}})
    plan = build_plan(_job("other"), user, DOCS, enumerated_fields=fields)
    q = next(f for f in plan.fields if f.field_id == "q_auth")
    assert q.value == "Yes" and q.status == "filled"


def test_essay_field_uses_injected_drafter():
    fields = [EnumeratedField(field_id="q_why", label="Why do you want to work here?")]
    plan = build_plan(
        _job("other"),
        _user(),
        DOCS,
        enumerated_fields=fields,
        draft_essays=lambda pairs: {fid: "Because..." for fid, _ in pairs},
    )
    q = next(f for f in plan.fields if f.field_id == "q_why")
    assert q.value == "Because..." and q.status == "drafted"


def test_needs_essay_pass_detection():
    assert (
        needs_essay_pass(
            _job("other"), [EnumeratedField(field_id="q", label="Why us?")]
        )
        is True
    )
    assert (
        needs_essay_pass(_job("other"), [EnumeratedField(field_id="g", label="Gender")])
        is False
    )
    assert needs_essay_pass(_job("greenhouse"), None) is False


def test_needs_essay_pass_skips_static_schema_field_ids():
    # An enumerated field whose id collides with a greenhouse static-schema field
    # is skipped by build_plan (seen_ids), so needs_essay_pass must not count it —
    # otherwise map_fields would be billed for an essay pass that never runs.
    collide = [EnumeratedField(field_id="cover_letter", label="Why do you want this job?")]
    assert needs_essay_pass(_job("greenhouse"), collide) is False
    # Same label on a non-colliding id still triggers the pass.
    fresh = [EnumeratedField(field_id="q_custom", label="Why do you want this job?")]
    assert needs_essay_pass(_job("greenhouse"), fresh) is True
