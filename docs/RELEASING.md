# دليل إصدار نسخة جديدة من ديربي

(English summary at the bottom.)

هذا الدليل لصاحب المشروع (أو من يقوم بالبناء والنشر)، وليس للكاشير أو
صاحب الكافيه — دليل الاستخدام اليومي موجود في
[docs/USER-GUIDE-AR.md](USER-GUIDE-AR.md).

## 1. رفع رقم الإصدار

الإصدار موجود في مكان واحد فقط: `derby/__init__.py` (`__version__`).
عدّله هناك، ثم تأكد أن `pyproject.toml` (`version = "..."`) مطابق له —
يوجد اختبار (`tests/test_policy.py::test_version_matches_pyproject`)
يفشل تلقائيًا لو اختلفا.

```bash
# تحقق أن كل الاختبارات ما زالت ناجحة بعد التعديل
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m ruff check .
```

## 2. البناء (Build)

```bash
build.bat
```

هذا يشغّل (بالترتيب، ويتوقف فورًا لو فشلت أي خطوة): `ruff check .`، ثم
كل الاختبارات، ثم PyInstaller (حسب `derby.spec`)، ثم يتحقق تلقائيًا من
الناتج (`dist\Derby\Derby.exe --selftest` لازم يرجع بنجاح، لا توجد ملفات
QtNetwork/QtSvg، يطبع حجم المجلد وعدد الملفات وبصمة SHA-256).

## 3. المثبّت (Installer)

يحتاج Inno Setup 6 (غير مثبّت تلقائيًا — نزّله من
https://jrsoftware.org/isdl.php إذا لم يكن موجودًا).

```bash
.venv\Scripts\python.exe tools\build_installer.py
```

هذا يعيد توليد `installer\version.iss` من رقم الإصدار الحالي، يبني
`release\Derby-Setup-<version>.exe` عبر Inno Setup، ثم يتحقق منه تلقائيًا:
تثبيت صامت في مجلد مؤقت، تشغيل `--selftest`، إلغاء تثبيت صامت، والتأكد
أن مجلد التثبيت فرغ تمامًا وأن بيانات الاختبار لم تُمسّ. لا يثبّت أبدًا
في Program Files الحقيقي ولا ينشئ اختصارات حقيقية أثناء هذا التحقق.

إذا لم يكن Inno Setup مثبّتًا، تحصل على رسالة توضّح بالضبط من أين تحمّله
وأمر الترجمة (compile) اليدوي بالضبط — ملف `installer\derby.iss` يبقى
جاهزًا ومكتملًا بغض النظر.

## 4. نشر إصدار على GitHub (مستودع عام Public)

1. أنشئ إصدار (Release) جديد على GitHub، بعلامة Tag مثل `v0.2.0`
   (يطابق رقم الإصدار في `derby/__init__.py`).
2. ارفع `release\Derby-Setup-<version>.exe` و `release\SHA256SUMS.txt`
   كمرفقات (Assets) على هذا الإصدار.
3. المستودع **لازم يكون عام (Public)** — رابط التحميل المباشر لا يعمل
   إلا لو كان المستودع عامًا.

## 5. نشر version.json (لفحص التحديثات اليدوي)

```bash
.venv\Scripts\python.exe tools\write_version_json.py
```

هذا يولّد `release\version.json` بالشكل بالضبط الذي يتوقعه البرنامج
(`derby/core/updates/version_logic.py`):

```json
{
  "version": "0.2.0",
  "notes": "نص قصير يظهر للمالك",
  "download_url": "https://github.com/<owner>/<repo>/releases/download/v0.2.0/Derby-Setup-0.2.0.exe"
}
```

قبل رفعه، افتح الملف وعدّل `download_url` ليطابق رابط التحميل الحقيقي
من الإصدار الذي رفعته في الخطوة 4 (الأداة تكتب رابطًا نموذجيًا فقط).
`download_url` لازم يكون `https://` وعلى نطاق `github.com` أو
`objects.githubusercontent.com` أو `raw.githubusercontent.com` — أي نطاق
آخر يرفضه البرنامج نفسه كحماية إضافية.

**أين تنشر `version.json`؟** ضمن نفس إصدار GitHub (كمرفق Asset) هو
الأبسط. ثم احسب رابط "raw" المباشر له (مثال لو رفعته كمرفق على الإصدار
`v0.2.0` في مستودع `owner/repo`):

```
https://github.com/owner/repo/releases/download/v0.2.0/version.json
```

انسخ هذا الرابط إلى: الإعدادات ← رابط ملف التحديثات (`update_manifest_url`)
— هذا هو الرابط الذي يضغط عليه صاحب الكافيه "فحص التحديثات" ليفحصه.
فحص التحديثات **يدوي فقط** (زر واحد في الإعدادات) — البرنامج لا يفحص
شيئًا تلقائيًا ولا يتصل بالإنترنت في أي وقت آخر.

## 6. ضمانات الترقية (Upgrade guarantees)

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
in sync with `pyproject.toml` by a test. `build.bat` runs ruff + the
full test suite + PyInstaller (`derby.spec`) and verifies the frozen
output automatically. `tools\build_installer.py` compiles
`installer\derby.iss` with Inno Setup 6 (if installed) and verifies a
full silent install/selftest/uninstall cycle in temp directories only.
Publish the installer + `SHA256SUMS.txt` as GitHub Release assets in a
**public** repo; generate `release\version.json` with
`tools\write_version_json.py`, fix its placeholder `download_url`, host
it (e.g. as another release asset), and put its raw URL into
Settings -> `update_manifest_url` -- the owner's manual "Check for
Updates" button is the only thing that ever reads it; nothing else in
the app makes a network call. Upgrades never touch
`%APPDATA%\Derby`/`Documents\Derby`; database migrations take a
verified backup first and abort (with a clear error) rather than risk
the data if that backup fails; any backup can be restored from the
Settings restore screen as a rollback.
