"""Inspector preview pane, badges, styled capsule pills, and preview HTML generators."""
from __future__ import annotations

import html
import os
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt

from mjolnir import styles

_WORD_RE = re.compile(r"\w+", re.UNICODE)
_MAX_TOKENS = 32
_SENTINELS = (("\x00", "&"), ("\x01", "<"), ("\x02", ">"))


def _escape_for_highlight(text: str) -> str:
    escaped = html.escape(text, quote=False)
    if "\x00" in escaped or "\x01" in escaped or "\x02" in escaped:
        return escaped
    for mark, char in _SENTINELS:
        escaped = escaped.replace(html.escape(char, quote=False), mark)
    return escaped


def _restore_entities(text: str) -> str:
    for mark, char in _SENTINELS:
        text = text.replace(mark, html.escape(char, quote=False))
    return text


def highlight_html(snippet: str, query: str, min_len: int = 1) -> str:
    """HTML-escape snippet and bold every case-insensitive match of a query token."""
    text = _escape_for_highlight(snippet or "")
    if not text:
        return ""
    tokens: List[str] = []
    seen = set()
    for token in _WORD_RE.findall(query or ""):
        if len(token) < max(1, int(min_len)):
            continue
        low = token.lower()
        if low in seen:
            continue
        seen.add(low)
        tokens.append(token)
    if not tokens:
        return _restore_entities(text)
    tokens.sort(key=len, reverse=True)
    pattern = re.compile("|".join(re.escape(t) for t in tokens[:_MAX_TOKENS]),
                         re.IGNORECASE)
    marked = pattern.sub(
        lambda m: f'<b style="color:{styles.ACCENT_SOLID};font-weight:700">{m.group(0)}</b>',
        text,
    )
    return _restore_entities(marked)


