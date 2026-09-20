"""
main.py - Plethora Mjolnir Application Entrypoint with Win32 Global Hotkey (Alt+Space).
"""

import sys
import os
import ctypes
from ctypes import wintypes
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QAbstractNativeEventFilter, QTimer

from mjolnir.ui import MjolnirWindow

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

def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    window = MjolnirWindow()

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
