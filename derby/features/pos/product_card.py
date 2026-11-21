"""A single product tile for the cashier's product grid: a fixed 4:3
cover-cropped image (rounded top corners) over a name that wraps to at
most two lines (elided with "…" only past that) and the price in an
amber pill. One component, reused everywhere the app shows this picker,
so every card looks identical regardless of source image size.

Image handling is deliberately cheap for a weak Windows 7 PC: the source
pixmap comes from derby/features/menu/images.py's own thumbnail cache (a
160px-longest-side JPEG, already decoded once), and the cropped/rounded
result for a given (file, width, height) is cached here too, so scrolling
or re-filtering the grid never re-scales or re-paints the same image.
"""
from __future__ import annotations

from typing import List, Optional

from PySide2.QtCore import QSize, Qt, Signal
from PySide2.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPixmap
from PySide2.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from derby.core.theme import tokens
from derby.core.theme.fonts import CAIRO_FAMILY
from derby.core.theme.icons import icon_mark_pixmap
from derby.core.theme.styled import enable_styled_background
from derby.core.utils.money import format_egp
from derby.features.menu import images

CARD_WIDTH = 168
IMAGE_HEIGHT = 126  # 4:3 at CARD_WIDTH
IMAGE_RADIUS = tokens.RADIUS_LG
NAME_MAX_LINES = 2
NAME_FONT_PIXEL_SIZE = tokens.FONT_SIZE_BODY


def _name_font() -> QFont:
    # A fixed, explicit font (family + exact pixel size) rather than
    # reading the label's own .font(): at construction time the label
    # has not yet been polished against the app stylesheet, so its
    # .font() would under-report the size that actually ends up
    # rendered -- and wrap_to_lines() must measure the exact font that
    # paints, or text wrapped to fit 2 lines here can still overflow to
    # a visual 3rd line once Qt re-wraps at the real (larger) size.
    font = QFont(CAIRO_FAMILY)
    font.setPixelSize(NAME_FONT_PIXEL_SIZE)
    return font

_card_image_cache: "dict[tuple, QPixmap]" = {}
_CARD_IMAGE_CACHE_MAX_ITEMS = 256


