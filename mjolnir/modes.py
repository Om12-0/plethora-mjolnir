"""Prefix keyword modes: one input line, five behaviours. Qt-free."""
from __future__ import annotations

import ast
import math
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .modes_matching import fuzzy_score, rank_items, one_line
from .open_scanner import (
    Entry, start_menu_roots, scan_start_menu, scan_path,
    scan_targets, search_targets, invalidate_cache,
    START_MENU_ENVVARS, SHORTCUT_EXTS, APP_EXTS, SCAN_TTL
)

__all__ = [
    # modes
    "MODE_SEARCH", "MODE_OPEN", "MODE_CALC", "MODE_SHELL", "MODE_CLIPBOARD",
    "MODES", "MODE_LABELS", "MODE_PLACEHOLDERS", "PREFIX_EXAMPLES",
    "Query", "parse", "mode_label", "placeholder",
    # calculator
    "CalcResult", "calculate", "format_number",
    "ALLOWED_FUNCTIONS", "ALLOWED_CONSTANTS",
    # open mode
    "Entry", "start_menu_roots", "scan_start_menu", "scan_path",
    "scan_targets", "search_targets", "invalidate_cache",
    "START_MENU_ENVVARS", "SHORTCUT_EXTS", "APP_EXTS", "SCAN_TTL",
    # terminal
    "ShellPlan", "shell_plan", "run_shell", "spawn", "MAX_COMMAND_CHARS",
    # matching
    "fuzzy_score", "rank_items", "one_line",
]

_DEVNULL = subprocess.DEVNULL if hasattr(subprocess, "DEVNULL") else None

MODE_SEARCH = "search"
MODE_OPEN = "open"
MODE_CALC = "calc"
MODE_SHELL = "shell"
MODE_CLIPBOARD = "clipboard"

MODES: Tuple[str, ...] = (MODE_SEARCH, MODE_OPEN, MODE_CALC, MODE_SHELL, MODE_CLIPBOARD)

MODE_LABELS: Dict[str, str] = {
    MODE_SEARCH: "Documents",
    MODE_OPEN: "Launcher",
    MODE_CALC: "Calculator",
    MODE_SHELL: "Terminal",
    MODE_CLIPBOARD: "Clipboard",
}

MODE_PLACEHOLDERS: Dict[str, str] = {
    MODE_SEARCH: "Search documents, code, notes by meaning...",
    MODE_OPEN: "Open an app, shortcut or file...",
    MODE_CALC: "Type an expression, e.g. 45 * 1.18  ·  sqrt(256)",
    MODE_SHELL: "Type a command; Enter runs it in a terminal",
    MODE_CLIPBOARD: "Search clipboard history…",
}

PREFIX_EXAMPLES: Tuple[Tuple[str, str], ...] = (
    ("report from june", MODE_SEARCH),
    ("? report", MODE_SEARCH),
    ("find report", MODE_SEARCH),
    ("open chrome", MODE_OPEN),
    ("calc 2 ** 10", MODE_CALC),
    ("= 45 * 1.18", MODE_CALC),
    ("=45*1.18", MODE_CALC),
    ("> ipconfig /flushdns", MODE_SHELL),
    (">ping 1.1.1.1", MODE_SHELL),
    ("cb invoice", MODE_CLIPBOARD),
    ("cb", MODE_CLIPBOARD),
)

_CHAR_PREFIXES: Dict[str, str] = {
    "?": MODE_SEARCH,
    "=": MODE_CALC,
    ">": MODE_SHELL,
}

_WORD_PREFIXES: Dict[str, str] = {
    "find": MODE_SEARCH,
    "open": MODE_OPEN,
    "calc": MODE_CALC,
    "cb": MODE_CLIPBOARD,
}

