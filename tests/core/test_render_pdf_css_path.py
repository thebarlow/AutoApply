from pathlib import Path

import core.utils as utils


class _FakeBrowserCtx:
    def __enter__(self):
        return _FakeP()

    def __exit__(self, *a):
        return False


class _FakeP:
    @property
    def chromium(self):
        return self

    def launch(self, *a, **k):
        return self

    def new_page(self, *a, **k):
        return self

    def set_content(self, *a, **k):
        pass

    def pdf(self, *a, **k):
        path = Path(k.get("path"))
        path.write_bytes(b"%PDF-1.4 fake")

    def emulate_media(self, *a, **k):
        pass

    def close(self, *a, **k):
        pass


def _stub_pipeline(monkeypatch, captured):
    """Patch pandoc + Playwright so render_pdf runs without external tools."""
    monkeypatch.setattr(
        utils.subprocess,
        "run",
        lambda *a, **k: type("R", (), {"stdout": "<p>body</p>"})(),
    )

    class _FakeEnv:
        def __init__(self, *a, **k):
            self.filters = {}

        def from_string(self, _tpl):
            class _T:
                def render(self, **kw):
                    captured["css"] = kw.get("css", "")
                    return "<html></html>"

            return _T()

    monkeypatch.setattr(utils, "Environment", _FakeEnv)
    monkeypatch.setattr(utils, "sync_playwright", lambda: _FakeBrowserCtx())


def test_css_path_override_is_inlined(tmp_path, monkeypatch):
    captured = {}
    _stub_pipeline(monkeypatch, captured)
    md = tmp_path / "r.md"
    md.write_text("hello", encoding="utf-8")
    css = tmp_path / "custom.css"
    css.write_text(".x{color:red}", encoding="utf-8")
    tpl = tmp_path / "resume_template.html"
    tpl.write_text("{{ css }}{{ content_html }}", encoding="utf-8")
    utils.render_pdf(md, tmp_path / "out.pdf", tpl, css_path=css)
    assert captured["css"] == ".x{color:red}"


def test_css_path_none_derives_from_template_stem(tmp_path, monkeypatch):
    captured = {}
    _stub_pipeline(monkeypatch, captured)
    md = tmp_path / "r.md"
    md.write_text("hello", encoding="utf-8")
    (tmp_path / "resume.css").write_text(".stem{color:blue}", encoding="utf-8")
    tpl = tmp_path / "resume_template.html"
    tpl.write_text("{{ css }}{{ content_html }}", encoding="utf-8")
    utils.render_pdf(md, tmp_path / "out.pdf", tpl, css_path=None)
    assert captured["css"] == ".stem{color:blue}"
