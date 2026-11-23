# سجل التغييرات / Changelog

## Unreleased (Phase 11)

### بالعربي

- سجل العمليات (Audit log): شاشة جديدة للمالك فقط تعرض كل العمليات
  الحساسة (تسجيل دخول، إبطال فاتورة، خصومات، تعديل أسعار، مصروفات،
  الخزنة، النسخ الاحتياطي، ...) مع فلاتر بالتاريخ والمستخدم والعملية
  والخطورة، وتفاصيل قبل/بعد، وتصدير CSV/Excel. السجل لا يُحذف تلقائيًا
  أبدًا، ومحمي داخل قاعدة البيانات نفسها من أي تعديل أو حذف.
- النسخ الاحتياطي: نسخة شهرية منفصلة عن اليومية، إعدادات جديدة (عدد
  النسخ الشهرية، أيام التنبيه، نسخة إضافية كل N ساعة)، شاشة "عرض النسخ
  الاحتياطية" تعرض كل نسخة بتاريخها وحجمها وإصدار البرنامج وقاعدة
  البيانات وهل تم التحقق منها، وحذف يدوي للنسخ القديمة حسب السياسة.
  مؤشر على الرئيسية لحالة آخر نسخة خارجية (سليمة/متأخرة/غير موجودة).
- الورديات والموظفين: فتح/إغلاق وردية (مرتبطة بفتح/جرد الخزنة)، تسليم
  وردية لمستخدم آخر في خطوة واحدة، تقرير وردية كامل (مبيعات حسب طريقة
  الدفع، فواتير مبطلة، خصومات، مصروفات نقدية، الفرق في الخزنة). شاشة
  الموظفين (إضافة/تعديل/تعطيل)، تسجيل حضور وانصراف، سلف واستقطاعات
  وحوافز، وكشف رواتب شهري يسجّل الدفع كمصروف عادي.
- العملاء والآجل: بيع بالآجل كطريقة دفع جديدة (لا يدخل في حساب الكاش في
  الخزنة)، حد ائتمان اختياري يحتاج تجاوزه رقم سري المالك، تسجيل دفعات
  العملاء (نقدي/إنستاباي)، كشف حساب بالرصيد المتراكم، تذكير واتساب،
  وبطاقة على الرئيسية لإجمالي المستحق والمتأخر.
- خصومات محفوظة (قابلة للاختيار عند الدفع مباشرة)، تنبيهات الرئيسية
  (جلسة بلايستيشن طويلة، عملاء متأخرون، تأخر النسخة الخارجية، مخزون
  ناقص، الدرج لم يُفتح، وردية مفتوحة من يوم سابق، فواتير موردين متأخرة)
  قابلة للتعطيل كل واحدة على حدة، وقائمة إعادة الطلب من المخزون الناقص
  مجمّعة حسب المورد مع كمية مقترحة، قابلة للنسخ كنص.

### English

- Audit log (سجل العمليات): a new owner-only screen listing every
  sensitive action (logins, voids, discounts, price changes, expenses,
  drawer moves, backups, ...) with date/user/action/severity filters,
  before/after detail, and CSV/Excel export. The log is never
  auto-deleted and is protected at the database level against any
  update or delete.
- Backups: a separate monthly snapshot tier alongside the daily one,
  new settings (monthly keep count, warning days, an optional extra
  backup every N hours), a "عرض النسخ الاحتياطية" screen listing every
  backup with its date/size/app version/schema version/verified flag,
  and a manual "delete old backups per policy" action. A home-screen
  indicator shows the external backup's health (ok/warning/missing).
- Shifts & employees: open/close a shift (tied to the existing drawer
  open/count), a one-step handover to another user, a full shift
  report (sales by payment method, voids, discounts, cash expenses,
  drawer difference). An employees screen, clock in/out, advances/
  deductions/bonuses, and a monthly payroll sheet whose "record payment"
  files an ordinary expense.
- Customers & credit (آجل): a new credit payment method (never counted
  as cash in the drawer), an optional credit limit that needs the
  owner's PIN to exceed, recording customer payments (cash/InstaPay), a
  running-balance statement, a WhatsApp reminder, and a home-screen tile
  for total/overdue receivables.
- Saved discount presets (selectable directly at checkout), a home-
  screen alerts center (long PS sessions, overdue customers, overdue
  external backup, low stock, drawer not opened, a shift left open,
  overdue supplier invoices) with a per-type on/off setting, and a
  reorder list built from low-stock items, grouped by supplier with a
  suggested quantity, copyable as plain text.

## 1.1.0 — 2026-11-22

### بالعربي

- المخزون والمخازن: تتبّع الكمية والتكلفة لكل مكوّن/خامة، وحركة مخزون
  (دخول/خروج/هالك) مرتبطة بالتاريخ التجاري.
- المشتريات والموردين: تسجيل فواتير الشراء وربطها بالموردين وبتحديث
  المخزون تلقائيًا.
- الوصفات (Recipes): ربط كل منتج بمكوّناته وكمياتها، مع حساب التكلفة
  والهامش (margin) تلقائيًا.
- تقرير الربح: شاشة مخصّصة تجمع صافي المبيعات والمصروفات في ربح واحد
  واضح.
- الخزنة (Cash Drawer): فتح/إغلاق الخزنة، عدّ الكاش، ومراجعة البضاعة
  (goods review) كجزء من الإقفال.
- الشاشة الرئيسية الجديدة: لوحة إحصائيات اليوم مع تدفّق فتح فاتورة
  جديدة مباشرة من الشاشة الرئيسية، وقسم للطلبات المفتوحة.
- إضافات على الإقفال اليومي ورسالة واتساب: تفاصيل أوسع في رسالة
  التقرير المُرسلة للمالك.
- إصلاح حساب تكلفة الهالك (waste) بحيث يُحسب على اليوم التجاري الصحيح
  بدل اليوم التقويمي.
- إصلاح تعطّل تسجيل الدخول الناتج عن عدم تطابق مخطط جدول `drawer_entries`
  (`is_historical`) بعد الترقية.
- تنظيف تلقائي لمرة واحدة فقط لذاكرة التخزين المؤقت (cache) عند الترقية
  من 1.0.0 إلى 1.1.0، لتفادي أي كاش قديم من قبل هذا الإصدار.
- رابط فحص التحديثات أصبح ثابتًا في الكود (بدل حقل قابل للتعديل في
  الإعدادات)، فيستمر زر "فحص التحديثات" في العمل بدون أي ضبط إضافي من
  المالك.

### English

- Inventory & stock: quantity and cost tracking per ingredient/item, and
  stock movements (in/out/waste) tied to the business day.
- Purchases & suppliers: record purchase invoices linked to suppliers,
  automatically updating stock.
- Recipes: link each product to its ingredients and quantities, with
  automatic cost and margin calculation.
- Profit report: a dedicated screen combining net sales and expenses
  into a single, clear profit figure.
- Cash drawer (الخزنة): open/close the drawer, cash count, and a goods
  review as part of daily closing.
- New home dashboard: today's stats plus a new-invoice flow directly
  from the home screen, and an open-orders section.
- Daily close / WhatsApp additions: richer detail in the report message
  sent to the owner.
- Fixed waste-cost calculation to use the correct business day instead
  of the calendar day.
- Fixed a login crash caused by a `drawer_entries.is_historical` schema
  mismatch after upgrading.
- One-time cache clear on upgrade from 1.0.0 to 1.1.0 only, to avoid any
  stale cache left over from the previous build.
- The update-check URL is now a fixed constant in code instead of an
  editable Settings field, so the "Check for Updates" button keeps
  working with no extra setup by the owner.
