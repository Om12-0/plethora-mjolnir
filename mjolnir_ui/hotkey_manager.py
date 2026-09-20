"""Global hotkey registration with Win32 RegisterHotKey and fallback chain."""
from __future__ import annotations

import os
import sys
import threading
import time
from typing import List, Optional, Sequence, Tuple

from PySide6 import QtCore
from PySide6.QtCore import Signal

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
PM_NOREMOVE = 0x0000
VK_SPACE = 0x20
VK_C = 0x43

HOTKEY_PRIMARY = 9000       # Alt + Space
HOTKEY_FALLBACK_1 = 9001    # Ctrl + Shift + Space
HOTKEY_CLIPBOARD = 9002     # Alt + Shift + C
HOTKEY_FALLBACK_2 = 9003    # Alt + Shift + Space

# Fallback sequence for the launcher toggle
TOGGLE_FALLBACKS: List[Tuple[int, int, str, int]] = [
    (MOD_ALT, VK_SPACE, "Alt+Space", HOTKEY_PRIMARY),
    (MOD_CONTROL | MOD_SHIFT, VK_SPACE, "Ctrl+Shift+Space", HOTKEY_FALLBACK_1),
    (MOD_ALT | MOD_SHIFT, VK_SPACE, "Alt+Shift+Space", HOTKEY_FALLBACK_2),
]


class HotkeyThread(QtCore.QThread):
    """Registers global hotkeys and emits `triggered` and `fired(int)` when one fires."""

    triggered = Signal()
    fired = Signal(int)
    warning = Signal(str)

    def __init__(self, combos: Optional[Sequence[Tuple[int, int]]] = None):
        super().__init__()
        self.combos = list(combos) if combos is not None else []
        self.registered: list[int] = []
        self._state_lock = threading.Lock()
        self._thread_id = 0
        self._stop_requested = False
        self.active_hotkey_label = ""

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

            # If explicit combos were provided, register them
            if self.combos:
                for i, (mods, vk) in enumerate(self.combos):
                    hid = 9000 + i
                    if user32.RegisterHotKey(None, hid, mods, vk):
                        registered.append(hid)
                    else:
                        self.warning.emit(f"Hotkey id {hid} occupied by another process.")
            else:
                # Standard fallback chain: Primary -> Fallback 1 -> Fallback 2
                toggle_ok = False
                for mods, vk, label, hid in TOGGLE_FALLBACKS:
                    if user32.RegisterHotKey(None, hid, mods, vk):
                        registered.append(hid)
                        toggle_ok = True
                        self.active_hotkey_label = label
                        break
                    else:
                        self.warning.emit(f"Warning: {label} is occupied by another process.")

                if not toggle_ok:
                    self.warning.emit("Warning: All toggle hotkeys (Alt+Space, Ctrl+Shift+Space, Alt+Shift+Space) failed to register.")

                # Register clipboard shortcut Alt + Shift + C
                if user32.RegisterHotKey(None, HOTKEY_CLIPBOARD, MOD_ALT | MOD_SHIFT, VK_C):
                    registered.append(HOTKEY_CLIPBOARD)
                else:
                    self.warning.emit("Warning: Clipboard hotkey Alt+Shift+C is occupied by another process.")

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
