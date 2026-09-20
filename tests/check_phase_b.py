"""Phase B acceptance probe: prefix modes, calculator, clipboard history, launcher.

Headless (``QT_QPA_PLATFORM=offscreen``) and side-effect free:

* the calculator is driven through its grammar (no dynamic code execution),
* every action an ``open`` launch or a ``>`` command would take is asserted as
  **data** (the argv of the plan) or through a monkeypatched recorder,
* the clipboard store is exercised against temporary SQLite files,
* the clipboard watcher is driven with an injected sequence number and reader, so
  the real clipboard is never read, never written and never typed into.

Covers:

2.3  prefix routing (``?`` / ``find`` / ``open`` / ``calc`` / ``=`` / ``>`` / ``cb``),
     the safe expression grammar and its error paths, the cached Start Menu + PATH
     scan, and the terminal command plan
2.4  the clipboard store (insert / de-duplicate / search / cap / skip), the watcher's
     cheap change detection, the stack page at index 2 and Enter = copy + paste
4    the new config fields and their documentation in config.example.json

Exit code is non-zero on any failure.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

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


def main() -> int:
    try:
        from PySide6 import QtGui, QtWidgets
        from PySide6.QtCore import Qt
    except Exception as exc:  # pragma: no cover
        print(f"[SKIP] PySide6 unavailable: {exc}")
        return 0

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    from mjolnir import clipboard as cb, gui, modes, openers, ui_components
    from mjolnir.clipboard import ClipboardStore, ClipboardWatcher
    from mjolnir.config import Config, default_clipboard_path, default_config_dir
    from mjolnir.embed import HashingEmbedder
    from mjolnir.store import Store

    tmp = tempfile.mkdtemp(prefix="mjolnir-phaseb-")
    gui_src = _read("mjolnir/gui.py")
    modes_src = _read("mjolnir/modes.py")
    clipboard_src = _read("mjolnir/clipboard.py")

    from tests.check_phase_b_core import run_phase_b_core
    (programs, fake_apps, shortcuts, store, capped, watch_store,
     no_seq_store, threaded) = run_phase_b_core(check, _read, tmp)

    # ------------------------------------------------------------------ 2.4 GUI
    print("2.4 launcher wiring (stack page 2, Enter = copy + paste)")
    gui_cfg = Config(roots=[tmp], extensions=[".md"],
                     index_path=os.path.join(tmp, "index.sqlite3"),
                     clipboard_db=os.path.join(tmp, "gui-clipboard.db"),
                     clipboard_enabled=False, embed_backend="hashing")
    gui_store = Store(gui_cfg.index_path)
    clip_store = ClipboardStore(gui_cfg.clipboard_db, max_items=50)
    for text_value in ("invoice 2026-09 from Acme", "capacitor report June",
                       "SELECT * FROM chunks"):
        clip_store.add(text_value)
    win = gui.Launcher(gui_cfg, gui_store, HashingEmbedder(), clipboard_store=clip_store)

    copied: list = []
    pasted: list = []
    win.copy_fn = lambda value: (copied.append(value), True)[1]
    win.paste_fn = lambda: pasted.append(True)
    win.paste_delay_ms = 0

    def wait_for(predicate, timeout: float = 5.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            app.processEvents()
            if predicate():
                return True
            time.sleep(0.01)
        return False

    try:
        check("the clipboard page is wired as stack index 2",
              gui.VIEW_CLIPBOARD == 2 and win.stack.count() == 3
              and win.stack.indexOf(win.clipboard_page) == 2
              and win.stack.widget(gui.VIEW_CLIPBOARD) is win.clipboard_page)
        check("the clipboard list is live (no longer the disabled placeholder)",
              win.clipboard_list.isEnabled()
              and win.clipboard_page.layout() is not None)
        check("clipboard_enabled=False leaves the background watcher off",
              win.start_clipboard_watcher() is None and win.clipboard_watcher is None)

        print("2.4 launcher: mode routing")
        for text_value, expected_mode, expected_view in (
                ("? report", modes.MODE_SEARCH, gui.VIEW_SEARCH),
                ("find report", modes.MODE_SEARCH, gui.VIEW_SEARCH),
                ("calc 2 ** 10", modes.MODE_CALC, gui.VIEW_SEARCH),
                ("= 45 * 1.18", modes.MODE_CALC, gui.VIEW_SEARCH),
                ("> ipconfig /flushdns", modes.MODE_SHELL, gui.VIEW_SEARCH),
                ("cb", modes.MODE_CLIPBOARD, gui.VIEW_CLIPBOARD),
                ("cb invoice", modes.MODE_CLIPBOARD, gui.VIEW_CLIPBOARD)):
            win.search.setText(text_value)
            win._fire_query()
            check(f"typing {text_value!r} lands in {expected_mode}",
                  win.mode == expected_mode and win.view == expected_view
                  and win.stack.currentIndex() == expected_view,
                  f"mode={win.mode} view={win.view} stack={win.stack.currentIndex()}")
        check("'cb' switches the launcher onto the clipboard page",
              win.stack.currentIndex() == 2 and win.view == gui.VIEW_CLIPBOARD)
        check("the clipboard page reports the visible and total count",
              "1 of 3" in win.clip_count.text(), win.clip_count.text())
        win.search.setText("cb")
        win._fire_query()
        check("the clipboard page lists the recorded items newest first",
              win.clipboard_list.count() == 3 and len(win.clip_items) == 3
              and win.clip_items[0].text == "SELECT * FROM chunks",
              str([i.text for i in win.clip_items]))
        row_widget = win.clipboard_list.itemWidget(win.clipboard_list.item(0))
        check("every clipboard row shows a preview, a timestamp and its size",
              isinstance(row_widget, ui_components.ClipboardRow)
              and row_widget.preview_label.text() == "SELECT * FROM chunks"
              and "chars" in row_widget.meta_label.text()
              and re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}",
                            row_widget.meta_label.text()),
              row_widget.meta_label.text())
        win.search.setText("cb invoice")
        win._fire_query()
        check("typing after 'cb' searches the history",
              win.clipboard_list.count() == 1
              and win.clip_items[0].text == "invoice 2026-09 from Acme",
              str([i.text for i in win.clip_items]))

        print("2.4 launcher: Enter copies and pastes")
        copied.clear()
        pasted.clear()
        QtWidgets.QApplication.sendEvent(
            win.search, QtGui.QKeyEvent(QtGui.QKeyEvent.KeyPress, Qt.Key_Return,
                                        Qt.NoModifier))
        check("Enter on the clipboard page copies the highlighted entry",
              wait_for(lambda: bool(copied))
              and copied[-1] == "invoice 2026-09 from Acme", str(copied))
        check("Enter then synthesises the paste (recorded, not really typed)",
              wait_for(lambda: bool(pasted)), str(pasted))
        check("the launcher hides so the previous window gets the focus back",
              not win.isVisible())
        check("the toast reports the paste", win.toast.text() == "Pasted",
              win.toast.text())

        copied.clear()
        win.show_centered()
        win.open_clipboard_history("capacitor")
        check("the Alt+Shift+C entry point opens the clipboard page",
              win.view == gui.VIEW_CLIPBOARD and win.stack.currentIndex() == 2
              and win.clipboard_list.count() == 1
              and win.clip_items[0].text == "capacitor report June",
              f"{win.view} {[i.text for i in win.clip_items]}")
        pastes_before = len(pasted)
        check("Ctrl+C on a clipboard entry copies without pasting",
              bool(win._handle_key(QtGui.QKeyEvent(QtGui.QKeyEvent.KeyPress,
                                                   Qt.Key_C, Qt.ControlModifier)))
              and copied[-1:] == ["capacitor report June"]
              and len(pasted) == pastes_before, f"{copied} {pasted}")
        check("Esc leaves clipboard mode for document search",
              win.close_clipboard_mode() and win.view == gui.VIEW_SEARCH
              and win.stack.currentIndex() == gui.VIEW_SEARCH
              and not win.search.text())
        check("'cb' and the global hotkey reach the same page",
              win.open_clipboard_history() and win.view == gui.VIEW_CLIPBOARD
              and win.stack.currentIndex() == gui.VIEW_CLIPBOARD)
        check("the Alt+Shift+C hotkey id routes to the clipboard page",
              gui.HOTKEY_CLIPBOARD == 9002
              and win.route_hotkey(gui.HOTKEY_CLIPBOARD)
              and win.view == gui.VIEW_CLIPBOARD)
        win.close_clipboard_mode()
        check("any other hotkey id still toggles the launcher",
              win.route_hotkey(gui.HOTKEY_TOGGLE) is True
              and win.view != gui.VIEW_CLIPBOARD)
        check("Alt+Shift+C is registered through the existing HotkeyThread",
              "MOD_ALT | MOD_SHIFT, VK_C" in gui_src
              and "fired.connect(win.route_hotkey)" in gui_src
              and "hotkeys.stop()" in gui_src)
        check("the hotkey thread keeps its WM_QUIT shutdown",
              "PostThreadMessageW" in gui_src and "WM_QUIT" in gui_src
              and "def stop(" in gui_src)
        check("the hotkey signal carries the id that fired",
              "fired = Signal(int)" in gui_src and "self.fired.emit" in gui_src)
        check("the launcher defaults to the ctypes clipboard helpers",
              "self.copy_fn = clipboard_history.set_clipboard_text" in gui_src
              and "self.paste_fn = clipboard_history.paste_ctrl_v" in gui_src)

        print("2.4 launcher: calc / open / shell pages")
        win.search.setText("= 45 * 1.18")
        win._fire_query()
        check("the calculator renders in the list and the inspector",
              win.results.count() == 1 and win.insp_title.text() == "= 53.1"
              and "53.1" in win.status.text(),
              f"{win.results.count()} {win.insp_title.text()!r} {win.status.text()!r}")
        check("the calculator row is a mode row widget",
              isinstance(win.results.itemWidget(win.results.item(0)),
                         ui_components.NoticeRow))
        copied.clear()
        win._handle_key(QtGui.QKeyEvent(QtGui.QKeyEvent.KeyPress, Qt.Key_Return,
                                        Qt.NoModifier))
        check("Enter on a calculator result copies it and toasts",
              copied == ["53.1"] and win.toast.text() == "Result copied!",
              f"{copied} {win.toast.text()!r}")
        win.search.setText("= 2 +")
        win._fire_query()
        check("a malformed calculation shows a friendly error, never a crash",
              not win.calc_result.ok and win.calc_result.error in win.status.text()
              and win.results.count() == 1,
              f"{win.calc_result.error!r} / {win.status.text()!r}")
        copied.clear()
        win._handle_key(QtGui.QKeyEvent(QtGui.QKeyEvent.KeyPress, Qt.Key_Return,
                                        Qt.NoModifier))
        check("Enter on a broken calculation copies nothing", not copied)

        print("2.4 launcher: 'open' over a fake Start Menu")
        fake_entries = modes.scan_targets(roots=[programs], pathenv=fake_apps,
                                          use_cache=False)
        real_search = modes.search_targets
        real_open, real_reveal = openers.open_target, openers.reveal
        launched: list = []
        revealed: list = []
        modes.search_targets = (lambda term, entries=None, limit=30, use_cache=True:
                                modes.rank_items(term, fake_entries, ("name", "path"),
                                                 limit=limit))
        openers.open_target = (lambda path, page=None, line=None:
                               launched.append(path) or "default")
        openers.reveal = lambda path: revealed.append(path)
        try:
            win.search.setText("open chrome")
            win._fire_query()
            check("'open chrome' presents the fake Start Menu matches",
                  win.mode == modes.MODE_OPEN and win.results.count() >= 2
                  and [entry.name for entry in win.rows[:2]]
                  == ["Chrome Remote Desktop", "Google Chrome"],
                  str([e.name for e in win.rows]))
            check("the matches are real launcher entries",
                  all(entry.path in set(shortcuts) for entry in win.rows))
            win.results.setCurrentRow(0)
            win._handle_key(QtGui.QKeyEvent(QtGui.QKeyEvent.KeyPress, Qt.Key_Return,
                                            Qt.NoModifier))
            check("Enter opens the highlighted launcher target",
                  launched == [win.rows[0].path], str(launched))
            check("...and the launcher gets out of the way", not win.isVisible())
            win.show_centered()
            win.search.setText("open notepad")
            win._fire_query()
            check("'open notepad' finds the PATH executable",
                  win.rows and win.rows[0].path.endswith("notepad.exe"),
                  str([e.path for e in win.rows]))
            win._handle_key(QtGui.QKeyEvent(QtGui.QKeyEvent.KeyPress, Qt.Key_Return,
                                            Qt.ShiftModifier))
            check("Shift+Enter reveals it in Explorer instead",
                  revealed == [win.rows[0].path] and len(launched) == 1,
                  f"{revealed} {launched}")
            check("the action panel can act on a launcher target too",
                  win.open_action_panel()
                  and win.action_panel.target.path == win.rows[0].path
                  and win.close_action_panel())
        finally:
            modes.search_targets = real_search
            openers.open_target, openers.reveal = real_open, real_reveal

        win.show_centered()
        win.search.setText("> ping 1.1.1.1")
        win._fire_query()
        check("'>' shows the command but does not run it",
              win.mode == modes.MODE_SHELL and win.shell_plan.ok
              and win.rows == [win.shell_plan] and "Nothing runs" in win.status.text(),
              win.status.text())
        check("the command page shows the exact argv it would run",
              all(part in (win.status.text() + win.insp_sub.text())
                  for part in ("powershell.exe", "-NoExit", "ping 1.1.1.1")),
              f"{win.status.text()!r} / {win.insp_sub.text()!r}")
        ran: list = []
        win.shell_runner = (lambda argv, new_console=False:
                            ran.append((list(argv), new_console)) or True)
        win._handle_key(QtGui.QKeyEvent(QtGui.QKeyEvent.KeyPress, Qt.Key_Return,
                                        Qt.NoModifier))
        check("Enter is what actually starts the terminal command",
              bool(ran) and "ping 1.1.1.1" in ran[0][0], str(ran))
        check("the command reaches the shell as argv, verbatim and last",
              ran and ran[0][0][-1] == "ping 1.1.1.1" and not win.isVisible())
        win.show_centered()
        win.search.setText("> ")
        win._fire_query()
        check("an empty '>' command is refused politely",
              not win.shell_plan.ok and bool(win.status.text()))

        print("2.4 launcher: document search after a mode page")
        from mjolnir.search import Hit
        win.mode = modes.MODE_SEARCH
        win.parsed = modes.parse("capacitor report")
        win._busy = False
        win._pending = None
        win._req_id += 1
        files = []
        for index in range(3):
            path = os.path.join(tmp, f"hit{index}.md")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(f"# hit {index}\ncapacitor report\n")
            files.append(path)
        hits = [Hit(path=p, page=1, score=0.5 - i * 0.05,
                    snippet=f"capacitor report {i}", chunk_index=i)
                for i, p in enumerate(files)]
        win._on_results(win._req_id, hits, "")
        check("search results render exactly as before",
              win.results.count() == 3 and len(win.hits) == 3
              and win.view == gui.VIEW_SEARCH and win.status.text() == "3 result(s)",
              f"{win.results.count()} {len(win.hits)} {win.status.text()!r}")
        check("the search rows keep their quick-jump badges",
              [win.results.itemWidget(win.results.item(i)).badge.text()
               for i in range(3)] == ["1", "2", "3"])
        check("the inspector capsule row is back",
              len(win.insp_caps_widget.findChildren(
                  ui_components.Capsule)) == 2)
        check("the footer hints follow the page",
              [label for _key, label in win._hints_for_view()][0] == "Open")
        win.open_clipboard_history()
        check("the footer hints change with the page",
              [label for _key, label in win._hints_for_view()][0] == "Paste")
        win.close_clipboard_mode()

        win.search.setText("calc 6 * 7")
        win._fire_query()
        win._busy = False
        win._req_id += 1
        win._on_results(win._req_id, hits, "")
        check("a late async search result cannot overwrite a mode page",
              win.mode == modes.MODE_CALC and win.results.count() == 1
              and not win.hits,
              f"mode={win.mode} rows={win.results.count()} hits={len(win.hits)}")
    finally:
        try:
            win.stop_clipboard_watcher()
        except Exception:
            pass
        try:
            win._thread.quit()
            win._thread.wait(1500)
        except Exception:
            pass
        try:
            win.close()
        except Exception:
            pass
        for handle in (gui_store, clip_store, store, capped, watch_store,
                       no_seq_store, threaded):
            try:
                handle.close()
            except Exception:
                pass

    print("-" * 62)
    if FAILURES:
        print(f"PHASE B FAIL ({len(FAILURES)}/{CHECKS} checks failed): "
              + "; ".join(FAILURES[:8]))
        return 1
    print(f"PHASE B OK ({CHECKS} checks passed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
