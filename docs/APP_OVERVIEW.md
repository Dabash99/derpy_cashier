# نظرة عامة على تطبيق Derby (Cafe POS)

**الإصدار:** 1.1.0 (`derby/__init__.py` → `__version__`)
**تاريخ هذا التحليل:** 2026-11-23
**نطاق التحليل:** قراءة فقط لكود المصدر، الاختبارات، الوثائق، سكربتات البناء/التثبيت والترحيلات (migrations) الموجودة في المستودع. لم يُفتح أي ملف قاعدة بيانات حقيقي أو نسخة احتياطية أو سجلات أو إعدادات مستخدم فعلية.

---

## جدول المحتويات

1. [نظرة عامة](#1-نظرة-عامة)
2. [التقنيات والبنية](#2-التقنيات-والبنية)
3. [الشاشات والمميزات](#3-الشاشات-والمميزات)
4. [القواعد التجارية (business rules)](#4-القواعد-التجارية-business-rules)
5. [نموذج البيانات](#5-نموذج-البيانات)
6. [الإعدادات](#6-الإعدادات)
7. [النسخ الاحتياطي والاسترجاع والتحديث](#7-النسخ-الاحتياطي-والاسترجاع-والتحديث)
8. [البناء والإصدار](#8-البناء-والإصدار)
9. [الاختبارات](#9-الاختبارات)
10. [القيود والمعروف نقصه](#10-القيود-والمعروف-نقصه)
11. [مصطلحات](#11-مصطلحات)
12. [Open points](#12-open-points)

---

## 1) نظرة عامة

**Derby** برنامج كاشير (نقطة بيع / POS) لمقهى اسمه "ديربي" في المنوفية، مصر، وله أيضًا ركن بلايستيشن. البرنامج:

- واجهة **عربية بالكامل، من اليمين لليسار (RTL)** — كل النصوص العربية مجمّعة في `derby/core/i18n/ar.py`.
- يعمل **بدون إنترنت تمامًا**، باستثناء زر واحد يدوي "فحص التحديثات" في الإعدادات (`derby/core/updates/update_check.py`)، بالإضافة إلى تسليم تقرير الإقفال اليومي إلى واتساب (`derby/core/integrations/whatsapp.py`) — وهذا الأخير ليس طلب شبكة من التطبيق نفسه، بل فتح تطبيق واتساب ديسكتوب أو متصفح المستخدم (`os.startfile` / `webbrowser.open`)، مع نسخ النص إلى الحافظة كخيار احتياطي.
- يدعم **Windows 7 SP1 64-bit و Windows 10 64-bit** من نفس الكود (`derby.spec`, `installer/derby.iss`). ويندوز 7 يحتاج تحديث KB2999226 (Universal C Runtime) — هذا شرط على نظام التشغيل، لا يستطيع التطبيق تثبيته بنفسه.
- **لا شبكة إطلاقًا** خارج ما سبق: لا حسابات سحابية، لا تحليلات (analytics)، لا تحديث تلقائي، لا تقارير أعطال عن بُعد.

### من يستخدمه

دوران فقط (`derby/core/db/users_repo.py`: `ROLE_OWNER`, `ROLE_CASHIER`):

| الدور | الوصف |
|---|---|
| **المالك (owner)** | صلاحية كاملة: المنيو، الإعدادات، التقارير، المصروفات، المخزون/الوصفات/الموردين، الموافقة بالـ PIN على أي إجراء يحتاج صلاحية مالك. |
| **الكاشير (cashier)** | يستخدم الكاشير، الترابيزات، البلايستيشن، الخزنة (كاش فقط)، المستلزمات (الإضافة والتعليم كمشترى) — بدون المصروفات أو التقارير أو الإعدادات أو بيانات التكلفة/الربح. |

لا يوجد أي دور ثالث في الكود (`derby/features/auth/permissions.py` يفرّق فقط بين هذين الدورين عبر أكثر من 20 دالة تحقّق صلاحية صغيرة ومباشرة).

### القيود الصارمة (من CLAUDE.md، مؤكدة بالكود واختبار `tests/test_policy.py`)

- لا شبكة إلا الملفين المذكورين أعلاه (محروسة بـ `tests/test_policy.py`: لا `socket`/`ssl`/`http.client`/`urllib.request`/`requests`... في أي ملف آخر تحت `derby/`).
- **Python 3.8.x 64-bit فقط** (كل ملف يبدأ بـ `from __future__ import annotations`، لا `match`، لا `X | Y`).
- **PySide2 5.15.2.1** فقط (لا `QtNetwork`/`QtWebEngine*`/`QtQml`/`QtSvg`... داخل `derby/`؛ `QtSvg` مسموح فقط في `tools/`).
- النقود دائمًا **عدد صحيح من القروش** (`derby/core/utils/money.py`) — لا `float` للنقود أبدًا.
- الطوابع الزمنية UTC في قاعدة البيانات، وتُحوَّل لتوقيت القاهرة فقط للعرض.

---

## 2) التقنيات والبنية

### المكوّنات التقنية

| المكوّن | القيمة |
|---|---|
| اللغة | Python 3.8.x 64-bit |
| الواجهة | PySide2 5.15.2.1 (`QtCore`, `QtGui`, `QtWidgets` فقط) |
| قاعدة البيانات | SQLite (`sqlite3` من المكتبة القياسية)، `WAL` + `foreign_keys=ON` |
| التعبئة/التوزيع | PyInstaller (one-dir) + Inno Setup 6 |
| الخطوط | Cairo (عربي) + Montserrat (أرقام/أسعار/علامة تجارية)، مضمّنة في `assets/fonts/` |

### خريطة المجلدات (مستوى واحد لكل حزمة، كما ظهرت فعليًا في الكود)

```
derby/
  __init__.py            __version__ = "1.1.0"
  __main__.py             نقطة الدخول (python -m derby)، يتحقق من --selftest أولاً
  app.py                   QApplication: HiDPI, RTL, خط Cairo, single-instance,
                           فتح قاعدة البيانات + migrations, جدولة الإقفال (30s),
                           نسخة احتياطية عند الخروج, توجيه بين SetupScreen/LoginScreen/MainWindow

  core/
    db/                    connection.py + migrations.py + *_repo.py (طبقة الوصول للبيانات فقط، SQL خام)
    theme/                 tokens.py (قياسات), stylesheet.py, fonts.py, icons.py,
                           stat_tile.py, styled.py, tab_bar.py, table_style.py
    i18n/                  ar.py — كل النصوص العربية (842 سطر)
    utils/                 money.py, time_utils.py, business_date.py, pin_hash.py,
                           single_instance.py, paths.py, resource_path.py,
                           platform_info.py, error_log.py, startup_cache.py
    updates/               update_check.py (الملف الوحيد المسموح له بعمل طلب شبكة), version_logic.py (منطق خالص)
    integrations/          whatsapp.py (تسليم فقط، بدون طلب شبكة من التطبيق)
    selftest.py              `python -m derby --selftest`

  features/
    auth/                  تسجيل الدخول، PIN، lockout، صلاحيات، الإعداد الأول
    shell/                 الهيدر، الشريط الجانبي، النافذة الرئيسية، مؤقت الخمول
    dashboard/             الرئيسية/إحصائيات اليوم
    menu/                  المنيو: فئات، منتجات، إضافات، استيراد/تصدير CSV، صور
    pos/                   الكاشير: السلة، الخصومات، الدفع، سجل المبيعات
    tables/                الترابيزات
    playstation/            أجهزة البلايستيشن والجلسات والتسعير
    expenses/              المصروفات (فئات، دورية، إيصالات)
    inventory/             المخزون (أصناف، وصفات) + الخزنة (drawer)
    supplies/               قائمة المستلزمات المطلوب شراؤها
    reports/               التقارير وتصديرها (CSV/Excel/PDF)
    settings/               الإعدادات، المستخدمين، فحص التحديثات، أدوات متقدمة
    closing/                الإقفال اليومي، النسخ الاحتياطي، الاسترجاع

assets/                    خطوط، شعار، أيقونات مولّدة (tools/render_assets.py)
tools/                      سكربتات وقت التطوير فقط (بناء، تثبيت، إصدار) — لا تُشحن مع التطبيق
installer/                 derby.iss (Inno Setup) + redist/
tests/                      106 ملف اختبار، 708 دالة test_*
```

### كيف يبدأ التطبيق (`derby/app.py::main`)

1. تثبيت معالج استثناءات عام (`error_log.install_exception_hook`).
2. تنظيف كاش قديم مرة واحدة فقط بعد الترقية من 1.0.0 (`startup_cache.py`).
3. ضبط HiDPI، إنشاء `QApplication`، ضبط RTL، تحميل الخطوط المضمّنة، الـ stylesheet، أيقونة التطبيق.
4. فحص نسخة واحدة فقط من التطبيق تعمل (`SingleInstanceGuard`، ملف قفل).
5. تطبيق أي استرجاع (restore) مُجدوَل قبل فتح قاعدة البيانات أصلاً.
6. فتح قاعدة البيانات، أخذ نسخة احتياطية محقَّقة قبل أي ترحيل (migration) على قاعدة بيانات موجودة فعلاً (`migrate_with_pre_backup`)، ثم تشغيل الترحيلات المعلّقة.
7. ضبط إعدادات افتراضية (`settings_repo.ensure_defaults`)، فحص اتساق جلسات البلايستيشن (تعطّل أثناء التشغيل)، إلغاء أي فاتورة مفتوحة فاضية من جلسة سابقة.
8. بناء `AppController`: يعرض `SetupScreen` (أول تشغيل بلا مستخدمين) أو `LoginScreen`، وبعد الدخول يبني `MainWindow`.
9. مؤقّت كل 30 ثانية (`SCHEDULER_INTERVAL_MS`) يشغّل الإقفال التلقائي للأيام المستحقة، ونسخة احتياطية أخيرة عند إغلاق التطبيق (`aboutToQuit`) إن لزم.

### ربط الشاشات (`derby/features/shell/sidebar.py` + `main_window.py`)

قائمة `SECTIONS` في `sidebar.py` تُعرّف كل قسم بـ (مفتاح، تسمية، أيقونة، صلاحية). `MainWindow._build_screens` يبني ويضيف فقط الشاشات التي يُسمح بها دور المستخدم الحالي؛ أول قسم مسموح به هو الصفحة الافتراضية بعد الدخول.

### طبقات الكود

- **repos** (`derby/core/db/*_repo.py`): SQL خام فقط عبر `sqlite3`، بدون منطق تجاري.
- **services** (`*_service.py` في كل `features/*`): منطق تجاري خالص (بدون Qt)، قابل للاختبار بدون واجهة. كل دالة تمرّر `commit=False` لمكالمات الـ repo وتُنهي بعملية commit واحدة أو rollback عند الخطأ.
- **UI** (شاشات/حوارات PySide2): تستدعي الخدمات فقط، لا تكتب SQL مباشرة.

### السجلات والأخطاء وأماكن البيانات

- قاعدة البيانات: `%APPDATA%\Derby\derby.db` (أو `DERBY_DATA_DIR` للاختبارات/المعاينة).
- السجلات: `%APPDATA%\Derby\logs\derby.log` (تدوير عند 1 ميجابايت، 3 نسخ احتياطية) — `derby/core/utils/error_log.py`. أي استثناء غير متوقَّع يُسجَّل بنص `traceback` فقط (لا قيم متغيّرات محلية، لذلك لا يمكن تسريب PIN عبر الـ log)، ويظهر مربع رسالة عربي فيه زر "نسخ".
- الصور: `derby/features/menu/images.py` (مجلد صور المنتجات تحت `%APPDATA%\Derby`).
- الإيصالات: `derby/features/expenses/receipts.py`.
- النسخ الاحتياطية الافتراضية: `Documents\Derby\Backups` (`paths.default_backup_dir`)، التصدير الافتراضي: `Documents\Derby\Exports`.
- `derby/core/utils/paths.py` هو **الوحدة الوحيدة** المسموح لها بقراءة `%APPDATA%`/`%USERPROFILE%` مباشرة — كل الوحدات الأخرى تمر عبرها (محروس باختبار `test_no_real_user_path_computed_outside_paths_py`).

---

## 3) الشاشات والمميزات

(المفاتيح والتسميات من `derby/features/shell/sidebar.py::SECTIONS` بالترتيب الفعلي؛ كل قسم محمي بدالة صلاحية من `permissions.py`.)

### الرئيسية (`daily_stats` → `DailyStatsScreen` / `daily_stats_service.py`)

- الصفحة الافتراضية لكل الأدوار. تعرض: مبيعات اليوم (من `report_service.build_report` نفسه الذي تستخدمه التقارير)، رسم بياني للمبيعات بالساعة (`sales_by_hour`)، عدد/إجمالي الفواتير المفتوحة، الجلسات الجارية على البلايستيشن، عدد الترابيزات المشغولة/الفاضية، ومقارنة % مع نفس اليوم الأسبوع الماضي وبالأمس (`ComparisonStat`).
- زر بدء فاتورة جديدة (تيك أواي مباشرة) وفتح الطلبات المفتوحة من نفس الشاشة (`open_orders_panel.py`، يصدر `order_opened`/`navigate_requested`).
- متاحة لكل الأدوار؛ أرقام الربح/المصروفات داخلها محجوبة بنفس صلاحية `view_reports` (مالك فقط) إن ظهرت.

### المنيو (`menu` → `MenuScreen`) — مالك فقط (`permissions.can_manage_menu`)

- فئات (`categories_panel.py`)، منتجات مع صورة وسعر، مجموعات إضافات (`addon_groups_panel.py`)، استيراد/تصدير CSV (`csv_importer.py`, `csv_exporter` عبر `csv_export.py`)، بحث عربي مرن (`arabic_search.py`).

### الكاشير (`pos` → `PosScreen`) — المالك والكاشير (`permissions.use_pos`)

- شبكة منتجات (`product_grid.py`, `product_card.py`)، سلة (`cart_panel.py`)، اختيار إضافات (`addon_selection.py`, `addon_dialog.py`)، خصم (`discount_dialog.py` — نسبة أو قيمة ثابتة)، دفع (`payment_dialog.py` — كاش/InstaPay)، فاتورة (`invoice_dialog.py`)، إلغاء فاتورة مفتوحة (`cancel_order_ui.py`)، موافقة المالك بـ PIN للإجراءات المقيّدة (`owner_pin_prompt.py` + `owner_approval.resolve_approver`).
- يعتمد على `orders_service.py` لكل منطق الفاتورة، و`stock_service.py` لخصم المخزون عند الدفع.

### الترابيزات (`tables` → `TablesScreen`) — المالك والكاشير لعرضها، المالك فقط لإدارتها (`manage_tables`)

- بطاقة لكل ترابيزة (مشغولة/فاضية)، نقل الفاتورة بين ترابيزة/جهاز بلايستيشن (`move_order_dialog.py` يستخدم `orders_service.move_order`)، إدارة الترابيزات (`tables_management_panel.py` — إضافة/تعطيل/إعادة ترتيب).

### سجل المبيعات (`sales_log` → `SalesLogScreen`) — كلاهما، لكن الكاشير مقيَّد باليوم الحالي فقط (`view_sales_today` مقابل `view_sales_all_dates` للمالك)

- قائمة الفواتير المدفوعة/الملغاة/المُبطَلة مع تفاصيلها.

### البلايستيشن (`playstation` → `PlaystationScreen`) — المالك والكاشير (`use_ps`)، إدارة الأجهزة للمالك فقط (`manage_ps_devices`)

- بطاقة لكل جهاز: بدء/تبديل نمط (Single/Multi)/إيقاف جلسة، مؤقّت مبني من `started_at_utc` (يصمد أمام إعادة تشغيل التطبيق)، ضبط وقت البدء بالتراجع (`ps_adjust_start_dialog.py`, يحتاج موافقة مالك)، تنبيه "جلسة طويلة" (`ps_long_session_hours`). إدارة الأجهزة والأسعار في `ps_device_management_panel.py`.

### المخزون (`inventory` → `InventoryScreen`) — مالك فقط (`manage_inventory`)

- أصناف المخزون (وحدة، كمية حالية، حد أدنى، متوسط تكلفة)، وصفات لكل منتج/إضافة (`recipe_editor_dialog.py`)، مشتريات وموردين (`purchases_repo.py`, `suppliers_repo.py`)، هالك (waste)، جرد (stocktake)، إعادة حساب الكمية (`stock_service.recompute_current_qty`).

### الخزنة (`drawer` → `DrawerScreen`) — كلاهما لعرضها (`view_drawer`/`manage_drawer`)، مراجعة البضاعة للمالك فقط (`view_goods_review`)

- فتح الخزنة برصيد ابتدائي، إيداع/سحب، رد نقدي، جرد كاش مع مقارنة الفرق بالمتوقَّع (`drawer_service.record_count`)، قسم "مراجعة البضاعة" (قيمة المخزون، الأصناف تحت الحد الأدنى، الأصناف بكمية سالبة، مديونيات موردين غير مدفوعة).

### المصروفات (`expenses` → `ExpensesScreen`) — مالك فقط (`can_access_expenses`/`manage_expenses`)

- فئات مصروفات، مصروفات دورية (شهرية، تذكير تلقائي عند الدخول كمالك عبر `RecurringDueDialog`)، إيصالات مرفقة (`receipt_viewer_dialog.py`)، إبطال/استبدال مصروف.

### المستلزمات (`supplies` → `SuppliesScreen`) — كلاهما (`view_supplies`)، إدخال تكلفة حقيقية وتحويلها لمصروف للمالك فقط (`manage_supplies_costs`)

- قائمة أشياء "مطلوب شراؤها" بأولوية (عادي/مستعجل) وحالة (مطلوب/تم الشراء/أُلغي).

### التقارير (`reports` → `ReportsScreen`) — مالك فقط (`can_access_reports`/`view_reports`/`export_data`)

- تقرير يومي/شهري/مدى مخصّص، تصدير CSV/Excel/PDF (`export_panel.py`, `export_service.py`, `export_worker.py` — يعمل في خيط منفصل)، تقرير الربح (`view_profit_report`).

### الإعدادات (`settings` → `SettingsScreen`) — مالك فقط (`can_access_settings`)، 6 تبويبات:

1. **عام** (`general_settings_form.py`): اسم المقهى، وقت الإقفال، حد أدنى دقائق بلايستيشن، خطوة التقريب، مدة القفل التلقائي.
2. **المستخدمون** (`users_management.py`): إضافة/تعطيل مستخدم، تعيين/تغيير PIN.
3. **التحديثات** (`update_check_panel.py`): زر الفحص اليدوي الوحيد الذي يصل الإنترنت.
4. **النسخ الاحتياطي والإقفال** (`backup_closing_panel.py`): كل إعدادات الإقفال/النسخ/واتساب + إجراءات (نسخ الآن، إقفال اليوم، إعادة محاولة المجلد الثاني، استرجاع، قائمة الإقفالات).
5. **عن البرنامج** (`about_panel.py`).
6. **أدوات متقدمة** (`advanced_tools_panel.py` → `go_live_cleanup_dialog.py`/`go_live_cleanup_service.py`): "تصفية بيانات التجربة" — حذف كل بيانات التجربة التشغيلية قبل الانطلاق الفعلي.

### تسجيل الدخول / PIN / القفل

- `SetupScreen` (`derby/features/auth/setup_screen.py`): يظهر فقط إن لم يوجد أي مستخدم بعد، لإنشاء أول مستخدم مالك.
- `LoginScreen` (`login_screen.py`): تسجيل دخول بـ PIN فقط (بدون اسم مستخدم/كلمة مرور) — الـ PIN يُعرِّف المستخدم لأن الـ PINs فريدة بين المستخدمين النشطين.
- **Lockout عام** (`derby/features/auth/lockout.py`): 5 محاولات خاطئة متتالية تقفل شاشة الدخول 5 دقائق، محفوظ في `settings` فلا يُصفَّر بإعادة تشغيل التطبيق.
- **قفل تلقائي بالخمول** (`idle_filter.py`): يرجع لشاشة الدخول بعد `auto_lock_minutes` دقيقة بلا نشاط.
- موافقة المالك بالـ PIN (`owner_approval.py`) تُستخدم لأي إجراء يحتاج صلاحية مالك يطلبه كاشير (خصم، إلغاء فاتورة بها عناصر، حذف سطر بلايستيشن، ضبط وقت بدء جلسة بالتراجع، تصفية بيانات التجربة) — تشترك في نفس عدّاد lockout.

### الإقفال اليومي، النسخ الاحتياطي، الاسترجاع

انظر القسم 7 بالتفصيل.

### إضافات Phase 11 (قيد التطوير، غير مُصدرة بعد)

أقسام جديدة في الشريط الجانبي، كل واحد محمي بدالة صلاحية من
`permissions.py` (انظر `tests/test_phase11_cross_cutting.py` لكل
مفاتيح الصلاحيات الجديدة):

- **سجل العمليات** (`audit_log` → `AuditLogScreen`, مالك فقط): جدول
  `audit_log` (migration 0012) أصبح append-only فعليًا (triggers تمنع
  UPDATE/DELETE)، بأعمدة جديدة (business_date, user_name, entity_type/
  id, summary_ar, details_json, severity). كل الخدمات تكتب إليه عبر
  `derby/core/audit_service.py` (لا UI يكتب مباشرة)، وفشل الكتابة لا
  يوقف أبدًا العملية التجارية نفسها.
- **النسخ الاحتياطي** (داخل الإعدادات، migration 0013): طبقة نسخ شهرية
  منفصلة (`backup_service.maybe_create_monthly_snapshot`)، إعدادات
  retention/warning/auto-hours جديدة، `BackupsListDialog` (عرض كل نسخة
  بإصدار البرنامج/القاعدة والتحقق)، ومؤشر صحة على الرئيسية
  (`backup_service.external_backup_status`).
- **الورديات والموظفين** (`shifts_employees`): جداول `shifts`،
  `employees`، `attendance`، `payroll_lines`، `payroll_payments`
  (migration 0014). تقرير الوردية (`shift_service.build_shift_report`)
  يُحسب من النافذة الزمنية الحقيقية للوردية (مش من عمود `shift_id` على
  كل صف) فيغطي كل مسارات الكتابة تلقائيًا. دفع الرواتب يعيد استخدام
  `expenses_service` (فئة "مرتبات" جديدة).
- **العملاء** (`customers`): جدولا `customers` و`customer_ledger`
  (append-only بالاتفاق، migration 0015). البيع بالآجل = فاتورة مدفوعة
  بـ `payment_method = NULL` و`customer_id` محدد (لم يُوسَّع قيد
  CHECK على `payment_method`). دفعة عميل نقدية تُسجَّل في جدول جديد
  `extra_drawer_entries` (نفس السبب: CHECK على `drawer_entries.
  entry_type`)، ويُجمع هذا الجدول مع `drawer_entries` بالتوقيت الزمني
  عند حساب الكاش المتوقع (`drawer_service.expected_cash_piasters`).
- **الإضافات** (migration 0016): `discount_presets`، إعدادات تنبيهات
  الرئيسية (`derby/features/dashboard/alerts_service.py` — كل تنبيه
  بدالة صغيرة معزولة بـ try/except خاص بيه)، وعمود `stock_items.
  target_qty` لقائمة إعادة الطلب (`derby/features/inventory/
  reorder_service.py`، يجمع حسب آخر مورد اشتُري منه كل عنصر بدل عمود
  مورد ثابت).

تقرير التفاصيل الكامل: [`docs/PHASE11_REPORT.md`](PHASE11_REPORT.md).

---

## 4) القواعد التجارية (business rules)

### تسعير البلايستيشن (`derby/features/playstation/pricing.py` + `derby/core/utils/money.py`)

- كل جهاز له سعر **Single** وسعر **Multi** بالساعة (قروش/ساعة).
- الدقائق الفعلية = `ceil(ثواني الجلسة / 60)` بحد أدنى دقيقة واحدة (`actual_minutes_from_seconds`).
- **الحد الأدنى للفوترة** (`ps_min_minutes`، افتراضي 30 دقيقة) يُطبَّق **مرة واحدة فقط لكل فاتورة (visit)**، وعند **الإيقاف النهائي (final) فقط**: إذا كان إجمالي الدقائق المفوترة سابقًا على نفس الفاتورة + دقائق هذه الجلسة الأخيرة أقل من الحد الأدنى، تُرفع دقائق هذه الجلسة الأخيرة لتغطية الفرق. **تبديل النمط (Single↔Multi) لا يُطبَّق عليه الحد الأدنى أبدًا** — دقائقه المفوترة = دقائقه الفعلية (`billed_minutes_for_session`).
- السعر لكل سطر جلسة = `السعر بالساعة × الدقائق المفوترة / 60`، مُقرَّب لأقرب `rounding_step_egp` (افتراضي 5 جنيه، تقريب نصف لأعلى) — **كل سطر جلسة يُقرَّب بشكل مستقل وقت فوترته**، فزيارة بها عدة جلسات = مجموع سطور مُقرَّبة كل واحدة على حدة، لا تقريب واحد لإجمالي الزيارة.
- مثال من الكود: 40 ج.م/ساعة × 37 دقيقة = 24.666 ج.م → تُقرَّب إلى 25 ج.م.
- المؤقّت يُحسَب دائمًا من `started_at_utc` المخزَّن (لا عدّاد في الذاكرة)، فيصمد أمام إعادة تشغيل التطبيق أو الجهاز.
- فحص اتساق عند بدء التشغيل (`run_startup_consistency_check`) يُنشئ سطر الفاتورة لأي جلسة توقّفت فعليًا لكن تعطّل التطبيق قبل إنشاء سطرها.

### الفواتير والطلبات (`derby/features/pos/orders_service.py`)

- حالات الطلب: `open → paid`، `open → cancelled`، `paid → void` (الإبطال للمالك فقط، يتطلّب سببًا).
- الفاتورة تخص **ترابيزة أو جهاز بلايستيشن أو تيك أواي** — لا يمكن أن تخص ترابيزة وجهازًا معًا (محروس بـ trigger في قاعدة البيانات نفسها بالإضافة لفحص في طبقة الخدمة).
- نقل الفاتورة (`move_order`) بين ترابيزة/جهاز يُرفض إن كان الهدف مشغولًا (لا دمج أبدًا)، أو إن كان للجهاز المصدر جلسة بلايستيشن جارية (يجب إيقافها أولًا).
- الخصم: المالك يطبّقه مباشرة؛ الكاشير يحتاج PIN مالك دائمًا (`apply_discount_direct`). الخصم بالقيمة الثابتة أو بالنسبة (1-100%)، ولا يمكن أن يتجاوز المجموع الفرعي (subtotal) أبدًا؛ إن قلّت الأصناف بعد تطبيق خصم فالخصم يُقلَّص تلقائيًا ليطابق المجموع الفرعي الجديد.
- الدفع: **كاش أو InstaPay** فقط؛ لا ضرائب، لا رسوم معاملات. الدفع بالكاش فقط يُنشئ سطر `sale_cash` في دفتر الخزنة (InstaPay لا يلمس الخزنة الفعلية أبدًا).
- حذف سطر بلايستيشن من فاتورة (`remove_ps_item`) يحتاج موافقة مالك، ويبقي الجلسة نفسها لكن يعلّمها `voided`.

### اليوم التجاري (business day) (`derby/core/utils/business_date.py`)

- `settings.business_close_time` (افتراضي 23:59) يحدد أين ينتهي "يوم" المقهى.
- إن كان وقت الإقفال ≥ الظهر: اليوم التجاري = التاريخ التقويمي بتوقيت القاهرة، بلا أي تحويل.
- إن كان وقت الإقفال < الظهر (مثلًا 03:00): كل وقت حتى وقت الإقفال نفسه يخص **اليوم السابق**.

### خصم المخزون من الوصفات (`derby/features/inventory/stock_service.py`)

- عند دفع الفاتورة (`orders_service.pay`)، لكل سطر منتج: يُخصم من المخزون بحسب وصفة المنتج (`recipe_lines` لكل `stock_item` بكمية `qty_per_unit × qty`)، **وأيضًا وصفة كل إضافة (addon) على السطر نفسها إن وُجدت**.
- يُسمح أن تصبح الكمية سالبة — المقهى لا يُمنَع من البيع؛ شاشة المخزون المنخفض هي التي تُظهر التحذير.
- تكلفة البيع (`cost_at_sale_piasters`) تُحسَب وتُحفَظ لحظة البيع فقط (snapshot)، فلا يتغيّر ربح الماضي إن تغيّرت التكلفة أو الوصفة لاحقًا.
- الإبطال (void) يعكس كل حركة بيع بحركة `return` معادلة ومضادة — لا تُعدَّل الحركات الأصلية أبدًا (سجل append-only).

### متوسط التكلفة المرجَّح (weighted average cost)

- عند كل مشترى: `متوسط التكلفة الجديد = (الكمية الحالية × متوسط التكلفة الحالي + الكمية المُضافة × تكلفة الوحدة) / (الكمية الحالية + الكمية المُضافة)`.
- الكمية الحالية المستخدمة في الحساب لا تقل عن صفر أبدًا (صنف بكمية سالبة لا "يجرّ" المتوسط لأسفل أكثر).

### دفتر الخزنة (`derby/features/inventory/drawer_service.py`)

- سجل append-only (لا تعديل ولا حذف أبدًا — كل تصحيح سطر جديد).
- **النقد المتوقَّع (expected cash)** = مجموع كل السطور **الحيّة (غير `is_historical`)** بدءًا من آخر سطر "فتح خزنة" حقيقي فقط. السطور التاريخية (من ترحيل الترقية 0009) لا تدخل الحساب الحيّ أبدًا — فالترقية من إصدار سابق لا "تحتسب" كل مبيعات الكاش القديمة كأنها "في الدرج الآن".
- الجرد (`record_count`) يقارن المعدود بالمتوقَّع، يحفظ الفرق، وبشكل اختياري (مفعّل بالافتراضي) يسجّل حركة `count_adjustment` بالفرق فيصبح المتوقَّع = المعدود من الآن فصاعدًا.

### صيغ الربح (`derby/features/reports/report_service.py`)

| المقياس | الصيغة |
|---|---|
| المبيعات الصافية (net sales) | `SUM(total_piasters)` للفواتير **المدفوعة فقط** (باستثناء الملغاة/المُبطَلة) — أي **بعد** خصم كل فاتورة. |
| الأكثر مبيعًا / المبيعات بالفئة | تُحسَب من `order_items` مباشرة، فهي **إجمالية (gross)** — **قبل** خصم الفاتورة — والشاشة تُظهر ذلك بجانبها. |
| ساعات البلايستيشن | `SUM(actual_minutes) / 60` لسطور `ps_time` المتبقية على فاتورة مدفوعة؛ السطر المحذوف (المُبطَل) يفقد صفّه من `order_items` فيخرج تلقائيًا بلا فلتر إضافي. |
| تكلفة البضاعة المباعة (COGS) | مجموع `cost_at_sale_piasters` لكل سطور المنتجات + تكلفة سطور البلايستيشن (تكلفة كهرباء/استهلاك اختيارية للجهاز، صفر افتراضيًا). |
| الربح الإجمالي (gross profit) | `المبيعات الصافية − COGS`. |
| المصروفات التشغيلية (operating expenses) | `إجمالي المصروفات النشطة − مصروفات فئة "مشتريات"` (لتفادي حساب تكلفة المشتريات مرتين: مرة كـ COGS ومرة كمصروف). |
| الربح الصافي (net profit) | `الربح الإجمالي − المصروفات التشغيلية`. |
| الربح (في شاشة الإقفال/لوحة الإحصائيات القديمة) | `المبيعات الصافية − إجمالي المصروفات` (أبسط، نقدي بالكامل، بلا COGS) — **صيغة مختلفة عن net_profit أعلاه**، مستخدَمة في `day_closures`/`closing_text` فقط. |
| متوسط يومي | `المبيعات الصافية ÷ عدد الأيام المنقضية`، حيث عدد الأيام = كامل المدى إن انتهت قبل اليوم الحالي، أو حتى اليوم الحالي ضمنًا إن كانت المدة جارية. |
| صنف منخفض الهامش | هامشه < 10% (أو تكلفته > 0 وهامشه غير معروف) — رقم اختياري وضعه المطوّر، غير مذكور في SPEC.md. |

### مخزون منخفض وهامش منخفض

- صنف "منخفض المخزون": `current_qty ≤ min_qty` (نشط فقط) — `stock_items_repo.list_low_stock`.
- صنف "منخفض الهامش": انظر الجدول أعلاه.

### مصفوفة الصلاحيات (ملخّص من `derby/features/auth/permissions.py`)

| الإجراء | المالك | الكاشير |
|---|---|---|
| إدارة المنيو | ✅ | ❌ |
| الكاشير (بيع) | ✅ | ✅ |
| إدارة الترابيزات | ✅ | ❌ (عرض فقط) |
| خصم مباشر بلا PIN | ✅ | ❌ (يحتاج PIN مالك) |
| إبطال فاتورة مدفوعة | ✅ | ❌ |
| سجل مبيعات كل التواريخ | ✅ | ❌ (اليوم الحالي فقط) |
| إدارة أجهزة البلايستيشن | ✅ | ❌ |
| المصروفات | ✅ | ❌ |
| التقارير / تصدير البيانات | ✅ | ❌ |
| الإعدادات | ✅ | ❌ |
| المستلزمات (عرض/إضافة) | ✅ | ✅ |
| إدخال تكلفة حقيقية للمستلزمات | ✅ | ❌ |
| المخزون/الوصفات/المشتريات/الموردين | ✅ | ❌ |
| عرض الخزنة / فتح/إيداع/سحب/جرد | ✅ | ✅ |
| مراجعة البضاعة (قيمة مخزون، مديونيات) | ✅ | ❌ |
| بيانات التكلفة/الهامش في أي مكان | ✅ | ❌ |

---

## 5) نموذج البيانات

كل الجداول من `derby/core/db/migrations.py` (11 ترحيلًا، مُرقَّمة عبر `PRAGMA user_version`):

| الجدول | الغرض | أهم الأعمدة |
|---|---|---|
| `users` | المستخدمون | `role` (owner/cashier)، `pin_hash`/`pin_salt`، `failed_attempts`، `locked_until_utc` |
| `settings` | مفتاح/قيمة لكل الإعدادات | `key`, `value` (نص دائمًا) |
| `audit_log` | سجل تدقيق لكل إجراء مهم | `action`, `details`, `user_id` |
| `categories` | فئات المنيو | `name`, `sort_order` |
| `products` | منتجات المنيو | `price_piasters`, `image_file`, `needs_price_review` |
| `addon_groups` / `addons` | مجموعات الإضافات وإضافاتها | `min_select`/`max_select`, `price_delta_piasters` |
| `product_addon_groups` | ربط منتج↔مجموعة إضافات | |
| `tables` | الترابيزات | `name`, `sort_order` |
| `orders` | الفواتير/الطلبات | `status`, `table_id`/`device_id` (حصري)، `subtotal/discount/total_piasters`, `payment_method`, `business_date` |
| `order_items` | سطور الفاتورة | `kind` (product/ps_time), `unit_price_snapshot_piasters`, `cost_at_sale_piasters`, `ps_session_id` |
| `order_item_addons` | إضافات كل سطر | `price_delta_snapshot_piasters` |
| `ps_devices` | أجهزة البلايستيشن | `single_rate.../multi_rate_piasters_per_hour`, `hourly_cost_piasters` |
| `ps_sessions` | جلسات البلايستيشن | `mode`, `started_at_utc`/`stopped_at_utc`, `actual_minutes`, `billed_minutes`, `is_final` |
| `expense_categories` | فئات المصروفات | |
| `recurring_expenses` | قوالب مصروفات دورية شهرية | `day_of_month`, `last_generated_month` |
| `expenses` | المصروفات | `amount_piasters`, `status` (active/void), `replaced_by_id` |
| `day_closures` | إقفالات يومية | `net_sales_piasters`, `profit_piasters`, `backup_*_status`, `stale` |
| `backup_log` | سجل كل محاولة نسخ احتياطي | `kind`, `target` (primary/secondary), `sha256`, `verified` |
| `supplies` | قائمة مستلزمات مطلوب شراؤها | `priority`, `status`, `cost_piasters`, `expense_id` |
| `stock_items` | أصناف المخزون | `unit`, `current_qty`, `min_qty`, `avg_cost_piasters` (كلها REAL) |
| `suppliers` | الموردون | `phone`, `notes` |
| `purchases` / `purchase_lines` | فواتير الشراء وسطورها | `total_cost_piasters`, `is_paid` |
| `recipe_lines` | وصفة كل منتج/إضافة | `owner_type` (product/addon), `qty_per_unit` |
| `stock_movements` | حركات المخزون | `movement_type` (purchase/sale/waste/adjustment/return), `qty_delta`, `business_date` |
| `drawer_entries` | دفتر الخزنة (append-only) | `entry_type`, `amount_delta_piasters`, `is_historical` |
| `drawer_counts` | جرد الخزنة | `expected_piasters`, `counted_piasters`, `difference_piasters` |

### جدول الترحيلات (migrations)

| # | الاسم | يضيف |
|---|---|---|
| 1 | `_migration_0001_initial` | `users`, `settings`, `audit_log` |
| 2 | `_migration_0002_menu` | `categories`, `products`, `addon_groups`, `addons`, `product_addon_groups` |
| 3 | `_migration_0003_cashier` | `tables`, `orders`, `order_items`, `order_item_addons`, فهارس، ترابيزات افتراضية |
| 4 | `_migration_0004_playstation` | `ps_devices`, `ps_sessions`, عمود `order_items.ps_session_id`، triggers حصرية ترابيزة/جهاز |
| 5 | `_migration_0005_expenses` | `expense_categories`, `recurring_expenses`, `expenses` |
| 6 | `_migration_0006_closing` | `day_closures`, `backup_log`، إعدادات الإقفال الافتراضية |
| 7 | `_migration_0007_supplies` | `supplies` |
| 8 | `_migration_0008_order_label` | عمود `orders.label` (تسمية تيك أواي) |
| 9 | `_migration_0009_inventory` | `stock_items`, `suppliers`, `purchases`, `purchase_lines`, `recipe_lines`, `stock_movements`, `drawer_entries`, `drawer_counts` + أعمدة تكلفة + تعبئة رجعية (backfill) لحركات الخزنة |
| 10 | `_migration_0010_stock_movement_business_date` | عمود `stock_movements.business_date` + تعبئة رجعية بنفس قاعدة اليوم التجاري |
| 11 | `_migration_0011_drawer_entries_is_historical_repair` | إصلاح دفاعي لعمود `is_historical` إن غاب (انحراف واقعي حدث في بيئة تطوير، موصوف في تعليق الكود) |

### ملاحظات حول البيانات

- **كل قيمة نقدية مخزَّنة كعدد صحيح من القروش** (`*_piasters`) — إلا كميات المخزون (`current_qty`, `min_qty`, `qty_per_unit`, `qty_delta`) وتكلفة الوحدة (`avg_cost_piasters`, `unit_cost_snapshot_piasters`) التي هي REAL لأنها جرامات/مليلترات/قطع أو كسور قرش.
- **الطوابع الزمنية** (`*_at_utc`) نصوص ISO-8601 بتوقيت UTC، تُحوَّل لتوقيت أفريقيا/القاهرة فقط عند العرض (`time_utils.py`).
- **اليوم التجاري** (`business_date`) نص تاريخ (`YYYY-MM-DD`) محسوب بقاعدة `business_date.py`، ويُخزَّن على `orders` (فقط بعد الدفع)، `expenses`، و`stock_movements`.

---

## 6) الإعدادات

كل المفاتيح من `derby/core/db/settings_repo.py::DEFAULTS` (+ `_LAZY_DEFAULTS` المحلولة وقت أول تشغيل فعلي لا وقت استيراد الوحدة):

| المفتاح | الافتراضي | من يغيّره | يؤثر على |
|---|---|---|---|
| `cafe_name` | `""` | مالك (الإعدادات: عام) | اسم المقهى في الهيدر ونص الإقفال/واتساب |
| `business_close_time` | `"23:59"` | مالك | حدود اليوم التجاري في كل مكان |
| `ps_min_minutes` | `"30"` | مالك | الحد الأدنى لفوترة جلسة بلايستيشن |
| `rounding_step_egp` | `"5"` | مالك | خطوة تقريب سعر جلسة بلايستيشن |
| `ps_long_session_hours` | `"6"` | — (لا واجهة تعديل مرئية في `general_settings_form.py`، يُقرَأ فقط) | تنبيه "جلسة طويلة" في شاشة البلايستيشن |
| `whatsapp_number` | `""` | مالك (تبويب النسخ/الإقفال) | رقم استقبال تقرير الإقفال عبر واتساب |
| `backup_folder_primary` | `Documents\Derby\Backups` (محسوب وقت أول تشغيل حقيقي) | مالك | مجلد النسخة الاحتياطية الأساسي |
| `backup_folder_secondary` | `""` | مالك | مجلد نسخة احتياطية ثانٍ اختياري (يُحذَّر إن كان على نفس القرص) |
| `auto_lock_minutes` | `"10"` | مالك | مدة الخمول قبل القفل التلقائي |
| `update_manifest_url` | ثابت في الكود (`DEFAULT_UPDATE_MANIFEST_URL`) | لا واجهة تعديل مرئية؛ القيمة تُملأ افتراضيًا عند `ensure_defaults` | عنوان ملف فحص التحديثات |
| `login_failed_attempts` / `login_locked_until_utc` | `"0"` / `""` | النظام تلقائيًا | قفل تسجيل الدخول العام |
| `closing_enabled` | `"1"` | مالك | تفعيل/تعطيل الإقفال اليومي التلقائي |
| `backup_keep_count` | `"30"` | مالك | عدد النسخ الاحتياطية اليومية المحفوظة قبل حذف الأقدم |
| `whatsapp_method` | `"desktop"` أو محسوب حسب إصدار ويندوز وقت أول تشغيل حقيقي | مالك | ديسكتوب/متصفح/نسخ للحافظة |
| `last_exit_backup_utc` | `""` | النظام تلقائيًا | متابعة آخر نسخة احتياطية عند الخروج |
| `app_first_run_date` | `""` | النظام تلقائيًا (مرة واحدة) | نقطة انطلاق حساب الإقفالات المستحقة |
| `next_invoice_no` | `"1"` | النظام تلقائيًا | ترقيم الفواتير المتسلسل |

---

## 7) النسخ الاحتياطي والاسترجاع والتحديث

### النسخ الاحتياطي (`derby/features/closing/backup_service.py`)

- يستخدم **SQLite Backup API** (`sqlite3.Connection.backup`) لا نسخ ملف خام، فلا يتأثر بنسخ أثناء كتابة متزامنة.
- بعد النسخ: **تحقّق (verify)**: `PRAGMA integrity_check`، تطابق `PRAGMA user_version`، وتطابق عدد صفوف جداول `users, orders, order_items, expenses, ps_sessions` مع لقطة (`snapshot`) أُخذت قبل النسخ.
- **مسارين**: أساسي (primary) وثانوي (secondary) اختياري — الثانوي يُنسخ من ملف الأساسي المُتحقَّق منه (بمقارنة SHA-256) لا بنسخة SQLite مستقلة، إلا إذا فشل الأساسي فيحاول الثانوي نسخة مستقلة.
- **تدوير**: يحذف الأقدم بعد `backup_keep_count` (اليومي) أو 10 (اليدوي، ثابت `MANUAL_KEEP_COUNT`).
- أسماء الملفات: `derby-YYYY-MM-DD.db` (يومي)، `derby-manual-YYYYMMDD-HHMMSS.db` (يدوي).
- نسخة احتياطية محقَّقة إلزامية قبل: أي ترحيل (migration) على قاعدة بيانات موجودة فعلًا، وقبل "تصفية بيانات التجربة" — إن فشل التحقّق، العملية **لا تُنفَّذ أبدًا**.

### ملاحظة هامة: الصور والإيصالات

- يوجد دالة `backup_service.mirror_folder()` ومنطق في `restore_service.offer_mirror_restore()` يتوقّع وجود مجلد `<مجلد النسخة>\files\images` و`\files\receipts` بجانب ملف `.db` ليعيد نسخها عند **الاسترجاع**.
- **لكن لا يوجد في الكود أي مكان يكتب هذا المجلد `files\images`/`files\receipts` فعليًا أثناء أخذ نسخة احتياطية** — لا في `run_backup_pair` ولا في `close_or_rebuild_day` ولا أي مكان آخر تم فحصه. هذه مغايرة فعلية عن CLAUDE.md الذي يقول "Backups (Phase 7) must include the images folder... and the receipts folder" وعن docs/SPEC.md الذي يذكر "including the images/receipts mirror" في وصف Phase 7. **الكود الفعلي لا ينسخ هذين المجلدين احتياطيًا تلقائيًا** — انظر القسم 10.

### الإقفال اليومي (`derby/features/closing/closing_service.py`)

- مؤقّت كل 30 ثانية + لحاق (catchup) عند بدء التشغيل يحسب كل الأيام التجارية المستحقة (التي مرّ وقت إقفالها ولا يوجد لها صف `day_closures`)، محدودة بسقف 60 يومًا لحاقًا واحدًا.
- كل إقفال يبني: تقرير اليوم + تقرير الشهر حتى هذا اليوم، نص تقرير جاهز لواتساب (`closing_text.py`)، زوج نسخ احتياطي، ويحفظ صفًا في `day_closures`.
- **التقادم (staleness)**: إقفال سابق (ضمن آخر 14 يومًا) تُعاد مقارنته بأرقامه الحيّة؛ إن تغيّرت (مثلًا فاتورة أُبطلت بعد الإقفال) يُعلَّم `stale`.
- **نسخة احتياطية عند الخروج**: إن لم تُؤخذ نسخة أساسية محقَّقة منذ أكثر من 6 ساعات، يُنشئ نسخة عند إغلاق التطبيق (بحد زمني 15 ثانية لا تعطيل الخروج أكثر).

### الاسترجاع (`derby/features/closing/restore_service.py` + `restore_dialog.py`)

- الاسترجاع **مُجدوَل (staged)**: يضع علامة (marker file) + نسخة أمان من القاعدة الحالية، ويُطبَّق فعليًا في **بداية التشغيل التالي، قبل فتح قاعدة البيانات**.
- عند التطبيق: ملف النسخة المختارة يستبدل `derby.db` الحالي، ثم تشغيل الترحيلات العادي يتولى ترقية قاعدة بيانات قديمة الإصدار تلقائيًا (استرجاع من إصدار أقدم ثم ترقية عبر الترحيلات نفسها — لا منطق ترحيل مخصّص للاسترجاع).
- خيار اختياري في حوار الاسترجاع لنسخ الصور/الإيصالات مرة أخرى **فقط إن وُجد** مجلد `files\images`/`files\receipts` بجانب ملف النسخة المختار (انظر الملاحظة أعلاه — هذا المجلد لا يُنشأ تلقائيًا بالكود الحالي).

### فحص التحديثات (`derby/core/updates/update_check.py` + `version_logic.py`)

- **الملف الوحيد** في التطبيق الذي يعمل طلب شبكة، ولا يُشغَّل إلا بنقرة المالك على "فحص التحديثات".
- طلب HTTPS فقط (يرفض أي رابط غير https)، مهلة 5 ثوانٍ، بلا إعادة محاولة، في خيط منفصل (`QThread`).
- عنوان الفحص الافتراضي (ثابت في الكود، `DEFAULT_UPDATE_MANIFEST_URL`): `https://raw.githubusercontent.com/Dabash99/derpy_cashier/releases/version.json` — يُنشر على فرع orphan اسمه `releases` في نفس المستودع، لا يحتوي كودًا.
- شكل `version.json` المتوقَّع: `{"version": "...", "notes": "...", "download_url": "...", "sha256": "<64 hex>"}`. يُرفض الملف إن كان `download_url` ليس من استضافات GitHub المسموحة (`github.com`, `objects.githubusercontent.com`, `raw.githubusercontent.com`) أو `sha256` ليس 64 حرفًا سداسي عشريًا.
- عند وجود إصدار أحدث: زر فتح صفحة التحميل (`webbrowser.open`/`os.startfile` على رابط التحميل، لا تحميل تلقائي).

---

## 8) البناء والإصدار

### التشغيل من المصدر

```bat
run.bat
```
أو مباشرة:
```bash
.venv\Scripts\python.exe -m derby
```

### البناء

```bat
build.bat
```
يستدعي `tools/build.py` الذي (بحسب تعليقات `derby.spec`) يُشغّل `ruff` + كل مجموعة الاختبارات + اختبارات السياسة (`test_policy.py`) أولًا، ويفشل عند أي خطأ، ثم يبني عبر PyInstaller بمواصفات `derby.spec` (**one-dir**، لا UPX، `console=False`)، ثم يتحقّق من المخرجات (`--selftest`، حجم/DLLs، SHA-256).
- `derby.spec` يستثني كل وحدات PySide2 غير المستخدمة (`QtWebEngine*`, `Qt3D*`, `QtCharts`, إلخ) فلا تُستخرج أصلًا إلى `dist/Derby`.

### المثبّت (installer)

- `installer/derby.iss` (Inno Setup 6)، 64-bit فقط، يثبّت في `{autopf}\Derby` (`Program Files`، لا مجلد خاص بالمستخدم — جهاز مشترك، تثبيت واحد).
- إلغاء التثبيت **لا يلمس أبدًا** `%APPDATA%\Derby` أو `Documents\Derby`.
- يُبنى عبر `tools/build_installer.py` (يُشغّل `tools/write_installer_version.py` ثم `ISCC.exe`).

### الإصدار وأدوات الإصدار (`tools/*`)

- رقم الإصدار مصدره الوحيد `derby/__init__.py::__version__`، ويُطابقه `pyproject.toml` (محروس باختبار `test_version_matches_pyproject`).
- `tools/make_release.py` هو أمر الإصدار الموحَّد: يشغّل بوابات الجودة (quality gates)، يبني التطبيق والمثبّت، يكتب `release/version.json` + `release/public/` (نسخة آمنة للنشر، يفحصها `tools/check_public_files.py` كحارس خصوصية)، ثم يطبع خطوات يدوية (أو، مع `--publish`، يستدعي `tools/publish_release.py`).
- `tools/publish_release.py`: git/gh فقط — لا يستخدم Python لعمل طلبات شبكة؛ يدفع `version.json`/`README.md`/`releases-history.json` إلى فرع orphan باسم `releases` **عبر clone منفصل** تحت `build/releases-clone` (لا الـ checkout الأساسي)، وينشئ GitHub Release مع المثبّت و`SHA256SUMS.txt`. يُشغَّل يدويًا بواسطة المالك فقط.

---

## 9) الاختبارات

- **106 ملف اختبار** تحت `tests/`، تحتوي **708 دالة `test_*`** (عدّ مباشر بـ `grep`).
- التشغيل: `.venv\Scripts\python.exe -m pytest`.
- التغطية تشمل، بحسب أسماء الملفات: كل الـ repos (`test_*_repo.py`)، منطق التسعير الخالص (`test_ps_pricing.py`, `test_money.py`, `test_discount_math.py`)، خدمات الطلبات/المخزون/الخزنة/المصروفات/الإقفال/الاسترجاع، شاشات الواجهة الرئيسية (`test_*_screen.py`, `test_gui_login_flow.py`, `test_pos_gui_flow.py`)، الصلاحيات لكل شاشة (`test_*_permissions.py`)، سياسة المشروع نفسها (`test_policy.py`)، البناء/الإصدار (`test_installer_assets.py`, `test_version_json.py`, `test_publish_release.py`, `test_check_public_files.py`)، الخطوط/الثيم/التباين (`test_fonts.py`, `test_theme_contrast.py`, `test_rtl_and_fonts.py`)، وسيناريوهات ترحيل/ترقية محدَّدة (`test_migration_0010_stock_business_date.py`, `test_restore_then_migrate_phase9.py`, `test_pre_migration_backup.py`).
- لا يوجد ملف اختبار واحد لـ `whatsapp.py` باسم مختلف — موجود (`test_whatsapp.py`) ويغطي بناء الروابط والتحقق من الرقم والنسخ للحافظة، لا يغطي فتح واتساب ديسكتوب فعليًا (لا يمكن أتمتته بدون واتساب مثبّت).
- لا يوجد اختبار مخصَّص لحساب الربح "القديم" (`net_sales - expenses` في `closing_service`) مقابل "الصيغة الجديدة" (`net_profit_piasters` مع COGS) للتأكد من أن الفرق بينهما مقصود ومفهوم في كل الشاشات — انظر القسم 10.

---

## 10) القيود والمعروف نقصه

- **لا توجد تعليقات `TODO`/`FIXME`/`XXX`** في `derby/` (بحث شامل) — أي عمل مؤجَّل مذكور فقط في `docs/SPEC.md` (الطباعة/شاشة المطبخ "مؤجَّلة") وCHANGELOG.
- **عدم تطابق فعلي بين الوثائق والكود**: CLAUDE.md وSPEC.md يذكران أن النسخ الاحتياطي اليومي "يشمل مجلد الصور والإيصالات"، لكن الكود الفعلي (`backup_service.run_backup_pair`/`close_or_rebuild_day`) **لا ينسخ** `images`/`receipts` احتياطيًا أبدًا — فقط ملف `.db`. منطق استرجاعهما (`mirror_folder`, `offer_mirror_restore`) موجود ويعمل **فقط إن وُجد** مجلد `files\images`/`files\receipts` بجانب ملف النسخة بشكل يدوي من المالك؛ لا آلية تلقائية تُنشئه. هذا يعني أن استرجاع نسخة احتياطية تلقائية لا يُعيد صور المنتجات أو إيصالات المصروفات.
- **أداة "تصفية بيانات التجربة" (`go_live_cleanup_service.py`) لا تشمل جداول المخزون/الخزنة** (`stock_items`, `stock_movements`, `purchase_lines`/`purchases`, `recipe_lines`, `suppliers`, `drawer_entries`, `drawer_counts`) — قائمة `_TABLES_IN_DELETE_ORDER` تعود لما قبل Phase 9 ولم تُحدَّث. تشغيلها على قاعدة بيانات بها بيانات مخزون/خزنة تجريبية سيحذف الطلبات/المصروفات لكنه **يترك** حركات المخزون وسجل الخزنة التجريبي كما هو.
- **صيغتان مختلفتان للربح**: `report_service.ReportResult.profit_piasters` (= صافي مبيعات − كل المصروفات، بلا COGS) تُستخدم في نص الإقفال اليومي/`day_closures`، بينما `net_profit_piasters` (مع COGS وخصم فئة "مشتريات" من المصروفات) تُستخدم في شاشة التقارير. لا تعليق صريح يشرح الفرق للمالك على الشاشة نفسها (الكود يفرّق بينهما لكن هذا قد يُلبس على مستخدم غير مطوّر يقرأ رقمين مختلفين لـ"الربح" في شاشتين مختلفتين).
- **`ps_long_session_hours`** موجود كإعداد فعّال (يُستخدم في `ps_service._long_session_seconds`) لكن **لا توجد له واجهة تعديل** في `general_settings_form.py` أو أي شاشة أخرى تم فحصها — لا يمكن للمالك تغييره إلا بتعديل قاعدة البيانات مباشرة.
- **لا طباعة فواتير ولا شاشة مطبخ (kitchen ticket)**: مؤجّلة بوضوح في `docs/SPEC.md` (Phase 5، "مؤجَّلة").
- **مخاطر أداء محتملة مع بيانات كبيرة**: `report_service.build_report` يحمّل كل الفواتير المدفوعة في المدى المطلوب بالكامل في الذاكرة (`reports_repo.list_paid_orders_in_range`) ثم يُجمِّعها بـ Python، لا بـ SQL `GROUP BY`. لمقهى صغير هذا غير ملحوظ، لكن تقرير "مخصّص" على مدى طويل (أشهر/سنوات) مع آلاف الفواتير سيكبر خطيًا في الاستهلاك والوقت. لم يُلاحَظ أي اختبار أداء (`test_menu_screen_performance.py` يغطي المنيو فقط، لا التقارير).
- **أمان PIN**: التجزئة PBKDF2-HMAC-SHA256 بـ150,000 تكرار وملح عشوائي لكل مستخدم (`pin_hash.py`) — مناسب لرقم سري قصير (4-6 أرقام). لا قفل خاص بكل مستخدم على حدة؛ الـ lockout عام لكل محاولات تسجيل الدخول في التطبيق (مصمَّم كذلك عمدًا حسب تعليق الكود).
- **بيانات شخصية**: رقم واتساب المالك (`whatsapp_number`) يُخزَّن كنص عادي في جدول `settings` غير مُشفَّر — منطقي لأنه ليس سرًّا (المالك يملك الرقم)، لكنه موجود كـ plain text في ملف `.db` الذي يُنسخ احتياطيًا وقد يُرسَل بين أجهزة.
- **لا حماية كلمة مرور على قاعدة البيانات نفسها**: `derby.db` ملف SQLite عادي غير مُشفَّر على القرص؛ أي من يصل لملف النظام يمكنه فتحه بأي أداة SQLite، فيرى كل الفواتير/التجزئات المُشفَّرة للـ PIN (لا PIN نفسه) والمصروفات. هذا متوقَّع لتطبيق محلي بالكامل على جهاز كاشير واحد، لكنه يستحق الذكر.
- **اختبار واتساب غير شامل**: الاختبارات الموجودة تغطي بناء الروابط/التحقق فقط، لا السلوك الفعلي لفتح واتساب ديسكتوب (غير قابل للأتمتة في CI).

---

## 11) مصطلحات

| المصطلح العربي | الاسم/الهوية في الكود |
|---|---|
| المالك | `ROLE_OWNER` (`users_repo.py`) |
| الكاشير | `ROLE_CASHIER` |
| إحصائيات اليوم / الرئيسية | `daily_stats` قسم، `DailyStatsScreen`, `daily_stats_service.py` |
| المنيو | `menu` قسم، `MenuScreen` |
| الكاشير (شاشة البيع) | `pos` قسم، `PosScreen`, `orders_service.py` |
| الترابيزات | `tables` قسم، `TablesScreen` |
| سجل المبيعات | `sales_log` قسم، `SalesLogScreen` |
| البلايستيشن | `playstation` قسم، `PlaystationScreen`, `ps_service.py` |
| المخزون | `inventory` قسم، `InventoryScreen`, `stock_service.py` |
| الخزنة | `drawer` قسم، `DrawerScreen`, `drawer_service.py` |
| مراجعة البضاعة | `GOODS_REVIEW_*` نصوص، داخل `DrawerScreen` |
| المصروفات | `expenses` قسم، `ExpensesScreen` |
| المستلزمات | `supplies` قسم، `SuppliesScreen` |
| التقارير | `reports` قسم، `ReportsScreen`, `report_service.py` |
| الإعدادات | `settings` قسم، `SettingsScreen` |
| الإقفال اليومي | `day_closures` جدول، `closing_service.py` |
| النسخ الاحتياطي | `backup_log` جدول، `backup_service.py` |
| الاسترجاع | `restore_service.py`, `restore_dialog.py` |
| فحص التحديثات | `update_check.py`, `update_check_panel.py` |
| تصفية بيانات التجربة | `go_live_cleanup_service.py` |
| اليوم التجاري | `business_date` عمود/دالة |
| القروش | `piasters` وحدة النقود (1 ج.م = 100 قرش) |
| وحيد (جلسة بلايستيشن فردية) | `MODE_SINGLE` |
| جماعي (جلسة بلايستيشن متعددة) | `MODE_MULTI` |
| تسوية جرد الدرج | `TYPE_COUNT_ADJUSTMENT` (`drawer_repo.py`) |

---

## 12) Open points

- لم يُفتح ملف قاعدة بيانات حقيقي أو نسخة احتياطية فعلية في هذا التحليل — كل ما في الأقسام أعلاه مستنتج من الكود والاختبارات فقط.
- `ps_long_session_hours` يبدو إعدادًا بلا واجهة تعديل مرئية حاليًا؛ لم يتم تتبّع كل حوار/شاشة في المشروع للتأكد المطلق من عدم وجود واجهة له في مكان آخر (مثل حوار إدارة الأجهزة) — تم فحص `general_settings_form.py` فقط باعتباره الموضع المنطقي.
- لم تُفحَص كل شاشة/حوار في `derby/features/*` سطرًا بسطر (المشروع يحتوي أكثر من 140 ملف Python) — الوصف في القسم 3 مبني على قراءة الخدمات (`*_service.py`) والشاشات الرئيسية لكل قسم وربطها بـ`sidebar.py`/`main_window.py`، وليس كل حوار فرعي (مثل كل حوار تأكيد صغير) تمت قراءته.
- لم يتم تشغيل التطبيق فعليًا أو تنفيذ `pytest`/`ruff` في هذا التحليل — هذا تحليل كود ثابت (static) فقط، كما طلب النطاق "قراءة فقط".
- عدد المستخدمين "حتى 3 كاشيرات" المذكور في `docs/SPEC.md` هو توقّع تشغيلي فقط — لا حد فعلي في مخطط قاعدة البيانات أو الكود يفرض هذا العدد.
