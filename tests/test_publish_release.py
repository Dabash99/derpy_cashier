"""tools/publish_release.py talks to git/gh only through subprocess --
every test here mocks publish_release._run (or monkeypatches its
module-level directory constants) so nothing ever touches a real git
remote or GitHub. See CLAUDE.md: no real network in tests.
"""
from __future__ import annotations

import importlib.util
import json
import types
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("publish_release", PROJECT_ROOT / "tools" / "publish_release.py")
publish_release = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(publish_release)

VALID_SHA256 = "a" * 64


def _fake_completed(returncode=0, stdout="", stderr=""):
    return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------


def test_merge_history_prepends_new_entry():
    history = [{"version": "1.0.0", "date": "2026-01-01", "notes": "first"}]
    merged = publish_release.merge_history(history, {"version": "1.0.1", "date": "2026-02-01", "notes": "second"})

    assert [item["version"] for item in merged] == ["1.0.1", "1.0.0"]


def test_merge_history_replaces_same_version_instead_of_duplicating():
    history = [{"version": "1.0.0", "date": "2026-01-01", "notes": "first try"}]
    merged = publish_release.merge_history(history, {"version": "1.0.0", "date": "2026-01-02", "notes": "retry"})

    assert len(merged) == 1
    assert merged[0]["notes"] == "retry"


def test_build_readme_text_includes_download_link_sha256_and_history_rows():
    history = [
        {"version": "1.0.1", "date": "2026-02-01", "notes": "فيه تحسينات"},
        {"version": "1.0.0", "date": "2026-01-01", "notes": "أول إصدار"},
    ]
    text = publish_release.build_readme_text(
        history, download_url="https://github.com/a/b/Derby-Setup-1.0.1.exe", sha256=VALID_SHA256
    )

    assert "https://github.com/a/b/Derby-Setup-1.0.1.exe" in text
    assert VALID_SHA256 in text
    assert "1.0.1" in text and "1.0.0" in text
    assert "فيه تحسينات" in text and "أول إصدار" in text
    assert "SmartScreen" in text
    assert "Windows 7" in text


def test_build_readme_text_requires_at_least_one_history_entry():
    with pytest.raises(ValueError):
        publish_release.build_readme_text([], download_url="https://x", sha256=VALID_SHA256)


def test_load_history_returns_empty_list_when_file_missing(tmp_path):
    assert publish_release.load_history(tmp_path) == []


def test_load_history_reads_existing_file(tmp_path):
    history = [{"version": "1.0.0", "date": "2026-01-01", "notes": "x"}]
    (tmp_path / publish_release.HISTORY_FILE_NAME).write_text(json.dumps(history), encoding="utf-8")

    assert publish_release.load_history(tmp_path) == history


# ---------------------------------------------------------------------------
# Preconditions
# ---------------------------------------------------------------------------


def _write_release_fixture(tmp_path, monkeypatch, *, version="1.0.0", sha256=None, matching_version=None):
    release_dir = tmp_path / "release"
    public_dir = release_dir / "public"
    public_dir.mkdir(parents=True)

    installer_path = release_dir / "Derby-Setup-{0}.exe".format(version)
    installer_path.write_bytes(b"fake installer bytes")
    real_sha256 = publish_release._sha256_of(installer_path)

    (release_dir / "SHA256SUMS.txt").write_text("{0}  {1}\n".format(real_sha256, installer_path.name))

    manifest = {
        "version": matching_version if matching_version is not None else version,
        "notes": "test notes",
        "download_url": "https://github.com/a/b/Derby-Setup-{0}.exe".format(version),
        "sha256": sha256 if sha256 is not None else real_sha256,
    }
    (public_dir / "version.json").write_text(json.dumps(manifest), encoding="utf-8")
    (public_dir / "README.md").write_text("# Derby releases\n", encoding="utf-8")

    monkeypatch.setattr(publish_release, "RELEASE_DIR", release_dir)
    monkeypatch.setattr(publish_release, "PUBLIC_DIR", public_dir)
    return manifest