def _top_rounded_rect_path(width: int, height: int, radius: int) -> QPainterPath:
    radius = max(0, min(radius, width // 2, height // 2))
    path = QPainterPath()
    path.moveTo(0, radius)
    path.arcTo(0, 0, 2 * radius, 2 * radius, 180, -90)
    path.lineTo(width - radius, 0)
    path.arcTo(width - 2 * radius, 0, 2 * radius, 2 * radius, 90, -90)
    path.lineTo(width, height)
    path.lineTo(0, height)
    path.closeSubpath()
    return path


def _cover_crop(source: QPixmap, width: int, height: int) -> QPixmap:
    scaled = source.scaled(width, height, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    x = max(0, (scaled.width() - width) // 2)
    y = max(0, (scaled.height() - height) // 2)
    return scaled.copy(x, y, width, height)


def _render_card_image(source: Optional[QPixmap], width: int, height: int, radius: int) -> QPixmap:
    result = QPixmap(width, height)
    result.fill(Qt.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setClipPath(_top_rounded_rect_path(width, height, radius))
    if source is None or source.isNull():
        # AMBER_100 rather than the page's own cream background -- a
        # pure-cream placeholder was visually indistinguishable from the
        # page behind it, so a card with no photo looked like a floating
        # icon instead of an intentional placeholder tile.
        painter.fillRect(0, 0, width, height, QColor(tokens.AMBER_100))
        bean = icon_mark_pixmap("mono-black", min(width, height) // 2)
        if not bean.isNull():
            bx = (width - bean.width()) // 2
            by = (height - bean.height()) // 2
            painter.drawPixmap(bx, by, bean)
    else:
        painter.drawPixmap(0, 0, _cover_crop(source, width, height))
    painter.end()
    return result


def _get_card_image(image_file: Optional[str], width: int, height: int, radius: int) -> QPixmap:
    key = (image_file or "", width, height, radius)
    cached = _card_image_cache.get(key)
    if cached is not None:
        return cached
    source = images.load_thumbnail_pixmap(image_file) if image_file else None
    pixmap = _render_card_image(source, width, height, radius)
    if len(_card_image_cache) >= _CARD_IMAGE_CACHE_MAX_ITEMS:
        _card_image_cache.pop(next(iter(_card_image_cache)))
    _card_image_cache[key] = pixmap
    return pixmap


def wrap_to_lines(text: str, metrics: QFontMetrics, max_width: int, max_lines: int = NAME_MAX_LINES) -> List[str]:
    """Greedy word-wrap into at most `max_lines` lines no wider than
    `max_width`, eliding the last line with "…" if text remains. Falls
    back to character-level breaking for a single word wider than the
    line (long, space-less Arabic names)."""
    words = (text or "").split()
    if not words:
        return [""]

    lines: List[str] = []
    current = ""
    remaining_words = list(words)

    while remaining_words and len(lines) < max_lines:
        word = remaining_words[0]
        candidate = "{0} {1}".format(current, word).strip()
        if metrics.horizontalAdvance(candidate) <= max_width or not current:
            if metrics.horizontalAdvance(word) > max_width and not current:
                # a single word alone is wider than the line -- break it
                # by character instead of overflowing.
                chunk = ""
                for char in word:
                    if metrics.horizontalAdvance(chunk + char) > max_width and chunk:
                        break
                    chunk += char
                current = chunk
                remaining_words[0] = word[len(chunk):]
                if not remaining_words[0]:
                    remaining_words.pop(0)
            else:
                current = candidate
                remaining_words.pop(0)
        else:
            lines.append(current)
            current = ""

    if current:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]

    consumed_words = " ".join(lines).split()
    if remaining_words or consumed_words != words[: len(consumed_words)] or len(words) > len(consumed_words):
        if lines:
            last = lines[-1]
            while last and metrics.horizontalAdvance(last + "…") > max_width:
                last = last[:-1]
            lines[-1] = (last or lines[-1][:1]) + "…"
    return lines or [""]


class ProductCard(QFrame):
    clicked = Signal()

    def __init__(self, name: str, price_piasters: int, image_file: Optional[str] = None, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setProperty("variant", "productCard")
        enable_styled_background(self)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedWidth(CARD_WIDTH)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(tokens.SPACE_2)

        self._image_label = QLabel()
        self._image_label.setFixedSize(CARD_WIDTH, IMAGE_HEIGHT)
        self._image_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._image_label)

        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(tokens.SPACE_2, 0, tokens.SPACE_2, tokens.SPACE_2)
        info_layout.setSpacing(tokens.SPACE_1)

        self._name_label = QLabel()
        self._name_label.setAlignment(Qt.AlignCenter)
        self._name_label.setWordWrap(True)
        self._name_label.setFont(_name_font())
        info_layout.addWidget(self._name_label)

        price_row = QHBoxLayout()
        price_row.addStretch(1)
        self._price_label = QLabel()
        self._price_label.setProperty("variant", "pricePill")
        price_row.addWidget(self._price_label)
        price_row.addStretch(1)
        info_layout.addLayout(price_row)
        info_layout.addStretch(1)

        layout.addLayout(info_layout)

        self._image_file = image_file
        self._image_loaded = False
        self.set_placeholder_image()
        self.set_name(name)
        self.set_price(price_piasters)

    # --- content -------------------------------------------------------

    def set_name(self, name: str) -> None:
        metrics = QFontMetrics(_name_font())
        max_width = CARD_WIDTH - 2 * tokens.SPACE_2
        lines = wrap_to_lines(name or "", metrics, max_width)
        self._name_label.setText("\n".join(lines))

    def set_price(self, price_piasters: int) -> None:
        self._price_label.setText(format_egp(price_piasters))

    def set_placeholder_image(self) -> None:
        self._image_label.setPixmap(_get_card_image(None, CARD_WIDTH, IMAGE_HEIGHT, IMAGE_RADIUS))
        self._image_loaded = False

    def load_image(self) -> None:
        """Called once the card scrolls into view -- see ProductGrid's
        lazy reveal. A no-op if there is no image or it was already
        loaded, so calling it repeatedly while visible is harmless."""
        if self._image_loaded:
            return
        self._image_loaded = True
        if not self._image_file:
            return
        self._image_label.setPixmap(_get_card_image(self._image_file, CARD_WIDTH, IMAGE_HEIGHT, IMAGE_RADIUS))

    def sizeHint(self) -> QSize:  # noqa: N802 -- Qt override
        return QSize(CARD_WIDTH, IMAGE_HEIGHT + 64)

    # --- interaction -----------------------------------------------------

    def mousePressEvent(self, event) -> None:  # noqa: N802 -- Qt override
        super().mousePressEvent(event)
        self.setProperty("pressed", "true")
        self.style().unpolish(self)
        self.style().polish(self)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 -- Qt override
        super().mouseReleaseEvent(event)
        self.setProperty("pressed", "false")
        self.style().unpolish(self)
        self.style().polish(self)
        if self.rect().contains(event.pos()):
            self.clicked.emit()
