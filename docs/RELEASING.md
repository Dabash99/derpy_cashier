# دليل إصدار نسخة جديدة من ديربي

(English summary at the bottom.)

هذا الدليل لصاحب المشروع (أو من يقوم بالبناء والنشر)، وليس للكاشير أو
صاحب الكافيه — دليل الاستخدام اليومي موجود في
[docs/USER-GUIDE-AR.md](USER-GUIDE-AR.md).

## 0. المستودع (مهم جدًا)

كل شيء الآن في مستودع واحد: **`Dabash99/derpy_cashier`** (هذا المستودع)،
**عام (Public)** بقرار صاحب المشروع. داخله:

- **فرع `master`** — الكود المصدري الكامل.
- **فرع orphan باسم `releases`** — لا يحتوي **أي كود مصدري إطلاقًا**،
  فقط ثلاثة ملفات: `version.json`، `README.md`، `releases-history.json`.
  هذا هو الفرع الذي يقرأه البرنامج عند الضغط على "فحص التحديثات".
- **GitHub Releases** على نفس المستودع — كل Release بعلامة `v<ver>`
  يحمل مرفقَين (Assets): المثبّت `Derby-Setup-<ver>.exe` و
  `SHA256SUMS.txt`.

**تذكير دائم مهم**: تاريخ Git لفرع `master` يحتوي على بيانات قائمة
حقيقية (صور منتجات + أسعار) اتضافت في الكوميت `00edea1` ثم أُزيلت من
التتبّع بكوميت لاحق (`38ddf3c`) — لكنها **لسه موجودة بالكامل في تاريخ
Git** لأنه ما تم تنظيفه (rewrite). بما أن المستودع عام الآن، هذه
البيانات **معروضة فعليًا لأي حد يفتح الكوميتات القديمة** — هذا قرار
اتخذه صاحب المشروع بوعي، وليس خطأ. لو احتاج صاحب المشروع يمحوها فعليًا
من التاريخ لاحقًا، هذا يتطلب history rewrite (مثل `git filter-repo`)
وتنسيق مع أي حد عنده نسخة محلية من المستودع — خارج نطاق أي أداة تلقائية
هنا عمدًا.

لا يوجد مستودع عام منفصل (`derby-releases` أو غيره) — الفكرة القديمة
دي أُلغيت لصالح فرع orphan واحد في نفس المستودع العام.

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
   التحميل من GitHub Release في هذا المستودع، البصمة).
6. يكتب `release\public\version.json` و `release\public\README.md` —
   معاينة محمية بفحص خصوصية لِما سيُنشر على فرع `releases`.
