"""The one-time 1.0.0 -> 1.1.0 cache clear: must fire exactly once for
that specific transition, never again on any later update, and never
touch .venv/.git/build/dist or anything outside the project root.
"""
from __future__ import annotations

from derby.core.utils.startup_cache import TARGET_VERSION, clear_cache_once_after_1_0_0_upgrade, marker_path


def _make_pycache(root, *parts):
    pycache_dir = root.joinpath(*parts, "__pycache__")
    pycache_dir.mkdir(parents=True, exist_ok=True)
    (pycache_dir / "mod.cpython-38.pyc").write_text("x")
    return pycache_dir


def test_clears_on_first_launch_of_the_new_version_with_no_marker(tmp_path):
    pycache = _make_pycache(tmp_path, "derby")
    loose_pyc = tmp_path / "tools" / "stray.pyc"
    loose_pyc.parent.mkdir(parents=True, exist_ok=True)
    loose_pyc.write_text("x")
    (tmp_path / ".pytest_cache").mkdir()
    (tmp_path / ".ruff_cache").mkdir()

    cleared = clear_cache_once_after_1_0_0_upgrade(root=tmp_path, current_version=TARGET_VERSION)

    assert cleared is True
    assert not pycache.exists()
    assert not loose_pyc.exists()
    assert not (tmp_path / ".pytest_cache").exists()
    assert not (tmp_path / ".ruff_cache").exists()
    assert marker_path(tmp_path).exists()
    assert marker_path(tmp_path).read_text(encoding="utf-8") == TARGET_VERSION


def test_skips_silently_when_marker_already_exists(tmp_path):
    pycache = _make_pycache(tmp_path, "derby")
    marker_path(tmp_path).write_text("1.1.0", encoding="utf-8")

    cleared = clear_cache_once_after_1_0_0_upgrade(root=tmp_path, current_version=TARGET_VERSION)

    assert cleared is False
    assert pycache.exists()  # never touched -- marker already present


def test_never_fires_for_a_later_version_even_without_a_marker(tmp_path):
    """Simulates a hypothetical 1.2.0 release that somehow lost its
    marker -- TARGET_VERSION is hardcoded to 1.1.0, so this must still
    be a no-op, not a second clear."""
    pycache = _make_pycache(tmp_path, "derby")

    cleared = clear_cache_once_after_1_0_0_upgrade(root=tmp_path, current_version="1.2.0")

    assert cleared is False
    assert pycache.exists()
    assert not marker_path(tmp_path).exists()


def test_fresh_install_of_the_new_version_is_harmless_with_no_caches_present(tmp_path):
    """A brand-new install of 1.1.0 (never ran 1.0.0) has nothing to
    clear -- must still write the marker without erroring."""
    cleared = clear_cache_once_after_1_0_0_upgrade(root=tmp_path, current_version=TARGET_VERSION)
    assert cleared is True
    assert marker_path(tmp_path).exists()


def test_never_touches_venv_git_build_or_dist(tmp_path):
    protected = {}
    for dir_name in (".venv", ".git", "build", "dist"):
        protected[dir_name] = _make_pycache(tmp_path, dir_name, "nested")
    unprotected = _make_pycache(tmp_path, "derby", "features")

    clear_cache_once_after_1_0_0_upgrade(root=tmp_path, current_version=TARGET_VERSION)

    for dir_name, path in protected.items():
        assert path.exists(), "{0} must never be touched".format(dir_name)
    assert not unprotected.exists()


def test_default_current_version_reads_the_single_source_of_truth(tmp_path, monkeypatch):
    import derby

    monkeypatch.setattr(derby, "__version__", TARGET_VERSION)
    cleared = clear_cache_once_after_1_0_0_upgrade(root=tmp_path)  # no current_version override
    assert cleared is True