class Capsule(QtWidgets.QFrame):
    """A small pill: 22px tall, 11px corners, 1px themed border."""

    def __init__(self, text: str = "", variant: str = "neutral",
                 tooltip: str = "", parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.variant = "accent" if str(variant).lower() == "accent" else "neutral"
        self.setObjectName("capsuleAccent" if self.variant == "accent" else "capsule")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(styles.CAPSULE_HEIGHT)
        self.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.setStyleSheet(styles.capsule_qss(self.variant))

        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self.label = QtWidgets.QLabel(str(text))
        self.label.setObjectName("capsuleText")
        self.label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("background: transparent; border: none;")
        row.addWidget(self.label, 0, Qt.AlignVCenter)
        if tooltip:
            self.setToolTip(str(tooltip))

    def text(self) -> str:
        return self.label.text()

    def setText(self, text: str):  # noqa: N802 (Qt naming)
        self.label.setText(str(text))
        self.updateGeometry()

    def set_tooltip(self, text: str):
        self.setToolTip(str(text or ""))


def capsule_row(items: Sequence, parent: Optional[QtWidgets.QWidget] = None,
                spacing: int = 6) -> QtWidgets.QWidget:
    """Horizontal row of capsules."""
    row = QtWidgets.QWidget(parent)
    row.setObjectName("capsuleRow")
    row.setAttribute(Qt.WA_TransparentForMouseEvents, True)
    lay = QtWidgets.QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(int(spacing))
    for item in items or []:
        if item is None or (isinstance(item, str) and not item):
            continue
        if isinstance(item, QtWidgets.QWidget):
            cap = item
        elif isinstance(item, (tuple, list)) and len(item) >= 2:
            cap = Capsule(str(item[0]), str(item[1]))
        else:
            cap = Capsule(str(item))
        lay.addWidget(cap, 0, Qt.AlignVCenter)
    lay.addStretch(1)
    return row


def match_percent(score, top=None) -> Optional[int]:
    """0..100 integer for a score, or None when there is no score."""
    if score is None:
        return None
    try:
        value = float(score)
    except (TypeError, ValueError):
        return None
    if value != value:
        return None
    if top is not None:
        try:
            scale = float(top)
        except (TypeError, ValueError):
            scale = 0.0
        if scale > 0:
            value = value / scale
    if value > 1.0:
        value = min(100.0, value) / 100.0
    return max(0, min(100, int(round(value * 100.0))))


def position_text(chunk_index=None, chunk_total=None, page=None) -> str:
    """Chunk 2/5 · p. 1 - whichever parts are known."""
    parts: List[str] = []
    index = None
    if chunk_index is not None:
        try:
            index = int(chunk_index)
        except (TypeError, ValueError):
            index = None
    total = None
    if chunk_total is not None:
        try:
            total = int(chunk_total)
        except (TypeError, ValueError):
            total = None
    if index is not None:
        parts.append(f"Chunk {index + 1}/{total}" if total else f"Chunk {index + 1}")
    elif total:
        parts.append(f"{total} chunks")
    if page not in (None, "", 0):
        if isinstance(page, str):
            parts.append(page)
        else:
            try:
                parts.append(f"p. {int(page)}")
            except (TypeError, ValueError):
                parts.append(str(page))
    return " · ".join(parts)


def match_capsule(score, chunk_index=None, chunk_total=None, page=None,
                  parent: Optional[QtWidgets.QWidget] = None) -> QtWidgets.QWidget:
    """Inspector capsule row: match percentage + chunk/page position."""
    pct = match_percent(score)
    items: List[object] = []
    if pct is None:
        items.append(Capsule("match —", "accent"))
    else:
        tooltip = ""
        try:
            tooltip = f"score {float(score):.4f}"
        except (TypeError, ValueError):
            tooltip = ""
        items.append(Capsule(f"{pct}% match", "accent", tooltip=tooltip))
    position = position_text(chunk_index, chunk_total, page)
    if position:
        items.append(Capsule(position))
    return capsule_row(items, parent)


def _kv(label: str, value: str, mono: bool = True) -> str:
    family = styles.MONO_STACK if mono else styles.FONT_STACK
    return (f'<div style="font-size:11px;color:{styles.FG_MUTED};">'
            f'{html.escape(label)} <span style="font-family:{family};'
            f'color:{styles.FG};">{html.escape(value)}</span></div>')


def preview_html(hit: dict) -> str:
    """Rich-text preview panel body for one search hit."""
    data = hit if isinstance(hit, dict) else {}
    path = str(data.get("path") or "")
    name = str(data.get("name") or "") or os.path.basename(path) or path or "(untitled)"
    snippet = str(data.get("snippet") or "")
    page = data.get("page")
    score = data.get("score")
    chunk_index = data.get("chunk_index")

    ext = os.path.splitext(path or name)[1].lower()
    category = "CODE" if ext in (".py", ".js", ".ts", ".go", ".rs", ".c", ".cpp") else "DOC"
    fg, bg = styles.category_color(category)

    meta: List[str] = []
    if page not in (None, "", 0):
        meta.append(str(page) if isinstance(page, str) else f"p. {int(page)}")
    if chunk_index:
        try:
            meta.append(f"chunk {int(chunk_index)}")
        except (TypeError, ValueError):
            pass
    if score is not None:
        try:
            meta.append(f"score {float(score):.3f}")
        except (TypeError, ValueError):
            pass

    parts = [
        f'<div style="font-size:14px;font-weight:700;color:{styles.FG};">{html.escape(name)}</div>',
        f'<div style="font-size:11px;color:{styles.FG_MUTED};margin-top:2px;">{html.escape(path)}</div>',
    ]
    meta_html = (f'<span style="background:{bg};color:{fg};border-radius:4px;padding:0px 4px;font-weight:600;">'
                 f'{html.escape(category)}</span>')
    if meta:
        meta_html += f'<span style="color:{styles.FG_MUTED};">&nbsp;&nbsp;{html.escape(" · ".join(meta))}</span>'
    parts.append(f'<div style="font-size:10px;margin-top:6px;">{meta_html}</div>')

    if snippet:
        query = str(data.get("query") or "")
        parts.append(f'<div style="margin-top:10px;font-size:12px;line-height:150%;color:{styles.FG};">'
                     f'{highlight_html(snippet, query)}</div>')
    return "".join(parts)


def calc_html(result) -> str:
    """Inspector body for the calculator page."""
    expression = str(getattr(result, "expression", "") or "")
    ok = bool(getattr(result, "ok", False))
    body = str(getattr(result, "text", "") or "")
    error = str(getattr(result, "error", "") or "")
    parts = []
    if expression:
        parts.append(f'<div style="font-size:12px;color:{styles.FG_MUTED};font-family:{styles.MONO_STACK};">'
                     f'= {html.escape(expression)}</div>')
    if ok:
        parts.append(f'<div style="font-size:24px;font-weight:700;color:{styles.FG};font-family:{styles.MONO_STACK};'
                     f'margin-top:8px;">{html.escape(body)}</div>')
        parts.append(f'<div style="font-size:10px;color:{styles.FG_MUTED};margin-top:10px;">'
                     f'Enter copies the result to the clipboard.</div>')
    else:
        parts.append(f'<div style="font-size:13px;color:{styles.WARNING};margin-top:8px;">{html.escape(error)}</div>')
        parts.append(f'<div style="font-size:10px;color:{styles.FG_MUTED};margin-top:10px;">'
                     f'Try <span style="font-family:{styles.MONO_STACK};">= 45 * 1.18</span> or '
                     f'<span style="font-family:{styles.MONO_STACK};">sqrt(256)</span>.</div>')
    return "".join(parts)


def launch_html(label: str, path: str, kind: str = "", query: str = "", empty: bool = False) -> str:
    """Inspector body for open mode entry."""
    if empty:
        return (f'<div style="font-size:12px;color:{styles.FG_MUTED};">No launcher target matches '
                f'<span style="font-family:{styles.MONO_STACK};">{html.escape(query)}</span>.</div>')
    fg, bg = styles.category_color("APP")
    parts = [f'<div style="font-size:14px;font-weight:700;color:{styles.FG};">{html.escape(label)}</div>']
    if path:
        parts.append(f'<div style="font-size:11px;color:{styles.FG_MUTED};font-family:{styles.MONO_STACK};'
                     f'margin-top:2px;word-wrap:break-word;">{html.escape(path)}</div>')
    tag = f'<span style="background:{bg};color:{fg};border-radius:4px;padding:0px 4px;font-weight:600;">APP</span>'
    if kind:
        tag += f'<span style="color:{styles.FG_MUTED};">&nbsp;&nbsp;{html.escape(kind)}</span>'
    parts.append(f'<div style="font-size:10px;margin-top:8px;">{tag}</div>')
    parts.append(f'<div style="font-size:10px;color:{styles.FG_MUTED};margin-top:10px;">'
                 f'Enter opens it · Shift+Enter reveals it · Tab opens action panel.</div>')
    return "".join(parts)


def command_html(display: str, target_label: str, cwd: str = "", error: str = "") -> str:
    """Inspector body for a > command before staging/execution."""
    if error:
        return (f'<div style="font-size:13px;color:{styles.WARNING};">{html.escape(error)}</div>'
                f'<div style="font-size:10px;color:{styles.FG_MUTED};margin-top:10px;">'
                f'Examples: <span style="font-family:{styles.MONO_STACK};">> ipconfig /flushdns</span></div>')
    parts = [f'<div style="font-size:12px;color:{styles.FG_MUTED};">Runs in {html.escape(target_label or "a terminal")}</div>',
             f'<div style="font-size:12px;color:{styles.FG};font-family:{styles.MONO_STACK};margin-top:8px;'
             f'word-wrap:break-word;">{html.escape(display)}</div>']
    if cwd:
        parts.append(_kv("working directory:", cwd))
    parts.append(f'<div style="font-size:10px;color:{styles.FG_MUTED};margin-top:10px;">Nothing runs until you press Enter.</div>')
    return "".join(parts)


def confirmation_html(command: str, cwd: str, shell_name: str = "PowerShell",
                      destructive: bool = False, streaming_output: str = "") -> str:
    """Execution Confirmation Card for visual staging state."""
    header_color = styles.WARNING
    parts = [
        f'<div style="font-size:13px;font-weight:700;color:{header_color};margin-bottom:8px;">'
        f'Ready to execute in {html.escape(shell_name)}:</div>',
        f'<div style="font-size:12px;color:{styles.FG};font-family:{styles.MONO_STACK};'
        f'background:rgba(255,255,255,0.04);padding:8px;border-radius:4px;word-wrap:break-word;">'
        f'&gt; {html.escape(command)}</div>',
        f'<div style="font-size:11px;color:{styles.FG_MUTED};margin-top:8px;">'
        f'Working directory: <span style="font-family:{styles.MONO_STACK};color:{styles.FG};">{html.escape(cwd)}</span></div>',
    ]
    if destructive:
        parts.append(
            f'<div style="font-size:11px;font-weight:600;color:{styles.WARNING};margin-top:10px;'
            f'background:rgba(245,158,11,0.12);padding:6px;border-radius:4px;">'
            f'WARNING: Potentially destructive command! Requires --force or [Ctrl + Enter]</div>'
        )
    parts.append(
        f'<div style="font-size:11px;color:{styles.FG_MUTED};margin-top:14px;line-height:160%;">'
        f'<b style="color:{styles.FG};">Press [Enter] again</b> to run in background<br/>'
        f'<b style="color:{styles.FG};">Press [Ctrl + Enter]</b> to launch in a visible terminal window<br/>'
        f'<b style="color:{styles.FG};">Press [Esc]</b> to abort</div>'
    )
    if streaming_output:
        parts.append(
            f'<div style="margin-top:12px;border-top:1px solid rgba(255,255,255,0.1);padding-top:8px;">'
            f'<div style="font-size:11px;color:{styles.FG_MUTED};margin-bottom:4px;">Output:</div>'
            f'<pre style="font-family:{styles.MONO_STACK};font-size:11px;color:{styles.FG};'
            f'white-space:pre-wrap;max-height:160px;overflow-y:auto;">{html.escape(streaming_output)}</pre></div>'
        )
    return "".join(parts)
