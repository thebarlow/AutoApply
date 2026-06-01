from __future__ import annotations

from core.skill_analytics import normalize_skill, aggregate_skill_frequency


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


class TestAggregateSkillFrequency:
    def test_empty_input_returns_zeroed_structure(self):
        result = aggregate_skill_frequency([])
        assert result == {"skills": [], "tech_stack": [], "total_jobs": 0}

    def test_required_skill_counted(self):
        jobs = [_FakeJob(required="Python")]
        result = aggregate_skill_frequency(jobs)
        assert result["skills"] == [{"skill": "Python", "required": 1, "preferred": 0}]
        assert result["total_jobs"] == 1

    def test_required_wins_over_preferred_in_same_job(self):
        jobs = [_FakeJob(required="Python", preferred="Python")]
        result = aggregate_skill_frequency(jobs)
        assert result["skills"] == [{"skill": "Python", "required": 1, "preferred": 0}]

    def test_preferred_only_counted_separately(self):
        jobs = [
            _FakeJob(required="Python"),
            _FakeJob(preferred="Python"),
        ]
        result = aggregate_skill_frequency(jobs)
        assert result["skills"] == [{"skill": "Python", "required": 1, "preferred": 1}]

    def test_dedupes_within_job(self):
        jobs = [_FakeJob(required="Python, python")]
        result = aggregate_skill_frequency(jobs)
        assert result["skills"] == [{"skill": "Python", "required": 1, "preferred": 0}]

    def test_skills_sorted_by_total_desc_then_name(self):
        jobs = [
            _FakeJob(required="Python, React"),
            _FakeJob(required="Python", preferred="Go"),
            _FakeJob(preferred="Python"),
        ]
        result = aggregate_skill_frequency(jobs)
        totals = [row["required"] + row["preferred"] for row in result["skills"]]
        assert totals == sorted(totals, reverse=True)
        assert result["skills"][0] == {"skill": "Python", "required": 2, "preferred": 1}

    def test_tech_stack_counted_separately(self):
        jobs = [_FakeJob(required="Python", tech_stack="AWS, Docker")]
        result = aggregate_skill_frequency(jobs)
        assert result["skills"] == [{"skill": "Python", "required": 1, "preferred": 0}]
        tech = {row["skill"]: row["count"] for row in result["tech_stack"]}
        assert tech == {"AWS": 1, "Docker": 1}

    def test_total_jobs_counts_all_jobs(self):
        jobs = [_FakeJob(seniority="Senior"), _FakeJob(required="Python")]
        result = aggregate_skill_frequency(jobs)
        assert result["total_jobs"] == 2
        assert result["skills"] == [{"skill": "Python", "required": 1, "preferred": 0}]

    def test_junk_tokens_excluded(self):
        jobs = [_FakeJob(required="Python, , 3.x, ...")]
        result = aggregate_skill_frequency(jobs)
        assert result["skills"] == [{"skill": "Python", "required": 1, "preferred": 0}]
