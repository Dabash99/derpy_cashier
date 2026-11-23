# سجل التغييرات / Changelog

## Unreleased (Phase 11)

### بالعربي

- سجل العمليات (Audit log): شاشة جديدة للمالك فقط تعرض كل العمليات
  الحساسة (تسجيل دخول، إبطال فاتورة، خصومات، تعديل أسعار، مصروفات،
  الخزنة، النسخ الاحتياطي، ...) مع فلاتر بالتاريخ والمستخدم والعملية
  والخطورة، وتفاصيل قبل/بعد، وتصدير CSV/Excel. السجل لا يُحذف تلقائيًا
  أبدًا، ومحمي داخل قاعدة البيانات نفسها من أي تعديل أو حذف.

### English

- Audit log (سجل العمليات): a new owner-only screen listing every
  sensitive action (logins, voids, discounts, price changes, expenses,
  drawer moves, backups, ...) with date/user/action/severity filters,
  before/after detail, and CSV/Excel export. The log is never
  auto-deleted and is protected at the database level against any
  update or delete.

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
