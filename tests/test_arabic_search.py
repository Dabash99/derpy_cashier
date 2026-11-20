from __future__ import annotations

from derby.features.menu.arabic_search import normalize_arabic_text, search_matches


def test_normalize_strips_tashkeel():
    assert normalize_arabic_text("قَهْوَة") == normalize_arabic_text("قهوة")


def test_normalize_alef_variants():
    assert normalize_arabic_text("أحمد") == normalize_arabic_text("احمد")
    assert normalize_arabic_text("إحمد") == normalize_arabic_text("احمد")
    assert normalize_arabic_text("آحمد") == normalize_arabic_text("احمد")


def test_normalize_ta_marbuta():
    assert normalize_arabic_text("قهوة") == normalize_arabic_text("قهوه")


def test_search_matches_partial():
    assert search_matches("قهوه", "قهوة باردة") is True
    assert search_matches("احمد", "أحمد علي") is True
    assert search_matches("شاي", "قهوة باردة") is False


def test_empty_query_matches_everything():
    assert search_matches("", "anything") is True
    assert search_matches("   ", "anything") is True
