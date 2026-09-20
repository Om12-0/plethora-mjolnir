"""Persistent clipboard history: a SQLite table, a Win32 reader, a watch thread. Qt-free."""
from __future__ import annotations

import hashlib
import os
import sqlite3
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Sequence

from . import modes, openers

__all__ = [
    "Item", "ClipboardStore", "ClipboardWatcher",
    "clipboard_sequence", "get_clipboard_text", "set_clipboard_text",
    "paste_ctrl_v", "clear_clipboard", "is_sensitive_window",
    "format_when", "format_age", "one_line",
    "FROM_CONFIG_DEFAULT_MAX_ITEMS", "FROM_CONFIG_DEFAULT_MAX_CHARS",
    "SCHEMA", "PRAGMAS", "MAX_ENTRY_BYTES",
]

FROM_CONFIG_DEFAULT_MAX_ITEMS = 500
FROM_CONFIG_DEFAULT_MAX_CHARS = 100_000
MAX_ENTRY_BYTES = 1024 * 1024  # 1 MB maximum per stored entry

SCHEMA = """
CREATE TABLE IF NOT EXISTS clipboard_items(
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    content    TEXT    NOT NULL,
    nchars     INTEGER NOT NULL,
    created_at REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_clipboard_created ON clipboard_items(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_clipboard_id ON clipboard_items(id DESC);
"""

PRAGMAS = (
    "PRAGMA journal_mode = WAL",
    "PRAGMA synchronous = NORMAL",
    "PRAGMA busy_timeout = 4000",
)

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
VK_CONTROL = 0x11
VK_V = 0x56
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002

KNOWN_PASSWORD_MANAGERS = (
    "1password", "bitwarden", "keepass", "keepassxc", "lastpass",
    "enpass", "dashlane", "roboform", "nordpass", "authy"
)

def is_sensitive_window(hwnd: Optional[int] = None) -> bool:
    """Return True if active window belongs to a known password manager."""
    if not sys.platform.startswith("win"):
        return False
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        target_hwnd = hwnd or user32.GetForegroundWindow()
        if not target_hwnd:
            return False

        length = user32.GetWindowTextLengthW(target_hwnd)
        if length > 0:
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(target_hwnd, buff, length + 1)
            if any(pm in buff.value.lower() for pm in KNOWN_PASSWORD_MANAGERS):
                return True

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(target_hwnd, ctypes.byref(pid))
        if pid.value:
            kernel32 = ctypes.windll.kernel32
            hproc = kernel32.OpenProcess(0x1000, False, pid.value)
            if hproc:
                try:
                    name_buf = ctypes.create_unicode_buffer(1024)
                    size = wintypes.DWORD(1024)
                    if hasattr(kernel32, "QueryFullProcessImageNameW") and kernel32.QueryFullProcessImageNameW(hproc, 0, name_buf, ctypes.byref(size)):
                        if any(pm in os.path.basename(name_buf.value).lower() for pm in KNOWN_PASSWORD_MANAGERS):
                            return True
                finally:
                    kernel32.CloseHandle(hproc)
    except Exception:
        pass
    return False

def one_line(text: Any, width: int = 160) -> str:
    return modes.one_line(text, width)

def format_when(timestamp: Any, now: Optional[float] = None) -> str:
    try:
        val = float(timestamp)
        return datetime.fromtimestamp(val).strftime("%Y-%m-%d %H:%M") if val > 0 else ""
    except Exception:
        return ""

def format_age(timestamp: Any, now: Optional[float] = None) -> str:
    try:
        val = float(timestamp)
        if val <= 0:
            return ""
        secs = max(0.0, (time.time() if now is None else float(now)) - val)
        if secs < 45:
            return "just now"
        if secs < 3600:
            return f"{int(secs // 60)}m ago"
        if secs < 86400:
            return f"{int(secs // 3600)}h ago"
        return f"{int(secs // 86400)}d ago"
    except Exception:
        return ""

@dataclass(frozen=True)
class Item:
    id: int
    text: str
    created_at: float
    nchars: int = 0

    @property
    def preview(self) -> str:
        return one_line(self.text, 160)

    @property
    def when(self) -> str:
        return format_when(self.created_at)

    @property
    def age(self) -> str:
        return format_age(self.created_at)

    @property
    def meta(self) -> str:
        return "  ·  ".join(p for p in (self.when, f"{self.nchars:,} chars") if p)

    @property
    def size_label(self) -> str:
        return f"{self.nchars:,} chars"

