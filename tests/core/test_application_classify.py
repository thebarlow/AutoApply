import pytest

from core.application_classify import classify_custom, is_eeo_label, match_eligibility

EEO_LABELS = [
    "Race / Ethnicity",
    "What is your gender?",
    "Gender identity",
    "Are you a protected veteran?",
    "Veteran status",
    "Disability status",
    "Do you have a disability?",
    "Hispanic or Latino?",
    "Sexual orientation",
]


@pytest.mark.parametrize("label", EEO_LABELS)
def test_eeo_guard_catches_demographic_labels(label):
    assert is_eeo_label(label) is True
    assert classify_custom(label) == "eeo"  # guard wins, never essay


@pytest.mark.parametrize(
    "label",
    [
        "Why do you want to work here?",
        "Tell us about a challenging project",
        "First name",
        "Email address",
    ],
)
def test_eeo_guard_ignores_non_demographic(label):
    assert is_eeo_label(label) is False


def test_eligibility_matching():
    assert (
        match_eligibility("Are you authorized to work in the US?") == "work_authorized"
    )
    assert (
        match_eligibility("Will you now or in the future require sponsorship?")
        == "requires_sponsorship"
    )
    assert match_eligibility("Are you willing to relocate?") == "willing_to_relocate"
    assert match_eligibility("Earliest start date") == "start_date"
    assert match_eligibility("Years of experience with Python") == "years_experience"
    assert match_eligibility("Why this company?") is None


def test_classify_routes_essay_as_fallback():
    assert classify_custom("Describe your ideal work environment") == "essay"
    assert classify_custom("Are you authorized to work in the US?") == "eligibility"
