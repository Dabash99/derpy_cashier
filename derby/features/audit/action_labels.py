"""Arabic labels for audit_log action codes. Deliberately a plain dict,
not a translation framework -- any action code missing here still shows
(as its raw snake_case text) rather than crashing the screen, since
audit entries from an older release, or a future one, can carry a code
this file doesn't know about yet.
"""
from __future__ import annotations

from typing import Dict

ACTION_LABELS: Dict[str, str] = {
    # Auth
    "login": "تسجيل دخول",
    "login_failed": "محاولة دخول خاطئة",
    "login_lockout": "قفل الدخول (محاولات كثيرة)",
    "user_created": "إضافة مستخدم",
    "user_renamed": "تعديل اسم مستخدم",
    "user_pin_changed": "تغيير الرقم السري",
    "user_deactivated": "تعطيل مستخدم",
    "user_reactivated": "تفعيل مستخدم",
    # Orders / POS
    "order_voided": "إبطال فاتورة",
    "order_cancelled": "إلغاء طلب",
    "order_moved": "نقل طلب",
    "discount_applied": "تطبيق خصم",
    "discount_removed": "إلغاء خصم",
    "discount_preset_used": "تطبيق خصم محفوظ",
    "ps_line_removed": "حذف سطر بلايستيشن",
    "permission_denied": "محاولة بدون صلاحية",
    # Menu
    "product_price_changed": "تغيير سعر منتج",
    "menu_csv_import": "استيراد منيو من ملف",
    # PlayStation
    "ps_session_started": "بدء جلسة بلايستيشن",
    "ps_session_mode_changed": "تغيير وضع الجلسة",
    "ps_session_stopped": "إيقاف جلسة بلايستيشن",
    "ps_session_start_adjusted": "تعديل وقت بدء الجلسة",
    "ps_device_added": "إضافة جهاز بلايستيشن",
    "ps_device_renamed": "تعديل اسم جهاز",
    "ps_device_rate_changed": "تغيير تعريفة جهاز",
    "ps_consistency_repair": "إصلاح تلقائي لجلسة بلايستيشن",
    # Expenses
    "expense_created": "تسجيل مصروف",
    "expense_voided": "إبطال مصروف",
    "expense_replaced": "تعديل مصروف",
    "recurring_template_changed": "تعديل مصروف دوري",
    "recurring_skipped": "تخطي مصروف دوري",
    "expense_category_changed": "تعديل نوع مصروف",
    # Supplies / purchases / stock
    "supply_added": "إضافة مستلزم",
    "supply_updated": "تعديل مستلزم",
    "supply_bought": "شراء مستلزم",
    "supply_dropped": "إلغاء مستلزم",
    "supply_converted_to_expense": "تحويل مستلزم لمصروف",
    "purchase_recorded": "تسجيل مشترى",
    "purchase_marked_paid": "تسديد مشترى",
    "stock_waste": "تسجيل هالك",
    "stocktake": "جرد مخزون",
    # Drawer
    "drawer_opened": "فتح الدرج",
    "drawer_deposit": "إيداع في الدرج",
    "drawer_withdrawal": "سحب من الدرج",
    "drawer_refund": "استرجاع نقدي",
    "drawer_count": "جرد الدرج",
    # Backups / closing / updates
    "day_closed": "إقفال اليوم",
    "backup_now": "نسخة احتياطية يدوية",
    "backup_external": "نسخة احتياطية خارجية",
    "backup_retry_secondary": "إعادة محاولة النسخة الخارجية",
    "db_restored": "استرجاع نسخة احتياطية",
    "db_restore_failed": "فشل استرجاع نسخة احتياطية",
    "backup_retention_cleanup": "حذف نسخ قديمة حسب السياسة",
    "update_check": "فحص تحديثات",
    "go_live_cleanup": "تصفية بيانات التجربة",
    "settings_changed": "تغيير إعدادات",
    # Shifts / employees / payroll (Part C)
    "shift_opened": "فتح وردية",
    "shift_closed": "إغلاق وردية",
    "shift_handover": "تسليم وردية",
    "employee_created": "إضافة موظف",
    "employee_updated": "تعديل موظف",
    "employee_deactivated": "تعطيل موظف",
    "attendance_clock_in": "تسجيل حضور",
    "attendance_clock_out": "تسجيل انصراف",
    "attendance_corrected": "تعديل حضور/انصراف",
    "payroll_advance": "تسجيل سلفة",
    "payroll_deduction": "تسجيل استقطاع",
    "payroll_bonus": "تسجيل حافز",
    "payroll_paid": "دفع مرتب",
    # Customers / credit (Part D)
    "customer_created": "إضافة عميل",
    "customer_updated": "تعديل عميل",
    "customer_deactivated": "تعطيل عميل",
    "credit_sale": "بيع بالآجل",
    "credit_sale_void_reversed": "عكس بيع بالآجل (إبطال)",
    "customer_payment_recorded": "تسجيل دفعة عميل",
    "credit_limit_exceeded_approved": "تجاوز حد الآجل (بموافقة المالك)",
    # Extras (Part E)
    "discount_preset_changed": "تعديل خصم محفوظ",
    "alert_setting_changed": "تعديل تنبيهات الرئيسية",
    "reorder_target_changed": "تعديل مستوى إعادة الطلب",
}


def label_for_action(action: str) -> str:
    return ACTION_LABELS.get(action, action.replace("_", " "))
