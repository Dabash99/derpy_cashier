# دليل إصدار نسخة جديدة من ديربي

(English summary at the bottom.)

هذا الدليل لصاحب المشروع (أو من يقوم بالبناء والنشر)، وليس للكاشير أو
صاحب الكافيه — دليل الاستخدام اليومي موجود في
[docs/USER-GUIDE-AR.md](USER-GUIDE-AR.md).

## 0. المستودعان (مهم جدًا)

- **`Dabash99/derpy_cashier`** (هذا المستودع) — لازم يبقى **خاص (Private)**
  دائمًا. تاريخ Git فيه يحتوي على بيانات قائمة حقيقية (صور منتجات +
  أسعار) اتضافت في الكوميت `00edea1` ثم أُزيلت من التتبّع بعدها بكوميت
  لاحق (`38ddf3c`) — لكنها **لسه موجودة بالكامل في تاريخ Git** لأنه ما
  تم تنظيفه (rewrite). لو اتحول هذا المستودع لعام في أي وقت قبل تنظيف
  هذا التاريخ، الصور والأسعار الحقيقية تظهر لأي حد يفتح الكوميتات
  القديمة.
- **`Dabash99/derby-releases`** — مستودع **عام** منفصل تمامًا، بدون كود
  مصدري وبدون أي بيانات كافيه. يحتوي فقط على `version.json` و
  `README.md` على فرع `main`، ومرفقات (Assets) على GitHub Releases
  (ملف المثبّت `.exe` و `SHA256SUMS.txt`). هذا هو المستودع الذي يقرأه
  البرنامج عند الضغط على "فحص التحديثات".

لا يوجد فرع orphan `releases` داخل `derpy_cashier` — هذه الفكرة القديمة
أُلغيت لصالح المستودع المنفصل أعلاه.

## 1. رفع رقم الإصدار

الإصدار موجود في مكان واحد فقط: `derby/__init__.py` (`__version__`).
عدّله هناك، ثم تأكد أن `pyproject.toml` (`version = "..."`) مطابق له —
يوجد اختبار (`tests/test_policy.py::test_version_matches_pyproject`)
يفشل تلقائيًا لو اختلفا.

## 2. أمر واحد لكل شيء: `tools/make_release.py`

```bash
.venv\Scripts\python.exe tools\make_release.py
```

يشغّل بالترتيب، ويتوقف فورًا (برسالة واضحة) لو فشلت أي خطوة:

1. `ruff check .`
2. `pytest -q` (كل الاختبارات، بما فيها `tests/test_policy.py`)
3. `tools/build.py` — PyInstaller + `--selftest` على النسخة المبنية
4. `tools/build_installer.py` — يحتاج **Inno Setup 6** (نزّله من
   https://jrsoftware.org/isdl.php لو غير موجود؛ السكربت يبحث عنه في
   مساراته الافتراضية ويطبع أمر الترجمة اليدوي لو ملقاهوش). يترجم
   `installer\derby.iss`، ثم يثبّت المثبّت تثبيتًا صامتًا في مجلد
   **مؤقت** (ليس Program Files الحقيقي)، يشغّل `Derby.exe --selftest`
   من داخل التثبيت، يلغي التثبيت صامتًا، ويتأكد أن مجلد التثبيت فرغ
   تمامًا وأن بيانات الاختبار لم تُمسّ — ويكتب `release\SHA256SUMS.txt`.
5. يحسب بصمة SHA-256 الحقيقية لـ `release\Derby-Setup-<version>.exe`
   ويكتب `release\version.json` كاملًا (الإصدار، نص عربي قصير، رابط
   التحميل على `derby-releases`، البصمة).
6. يكتب `release\public\version.json` و `release\public\README.md` —
   **هذا هو المجلد الوحيد** الذي يُفترض نسخ محتواه لمستودع
   `derby-releases`.
