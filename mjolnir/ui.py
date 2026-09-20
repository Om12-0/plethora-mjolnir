"""
mjolnir/ui.py - Alfred 5 Spotlight Interface with Instant Response & Action Bar.
"""

import os
import sys
import subprocess
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QListWidget,
    QListWidgetItem, QLabel, QFrame, QSystemTrayIcon, QMenu, QStyle, QApplication
)
from PySide6.QtCore import Qt, QTimer, QThread, Signal
from PySide6.QtGui import QKeyEvent, QGuiApplication

from mjolnir.engine import SearchEngine
from mjolnir.settings import load_settings, THEMES, PreferencesDialog

class AsyncSearchWorker(QThread):
    results_ready = Signal(int, list)

    def __init__(self, qid: int, query: str, limit: int = 9):
        super().__init__()
        self.qid = qid
        self.query = query
        self.limit = limit

    def run(self):
        try:
            results = SearchEngine.instance().query(self.query, limit=self.limit)
        except Exception:
            results = []
        self.results_ready.emit(self.qid, results)

class MjolnirWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.cfg = load_settings()
        self.query_id = 0
        self.worker = None

        self._init_window()
        self._build_ui()
        self._setup_tray()
        self.apply_theme()

        self.debounce = QTimer()
        self.debounce.setSingleShot(True)
        self.debounce.timeout.connect(self._run_search)

    def _init_window(self):
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(760, 460)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.card = QFrame()
        self.card.setObjectName("mainCard")
        cl = QVBoxLayout(self.card)
        cl.setContentsMargins(14, 14, 14, 14)
        cl.setSpacing(10)

        # Header Search Row
        top_row = QHBoxLayout()
        self.search_bar = QLineEdit()
        self.search_bar.setObjectName("searchBar")
        self.search_bar.setPlaceholderText("Search apps, documents, games, or paths...")
        self.search_bar.textChanged.connect(self._on_text_changed)
        top_row.addWidget(self.search_bar)

        self.gear_btn = QLabel("⚙")
        self.gear_btn.setObjectName("gearBtn")
        self.gear_btn.setCursor(Qt.PointingHandCursor)
        self.gear_btn.mousePressEvent = lambda _: self.open_settings()
        top_row.addWidget(self.gear_btn)
        cl.addLayout(top_row)

        # Split Content (Results List + Preview)
        content_row = QHBoxLayout()
        self.result_list = QListWidget()
        self.result_list.setObjectName("resultList")
        self.result_list.currentRowChanged.connect(self._on_row_changed)
        self.result_list.itemDoubleClicked.connect(self._action_open)
        content_row.addWidget(self.result_list, stretch=6)

        self.preview = QFrame()
        self.preview.setObjectName("previewBox")
        pl = QVBoxLayout(self.preview)
        pl.setContentsMargins(12, 12, 12, 12)

        self.prev_title = QLabel("No selection")
        self.prev_title.setObjectName("prevTitle")
        self.prev_title.setWordWrap(True)
        pl.addWidget(self.prev_title)

        self.prev_meta = QLabel("")
        self.prev_meta.setObjectName("prevMeta")
        self.prev_meta.setWordWrap(True)
        pl.addWidget(self.prev_meta)
        pl.addStretch()
        content_row.addWidget(self.preview, stretch=4)
        cl.addLayout(content_row)

        # Action Footer
        self.footer = QFrame()
        self.footer.setObjectName("footerBar")
        fl = QHBoxLayout(self.footer)
        fl.setContentsMargins(8, 4, 8, 4)

        self.status_lbl = QLabel("Ready")
        self.status_lbl.setObjectName("footerText")
        fl.addWidget(self.status_lbl)
        fl.addStretch()

        actions = QLabel("↵ Open   Alt+↵ Reveal   Ctrl+C Copy   Ctrl+T Terminal   Esc Close")
        actions.setObjectName("footerActions")
        fl.addWidget(actions)
        cl.addWidget(self.footer)

        layout.addWidget(self.card)

    def apply_theme(self):
        self.cfg = load_settings()
        t = THEMES.get(self.cfg.get("theme"), THEMES["Plethora Obsidian"])
        op = self.cfg.get("opacity", 96) / 100.0
        self.setWindowOpacity(op)

        self.setStyleSheet(f"""
            #mainCard {{
                background-color: {t['bg']};
                border: 1px solid {t['border']};
                border-radius: 12px;
            }}
            #searchBar {{
                background-color: {t['card']};
                color: {t['text']};
                border: 1px solid {t['border']};
                border-radius: 8px;
                padding: 10px 14px;
                font-size: 16px;
            }}
            #searchBar:focus {{
                border: 1px solid {t['accent']};
            }}
            #gearBtn {{
                font-size: 18px;
                color: {t['subtext']};
                padding: 4px;
            }}
            #gearBtn:hover {{
                color: {t['accent']};
            }}
            #resultList {{
                background-color: {t['bg']};
                border: none;
                color: {t['text']};
                font-size: 14px;
            }}
            #resultList::item {{
                padding: 8px 10px;
                border-radius: 6px;
                margin-bottom: 2px;
            }}
            #resultList::item:selected {{
                background-color: {t['accent']};
                color: #ffffff;
            }}
            #previewBox {{
                background-color: {t['card']};
                border: 1px solid {t['border']};
                border-radius: 8px;
            }}
            #prevTitle {{
                font-size: 15px;
                font-weight: bold;
                color: {t['text']};
            }}
            #prevMeta {{
                font-size: 12px;
                color: {t['subtext']};
            }}
            #footerBar {{
                background-color: {t['card']};
                border-radius: 6px;
            }}
            #footerText, #footerActions {{
                font-size: 11px;
                color: {t['subtext']};
            }}
        """)

    def show_centered(self):
        screen = QGuiApplication.primaryScreen().availableGeometry()
        x = screen.x() + (screen.width() - self.width()) // 2
        y = screen.y() + (screen.height() - self.height()) // 3
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
        self.search_bar.setFocus()
        self.search_bar.selectAll()

    def _setup_tray(self):
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(self.style().standardIcon(QStyle.SP_ComputerIcon))
        menu = QMenu()
        menu.addAction("Show Mjolnir (Alt+Space)", self.show_centered)
        menu.addAction("Preferences...", self.open_settings)
        menu.addSeparator()
        menu.addAction("Quit", QApplication.instance().quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda r: self.show_centered() if r == QSystemTrayIcon.Trigger else None)
        self.tray.show()

    def _on_text_changed(self, text: str):
        if not text.strip():
            self.result_list.clear()
            self.prev_title.setText("No selection")
            self.prev_meta.setText("")
            self.status_lbl.setText("Ready")
            return
        self.debounce.start(30)

    def _run_search(self):
        self.query_id += 1
        query = self.search_bar.text()
        limit = self.cfg.get("max_results", 9)
        # Clean up previous worker to avoid zombie threads
        try:
            if self.worker is not None and self.worker.isRunning():
                pass  # let it finish; results are discarded via query_id check
        except Exception:
            pass
        self.worker = AsyncSearchWorker(self.query_id, query, limit=limit)
        self.worker.results_ready.connect(self._populate_results)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()

    def _populate_results(self, qid: int, results: list):
        if qid != self.query_id:
            return

        self.result_list.clear()
        for r in results:
            item = QListWidgetItem(f"[{r['category']}]  {r['title']}")
            item.setData(Qt.UserRole, r)
            self.result_list.addItem(item)

        if results:
            self.result_list.setCurrentRow(0)
            self.status_lbl.setText(f"{len(results)} matches found")
        else:
            self.prev_title.setText("No results found")
            self.prev_meta.setText("")
            self.status_lbl.setText("0 matches")

    def _on_row_changed(self, row: int):
        if row < 0 or row >= self.result_list.count():
            return
        item = self.result_list.item(row)
        data = item.data(Qt.UserRole)
        self.prev_title.setText(data.get("title", ""))
        self.prev_meta.setText(f"Path: {data.get('path', '')}\nCategory: {data.get('category', '')}")

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        mods = event.modifiers()

        if key == Qt.Key_Escape:
            self.hide()
            return
        elif key == Qt.Key_Down:
            c = self.result_list.currentRow()
            if c < self.result_list.count() - 1:
                self.result_list.setCurrentRow(c + 1)
            return
        elif key == Qt.Key_Up:
            c = self.result_list.currentRow()
            if c > 0:
                self.result_list.setCurrentRow(c - 1)
            return
        elif key in (Qt.Key_Return, Qt.Key_Enter):
            if mods & (Qt.AltModifier | Qt.ControlModifier):
                self._action_reveal()
            else:
                self._action_open()
            return
        elif mods & Qt.ControlModifier and key == Qt.Key_C:
            self._action_copy()
            return
        elif mods & Qt.ControlModifier and key == Qt.Key_T:
            self._action_terminal()
            return
        elif mods & Qt.ControlModifier and key == Qt.Key_Comma:
            self.open_settings()
            return
        elif mods & Qt.AltModifier and Qt.Key_1 <= key <= Qt.Key_9:
            idx = key - Qt.Key_1
            if idx < self.result_list.count():
                self.result_list.setCurrentRow(idx)
                self._action_open()
            return

        super().keyPressEvent(event)

    def _action_open(self):
        curr = self.result_list.currentItem()
        if not curr:
            return
        path = curr.data(Qt.UserRole).get("path")
        if path:
            try:
                os.startfile(path)
                self.hide()
            except Exception as e:
                self.status_lbl.setText(f"Launch error: {e}")

    def _action_reveal(self):
        curr = self.result_list.currentItem()
        if not curr:
            return
        path = curr.data(Qt.UserRole).get("path")
        if path and os.path.exists(path):
            subprocess.Popen(f'explorer /select,"{os.path.normpath(path)}"')
            self.hide()

    def _action_copy(self):
        curr = self.result_list.currentItem()
        if not curr:
            return
        path = curr.data(Qt.UserRole).get("path")
        if path:
            QApplication.clipboard().setText(path)
            self.status_lbl.setText("Copied path to clipboard!")

    def _action_terminal(self):
        curr = self.result_list.currentItem()
        if not curr:
            return
        path = curr.data(Qt.UserRole).get("path")
        target = path if os.path.isdir(path) else os.path.dirname(path)
        if target and os.path.exists(target):
            try:
                subprocess.Popen(["wt.exe", "-d", target])
            except FileNotFoundError:
                subprocess.Popen(f'cmd.exe /K cd /d "{target}"', shell=True)
            self.hide()

    def changeEvent(self, event):
        if event.type() == event.Type.ActivationChange:
            if not self.isActiveWindow() and self.cfg.get("hide_on_blur", True):
                self.hide()
        super().changeEvent(event)

    def open_settings(self):
        dlg = PreferencesDialog(self)
        dlg.theme_changed.connect(self.apply_theme)
        dlg.exec()
