"""High-DPI / geometry check for the dual-pane launcher (offscreen-safe).

Sets the Qt HighDpiScaleFactorRoundingPolicy to PassThrough *before* creating
the QApplication, builds the launcher with ``QT_QPA_PLATFORM=offscreen``,
asserts the default window/panel size is 760x480, grabs a snapshot, and prints
``HighDPI OK``. Exit code is non-zero on failure.
"""
from __future__ import annotations

import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    try:
        from PySide6 import QtWidgets
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QGuiApplication
    except Exception as exc:
        print(f"[SKIP] PySide6 unavailable: {exc}")
        return 0

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    from mjolnir.config import Config
    from mjolnir.embed import HashingEmbedder
    from mjolnir.gui import Launcher
    from mjolnir.store import Store

    tmp = tempfile.mkdtemp(prefix="mjolnir-hidpi-")
    cfg = Config(
        roots=[tmp], extensions=[".txt"], excludes=[],
        index_path=os.path.join(tmp, "index.sqlite3"),
        embed_backend="hashing",
    )
    assert int(cfg.ui_width) == 760, f"ui_width={cfg.ui_width}"
    assert int(cfg.ui_height) == 480, f"ui_height={cfg.ui_height}"

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    store = Store(cfg.index_path)
    win = Launcher(cfg, store, HashingEmbedder())
    try:
        win.show()
        app.processEvents()
        app.processEvents()

        w, h = win.width(), win.height()
        assert (w, h) == (760, 480), f"window size {w}x{h}, expected 760x480"
        pw, ph = win.panel.width(), win.panel.height()
        assert abs(pw - 760) <= 4 and abs(ph - 480) <= 4, (
            f"panel size {pw}x{ph}, expected ~760x480")

        # Snapshot proves the dual-pane surface renders offscreen.
        shot = os.path.join(tmp, "launcher.png")
        win.grab().save(shot)
        assert os.path.isfile(shot) and os.path.getsize(shot) > 0, "empty snapshot"

        # Dual-pane anatomy sanity: results + preview widgets exist.
        assert win.results is not None and win.preview is not None
        print(f"HighDPI OK (window {w}x{h}, panel {pw}x{ph}, shot {shot})")
        return 0
    except AssertionError as exc:
        print(f"[FAIL] {exc}")
        return 1
    finally:
        try:
            win._thread.quit()
            win._thread.wait(1500)
        except Exception:
            pass
        try:
            win.close()
        except Exception:
            pass
        try:
            store.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
