"""Acceptance check for token-driven tray icon theme responsiveness."""
from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main() -> int:
    from PySide6 import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    from mjolnir_ui.tray_icon import app_icon, icon_bytes
    from mjolnir import styles

    default_icon = app_icon()
    default_bytes = icon_bytes(default_icon)

    # 1. Custom gradient and fg yields different bytes
    theme1 = {"icon_gradient": ("#FF1122", "#334455"), "icon_fg": "#FFFFFF"}
    icon1 = app_icon(theme1)
    bytes1 = icon_bytes(icon1)
    if bytes1 == default_bytes:
        print("FAIL: theme1 produced identical icon bytes to default")
        return 1
    print("  ok   custom gradient theme alters icon bytes")

    # 2. Accent-only recolor yields different bytes
    theme2 = {"accent_solid": "#00FF88"}
    icon2 = app_icon(theme2)
    bytes2 = icon_bytes(icon2)
    if bytes2 == default_bytes or bytes2 == bytes1:
        print("FAIL: accent_solid recolor produced identical icon bytes")
        return 1
    print("  ok   accent-only theme alters icon bytes")

    # 3. Cache returns identical instance
    cached_icon = app_icon(theme1)
    if cached_icon is not icon1:
        print("FAIL: app_icon failed to return cached instance for identical theme")
        return 1
    print("  ok   identical theme returns cached QIcon")

    print("\nALL TRAY THEME CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
