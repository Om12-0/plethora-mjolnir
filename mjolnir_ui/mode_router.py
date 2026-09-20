"""Prefix parser and state machine managing transitions and terminal safety."""
from __future__ import annotations

import os
import re
import subprocess
import threading
from typing import Callable, Optional

from PySide6 import QtCore
from PySide6.QtCore import Signal

from mjolnir import modes

# Blacklist of potentially destructive commands
DESTRUCTIVE_PATTERN = re.compile(
    r"\b("
    r"rmdir|rd|del|erase|remove-item|ri|"
    r"format|diskpart|"
    r"drop-database|"
    r"stop-computer|restart-computer|"
    r"set-executionpolicy"
    r")\b",
    re.IGNORECASE,
)

FORCE_PATTERN = re.compile(r"(?:^|\s)(?:--force|-force)\b", re.IGNORECASE)


def is_destructive(cmd: str) -> bool:
    """Return True if command matches the destructive pattern."""
    if not cmd:
        return False
    return bool(DESTRUCTIVE_PATTERN.search(cmd))


def is_forced(cmd: str) -> bool:
    """Return True if command includes --force or -force flag."""
    if not cmd:
        return False
    return bool(FORCE_PATTERN.search(cmd))


class BackgroundCommandRunner(QtCore.QObject):
    """Executes a command in background, streaming stdout/stderr via Qt signals."""

    line_received = Signal(str)
    finished = Signal(int)

    def __init__(self, command: str, cwd: str):
        super().__init__()
        self.command = command
        self.cwd = cwd
        self._proc: Optional[subprocess.Popen] = None
        self._thread: Optional[threading.Thread] = None

    def start(self):
        def _run():
            try:
                # Run with powershell -NoProfile -Command
                self._proc = subprocess.Popen(
                    ["powershell.exe", "-NoProfile", "-Command", self.command],
                    cwd=self.cwd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                if self._proc.stdout:
                    for line in iter(self._proc.stdout.readline, ""):
                        self.line_received.emit(line)
                    self._proc.stdout.close()
                code = self._proc.wait()
                self.finished.emit(code)
            except Exception as exc:
                self.line_received.emit(f"Execution failed: {exc}\n")
                self.finished.emit(1)

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

    def terminate(self):
        if self._proc:
            try:
                self._proc.terminate()
            except Exception:
                pass


class ModeRouter:
    """State machine managing transitions between search, open, calc, shell, and clipboard."""

    STAGE_INPUT = "input"
    STAGE_CONFIRMING = "confirming"
    STAGE_RUNNING = "running"

    def __init__(self):
        self.mode = modes.MODE_SEARCH
        self.parsed = modes.parse("")
        self.shell_stage = self.STAGE_INPUT
        self.streaming_output = ""
        self.runner: Optional[BackgroundCommandRunner] = None

    def parse_query(self, text: str) -> modes.Query:
        self.parsed = modes.parse(text)
        self.mode = self.parsed.mode
        if not self.parsed.is_shell:
            self.shell_stage = self.STAGE_INPUT
            self.streaming_output = ""
        return self.parsed

    def stage_shell_confirmation(self) -> bool:
        """Move shell mode to confirming stage. Returns True if staged."""
        if not self.parsed.is_shell:
            return False
        self.shell_stage = self.STAGE_CONFIRMING
        return True

    def cancel_shell_confirmation(self) -> bool:
        """Cancel confirmation state back to input. Returns True if was confirming."""
        if self.shell_stage == self.STAGE_CONFIRMING:
            self.shell_stage = self.STAGE_INPUT
            return True
        return False

    def can_run_shell_on_enter(self, command: str) -> Tuple[bool, str]:
        """Check whether command is allowed to run on raw Enter.

        Destructive commands require explicit --force or Ctrl+Enter.
        """
        if is_destructive(command) and not is_forced(command):
            return False, "Destructive command blocked! Requires --force or [Ctrl + Enter] to confirm."
        return True, ""
