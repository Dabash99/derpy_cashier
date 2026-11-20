"""resource_path() must resolve correctly both from source and from a
PyInstaller-frozen build (sys.frozen=True, one-dir)."""
from __future__ import annotations

from pathlib import Path

from derby.core.utils import resource_path as rp


def test_project_root_from_source_is_the_real_project_root():
    root = rp.project_root()
    assert (root / "derby" / "__init__.py").exists()
    assert (root / "assets").exists()


def test_resource_path_joins_onto_project_root():
    path = rp.resource_path("assets", "fonts", "Cairo-Regular.ttf")
    assert path == rp.project_root() / "assets" / "fonts" / "Cairo-Regular.ttf"
    assert path.exists()


def test_project_root_when_frozen_resolves_next_to_the_executable(monkeypatch, tmp_path):
    fake_exe = tmp_path / "dist" / "Derby" / "Derby.exe"
    fake_exe.parent.mkdir(parents=True)
    fake_exe.write_text("", encoding="utf-8")

    monkeypatch.setattr(rp.sys, "frozen", True, raising=False)
    monkeypatch.setattr(rp.sys, "executable", str(fake_exe))

    assert rp.project_root() == Path(fake_exe).resolve().parent
