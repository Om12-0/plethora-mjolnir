"""Action panel: 1-9 overlay menu triggered by Tab or Right Arrow on a highlighted result."""
from __future__ import annotations

from typing import List, Optional, Sequence

from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import Qt

from mjolnir import actions


class ActionRow(QtWidgets.QFrame):
    """One clickable line of the action panel: key badge, glyph, title, detail."""

    clicked = QtCore.Signal(str)

    def __init__(self, ident: str, key: str, title: str, detail: str = "",
                 glyph: str = "", parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.ident = str(ident)
        self.setObjectName("actionRow")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setProperty("selected", False)
        self.setFixedHeight(34)
        self.setCursor(Qt.PointingHandCursor)

        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(8, 3, 10, 3)
        row.setSpacing(9)

        self.key_label = QtWidgets.QLabel(str(key))
        self.key_label.setObjectName("actionKey")
        self.key_label.setAlignment(Qt.AlignCenter)
        self.key_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.key_label.setFixedWidth(18)
        row.addWidget(self.key_label, 0, Qt.AlignVCenter)

        self.glyph_label = QtWidgets.QLabel(str(glyph or "•"))
        self.glyph_label.setObjectName("actionGlyph")
        self.glyph_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.glyph_label.setFixedWidth(16)
        self.glyph_label.setAlignment(Qt.AlignCenter)
        row.addWidget(self.glyph_label, 0, Qt.AlignVCenter)

        self.title_label = QtWidgets.QLabel(str(title))
        self.title_label.setObjectName("actionTitle")
        self.title_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        row.addWidget(self.title_label, 0, Qt.AlignVCenter)

        self.detail_label = QtWidgets.QLabel(str(detail))
        self.detail_label.setObjectName("actionDetail")
        self.detail_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        row.addWidget(self.detail_label, 1, Qt.AlignVCenter)

    def set_selected(self, selected: bool):
        self.setProperty("selected", bool(selected))
        style = self.style()
        style.unpolish(self)
        style.polish(self)
        self.update()

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.ident)
            event.accept()
            return
        super().mousePressEvent(event)


