"""Mode view pages (calc, open, shell, clipboard) and action execution mixin."""
from __future__ import annotations

import os
import shutil
import threading
from typing import Optional

from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import QTimer, Signal

from mjolnir import actions, clipboard as clipboard_history, modes, openers, styles
from .inspector_pane import (
    Capsule, calc_html, command_html, confirmation_html, launch_html
)
from .mode_router import (
    BackgroundCommandRunner, ModeRouter, is_destructive, is_forced
)
from .result_list import (
    ClipboardRow, NoticeRow, ResultItemWidget, category_of
)


class ModeViewsMixin:
    """Methods managing non-search modes: calc, open, shell, clipboard and actions."""

    def _show_calc(self, expression: str) -> None:
        self.show_view(0)
        result = modes.calculate(expression)
        self.calc_result = result
        self._reset_list()
        self.rows = [result]
        self._add_row(NoticeRow(result.display, result.expression or expression,
                                tag="calc", glyph="=", variant="big"),
                      height=54, tooltip=result.display)
        self.results.setCurrentRow(0)
        self.insp_title.setText(f"= {result.text}" if result.ok else "Calculator")
        self.insp_sub.setText(result.expression or "type an expression after =")
        self.preview.setHtml(calc_html(result))
        if result.ok:
            self.status.setText(f"= {result.text}  ·  Enter copies it")
        else:
            self.status.setText(result.error)

    def _show_open(self, term: str) -> None:
        self.show_view(0)
        self._reset_list()
        try:
            self.rows = list(modes.search_targets(term, limit=40))
        except Exception:
            self.rows = []
        for position, entry in enumerate(self.rows):
            self._add_row(
                ResultItemWidget(entry.label, entry.path, category_of(entry.path),
                                 page=entry.kind_label, index=position + 1),
                height=52, tooltip=entry.path)
        if self.rows:
            self.results.setCurrentRow(0)
            self.status.setText(f"{len(self.rows)} target(s)  ·  Enter opens")
        else:
            self.status.setText("Nothing found — scanned Start Menu shortcuts and executables on PATH.")
            self.insp_title.setText("Launcher")
            self.insp_sub.setText("")
            self.preview.setHtml(launch_html("", "", "", term, empty=True))
            self._render_capsules(None, None, None, None)

    def _update_open_preview(self, row) -> None:
        if not (0 <= row < len(self.rows)):
            return
        entry = self.rows[row]
        self.insp_title.setText(entry.label)
        self.insp_sub.setText(entry.path)
        self._render_capsules(None, None, None, None)
        self.preview.setHtml(launch_html(entry.label, entry.path, entry.kind_label, self.parsed.term))

    def _current_entry(self):
        row = self.results.currentRow()
        if self.mode == modes.MODE_OPEN and 0 <= row < len(self.rows):
            return self.rows[row]
        return None

    def _selected_target(self) -> "actions.Target":
        entry = self._current_entry()
        if entry is not None:
            return actions.Target(path=entry.path)
        return self._target_of(self._current_hit())

    def _show_shell(self, command: str) -> None:
        self.show_view(0)
        self._reset_list()
        try:
            plan = modes.shell_plan(command, cwd=os.path.expanduser("~"), which=shutil.which)
        except Exception:
            plan = modes.ShellPlan(error="Could not build that command.")
        self.shell_plan = plan
        self.rows = [plan]
        if plan.ok:
            self._add_row(NoticeRow(plan.command, plan.display,
                                    tag="Enter to stage", glyph="\u276f"),
                          height=52, tooltip=plan.display)
            self.results.setCurrentRow(0)
            self.insp_title.setText(plan.target)
            self.insp_sub.setText(plan.display)
            self.preview.setHtml(command_html(plan.display, plan.target, plan.cwd))
            self.status.setText(f"Nothing runs until you press Enter  ·  {plan.target}")
            return
        self.insp_title.setText("Terminal")
        self.insp_sub.setText("")
        self.preview.setHtml(command_html("", "", "", error=plan.error))
        self._render_capsules(None, None, None, None)
        self.status.setText(plan.error)

    def _handle_shell_enter(self, ctrl: bool = False) -> bool:
        plan = self.shell_plan
        if plan is None or not bool(getattr(plan, "ok", False)):
            self._toast(getattr(plan, "error", "") or "Nothing to run")
            return False

        command = plan.command
        destructive = is_destructive(command)
        forced = is_forced(command)

        if destructive and not forced and not ctrl:
            if self.router.shell_stage == ModeRouter.STAGE_INPUT:
                self.router.stage_shell_confirmation()
                self._set_inspector_warning_border(True)
                self.preview.setHtml(confirmation_html(
                    command=command,
                    cwd=plan.cwd,
                    shell_name=plan.target or "PowerShell",
                    destructive=True,
                ))
                self.status.setText("Destructive command! Press [Ctrl+Enter] to launch, or add --force.")
                return True
            self._toast("Refused: Destructive command requires --force or Ctrl+Enter")
            self.status.setText("Blocked! Add --force to command or press [Ctrl + Enter] to launch.")
            return False

        if ctrl or self.shell_runner is not None:
            started = modes.run_shell(plan, spawner=self.shell_runner)
            if started:
                self._toast(f"Launched in {plan.target or 'terminal'}")
                self.hide()
                return True
            self._toast("Could not launch terminal")
            return False

        if self.router.shell_stage == ModeRouter.STAGE_INPUT:
            self.router.stage_shell_confirmation()
            self._set_inspector_warning_border(True)
            self.preview.setHtml(confirmation_html(
                command=command,
                cwd=plan.cwd,
                shell_name=plan.target or "PowerShell",
                destructive=False,
            ))
            self.status.setText("Press [Enter] again to run in background · [Ctrl+Enter] for terminal · [Esc] abort")
            return True

        if self.router.shell_stage == ModeRouter.STAGE_CONFIRMING:
            self.router.shell_stage = ModeRouter.STAGE_RUNNING
            self.router.streaming_output = ""
            self.status.setText(f"Running background command: {command[:30]}...")

            runner = BackgroundCommandRunner(command, plan.cwd)
            self.router.runner = runner

            def on_line(line: str):
                self.router.streaming_output += line
                self.preview.setHtml(confirmation_html(
                    command=command,
                    cwd=plan.cwd,
                    shell_name=plan.target or "PowerShell",
                    destructive=False,
                    streaming_output=self.router.streaming_output,
                ))

            def on_finished(exit_code: int):
                self.router.shell_stage = ModeRouter.STAGE_INPUT
                self.status.setText(f"Command finished with exit code {exit_code}")

            runner.line_received.connect(on_line)
            runner.finished.connect(on_finished)
            runner.start()
            return True

        return False

    def _show_clipboard(self, term: str) -> None:
        self.show_view(2)
        self.rows = []
        self.hits = []
        items: list = []
        total = 0
        if self.clipboard_store is not None:
            try:
                items = list(self.clipboard_store.search(term, limit=200))
                total = int(self.clipboard_store.count())
            except Exception:
                items, total = [], 0
        self.clip_items = items
        self.clipboard_list.clear()
        for position, item in enumerate(self.clip_items):
            widget = ClipboardRow(item.preview, item.meta, index=position + 1,
                                  nchars=item.nchars, tooltip=item.text[:800])
            row_item = QtWidgets.QListWidgetItem()
            row_item.setSizeHint(QtCore.QSize(0, 50))
            row_item.setToolTip(item.text[:800])
            self.clipboard_list.addItem(row_item)
            self.clipboard_list.setItemWidget(row_item, widget)
        if self.clip_items:
            self.clipboard_list.setCurrentRow(0)
        self.clip_count.setText(f"{len(self.clip_items)} of {total} item(s)")
        if self.clipboard_store is None:
            self.clip_note.setText("Clipboard history is off or database could not be opened.")
        elif not self.clip_items:
            self.clip_note.setText(f"No clipboard item matches {term!r}." if term else "Nothing copied yet.")
        else:
            self.clip_note.setText("Enter copies and pastes into active window · Esc returns to document search.")
        self.status.setText(f"{len(self.clip_items)} of {total} item(s)  ·  Enter pastes  ·  Esc goes back")

    def _on_clipboard_row_changed(self, _row: int) -> None:
        item = self._current_clip_item()
        if item is not None:
            self.status.setText(f"{item.meta}  ·  Enter pastes  ·  Esc goes back")

    def start_clipboard_watcher(self) -> "clipboard_history.ClipboardWatcher | None":
        if self.clipboard_store is None or self.clipboard_watcher is not None:
            return self.clipboard_watcher
        if not bool(getattr(self.cfg, "clipboard_enabled", True)):
            return None
        interval = max(50, int(getattr(self.cfg, "clipboard_poll_ms", 500) or 500)) / 1000.0
        try:
            watcher = clipboard_history.ClipboardWatcher(
                self.clipboard_store, interval=interval,
                on_change=self._clip_sig.added.emit)
        except Exception:
            return None
        self.clipboard_watcher = watcher
        try:
            watcher.start()
        except Exception:
            self.clipboard_watcher = None
        return self.clipboard_watcher

    def stop_clipboard_watcher(self, timeout: float = 2.0) -> bool:
        watcher = self.clipboard_watcher
        if watcher is None:
            return True
        self.clipboard_watcher = None
        try:
            return bool(watcher.stop(timeout))
        except Exception:
            return False

    @QtCore.Slot(int)
    def _on_clipboard_added(self, _rowid: int) -> None:
        if self.view == 2:
            self._show_clipboard(self.parsed.term)

    def open_clipboard_history(self, term: str = "") -> bool:
        try:
            if not self.isVisible():
                self.show_centered()
        except Exception:
            pass
        text = "cb" if not str(term or "").strip() else f"cb {str(term).strip()}"
        self.search.setText(text)
        self._fire_query()
        return self.view == 2

    def close_clipboard_mode(self) -> bool:
        if self.view != 2:
            return False
        self.mode = modes.MODE_SEARCH
        self.show_view(0)
        self.search.clear()
        self._refresh_stats()
        return True

    def _current_clip_item(self):
        row = self.clipboard_list.currentRow()
        if 0 <= row < len(self.clip_items):
            return self.clip_items[row]
        return None

    def _clipboard_enter(self) -> bool:
        item = self._current_clip_item()
        if item is None:
            self._toast("No clipboard item selected")
            return False
        try:
            copied = bool(self.copy_fn(item.text))
        except Exception:
            copied = False
        if not copied:
            self._toast("Clipboard unavailable")
            return False
        self._toast("Pasted")
        self.hide()
        QTimer.singleShot(max(0, int(self.paste_delay_ms)), self._emit_paste)
        return True

    def _emit_paste(self) -> None:
        try:
            self.paste_fn()
        except Exception:
            pass

    def _copy_calc(self) -> bool:
        result = self.calc_result
        if result is None or not bool(getattr(result, "ok", False)):
            self._toast(getattr(result, "error", "") or "Nothing to copy")
            return False
        try:
            copied = bool(self.copy_fn(result.text))
        except Exception:
            copied = False
        self._toast("Result copied!" if copied else "Clipboard unavailable")
        return copied

    def _copy_clip_item(self) -> bool:
        item = self._current_clip_item()
        if item is None:
            self._toast("No clipboard item selected")
            return False
        try:
            copied = bool(self.copy_fn(item.text))
        except Exception:
            copied = False
        self._toast("Copied!" if copied else "Clipboard unavailable")
        return copied

    def _activate_row(self, shift: bool = False, ctrl: bool = False) -> bool:
        if self.view == 2:
            return self._clipboard_enter()
        if self.mode == modes.MODE_CALC:
            return self._copy_calc()
        if self.mode == modes.MODE_SHELL:
            return self._handle_shell_enter(ctrl=ctrl)
        if self.mode == modes.MODE_OPEN:
            entry = self._current_entry()
            if entry is None:
                self._toast("Nothing to open")
                return False
            if shift:
                openers.reveal(entry.path)
                return True
            openers.open_target(entry.path)
            self.hide()
            return True
        if shift:
            self._reveal_selected()
        else:
            self._open_selected()
        return True

    def open_action_panel(self) -> bool:
        target = self._selected_target()
        if not target.path:
            self._toast("Select a result first")
            return False
        self.action_panel.set_target(target)
        self.action_panel.ensure_handlers(self.action_ctx.handlers)
        self.action_panel.set_focus_cursor()
        self.show_view(1)
        self.status.setText(f"Actions for {os.path.basename(target.path)}")
        return True

    def close_action_panel(self) -> bool:
        if self.view == 0:
            return False
        self.show_view(0)
        self._refresh_stats()
        return True

    def _quick_actions(self):
        return self.open_action_panel()

    def _on_action_requested(self, action_id: str, handler_id: str):
        self.run_action(action_id, handler_id=handler_id)

    def run_action(self, action_id: str, handler_id: str = "") -> bool:
        target = self._selected_target()
        if not target.path:
            self._toast("No item selected")
            return False
        kwargs = {}
        if handler_id:
            kwargs["handler_id"] = handler_id
        if action_id in actions.ASYNC_ACTIONS:
            self.status.setText(f"Running {action_id}…")
            threading.Thread(
                target=lambda: self._action_sig.done.emit(
                    action_id, actions.run(action_id, target, self.action_ctx, **kwargs)
                ),
                daemon=True,
            ).start()
            return True
        result = actions.run(action_id, target, self.action_ctx, **kwargs)
        self._apply_action_result(action_id, result)
        return bool(result.ok)

    @QtCore.Slot(str, object)
    def _on_action_done(self, action_id: str, result):
        self._apply_action_result(action_id, result)

    def _apply_action_result(self, action_id: str, result):
        msg = getattr(result, "message", "") or ("Done" if result.ok else "Failed")
        self._toast(msg)
        self.status.setText(msg)
        if action_id == "recycle" and result.ok:
            self._drop_current_row()
            return
        if action_id == "reindex_file" and result.ok:
            self._chunk_totals.clear()
            self._refresh_stats()
            return
        if action_id == "reveal":
            self.hide()
            return
        if self.view == 1:
            self.close_action_panel()
        else:
            self._refresh_stats()

    def _selftest_view(self) -> None:
        try:
            capsules = self.insp_caps_widget.findChildren(Capsule) if self.insp_caps_widget is not None else []
            texts = [c.text() for c in capsules]
            print(f"[selftest] views={self.stack.count()} rows={self.results.count()} capsules={texts}")
            badges = []
            for i in range(min(self.results.count(), 10)):
                it = self.results.item(i)
                w = self.results.itemWidget(it) if it else None
                b = getattr(w, "badge", None) if w else None
                badges.append(b.text() if b is not None else None)
            print(f"[selftest] badges={badges}")
            self.open_action_panel()
            print(f"[selftest] action_panel visible={self.view == 1} rows={len(self.action_panel.rows)}")
            self.close_action_panel()
        except Exception as exc:
            print(f"[selftest] view probe failed: {exc}")

    def _selftest_modes(self) -> None:
        try:
            for text, expected_mode, expected_view in [
                ("calc 2 ** 10", modes.MODE_CALC, 0),
                ("> ipconfig /flushdns", modes.MODE_SHELL, 0),
                ("cb", modes.MODE_CLIPBOARD, 2),
            ]:
                self.search.setText(text)
                self._fire_query()
                print(f"[selftest] probe {text!r} -> mode={self.mode} view={self.view} (ok={self.mode == expected_mode and self.view == expected_view})")
        except Exception as exc:
            print(f"[selftest] mode probe failed: {exc}")
