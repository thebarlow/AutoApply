from __future__ import annotations

from core.skill_analytics import (
    normalize_skill,
    aggregate_skill_frequency,
    job_has_skill,
    tech_category,
    skill_key,
)


class TestNormalizeSkill:
    def test_case_folding_and_canonical_display(self):
        assert normalize_skill("PYTHON") == "Python"
        assert normalize_skill("python") == "Python"

    def test_trims_whitespace(self):
        assert normalize_skill("  React  ") == "React"

    def test_alias_mapping(self):
        assert normalize_skill("js") == "JavaScript"
        assert normalize_skill("k8s") == "Kubernetes"
        assert normalize_skill("react.js") == "React"

    def test_strips_version_tokens(self):
        assert normalize_skill("Python 3.11") == "Python"
        assert normalize_skill("Vue v2") == "Vue"
        assert normalize_skill("Java 17") == "Java"

    def test_empty_or_whitespace_returns_none(self):
        assert normalize_skill("") is None
        assert normalize_skill("   ") is None

    def test_junk_after_stripping_returns_none(self):
        assert normalize_skill("...") is None
        assert normalize_skill("3.x") is None

    def test_unknown_skill_passes_through_titlecased(self):
        # Multi-word unknown skill keeps each word capitalized.
        assert normalize_skill("machine learning") == "Machine Learning"

    def test_all_caps_acronym_preserved(self):
        assert normalize_skill("AWS") == "AWS"
        assert normalize_skill("GCP") == "GCP"

    def test_mixed_case_skills_canonicalized(self):
        assert normalize_skill("graphql") == "GraphQL"
        assert normalize_skill("ios") == "iOS"


class _FakeJob:
    """Minimal stand-in exposing the extraction attributes used by aggregation."""

    def __init__(self, required="", preferred="", tech_stack="", seniority=""):
        self.ext_required_skills = required
        self.ext_preferred_skills = preferred
        self.ext_tech_stack = tech_stack
        self.ext_seniority = seniority


class TestTechCategory:
    def test_known_skills_map_to_category(self):
        assert tech_category("Python") == "Languages"
        assert tech_category("React") == "Frontend"
        assert tech_category("AWS") == "Cloud"
        assert tech_category("Docker") == "DevOps"
        assert tech_category("PostgreSQL") == "Databases"

    def test_case_insensitive(self):
        assert tech_category("python") == "Languages"
        assert tech_category("PYTHON") == "Languages"

    def test_unknown_skill_is_other(self):
        assert tech_category("Wizardry") == "Other"


class TestAggregateSkillFrequency:
    def test_empty_input(self):
        assert aggregate_skill_frequency([]) == {
            "skills": [], "categories": [], "total_jobs": 0,
        }

    def test_required_is_high(self):
        result = aggregate_skill_frequency([_FakeJob(required="Python")])
        assert result["skills"] == [
            {"key": "python", "skill": "Python", "high": 1, "med": 0, "low": 0, "category": "Languages"}
        ]
        assert result["total_jobs"] == 1

    def test_preferred_is_med(self):
        result = aggregate_skill_frequency([_FakeJob(preferred="React")])
        assert result["skills"] == [
            {"key": "react", "skill": "React", "high": 0, "med": 1, "low": 0, "category": "Frontend"}
        ]

    def test_tech_stack_only_is_low(self):
        result = aggregate_skill_frequency([_FakeJob(tech_stack="Docker")])
        assert result["skills"] == [
            {"key": "docker", "skill": "Docker", "high": 0, "med": 0, "low": 1, "category": "DevOps"}
        ]

    def test_required_wins_over_preferred_and_tech(self):
        result = aggregate_skill_frequency(
            [_FakeJob(required="Python", preferred="Python", tech_stack="Python")]
        )
        assert result["skills"] == [
            {"key": "python", "skill": "Python", "high": 1, "med": 0, "low": 0, "category": "Languages"}
        ]
        assert result["total_jobs"] == 1

    def test_preferred_wins_over_tech_stack(self):
        result = aggregate_skill_frequency(
            [_FakeJob(preferred="React", tech_stack="React")]
        )
        assert result["skills"] == [
            {"key": "react", "skill": "React", "high": 0, "med": 1, "low": 0, "category": "Frontend"}
        ]

    def test_tiers_accumulate_across_jobs(self):
        jobs = [
            _FakeJob(required="Python"),
            _FakeJob(preferred="Python"),
            _FakeJob(tech_stack="Python"),
        ]
        row = aggregate_skill_frequency(jobs)["skills"][0]
        assert row["skill"] == "Python"
        assert (row["high"], row["med"], row["low"]) == (1, 1, 1)

    def test_skills_sorted_by_total_desc_then_name(self):
        jobs = [_FakeJob(required="Python, React"), _FakeJob(required="Python")]
        result = aggregate_skill_frequency(jobs)
        assert [r["skill"] for r in result["skills"]] == ["Python", "React"]

    def test_categories_count_distinct_jobs(self):
        result = aggregate_skill_frequency(
            [_FakeJob(required="React, Vue", tech_stack="AWS")]
        )
        cats = {c["category"]: c["count"] for c in result["categories"]}
        assert cats == {"Frontend": 1, "Cloud": 1}

    def test_dedupes_within_field(self):
        result = aggregate_skill_frequency([_FakeJob(required="Python, python")])
        assert result["skills"] == [
            {"key": "python", "skill": "Python", "high": 1, "med": 0, "low": 0, "category": "Languages"}
        ]

    def test_unknown_skill_categorized_as_other(self):
        result = aggregate_skill_frequency([_FakeJob(required="Wizardry")])
        cats = {c["category"]: c["count"] for c in result["categories"]}
        assert cats == {"Other": 1}


