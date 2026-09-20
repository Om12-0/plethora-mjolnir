"""Modular PySide6 UI components for PLETHORA MJOLNIR."""
from __future__ import annotations

from .action_panel import ActionPanel, ActionRow
from .hotkey_manager import (
    HotkeyThread, HOTKEY_PRIMARY, HOTKEY_FALLBACK_1, HOTKEY_FALLBACK_2, HOTKEY_CLIPBOARD
)
from .inspector_pane import (
    Capsule, match_capsule, match_percent, position_text, capsule_row,
    preview_html, calc_html, launch_html, command_html, confirmation_html, highlight_html
)
from .mode_router import ModeRouter, BackgroundCommandRunner, is_destructive, is_forced
from .result_list import (
    ResultItemWidget, NoticeRow, ClipboardRow, keycaps, format_size, format_mtime,
    make_shadow, category_of, badge_colors
)
from .tray_icon import app_icon, icon_bytes
from .window import (
    Launcher, run_gui,
    VIEW_SEARCH, VIEW_ACTIONS, VIEW_CLIPBOARD, PASTE_DELAY_MS,
    HINTS_SEARCH, HINTS_OPEN, HINTS_CALC, HINTS_SHELL, HINTS_CLIPBOARD,
)

__all__ = [
    "Launcher", "run_gui",
    "VIEW_SEARCH", "VIEW_ACTIONS", "VIEW_CLIPBOARD", "PASTE_DELAY_MS",
    "HINTS_SEARCH", "HINTS_OPEN", "HINTS_CALC", "HINTS_SHELL", "HINTS_CLIPBOARD",
    "ActionPanel", "ActionRow",
    "HotkeyThread", "HOTKEY_PRIMARY", "HOTKEY_FALLBACK_1", "HOTKEY_FALLBACK_2", "HOTKEY_CLIPBOARD",
    "Capsule", "match_capsule", "match_percent", "position_text", "capsule_row",
    "preview_html", "calc_html", "launch_html", "command_html", "confirmation_html", "highlight_html",
    "ModeRouter", "BackgroundCommandRunner", "is_destructive", "is_forced",
    "ResultItemWidget", "NoticeRow", "ClipboardRow", "keycaps",
    "format_size", "format_mtime", "make_shadow", "category_of", "badge_colors",
    "app_icon", "icon_bytes",
]
