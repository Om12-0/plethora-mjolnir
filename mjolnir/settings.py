"""
mjolnir/settings.py - Alfred-Style Configuration & Theme Engine.
"""

import json
import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLabel, QCheckBox, QSlider, QComboBox, QLineEdit, QPushButton,
    QFileDialog, QListWidget, QGroupBox, QSpinBox
)
from PySide6.QtCore import Qt, Signal

SETTINGS_PATH = os.path.expandvars(r"%APPDATA%\Plethora\mjolnir\settings.json")

THEMES = {
    "Plethora Obsidian": {
        "bg": "#0c0d12",
        "card": "#141721",
        "accent": "#7c3aed",
        "text": "#f3f4f6",
        "subtext": "#9ca3af",
        "border": "#272a38"
    },
    "Alfred Classic Charcoal": {
        "bg": "#1e1e1e",
        "card": "#2d2d2d",
        "accent": "#d97706",
        "text": "#ffffff",
        "subtext": "#888888",
        "border": "#3c3c3c"
    },
    "Cyberpunk Midnight": {
        "bg": "#08090d",
        "card": "#10131d",
        "accent": "#06b6d4",
        "text": "#e0f2fe",
        "subtext": "#64748b",
        "border": "#1e293b"
    }
}

DEFAULT_SETTINGS = {
    "hotkey": "Alt+Space",
    "hide_on_blur": True,
    "theme": "Plethora Obsidian",
    "opacity": 96,
    "max_results": 9,
    "search_paths": [
        os.path.expanduser(r"~\Documents"),
        os.path.expanduser(r"~\Desktop"),
        os.path.expanduser(r"~\Downloads")
    ]
}

def load_settings() -> dict:
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r") as f:
                return {**DEFAULT_SETTINGS, **json.load(f)}
        except Exception:
            pass
    return DEFAULT_SETTINGS.copy()

def save_settings(cfg: dict):
    os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
    with open(SETTINGS_PATH, "w") as f:
        json.dump(cfg, f, indent=2)

class PreferencesDialog(QDialog):
    theme_updated = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Plethora Mjolnir Preferences")
        self.resize(560, 440)
        self.cfg = load_settings()
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        tabs = QTabWidget()

        # Tab 1: General
        t1 = QWidget()
        l1 = QVBoxLayout(t1)
        hb = QGroupBox("Keyboard Shortcut")
        hbl = QHBoxLayout(hb)
        hbl.addWidget(QLabel("Global Invocation:"))
        self.hk = QLineEdit(self.cfg["hotkey"])
        hbl.addWidget(self.hk)
        l1.addWidget(hb)

        self.cb_blur = QCheckBox("Dismiss window when focus is lost")
        self.cb_blur.setChecked(self.cfg["hide_on_blur"])
        l1.addWidget(self.cb_blur)
        l1.addStretch()
        tabs.addTab(t1, "General")

        # Tab 2: Appearance (Alfred Theming)
        t2 = QWidget()
        l2 = QVBoxLayout(t2)
        l2.addWidget(QLabel("Color Theme:"))
        self.theme_sel = QComboBox()
        self.theme_sel.addItems(list(THEMES.keys()))
        self.theme_sel.setCurrentText(self.cfg["theme"])
        l2.addWidget(self.theme_sel)

        l2.addWidget(QLabel("Window Opacity (%):"))
        self.op_slider = QSlider(Qt.Horizontal)
        self.op_slider.setRange(70, 100)
        self.op_slider.setValue(self.cfg["opacity"])
        l2.addWidget(self.op_slider)

        l2.addWidget(QLabel("Visible Results Limit:"))
        self.max_res = QSpinBox()
        self.max_res.setRange(5, 15)
        self.max_res.setValue(self.cfg["max_results"])
        l2.addWidget(self.max_res)
        l2.addStretch()
        tabs.addTab(t2, "Appearance")

        # Tab 3: Search Paths
        t3 = QWidget()
        l3 = QVBoxLayout(t3)
        self.path_list = QListWidget()
        for p in self.cfg["search_paths"]:
            self.path_list.addItem(p)
        l3.addWidget(self.path_list)

        btn_row = QHBoxLayout()
        add_b = QPushButton("Add Folder...")
        add_b.clicked.connect(self._add_path)
        rem_b = QPushButton("Remove")
        rem_b.clicked.connect(self._rem_path)
        btn_row.addWidget(add_b)
        btn_row.addWidget(rem_b)
        l3.addLayout(btn_row)
        tabs.addTab(t3, "Search Scope")

        layout.addWidget(tabs)

        bot = QHBoxLayout()
        save_btn = QPushButton("Save & Apply")
        save_btn.clicked.connect(self._save)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        bot.addStretch()
        bot.addWidget(cancel_btn)
        bot.addWidget(save_btn)
        layout.addLayout(bot)

    def _add_path(self):
        f = QFileDialog.getExistingDirectory(self, "Add Search Folder")
        if f:
            self.path_list.addItem(f)

    def _rem_path(self):
        for item in self.path_list.selectedItems():
            self.path_list.takeItem(self.path_list.row(item))

    def _save(self):
        self.cfg["hotkey"] = self.hk.text()
        self.cfg["hide_on_blur"] = self.cb_blur.isChecked()
        self.cfg["theme"] = self.theme_sel.currentText()
        self.cfg["opacity"] = self.op_slider.value()
        self.cfg["max_results"] = self.max_res.value()
        self.cfg["search_paths"] = [self.path_list.item(i).text() for i in range(self.path_list.count())]
        save_settings(self.cfg)
        self.theme_updated.emit()
        self.accept()
