"""All user-facing Arabic text lives here, in one place.

Keeping every string in one module makes it easy for a non-programmer to
find and tweak wording later without touching any logic.
"""
from __future__ import annotations

APP_TITLE = "ديربي"

# --- First-run setup screen ---------------------------------------------
SETUP_TITLE = "إعداد البرنامج لأول مرة"
SETUP_CAFE_NAME_LABEL = "اسم الكافيه"
SETUP_OWNER_NAME_LABEL = "اسم صاحب الكافيه"
SETUP_OWNER_PIN_LABEL = "الرقم السري (٤ إلى ٦ أرقام)"
SETUP_OWNER_PIN_CONFIRM_LABEL = "تأكيد الرقم السري"
SETUP_SUBMIT_BUTTON = "إنشاء الحساب والبدء"
SETUP_ERROR_CAFE_NAME_REQUIRED = "من فضلك اكتب اسم الكافيه"
SETUP_ERROR_OWNER_NAME_REQUIRED = "من فضلك اكتب اسم صاحب الكافيه"
SETUP_ERROR_PIN_FORMAT = "الرقم السري يجب أن يكون من ٤ إلى ٦ أرقام فقط"
SETUP_ERROR_PIN_MISMATCH = "الرقمان السريان غير متطابقين"

# --- Login screen ---------------------------------------------------------
LOGIN_TITLE = "تسجيل الدخول"
LOGIN_ENTER_PIN = "ادخل الرقم السري"
LOGIN_BUTTON = "دخول"
LOGIN_CLEAR_BUTTON = "مسح"
LOGIN_ERROR_WRONG_PIN = "الرقم السري غير صحيح"
LOGIN_ERROR_LOCKED = "تم قفل الدخول مؤقتًا بسبب محاولات خاطئة كثيرة. حاول مرة أخرى بعد {minutes} دقيقة و {seconds} ثانية"
LOGIN_ERROR_NO_ACTIVE_USERS = "لا يوجد مستخدمون نشطون. تواصل مع صاحب الكافيه"

# --- Single instance -------------------------------------------------------
ALREADY_RUNNING_TITLE = "البرنامج يعمل بالفعل"
ALREADY_RUNNING_MESSAGE = "البرنامج مفتوح بالفعل على هذا الجهاز. لا يمكن فتح نسخة ثانية في نفس الوقت"

# --- Sidebar / shell --------------------------------------------------------
SIDEBAR_MENU = "المنيو"
SIDEBAR_CASHIER = "الكاشير"
SIDEBAR_TABLES = "الترابيزات"
SIDEBAR_PLAYSTATION = "البلاي ستيشن"
SIDEBAR_EXPENSES = "المصروفات"
SIDEBAR_REPORTS = "التقارير"
SIDEBAR_SETTINGS = "الإعدادات"

PLACEHOLDER_COMING_SOON = "قريبًا — المرحلة {phase}"

HEADER_LOCK_BUTTON = "قفل"
HEADER_USER_ROLE_OWNER = "صاحب الكافيه"
HEADER_USER_ROLE_CASHIER = "كاشير"

AUTO_LOCK_RETURN_TO_LOGIN = "تم قفل الشاشة بسبب عدم النشاط"

# --- Settings screen ---------------------------------------------------------
SETTINGS_TITLE = "الإعدادات"
SETTINGS_TAB_GENERAL = "عام"
SETTINGS_TAB_USERS = "المستخدمون"
SETTINGS_TAB_UPDATES = "التحديثات"
SETTINGS_SAVE_BUTTON = "حفظ"
SETTINGS_SAVED_MESSAGE = "تم حفظ الإعدادات بنجاح"
SETTINGS_CAFE_NAME_LABEL = "اسم الكافيه"
SETTINGS_CLOSE_TIME_LABEL = "وقت إغلاق اليوم التجاري"
SETTINGS_PS_MIN_MINUTES_LABEL = "أقل مدة محسوبة للبلاي ستيشن (دقيقة)"
SETTINGS_ROUNDING_STEP_LABEL = "تقريب السعر لأقرب (جنيه)"
SETTINGS_WHATSAPP_NUMBER_LABEL = "رقم واتساب (مع كود الدولة)"
SETTINGS_BACKUP_PRIMARY_LABEL = "مجلد النسخة الاحتياطية الأساسي"
SETTINGS_BACKUP_SECONDARY_LABEL = "مجلد النسخة الاحتياطية الاحتياطي (اختياري)"
SETTINGS_AUTO_LOCK_LABEL = "القفل التلقائي بعد (دقيقة)"
SETTINGS_UPDATE_URL_LABEL = "رابط ملف التحديثات"
SETTINGS_ERROR_INVALID_NUMBER = "من فضلك اكتب رقمًا صحيحًا"
SETTINGS_ERROR_INVALID_TIME = "من فضلك اكتب وقتًا صحيحًا بصيغة س:د"
SETTINGS_ERROR_INVALID_WHATSAPP = "رقم واتساب يجب أن يكون أرقامًا فقط"

