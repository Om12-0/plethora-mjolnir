"""Core frameless launcher window, geometry, multi-monitor placement, and animations."""
from __future__ import annotations

import os
import sys
import threading

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import QTimer, Qt, Signal

from mjolnir import actions, clipboard as clipboard_history, modes, styles
from mjolnir.search import Searcher

from .action_panel import ActionPanel
from .hotkey_manager import (
    HotkeyThread, HOTKEY_PRIMARY, HOTKEY_FALLBACK_1, HOTKEY_FALLBACK_2, HOTKEY_CLIPBOARD
)
from .mode_router import ModeRouter
from .mode_views import ModeViewsMixin
from .result_list import keycaps, make_shadow
from .search_controller import SearchControllerMixin, SearchWorker, _SearchSignal
from .tray_icon import app_icon

VIEW_SEARCH, VIEW_ACTIONS, VIEW_CLIPBOARD = 0, 1, 2
PASTE_DELAY_MS = 160

HINTS_SEARCH = (("\u23ce", "Open"), ("Tab", "Actions"),
                ("Alt+1\u20139", "Jump"), ("Ctrl+C", "Copy"), ("Esc", "Close"))
HINTS_OPEN = (("\u23ce", "Open"), ("Shift+\u23ce", "Reveal"),
              ("Tab", "Actions"), ("Alt+1\u20139", "Jump"), ("Esc", "Close"))
HINTS_CALC = (("\u23ce", "Copy result"), ("Ctrl+C", "Copy"), ("Esc", "Close"))
HINTS_SHELL = (("\u23ce", "Run in terminal"), ("Esc", "Close"))
HINTS_CLIPBOARD = (("\u23ce", "Paste"), ("\u2191\u2193", "Move"),
                   ("Alt+1\u20139", "Jump"), ("Ctrl+C", "Copy"), ("Esc", "Back"))


def _is_offscreen() -> bool:
    return os.environ.get("QT_QPA_PLATFORM") == "offscreen"


class _ActionSignal(QtCore.QObject):
    done = Signal(str, object)


class _ClipboardSignal(QtCore.QObject):
    added = Signal(int)


