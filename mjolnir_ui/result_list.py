"""Result list row widgets: search results, quick-jump badges, notices, and clipboard rows."""
from __future__ import annotations

import os
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt

from mjolnir import styles

_DEFAULT_CATEGORY = "OTHER"

_EXT_CATEGORY: Dict[str, str] = {
    ".pdf": "PDF", ".docx": "DOC", ".doc": "DOC", ".rtf": "DOC",
    ".txt": "TEXT", ".md": "MARKDOWN", ".markdown": "MARKDOWN",
    ".py": "PYTHON", ".ipynb": "NOTEBOOK",
    ".js": "JAVASCRIPT", ".jsx": "REACT", ".ts": "TYPESCRIPT", ".tsx": "REACT",
    ".json": "JSON", ".yaml": "YAML", ".yml": "YAML", ".toml": "TOML",
    ".html": "HTML", ".css": "CSS", ".scss": "SCSS",
    ".sql": "SQL", ".csv": "CSV",
    ".c": "C", ".h": "C", ".cpp": "CPP", ".hpp": "CPP",
    ".cs": "CSHARP", ".go": "GO", ".rs": "RUST", ".rb": "RUBY",
    ".java": "JAVA", ".sh": "SHELL", ".ps1": "POWERSHELL", ".bat": "BATCH",
}


def category_of(path_or_ext: str) -> str:
    """Map a filename or extension to a short category code."""
    raw = str(path_or_ext or "").strip()
    if not raw:
        return _DEFAULT_CATEGORY
    _, ext = os.path.splitext(raw)
    if not ext:
        ext = raw.lower()
    if not ext.startswith("."):
        ext = "." + ext
    return _EXT_CATEGORY.get(ext, _DEFAULT_CATEGORY)


def badge_colors(category: str) -> Tuple[str, str]:
    """(foreground, background) for a category."""
    return styles.category_color(category or _DEFAULT_CATEGORY)


def make_shadow(widget: QtWidgets.QWidget, blur: Optional[int] = None,
                dx: Optional[int] = None, dy: Optional[int] = None,
                alpha: Optional[int] = None) -> QtWidgets.QGraphicsDropShadowEffect:
    """Attach standard soft drop shadow to widget."""
    cfg = styles.SHADOW
    effect = QtWidgets.QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(float(cfg["blur"] if blur is None else blur))
    effect.setOffset(float(cfg["dx"] if dx is None else dx),
                     float(cfg["dy"] if dy is None else dy))
    effect.setColor(QtGui.QColor(0, 0, 0, int(cfg["alpha"] if alpha is None else alpha)))
    widget.setGraphicsEffect(effect)
    return effect


def format_size(num_bytes) -> str:
    """Human file size: 0 B, 1.5 KB, 12.4 MB, etc."""
    try:
        size = float(num_bytes)
    except (TypeError, ValueError):
        return "0 B"
    if size != size or size in (float("inf"), float("-inf")):
        return "0 B"
    if size < 0:
        size = 0.0
    units = ("B", "KB", "MB", "GB", "TB")
    index = 0
    while size >= 1024.0 and index < len(units) - 1:
        size /= 1024.0
        index += 1
    if index == 0:
        return f"{int(size)} B"
    return f"{size:.1f} {units[index]}"


def format_mtime(ts) -> str:
    """Local YYYY-MM-DD HH:MM for timestamp."""
    try:
        value = float(ts)
    except (TypeError, ValueError):
        return ""
    if value <= 0:
        return ""
    try:
        return datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M")
    except (OSError, OverflowError, ValueError):
        return ""


def _as_shortcut(index) -> Optional[int]:
    try:
        val = int(index)
        return val if 1 <= val <= 9 else None
    except (TypeError, ValueError):
        return None


def _ref_text(page, line) -> str:
    if line not in (None, "", 0):
        return f"L:{line}" if not isinstance(line, str) else line
    if page in (None, "", 0):
        return ""
    try:
        num = int(page)
        return f"p. {num}" if num > 0 else f"L:{abs(num)}"
    except (TypeError, ValueError):
        return str(page)


