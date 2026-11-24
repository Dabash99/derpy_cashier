"""On Windows 7 without KB2533623, os.add_dll_directory() raises OSError
(WinError 127) because AddDllDirectory is missing from kernel32.dll.
derby.core.utils.win_dll_search must make that degrade gracefully instead
of crashing the frozen app before PySide2 even finishes importing."""
from __future__ import annotations

import pytest

from derby.core.utils import win_dll_search as dll_search


@pytest.fixture(autouse=True)
def _restore_os_add_dll_directory():
    """_patch_add_dll_directory() reassigns os.add_dll_directory directly
    (that's its whole job), which is a real module-level mutation monkeypatch
    does not see unless a test also routes the same attribute through it --
    this fixture guarantees the real function is back in place for every
    other test regardless of which path a given test takes."""
    original = getattr(dll_search.os, "add_dll_directory", None)
    yield
    if original is None:
        if hasattr(dll_search.os, "add_dll_directory"):
            del dll_search.os.add_dll_directory
    else:
        dll_search.os.add_dll_directory = original


def test_patch_falls_back_to_path_when_original_raises_oserror(monkeypatch, tmp_path):
    def _raising_add_dll_directory(path):
        raise OSError("[WinError 127] The specified procedure could not be found")

    monkeypatch.setattr(dll_search.os, "add_dll_directory", _raising_add_dll_directory, raising=False)
    monkeypatch.setenv("PATH", "C:\\existing")

    dll_search._patch_add_dll_directory()

    cookie = dll_search.os.add_dll_directory(str(tmp_path))

    assert dll_search.os.environ["PATH"] == "{0}{1}C:\\existing".format(tmp_path, dll_search.os.pathsep)
    # The real os.add_dll_directory() result supports close() and use as a
    # context manager -- the fallback cookie must too, so PySide2's own
    # (unpatched) call sites don't break on either usage.
    cookie.close()
    with dll_search.os.add_dll_directory(str(tmp_path)) as entered:
        assert entered is not None


def test_patch_still_delegates_to_the_original_when_it_succeeds(monkeypatch, tmp_path):
    calls = []

    def _working_add_dll_directory(path):
        calls.append(path)
        return "real-cookie"

    monkeypatch.setattr(dll_search.os, "add_dll_directory", _working_add_dll_directory, raising=False)

    dll_search._patch_add_dll_directory()

    result = dll_search.os.add_dll_directory(str(tmp_path))

    assert result == "real-cookie"
    assert calls == [str(tmp_path)]


def test_patch_is_a_noop_when_add_dll_directory_does_not_exist(monkeypatch):
    monkeypatch.delattr(dll_search.os, "add_dll_directory", raising=False)

    dll_search._patch_add_dll_directory()  # must not raise

    assert not hasattr(dll_search.os, "add_dll_directory")


def test_app_root_dirs_is_empty_when_not_frozen(monkeypatch):
    monkeypatch.setattr(dll_search.sys, "frozen", False, raising=False)

    assert dll_search._app_root_dirs() == []


def test_app_root_dirs_includes_existing_pyside2_and_shiboken2_subfolders(monkeypatch, tmp_path):
    fake_exe = tmp_path / "Derby.exe"
    fake_exe.write_text("", encoding="utf-8")
    (tmp_path / "PySide2").mkdir()
    (tmp_path / "shiboken2").mkdir()
    # Deliberately NOT created: a missing subfolder must simply be skipped,
    # not raise.

    monkeypatch.setattr(dll_search.sys, "frozen", True, raising=False)
    monkeypatch.setattr(dll_search.sys, "executable", str(fake_exe))

    dirs = dll_search._app_root_dirs()

    assert str(tmp_path) in dirs
    assert str(tmp_path / "PySide2") in dirs
    assert str(tmp_path / "shiboken2") in dirs
    assert len(dirs) == 3


def test_ensure_win_dll_search_paths_prepends_app_root_dirs_to_path(monkeypatch, tmp_path):
    fake_exe = tmp_path / "Derby.exe"
    fake_exe.write_text("", encoding="utf-8")
    (tmp_path / "PySide2").mkdir()

    monkeypatch.setattr(dll_search.sys, "frozen", True, raising=False)
    monkeypatch.setattr(dll_search.sys, "executable", str(fake_exe))
    monkeypatch.setenv("PATH", "C:\\existing")

    added = []
    monkeypatch.setattr(
        dll_search.os, "add_dll_directory", lambda path: added.append(path), raising=False
    )

    dll_search.ensure_win_dll_search_paths()

    assert str(tmp_path) in added
    assert str(tmp_path / "PySide2") in added
    assert str(tmp_path) in dll_search.os.environ["PATH"]
    assert str(tmp_path / "PySide2") in dll_search.os.environ["PATH"]


@pytest.mark.parametrize("has_add_dll_directory", [True, False])
def test_ensure_win_dll_search_paths_is_safe_when_not_frozen(monkeypatch, has_add_dll_directory):
    monkeypatch.setattr(dll_search.sys, "frozen", False, raising=False)
    if not has_add_dll_directory:
        monkeypatch.delattr(dll_search.os, "add_dll_directory", raising=False)

    dll_search.ensure_win_dll_search_paths()  # must not raise either way