class Launcher(SearchControllerMixin, ModeViewsMixin, QtWidgets.QWidget):
    """Floating spotlight-style launcher overlay."""

    def __init__(self, cfg, store, embedder, clipboard_store=None):
        super().__init__()
        self.cfg = cfg
        self.store = store
        self.embedder = embedder
        self.searcher = Searcher(store, embedder)
        self.hits: list = []
        self.view = VIEW_SEARCH
        self._req_id = 0
        self._busy = False
        self._pending: str | None = None
        self._lock = threading.Lock()
        self._query_by_req: dict[int, str] = {}
        self._chunk_totals: dict[str, int] = {}

        self.router = ModeRouter()
        self.parsed = modes.parse("")
        self.mode = modes.MODE_SEARCH
        self.rows: list = []
        self.calc_result = None
        self.shell_plan = None
        self.copy_fn = clipboard_history.set_clipboard_text
        self.paste_fn = clipboard_history.paste_ctrl_v
        self.shell_runner = None
        self.paste_delay_ms = PASTE_DELAY_MS

        self.clipboard_store = clipboard_store
        if self.clipboard_store is None and bool(getattr(cfg, "clipboard_enabled", True)):
            self.clipboard_store = clipboard_history.from_config(cfg)
        self.clipboard_watcher = None
        self.clip_items: list = []
        self._clip_sig = _ClipboardSignal()
        self._clip_sig.added.connect(self._on_clipboard_added)

        self.action_ctx = actions.ActionContext(
            reindex=actions.make_reindexer(cfg, store, embedder))
        self._action_sig = _ActionSignal()
        self._action_sig.done.connect(self._on_action_done)

        width = int(getattr(cfg, "ui_width", 760) or 760)
        height = int(getattr(cfg, "ui_height", 480) or 480)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle("PLETHORA MJOLNIR")
        self.setFixedSize(width, height)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.panel = QtWidgets.QFrame()
        self.panel.setObjectName("panel")
        make_shadow(self.panel)
        outer.addWidget(self.panel)

        lay = QtWidgets.QVBoxLayout(self.panel)
        lay.setContentsMargins(14, 12, 14, 8)
        lay.setSpacing(8)

        self._build_search_row(lay)
        sep = QtWidgets.QFrame()
        sep.setObjectName("separator")
        sep.setFixedHeight(1)
        lay.addWidget(sep)
        self._build_body(lay)
        self._build_footer(lay)

        self.toast = QtWidgets.QLabel("Snippet copied!", self.panel)
        self.toast.setObjectName("pill")
        self.toast.hide()
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self.toast.hide)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(int(getattr(cfg, "debounce_ms", 120) or 120))
        self._search_timer.timeout.connect(self._dispatch_async_search)
        self._timer = self._search_timer
        self._thread = QtCore.QThread(self)
        self._worker = SearchWorker(self.searcher, self._lock)
        self._worker.moveToThread(self._thread)
        self._sig = _SearchSignal()
        self._sig.requested.connect(self._worker.do_search)
        self._worker.finished.connect(self._on_results)
        self._thread.start()
        self._current_query_id = 0

        self.search.textChanged.connect(self._schedule)
        self.search.installEventFilter(self)
        self.results.currentRowChanged.connect(self._on_row_changed)
        self.clipboard_list.currentRowChanged.connect(self._on_clipboard_row_changed)
        self.results.itemActivated.connect(lambda _i: self._activate_row())
        self.clipboard_list.itemActivated.connect(lambda _i: self._clipboard_enter())
        self.show_view(VIEW_SEARCH)
        self._refresh_stats()

    def _dispatch_async_search(self):
        self._fire_query()

    def _build_search_row(self, lay):
        h = QtWidgets.QHBoxLayout()
        h.setContentsMargins(2, 2, 2, 2)
        h.setSpacing(10)
        self.logo_label = QtWidgets.QLabel()
        self.logo_label.setObjectName("appIcon")
        self.logo_label.setFixedSize(24, 24)

        base_dir = getattr(sys, '_MEIPASS', os.path.abspath("."))
        icon_path = os.path.join(base_dir, "assets", "mjolnir.png")
        if not os.path.exists(icon_path):
            icon_path = os.path.join(base_dir, "assets", "mjolnir.ico")

        if os.path.exists(icon_path):
            pix = QtGui.QPixmap(icon_path)
            if not pix.isNull():
                self.logo_label.setPixmap(pix.scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.logo_label.setPixmap(app_icon(getattr(self.cfg, "theme", None)).pixmap(24, 24))

        h.addWidget(self.logo_label, 0, Qt.AlignVCenter)
        self.search = QtWidgets.QLineEdit()
        self.search.setObjectName("search")
        self.search.setPlaceholderText("Search documents, code, notes by meaning...")
        h.addWidget(self.search, 1)
        self.spinner = QtWidgets.QLabel("…")
        self.spinner.setObjectName("spinner")
        self.spinner.hide()
        h.addWidget(self.spinner, 0, Qt.AlignVCenter)
        lay.addLayout(h)

    def _build_body(self, lay):
        self.stack = QtWidgets.QStackedWidget()
        self.stack.setObjectName("bodyStack")
        self.stack.addWidget(self._build_search_page())
        self.action_panel = ActionPanel(parent=self)
        self.action_panel.activated.connect(self._on_action_requested)
        self.action_panel.back.connect(self.close_action_panel)
        self.stack.addWidget(self.action_panel)
        self.stack.addWidget(self._build_clipboard_page())
        lay.addWidget(self.stack, 1)

    def _build_search_page(self) -> QtWidgets.QWidget:
        body = QtWidgets.QWidget()
        body.setObjectName("searchResultsPage")
        h = QtWidgets.QHBoxLayout(body)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(12)
        self.results = QtWidgets.QListWidget()
        self.results.setObjectName("results")
        self.results.setFocusPolicy(Qt.NoFocus)
        self.results.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        h.addWidget(self.results, 55)

        self.insp_frame = QtWidgets.QFrame()
        self.insp_frame.setObjectName("inspector")
        v = QtWidgets.QVBoxLayout(self.insp_frame)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(6)
        self.insp_title = QtWidgets.QLabel("No selection")
        self.insp_title.setObjectName("resultName")
        self.insp_title.setWordWrap(True)
        v.addWidget(self.insp_title)
        self.insp_sub = QtWidgets.QLabel("")
        self.insp_sub.setObjectName("resultPath")
        self.insp_sub.setWordWrap(True)
        v.addWidget(self.insp_sub)
        self.preview = QtWidgets.QTextBrowser()
        self.preview.setObjectName("preview")
        self.preview.setOpenExternalLinks(False)
        v.addWidget(self.preview, 1)

        self.insp_caps = QtWidgets.QHBoxLayout()
        self.insp_caps.setContentsMargins(0, 0, 0, 0)
        self.insp_caps.setSpacing(0)
        v.addLayout(self.insp_caps)
        self.insp_caps_widget: "QtWidgets.QWidget | None" = None
        self._render_capsules(None, None, None, None)
        h.addWidget(self.insp_frame, 45)
        return body

    def _build_clipboard_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        self.clipboard_page = page
        page.setObjectName("clipboardPanel")
        page.setAttribute(Qt.WA_StyledBackground, True)
        v = QtWidgets.QVBoxLayout(page)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(4)
        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        title = QtWidgets.QLabel("Clipboard History")
        title.setObjectName("actionFileName")
        header.addWidget(title, 0, Qt.AlignVCenter)
        self.clip_count = QtWidgets.QLabel("")
        self.clip_count.setObjectName("actionHint")
        header.addWidget(self.clip_count, 1, Qt.AlignVCenter)
        v.addLayout(header)
        self.clip_note = QtWidgets.QLabel("")
        self.clip_note.setObjectName("emptyState2")
        self.clip_note.setWordWrap(True)
        v.addWidget(self.clip_note)
        self.clipboard_list = QtWidgets.QListWidget()
        self.clipboard_list.setObjectName("results")
        self.clipboard_list.setFocusPolicy(Qt.NoFocus)
        self.clipboard_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        v.addWidget(self.clipboard_list, 1)
        return page

    def _build_footer(self, lay):
        bar = QtWidgets.QWidget()
        bar.setObjectName("footer")
        h = QtWidgets.QHBoxLayout(bar)
        h.setContentsMargins(2, 4, 2, 0)
        h.setSpacing(8)
        self.status = QtWidgets.QLabel("")
        self.status.setObjectName("status")
        h.addWidget(self.status, 1)
        self.hints_host = QtWidgets.QWidget()
        self.hints_host.setObjectName("keycaps")
        self.hints_layout = QtWidgets.QHBoxLayout(self.hints_host)
        self.hints_layout.setContentsMargins(0, 0, 0, 0)
        self.hints_layout.setSpacing(0)
        self._hints_widget = None
        h.addWidget(self.hints_host, 0, Qt.AlignVCenter)
        lay.addWidget(bar)

    def show_view(self, index: int) -> int:
        index = int(index)
        if not (0 <= index < self.stack.count()):
            index = VIEW_SEARCH
        self.view = index
        self.stack.setCurrentIndex(index)
        if index == VIEW_ACTIONS:
            self.action_panel.set_target(self._selected_target())
            self.action_panel.set_focus_cursor()
        self._apply_hints()
        return index

    def _apply_hints(self):
        try:
            strip = keycaps(list(self._hints_for_view()))
        except Exception:
            return
        previous = getattr(self, "_hints_widget", None)
        if previous is not None:
            self.hints_layout.removeWidget(previous)
            previous.setParent(None)
            previous.deleteLater()
        self._hints_widget = strip
        self.hints_layout.addWidget(strip, 0, Qt.AlignVCenter)

    def _hints_for_view(self):
        if self.view == VIEW_CLIPBOARD:
            return HINTS_CLIPBOARD
        return {
            modes.MODE_OPEN: HINTS_OPEN,
            modes.MODE_CALC: HINTS_CALC,
            modes.MODE_SHELL: HINTS_SHELL,
        }.get(self.mode, HINTS_SEARCH)

    def target_screen(self):
        screen = None
        try:
            screen = QtGui.QGuiApplication.screenAt(QtGui.QCursor.pos())
        except Exception:
            screen = None
        if screen is None:
            try:
                screen = QtGui.QGuiApplication.primaryScreen()
            except Exception:
                screen = None
        return screen

    def show_centered(self):
        screen = self.target_screen()
        geom = screen.availableGeometry() if screen else QtCore.QRect(0, 0, 1280, 800)
        x = geom.center().x() - self.width() // 2
        y = geom.top() + int(geom.height() * 0.18)
        self.move(max(geom.left(), x), max(geom.top(), y))
        if self.view != VIEW_SEARCH:
            self.show_view(VIEW_SEARCH)
        self.show()
        self.raise_()
        self.activateWindow()
        self.search.setFocus()
        self.search.selectAll()

    def toggle(self):
        if self.isVisible() and self.isActiveWindow():
            self.hide()
        else:
            self.show_centered()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QtCore.QEvent.WindowDeactivate and not self.isActiveWindow():
            if not _is_offscreen() and not QtWidgets.QApplication.activePopupWidget():
                self.hide()

    def closeEvent(self, event):
        try:
            self._thread.quit()
            self._thread.wait(1500)
        except Exception:
            pass
        self.stop_clipboard_watcher()
        super().closeEvent(event)

    def route_hotkey(self, hotkey_id: int) -> bool:
        if int(hotkey_id) == HOTKEY_CLIPBOARD:
            return self.open_clipboard_history()
        self.toggle()
        return True

    def _toast(self, text):
        self.toast.setText(text)
        self.toast.adjustSize()
        x = (self.panel.width() - self.toast.width()) // 2
        self.toast.move(max(8, x), self.panel.height() - 44)
        self.toast.show()
        self.toast.raise_()
        self._toast_timer.start(1400)

    def eventFilter(self, obj, event):
        if obj is self.search and event.type() == QtCore.QEvent.KeyPress:
            return self._handle_key(event) or super().eventFilter(obj, event)
        return super().eventFilter(obj, event)

    def _handle_key(self, event) -> bool:
        key = event.key()
        mods = event.modifiers()
        in_panel = self.view == VIEW_ACTIONS
        in_clipboard = self.view == VIEW_CLIPBOARD

        if key == Qt.Key_Escape:
            if self.mode == modes.MODE_SHELL and self.router.cancel_shell_confirmation():
                self._set_inspector_warning_border(False)
                plan = self.shell_plan
                if plan and plan.ok:
                    from .inspector_pane import command_html
                    self.preview.setHtml(command_html(plan.display, plan.target, plan.cwd))
                    self.status.setText(f"Nothing runs until you press Enter  ·  {plan.target}")
                return True
            if in_panel:
                if not self.action_panel.escape():
                    self.close_action_panel()
                return True
            if in_clipboard:
                self.close_clipboard_mode()
                return True
            self.hide()
            return True

        if key == Qt.Key_Left:
            if in_panel:
                if not self.action_panel.escape():
                    self.close_action_panel()
                return True
            return False

        if key in (Qt.Key_Return, Qt.Key_Enter):
            if in_panel:
                self.action_panel.enter()
                return True
            ctrl_pressed = bool(mods & Qt.ControlModifier)
            shift_pressed = bool(mods & Qt.ShiftModifier)
            return bool(self._activate_row(shift=shift_pressed, ctrl=ctrl_pressed))

        if key == Qt.Key_Tab:
            if in_clipboard:
                return False
            self.open_action_panel()
            return True

        if key == Qt.Key_Right and not in_panel:
            if in_clipboard:
                return False
            if self.search.cursorPosition() >= len(self.search.text()):
                self.open_action_panel()
                return True
            return False

        if Qt.Key_1 <= key <= Qt.Key_9:
            if in_panel:
                self.action_panel.digit(str(key - Qt.Key_0))
                return True
            if mods & Qt.AltModifier:
                self._quick_jump(key - Qt.Key_0)
                return True

        if key in (Qt.Key_Down, Qt.Key_Up):
            delta = 1 if key == Qt.Key_Down else -1
            if in_panel:
                self.action_panel.move_cursor(delta)
                return True
            target = self.clipboard_list if in_clipboard else self.results
            row = target.currentRow() + delta
            row = max(0, min(row, target.count() - 1))
            target.setCurrentRow(row)
            return True

        if key == Qt.Key_C and mods & Qt.ControlModifier:
            if in_clipboard:
                return bool(self._copy_clip_item())
            if self.mode == modes.MODE_CALC:
                return bool(self._copy_calc())
            self._copy_snippet()
            return True

        if key == Qt.Key_R and mods & Qt.ControlModifier:
            self.reindex()
            return True

        return False


def run_gui(cfg, store, embedder, log=print, tray_only: bool = False) -> int:
    """Launch the floating GUI overlay."""
    app = QtWidgets.QApplication.instance()
    if app is None:
        if hasattr(Qt, "HighDpiScaleFactorRoundingPolicy"):
            try:
                QtWidgets.QApplication.setHighDpiScaleFactorRoundingPolicy(
                    Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
            except Exception:
                pass
        app = QtWidgets.QApplication(sys.argv)

    app.setStyleSheet(styles.PANEL_QSS)
    icon = app_icon(getattr(cfg, "theme", None))
    app.setWindowIcon(icon)

    win = Launcher(cfg, store, embedder)

    tray = QtWidgets.QSystemTrayIcon(icon, app)
    tray.setToolTip("PLETHORA MJOLNIR")
    tray_menu = QtWidgets.QMenu()
    tray_menu.addAction("Open MJOLNIR", win.toggle)
    tray_menu.addAction("Clipboard History", win.open_clipboard_history)
    tray_menu.addSeparator()
    tray_menu.addAction("Re-index All", win.reindex)
    tray_menu.addSeparator()
    tray_menu.addAction("Quit", app.quit)
    tray.setContextMenu(tray_menu)
    tray.activated.connect(lambda _r: win.toggle())
    try:
        tray.show()
    except Exception:
        pass

    try:
        win.start_clipboard_watcher()
    except Exception:
        pass

    hotkeys = HotkeyThread()
    hotkeys.warning.connect(lambda msg: win.status.setText(msg))
    try:
        hotkeys.fired.connect(win.route_hotkey)
        hotkeys.start()
    except Exception:
        pass

    log("[mjolnir] launcher ready. Alt+Space toggles it, Alt+Shift+C opens clipboard history; tray icon for menu.")

    selftest = os.environ.get("MJOLNIR_UI_SELFTEST")
    if selftest:
        win.show_centered()
        win.search.setText(selftest)
        QTimer.singleShot(1500, win._selftest_view)
        QTimer.singleShot(2400, win._selftest_modes)
        QTimer.singleShot(6000, app.quit)
    elif not tray_only:
        win.show_centered()

    try:
        app.exec()
    finally:
        try:
            hotkeys.stop()
        except Exception:
            pass
        try:
            win.stop_clipboard_watcher()
        except Exception:
            pass
        try:
            win._thread.quit()
            win._thread.wait(1500)
        except Exception:
            pass

    if selftest:
        print(f"[selftest] results for {selftest!r}: {len(win.hits)}")
    return 0
