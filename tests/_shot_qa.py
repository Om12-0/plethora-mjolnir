"""Throwaway visual QA: render the three stacked views offscreen to PNGs."""
from __future__ import annotations

import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, r"C:\plethora-mjolnir")

from PySide6 import QtGui, QtWidgets  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402

QtGui.QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
    Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
app = QtWidgets.QApplication([])

from mjolnir import gui, styles, ui_components  # noqa: E402
from mjolnir.config import Config  # noqa: E402
from mjolnir.embed import HashingEmbedder  # noqa: E402
from mjolnir.search import Hit  # noqa: E402
from mjolnir.store import Store  # noqa: E402

app.setStyleSheet(styles.PANEL_QSS)

tmp = tempfile.mkdtemp(prefix="mjolnir-shot-")
cfg = Config(roots=[tmp], extensions=[".md", ".pdf"],
             index_path=os.path.join(tmp, "i.sqlite3"), embed_backend="hashing")
store = Store(cfg.index_path)
win = gui.Launcher(cfg, store, HashingEmbedder())

paths = []
for i in range(6):
    p = os.path.join(tmp, f"circuit_report_{i}.pdf" if i % 2 else f"notes_{i}.md")
    open(p, "w", encoding="utf-8").write("capacitor report\n")
    paths.append(p)

hits = [Hit(path=p, page=(i + 1 if p.endswith(".pdf") else None),
            score=0.0328 - i * 0.0022,
            snippet="The capacitor report from June covers ripple current "
                    "derating across the full temperature range, including the "
                    "AEC-Q200 qualification notes and the measured ESR table.",
            chunk_index=i % 4, matched=["capacitor"]) for i, p in enumerate(paths)]
win.search.setText("capacitor report from June")   # set the query first, then
win._req_id = 3                                    # inject deterministic hits
win._on_results(3, hits, "")
win.show_centered()
for _ in range(4):
    app.processEvents()
print("rows:", win.results.count(), "hits:", len(win.hits))
print("capsules:", [c.text() for c in
                    win.insp_caps_widget.findChildren(ui_components.Capsule)])

out = os.path.join(tempfile.gettempdir(), "mjolnir-qa")
os.makedirs(out, exist_ok=True)
win.grab().save(os.path.join(out, "1_search.png"))

win.open_action_panel()
for _ in range(3):
    app.processEvents()
win.grab().save(os.path.join(out, "2_actions.png"))

win.action_panel.digit("2")          # inline Open With submenu
for _ in range(3):
    app.processEvents()
win.grab().save(os.path.join(out, "3_openwith.png"))

win.close_action_panel()
win.show_view(gui.VIEW_CLIPBOARD)
for _ in range(3):
    app.processEvents()
win.grab().save(os.path.join(out, "4_clipboard.png"))

# icon proof: default vs a recoloured theme
ui_components.app_icon().pixmap(128, 128).save(os.path.join(out, "icon_default.png"))
ui_components.app_icon({"icon_gradient": ("#FF3B30", "#FFCC00"),
                        "icon_fg": "#FFFFFF"}).pixmap(128, 128).save(
    os.path.join(out, "icon_themed.png"))

print("shots in", out)
print("final rows:", win.results.count())
print("final capsules:", [c.text() for c in
                          win.insp_caps_widget.findChildren(ui_components.Capsule)])
win._thread.quit()
win._thread.wait(1000)
store.close()
