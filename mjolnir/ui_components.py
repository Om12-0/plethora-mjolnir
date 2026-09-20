"""UI components for PLETHORA MJOLNIR.

Facade re-exporting modular components from :mod:`mjolnir_ui`.
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple
from PySide6 import QtCore, QtGui
from PySide6.QtCore import Qt

from mjolnir import styles
from mjolnir_ui import (
    ActionPanel, ActionRow, Capsule, ClipboardRow, NoticeRow, ResultItemWidget,
    badge_colors, calc_html, capsule_row, category_of, command_html,
    confirmation_html, format_mtime, format_size, highlight_html, keycaps,
    launch_html, make_shadow, match_capsule, match_percent, position_text,
    preview_html,
)

__all__ = [
    "ResultItemWidget", "NoticeRow", "ClipboardRow",
    "ActionPanel", "ActionRow",
    "Capsule", "capsule_row", "match_capsule", "match_percent", "position_text",
    "preview_html", "calc_html", "launch_html", "command_html", "confirmation_html",
    "highlight_html", "keycaps", "format_size", "format_mtime", "make_shadow",
    "category_of", "badge_colors", "app_icon", "icon_bytes",
]

_ICON_CACHE: Dict[Tuple, QtGui.QIcon] = {}


def app_icon(theme=None, size: Optional[int] = None,
             device_pixel_ratio: float = 1.0) -> QtGui.QIcon:
    """The Mjolnir icon, painted from design tokens (never from hex literals)."""
    base = int(size or styles.ICON_SIZE)
    ratio = max(1.0, float(device_pixel_ratio or 1.0))
    key = (styles.icon_signature(theme), base, round(ratio, 3))
    cached = _ICON_CACHE.get(key)
    if cached is not None:
        return cached

    palette = styles.icon_palette(theme)
    physical = max(1, int(round(base * ratio)))
    pixmap = QtGui.QPixmap(physical, physical)
    pixmap.fill(Qt.transparent)
    painter = QtGui.QPainter(pixmap)
    try:
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.scale(physical / float(base), physical / float(base))
        gradient = QtGui.QLinearGradient(0, 0, base, base)
        gradient.setColorAt(0.0, QtGui.QColor(palette["start"]))
        gradient.setColorAt(1.0, QtGui.QColor(palette["end"]))
        painter.setBrush(QtGui.QBrush(gradient))
        painter.setPen(Qt.NoPen)
        margin = base * 6.0 / 64.0
        radius = base * 14.0 / 64.0
        span = base - 2 * margin
        painter.drawRoundedRect(QtCore.QRectF(margin, margin, span, span),
                                radius, radius)
        painter.setPen(QtGui.QColor(palette["fg"]))
        font = painter.font()
        font.setBold(True)
        font.setPixelSize(max(1, int(round(base * 34.0 / 64.0))))
        painter.setFont(font)
        painter.drawText(QtCore.QRectF(0, 0, base, base), Qt.AlignCenter, "M")
    finally:
        painter.end()

    pixmap.setDevicePixelRatio(ratio)
    icon = QtGui.QIcon(pixmap)
    _ICON_CACHE[key] = icon
    return icon


def icon_bytes(icon: QtGui.QIcon, size: int = 64) -> bytes:
    """PNG bytes of *icon* at *size*: a stable fingerprint for tests/snapshots."""
    image = icon.pixmap(QtCore.QSize(int(size), int(size))).toImage()
    buffer = QtCore.QBuffer()
    buffer.open(QtCore.QIODevice.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())