class TestJobHasSkill:
    def test_matches_required_field(self):
        job = _FakeJob(required="Python, React")
        assert job_has_skill(job, "Python") is True

    def test_matches_preferred_field(self):
        job = _FakeJob(preferred="Docker")
        assert job_has_skill(job, "Docker") is True

    def test_matches_tech_stack_field(self):
        job = _FakeJob(tech_stack="AWS")
        assert job_has_skill(job, "AWS") is True

    def test_matches_via_normalization_alias(self):
        # Raw "k8s" in the job must match canonical "Kubernetes".
        job = _FakeJob(tech_stack="k8s")
        assert job_has_skill(job, "Kubernetes") is True

    def test_no_match_returns_false(self):
        job = _FakeJob(required="Python")
        assert job_has_skill(job, "Go") is False

    def test_empty_fields_return_false(self):
        job = _FakeJob()
        assert job_has_skill(job, "Python") is False


class _J:
    def __init__(self, req="", pref="", tech=""):
        self.ext_required_skills = req
        self.ext_preferred_skills = pref
        self.ext_tech_stack = tech


def test_skill_key_folds_case():
    assert skill_key("FASTAPI") == skill_key("FastAPI") == "fastapi"


def test_skill_key_applies_alias():
    aliases = {"js": "JavaScript", "javascript": "JavaScript"}
    assert skill_key("JS", aliases) == "javascript"
    assert skill_key("javascript", aliases) == "javascript"


def test_aggregate_merges_case_variants_with_frequent_display():
    jobs = [_J(req="FastAPI"), _J(req="FastAPI"), _J(req="FASTAPI")]
    result = aggregate_skill_frequency(jobs)
    rows = {r["key"]: r for r in result["skills"]}
    assert set(rows) == {"fastapi"}
    row = rows["fastapi"]
    assert row["high"] == 3
    assert row["skill"] == "FastAPI"


def test_aggregate_uses_alias_canonical_for_display():
    jobs = [_J(req="js"), _J(req="JavaScript")]
    aliases = {"js": "JavaScript", "javascript": "JavaScript"}
    result = aggregate_skill_frequency(jobs, aliases=aliases)
    rows = {r["key"]: r for r in result["skills"]}
    assert set(rows) == {"javascript"}
    assert rows["javascript"]["skill"] == "JavaScript"
    assert rows["javascript"]["high"] == 2


def test_job_has_skill_is_case_insensitive():
    assert job_has_skill(_J(req="FASTAPI"), "FastAPI") is True
    assert job_has_skill(_J(req="Python"), "Rust") is False
