"""
mjolnir/settings.py - Alfred Preferences & Appearance Configuration.
"""

import json
import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLabel, QCheckBox, QSlider, QComboBox, QLineEdit, QPushButton,
    QFileDialog, QListWidget, QGroupBox, QSpinBox
)
from PySide6.QtCore import Qt, Signal

SETTINGS_FILE = os.path.expandvars(r"%APPDATA%\Plethora\mjolnir\settings.json")

THEMES = {
    "Plethora Obsidian": {
        "bg": "#0b0d13",
        "card": "#131722",
        "accent": "#7c3aed",
        "text": "#f9fafb",
        "subtext": "#9ca3af",
        "border": "#242938"
    },
    "Alfred Classic Charcoal": {
        "bg": "#1c1c1e",
        "card": "#2c2c2e",
        "accent": "#d97706",
        "text": "#ffffff",
        "subtext": "#8e8e93",
        "border": "#3a3a3c"
    },
    "Cyberpunk Neon": {
        "bg": "#090a0f",
        "card": "#0f1422",
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
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                return {**DEFAULT_SETTINGS, **json.load(f)}
        except Exception:
            pass
    return DEFAULT_SETTINGS.copy()

def save_settings(cfg: dict):
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    with open(SETTINGS_FILE, "w") as f:
        json.dump(cfg, f, indent=2)

class PreferencesDialog(QDialog):
    theme_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Plethora Mjolnir Preferences")
        self.resize(560, 420)
        self.cfg = load_settings()
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        tabs = QTabWidget()

        # Tab 1: General
        gen = QWidget()
        gl = QVBoxLayout(gen)
        hk_box = QGroupBox("Keyboard Shortcut")
        hkl = QHBoxLayout(hk_box)
        hkl.addWidget(QLabel("Global Invocation:"))
        self.hk_input = QLineEdit(self.cfg["hotkey"])
        hkl.addWidget(self.hk_input)
        gl.addWidget(hk_box)

        self.cb_blur = QCheckBox("Dismiss window on lost focus (click outside)")
        self.cb_blur.setChecked(self.cfg["hide_on_blur"])
        gl.addWidget(self.cb_blur)
        gl.addStretch()
        tabs.addTab(gen, "General")

        # Tab 2: Appearance
        app = QWidget()
        al = QVBoxLayout(app)
        al.addWidget(QLabel("Color Theme:"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(list(THEMES.keys()))
        self.theme_combo.setCurrentText(self.cfg["theme"])
        al.addWidget(self.theme_combo)

        al.addWidget(QLabel("Window Opacity (%):"))
        self.op_slider = QSlider(Qt.Horizontal)
        self.op_slider.setRange(70, 100)
        self.op_slider.setValue(self.cfg["opacity"])
        al.addWidget(self.op_slider)

        al.addWidget(QLabel("Max Results:"))
        self.res_spin = QSpinBox()
        self.res_spin.setRange(5, 15)
        self.res_spin.setValue(self.cfg["max_results"])
        al.addWidget(self.res_spin)
        al.addStretch()
        tabs.addTab(app, "Appearance")

        # Tab 3: Search Paths
        scope = QWidget()
        sl = QVBoxLayout(scope)
        self.path_list = QListWidget()
        for p in self.cfg["search_paths"]:
            self.path_list.addItem(p)
        sl.addWidget(self.path_list)

        btn_bar = QHBoxLayout()
        add_b = QPushButton("Add Folder...")
        add_b.clicked.connect(self._add_dir)
        rem_b = QPushButton("Remove")
        rem_b.clicked.connect(self._rem_dir)
        btn_bar.addWidget(add_b)
        btn_bar.addWidget(rem_b)
        sl.addLayout(btn_bar)
        tabs.addTab(scope, "Search Scope")

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

    def _add_dir(self):
        f = QFileDialog.getExistingDirectory(self, "Add Search Folder")
        if f:
            self.path_list.addItem(f)

    def _rem_dir(self):
        for item in self.path_list.selectedItems():
            self.path_list.takeItem(self.path_list.row(item))

    def _save(self):
        self.cfg["hotkey"] = self.hk_input.text()
        self.cfg["hide_on_blur"] = self.cb_blur.isChecked()
        self.cfg["theme"] = self.theme_combo.currentText()
        self.cfg["opacity"] = self.op_slider.value()
        self.cfg["max_results"] = self.res_spin.value()
        self.cfg["search_paths"] = [self.path_list.item(i).text() for i in range(self.path_list.count())]
        save_settings(self.cfg)
        self.theme_changed.emit()
        self.accept()
