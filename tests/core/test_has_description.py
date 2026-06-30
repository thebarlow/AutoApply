"""Unit tests for Job.has_description()."""
from core.job import Job


def _job(description):
    j = Job.__new__(Job)  # bypass __init__; conftest configures mappers
    j.description = description
    return j


def test_has_description_true_for_content():
    assert _job("Senior Python role, remote.").has_description() is True


def test_has_description_false_for_none():
    assert _job(None).has_description() is False


def test_has_description_false_for_empty():
    assert _job("").has_description() is False


def test_has_description_false_for_whitespace():
    assert _job("   \n\t  ").has_description() is False
