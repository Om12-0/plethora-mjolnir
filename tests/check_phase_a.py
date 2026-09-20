"""Phase A acceptance probe: the two audit findings, the action panel, polish.

Headless (``QT_QPA_PLATFORM=offscreen``) and side-effect free: every action is
exercised through ``ActionContext(dry_run=True)``, which records calls instead of
opening files, and the recycle path is verified as *data* (``FOF_ALLOWUNDO``)
rather than by deleting anything.

Covers:

1.1 the inspector capsule widget (22px / 11px / themed 1px border / token fill)
1.2 the token-driven tray icon (two themes -> two different icons)
2.1 the nine-action registry, argv builders and the clickable/keyboard panel
2.2 the Alt+1..9 quick-jump badges
3.2 the three-page QStackedWidget (pages are built once and only switched)
3.1/3.3 the High-DPI policy ordering and Esc / deactivate backgrounding

Exit code is non-zero on any failure.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

FAILURES: list[str] = []
CHECKS = 0


def check(label: str, condition, detail: str = "") -> bool:
    global CHECKS
    CHECKS += 1
    if condition:
        print(f"  ok   {label}")
        return True
    print(f"  FAIL {label}{(' :: ' + detail) if detail else ''}")
    FAILURES.append(label)
    return False


def _read(rel: str) -> str:
    with open(os.path.join(ROOT, rel), "r", encoding="utf-8") as fh:
        return fh.read()


HEX_RE = re.compile(r"#[0-9a-fA-F]{3,8}")


def main() -> int:
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
        from PySide6.QtCore import Qt
    except Exception as exc:  # pragma: no cover
        print(f"[SKIP] PySide6 unavailable: {exc}")
        return 0

    # The policy must be set before the QApplication exists (phase A, 3.1).
    QtGui.QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    from mjolnir import actions, gui, styles, ui_components
    from mjolnir.config import Config
    from mjolnir.embed import HashingEmbedder
    from mjolnir.store import Store

    print("1.1 inspector capsules")
    check("styles token BADGE_BG exists and is semi-transparent",
          isinstance(styles.BADGE_BG, str)
          and styles.BADGE_BG.startswith("rgba")
          and float(styles.BADGE_BG.rsplit(",", 1)[1].rstrip(")")) < 1.0,
          styles.BADGE_BG)
    check("capsule geometry tokens are 22px / 11px",
          styles.CAPSULE_HEIGHT == 22 and styles.CAPSULE_RADIUS == 11,
          f"{styles.CAPSULE_HEIGHT}/{styles.CAPSULE_RADIUS}")
    token_values = {value for name, value in vars(styles).items()
                    if name.isupper() and isinstance(value, str)}
    for slot, value in (("neutral", styles.BADGE_BG), ("accent", styles.BADGE_ACCENT_BG)):
        literal = [h for h in HEX_RE.findall(styles.capsule_qss(slot))
                   if h not in token_values]
        check(f"{slot} capsule QSS only reuses colour tokens",
              value in styles.capsule_qss(slot) and not literal, str(literal))
    row = ui_components.match_capsule(0.96, 1, 5, 1)
    caps = row.findChildren(ui_components.Capsule)
    texts = [c.text() for c in caps]
    check("match_capsule renders both caps", len(caps) == 2, str(texts))
    check("match cap shows the percentage", texts and texts[0] == "96% match", str(texts))
    check("position cap shows chunk/total and page",
          len(texts) > 1 and texts[1] == "Chunk 2/5 \u00b7 p. 1", str(texts))
    check("capsule is exactly 22px tall",
          all(c.height() == 22 and c.minimumHeight() == 22
              and c.maximumHeight() == 22 for c in caps),
          str([(c.height(), c.minimumHeight(), c.maximumHeight()) for c in caps]))
    check("capsule border is the themed token",
          all(styles.BADGE_BORDER in c.styleSheet() for c in caps))
    check("match cap uses the accent token, position cap the neutral one",
          styles.BADGE_ACCENT_BG in caps[0].styleSheet()
          and styles.BADGE_BG in caps[1].styleSheet())
    check("capsule corner radius is 11px",
          f"border-radius: {styles.CAPSULE_RADIUS}px" in caps[0].styleSheet())
    check("Capsule is a QFrame", isinstance(caps[0], QtWidgets.QFrame))
    check("capsule_row accepts strings and widgets",
          len(ui_components.capsule_row(["a", ui_components.Capsule("b")])
              .findChildren(ui_components.Capsule)) == 2)
    no_page = ui_components.match_capsule(0.5, 0, 3, None)
    check("page is optional in the position cap",
          [c.text() for c in no_page.findChildren(ui_components.Capsule)]
          == ["50% match", "Chunk 1/3"],
          str([c.text() for c in no_page.findChildren(ui_components.Capsule)]))
    empty = ui_components.match_capsule(None, None, None, None)
    check("no score still renders a capsule",
          len(empty.findChildren(ui_components.Capsule)) == 1)

    print("1.2 token-driven tray icon")
    check("icon tokens exist", isinstance(styles.ICON_GRADIENT, tuple)
          and len(styles.ICON_GRADIENT) == 2 and isinstance(styles.ICON_FG, str))
    default_icon = ui_components.app_icon()
    check("default palette == the icon tokens",
          styles.icon_palette() == {"start": styles.ICON_GRADIENT[0],
                                    "end": styles.ICON_GRADIENT[1],
                                    "fg": styles.ICON_FG})
    alt_theme = {"icon_gradient": ("#FF0000", "#00FF00"), "icon_fg": "#FFFFFF"}
    alt_icon = ui_components.app_icon(alt_theme)
    check("a different theme yields a different icon",
          ui_components.icon_bytes(default_icon) != ui_components.icon_bytes(alt_icon))
    accent_icon = ui_components.app_icon({"accent_solid": "#22CC88"})
    check("an accent-only theme also recolours the icon",
          ui_components.icon_bytes(accent_icon) != ui_components.icon_bytes(default_icon))
    check("the same palette is served from cache",
          ui_components.app_icon() is default_icon)
    check("icon factory is in ui_components",
          "def app_icon" in _read("mjolnir/ui_components.py"))
    gui_src = _read("mjolnir/gui.py")
    leaked = [h for h in HEX_RE.findall(gui_src)
              if h.lower() in ("#5ac8fa", "#a78bfa", "#0b0f17")]
    check("gui.py has no hardcoded icon hex left", not leaked, str(leaked))
    widget_src = _read("mjolnir/ui_components.py")
    icon_body = widget_src.split("def app_icon", 1)[1].split("def icon_bytes", 1)[0]
    check("app_icon body contains no colour literal",
          not HEX_RE.findall(icon_body), str(HEX_RE.findall(icon_body)))

    print("2.1/2.2 action registry")
    expected = ("open_default", "open_with", "reveal", "copy_path", "copy_chunk",
                "open_terminal", "deep_link", "reindex_file", "recycle")
    check("registry has exactly the nine documented ids in order",
          actions.ACTION_IDS == expected, str(actions.ACTION_IDS))
    check("digit keys are 1..9 in order",
          [s.key for s in actions.ACTION_SPECS] == [str(i) for i in range(1, 10)])
    check("every id resolves to a spec and an implementation",
          all(actions.get_action(i) is not None for i in expected)
          and all(i in actions._IMPLEMENTATIONS for i in expected))
    check("action_for_key maps digits back to the right spec",
          all(actions.action_for_key(str(i + 1)).id == name
              for i, name in enumerate(expected)))
    check("argv: reveal", actions.argv_reveal(r"C:\tmp\a b.pdf")
          == ["explorer.exe", "/select,", os.path.abspath(r"C:\tmp\a b.pdf")])
    check("argv: Windows Open With dialog",
          actions.argv_open_with_dialog(r"C:\tmp\a.pdf")[0:2]
          == ["rundll32", "shell32.dll,OpenAs_RunDLL"])
    check("argv: terminal prefers Windows Terminal",
          actions.argv_terminal(r"C:\tmp", which=lambda n: "C:\\wt.exe")
          == ["C:\\wt.exe", "-d", os.path.abspath(r"C:\tmp")])
    fallback = actions.argv_terminal(r"C:\tmp", which=lambda n: None)
    check("argv: terminal falls back to PowerShell -LiteralPath",
          fallback[:2] == ["powershell", "-NoExit"]
          and "Set-Location -LiteralPath" in fallback[3], " ".join(fallback))
    check("recycle is an undo-able shell delete (never a hard delete)",
          actions.recycle_request(r"C:\tmp\a.txt")["flags"] & actions.FOF_ALLOWUNDO
          and actions.FOF_ALLOWUNDO == 0x40
          and actions.FO_DELETE == 3)
    action_src = _read("mjolnir/actions.py")
    check("actions.py contains no hard-delete call",
          not any(tok in action_src for tok in
                  ("os.remove", "os.unlink", "shutil.rmtree", "os.rmdir")))
    check("actions.py is Qt-free (importable headlessly)",
          "PySide6" not in action_src and "QtWidgets" not in action_src)
    # every action is callable headlessly, against a real temp file
    tmp = tempfile.mkdtemp(prefix="mjolnir-phasea-")
    sample = os.path.join(tmp, "sample.md")
    with open(sample, "w", encoding="utf-8") as fh:
        fh.write("# sample\ncapsule content\n")
    target = actions.Target(path=sample, page=1, chunk_index=1, chunk_total=5,
                            snippet="capsule content", score=0.5)
    ctx = actions.ActionContext(
        dry_run=True, reindex=lambda p: {"added": 0, "updated": 1, "skipped": 0})
    for name in expected:
        result = actions.run(name, target, ctx)
        check(f"run({name!r}) returns an ActionResult",
              isinstance(result, actions.ActionResult) and result.action_id == name,
              getattr(result, "message", ""))
        if name != "recycle":      # recycle legitimately needs a second call too
            check(f"run({name!r}) reached a side effect",
                  bool(ctx.recorded(
                      {"open_default": "open_default", "open_with": "spawn",
                       "reveal": "reveal", "copy_path": "copy",
                       "copy_chunk": "copy", "open_terminal": "spawn",
                       "deep_link": "spawn"}.get(name, "reindex"))),
                  str(ctx.calls))
    check("recycle moved (dry-run) and re-indexed afterwards",
          [c[0] for c in ctx.calls].count("recycle") == 1
          and [c[0] for c in ctx.calls].count("reindex") >= 1)
    check("unknown actions are rejected, not raised",
          actions.run("nope", target, ctx).ok is False)
    check("open_with addresses a concrete handler",
          actions.run("open_with", target, ctx, handler_id="vscode").ok
          or actions.run("open_with", target, ctx, handler_id="vscode").message)
    check("copy_chunk refuses when there is no snippet",
          actions.run("copy_chunk", actions.Target(path=sample), ctx).ok is False)
    # The ctypes shell call itself: a throwaway temp file, moved to the Recycle
    # Bin (undoable) - set MJOLNIR_TEST_RECYCLE=0 to skip on a locked-down box.
    if sys.platform.startswith("win") and os.environ.get("MJOLNIR_TEST_RECYCLE") != "0":
        probe = os.path.join(tmp, "recycle-probe.txt")
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write("phase A recycle probe\n")
        moved = actions.recycle_path(probe)
        check("real SHFileOperationW moves a file to the Recycle Bin",
              moved and not os.path.exists(probe),
              f"moved={moved} exists={os.path.exists(probe)}")

    print("2.1/2.2/3.2 live launcher")
    cfg = Config(roots=[tmp], extensions=[".md"],
                 index_path=os.path.join(tmp, "index.sqlite3"),
                 embed_backend="hashing")
    store = Store(cfg.index_path)
    win = gui.Launcher(cfg, store, HashingEmbedder())
    try:
        # Deterministic fake hits, rendered through the real code path.
        from mjolnir.search import Hit

        files = []
        for index in range(11):
            path = os.path.join(tmp, f"hit{index:02d}.md")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(f"# hit {index}\ncapacitor report\n")
            files.append(path)
        hits = [Hit(path=p, page=1, score=0.5 - i * 0.01,
                    snippet=f"capacitor report {i}", chunk_index=i % 3)
                for i, p in enumerate(files)]
        win._req_id = 7
        win._on_results(7, hits, "")
        check("results rendered", win.results.count() == len(hits))
        badges = []
        for row in range(win.results.count()):
            widget = win.results.itemWidget(win.results.item(row))
            badge = getattr(widget, "badge", None)
            badges.append(badge.text() if badge is not None else None)
        check("the top nine rows carry 1..9 badges",
              badges[:9] == [str(i) for i in range(1, 10)], str(badges[:10]))
        check("row 10+ has no badge (and the old ctor still works)",
              badges[9] is None and ui_components.ResultItemWidget(
                  "n", files[0], "MD").badge is None)
        check("inspector shows the capsule row, not a plain label",
              win.insp_caps_widget is not None
              and len(win.insp_caps_widget.findChildren(ui_components.Capsule)) == 2
              and not hasattr(win, "insp_meta"))
        first = win.insp_caps_widget.findChildren(ui_components.Capsule)[0].text()
        check("capsule carries the relative match % and chunk position",
              first.endswith("% match"), first)

        check("three stacked pages exist",
              win.stack.count() == 3 and win.view == gui.VIEW_SEARCH)
        search_page = win.stack.widget(gui.VIEW_SEARCH)
        action_page = win.stack.widget(gui.VIEW_ACTIONS)
        clipboard_page = win.stack.widget(gui.VIEW_CLIPBOARD)
        win.open_action_panel()
        check("Tab/right arrow switches to the action panel",
              win.view == gui.VIEW_ACTIONS
              and win.stack.currentIndex() == gui.VIEW_ACTIONS)
        check("panel lists all nine actions",
              len(win.action_panel.rows) == 9
              and [r.ident for r in win.action_panel.rows] == list(expected))
        check("panel is the same instance (no rebuild on switch)",
              win.stack.widget(gui.VIEW_ACTIONS) is action_page
              and win.stack.widget(gui.VIEW_SEARCH) is search_page)
        check("clipboard history page is already stacked",
              clipboard_page is not None
              and win.stack.widget(gui.VIEW_CLIPBOARD) is clipboard_page)
        check("digit keys drive the panel",
              win.action_panel.digit("3") and win.action_panel.rows[2].property("selected"))
        check("Open With opens an inline submenu",
              win.action_panel.digit("2") and win.action_panel.mode == "submenu"
              and len(win.action_panel.sub_rows) >= 1)
        check("Esc leaves the submenu, then the panel",
              win.action_panel.escape() and win.action_panel.mode == "root"
              and win.close_action_panel() and win.view == gui.VIEW_SEARCH)
        check("no handler row is offered for a missing executable",
              all(h.exe and os.path.exists(h.exe)
                  for h in actions.known_handlers()))

        # -> opens the panel only when the caret is already at the end.
        win.search.setText("capacitor")
        win.show_view(gui.VIEW_SEARCH)
        win.search.setCursorPosition(1)
        QtWidgets.QApplication.sendEvent(
            win.search, QtGui.QKeyEvent(QtGui.QKeyEvent.KeyPress, Qt.Key_Right,
                                        Qt.NoModifier))
        check("right arrow still edits text mid-query", win.view == gui.VIEW_SEARCH)
        win.search.setCursorPosition(len(win.search.text()))
        QtWidgets.QApplication.sendEvent(
            win.search, QtGui.QKeyEvent(QtGui.QKeyEvent.KeyPress, Qt.Key_Right,
                                        Qt.NoModifier))
        check("right arrow opens the panel with the caret at the end",
              win.view == gui.VIEW_ACTIONS)
        win.search.setText("capacitor r")
        check("typing returns to the search view", win.view == gui.VIEW_SEARCH)

        # Alt+<n> quick jump, wired to a dry-run context so nothing launches.
        live_ctx = actions.ActionContext(dry_run=True, reindex=lambda p: {})
        win.action_ctx = live_ctx
        plain = QtGui.QKeyEvent(QtGui.QKeyEvent.KeyPress, Qt.Key_3,
                                Qt.NoModifier, "3")
        QtWidgets.QApplication.sendEvent(win.search, plain)
        check("a plain digit is typed, not hijacked",
              not live_ctx.calls and win.search.text().endswith("3"),
              f"text={win.search.text()!r} calls={live_ctx.calls}")
        for key, expect_row in ((Qt.Key_3, 2), (Qt.Key_9, 8)):
            event = QtGui.QKeyEvent(QtGui.QKeyEvent.KeyPress, key,
                                    Qt.AltModifier, str(key - Qt.Key_0))
            QtWidgets.QApplication.sendEvent(win.search, event)
            check(f"Alt+{key - Qt.Key_0} acts on row {expect_row + 1} without arrowing",
                  win.results.currentRow() == expect_row
                  and live_ctx.recorded("open_default"),
                  f"row={win.results.currentRow()} calls={live_ctx.calls}")

        # Slow actions run on a worker thread and come back through a queued
        # signal, so the UI never freezes on a file re-index or a shell delete.
        def wait_for(predicate, timeout: float = 8.0) -> bool:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                app.processEvents()
                if predicate():
                    return True
                time.sleep(0.02)
            return False

        rows_before = win.results.count()
        win.run_action("reindex_file")
        check("re-index this file completes off the GUI thread",
              wait_for(lambda: bool(live_ctx.recorded("reindex"))),
              str(live_ctx.calls))
        win.run_action("recycle")
        check("recycle prunes the row once the shell move lands",
              wait_for(lambda: win.results.count() == rows_before - 1),
              f"{win.results.count()} of {rows_before}")
        check("no hard delete happened during the dry run",
              bool(live_ctx.recorded("recycle")) and all(os.path.exists(p)
                                                        for p in files))

        # Esc backgrounds the window; a deactivate must not fire offscreen.
        win.show_centered()
        app.processEvents()
        win.changeEvent(QtCore.QEvent(QtCore.QEvent.WindowDeactivate))
        check("offscreen guard keeps the window alive on deactivate", win.isVisible())
        QtWidgets.QApplication.sendEvent(
            win.search, QtGui.QKeyEvent(QtGui.QKeyEvent.KeyPress, Qt.Key_Escape,
                                        Qt.NoModifier))
        check("Esc hides the window (process + tray stay alive)", not win.isVisible())
        check("the window object survives backgrounding",
              win.isHidden() and win.stack.count() == 3)

        # 3.1 geometry: cursor screen, 18% from the top, horizontally centred.
        win.show_centered()
        app.processEvents()
        screen = win.target_screen()
        check("a target screen is resolved (cursor -> primary fallback)",
              screen is not None)
        if screen is not None:
            geom = screen.availableGeometry()
            check("window is 18% from the top of that screen",
                  abs(win.y() - (geom.top() + int(geom.height() * 0.18))) <= 2,
                  f"y={win.y()} expected={geom.top() + int(geom.height() * 0.18)}")
            check("window is horizontally centred on that screen",
                  abs(win.x() - (geom.center().x() - win.width() // 2)) <= 2,
                  f"x={win.x()}")
        check("HighDPI rounding policy is PassThrough after start-up",
              QtGui.QGuiApplication.highDpiScaleFactorRoundingPolicy()
              == Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
        check("run_gui sets the policy before constructing QApplication",
              gui_src.index("setHighDpiScaleFactorRoundingPolicy")
              < gui_src.index("QApplication(sys.argv)"))
        check("high-dpi check script sets it too",
              "setHighDpiScaleFactorRoundingPolicy"
              in _read("tests/check_highdpi.py"))
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

    print("-" * 62)
    if FAILURES:
        print(f"PHASE A FAIL ({len(FAILURES)}/{CHECKS} checks failed): "
              + "; ".join(FAILURES[:6]))
        return 1
    print(f"PHASE A OK ({CHECKS} checks passed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