_KEYWORD_RE = re.compile(
    r"^(" + "|".join(re.escape(k) for k in _WORD_PREFIXES) + r")(?:\s+(.*)|$)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Query:
    raw: str
    mode: str
    term: str
    prefix: str = ""

    @property
    def is_search(self) -> bool:
        return self.mode == MODE_SEARCH

    @property
    def is_open(self) -> bool:
        return self.mode == MODE_OPEN

    @property
    def is_calc(self) -> bool:
        return self.mode == MODE_CALC

    @property
    def is_shell(self) -> bool:
        return self.mode == MODE_SHELL

    @property
    def is_clipboard(self) -> bool:
        return self.mode == MODE_CLIPBOARD

    @property
    def empty(self) -> bool:
        return not self.term

    @property
    def label(self) -> str:
        return mode_label(self.mode)


def mode_label(mode: str) -> str:
    return MODE_LABELS.get(str(mode or ""), MODE_LABELS[MODE_SEARCH])


def placeholder(mode: str) -> str:
    return MODE_PLACEHOLDERS.get(str(mode or ""), MODE_PLACEHOLDERS[MODE_SEARCH])


def parse(text: Any) -> Query:
    raw = "" if text is None else str(text)
    stripped = raw.lstrip()
    if not stripped:
        return Query(raw=raw, mode=MODE_SEARCH, term="", prefix="")

    head = stripped[0]
    if head in _CHAR_PREFIXES:
        return Query(raw=raw, mode=_CHAR_PREFIXES[head],
                     term=stripped[1:].strip(), prefix=head)

    match = _KEYWORD_RE.match(stripped)
    if match:
        word = match.group(1).lower()
        remainder = match.group(2)
        term = "" if remainder is None else remainder.strip()
        return Query(raw=raw, mode=_WORD_PREFIXES[word], term=term, prefix=word)

    return Query(raw=raw, mode=MODE_SEARCH, term=stripped, prefix="")


# --- safe ast calculator ---------------------------------------------------
class _Rejected(Exception):
    """A node the grammar does not allow (carries the user-facing reason)."""


def _guard_power(base, exponent) -> None:
    if isinstance(base, complex) or isinstance(exponent, complex):
        raise _Rejected("Complex numbers are not supported.")
    try:
        magnitude = abs(float(exponent))
        scale = abs(float(base))
    except (TypeError, ValueError, OverflowError):
        raise _Rejected("Exponent must be a number.")
    if magnitude > MAX_EXPONENT and scale not in (0.0, 1.0):
        raise _Rejected(f"Exponent too large (max {MAX_EXPONENT}).")


def _safe_power(base, exponent, modulus=None):
    _guard_power(base, exponent)
    if modulus is None:
        return pow(base, exponent)
    return pow(base, exponent, modulus)


ALLOWED_FUNCTIONS: Dict[str, Callable[..., Any]] = {
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log,
    "log10": math.log10,
    "exp": math.exp,
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "pow": lambda base, exponent, *rest: _safe_power(base, exponent, *rest),
}

ALLOWED_CONSTANTS: Dict[str, float] = {"pi": math.pi, "e": math.e}

MAX_EXPRESSION_CHARS = 500
MAX_EXPRESSION_NODES = 120
MAX_EXPONENT = 512

_BIN_OPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow)
_UNARY_OPS = (ast.UAdd, ast.USub)


def _apply_binop(op_type, left, right):
    if op_type is ast.Add:
        return left + right
    if op_type is ast.Sub:
        return left - right
    if op_type is ast.Mult:
        return left * right
    if op_type is ast.Div:
        return left / right
    if op_type is ast.FloorDiv:
        return left // right
    if op_type is ast.Mod:
        return left % right
    if op_type is ast.Pow:
        _guard_power(left, right)
        return left ** right
    raise _Rejected("Operator not supported.")


def _eval_node(node):
    if isinstance(node, ast.Constant):
        value = node.value
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise _Rejected("Only numeric literals are supported.")
        return value

    if isinstance(node, ast.Name):
        if node.id in ALLOWED_CONSTANTS:
            return ALLOWED_CONSTANTS[node.id]
        raise _Rejected(f"Unknown name: {node.id}")

    if isinstance(node, ast.UnaryOp):
        if not isinstance(node.op, _UNARY_OPS):
            raise _Rejected("Unary operator not supported.")
        operand = _eval_node(node.operand)
        return -operand if isinstance(node.op, ast.USub) else +operand

    if isinstance(node, ast.BinOp):
        if not isinstance(node.op, _BIN_OPS):
            raise _Rejected("Operator not supported.")
        return _apply_binop(type(node.op), _eval_node(node.left), _eval_node(node.right))

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise _Rejected("Only the built-in functions can be called.")
        name = node.func.id
        function = ALLOWED_FUNCTIONS.get(name)
        if function is None:
            raise _Rejected(f"Unknown function: {name}()")
        if len(node.args) > 8:
            raise _Rejected("Too many arguments.")
        keywords: Dict[str, Any] = {}
        for keyword in node.keywords:
            if keyword.arg is None:
                raise _Rejected("** arguments are not supported.")
            keywords[keyword.arg] = _eval_node(keyword.value)
        values = [_eval_node(arg) for arg in node.args]
        try:
            return function(*values, **keywords)
        except TypeError as exc:
            raise _Rejected(f"{name}(): {exc}")

    raise _Rejected("Unsupported expression.")


def _normalise_expression(text: str) -> str:
    source = str(text if text is not None else "").strip()
    if source.startswith("="):
        source = source[1:].lstrip()
    elif source[:5].lower() == "calc ":
        source = source[5:].lstrip()
    if source.endswith("="):
        source = source[:-1].rstrip()
    return source


def format_number(value: Any) -> str:
    if isinstance(value, bool):
        value = int(value)
    if isinstance(value, int):
        return str(value)
    number = float(value)
    if number.is_integer() and abs(number) < 1e15:
        return str(int(number))
    return f"{number:.10g}"


@dataclass(frozen=True)
class CalcResult:
    ok: bool
    expression: str = ""
    value: Any = None
    text: str = ""
    error: str = ""

    def __bool__(self) -> bool:
        return bool(self.ok)

    @property
    def display(self) -> str:
        return self.text if self.ok else self.error


