import pytest
from pathlib import Path
from core.utils import strip_header_block


def test_strip_header_block_removes_yaml_frontmatter():
    md = "---\nname: foo\n---\n## Experience\n- did things"
    assert strip_header_block(md) == "## Experience\n- did things"


def test_strip_header_block_no_frontmatter_returns_from_first_section():
    md = "Some intro text\n## Experience\n- did things"
    assert strip_header_block(md) == "## Experience\n- did things"


def test_strip_header_block_already_starts_with_section():
    md = "## Experience\n- did things"
    assert strip_header_block(md) == md


def test_strip_header_block_empty_string():
    assert strip_header_block("") == ""