def clipboard_sequence() -> int:
    if not sys.platform.startswith("win"):
        return 0
    try:
        import ctypes
        getter = ctypes.windll.user32.GetClipboardSequenceNumber
        getter.restype = ctypes.c_uint
        return int(getter()) & 0xFFFFFFFF
    except Exception:
        return 0

def _read_clipboard_once() -> Optional[str]:
    import ctypes
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    user32.GetClipboardData.restype = ctypes.c_void_p
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]

    if not user32.OpenClipboard(None):
        return None
    try:
        if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            return ""
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return ""
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            return ""
        try:
            return ctypes.wstring_at(pointer)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()

def get_clipboard_text(retries: int = 6, delay: float = 0.03) -> str:
    if not sys.platform.startswith("win"):
        return ""
    attempts = max(1, int(retries))
    for attempt in range(attempts):
        try:
            text = _read_clipboard_once()
        except Exception:
            text = ""
        if text is not None:
            return str(text)
        if attempt + 1 < attempts:
            time.sleep(max(0.0, float(delay)))
    return ""

def _set_clipboard_once(text: str) -> bool:
    import ctypes
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    user32.SetClipboardData.restype = ctypes.c_void_p
    user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]

    if not user32.OpenClipboard(None):
        return False
    handle = None
    try:
        if not user32.EmptyClipboard():
            return False
        payload = (str(text) + "\0").encode("utf-16-le")
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(payload))
        if not handle:
            return False
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            kernel32.GlobalFree(handle)
            return False
        ctypes.memmove(pointer, payload, len(payload))
        kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            kernel32.GlobalFree(handle)
            return False
        handle = None
        return True
    except Exception:
        return False
    finally:
        if handle:
            try:
                kernel32.GlobalFree(handle)
            except Exception:
                pass
        user32.CloseClipboard()

def set_clipboard_text(text: Any, retries: int = 5) -> bool:
    payload = "" if text is None else str(text)
    if sys.platform.startswith("win"):
        for attempt in range(max(1, int(retries))):
            try:
                if _set_clipboard_once(payload):
                    return True
            except Exception:
                pass
            time.sleep(0.03)
    try:
        return bool(openers.copy_to_clipboard(payload))
    except Exception:
        return False

def clear_clipboard() -> bool:
    if not sys.platform.startswith("win"):
        return False
    try:
        import ctypes
        user32 = ctypes.windll.user32
        if not user32.OpenClipboard(None):
            return False
        try:
            return bool(user32.EmptyClipboard())
        finally:
            user32.CloseClipboard()
    except Exception:
        return False

def _send_input_ctrl_v() -> bool:
    import ctypes
    from ctypes import wintypes
    ULONG_PTR = ctypes.c_size_t

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]

    class _INPUTUNION(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]

    def key_event(vk: int, key_up: bool) -> "INPUT":
        event = INPUT()
        event.type = INPUT_KEYBOARD
        event.u.ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=KEYEVENTF_KEYUP if key_up else 0, time=0, dwExtraInfo=0)
        return event

    batch = (INPUT * 4)(key_event(VK_CONTROL, False), key_event(VK_V, False),
                        key_event(VK_V, True), key_event(VK_CONTROL, True))
    user32 = ctypes.windll.user32
    user32.SendInput.argtypes = [ctypes.c_uint, ctypes.c_void_p, ctypes.c_int]
    user32.SendInput.restype = ctypes.c_uint
    return int(user32.SendInput(4, ctypes.byref(batch), ctypes.sizeof(INPUT))) == 4

def _keybd_event_ctrl_v() -> bool:
    try:
        import ctypes
        user32 = ctypes.windll.user32
        user32.keybd_event(VK_CONTROL, 0, 0, 0)
        user32.keybd_event(VK_V, 0, 0, 0)
        user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
        user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
        return True
    except Exception:
        return False

def paste_ctrl_v() -> bool:
    if not sys.platform.startswith("win"):
        return False
    try:
        if _send_input_ctrl_v():
            return True
    except Exception:
        pass
    return _keybd_event_ctrl_v()

