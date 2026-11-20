"""Dev-time ONLY (never imported by the app, never part of the
PyInstaller build/installer). Publishes a release already built by
tools/make_release.py to THIS SAME repo, Dabash99/derpy_cashier (public):
the installer + SHA256SUMS.txt go on a tagged GitHub Release, and
version.json/README.md/releases-history.json go on an orphan branch
named "releases" that never holds any source code. See docs/RELEASING.md.

Uses ONLY subprocess calls to `git` and `gh` (the GitHub CLI) -- no
Python network library is imported here, matching CLAUDE.md's "no
networking" rule for the app itself (this is a separate dev tool, run
explicitly by the owner, not shipped, not exercised by tests/test_policy.py
which only scans derby/).

This script NEVER switches branches or otherwise touches the working
tree of the main checkout (the one this file lives in) -- all git work
happens in a SEPARATE clone of the same repo under build\\releases-clone.

Steps: check preconditions -> print a summary and ask for confirmation
(unless --yes) -> clone/update that separate working copy and check out
its "releases" branch (creating it as an orphan branch with a first
commit if it doesn't exist remotely yet) -> update
version.json/README.md/releases-history.json there -> commit + push
(skipped if nothing changed, e.g. a previous run already pushed but the
GitHub Release step then failed) -> `gh release create` with the
installer + SHA256SUMS.txt -> verify the published assets' sizes match
the local files.

Usage:
    .venv\\Scripts\\python.exe tools\\publish_release.py [--dry-run] [--yes]
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

RELEASE_DIR = PROJECT_ROOT / "release"
PUBLIC_DIR = RELEASE_DIR / "public"
CLONE_DIR = PROJECT_ROOT / "build" / "releases-clone"
REPO = "Dabash99/derpy_cashier"
RELEASES_BRANCH = "releases"
HISTORY_FILE_NAME = "releases-history.json"

_CHECK_PUBLIC_FILES_SPEC = importlib.util.spec_from_file_location(
    "check_public_files", Path(__file__).resolve().parent / "check_public_files.py"
)
check_public_files = importlib.util.module_from_spec(_CHECK_PUBLIC_FILES_SPEC)
_CHECK_PUBLIC_FILES_SPEC.loader.exec_module(check_public_files)


class PublishError(RuntimeError):
    """Carries an Arabic, user-facing message -- never a raw traceback."""


def _run(args, **kwargs):
    print("+ {0}".format(" ".join(str(a) for a in args)))
    return subprocess.run(args, **kwargs)


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(str(path), "rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Pure functions -- no subprocess, no filesystem writes outside what's
# passed in. Tested directly in tests/test_publish_release.py.
# ---------------------------------------------------------------------------


def merge_history(history: List[dict], entry: dict) -> List[dict]:
    """Prepends `entry`, replacing any existing row for the same version
    (a retry of the same version must not duplicate its row)."""
    filtered = [item for item in history if item.get("version") != entry["version"]]
    filtered.insert(0, entry)
    return filtered


README_TEMPLATE = """# ديربي (Derby) -- نظام نقاط البيع لكافيه ديربي

(لا يوجد كود مصدري أو بيانات كافيه في هذا المستودع -- فقط ملف التحديثات
ومرفقات الإصدارات.)

## تحميل آخر إصدار (v{version})

**[تحميل Derby-Setup-{version}.exe]({download_url})**

بصمة التحقق (SHA-256): `{sha256}`

**المتطلبات:** Windows 7 Service Pack 1 (64-bit) أو Windows 10 (64-bit).
على Windows 7 يلزم تحديث Universal C Runtime (KB2999226) مثبّتًا مسبقًا.

## التثبيت

نزّل الملف أعلاه وشغّله. لو ويندوز أظهر تحذير SmartScreen الأزرق
("Windows protected your PC")، اضغط **"More info"** ثم **"Run anyway"**
-- هذا طبيعي لبرنامج جديد غير موقّع بشهادة مدفوعة، ولا يعني وجود مشكلة.

## الإصدارات السابقة

| الإصدار | التاريخ | الرابط | ملاحظات |
|---|---|---|---|
{rows}

---

