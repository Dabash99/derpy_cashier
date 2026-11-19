"""Dev-time ONLY (Part B6). Renders docs/USER-GUIDE-AR.md's content as a
printable, branded, RTL, A4 PDF via the app's own Qt PDF pipeline
(derby/features/reports/export_service.py -- the same QPdfWriter +
QTextDocument path report exports already use, so no new rendering
code, and page numbers come for free).

This does not parse the Markdown file -- it is a hand-written HTML
mirror of the same content, kept in sync by hand when the guide
changes (matching how every other PDF in this app is built from a
hand-rolled HTML string, not a template engine).

Usage:
    .venv\\Scripts\\python.exe tools\\make_user_guide_pdf.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from PySide2.QtWidgets import QApplication  # noqa: E402

from derby.core.theme import tokens  # noqa: E402
from derby.features.reports.export_service import _logo_header_html, render_html_to_pdf  # noqa: E402

OUT_PATH = PROJECT_ROOT / "release" / "دليل-استخدام-ديربي.pdf"


def _section(title: str, body_html: str) -> str:
    return "<h2 style='color:{color};'>{title}</h2>{body}".format(color=tokens.AMBER_900, title=title, body=body_html)


def _p(text: str) -> str:
    return "<p>{0}</p>".format(text)


def _ul(items) -> str:
    return "<ul>{0}</ul>".format("".join("<li>{0}</li>".format(item) for item in items))


def build_guide_html() -> str:
    sections = []

    sections.append(_section(
        "أول تشغيل وكلمة سر المالك",
        _p(
            "عند أول تشغيل تظهر شاشة \"إعداد البرنامج لأول مرة\": اسم الكافيه، "
            "اسم صاحب الكافيه، ثم رقم سري من ٤ إلى ٦ أرقام لحساب المالك الأول. "
            "بعدها، تسجيل الدخول في كل مرة بالرقم السري فقط -- لا يوجد اسم "
            "مستخدم منفصل. عدة محاولات خاطئة متتالية تُقفل الدخول مؤقتًا."
        ),
    ))

    sections.append(_section(
        "المستخدمون والأرقام السرية",
        _p(
            "من الإعدادات &larr; المستخدمون (المالك فقط): أضف كاشيرًا جديدًا "
            "برقم سري مختلف عن كل الأرقام الأخرى. الكاشير لا يرى الإعدادات "
            "ولا المصروفات ولا التقارير."
        ),
    ))

    sections.append(_section(
        "إعداد المنيو",
        _ul([
            "إضافة قسم: اكتب الاسم واضغط \"إضافة قسم\".",
            "إضافة منتج: القسم، الاسم بالعربي، السعر، وصورة اختياريًا.",
            "الإضافات (Add-ons): مجموعات اختيار تُربط بمنتج معين (مثل الحجم).",
            "استيراد CSV بالأعمدة: category, name_ar, name_en, price, currency, image_file "
            "-- يصنَّف كل صف قبل التطبيق (جديد / موجود / غير صحيح).",
            "شارة \"⚠ السعر يحتاج مراجعة\" تظهر على أي منتج سعره غير مؤكد.",
        ]),
    ))

    sections.append(_section(
        "الترابيزات",
        _p(
            "شبكة بكل الترابيزات (فاضية / مشغولة مع الإجمالي ووقت الفتح). "
            "الضغط على ترابيزة فاضية يفتح طلبًا جديدًا عليها. \"نقل الفاتورة\" "
            "ينقل طلبًا مفتوحًا بين ترابيزة وأخرى أو من/إلى جهاز بلاي ستيشن."
        ),
    ))

    sections.append(_section(
        "شاشة الكاشير",
        _p(
            "أضف أصنافًا من الشبكة (مع اختيار الإضافات لو وُجدت). عدّل الكمية "
            "بـ +/‑. \"خصم\" لفتح نافذة خصم بسبب. زر \"دفع\" الكبير يفتح "
            "نافذة الدفع: نقدي أو إنستاباي، ثم تظهر الفاتورة."
        ),
    ))

    sections.append(_section(
        "البلاي ستيشن",
        _ul([
            "حدد سعر الساعة (سينجل/مالتي) لكل جهاز من \"إدارة الأجهزة\" أولًا.",
            "\"بدء Single/Multi\" يبدأ عدادًا حيًا؛ \"تغيير الوضع\" يبدّل أثناء الجلسة.",
            "الحد الأدنى ٣٠ دقيقة لكل زيارة (قابل للتغيير) يُطبّق مرة واحدة فقط "
            "عند الإيقاف النهائي، وليس عند كل تبديل وضع.",
            "السعر النهائي لكل جلسة/فترة يُقرّب لأقرب ٥ جنيه (قابل للتغيير) بمفرده.",
            "\"نقل الفاتورة\" يدمج طلب البلاي ستيشن مع طلب ترابيزة أو العكس.",
        ]),
    ))

    sections.append(_section(
        "المصروفات",
        _p(
            "أضف مصروفًا بالنوع والمبلغ والتاريخ (وصورة إيصال اختياريًا). "
            "\"المصروفات الثابتة\" (كالإيجار الشهري) تظهر كتذكير عند يوم "
            "الاستحقاق، ويحتاج تأكيدك يدويًا قبل الإضافة."
        ),
    ))

    sections.append(_section(
        "التقارير والتصدير",
        _p(
            "يومي / شهري / فترة مخصصة: المبيعات، عدد الفواتير، متوسط الفاتورة، "
            "طرق الدفع، الأصناف الأكثر طلبًا (قبل الخصم)، المبيعات حسب القسم، "
            "ساعات البلاي ستيشن، المصروفات، والربح. تصدير CSV أو Excel أو PDF."
        ),
    ))

    sections.append(_section(
        "الإقفال اليومي والنسخ الاحتياطي وواتساب",
        _p(
            "من الإعدادات &larr; النسخ الاحتياطي والإقفال: المجلد الأساسي "
            "ومجلد ثانٍ اختياري (يُفضَّل فلاشة منفصلة). عند إغلاق اليوم يُبنى "
            "تقرير نصي وتُؤخذ نسخة احتياطية محقَّقة فعليًا. اكتب رقم واتساب "
            "<b>مع كود الدولة</b> (20 لمصر). \"تم الإرسال\" تعليم يدوي بالكامل."
        ),
    ))

    sections.append(_section(
        "النسخ الاحتياطي والاسترجاع",
        _p(
            "الاسترجاع (الإعدادات &larr; الاسترجاع): اختر ملف نسخة احتياطية، "
            "يتأكد البرنامج من سلامتها، ثم تُطبَّق عند إعادة التشغيل. لو تعطّل "
            "الجهاز بالكامل: ثبّت البرنامج على جهاز جديد، انسخ آخر نسخة "
            "احتياطية من الفلاشة، وافتح شاشة الاسترجاع."
        ),
    ))

    sections.append(_section(
        "التحديثات",
        _p(
            "زر \"فحص التحديثات\" في الإعدادات <b>يدوي فقط</b> -- البرنامج لا "
            "يتصل بالإنترنت تلقائيًا في أي وقت آخر."
        ),
    ))

    sections.append(_section(
        "ورقة مرجعية سريعة للكاشير",
        _ul([
            "تسجيل الدخول بالرقم السري.",
            "اختر ترابيزة فاضية أو تيك أواي أو جهاز بلاي ستيشن.",
            "أضف الأصناف واختر الإضافات عند الطلب.",
            "عند الدفع: \"دفع\" ← نقدي أو إنستاباي.",
            "البلاي ستيشن: \"بدء\" عند البدء، \"إيقاف\" عند الانتهاء.",
            "نقل المكان؟ استخدم \"نقل الفاتورة\"، لا تفتح طلبًا جديدًا.",
        ]),
    ))

    sections.append(_section(
        "قبل الافتتاح -- قائمة تحقق نهائية",
        _ul([
            "حدّد سعر الساعة لكل جهاز بلاي ستيشن فعلي.",
            "استبدل أي أسعار أو صور تجريبية بالمنيو الحقيقي الكامل.",
            "راجع كل شارات \"⚠ السعر يحتاج مراجعة\".",
            "اضبط وقت إغلاق اليوم التجاري الصحيح.",
            "اكتب رقم واتساب صحيح مع كود الدولة (20).",
            "اختر مجلدًا ثانيًا على فلاشة منفصلة واختبره.",
            "جرّب إغلاق يوم واسترجاع نسخة فعليًا قبل الاعتماد عليه.",
            "غيّر كل الأرقام السرية الافتراضية.",
        ]),
    ))

    body = "".join(sections)
    return (
        "<html><body dir='rtl' style='font-family: Cairo; font-size: 11pt; color:{text};'>"
        "{logo_header}"
        "<h1>دليل استخدام ديربي</h1>"
        "{body}"
        "</body></html>"
    ).format(text=tokens.TEXT_PRIMARY, logo_header=_logo_header_html(), body=body)


def main() -> int:
    app = QApplication.instance() or QApplication([])
    _ = app
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    render_html_to_pdf(build_guide_html(), OUT_PATH)
    print("wrote {0} ({1} bytes)".format(OUT_PATH.relative_to(PROJECT_ROOT), OUT_PATH.stat().st_size))
    return 0


if __name__ == "__main__":
    sys.exit(main())
