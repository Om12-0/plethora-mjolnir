"""Floating spotlight-style launcher overlay for PLETHORA MJOLNIR.

Facade re-exporting and wrapping :mod:`mjolnir_ui`.
"""
from __future__ import annotations

import os
import sys
import threading
import time
from typing import List, Optional, Sequence, Tuple

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import QTimer, Qt, Signal

from . import actions, clipboard as clipboard_history, modes, openers, styles, ui_components
from .ui_components import (
    ActionPanel, ActionRow, Capsule, ClipboardRow, NoticeRow, ResultItemWidget,
    app_icon, calc_html, capsule_row, category_of, command_html, format_mtime,
    format_size, launch_html, make_shadow, match_capsule, preview_html,
)
from mjolnir_ui import (
    Launcher, run_gui,
    VIEW_SEARCH, VIEW_ACTIONS, VIEW_CLIPBOARD,
    HINTS_SEARCH, HINTS_OPEN, HINTS_CALC, HINTS_SHELL, HINTS_CLIPBOARD,
)
from mjolnir_ui.hotkey_manager import (
    MOD_ALT, MOD_CONTROL, MOD_SHIFT, VK_SPACE, VK_C, WM_HOTKEY, WM_QUIT, PM_NOREMOVE,
    HOTKEY_PRIMARY as HOTKEY_TOGGLE, HOTKEY_FALLBACK_1 as HOTKEY_TOGGLE_CTRL, HOTKEY_CLIPBOARD,
)

__all__ = [
    "Launcher", "run_gui", "HotkeyThread",
    "VIEW_SEARCH", "VIEW_ACTIONS", "VIEW_CLIPBOARD",
    "HOTKEY_TOGGLE", "HOTKEY_TOGGLE_CTRL", "HOTKEY_CLIPBOARD",
    "HINTS_SEARCH", "HINTS_OPEN", "HINTS_CALC", "HINTS_SHELL", "HINTS_CLIPBOARD",
]


class HotkeyThread(QtCore.QThread):
    """Registers global hotkeys and emits `triggered` and `fired(int)` when one fires."""

    triggered = Signal()
    fired = Signal(int)

    def __init__(self, combos: Optional[Sequence[Tuple[int, int]]] = None):
        super().__init__()
        self.combos = list(combos) if combos is not None else [
            (MOD_ALT, VK_SPACE),
            (MOD_CONTROL | MOD_SHIFT, VK_SPACE),
            (MOD_ALT | MOD_SHIFT, VK_C),
            (MOD_ALT | MOD_SHIFT, VK_SPACE),
        ]
        self.registered: list[int] = []
        self._state_lock = threading.Lock()
        self._thread_id = 0
        self._stop_requested = False

    def run(self):
        if not sys.platform.startswith("win"):
            return
        import ctypes
        import ctypes.wintypes as wt

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        registered: list[int] = []
        msg = wt.MSG()
        try:
            user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_NOREMOVE)
            with self._state_lock:
                self._thread_id = int(kernel32.GetCurrentThreadId()) & 0xFFFFFFFF
            for i, (mods, vk) in enumerate(self.combos):
                hid = 9000 + i
                if user32.RegisterHotKey(None, hid, mods, vk):
                    registered.append(hid)
            with self._state_lock:
                self.registered = list(registered)
                stop_early = self._stop_requested
            if not registered or stop_early:
                return
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
                if msg.message == WM_HOTKEY:
                    self.triggered.emit()
                    try:
                        self.fired.emit(int(msg.wParam) & 0xFFFFFFFF)
                    except Exception:
                        pass
        except Exception:
            pass
        finally:
            for hid in registered:
                try:
                    user32.UnregisterHotKey(None, hid)
                except Exception:
                    pass
            with self._state_lock:
                self.registered = []
                self._thread_id = 0

    def _wait_for_thread_id(self, deadline: float) -> int:
        while time.monotonic() < deadline:
            with self._state_lock:
                tid = self._thread_id
                if tid:
                    return tid
            time.sleep(0.01)
        return 0

    def stop(self, timeout_ms: int = 2000) -> bool:
        """Ask the message loop to exit and join worker."""
        try:
            deadline = time.monotonic() + max(0.0, timeout_ms / 1000.0)
            with self._state_lock:
                self._stop_requested = True
            tid = self._wait_for_thread_id(deadline)
            if tid and self.isRunning():
                try:
                    import ctypes
                    ctypes.windll.user32.PostThreadMessageW(ctypes.c_ulong(tid), WM_QUIT, 0, 0)
                except Exception:
                    pass
            remaining_ms = int(max(0.0, deadline - time.monotonic()) * 1000)
            return bool(self.wait(remaining_ms))
        except Exception:
            return False


def _launcher_lifecycle_bindings(self):
    # Ensure standard seams are wired up
    self.copy_fn = clipboard_history.set_clipboard_text
    self.paste_fn = clipboard_history.paste_ctrl_v


def _run_app(cfg, store, embedder, log=print) -> int:
    app = QtWidgets.QApplication.instance()
    if app is None:
        if hasattr(Qt, "HighDpiScaleFactorRoundingPolicy"):
            try:
                QtWidgets.QApplication.setHighDpiScaleFactorRoundingPolicy(
                    Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
            except Exception:
                pass
        app = QtWidgets.QApplication(sys.argv)

    app.setStyleSheet(styles.PANEL_QSS)
    icon = app_icon(getattr(cfg, "theme", None))
    app.setWindowIcon(icon)

    win = Launcher(cfg, store, embedder)
    _launcher_lifecycle_bindings(win)

    hotkeys = HotkeyThread([(MOD_ALT, VK_SPACE),
                            (MOD_CONTROL | MOD_SHIFT, VK_SPACE),
                            (MOD_ALT | MOD_SHIFT, VK_C),
                            (MOD_ALT | MOD_SHIFT, VK_SPACE)])
    try:
        hotkeys.fired.connect(win.route_hotkey)
        hotkeys.start()
    except Exception:
        pass

    try:
        win.show_centered()
        return app.exec()
    finally:
        try:
            hotkeys.stop()
        except Exception:
            pass
