"""Sanity checks for the generated user-guide PDF and its HTML builder.
Not a full re-render (that needs Qt's PDF pipeline, dev-time only); if
this fails, re-run:
    .venv\\Scripts\\python.exe tools\\make_user_guide_pdf.py
"""
from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PDF_PATH = PROJECT_ROOT / "release" / "دليل-استخدام-ديربي.pdf"


def test_guide_pdf_exists_and_is_a_valid_pdf():
    assert PDF_PATH.exists()
    data = PDF_PATH.read_bytes()
    assert data.startswith(b"%PDF")
    assert len(data) > 1000


def test_guide_html_builder_covers_every_major_section(qapp):
    import sys

    sys.path.insert(0, str(PROJECT_ROOT / "tools"))
    from make_user_guide_pdf import build_guide_html

    html = build_guide_html()
    for marker in (
        "أول تشغيل",
        "المستخدمون",
        "إعداد المنيو",
        "الترابيزات",
        "شاشة الكاشير",
        "البلاي ستيشن",
        "المصروفات",
        "التقارير والتصدير",
        "الإقفال اليومي",
        "الاسترجاع",
        "التحديثات",
        "ورقة مرجعية سريعة",
        "قبل الافتتاح",
    ):
        assert marker in html, "missing section: {0}".format(marker)