class ActionPanel(QtWidgets.QWidget):
    """The Alfred-style action panel (Tab / Right Arrow on a highlighted result)."""

    activated = QtCore.Signal(str, str)
    back = QtCore.Signal()

    def __init__(self, specs: Optional[Sequence] = None, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.setObjectName("actionPanel")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.specs = list(specs) if specs is not None else list(actions.ACTION_SPECS)
        self.target = actions.Target(path="")
        self.handlers: List[actions.Handler] = []
        self.cursor = 0
        self.mode = "root"

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(6)

        self.name_label = QtWidgets.QLabel("No selection")
        self.name_label.setObjectName("actionFileName")
        self.name_label.setWordWrap(True)
        root.addWidget(self.name_label)

        self.path_label = QtWidgets.QLabel("")
        self.path_label.setObjectName("actionFilePath")
        self.path_label.setWordWrap(True)
        root.addWidget(self.path_label)

        self.hint_label = QtWidgets.QLabel("press 1–9 · ↑↓ then ↵ · Esc or ← to go back")
        self.hint_label.setObjectName("actionHint")
        root.addWidget(self.hint_label)

        self.rows_box = QtWidgets.QWidget()
        self.rows_box.setObjectName("actionRows")
        rows = QtWidgets.QVBoxLayout(self.rows_box)
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setSpacing(2)
        self.rows: List[ActionRow] = []
        for spec in self.specs:
            row = ActionRow(spec.id, spec.key, spec.title, spec.detail, spec.glyph)
            row.clicked.connect(self.activate)
            rows.addWidget(row)
            self.rows.append(row)
        rows.addStretch(1)
        root.addWidget(self.rows_box, 1)

        # Inline "Open With..." submenu
        self.submenu = QtWidgets.QWidget()
        self.submenu.setObjectName("actionSubmenu")
        self.submenu.setAttribute(Qt.WA_StyledBackground, True)
        sub_lay = QtWidgets.QVBoxLayout(self.submenu)
        sub_lay.setContentsMargins(0, 0, 0, 0)
        sub_lay.setSpacing(2)
        self.sub_title = QtWidgets.QLabel("Open With…")
        self.sub_title.setObjectName("actionHint")
        sub_lay.addWidget(self.sub_title)
        self.sub_rows: List[ActionRow] = []
        sub_lay.addStretch(1)
        root.addWidget(self.submenu, 1)
        self.submenu.hide()

    def set_target(self, target) -> None:
        self.target = actions.Target.coerce(target)
        if not self.target.path:
            self.name_label.setText("No selection")
            self.path_label.setText("")
            return
        self.name_label.setText(self.target.name)
        sub = self.target.path
        if self.target.page not in (None, "", 0):
            sub += f" · p. {self.target.page}"
        if self.target.chunk_index:
            sub += f" · chunk {self.target.chunk_index + 1}"
        self.path_label.setText(sub)

    def set_handlers(self, handlers: Sequence) -> None:
        self.handlers = list(handlers or [])
        for row in self.sub_rows:
            row.setParent(None)
            row.deleteLater()
        self.sub_rows = []
        layout = self.submenu.layout()
        for handler in self.handlers:
            index = len(self.sub_rows) + 1
            row = ActionRow(handler.id, str(index), handler.label, handler.kind, "▸")
            row.clicked.connect(self.activate)
            layout.insertWidget(layout.count() - 1, row)
            self.sub_rows.append(row)
        row = ActionRow(actions.OPEN_WITH_DIALOG_ID, str(len(self.sub_rows) + 1),
                        "Choose another app…", "Windows dialog", "…")
        row.clicked.connect(self.activate)
        layout.insertWidget(layout.count() - 1, row)
        self.sub_rows.append(row)

    def ensure_handlers(self, provider=None) -> None:
        if not self.sub_rows and provider is not None:
            self.set_handlers(provider())

    def _active_rows(self) -> List[ActionRow]:
        return self.sub_rows if self.mode == "submenu" and self.sub_rows else self.rows

    def select(self, index: int) -> None:
        rows = self._active_rows()
        self.cursor = max(0, min(int(index), max(0, len(rows) - 1)))
        for position, row in enumerate(rows):
            row.set_selected(position == self.cursor)

    def move_cursor(self, delta: int) -> None:
        rows = self._active_rows()
        if not rows:
            return
        self.select((self.cursor + int(delta)) % len(rows))

    def open_submenu(self) -> bool:
        if not self.sub_rows:
            return False
        self.mode = "submenu"
        self.rows_box.hide()
        self.submenu.show()
        self.select(0)
        return True

    def close_submenu(self) -> bool:
        if self.mode != "submenu":
            return False
        self.mode = "root"
        self.submenu.hide()
        self.rows_box.show()
        self.select(min(self.cursor, len(self.rows) - 1))
        return True

    def activate(self, ident: str) -> None:
        ident = str(ident)
        if self.mode != "submenu" and ident == "open_with" and self.open_submenu():
            return
        handler_id = ident if self.mode == "submenu" else ""
        if self.mode == "submenu":
            self.activated.emit("open_with", handler_id)
            self.close_submenu()
            return
        self.activated.emit(ident, "")

    def digit(self, key: str) -> bool:
        rows = self._active_rows()
        try:
            index = int(str(key)) - 1
        except (TypeError, ValueError):
            return False
        if not (0 <= index < len(rows)):
            return False
        self.select(index)
        self.activate(rows[index].ident)
        return True

    def enter(self) -> bool:
        rows = self._active_rows()
        if not rows:
            return False
        self.activate(rows[self.cursor].ident)
        return True

    def escape(self) -> bool:
        if self.close_submenu():
            return True
        return False

    def set_focus_cursor(self) -> None:
        if self.mode == "submenu":
            self.select(0)
        else:
            self.mode = "root"
            self.submenu.hide()
            self.rows_box.show()
            self.select(0)
