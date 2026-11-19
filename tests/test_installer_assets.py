"""Sanity checks for the generated installer wizard images and for
installer/derby.iss's content (not a compile -- that needs Inno Setup
6, which this environment does not have; see tools/build_installer.py).
If the image checks fail, re-run:
    .venv\\Scripts\\python.exe tools\\make_installer_images.py
"""
from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INSTALLER_DIR = PROJECT_ROOT / "installer"


def test_wizard_image_is_164x314_bmp():
    from PySide2.QtGui import QImage

    path = INSTALLER_DIR / "wizard-image.bmp"
    assert path.exists()
    image = QImage(str(path))
    assert not image.isNull()
    assert (image.width(), image.height()) == (164, 314)


def test_wizard_small_image_is_55x55_bmp():
    from PySide2.QtGui import QImage

    path = INSTALLER_DIR / "wizard-small-image.bmp"
    assert path.exists()
    image = QImage(str(path))
    assert not image.isNull()
    assert (image.width(), image.height()) == (55, 55)


def test_derby_iss_exists_and_has_required_directives():
    text = (INSTALLER_DIR / "derby.iss").read_text(encoding="utf-8")
    assert "ArchitecturesAllowed=x64" in text
    assert "MinVersion=6.1sp1" in text
    assert "AppId={#MyAppId}" in text
    assert "WizardImageFile=wizard-image.bmp" in text
    assert "WizardSmallImageFile=wizard-small-image.bmp" in text
    assert "SetupIconFile=..\\assets\\derby.ico" in text
    assert "#include \"version.iss\"" in text


def test_derby_iss_never_deletes_real_user_data_folders():
    lines = (INSTALLER_DIR / "derby.iss").read_text(encoding="utf-8").splitlines()
    assert not any(line.strip() == "[UninstallDelete]" for line in lines)
    assert any("UninstallDataNotice" in line for line in lines)  # the "your data is kept" notice is wired up


def test_derby_iss_uninstall_notice_is_guarded_for_silent_mode():
    """A silent uninstall (/VERYSILENT, used by tools/build_installer.py's
    own automated verification) must never block on an unguarded MsgBox."""
    text = (INSTALLER_DIR / "derby.iss").read_text(encoding="utf-8")
    assert "UninstallSilent()" in text


def test_version_iss_defines_my_app_version_matching_derby_version():
    import derby

    text = (INSTALLER_DIR / "version.iss").read_text(encoding="utf-8")
    assert 'MyAppVersion "{0}"'.format(derby.__version__) in text


def test_redist_placeholder_or_real_file_present():
    redist_dir = INSTALLER_DIR / "redist"
    assert redist_dir.exists()
    has_real_file = (redist_dir / "vc_redist.x64.exe").exists()
    has_placeholder = (redist_dir / "PLACEHOLDER.md").exists()
    assert has_real_file or has_placeholder