7. يشغّل `tools/check_public_files.py` على `release\public\` —
   يتأكد أنه يحتوي فقط على الملفين المذكورين، وأن `version.json` ما فيه
   أي بيانات شخصية (مسار حقيقي، إيميل، رقم تليفون).
8. يطبع خطوات النسخ/الرفع اليدوية بالضبط (الخطوة 3 تحت).

هذا السكربت **لا يلمس git أبدًا** (لا فرع، لا worktree، لا commit)، ولا
يرفع (`push`) ولا ينشئ Tag أو GitHub Release، ولا يتصل بالإنترنت في أي
لحظة، **إلا لو مررت `--publish`** (التفصيل في القسم 3 تحت) — بدونها
يطبع فقط خطوات النسخ/الرفع اليدوية.

## 3. النشر: تلقائي (`tools/publish_release.py`) أو يدوي

### الطريقة الأسهل: أمر واحد من البداية للنهاية

```bash
.venv\Scripts\python.exe tools\make_release.py --publish
```

هذا يشغّل كل خطوات القسم 2 ثم، لو نجحت، يشغّل `tools/publish_release.py`
تلقائيًا (ويسألك تأكيد قبل النشر الفعلي، إلا لو ضفت `--yes` كمان).

### أو تشغيل النشر بمفرده بعد `make_release.py` عادي

```bash
.venv\Scripts\python.exe tools\publish_release.py
```

يستخدم فقط أوامر `git` و `gh` (GitHub CLI) عبر subprocess — **لا يستورد
أي مكتبة شبكة بايثون**، نفس روح قاعدة "بدون شبكة" في CLAUDE.md، لكنه
أداة تطوير صريحة يشغّلها المالك بنفسه وليست جزءًا من البرنامج المُجمَّع.

قبل أي شيء يتحقق من (برسالة عربية واضحة ويتوقف لو فشل أي شرط):
- وجود `release\Derby-Setup-<ver>.exe` و `release\SHA256SUMS.txt` و
  `release\public\version.json`
- أن `version.json` يطابق رقم الإصدار الحقيقي وبصمة SHA-256 الحقيقية
  للملف
- نجاح `tools/check_public_files.py`
- أن `gh --version` يعمل و `gh auth status` مسجّل دخول (لو `gh` غير
  مثبّت: يطلب منك تثبيته من https://cli.github.com ثم `gh auth login` —
  لا يحاول تثبيت أي شيء بنفسه)
- أن الإصدار (tag) `v<ver>` **غير موجود بالفعل** على `derby-releases` —
  يرفض رفع نفس الإصدار مرتين ويطلب ترقيم إصدار جديد

ثم يطبع ملخص (الإصدار، أسماء الملفات وأحجامها، البصمة، المستودع
المستهدف) ويطلب تأكيدًا (إلا مع `--yes`)، أو يطبع الملخص فقط ويتوقف مع
`--dry-run` بدون أي تنفيذ فعلي.

بعد التأكيد: يستنسخ (أو يحدّث) نسخة محلية من `derby-releases` تحت
`build\derby-releases` (لا يلمس أبدًا حالة git لمستودع ديربي نفسه)،
يحدّث فيها `version.json` و `README.md` (رابط تحميل مباشر بارز، البصمة،
متطلبات Windows 7 SP1/10 64-bit، ملاحظة عن تحذير SmartScreen "More
info → Run anyway"، وجدول كل الإصدارات السابقة مُولَّد من
`releases-history.json` وليس معدَّلًا باليد) و `releases-history.json`،
يعمل commit + push (أو يتخطى هذا لو لم يتغيّر شيء — مثلًا لو تشغيل سابق
رفع لكن فشل في إنشاء GitHub Release، فإعادة التشغيل تكمل من حيث توقفت
بدون تكرار الكوميت)، ثم `gh release create` مع المثبّت و
`SHA256SUMS.txt`، ثم يتحقق أن حجم الملفين على GitHub يطابق الملفين
المحليين ويطبع الروابط النهائية.

لو فشلت خطوة إنشاء GitHub Release بعد نجاح الرفع (push)، الرسالة توضّح
ذلك بالضبط وتطلب فقط إعادة تشغيل الأداة — لن يتكرر الكوميت أو الدفع.

### الطريقة اليدوية البديلة (بدون `gh` أو بدون تشغيل الأداة)

1. افتح نسخة محلية (`git clone`) من `Dabash99/derby-releases` على جهازك،
   وانسخ لها:
   ```
   release\public\version.json  ->  <نسخة derby-releases>\version.json
   release\public\README.md     ->  <نسخة derby-releases>\README.md
   ```
   ثم من داخل تلك النسخة:
   ```bash
   git add version.json README.md
   git commit -m "Release v1.0.0"
   git push origin main
   ```
2. على GitHub، أنشئ Release جديد على `Dabash99/derby-releases` بعلامة
   Tag مثل `v1.0.0`، وارفع كمرفقات (Assets):
   - `release\Derby-Setup-1.0.0.exe`
   - `release\SHA256SUMS.txt`
3. تأكد أن رابط الـ raw يفتح في المتصفح:
   ```
   https://raw.githubusercontent.com/Dabash99/derby-releases/main/version.json
   ```
4. في البرنامج: الإعدادات ← رابط ملف التحديثات — مُعبّى تلقائيًا
   بهذا الرابط بالضبط كقيمة افتراضية (`update_manifest_url`)، والمالك
   يقدر يغيّره. اضغط "فحص التحديثات" وتأكد إنه يجد الإصدار الجديد،
   ويعرض النص العربي وبصمة SHA-256، وزر "تحميل" يفتح المتصفح على رابط
   GitHub (لا يحمّل الملف داخل البرنامج نفسه).

## 4. كيف تختبر مسار التحديث بالكامل (بدون لمس المستودع العام الحقيقي)

1. ثبّت نسخة 1.0.0 (من المثبّت الذي بنيته).
2. ارفع رقم الإصدار لـ 1.0.1 محليًا وشغّل `tools/make_release.py` تاني
   (يبني installer 1.0.1 و `release\version.json` الخاص به).
3. لا تلمس `derby-releases` الحقيقي لتجربة هذا — بدّل مؤقتًا رابط
   `update_manifest_url` في الإعدادات إلى ملف `version.json` المحلي
   (مثلًا عبر سيرفر HTTP محلي بسيط، أو حتى مباشرة لو عدّلت الكود
   مؤقتًا ليقرأ ملف محلي في بيئة تطوير) — المهم إنه رابط اختباري غير
   حقيقي، نفس فلسفة `tests/test_update_version_logic.py` و
   `tests/test_update_check_panel.py` التي تستخدم خادمًا مزيّفًا
   (fake server) أو mocked opener بدلًا من أي اتصال حقيقي.
4. تأكد أن الحوار يعرض "يوجد إصدار جديد: 1.0.1" والنص العربي والبصمة،
   وأن زر "تحميل" يفتح الرابط الصحيح.

## 5. ضمانات الترقية (Upgrade guarantees)

- **البيانات خارج مجلد التثبيت دائمًا**: قاعدة البيانات، الصور،
  الإيصالات، والنسخ الاحتياطية كلها في `%APPDATA%\Derby` و
  `Documents\Derby` — أبدًا داخل مجلد البرنامج (`Program Files\Derby`).
  تثبيت نسخة جديدة فوق القديمة (نفس AppId) لا يمسّ هذه المجلدات إطلاقًا،
  وكذلك إلغاء التثبيت.
- **الترقية التلقائية لقاعدة البيانات، بأمان**: عند أول تشغيل بعد
  الترقية، البرنامج يطبّق تحديثات قاعدة البيانات اللازمة تلقائيًا —
  لكن قبل أي تحديث فعلي على قاعدة بيانات موجودة مسبقًا، يأخذ نسخة
  احتياطية محقّقة (verified) أولًا. لو فشلت هذه النسخة الاحتياطية لأي
  سبب، **لا يتم تحديث قاعدة البيانات إطلاقًا** ويظهر للمستخدم رسالة
  عربية واضحة بدل أن يخاطر ببياناته.
- **التراجع (Rollback) عبر شاشة الاسترجاع**: لو حصلت مشكلة بعد الترقية،
  يمكن استرجاع أي نسخة احتياطية سابقة (قبل أو بعد الترقية) من شاشة
  "الاسترجاع" في الإعدادات — دون الحاجة لإعادة تثبيت أي شيء.

---

## English summary

Version lives in one place: `derby/__init__.py` (`__version__`), kept
in sync with `pyproject.toml` by a test. Releases are split across two
repos: **`Dabash99/derpy_cashier`** (this repo, source code) must stay
**private** -- its git history still contains real cafe menu
photos/prices from commit `00edea1`, never cleaned from history.
**`Dabash99/derby-releases`** is a separate **public** repo holding
only `version.json` + `README.md` on `main`, with installer assets on
its GitHub Releases. There is no orphan `releases` branch in this repo
-- that earlier idea was dropped in favor of the separate repo.

`tools/make_release.py` is the single release command: it runs
ruff + the full test suite, `tools/build.py` (PyInstaller +
`--selftest`), `tools/build_installer.py` (Inno Setup 6 compile + a
full silent install/`--selftest`/uninstall verification cycle, entirely
in temp directories), computes the installer's real SHA-256, writes
`release/version.json`, and writes the public-safe copy to
`release/public/` (checked by `tools/check_public_files.py` for stray
personal data). By itself it never touches git, never pushes, never
creates a release, and never makes a network request -- it just prints
the manual copy/push/release steps. Pass `--publish` (and optionally
`--yes`) to also run `tools/publish_release.py` at the end.

`tools/publish_release.py` is the automated publish step: git/gh only
via subprocess (no Python networking library), with strict
preconditions (files present, version/sha256 match, `check_public_files`
passes, `gh` installed and logged in, target tag doesn't already
exist), a confirmation prompt (or `--dry-run`/`--yes`), and an
idempotent clone-update-commit-push-release-verify sequence under
`build/derby-releases` -- a retry after a partial failure (e.g. the
push succeeded but `gh release create` didn't) never duplicates the
commit or the release.

Settings -> `update_manifest_url` is prefilled by default with
`https://raw.githubusercontent.com/Dabash99/derby-releases/main/version.json`
(the owner can still edit or clear it); the owner's manual "Check for
Updates" button is the only thing that ever reads it. Upgrades never
touch `%APPDATA%\Derby`/`Documents\Derby`; database migrations take a
verified backup first and abort (with a clear error) rather than risk
the data if that backup fails; any backup can be restored from the
Settings restore screen as a rollback.
