# tests/core/test_education_split.py
"""Unit tests for the Education-injection split used by render_pdf.

Education from frontmatter must always be placed as the section immediately
after Profile, regardless of what the second section is named (Experience,
Projects, …) or whether an Experience section exists at all.
"""
from core.utils import _split_body_for_education


def _h2(name: str) -> str:
    return f"<h2>{name}</h2>\n<p>body of {name}</p>\n"


def test_splits_before_second_section_when_experience_present():
    fragment = _h2("Profile") + _h2("Experience") + _h2("Skills")
    pre, post = _split_body_for_education(fragment)
    assert "Profile" in pre and "Experience" not in pre
    assert post.startswith("<h2>Experience</h2>")


def test_splits_before_second_section_when_no_experience():
    # The StreetID case: Profile → Projects → Skills, no Experience section.
    fragment = _h2("Profile") + _h2("Projects") + _h2("Skills")
    pre, post = _split_body_for_education(fragment)
    assert "Profile" in pre and "Projects" not in pre
    assert post.startswith("<h2>Projects</h2>")


def test_strips_llm_education_section():
    fragment = _h2("Profile") + _h2("Education") + _h2("Experience")
    pre, post = _split_body_for_education(fragment)
    assert "Education" not in pre and "Education" not in post
    assert post.startswith("<h2>Experience</h2>")


def test_single_section_leaves_post_empty():
    fragment = _h2("Profile")
    pre, post = _split_body_for_education(fragment)
    assert "Profile" in pre
    assert post == ""