# --- Users management (Settings, owner only) ---------------------------------
USERS_TITLE = "المستخدمون"
USERS_ADD_BUTTON = "إضافة مستخدم"
USERS_NAME_LABEL = "الاسم"
USERS_ROLE_LABEL = "الصلاحية"
USERS_ROLE_OWNER = "صاحب الكافيه"
USERS_ROLE_CASHIER = "كاشير"
USERS_PIN_LABEL = "الرقم السري"
USERS_PIN_CONFIRM_LABEL = "تأكيد الرقم السري"
USERS_RENAME_BUTTON = "تعديل الاسم"
USERS_CHANGE_PIN_BUTTON = "تغيير الرقم السري"
USERS_DEACTIVATE_BUTTON = "تعطيل"
USERS_REACTIVATE_BUTTON = "تفعيل"
USERS_ACTIVE_LABEL = "نشط"
USERS_INACTIVE_LABEL = "معطّل"
USERS_ERROR_NAME_REQUIRED = "من فضلك اكتب اسم المستخدم"
USERS_ERROR_PIN_FORMAT = "الرقم السري يجب أن يكون من ٤ إلى ٦ أرقام فقط"
USERS_ERROR_PIN_MISMATCH = "الرقمان السريان غير متطابقين"
USERS_ERROR_PIN_TAKEN = "هذا الرقم السري مستخدم من مستخدم آخر، اختر رقمًا مختلفًا"
USERS_ERROR_CANNOT_DEACTIVATE_SELF = "لا يمكنك تعطيل حسابك الحالي"
USERS_ERROR_CANNOT_DEACTIVATE_LAST_OWNER = "لا يمكن تعطيل آخر صاحب كافيه نشط"
USERS_SAVED_MESSAGE = "تم الحفظ بنجاح"

# --- Update check (Settings, owner only) -------------------------------------
UPDATE_CHECK_BUTTON = "فحص التحديثات"
UPDATE_CHECK_NO_URL_HINT = "لم يتم ضبط رابط التحديثات بعد"
UPDATE_CHECK_CHECKING = "جاري الفحص..."
UPDATE_CHECK_UP_TO_DATE = "أنت على آخر نسخة"
UPDATE_CHECK_NEW_VERSION_AVAILABLE = "يوجد إصدار جديد: {version}"
UPDATE_CHECK_OPEN_DOWNLOAD_PAGE = "فتح صفحة التحميل"
UPDATE_CHECK_FAILED_OFFLINE = "تعذر الاتصال بالإنترنت. حاول مرة أخرى لاحقًا"
UPDATE_CHECK_FAILED_SSL = "تعذّر الاتصال الآمن. حدّث ويندوز أو نزّل التحديث يدويًا"
UPDATE_CHECK_FAILED_INVALID_RESPONSE = "رد غير صالح من رابط التحديثات"
UPDATE_CHECK_REJECTED_DOWNLOAD_HOST = "رابط التحميل غير موثوق، تم رفضه"

# --- Generic ----------------------------------------------------------------
GENERIC_OK = "تم"
GENERIC_CANCEL = "إلغاء"
GENERIC_SAVE = "حفظ"
GENERIC_ERROR_TITLE = "خطأ"
GENERIC_SUCCESS_TITLE = "تم بنجاح"
