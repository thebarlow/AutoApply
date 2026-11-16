import json

import pytest

from workflows import merge_utils


@pytest.fixture(autouse=True)
def _isolate_backup_root(tmp_path, monkeypatch):
    """Point the backup root at a temp dir so tests don't touch the real backups/."""
    monkeypatch.setattr(merge_utils, "_BACKUP_ROOT", tmp_path / "backups")


def test_merge_job_entry_preserves_other_keys(tmp_path):
    """Regression test for the REPLACE_ME incident: merging one job's entry
    must leave every other job's entry byte-identical."""
    path = tmp_path / "resumes.json"
    original = {
        "job_a": {"summary": "original a"},
        "job_b": {"summary": "original b"},
    }
    path.write_text(json.dumps(original, indent=2), encoding="utf-8")

    merge_utils.merge_job_entry(path, "job_a", {"summary": "patched a"})

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["job_a"] == {"summary": "patched a"}
    assert data["job_b"] == original["job_b"]


def test_write_json_backs_up_previous_content(tmp_path):
    path = tmp_path / "resumes.json"
    original = {"job_a": {"summary": "original"}}
    merge_utils.write_json(path, original)

    merge_utils.write_json(path, {"job_a": {"summary": "changed"}})

    backups = list(merge_utils._BACKUP_ROOT.glob("resumes.*.json"))
    assert len(backups) == 1
    assert json.loads(backups[0].read_text(encoding="utf-8")) == original


def test_write_json_no_backup_on_first_write(tmp_path):
    path = tmp_path / "resumes.json"
    merge_utils.write_json(path, {"job_a": {"summary": "first"}})

    assert not merge_utils._BACKUP_ROOT.exists() or not list(
        merge_utils._BACKUP_ROOT.glob("*.json")
    )


def test_validate_entry_rejects_empty_value(tmp_path):
    path = tmp_path / "resumes.json"
    with pytest.raises(merge_utils.MergeValidationError):
        merge_utils.merge_job_entry(path, "job_a", {})


def test_validate_entry_rejects_non_dict_value(tmp_path):
    path = tmp_path / "resumes.json"
    with pytest.raises(merge_utils.MergeValidationError):
        merge_utils.merge_job_entry(path, "job_a", "not-a-dict")  # type: ignore[arg-type]


def test_validate_entry_rejects_job_key_mismatch(tmp_path):
    path = tmp_path / "resumes.json"
    with pytest.raises(merge_utils.MergeValidationError):
        merge_utils.merge_job_entry(path, "job_a", {"job_key": "job_b", "summary": "x"})


def test_validate_entry_allows_missing_job_key_field(tmp_path):
    """Legacy-shaped payloads with no self-identifying job_key still pass."""
    path = tmp_path / "resumes.json"
    result = merge_utils.merge_job_entry(path, "job_a", {"summary": "x"})
    assert result == {"summary": "x"}


def test_validate_entry_allows_matching_job_key_field(tmp_path):
    path = tmp_path / "resumes.json"
    result = merge_utils.merge_job_entry(
        path, "job_a", {"job_key": "job_a", "summary": "x"}
    )
    assert result == {"job_key": "job_a", "summary": "x"}


def test_merge_job_entries_validates_before_any_write(tmp_path):
    """A bad entry anywhere in the batch must fail before mutating the file."""
    path = tmp_path / "resumes.json"
    original = {"job_a": {"summary": "original a"}}
    path.write_text(json.dumps(original), encoding="utf-8")

    with pytest.raises(merge_utils.MergeValidationError):
        merge_utils.merge_job_entries(
            path,
            {
                "job_a": {"summary": "patched a"},
                "job_b": {},  # invalid — empty dict
            },
        )

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data == original