7. يشغّل `tools/check_public_files.py` على `release\public\` —
   يتأكد أنه يحتوي فقط على الملفين المذكورين، وأن `version.json` ما فيه
   أي بيانات شخصية (مسار حقيقي، إيميل، رقم تليفون).
8. يطبع خطوات النشر اليدوية بالضبط (الخطوة 3 تحت) — أو، مع `--publish`،
   يشغّل `tools/publish_release.py` لتنفيذها تلقائيًا.

هذا السكربت **لا يلمس git أبدًا** (لا فرع، لا worktree، لا commit)، ولا
يرفع (`push`) ولا ينشئ Tag أو GitHub Release، ولا يتصل بالإنترنت في أي
لحظة، **إلا لو مررت `--publish`** (التفصيل في القسم 3 تحت).

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
**لا يبدّل فرعًا ولا يلمس working tree الخاص بنسختك الرئيسية من المستودع
إطلاقًا** — كل عمليات git تحدث في نسخة (clone) منفصلة تمامًا تحت
`build\releases-clone\`.

قبل أي شيء يتحقق من (برسالة عربية واضحة ويتوقف لو فشل أي شرط):
- وجود `release\Derby-Setup-<ver>.exe` و `release\SHA256SUMS.txt` و
  `release\public\version.json`
- أن `version.json` يطابق رقم الإصدار الحقيقي وبصمة SHA-256 الحقيقية
  للملف
- نجاح `tools/check_public_files.py`
- أن `gh --version` يعمل و `gh auth status` مسجّل دخول (لو `gh` غير
  مثبّت: يطلب منك تثبيته من https://cli.github.com ثم `gh auth login` —
  لا يحاول تثبيت أي شيء بنفسه)
- أن الإصدار (tag) `v<ver>` **غير موجود بالفعل** على هذا المستودع —
  يرفض رفع نفس الإصدار مرتين ويطلب ترقيم إصدار جديد

ثم يطبع ملخص (الإصدار، أسماء الملفات وأحجامها، البصمة) ويطلب تأكيدًا
(إلا مع `--yes`)، أو يطبع الملخص فقط ويتوقف مع `--dry-run` بدون أي
تنفيذ فعلي.

بعد التأكيد: يستنسخ (أو يحدّث) نسخة محلية منفصلة من هذا المستودع تحت
`build\releases-clone\` ويتأكد أن فرع `releases` محدّد فيها (لو الفرع
موجود عن بعد يجلبه، لو موجود محليًا فقط يحدّثه، لو غير موجود أصلًا
ينشئه كفرع orphan جديد تمامًا بدون أي تاريخ أو كود مصدري). يحدّث فيها
`version.json` و `README.md` (رابط تحميل مباشر بارز، البصمة، متطلبات
Windows 7 SP1/10 64-bit، ملاحظة عن تحذير SmartScreen "More info → Run
anyway"، وجدول كل الإصدارات السابقة مُولَّد من `releases-history.json`
وليس معدَّلًا باليد) و `releases-history.json`، يعمل commit + push على
فرع `releases` (أو يتخطى هذا لو لم يتغيّر شيء — مثلًا لو تشغيل سابق رفع
لكن فشل في إنشاء GitHub Release، فإعادة التشغيل تكمل من حيث توقفت بدون
تكرار الكوميت)، ثم `gh release create` مع المثبّت و `SHA256SUMS.txt`،
ثم يتحقق أن حجم الملفين على GitHub يطابق الملفين المحليين ويطبع
الروابط النهائية.

لو فشلت خطوة إنشاء GitHub Release بعد نجاح الرفع (push)، الرسالة توضّح
ذلك بالضبط وتطلب فقط إعادة تشغيل الأداة — لن يتكرر الكوميت أو الدفع.

### الطريقة اليدوية البديلة (بدون `gh` أو بدون تشغيل الأداة)

1. افتح نسخة محلية منفصلة (`git clone`) من هذا المستودع في مجلد آخر على
   جهازك، وفيها أنشئ/حدّث فرع `releases` (أول مرة: `git checkout --orphan
   releases` ثم احذف كل الملفات الموروثة من الفرع القديم)، وانسخ له:
   ```
   release\public\version.json  ->  version.json
   release\public\README.md     ->  README.md
   ```
   ثم من داخل تلك النسخة:
   ```bash
   git add version.json README.md
   git commit -m "Release v1.0.0"
   git push origin releases
   ```
2. على GitHub، أنشئ Release جديد على `Dabash99/derpy_cashier` بعلامة
   Tag مثل `v1.0.0`، وارفع كمرفقات (Assets):
   - `release\Derby-Setup-1.0.0.exe`
   - `release\SHA256SUMS.txt`
3. تأكد أن رابط الـ raw يفتح في المتصفح:
   ```
   https://raw.githubusercontent.com/Dabash99/derpy_cashier/releases/version.json
   ```
4. في البرنامج: الإعدادات ← رابط ملف التحديثات — مُعبّى تلقائيًا
   بهذا الرابط بالضبط كقيمة افتراضية (`update_manifest_url`)، والمالك
   يقدر يغيّره. اضغط "فحص التحديثات" وتأكد إنه يجد الإصدار الجديد،
   ويعرض النص العربي وبصمة SHA-256، وزر "تحميل" يفتح المتصفح على رابط
   GitHub (لا يحمّل الملف داخل البرنامج نفسه).

## 4. كيف تختبر مسار التحديث بالكامل (بدون لمس فرع `releases` الحقيقي)

1. ثبّت نسخة 1.0.0 (من المثبّت الذي بنيته).
2. ارفع رقم الإصدار لـ 1.0.1 محليًا وشغّل `tools/make_release.py` تاني
   (يبني installer 1.0.1 و `release\version.json` الخاص به).
3. لا تلمس فرع `releases` الحقيقي لتجربة هذا — بدّل مؤقتًا رابط
   `update_manifest_url` في الإعدادات إلى ملف `version.json` المحلي
   (مثلًا عبر سيرفر HTTP محلي بسيط) — المهم إنه رابط اختباري غير
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
in sync with `pyproject.toml` by a test. Releases now live in this same
repo, **`Dabash99/derpy_cashier`**, which is **public** by the owner's
decision -- its git history still contains real cafe menu photos/prices
from commit `00edea1` (never cleaned from history), and since the repo
is public that history is genuinely visible now; this is a deliberate,
informed choice, not an oversight. An orphan branch named `releases`
holds only `version.json`, `README.md` and `releases-history.json` --
never source code. Installer assets go on tagged GitHub Releases on
this same repo.

`tools/make_release.py` is the single release command: it runs
ruff + the full test suite, `tools/build.py` (PyInstaller +
`--selftest`), `tools/build_installer.py` (Inno Setup 6 compile + a
full silent install/`--selftest`/uninstall verification cycle, entirely
in temp directories), computes the installer's real SHA-256, writes
`release/version.json`, and writes a privacy-checked preview to
`release/public/` (checked by `tools/check_public_files.py` for stray
personal data). By itself it never touches git, never pushes, never
creates a release, and never makes a network request. Pass `--publish`
(and optionally `--yes`) to also run `tools/publish_release.py` at the
end.

`tools/publish_release.py` is the automated publish step: git/gh only
via subprocess (no Python networking library), and it never switches
branches or touches the main checkout's working tree -- all git work
happens in a separate clone under `build/releases-clone/`. Strict
preconditions (files present, version/sha256 match, `check_public_files`
passes, `gh` installed and logged in, target tag doesn't already
exist), a confirmation prompt (or `--dry-run`/`--yes`), and an
idempotent sequence: clone/update that separate clone, check out
`releases` (creating it as a fresh orphan branch if it doesn't exist
yet, locally or remotely), update/commit/push, `gh release create`,
then verify published asset sizes. A retry after a partial failure
(e.g. the push succeeded but `gh release create` didn't) never
duplicates the commit or the release.

Settings -> `update_manifest_url` is prefilled by default with
`https://raw.githubusercontent.com/Dabash99/derpy_cashier/releases/version.json`
(the owner can still edit or clear it); the owner's manual "Check for
Updates" button is the only thing that ever reads it. Upgrades never
touch `%APPDATA%\Derby`/`Documents\Derby`; database migrations take a
verified backup first and abort (with a clear error) rather than risk
the data if that backup fails; any backup can be restored from the
Settings restore screen as a rollback.