class ClipboardStore:
    """Isolated SQLite clipboard history with WAL mode and size limits."""

    def __init__(self, path: str, max_items: int = FROM_CONFIG_DEFAULT_MAX_ITEMS,
                 max_chars: int = FROM_CONFIG_DEFAULT_MAX_CHARS):
        self.path = str(path)
        self.max_items = max(1, int(max_items or FROM_CONFIG_DEFAULT_MAX_ITEMS))
        self.max_chars = max(1, int(max_chars or FROM_CONFIG_DEFAULT_MAX_CHARS))
        self._lock = threading.RLock()
        folder = os.path.dirname(os.path.abspath(self.path))
        if folder:
            os.makedirs(folder, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        for stmt in PRAGMAS:
            try:
                self.conn.execute(stmt)
            except sqlite3.Error:
                pass
        with self._lock:
            self.conn.executescript(SCHEMA)
            self.conn.commit()

    @staticmethod
    def _row_to_item(row) -> Item:
        return Item(id=int(row["id"]), text=str(row["content"] or ""),
                    created_at=float(row["created_at"] or 0.0), nchars=int(row["nchars"] or 0))

    def close(self) -> None:
        with self._lock:
            try:
                self.conn.close()
            except Exception:
                pass

    def add(self, text: Any, created_at: Optional[float] = None) -> Optional[int]:
        payload = "" if text is None else str(text)
        if not payload.strip():
            return None
        # Strict 1 MB cap to prevent database bloating
        if len(payload) > min(self.max_chars, MAX_ENTRY_BYTES):
            return None
        if len(payload.encode("utf-8", "replace")) > MAX_ENTRY_BYTES:
            return None

        stamp = time.time() if created_at is None else float(created_at)
        with self._lock:
            newest = self.conn.execute("SELECT content FROM clipboard_items ORDER BY id DESC LIMIT 1").fetchone()
            if newest is not None and str(newest["content"]) == payload:
                return None
            cursor = self.conn.execute(
                "INSERT INTO clipboard_items(content, nchars, created_at) VALUES(?,?,?)",
                (payload, len(payload), stamp)
            )
            self.conn.commit()
            rowid = int(cursor.lastrowid or 0)
            self.trim()
            return rowid or None

    def trim(self) -> int:
        with self._lock:
            cursor = self.conn.execute(
                "DELETE FROM clipboard_items WHERE id NOT IN (SELECT id FROM clipboard_items ORDER BY id DESC LIMIT ?)",
                (self.max_items,)
            )
            self.conn.commit()
            return int(cursor.rowcount or 0)

    def delete(self, item_id: int) -> bool:
        with self._lock:
            cursor = self.conn.execute("DELETE FROM clipboard_items WHERE id=?", (int(item_id),))
            self.conn.commit()
            return bool(cursor.rowcount)

    def clear(self) -> int:
        with self._lock:
            count = self.count()
            self.conn.execute("DELETE FROM clipboard_items")
            self.conn.commit()
            return count

    def count(self) -> int:
        with self._lock:
            row = self.conn.execute("SELECT COUNT(*) c FROM clipboard_items").fetchone()
            return int(row["c"]) if row else 0

    def items(self, limit: Optional[int] = None) -> List[Item]:
        with self._lock:
            sql = "SELECT id, content, nchars, created_at FROM clipboard_items ORDER BY id DESC"
            params: Sequence[Any] = ()
            if limit is not None:
                sql += " LIMIT ?"
                params = (int(limit),)
            rows = list(self.conn.execute(sql, params))
        return [self._row_to_item(r) for r in rows]

    def get(self, item_id: int) -> Optional[Item]:
        with self._lock:
            row = self.conn.execute("SELECT id, content, nchars, created_at FROM clipboard_items WHERE id=?",
                                    (int(item_id),)).fetchone()
        return self._row_to_item(row) if row else None

    def newest(self) -> Optional[Item]:
        items = self.items(limit=1)
        return items[0] if items else None

    def search(self, term: Any, limit: int = 50) -> List[Item]:
        query = str(term or "").strip()
        pool = self.items(limit=None if not query else max(self.max_items, 1))
        return pool[:limit] if not query else modes.rank_items(query, pool, ("text",), limit=limit)

    def stats(self) -> Dict[str, Any]:
        items = self.items(limit=1)
        return {
            "db": self.path, "items": self.count(), "max_items": self.max_items,
            "max_chars": self.max_chars, "latest": items[0].created_at if items else 0.0,
        }

def from_config(cfg, log: Optional[Callable] = None) -> Optional[ClipboardStore]:
    try:
        path = getattr(cfg, "clipboard_db", "") or ""
        if not path:
            from .config import default_clipboard_path
            path = str(default_clipboard_path())
        return ClipboardStore(
            path,
            max_items=int(getattr(cfg, "clipboard_max_items", FROM_CONFIG_DEFAULT_MAX_ITEMS) or FROM_CONFIG_DEFAULT_MAX_ITEMS),
            max_chars=int(getattr(cfg, "clipboard_max_chars", FROM_CONFIG_DEFAULT_MAX_CHARS) or FROM_CONFIG_DEFAULT_MAX_CHARS),
        )
    except Exception as exc:
        if log:
            log(f"[mjolnir] clipboard history unavailable: {exc}")
        return None

class ClipboardWatcher(threading.Thread):
    """Background listener that ignores password managers and captures clipboard."""

    def __init__(self, store: ClipboardStore, interval: float = 0.5,
                 sequence: Optional[Callable[[], int]] = None,
                 reader: Optional[Callable[[], str]] = None,
                 on_change: Optional[Callable[[int], None]] = None,
                 sensitive_check: Optional[Callable[[], bool]] = None,
                 name: str = "mjolnir-clipboard"):
        super().__init__(name=name, daemon=True)
        self.store = store
        self.interval = max(0.05, float(interval or 0.5))
        self._sequence = sequence or clipboard_sequence
        self._reader = reader or get_clipboard_text
        self.on_change = on_change
        self._sensitive_check = sensitive_check or is_sensitive_window
        self.polls = 0
        self.recorded = 0
        self.last_error = ""
        self._stop_event = threading.Event()
        self._last_sequence = 0
        self._last_digest = ""
        self._primed = False

    def stop(self, timeout: float = 2.0) -> bool:
        self._stop_event.set()
        try:
            self.join(max(0.0, float(timeout)))
        except (RuntimeError, ValueError):
            return False
        return not self.is_alive()

    @property
    def stopped(self) -> bool:
        return self._stop_event.is_set()

    def _fingerprint(self) -> str:
        try:
            sequence = int(self._sequence() or 0)
        except Exception:
            sequence = 0
        if sequence:
            return f"seq:{sequence}"
        try:
            text = str(self._reader() or "")
        except Exception:
            text = ""
        return "hash:" + hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()

    def _poll_once(self) -> Optional[int]:
        self.polls += 1
        try:
            if self._sensitive_check and self._sensitive_check():
                self._last_sequence = self._sequence_number()
                self._last_digest = self._fingerprint()
                return None
        except Exception:
            pass

        fingerprint = self._fingerprint()
        if fingerprint.startswith("seq:"):
            sequence = int(fingerprint.split(":", 1)[1])
            if sequence == self._last_sequence:
                return None
            self._last_sequence = sequence
            text = self._reader()
        else:
            if fingerprint == self._last_digest:
                return None
            self._last_digest = fingerprint
            text = self._reader()

        try:
            rowid = self.store.add(text)
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            return None

        if rowid is not None:
            self.recorded += 1
            if self.on_change is not None:
                try:
                    self.on_change(rowid)
                except Exception as exc:
                    self.last_error = f"{type(exc).__name__}: {exc}"
        return rowid

    def prime(self) -> None:
        self._last_sequence = self._sequence_number()
        self._last_digest = self._fingerprint()
        self._primed = True

    def run(self) -> None:
        try:
            self.prime()
        except Exception:
            pass
        while not self._stop_event.is_set():
            try:
                self._poll_once()
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
            self._stop_event.wait(self.interval)

    def _sequence_number(self) -> int:
        try:
            return int(self._sequence() or 0)
        except Exception:
            return 0

    def stats(self) -> Dict[str, Any]:
        return {"running": self.is_alive(), "polls": self.polls,
                "recorded": self.recorded, "interval": self.interval,
                "last_error": self.last_error, "store": self.store.stats()}