class _Badge(QtWidgets.QLabel):
    def __init__(self, text: str, object_name: str = "chip", parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(str(text), parent)
        self.setObjectName(object_name)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAlignment(Qt.AlignCenter)


def _category_chip(category: str) -> _Badge:
    fg, bg = badge_colors(category)
    chip = _Badge(category, "chip")
    chip.setStyleSheet(
        f"background: {bg}; color: {fg}; border: 1px solid {bg};"
        f" border-radius: {styles.CONTROL_RADIUS}px; padding: 1px 7px;"
        f" font-family: {styles.MONO_STACK}; font-size: 10px; font-weight: 600;"
    )
    return chip


class ResultItemWidget(QtWidgets.QWidget):
    """One row of the result list with category chip and Alt+1..9 badge."""

    def __init__(self, name: str, path: str, category: str, page=None,
                 line=None, score=None, index=None,
                 parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.setObjectName("resultItem")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)

        self._full_path = str(path or "")
        self._category = (category or category_of(self._full_path)).upper()
        self.index = _as_shortcut(index)

        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(10, 7, 10, 7)
        row.setSpacing(8)

        self.badge: Optional[QtWidgets.QLabel] = None
        if self.index is not None:
            self.badge = QtWidgets.QLabel(str(self.index))
            self.badge.setObjectName("numBadge")
            self.badge.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self.badge.setAlignment(Qt.AlignCenter)
            self.badge.setFixedSize(styles.NUM_BADGE_SIZE, styles.NUM_BADGE_SIZE)
            self.badge.setStyleSheet(styles.num_badge_qss())
            self.badge.setToolTip(f"Alt+{self.index}")
            row.addWidget(self.badge, 0, Qt.AlignVCenter)

        text_col = QtWidgets.QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(1)

        self.name_label = QtWidgets.QLabel(str(name or os.path.basename(self._full_path)))
        self.name_label.setObjectName("resultName")
        self.name_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.name_label.setTextFormat(Qt.PlainText)

        self.path_label = QtWidgets.QLabel(self._full_path)
        self.path_label.setObjectName("resultPath")
        self.path_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.path_label.setTextFormat(Qt.PlainText)
        self.path_label.setToolTip(self._full_path)

        text_col.addWidget(self.name_label)
        text_col.addWidget(self.path_label)
        row.addLayout(text_col, 1)

        if score is not None:
            try:
                score_label = QtWidgets.QLabel(f"{float(score):.3f}")
                score_label.setObjectName("resultScore")
                score_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
                row.addWidget(score_label, 0, Qt.AlignVCenter)
            except (TypeError, ValueError):
                pass

        ref = _ref_text(page, line)
        self.pill: Optional[_Badge] = None
        if ref:
            self.pill = _Badge(ref, "pill")
            row.addWidget(self.pill, 0, Qt.AlignVCenter)

        self.chip = _category_chip(self._category)
        row.addWidget(self.chip, 0, Qt.AlignVCenter)

    def data(self) -> Dict[str, object]:
        return {"name": self.name_label.text(), "path": self._full_path,
                "category": self._category,
                "page": self.pill.text() if self.pill else None,
                "index": self.index}

    def set_selected(self, selected: bool):
        self.setProperty("selected", bool(selected))
        style = self.style()
        style.unpolish(self)
        style.polish(self)
        self.update()

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._apply_elide()

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        self._apply_elide()

    def _apply_elide(self):
        metrics = self.path_label.fontMetrics()
        reserved = self.chip.sizeHint().width() + 34
        if self.pill is not None:
            reserved += self.pill.sizeHint().width()
        if self.badge is not None:
            reserved += self.badge.width() + 8
        available = max(60, self.width() - reserved)
        self.path_label.setText(metrics.elidedText(self._full_path, Qt.ElideMiddle, available))


def keycaps(items: List[Tuple[str, str]]) -> QtWidgets.QWidget:
    strip = QtWidgets.QWidget()
    strip.setObjectName("keycaps")
    strip.setAttribute(Qt.WA_TransparentForMouseEvents, True)
    row = QtWidgets.QHBoxLayout(strip)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(6)
    for item in items or []:
        try:
            key_text, label_text = item
        except (TypeError, ValueError):
            key_text, label_text = str(item), ""
        cap = _Badge(str(key_text), "keycap")
        row.addWidget(cap, 0, Qt.AlignVCenter)
        if label_text:
            label = QtWidgets.QLabel(str(label_text))
            label.setObjectName("keycapLabel")
            label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            row.addWidget(label, 0, Qt.AlignVCenter)
    row.addStretch(1)
    return strip


class NoticeRow(QtWidgets.QWidget):
    """One headline row for a mode page: command, calc result, status notice."""

    def __init__(self, title: str, detail: str = "", tag: str = "",
                 glyph: str = "", variant: str = "normal",
                 parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.setObjectName("resultItem")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.variant = str(variant or "normal")
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)

        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(10, 8, 10, 8)
        row.setSpacing(9)

        if glyph:
            glyph_label = QtWidgets.QLabel(str(glyph))
            glyph_label.setObjectName("actionGlyph")
            glyph_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            glyph_label.setFixedWidth(16)
            glyph_label.setAlignment(Qt.AlignCenter)
            row.addWidget(glyph_label, 0, Qt.AlignVCenter)

        column = QtWidgets.QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(1)
        self.title_label = QtWidgets.QLabel(str(title))
        self.title_label.setObjectName("calcResult" if self.variant == "big" else "modeTitle")
        self.title_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.title_label.setTextFormat(Qt.PlainText)
        column.addWidget(self.title_label)
        self.detail_label = QtWidgets.QLabel(str(detail))
        self.detail_label.setObjectName("modeMeta")
        self.detail_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.detail_label.setTextFormat(Qt.PlainText)
        self.detail_label.setWordWrap(True)
        self.detail_label.setVisible(bool(detail))
        column.addWidget(self.detail_label)
        row.addLayout(column, 1)

        self.tag: Optional[_Badge] = None
        if tag:
            self.tag = _Badge(str(tag), "pill")
            row.addWidget(self.tag, 0, Qt.AlignVCenter)

    def data(self) -> Dict[str, object]:
        return {"title": self.title_label.text(), "detail": self.detail_label.text(),
                "tag": self.tag.text() if self.tag else ""}


class ClipboardRow(QtWidgets.QWidget):
    """One clipboard history line with preview and timestamp."""

    def __init__(self, preview: str, meta: str = "", index=None, nchars=None,
                 tooltip: str = "", parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.setObjectName("resultItem")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        self._preview = str(preview or "")
        self._meta = str(meta or "")
        self.index = _as_shortcut(index)

        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(10, 7, 10, 7)
        row.setSpacing(8)

        self.badge: Optional[QtWidgets.QLabel] = None
        if self.index is not None:
            self.badge = QtWidgets.QLabel(str(self.index))
            self.badge.setObjectName("numBadge")
            self.badge.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self.badge.setAlignment(Qt.AlignCenter)
            self.badge.setFixedSize(styles.NUM_BADGE_SIZE, styles.NUM_BADGE_SIZE)
            self.badge.setStyleSheet(styles.num_badge_qss())
            self.badge.setToolTip(f"Alt+{self.index}")
            row.addWidget(self.badge, 0, Qt.AlignVCenter)

        column = QtWidgets.QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(1)
        self.preview_label = QtWidgets.QLabel(self._preview)
        self.preview_label.setObjectName("resultName")
        self.preview_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.preview_label.setTextFormat(Qt.PlainText)
        column.addWidget(self.preview_label)
        self.meta_label = QtWidgets.QLabel(self._meta)
        self.meta_label.setObjectName("modeMeta")
        self.meta_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.meta_label.setTextFormat(Qt.PlainText)
        column.addWidget(self.meta_label)
        row.addLayout(column, 1)

        self.chars_label: Optional[_Badge] = None
        if nchars is not None:
            self.chars_label = _Badge(f"{int(nchars):,} chars", "pill")
            row.addWidget(self.chars_label, 0, Qt.AlignVCenter)

        self.setToolTip(tooltip or self._preview)

    def data(self) -> Dict[str, object]:
        return {"preview": self._preview, "meta": self._meta,
                "index": self.index,
                "nchars": self.chars_label.text() if self.chars_label else ""}

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._apply_elide()

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        self._apply_elide()

    def _apply_elide(self):
        metrics = self.preview_label.fontMetrics()
        reserved = 26
        if self.badge is not None:
            reserved += self.badge.width() + 8
        if self.chars_label is not None:
            reserved += self.chars_label.sizeHint().width()
        available = max(60, self.width() - reserved)
        self.preview_label.setText(metrics.elidedText(self._preview, Qt.ElideRight, available))
