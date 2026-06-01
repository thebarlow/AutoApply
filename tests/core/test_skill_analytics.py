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