This branch publishes `version.json` for Derby's manual "Check for
Updates" button -- no source code lives here. Installer assets are on
this repo's GitHub Releases (the "الإصدار" links above).
"""


def _release_page_url(version: str) -> str:
    return "https://github.com/{0}/releases/tag/v{1}".format(REPO, version)


def build_readme_text(history: List[dict], download_url: str, sha256: str) -> str:
    if not history:
        raise ValueError("history must have at least the version being published")
    rows = "\n".join(
        "| {0} | {1} | [{2}]({3}) | {4} |".format(
            item["version"],
            item["date"],
            "صفحة الإصدار",
            _release_page_url(item["version"]),
            item.get("notes", "").replace("\n", " "),
        )
        for item in history
    )
    return README_TEMPLATE.format(
        version=history[0]["version"],
        download_url=download_url,
        sha256=sha256,
        rows=rows,
    )


def load_history(clone_dir: Path) -> List[dict]:
    history_path = clone_dir / HISTORY_FILE_NAME
    if not history_path.exists():
        return []
    return json.loads(history_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Preconditions
# ---------------------------------------------------------------------------


def check_preconditions(version: str) -> dict:
    """Returns the public manifest dict on success. Raises PublishError
    (an Arabic message, never a raw traceback) on the first failing check."""
    installer_path = RELEASE_DIR / "Derby-Setup-{0}.exe".format(version)
    sums_path = RELEASE_DIR / "SHA256SUMS.txt"
    public_version_json_path = PUBLIC_DIR / "version.json"

    if not installer_path.exists():
        raise PublishError(
            "ملف المثبّت غير موجود: {0} -- شغّل tools/make_release.py أولًا".format(installer_path)
        )
    if not sums_path.exists():
        raise PublishError("release/SHA256SUMS.txt غير موجود -- شغّل tools/make_release.py أولًا")
    if not public_version_json_path.exists():
        raise PublishError("release/public/version.json غير موجود -- شغّل tools/make_release.py أولًا")

    try:
        manifest = json.loads(public_version_json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise PublishError("release/public/version.json ليس JSON صالحًا: {0}".format(error))

    if manifest.get("version") != version:
        raise PublishError(
            "رقم الإصدار في version.json ({0}) لا يطابق derby/__init__.py ({1}) "
            "-- أعد تشغيل tools/make_release.py بعد رفع رقم الإصدار".format(manifest.get("version"), version)
        )

    real_sha256 = _sha256_of(installer_path)
    if manifest.get("sha256") != real_sha256:
        raise PublishError(
            "بصمة SHA-256 في version.json لا تطابق الملف الحقيقي -- أعد تشغيل tools/make_release.py"
        )

    problems = check_public_files.check_public_dir(PUBLIC_DIR)
    if problems:
        raise PublishError(
            "release/public لم ينجح في فحص الخصوصية:\n  - " + "\n  - ".join(problems)
        )

    gh_version = _run(["gh", "--version"], capture_output=True, text=True)
    if gh_version.returncode != 0:
        raise PublishError(
            "أداة gh (GitHub CLI) غير مثبّتة أو لا تعمل -- نزّلها من https://cli.github.com "
            "ثم شغّل: gh auth login"
        )

    gh_auth = _run(["gh", "auth", "status"], capture_output=True, text=True)
    if gh_auth.returncode != 0:
        raise PublishError("لم تسجّل الدخول في gh -- شغّل: gh auth login")

    tag = "v{0}".format(version)
    tag_check = _run(["gh", "release", "view", tag, "--repo", REPO], capture_output=True, text=True)
    if tag_check.returncode == 0:
        raise PublishError(
            "الإصدار {0} موجود بالفعل على {1} -- رفع نفس الإصدار مرتين ممنوع، "
            "رقّم إصدارًا جديدًا في derby/__init__.py".format(tag, REPO)
        )

    return manifest


# ---------------------------------------------------------------------------
# git/gh orchestration
# ---------------------------------------------------------------------------


def _clear_working_tree_except_git(directory: Path) -> None:
    """Removes every file/folder in `directory` except .git itself --
    used right after creating a fresh orphan branch, whose working tree
    otherwise still holds whatever branch it was orphaned from (this repo's
    full source code)."""
    for item in directory.iterdir():
        if item.name == ".git":
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()


def _remote_has_branch(branch: str) -> bool:
    result = _run(
        ["git", "-C", str(CLONE_DIR), "ls-remote", "--exit-code", "--heads", "origin", branch],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _local_has_branch(branch: str) -> bool:
    result = _run(
        ["git", "-C", str(CLONE_DIR), "show-ref", "--verify", "--quiet", "refs/heads/{0}".format(branch)]
    )
    return result.returncode == 0


def _ensure_releases_branch_checked_out() -> None:
    fetch_result = _run(["git", "-C", str(CLONE_DIR), "fetch", "origin"])
    if fetch_result.returncode != 0:
        raise PublishError("تعذر git fetch في {0}".format(CLONE_DIR))

    if _local_has_branch(RELEASES_BRANCH):
        checkout_result = _run(["git", "-C", str(CLONE_DIR), "checkout", RELEASES_BRANCH])
        if checkout_result.returncode != 0:
            raise PublishError("تعذر git checkout {0} في {1}".format(RELEASES_BRANCH, CLONE_DIR))
        if _remote_has_branch(RELEASES_BRANCH):
            pull_result = _run(
                ["git", "-C", str(CLONE_DIR), "pull", "--ff-only", "origin", RELEASES_BRANCH]
            )
            if pull_result.returncode != 0:
                raise PublishError(
                    "تعذر تحديث فرع {0} المحلي (git pull --ff-only) في {1}".format(RELEASES_BRANCH, CLONE_DIR)
                )
        return

    if _remote_has_branch(RELEASES_BRANCH):
        checkout_result = _run(
            ["git", "-C", str(CLONE_DIR), "checkout", "-b", RELEASES_BRANCH, "origin/{0}".format(RELEASES_BRANCH)]
        )
        if checkout_result.returncode != 0:
            raise PublishError("تعذر checkout فرع {0} من origin في {1}".format(RELEASES_BRANCH, CLONE_DIR))
        return

    # Neither a local nor a remote "releases" branch exists yet -- create
    # it as a fresh orphan branch (no history, no source code).
    orphan_result = _run(["git", "-C", str(CLONE_DIR), "checkout", "--orphan", RELEASES_BRANCH])
    if orphan_result.returncode != 0:
        raise PublishError("تعذر إنشاء فرع {0} الجديد (orphan) في {1}".format(RELEASES_BRANCH, CLONE_DIR))
    _clear_working_tree_except_git(CLONE_DIR)


def clone_or_update_working_copy() -> None:
    if not CLONE_DIR.exists():
        CLONE_DIR.parent.mkdir(parents=True, exist_ok=True)
        result = _run(["gh", "repo", "clone", REPO, str(CLONE_DIR)])
        if result.returncode != 0:
            raise PublishError("تعذر استنساخ {0} إلى {1}".format(REPO, CLONE_DIR))
    _ensure_releases_branch_checked_out()


def update_working_copy_files(manifest: dict) -> None:
    version = manifest["version"]
    today = date.today().isoformat()

    history = load_history(CLONE_DIR)
    entry = {"version": version, "date": today, "notes": manifest.get("notes", "")}
    history = merge_history(history, entry)

    readme_text = build_readme_text(history, manifest["download_url"], manifest["sha256"])

    (CLONE_DIR / "version.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (CLONE_DIR / "README.md").write_text(readme_text, encoding="utf-8")
    (CLONE_DIR / HISTORY_FILE_NAME).write_text(
        json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def commit_and_push_if_needed(version: str) -> None:
    status = _run(["git", "-C", str(CLONE_DIR), "status", "--porcelain"], capture_output=True, text=True)
    if not status.stdout.strip():
        print(
            "لا يوجد تغييرات لنشرها على فرع {0} (رُفعت مسبقًا في تشغيل سابق) "
            "-- سيُعاد فقط محاولة إنشاء GitHub Release.".format(RELEASES_BRANCH)
        )
        return

    add_result = _run(
        ["git", "-C", str(CLONE_DIR), "add", "version.json", "README.md", HISTORY_FILE_NAME]
    )
    if add_result.returncode != 0:
        raise PublishError("تعذر git add في {0}".format(CLONE_DIR))

    commit_result = _run(["git", "-C", str(CLONE_DIR), "commit", "-m", "Release {0}".format(version)])
    if commit_result.returncode != 0:
        raise PublishError("تعذر git commit في {0}".format(CLONE_DIR))

    push_result = _run(["git", "-C", str(CLONE_DIR), "push", "-u", "origin", RELEASES_BRANCH])
    if push_result.returncode != 0:
        raise PublishError(
            "تعذر git push -- الكوميت محفوظ محليًا في {0}, أعد تشغيل الأداة لإعادة المحاولة "
            "(لن يتكرر الكوميت)".format(CLONE_DIR)
        )


def create_github_release(version: str, manifest: dict) -> None:
    tag = "v{0}".format(version)
    notes_path = CLONE_DIR / ".release-notes.txt"
    notes_path.write_text(manifest.get("notes", ""), encoding="utf-8")
    installer_path = RELEASE_DIR / "Derby-Setup-{0}.exe".format(version)
    sums_path = RELEASE_DIR / "SHA256SUMS.txt"
    try:
        result = _run(
            [
                "gh",
                "release",
                "create",
                tag,
                str(installer_path),
                str(sums_path),
                "--repo",
                REPO,
                "--title",
                "Derby {0}".format(version),
                "--notes-file",
                str(notes_path),
            ]
        )
    finally:
        notes_path.unlink(missing_ok=True)
    if result.returncode != 0:
        raise PublishError(
            "تم رفع version.json/README لكن إنشاء GitHub Release ({0}) فشل -- "
            "أعد تشغيل الأداة فقط (لن يتكرر الكوميت أو الدفع) لإعادة محاولة إنشاء الإصدار".format(tag)
        )


def verify_release(version: str, manifest: dict) -> None:
    tag = "v{0}".format(version)
    result = _run(
        ["gh", "release", "view", tag, "--repo", REPO, "--json", "assets,url"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise PublishError("تم إنشاء الإصدار لكن تعذّر التحقق منه بعد ذلك -- راجعه يدويًا على GitHub")

    data = json.loads(result.stdout)
    remote_sizes = {asset["name"]: asset["size"] for asset in data.get("assets", [])}

    installer_path = RELEASE_DIR / "Derby-Setup-{0}.exe".format(version)
    sums_path = RELEASE_DIR / "SHA256SUMS.txt"
    for local_path in (installer_path, sums_path):
        remote_size = remote_sizes.get(local_path.name)
        if remote_size != local_path.stat().st_size:
            raise PublishError(
                "حجم {0} على GitHub ({1}) لا يطابق الملف المحلي ({2})".format(
                    local_path.name, remote_size, local_path.stat().st_size
                )
            )

    print()
    print("تم النشر والتحقق بنجاح:")
    print("  رابط صفحة الإصدار: {0}".format(data.get("url")))
    print("  رابط التحميل المباشر: {0}".format(manifest["download_url"]))
    print(
        "  رابط version.json الخام: https://raw.githubusercontent.com/{0}/{1}/version.json".format(
            REPO, RELEASES_BRANCH
        )
    )


def print_summary(version: str, manifest: dict) -> None:
    installer_path = RELEASE_DIR / "Derby-Setup-{0}.exe".format(version)
    sums_path = RELEASE_DIR / "SHA256SUMS.txt"
    print("سيتم نشر الإصدار {0} على {1}:".format(version, REPO))
    print("  {0} ({1:.1f} MB)".format(installer_path.name, installer_path.stat().st_size / (1024 * 1024)))
    print("  {0}".format(sums_path.name))
    print("  sha256: {0}".format(manifest["sha256"]))
    print("  download_url: {0}".format(manifest["download_url"]))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print what would happen, change nothing")
    parser.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    args = parser.parse_args(argv)

    import derby

    version = derby.__version__

    try:
        manifest = check_preconditions(version)
    except PublishError as error:
        print("PUBLISH ABORTED: {0}".format(error))
        return 1

    print_summary(version, manifest)

    if args.dry_run:
        print()
        print("--dry-run: لم يتم تنفيذ أي شيء فعليًا (لا clone، لا commit، لا push، لا GitHub Release).")
        return 0

    if not args.yes:
        answer = input("أكّد نشر هذا الإصدار على {0}؟ (اكتب yes للتأكيد): ".format(REPO))
        if answer.strip().lower() != "yes":
            print("تم الإلغاء -- لم يتم نشر أي شيء.")
            return 1

    try:
        clone_or_update_working_copy()
        update_working_copy_files(manifest)
        commit_and_push_if_needed(version)
        create_github_release(version, manifest)
        verify_release(version, manifest)
    except PublishError as error:
        print("PUBLISH ABORTED: {0}".format(error))
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
