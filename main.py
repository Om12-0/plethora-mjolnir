"""
main.py - Plethora Mjolnir Application Entrypoint with Win32 Global Hotkey (Alt+Space).
Enforces UAC administrator elevation so bundled Everything 1.4 can read NTFS USN journals.
"""

import sys
import os
import ctypes
from ctypes import wintypes
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QAbstractNativeEventFilter, QTimer
from PySide6.QtGui import QIcon

from mjolnir.ui import MjolnirWindow

def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False

def elevate_and_restart():
    """Relaunches the current executable/script requesting Windows UAC elevation."""
    if hasattr(sys, "_MEIPASS"):
        # Running as PyInstaller frozen exe
        executable = sys.executable
        params = " ".join([f'"{arg}"' for arg in sys.argv[1:]])
    else:
        # Running in dev environment via python interpreter
        executable = sys.executable
        params = f'"{os.path.abspath(sys.argv[0])}" ' + " ".join([f'"{arg}"' for arg in sys.argv[1:]])

    # 1 = SW_SHOWNORMAL
    ret = ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        executable,
        params,
        os.getcwd(),
        1
    )
    # ShellExecute returns > 32 on success
    if int(ret) > 32:
        sys.exit(0)
    else:
        print("[WARN] User declined UAC elevation prompt.")
        sys.exit(1)

HOTKEY_ID = 9002
MOD_ALT = 0x0001
VK_SPACE = 0x20

class Win32HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, window):
        super().__init__()
        self.window = window

    def nativeEventFilter(self, eventType, message):
        if eventType == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(message.__int__())
            if msg.message == 0x0312 and msg.wParam == HOTKEY_ID:
                if self.window.isVisible():
                    self.window.hide()
                else:
                    self.window.show_centered()
                return True, 0
        return False, 0

def _app_icon_path():
    for name in ("icon.png", "icon.ico"):
        p = os.path.join(os.path.dirname(__file__), "assets", name)
        if os.path.exists(p):
            return p
    return None

def main():
    # 1. Enforce Admin Elevation First
    if not is_admin():
        elevate_and_restart()

    # 2. Start Qt Application
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    icon_path = _app_icon_path()
    if icon_path:
        app.setWindowIcon(QIcon(icon_path))

    window = MjolnirWindow()

    # Register Win32 Global Hotkey (Alt+Space)
    user32 = ctypes.windll.user32
    if not user32.RegisterHotKey(None, HOTKEY_ID, MOD_ALT, VK_SPACE):
        print("[WARN] Could not register global Alt+Space hotkey.")

    event_filter = Win32HotkeyFilter(window)
    app.installNativeEventFilter(event_filter)

    QTimer.singleShot(100, window.show_centered)

    try:
        ret = app.exec()
    finally:
        user32.UnregisterHotKey(None, HOTKEY_ID)
        sys.exit(ret)

if __name__ == "__main__":
    main()
