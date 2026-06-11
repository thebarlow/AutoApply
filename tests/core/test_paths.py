import importlib
from pathlib import Path

import core.paths as paths


def test_data_dir_defaults_to_repo_root(monkeypatch):
    monkeypatch.delenv("DATA_DIR", raising=False)
    # repo root is the parent of the core/ package dir
    expected = Path(paths.__file__).resolve().parent.parent
    assert paths.data_dir() == expected


def test_data_dir_uses_env_when_set(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    assert paths.data_dir() == tmp_path


def test_outputs_and_profiles_under_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    importlib.reload(paths)
    try:
        assert paths.OUTPUTS_DIR == tmp_path / "generator" / "outputs"
        assert paths.PROFILES_DIR == tmp_path / "profiles"
        assert paths.OUTPUTS_DIR.is_dir()   # created at import
        assert paths.PROFILES_DIR.is_dir()
    finally:
        monkeypatch.delenv("DATA_DIR", raising=False)
        importlib.reload(paths)  # restore default module state for other tests
