"""Handing a search hit over to the right application.

Three entry points, and none of them is allowed to raise:

* :func:`open_target` - open a file, jumping to a page (PDF) or a line (editor)
* :func:`reveal` - show the file in Explorer with the file pre-selected
* :func:`copy_to_clipboard` - put text on the clipboard without Qt

The PDF chain prefers SumatraPDF (small, fast, accepts ``-page N``), then Adobe
Acrobat/Reader (``/A page=N``), then whatever the shell has registered. Code
files go to VS Code (``code -g file:line``) when it is on ``PATH``, otherwise the
default handler decides.

Everything here is deliberately dependency-free (stdlib only) so the CLI, the
web UI and the Qt launcher can share it.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import Iterable, Optional, Sequence

__all__ = ["open_target", "reveal", "copy_to_clipboard", "CODE_EXTS", "PDF_EXTS",
           "find_editor", "find_pdf_reader"]

#: Extensions VS Code understands (and that have a meaningful "line" concept).
CODE_EXTS = {
    ".py", ".sql", ".js", ".ts", ".jsx", ".tsx", ".java", ".c", ".cpp", ".h",
    ".cs", ".go", ".rs", ".rb", ".php", ".html", ".css", ".json", ".yaml",
    ".yml", ".toml", ".sh", ".ps1", ".md", ".r", ".ipynb",
}

PDF_EXTS = {".pdf"}

# Explorer / acrobat need these; environment variables are expanded on use.
_SUMATRA_CANDIDATES = (
    r"C:\Program Files\SumatraPDF\SumatraPDF.exe",
    r"C:\Program Files (x86)\SumatraPDF\SumatraPDF.exe",
    r"%LOCALAPPDATA%\SumatraPDF\SumatraPDF.exe",
    r"%USERPROFILE%\scoop\apps\sumatrapdf\current\SumatraPDF.exe",
)
_ACROBAT_CANDIDATES = (
    r"C:\Program Files\Adobe\Acrobat DC\Acrobat\Acrobat.exe",
    r"C:\Program Files (x86)\Adobe\Acrobat DC\Acrobat\Acrobat.exe",
    r"C:\Program Files\Adobe\Acrobat\Acrobat.exe",
    r"C:\Program Files (x86)\Adobe\Acrobat\Acrobat.exe",
    r"C:\Program Files\Adobe\Acrobat Reader DC\Reader\AcroRd32.exe",
    r"C:\Program Files (x86)\Adobe\Acrobat Reader DC\Reader\AcroRd32.exe",
    r"C:\Program Files\Adobe\Acrobat Reader\Reader\AcroRd32.exe",
)

_DEVNULL = subprocess.DEVNULL if hasattr(subprocess, "DEVNULL") else None


# --- small process helpers --------------------------------------------------
def _which(*names: str) -> Optional[str]:
    """First of *names* found on ``PATH`` (``code`` resolves to ``code.cmd``)."""
    for name in names:
        try:
            found = shutil.which(name)
        except (OSError, TypeError):
            found = None
        if found:
            return found
    return None


def _first_existing(paths: Iterable[str]) -> Optional[str]:
    for candidate in paths:
        try:
            candidate = os.path.expandvars(candidate)
        except (TypeError, ValueError):
            continue
        if candidate and os.path.isfile(candidate):
            return candidate
    return None


def _run(argv: Sequence[str]) -> bool:
    """Run a launcher process; ``True`` when it started cleanly."""
    try:
        proc = subprocess.run(list(argv), shell=False, check=False,
                              stdout=_DEVNULL, stderr=_DEVNULL)
    except (OSError, ValueError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def _startfile(path: str) -> bool:
    """Shell-open *path* (``os.startfile`` on Windows, opener elsewhere)."""
    starter = getattr(os, "startfile", None)
    if starter is not None:
        try:
            starter(path)
            return True
        except OSError:
            return False
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    return _run([opener, path])


def _find_vscode() -> Optional[str]:
    return _which("code", "code.cmd", "code-insiders")


def _find_sumatra() -> Optional[str]:
    return (_which("sumatrapdf", "SumatraPDF", "SumatraPDF.exe")
            or _first_existing(_SUMATRA_CANDIDATES))


def _find_acrobat() -> Optional[str]:
    return (_which("Acrobat", "Acrobat.exe", "AcroRd32", "AcroRd32.exe")
            or _first_existing(_ACROBAT_CANDIDATES))


def _as_line(line) -> int:
    try:
        number = int(line)
    except (TypeError, ValueError):
        return 1
    return number if number > 0 else 1


def _as_page(page) -> Optional[int]:
    try:
        number = int(page)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


# --- backends ---------------------------------------------------------------
def _open_in_vscode(path: str, line=None) -> bool:
    exe = _find_vscode()
    if not exe:
        return False
    target = f"{path}:{_as_line(line)}"
    if exe.lower().endswith((".cmd", ".bat")):
        # CreateProcess cannot launch a .cmd directly -> go through cmd.exe.
        return _run(["cmd", "/c", exe, "-g", target])
    return _run([exe, "-g", target])


def _open_pdf_at_page(path: str, page) -> Optional[str]:
    """Open a PDF at *page*; returns the backend that was used, or ``None``."""
    number = _as_page(page)
    if number is None:
        return None
    exe = _find_sumatra()
    if exe and _run([exe, "-page", str(number), path]):
        return "sumatra"
    if _find_acrobat() and _run(["cmd", "/c", "start", "", "/A",
                                 f"page={number}", path]):
        return "acrobat"
    return None


def _resolve_open(path: str, page, line) -> Optional[str]:
    target = os.path.abspath(str(path))
    ext = os.path.splitext(target)[1].lower()

    if ext in CODE_EXTS:
        if _open_in_vscode(target, line):
            return "vscode"
        _startfile(target)
        return "default"

    if ext in PDF_EXTS and page not in (None, "", 0):
        backend = _open_pdf_at_page(target, page)
        if backend:
            return backend
        _startfile(target)
        return "default"

    _startfile(target)
    return "default"


def find_editor() -> Optional[str]:
    """The line-aware editor on this machine (VS Code), or ``None``.

    Public wrapper over :func:`_find_vscode` so a caller that wants to build its
    own argv (the action panel) does not have to reach for a private name.
    """
    return _find_vscode()


def find_pdf_reader() -> Optional[str]:
    """A reader that understands a page number (SumatraPDF), or ``None``."""
    return _find_sumatra()


# --- public API -------------------------------------------------------------
def open_target(path: str, page=None, line=None) -> str:
    """Open *path*, optionally at *page* (PDF) or *line* (code).

    Returns the backend that handled it - ``"vscode"``, ``"sumatra"``,
    ``"acrobat"`` or ``"default"`` (the OS shell handler). Never raises: any
    unexpected failure degrades to the default handler and returns ``"default"``.
    """
    result: Optional[str] = None
    try:
        result = _resolve_open(path, page, line)
    except Exception:
        result = None
    if result:
        return result
    try:
        _startfile(os.path.abspath(str(path)))
    except Exception:
        pass
    return "default"


def reveal(path: str) -> None:
    """Show *path* in the file manager with the file pre-selected.

    Windows: ``explorer.exe /select,"<abs path>"``, falling back to opening the
    containing folder. Never raises and never blocks the caller for long.
    """
    try:
        target = os.path.abspath(str(path))
    except (TypeError, ValueError):
        return

    if sys.platform.startswith("win"):
        try:
            subprocess.run(["explorer.exe", "/select,", target], shell=False,
                           check=False, stdout=_DEVNULL, stderr=_DEVNULL)
            return
        except Exception:
            pass
        try:
            _startfile(target if os.path.isdir(target) else os.path.dirname(target))
        except Exception:
            pass
        return

    folder = target if os.path.isdir(target) else (os.path.dirname(target) or os.curdir)
    try:
        _run(["open", folder] if sys.platform == "darwin" else ["xdg-open", folder])
    except Exception:
        pass


# --- clipboard --------------------------------------------------------------
def _clipboard_via_tk(text: str) -> bool:
    try:
        import tkinter
    except Exception:
        return False
    root = None
    try:
        root = tkinter.Tk()
        root.withdraw()
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()          # the OS takes a copy before the root dies
        return True
    except Exception:
        return False
    finally:
        if root is not None:
            try:
                root.destroy()
            except Exception:
                pass


def _clipboard_via_clip(text: str) -> bool:
    """``clip.exe`` fallback (used when tkinter) is unavailable."""
    for encoding in ("utf-8", "utf-16"):
        try:
            proc = subprocess.run(["clip"], input=text.encode(encoding),
                                  shell=False, check=False, stdout=_DEVNULL,
                                  stderr=_DEVNULL)
        except (OSError, ValueError, subprocess.SubprocessError):
            continue
        if proc.returncode == 0:
            return True
    return False


def copy_to_clipboard(text: str) -> bool:
    """Copy *text* to the system clipboard. Returns ``True`` on success.

    Tries tkinter first (no Qt, no console involved), then ``clip.exe`` with
    UTF-8 input. Returns ``False`` - rather than raising - if both fail.
    """
    try:
        payload = "" if text is None else str(text)
    except Exception:
        return False
    if _clipboard_via_tk(payload):
        return True
    if _clipboard_via_clip(payload):
        return True
    return False
