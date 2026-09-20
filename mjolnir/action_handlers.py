"""Command builders, external handlers discovery, and Recycle Bin integration. Qt-free."""
from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from . import openers

FO_DELETE = 3
FOF_SILENT = 0x0004
FOF_NOCONFIRMATION = 0x0010
FOF_ALLOWUNDO = 0x0040
FOF_NOERRORUI = 0x0400

OPEN_WITH_DIALOG_ID = "choose_another_app"

KNOWN_HANDLERS: Tuple[Tuple[str, str, str, Tuple[str, ...]], ...] = (
    ("vscode", "Visual Studio Code", "editor",
     ("code.cmd", "code.exe", r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe")),
    ("notepad", "Notepad", "editor", ("notepad.exe",)),
    ("notepad_plus_plus", "Notepad++", "editor",
     ("notepad++.exe", r"%ProgramFiles%\Notepad++\notepad++.exe",
      r"%ProgramFiles(x86)%\Notepad++\notepad++.exe")),
    ("sublime", "Sublime Text", "editor",
     ("subl.exe", r"%ProgramFiles%\Sublime Text\sublime_text.exe",
      r"%ProgramFiles%\Sublime Text 3\subl.exe")),
    ("cursor", "Cursor", "editor",
     ("cursor.cmd", "cursor.exe", r"%LOCALAPPDATA%\Programs\cursor\Cursor.exe")),
    ("sumatra", "SumatraPDF", "viewer",
     ("sumatrapdf.exe", r"%LOCALAPPDATA%\SumatraPDF\SumatraPDF.exe",
      r"%ProgramFiles%\SumatraPDF\SumatraPDF.exe")),
    ("explorer", "Windows Explorer", "system", ("explorer.exe",)),
)


@dataclass(frozen=True)
class Handler:
    """An application on this machine that can open a file."""

    id: str
    label: str
    exe: str
    kind: str = "editor"

    def argv(self, path: str) -> List[str]:
        exe = self.exe
        if os.name == "nt" and exe.lower().endswith((".cmd", ".bat")):
            return ["cmd", "/c", exe, path]
        return [exe, path]


def _which(which, *names: str) -> Optional[str]:
    for name in names:
        if os.path.isabs(name):
            expanded = os.path.expandvars(name)
            if os.path.isfile(expanded):
                return expanded
            continue
        try:
            found = which(name)
        except (OSError, TypeError):
            found = None
        if found:
            return found
    return None


def _which_with(lookup, exists, candidates: Sequence[str]) -> Optional[str]:
    for candidate in candidates:
        if os.path.isabs(candidate) or candidate.startswith("%"):
            expanded = os.path.expandvars(candidate)
            if exists(expanded):
                return expanded
            continue
        try:
            resolved = lookup(candidate)
        except (OSError, TypeError):
            resolved = None
        if resolved:
            return resolved
    return None


def known_handlers(path: Optional[str] = None, which=None, isfile=None) -> List[Handler]:
    lookup = which or shutil.which
    exists = isfile or os.path.isfile
    found: List[Handler] = []
    for handler_id, label, kind, candidates in KNOWN_HANDLERS:
        try:
            exe = _which_with(lookup, exists, candidates)
        except Exception:
            exe = None
        if exe:
            found.append(Handler(handler_id, label, exe, kind))
    return found


def argv_reveal(path: str) -> List[str]:
    return ["explorer.exe", "/select,", os.path.abspath(str(path))]


def argv_open_with_dialog(path: str) -> List[str]:
    return ["rundll32", "shell32.dll,OpenAs_RunDLL", os.path.abspath(str(path))]


def argv_terminal(directory: str, which=None) -> List[str]:
    folder = os.path.abspath(str(directory or os.curdir))
    lookup = which or shutil.which
    wt = _which(lookup, "wt", "wt.exe")
    if wt:
        return [wt, "-d", folder]
    return ["powershell", "-NoExit", "-Command", f"Set-Location -LiteralPath '{folder}'"]


def deep_link_backend(path: str) -> Optional[str]:
    ext = os.path.splitext(str(path or ""))[1].lower()
    if ext in openers.CODE_EXTS and openers.find_editor():
        return "vscode"
    if ext in openers.PDF_EXTS and openers.find_pdf_reader():
        return "pdf"
    return None


def _as_int(val) -> Optional[int]:
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def argv_deep_link(path: str, page=None, line=None) -> Optional[List[str]]:
    target = os.path.abspath(str(path))
    ext = os.path.splitext(target)[1].lower()
    number = _as_int(page)
    lineno = max(1, _as_int(line) or 1)

    if ext in openers.CODE_EXTS:
        exe = openers.find_editor()
        if not exe:
            return None
        spec = f"{target}:{lineno}"
        if exe.lower().endswith((".cmd", ".bat")):
            return ["cmd", "/c", exe, "-g", spec]
        return [exe, "-g", spec]

    if ext in openers.PDF_EXTS and number and number > 0:
        exe = openers.find_pdf_reader()
        if not exe:
            return None
        return [exe, "-page", str(number), target]

    return None


def recycle_request(path: str) -> Dict[str, Any]:
    return {
        "wFunc": FO_DELETE,
        "pFrom": os.path.abspath(str(path)),
        "flags": FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI,
        "allow_undo": True,
    }


def recycle_path(path: str) -> bool:
    if not sys.platform.startswith("win"):
        return False
    try:
        import ctypes
        from ctypes import wintypes

        request = recycle_request(path)

        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [
                ("hwnd", wintypes.HWND),
                ("wFunc", wintypes.UINT),
                ("pFrom", wintypes.LPCWSTR),
                ("pTo", wintypes.LPCWSTR),
                ("fFlags", ctypes.c_ushort),
                ("fAnyOperationsAborted", wintypes.BOOL),
                ("hNameMappings", ctypes.c_void_p),
                ("lpszProgressTitle", wintypes.LPCWSTR),
            ]

        source = ctypes.c_wchar_p(request["pFrom"] + "\0\0")
        op = SHFILEOPSTRUCTW()
        op.hwnd = None
        op.wFunc = request["wFunc"]
        op.pFrom = ctypes.cast(source, wintypes.LPCWSTR)
        op.pTo = None
        op.fFlags = request["flags"]
        op.fAnyOperationsAborted = False
        result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        return int(result) == 0 and not bool(op.fAnyOperationsAborted)
    except Exception:
        return False
