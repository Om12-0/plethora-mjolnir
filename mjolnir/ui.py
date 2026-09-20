"""
mjolnir/ui.py - The Alfred Spotlight Launcher Interface for Windows.
"""

import os
import sys
import subprocess
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QListWidget,
    QListWidgetItem, QLabel, QFrame, QSystemTrayIcon, QMenu, QStyle, QApplication
)
from PySide6.QtCore import Qt, QTimer, QThread, Signal
from PySide6.QtGui import QIcon, QKeyEvent, QGuiApplication, QClipboard

from mjolnir.engine import SearchEngine
from mjolnir.settings import load_settings, THEMES, PreferencesDialog

class AsyncWorker(QThread):
    results_ready = Signal(int, list)

    def __init__(self, qid: int, query: str):
        super().__init__()
        self.qid = qid
        self.query = query

    def run(self):
        res = SearchEngine.instance().query(self.query)
        self.results_ready.emit(self.qid, res)

class MjolnirWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.cfg = load_settings()
        self.query_id = 0
        self.worker = None

        self._setup_window_flags()
        self._build_interface()
        self._setup_tray()
        self.apply_theme()

        # 40ms debounce timer for keystroke responsiveness
        self.debounce = QTimer()
        self.debounce.setSingleShot(True)
        self.debounce.timeout.connect(self._dispatch_search)

    def _setup_window_flags(self):
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(750, 460)

    def _build_interface(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        # Outer Container Card
        self.card = QFrame()
        self.card.setObjectName("card")
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(10)

        # 1. Search Bar Top Row
        top_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setObjectName("searchInput")
        self.search_input.setPlaceholderText("Search apps, documents, or paths...")
        self.search_input.textChanged.connect(self._on_text_changed)
        top_row.addWidget(self.search_input)

        # Settings Gear Icon
        self.gear_btn = QLabel("⚙")
        self.gear_btn.setObjectName("gearBtn")
        self.gear_btn.setCursor(Qt.PointingHandCursor)
        self.gear_btn.mousePressEvent = lambda _: self.open_preferences()
        top_row.addWidget(self.gear_btn)
        card_layout.addLayout(top_row)

        # 2. Main Content Split View (List + Preview)
        content_row = QHBoxLayout()
        self.results_list = QListWidget()
        self.results_list.setObjectName("resultsList")
        self.results_list.currentRowChanged.connect(self._on_row_changed)
        self.results_list.itemDoubleClicked.connect(self._execute_primary)
        content_row.addWidget(self.results_list, stretch=6)

        # Alfred Preview Inspector
        self.preview_box = QFrame()
        self.preview_box.setObjectName("previewBox")
        pb_layout = QVBoxLayout(self.preview_box)
        pb_layout.setContentsMargins(12, 12, 12, 12)

        self.preview_title = QLabel("No selection")
        self.preview_title.setObjectName("previewTitle")
        self.preview_title.setWordWrap(True)
        pb_layout.addWidget(self.preview_title)

        self.preview_meta = QLabel("")
        self.preview_meta.setObjectName("previewMeta")
        self.preview_meta.setWordWrap(True)
        pb_layout.addWidget(self.preview_meta)
        pb_layout.addStretch()

        content_row.addWidget(self.preview_box, stretch=4)
        card_layout.addLayout(content_row)

        # 3. Alfred Action Bar (Footer)
        self.footer = QFrame()
        self.footer.setObjectName("footer")
        ft_layout = QHBoxLayout(self.footer)
        ft_layout.setContentsMargins(8, 4, 8, 4)

        self.status_lbl = QLabel("Ready")
        self.status_lbl.setObjectName("footerLabel")
        ft_layout.addWidget(self.status_lbl)
        ft_layout.addStretch()

        actions = QLabel("↵ Open   Alt+↵ Reveal   Ctrl+C Copy   Ctrl+T Terminal   Esc Close")
        actions.setObjectName("footerActions")
        ft_layout.addWidget(actions)
        card_layout.addWidget(self.footer)

        self.main_layout.addWidget(self.card)

    def apply_theme(self):
        self.cfg = load_settings()
        theme = THEMES.get(self.cfg.get("theme"), THEMES["Plethora Obsidian"])
        op = self.cfg.get("opacity", 96) / 100.0
        self.setWindowOpacity(op)

        style = f"""
            #card {{
                background-color: {theme['bg']};
                border: 1px solid {theme['border']};
                border-radius: 12px;
            }}
            #searchInput {{
                background-color: {theme['card']};
                color: {theme['text']};
                border: 1px solid {theme['border']};
                border-radius: 8px;
                padding: 10px 14px;
                font-size: 16px;
            }}
            #searchInput:focus {{
                border: 1px solid {theme['accent']};
            }}
            #gearBtn {{
                font-size: 18px;
                color: {theme['subtext']};
                padding: 4px;
            }}
            #gearBtn:hover {{
                color: {theme['accent']};
            }}
            #resultsList {{
                background-color: {theme['bg']};
                border: none;
                color: {theme['text']};
                font-size: 14px;
            }}
            #resultsList::item {{
                padding: 8px 10px;
                border-radius: 6px;
                margin-bottom: 2px;
            }}
            #resultsList::item:selected {{
                background-color: {theme['accent']};
                color: #ffffff;
            }}
            #previewBox {{
                background-color: {theme['card']};
                border: 1px solid {theme['border']};
                border-radius: 8px;
            }}
            #previewTitle {{
                font-size: 15px;
                font-weight: bold;
                color: {theme['text']};
            }}
            #previewMeta {{
                font-size: 12px;
                color: {theme['subtext']};
            }}
            #footer {{
                background-color: {theme['card']};
                border-radius: 6px;
            }}
            #footerLabel, #footerActions {{
                font-size: 11px;
                color: {theme['subtext']};
            }}
        """
        self.setStyleSheet(style)

    def show_centered(self):
        screen = QGuiApplication.primaryScreen().availableGeometry()
        x = screen.x() + (screen.width() - self.width()) // 2
        y = screen.y() + (screen.height() - self.height()) // 3  # Alfred upper-third
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
        self.search_input.setFocus()
        self.search_input.selectAll()

    def _setup_tray(self):
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(self.style().standardIcon(QStyle.SP_ComputerIcon))
        menu = QMenu()
        menu.addAction("Show Mjolnir (Alt+Space)", self.show_centered)
        menu.addAction("Preferences...", self.open_preferences)
        menu.addSeparator()
        menu.addAction("Quit", QApplication.instance().quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda r: self.show_centered() if r == QSystemTrayIcon.Trigger else None)
        self.tray.show()

    def _on_text_changed(self, text: str):
        if not text.strip():
            self.results_list.clear()
            self.preview_title.setText("No selection")
            self.preview_meta.setText("")
            self.status_lbl.setText("Ready")
            return
        self.debounce.start(40)

    def _dispatch_search(self):
        self.query_id += 1
        query = self.search_input.text()
        self.worker = AsyncWorker(self.query_id, query)
        self.worker.results_ready.connect(self._on_results)
        self.worker.start()

    def _on_results(self, qid: int, results: list):
        if qid != self.query_id:
            return  # Drop out-of-order responses

        self.results_list.clear()
        for r in results:
            item = QListWidgetItem(f"[{r['category']}]  {r['title']}")
            item.setData(Qt.UserRole, r)
            self.results_list.addItem(item)

        if results:
            self.results_list.setCurrentRow(0)
            self.status_lbl.setText(f"{len(results)} matches")
        else:
            self.preview_title.setText("No results found")
            self.preview_meta.setText("")
            self.status_lbl.setText("0 matches")

    def _on_row_changed(self, row: int):
        if row < 0 or row >= self.results_list.count():
            return
        item = self.results_list.item(row)
        data = item.data(Qt.UserRole)
        self.preview_title.setText(data.get("title", ""))
        self.preview_meta.setText(f"Path: {data.get('path', '')}\nCategory: {data.get('category', '')}")

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        modifiers = event.modifiers()

        # ESC: Close launcher
        if key == Qt.Key_Escape:
            self.hide()
            return

        # Up / Down: Navigate list
        if key == Qt.Key_Down:
            curr = self.results_list.currentRow()
            if curr < self.results_list.count() - 1:
                self.results_list.setCurrentRow(curr + 1)
            return
        elif key == Qt.Key_Up:
            curr = self.results_list.currentRow()
            if curr > 0:
                self.results_list.setCurrentRow(curr - 1)
            return

        # Enter: Open / Launch
        if key in (Qt.Key_Return, Qt.Key_Enter):
            if modifiers & Qt.AltModifier or modifiers & Qt.ControlModifier:
                self._execute_reveal()
            else:
                self._execute_primary()
            return

        # Ctrl+C: Copy Path
        if modifiers & Qt.ControlModifier and key == Qt.Key_C:
            self._execute_copy()
            return

        # Ctrl+T: Open in Terminal
        if modifiers & Qt.ControlModifier and key == Qt.Key_T:
            self._execute_terminal()
            return

        # Ctrl+, : Open Preferences
        if modifiers & Qt.ControlModifier and key == Qt.Key_Comma:
            self.open_preferences()
            return

        # Alt+1 to Alt+9: Quick Select
        if modifiers & Qt.AltModifier and Qt.Key_1 <= key <= Qt.Key_9:
            idx = key - Qt.Key_1
            if idx < self.results_list.count():
                self.results_list.setCurrentRow(idx)
                self._execute_primary()
            return

        super().keyPressEvent(event)

    def _execute_primary(self):
        curr = self.results_list.currentItem()
        if not curr:
            return
        path = curr.data(Qt.UserRole).get("path")
        if path and os.path.exists(path):
            os.startfile(path)
            self.hide()

    def _execute_reveal(self):
        curr = self.results_list.currentItem()
        if not curr:
            return
        path = curr.data(Qt.UserRole).get("path")
        if path and os.path.exists(path):
            subprocess.Popen(f'explorer /select,"{os.path.normpath(path)}"')
            self.hide()

    def _execute_copy(self):
        curr = self.results_list.currentItem()
        if not curr:
            return
        path = curr.data(Qt.UserRole).get("path")
        if path:
            QApplication.clipboard().setText(path)
            self.status_lbl.setText("Copied path to clipboard!")

    def _execute_terminal(self):
        curr = self.results_list.currentItem()
        if not curr:
            return
        path = curr.data(Qt.UserRole).get("path")
        target_dir = path if os.path.isdir(path) else os.path.dirname(path)
        if os.path.exists(target_dir):
            subprocess.Popen(["wt.exe", "-d", target_dir], shell=True)
            self.hide()

    def changeEvent(self, event):
        if event.type() == event.Type.ActivationChange:
            if not self.isActiveWindow() and self.cfg.get("hide_on_blur", True):
                self.hide()
        super().changeEvent(event)

    def open_preferences(self):
        dlg = PreferencesDialog(self)
        dlg.theme_updated.connect(self.apply_theme)
        dlg.exec()
