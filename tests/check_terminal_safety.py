"""Acceptance checks for terminal command execution safety, staging, and confirmation."""
from __future__ import annotations

import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main() -> int:
    from PySide6 import QtGui, QtWidgets
    from PySide6.QtCore import Qt

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    from mjolnir import gui
    from mjolnir.config import Config
    from mjolnir.embed import HashingEmbedder
    from mjolnir.store import Store
    from mjolnir_ui.mode_router import ModeRouter, is_destructive, is_forced

    failures = []

    def check(name: str, cond: bool, detail: str = ""):
        if cond:
            print(f"  ok   {name}")
        else:
            print(f"  FAIL {name} {detail}")
            failures.append(name)

    print("--- Terminal Command Safety Checks ---")

    # 1. Destructive command regex blacklist
    destructive = [
        "rmdir /s /q C:\\test",
        "RMDIR /S /Q C:\\test",
        "del /f /q myfile.txt",
        "DEL /F myfile.txt",
        "Remove-Item -Path C:\\test -Recurse",
        "remove-item -Recurse foo",
        "format D: /fs:NTFS",
        "FORMAT C:",
        "diskpart /s script.txt",
        "drop-database production",
        "Stop-Computer -Force",
        "Restart-Computer",
        "Set-ExecutionPolicy Unrestricted",
    ]
    for cmd in destructive:
        check(f"destructive flagged: {cmd}", is_destructive(cmd))

    safe = [
        "dir /b /s",
        "ping 1.1.1.1",
        "echo hello world",
        "python --version",
        "git status",
        "cat README.md",
    ]
    for cmd in safe:
        check(f"safe command not flagged: {cmd}", not is_destructive(cmd))

    # 2. Force flag detection
    check("is_forced detects --force", is_forced("rmdir /s /q test --force"))
    check("is_forced detects -Force", is_forced("Remove-Item test -Force"))
    check("is_forced detects -force", is_forced("del file -force"))
    check("is_forced false without flag", not is_forced("rmdir /s /q test"))

    # 3. Visual Staging and Execution Safety in Launcher
    tmp = tempfile.mkdtemp(prefix="mjolnir-safety-")
    cfg = Config(roots=[tmp], extensions=[".md"],
                 index_path=os.path.join(tmp, "index.sqlite3"),
                 embed_backend="hashing")
    store = Store(cfg.index_path)
    win = gui.Launcher(cfg, store, HashingEmbedder())

    try:
        # Destructive command without force -> stage then block on raw Enter
        win.search.setText("> rmdir /s /q C:\\danger")
        win._fire_query()
        check("starts in STAGE_INPUT", win.router.shell_stage == ModeRouter.STAGE_INPUT)

        ev_enter = QtGui.QKeyEvent(QtGui.QKeyEvent.KeyPress, Qt.Key_Return, Qt.NoModifier)
        win._handle_key(ev_enter)
        check("raw Enter transitions to STAGE_CONFIRMING",
              win.router.shell_stage == ModeRouter.STAGE_CONFIRMING)
        check("destructive status warning set",
              "Destructive command" in win.status.text())

        # Second Enter blocked
        ran_blocked = win._handle_key(ev_enter)
        check("second raw Enter is blocked", not ran_blocked)
        check("status warns blocked", "Blocked" in win.status.text() or "Refused" in win.status.text())

        # Escape cancels confirmation
        ev_esc = QtGui.QKeyEvent(QtGui.QKeyEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)
        win._handle_key(ev_esc)
        check("Escape cancels confirmation to STAGE_INPUT",
              win.router.shell_stage == ModeRouter.STAGE_INPUT)

        # Destructive command with --force or Ctrl+Enter is permitted
        win.search.setText("> rmdir /s /q C:\\danger --force")
        win._fire_query()
        ran = []
        win.shell_runner = lambda argv, new_console=False: ran.append(argv) or True
        ev_ctrl_enter = QtGui.QKeyEvent(QtGui.QKeyEvent.KeyPress, Qt.Key_Return, Qt.ControlModifier)
        win._handle_key(ev_ctrl_enter)
        check("destructive with --force / Ctrl+Enter launches", len(ran) == 1)

    finally:
        win._thread.quit()
        win._thread.wait(1000)
        win.close()

    if failures:
        print(f"\nFAIL: {len(failures)} checks failed")
        return 1
    print("\nALL TERMINAL SAFETY CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