def test_check_preconditions_passes_with_matching_files(tmp_path, monkeypatch):
    manifest = _write_release_fixture(tmp_path, monkeypatch)
    # gh --version and gh auth status must succeed; the tag-existence check must fail (tag absent).
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        if args[:2] == ["gh", "release"]:
            return _fake_completed(returncode=1)  # release does not exist yet
        return _fake_completed(returncode=0)

    monkeypatch.setattr(publish_release, "_run", fake_run)

    result = publish_release.check_preconditions("1.0.0")
    assert result["version"] == "1.0.0"
    assert result == manifest


def test_check_preconditions_rejects_missing_installer(tmp_path, monkeypatch):
    release_dir = tmp_path / "release"
    (release_dir / "public").mkdir(parents=True)
    monkeypatch.setattr(publish_release, "RELEASE_DIR", release_dir)
    monkeypatch.setattr(publish_release, "PUBLIC_DIR", release_dir / "public")

    with pytest.raises(publish_release.PublishError, match="المثبّت"):
        publish_release.check_preconditions("1.0.0")


def test_check_preconditions_rejects_version_mismatch(tmp_path, monkeypatch):
    _write_release_fixture(tmp_path, monkeypatch, version="1.0.0", matching_version="0.9.9")

    with pytest.raises(publish_release.PublishError, match="رقم الإصدار"):
        publish_release.check_preconditions("1.0.0")


def test_check_preconditions_rejects_sha256_mismatch(tmp_path, monkeypatch):
    _write_release_fixture(tmp_path, monkeypatch, sha256="b" * 64)

    with pytest.raises(publish_release.PublishError, match="SHA-256"):
        publish_release.check_preconditions("1.0.0")


def test_check_preconditions_rejects_dirty_public_folder(tmp_path, monkeypatch):
    manifest = _write_release_fixture(tmp_path, monkeypatch)
    (tmp_path / "release" / "public" / "menu.csv").write_text("x", encoding="utf-8")
    monkeypatch.setattr(publish_release, "_run", lambda *a, **k: _fake_completed(returncode=0))

    with pytest.raises(publish_release.PublishError, match="الخصوصية"):
        publish_release.check_preconditions(manifest["version"])


def test_check_preconditions_rejects_when_gh_missing(tmp_path, monkeypatch):
    _write_release_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(publish_release, "_run", lambda *a, **k: _fake_completed(returncode=1))

    with pytest.raises(publish_release.PublishError, match="gh"):
        publish_release.check_preconditions("1.0.0")


def test_check_preconditions_rejects_when_gh_not_logged_in(tmp_path, monkeypatch):
    _write_release_fixture(tmp_path, monkeypatch)

    def fake_run(args, **kwargs):
        if args[:2] == ["gh", "--version"]:
            return _fake_completed(returncode=0)
        return _fake_completed(returncode=1)  # gh auth status fails

    monkeypatch.setattr(publish_release, "_run", fake_run)

    with pytest.raises(publish_release.PublishError, match="تسجّل الدخول"):
        publish_release.check_preconditions("1.0.0")


def test_check_preconditions_refuses_to_overwrite_an_existing_tag(tmp_path, monkeypatch):
    _write_release_fixture(tmp_path, monkeypatch)

    def fake_run(args, **kwargs):
        if args[:2] == ["gh", "release"]:
            return _fake_completed(returncode=0)  # release already exists
        return _fake_completed(returncode=0)

    monkeypatch.setattr(publish_release, "_run", fake_run)

    with pytest.raises(publish_release.PublishError, match="موجود بالفعل"):
        publish_release.check_preconditions("1.0.0")


# ---------------------------------------------------------------------------
# Idempotent commit/push
# ---------------------------------------------------------------------------