def calculate(expression: Any) -> CalcResult:
    raw = "" if expression is None else str(expression)
    source = _normalise_expression(raw)
    if not source:
        return CalcResult(False, "", error="Type an expression — e.g. = 45 * 1.18")
    if len(source) > MAX_EXPRESSION_CHARS:
        return CalcResult(False, source, error=f"Too long (max {MAX_EXPRESSION_CHARS} characters).")
    if "$" in source or "`" in source or "\x00" in source:
        return CalcResult(False, source, error="Not a valid arithmetic expression.")

    try:
        tree = ast.parse(source, mode="exec")
    except (SyntaxError, ValueError, MemoryError, RecursionError):
        return CalcResult(False, source, error="Not a valid expression.")
    except Exception:
        return CalcResult(False, source, error="Not a valid expression.")

    if len(list(ast.walk(tree))) > MAX_EXPRESSION_NODES:
        return CalcResult(False, source, error="Expression is too complex.")
    if len(tree.body) != 1:
        return CalcResult(False, source, error="One expression at a time.")
    statement = tree.body[0]
    if not isinstance(statement, ast.Expr):
        return CalcResult(False, source, error="Only plain arithmetic is supported.")

    try:
        value = _eval_node(statement.value)
    except _Rejected as exc:
        return CalcResult(False, source, error=str(exc))
    except ZeroDivisionError:
        return CalcResult(False, source, error="Division by zero.")
    except (ValueError, OverflowError) as exc:
        return CalcResult(False, source, error=f"{type(exc).__name__}: {exc}")
    except RecursionError:
        return CalcResult(False, source, error="Expression is too deeply nested.")
    except Exception as exc:
        return CalcResult(False, source, error=f"Could not compute that ({type(exc).__name__}).")

    if isinstance(value, complex):
        return CalcResult(False, source, error="Complex results are not supported.")
    if isinstance(value, bool):
        value = int(value)
    if not isinstance(value, (int, float)):
        return CalcResult(False, source, error="That is not a number.")

    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return CalcResult(False, source, error="That is not a number.")
    if number != number or number in (float("inf"), float("-inf")):
        return CalcResult(False, source, error="Result is not a finite number.")

    text = format_number(number)
    return CalcResult(True, source, value=number, text=text)


# --- terminal runner --------------------------------------------------------
MAX_COMMAND_CHARS = 2000


@dataclass(frozen=True)
class ShellPlan:
    command: str = ""
    argv: Tuple[str, ...] = ()
    shell: str = ""
    cwd: str = ""
    error: str = ""

    def __bool__(self) -> bool:
        return bool(self.ok)

    @property
    def ok(self) -> bool:
        return bool(self.command) and bool(self.argv) and not self.error

    @property
    def display(self) -> str:
        if self.error:
            return self.error
        if not self.argv:
            return ""
        return " ".join(_quote(part) for part in self.argv)

    @property
    def target(self) -> str:
        return "Windows Terminal" if self.shell == "wt" else (
            "PowerShell" if self.shell == "powershell" else "")


def _quote(part: str) -> str:
    text = str(part)
    return f'"{text}"' if (" " in text or "\t" in text) else text


def shell_plan(command: Any, cwd: Optional[str] = None,
               which: Optional[Callable[[str], Optional[str]]] = None) -> ShellPlan:
    text = str(command if command is not None else "").strip()
    if not text:
        return ShellPlan(error="Type a command to run.")
    if len(text) > MAX_COMMAND_CHARS:
        return ShellPlan(command=text, error=f"Command too long (max {MAX_COMMAND_CHARS} characters).")
    if "\x00" in text:
        return ShellPlan(command=text, error="Command contains a null byte.")

    try:
        folder = os.path.abspath(str(cwd)) if cwd else os.path.abspath(os.curdir)
    except (OSError, ValueError, TypeError):
        folder = os.curdir
    lookup = which or shutil.which
    try:
        terminal = lookup("wt") or lookup("wt.exe")
    except (OSError, TypeError):
        terminal = None

    if terminal:
        argv = (str(terminal), "-d", folder, "powershell.exe", "-NoExit", "-Command", text)
        return ShellPlan(command=text, argv=argv, shell="wt", cwd=folder)
    argv = ("powershell", "-NoExit", "-Command", text)
    return ShellPlan(command=text, argv=argv, shell="powershell", cwd=folder)


def spawn(argv: Sequence[str], new_console: bool = False) -> bool:
    flags = 0
    maker = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    if (new_console and os.name == "nt" and maker
            and not str(argv[0] if argv else "").lower().endswith("wt.exe")):
        flags = maker
    try:
        subprocess.Popen(list(argv), shell=False, close_fds=True,
                         stdout=_DEVNULL, stderr=_DEVNULL, creationflags=flags)
        return True
    except (OSError, ValueError, subprocess.SubprocessError, IndexError):
        return False


def run_shell(plan: ShellPlan, spawner: Optional[Callable] = None) -> bool:
    if not plan or not plan.ok:
        return False
    runner = spawner or spawn
    try:
        return bool(runner(list(plan.argv), new_console=(plan.shell != "wt")))
    except TypeError:
        return bool(runner(list(plan.argv)))
    except Exception:
        return False
