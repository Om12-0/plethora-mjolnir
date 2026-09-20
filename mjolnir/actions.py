"""The launcher's action engine: nine things you can do to a search hit. Qt-free."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from . import openers
from .action_handlers import (
    Handler, KNOWN_HANDLERS, OPEN_WITH_DIALOG_ID, known_handlers,
    argv_reveal, argv_open_with_dialog, argv_terminal, argv_deep_link,
    deep_link_backend, recycle_path, recycle_request,
    FO_DELETE, FOF_ALLOWUNDO, FOF_NOCONFIRMATION, FOF_SILENT, FOF_NOERRORUI
)

__all__ = [
    "Target", "ActionResult", "ActionSpec", "ActionContext",
    "ACTION_SPECS", "ACTION_IDS", "ACTION_BY_KEY",
    "get_action", "action_for_key", "run", "run_key",
    "Handler", "KNOWN_HANDLERS", "OPEN_WITH_DIALOG_ID", "known_handlers",
    "argv_reveal", "argv_open_with_dialog", "argv_terminal", "argv_deep_link",
    "deep_link_backend", "recycle_path", "recycle_request", "make_reindexer",
    "FO_DELETE", "FOF_ALLOWUNDO", "FOF_NOCONFIRMATION", "FOF_SILENT", "FOF_NOERRORUI",
]

_DEVNULL = subprocess.DEVNULL if hasattr(subprocess, "DEVNULL") else None


@dataclass(frozen=True)
class Target:
    """One search hit, decoupled from search.Hit and from Qt."""

    path: str
    page: Optional[int] = None
    line: Optional[int] = None
    chunk_index: int = 0
    chunk_total: Optional[int] = None
    snippet: str = ""
    score: float = 0.0

    def __post_init__(self):
        if self.path and not os.path.isabs(self.path):
            object.__setattr__(self, "path", os.path.abspath(self.path))

    @property
    def name(self) -> str:
        return os.path.basename(self.path) or self.path

    @property
    def folder(self) -> str:
        folder = os.path.dirname(self.path)
        return folder or os.curdir

    @property
    def exists(self) -> bool:
        try:
            return os.path.exists(self.path)
        except OSError:
            return False

    @classmethod
    def coerce(cls, obj: Any) -> "Target":
        if isinstance(obj, cls):
            return obj
        if hasattr(obj, "path"):
            return cls(
                path=str(getattr(obj, "path", "") or ""),
                page=getattr(obj, "page", None),
                line=getattr(obj, "line", None),
                chunk_index=int(getattr(obj, "chunk_index", 0) or 0),
                chunk_total=getattr(obj, "chunk_total", None),
                snippet=str(getattr(obj, "snippet", "") or ""),
                score=float(getattr(obj, "score", 0.0) or 0.0),
            )
        if isinstance(obj, dict):
            return cls(
                path=str(obj.get("path") or ""),
                page=obj.get("page"),
                line=obj.get("line"),
                chunk_index=int(obj.get("chunk_index") or 0),
                chunk_total=obj.get("chunk_total"),
                snippet=str(obj.get("snippet") or ""),
                score=float(obj.get("score") or 0.0),
            )
        return cls(path=str(obj or ""))


@dataclass(frozen=True)
class ActionResult:
    ok: bool
    action_id: str
    message: str = ""
    detail: str = ""
    data: Dict[str, Any] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.ok)


@dataclass(frozen=True)
class ActionSpec:
    id: str
    key: str
    title: str
    detail: str
    glyph: str = ""
    shortcut_hint: str = ""
    is_async: bool = False


ACTION_SPECS: Tuple[ActionSpec, ...] = (
    ActionSpec("open_default", "1", "Open Default", "System default app", "↵", "Enter"),
    ActionSpec("open_with", "2", "Open With…", "Choose an app", "▸", "2"),
    ActionSpec("reveal", "3", "Reveal in Explorer", "Select in folder", "⌕", "Shift+Enter"),
    ActionSpec("copy_path", "4", "Copy Full Path", "Absolute file path", "⎘", "4"),
    ActionSpec("copy_chunk", "5", "Copy Matched Chunk", "Snippet text", "“", "Ctrl+C"),
    ActionSpec("open_terminal", "6", "Open Terminal Here", "wt / powershell", ">", "6"),
    ActionSpec("deep_link", "7", "Deep-Link", "Editor at line / PDF page", "↗", "7"),
    ActionSpec("reindex_file", "8", "Re-index File", "Update this file's vectors", "↻", "Ctrl+R", is_async=True),
    ActionSpec("recycle", "9", "Move to Recycle Bin", "Undo-able delete", "⌫", "Delete", is_async=True),
)

ACTION_IDS: Tuple[str, ...] = tuple(s.id for s in ACTION_SPECS)
ACTION_BY_KEY: Dict[str, ActionSpec] = {s.key: s for s in ACTION_SPECS}
_ACTION_BY_ID: Dict[str, ActionSpec] = {s.id: s for s in ACTION_SPECS}
ASYNC_ACTIONS = frozenset(s.id for s in ACTION_SPECS if s.is_async)


def get_action(action_id: str) -> Optional[ActionSpec]:
    return _ACTION_BY_ID.get(str(action_id or ""))


def action_for_key(key: Any) -> Optional[ActionSpec]:
    return ACTION_BY_KEY.get(str(key or "").strip())


def _default_copy(text: str) -> bool:
    return openers.copy_to_clipboard(text)


def _default_open_default(path: str) -> str:
    starter = getattr(os, "startfile", None)
    if starter is not None:
        starter(path)
        return "startfile"
    return openers.open_target(path)


def _default_reveal(path: str) -> None:
    openers.reveal(path)


def _default_spawn(argv: Sequence[str], new_console: bool = False) -> bool:
    flags = 0
    if new_console and os.name == "nt" and hasattr(subprocess, "CREATE_NEW_CONSOLE"):
        flags = subprocess.CREATE_NEW_CONSOLE
    try:
        subprocess.Popen(list(argv), shell=False, close_fds=True,
                         stdout=_DEVNULL, stderr=_DEVNULL, creationflags=flags)
        return True
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


def _default_deep_link(path: str, page=None, line=None) -> str:
    return openers.open_target(path, page=page, line=line)


def _default_recycle(path: str) -> bool:
    return recycle_path(path)


class ActionContext:
    """External environment dependency wrapper for actions (injectable for tests)."""

    def __init__(self, dry_run: bool = False, *,
                 copy=None, open_default=None, reveal=None, spawn=None,
                 deep_link=None, recycle=None, reindex=None,
                 which=None, isfile=None, platform=None):
        self.dry_run = bool(dry_run)
        self.calls: List[Tuple[str, tuple, dict]] = []
        self._impl: Dict[str, Optional[Callable]] = {
            "copy": copy or _default_copy,
            "open_default": open_default or _default_open_default,
            "reveal": reveal or _default_reveal,
            "spawn": spawn or _default_spawn,
            "deep_link": deep_link or _default_deep_link,
            "recycle": recycle or _default_recycle,
            "reindex": reindex,
        }
        self.which = which or shutil.which
        self.isfile = isfile or os.path.isfile
        self.platform = platform or sys.platform

    def call(self, name: str, *args, **kwargs):
        self.calls.append((name, args, kwargs))
        if self.dry_run:
            return True
        impl = self._impl.get(name)
        if impl is None:
            return None
        return impl(*args, **kwargs)

    def has(self, name: str) -> bool:
        return self.dry_run or self._impl.get(name) is not None

    def handlers(self) -> List[Handler]:
        return known_handlers(which=self.which, isfile=self.isfile)

    def recorded(self, name: str) -> List[tuple]:
        return [entry for entry in self.calls if entry[0] == name]


def act_open_default(target: Target, ctx: ActionContext) -> ActionResult:
    if not target.exists:
        return ActionResult(False, "open_default", f"File is gone: {target.name}")
    backend = ctx.call("open_default", target.path)
    if backend:
        return ActionResult(True, "open_default", f"Opened {target.name}",
                            detail=str(backend), data={"backend": str(backend)})
    return ActionResult(False, "open_default", f"Could not open {target.name}")


def act_open_with(target: Target, ctx: ActionContext, handler_id: str = "") -> ActionResult:
    handler_id = str(handler_id or "")
    if handler_id and handler_id != OPEN_WITH_DIALOG_ID:
        handler = next((h for h in ctx.handlers() if h.id == handler_id), None)
        if handler is None:
            return ActionResult(False, "open_with", f"Handler unavailable: {handler_id}")
        started = ctx.call("spawn", handler.argv(target.path))
        if started:
            return ActionResult(True, "open_with", f"Opened with {handler.label}",
                                detail=handler.exe, data={"handler": handler.id, "argv": handler.argv(target.path)})
        return ActionResult(False, "open_with", f"{handler.label} failed to start")

    argv = argv_open_with_dialog(target.path)
    started = ctx.call("spawn", argv, new_console=False)
    if started:
        return ActionResult(True, "open_with", "Choose an app…",
                            detail="rundll32 shell32.dll,OpenAs_RunDLL",
                            data={"handler": OPEN_WITH_DIALOG_ID, "argv": argv})
    return ActionResult(False, "open_with", "Could not open the Windows dialog")


def act_reveal(target: Target, ctx: ActionContext) -> ActionResult:
    if not target.exists:
        return ActionResult(False, "reveal", f"Nothing to reveal: {target.name}")
    ctx.call("reveal", target.path)
    return ActionResult(True, "reveal", f"Revealed {target.name}",
                        detail=target.folder, data={"argv": argv_reveal(target.path)})


def act_copy_path(target: Target, ctx: ActionContext) -> ActionResult:
    ok = bool(ctx.call("copy", target.path))
    return ActionResult(ok, "copy_path", "Path copied" if ok else "Clipboard unavailable", detail=target.path)


def act_copy_chunk(target: Target, ctx: ActionContext) -> ActionResult:
    snippet = str(target.snippet or "").strip()
    if not snippet:
        return ActionResult(False, "copy_chunk", "No matched chunk to copy")
    ok = bool(ctx.call("copy", snippet))
    return ActionResult(ok, "copy_chunk", "Chunk copied" if ok else "Clipboard unavailable", detail=snippet[:200])


def act_open_terminal(target: Target, ctx: ActionContext) -> ActionResult:
    folder = target.folder
    if not os.path.isdir(folder):
        return ActionResult(False, "open_terminal", f"No folder: {folder}")
    argv = argv_terminal(folder, which=ctx.which)
    started = ctx.call("spawn", argv, new_console=True)
    if started:
        return ActionResult(True, "open_terminal", f"Terminal at {folder}",
                            detail=" ".join(argv), data={"argv": argv})
    return ActionResult(False, "open_terminal", "Could not start a terminal")


def act_deep_link(target: Target, ctx: ActionContext) -> ActionResult:
    argv = argv_deep_link(target.path, page=target.page, line=target.line)
    if argv is not None:
        started = ctx.call("spawn", argv)
        if started:
            what = "page" if deep_link_backend(target.path) == "pdf" else "editor"
            return ActionResult(True, "deep_link", f"Opened in {what}",
                                detail=" ".join(argv), data={"argv": argv})
        return ActionResult(False, "deep_link", "Handler failed to start")
    backend = ctx.call("deep_link", target.path, target.page, target.line)
    if backend:
        return ActionResult(True, "deep_link", f"Opened ({backend})",
                            detail=str(backend), data={"backend": str(backend)})
    return ActionResult(False, "deep_link", "No deep-link handler for this file")


def act_reindex_file(target: Target, ctx: ActionContext) -> ActionResult:
    if not ctx.has("reindex"):
        return ActionResult(False, "reindex_file", "Re-index unavailable: no indexer attached")
    counters = ctx.call("reindex", target.path)
    if isinstance(counters, dict):
        changed = int(counters.get("added", 0)) + int(counters.get("updated", 0))
        return ActionResult(True, "reindex_file", f"Re-indexed: {changed} file update(s)",
                            detail=str(counters), data=counters)
    if ctx.dry_run:
        return ActionResult(True, "reindex_file", f"Re-indexed {target.name}", detail="dry-run")
    return ActionResult(False, "reindex_file", f"Could not re-index {target.name}")


def act_recycle(target: Target, ctx: ActionContext) -> ActionResult:
    if not target.exists:
        if ctx.has("reindex"):
            ctx.call("reindex", target.path)
        return ActionResult(False, "recycle", f"File is already gone: {target.name}")
    moved = bool(ctx.call("recycle", target.path))
    if not moved:
        return ActionResult(False, "recycle", "Recycle Bin move failed — nothing was deleted", detail=target.path)
    if ctx.has("reindex"):
        ctx.call("reindex", target.path)
    return ActionResult(True, "recycle", f"{target.name} → Recycle Bin", detail=target.path, data={"undo": True})


_IMPLEMENTATIONS = {
    "open_default": act_open_default,
    "open_with": act_open_with,
    "reveal": act_reveal,
    "copy_path": act_copy_path,
    "copy_chunk": act_copy_chunk,
    "open_terminal": act_open_terminal,
    "deep_link": act_deep_link,
    "reindex_file": act_reindex_file,
    "recycle": act_recycle,
}


def run(action_id: str, target, context: Optional[ActionContext] = None, **kwargs) -> ActionResult:
    ctx = context or ActionContext()
    spec = get_action(action_id)
    if spec is None:
        return ActionResult(False, str(action_id), f"Unknown action: {action_id!r}")
    resolved = Target.coerce(target)
    if not resolved.path:
        return ActionResult(False, spec.id, "Nothing selected")
    impl = _IMPLEMENTATIONS.get(spec.id)
    if impl is None:
        return ActionResult(False, spec.id, f"Action not implemented: {spec.id}")
    try:
        return impl(resolved, ctx, **kwargs)
    except Exception as exc:
        return ActionResult(False, spec.id, f"{type(exc).__name__}: {exc}")


def run_key(key, target, context: Optional[ActionContext] = None, **kwargs) -> ActionResult:
    spec = action_for_key(key)
    if spec is None:
        return ActionResult(False, str(key), f"No action for key {key!r}")
    return run(spec.id, target, context, **kwargs)


def make_reindexer(cfg, store, embedder, log=None) -> Callable[[str], Optional[dict]]:
    def reindex(path: str) -> Optional[dict]:
        from .indexer import Indexer
        try:
            indexer = Indexer(cfg, store, embedder, log=log or (lambda *_: None))
            return indexer.index_paths([path], rebuild=True)
        except Exception:
            return None
    return reindex
