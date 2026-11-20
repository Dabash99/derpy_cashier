from __future__ import annotations

import importlib.util
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "check_public_files", PROJECT_ROOT / "tools" / "check_public_files.py"
)
check_public_files = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(check_public_files)

VALID_MANIFEST = {
    "version": "1.0.0",
    "notes": "إصدار ديربي 1.0.0",
    "download_url": "https://github.com/Dabash99/derpy_cashier/releases/download/v1.0.0/Derby-Setup-1.0.0.exe",
    "sha256": "a" * 64,
}


def _write_valid_public_dir(tmp_path: Path) -> Path:
    public_dir = tmp_path / "public"
    public_dir.mkdir()
    (public_dir / "version.json").write_text(json.dumps(VALID_MANIFEST), encoding="utf-8")
    (public_dir / "README.md").write_text("# Derby releases\n", encoding="utf-8")
    return public_dir


def test_valid_public_dir_has_no_problems(tmp_path):
    public_dir = _write_valid_public_dir(tmp_path)
    assert check_public_files.check_public_dir(public_dir) == []


def test_missing_dir_is_a_problem(tmp_path):
    problems = check_public_files.check_public_dir(tmp_path / "does_not_exist")
    assert len(problems) == 1


def test_extra_file_is_flagged(tmp_path):
    public_dir = _write_valid_public_dir(tmp_path)
    (public_dir / "menu.csv").write_text("secret cafe data", encoding="utf-8")

    problems = check_public_files.check_public_dir(public_dir)
    assert any("menu.csv" in problem for problem in problems)


def test_missing_required_file_is_flagged(tmp_path):
    public_dir = tmp_path / "public"
    public_dir.mkdir()
    (public_dir / "version.json").write_text(json.dumps(VALID_MANIFEST), encoding="utf-8")

    problems = check_public_files.check_public_dir(public_dir)
    assert any("README.md" in problem for problem in problems)


def test_phone_number_in_notes_is_flagged(tmp_path):
    public_dir = tmp_path / "public"
    public_dir.mkdir()
    manifest = dict(VALID_MANIFEST, notes="اتصل بينا على 201234567890")
    (public_dir / "version.json").write_text(json.dumps(manifest), encoding="utf-8")
    (public_dir / "README.md").write_text("# Derby releases\n", encoding="utf-8")

    problems = check_public_files.check_public_dir(public_dir)
    assert problems


def test_real_sha256_and_version_digits_do_not_false_positive(tmp_path):
    # A hex sha256 and "1.0.0" both contain digit runs -- they must not be
    # mistaken for a phone number.
    public_dir = _write_valid_public_dir(tmp_path)
    assert check_public_files.check_public_dir(public_dir) == []


def test_releases_history_json_is_allowed_and_not_required(tmp_path):
    public_dir = _write_valid_public_dir(tmp_path)
    history = [{"version": "1.0.0", "date": "2026-01-01", "notes": "أول إصدار"}]
    (public_dir / "releases-history.json").write_text(json.dumps(history), encoding="utf-8")

    assert check_public_files.check_public_dir(public_dir) == []


def test_releases_history_json_with_personal_data_is_flagged(tmp_path):
    public_dir = _write_valid_public_dir(tmp_path)
    history = [{"version": "1.0.0", "date": "2026-01-01", "notes": "اتصل بينا على 201234567890"}]
    (public_dir / "releases-history.json").write_text(json.dumps(history), encoding="utf-8")

    problems = check_public_files.check_public_dir(public_dir)
    assert problems


def test_unexpected_key_in_version_json_is_flagged(tmp_path):
    public_dir = tmp_path / "public"
    public_dir.mkdir()
    manifest = dict(VALID_MANIFEST, owner_email="someone@example.com")
    (public_dir / "version.json").write_text(json.dumps(manifest), encoding="utf-8")
    (public_dir / "README.md").write_text("# Derby releases\n", encoding="utf-8")

    problems = check_public_files.check_public_dir(public_dir)
    assert any("owner_email" in problem for problem in problems)