def test_commit_and_push_skips_when_nothing_changed(tmp_path, monkeypatch):
    monkeypatch.setattr(publish_release, "CLONE_DIR", tmp_path)
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        if args[-1] == "--porcelain":
            return _fake_completed(returncode=0, stdout="")
        return _fake_completed(returncode=0)

    monkeypatch.setattr(publish_release, "_run", fake_run)
    publish_release.commit_and_push_if_needed("1.0.0")

    assert not any(args[2:3] == ["commit"] for args in calls)
    assert not any("push" in args for args in calls)


def test_commit_and_push_commits_and_pushes_when_dirty(tmp_path, monkeypatch):
    monkeypatch.setattr(publish_release, "CLONE_DIR", tmp_path)
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        if args[-1] == "--porcelain":
            return _fake_completed(returncode=0, stdout=" M version.json\n")
        return _fake_completed(returncode=0)

    monkeypatch.setattr(publish_release, "_run", fake_run)
    publish_release.commit_and_push_if_needed("1.0.0")

    assert any("commit" in args for args in calls)
    assert any("push" in args for args in calls)


# ---------------------------------------------------------------------------
# Orphan "releases" branch handling
# ---------------------------------------------------------------------------


def test_clear_working_tree_except_git_removes_everything_but_dot_git(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("x", encoding="utf-8")
    (tmp_path / "derby").mkdir()
    (tmp_path / "derby" / "app.py").write_text("x", encoding="utf-8")
    (tmp_path / "README.md").write_text("x", encoding="utf-8")

    publish_release._clear_working_tree_except_git(tmp_path)

    remaining = {p.name for p in tmp_path.iterdir()}
    assert remaining == {".git"}
    assert (tmp_path / ".git" / "config").exists()


def test_ensure_releases_branch_checked_out_uses_existing_local_branch(tmp_path, monkeypatch):
    monkeypatch.setattr(publish_release, "CLONE_DIR", tmp_path)
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        if "show-ref" in args:
            return _fake_completed(returncode=0)  # local branch exists
        if "ls-remote" in args:
            return _fake_completed(returncode=0)  # remote branch exists too
        return _fake_completed(returncode=0)

    monkeypatch.setattr(publish_release, "_run", fake_run)
    publish_release._ensure_releases_branch_checked_out()

    assert any(args[3:5] == ["checkout", "releases"] for args in calls)
    assert any("pull" in args for args in calls)
    assert not any("--orphan" in args for args in calls)
    assert not any(args[3:5] == ["checkout", "-b"] for args in calls)


def test_ensure_releases_branch_checked_out_tracks_existing_remote_branch(tmp_path, monkeypatch):
    monkeypatch.setattr(publish_release, "CLONE_DIR", tmp_path)
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        if "show-ref" in args:
            return _fake_completed(returncode=1)  # no local branch yet
        if "ls-remote" in args:
            return _fake_completed(returncode=0)  # but remote has it
        return _fake_completed(returncode=0)

    monkeypatch.setattr(publish_release, "_run", fake_run)
    publish_release._ensure_releases_branch_checked_out()

    assert any(args[3:6] == ["checkout", "-b", "releases"] for args in calls)
    assert not any("--orphan" in args for args in calls)


def test_ensure_releases_branch_checked_out_creates_orphan_branch_when_neither_exists(tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()
    (tmp_path / "some_source_file.py").write_text("stale content", encoding="utf-8")
    monkeypatch.setattr(publish_release, "CLONE_DIR", tmp_path)
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        if "show-ref" in args:
            return _fake_completed(returncode=1)  # no local branch
        if "ls-remote" in args:
            return _fake_completed(returncode=1)  # no remote branch either
        return _fake_completed(returncode=0)

    monkeypatch.setattr(publish_release, "_run", fake_run)
    publish_release._ensure_releases_branch_checked_out()

    assert any("--orphan" in args for args in calls)
    # The stale file left over from whatever branch this was orphaned
    # from must be gone -- only .git remains.
    assert {p.name for p in tmp_path.iterdir()} == {".git"}
