from types import SimpleNamespace

from core.application_fields import (
    CANONICAL_FIELDS,
    ResolveContext,
    resolve_canonical,
)


def _ctx(**over):
    user = SimpleNamespace(
        first_name="Ada",
        last_name="Lovelace",
        email="ada@example.com",
        phone="555-0100",
        linkedin="https://linkedin.com/in/ada",
        github="https://github.com/ada",
        website="",
        location="London",
        application_answers=over.pop("answers", {}),
    )
    user.full_name = lambda: "Ada Lovelace"
    return ResolveContext(
        user=user,
        documents=over.pop(
            "documents", {"resume_file": "/tmp/r.pdf", "cover_letter_text": "Dear"}
        ),
        job=SimpleNamespace(company="Acme"),
        answers=user.application_answers,
    )


def test_deterministic_fields_resolve_from_user():
    ctx = _ctx()
    assert resolve_canonical("first_name", ctx) == "Ada"
    assert resolve_canonical("full_name", ctx) == "Ada Lovelace"
    assert resolve_canonical("email", ctx) == "ada@example.com"
    assert resolve_canonical("linkedin_url", ctx) == "https://linkedin.com/in/ada"
    assert resolve_canonical("resume_file", ctx) == "/tmp/r.pdf"
    assert resolve_canonical("cover_letter_text", ctx) == "Dear"


def test_eligibility_resolves_from_answers_or_none():
    ctx = _ctx(answers={"eligibility": {"work_authorized": "yes"}})
    assert resolve_canonical("work_authorized", ctx) == "yes"
    assert resolve_canonical("requires_sponsorship", ctx) is None  # unset → None


def test_eeo_resolves_from_answers_or_none():
    ctx = _ctx(answers={"eeo": {"gender": "Decline to self-identify"}})
    assert resolve_canonical("eeo_gender", ctx) == "Decline to self-identify"
    assert resolve_canonical("eeo_veteran", ctx) is None


def test_field_kinds_are_declared():
    assert CANONICAL_FIELDS["first_name"].kind == "deterministic"
    assert CANONICAL_FIELDS["work_authorized"].kind == "eligibility"
    assert CANONICAL_FIELDS["eeo_gender"].kind == "eeo"
