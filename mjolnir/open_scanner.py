"""Start Menu shortcuts and PATH executables scanner for 'open' launcher mode. Qt-free."""
from __future__ import annotations

import os
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from . import modes_matching

START_MENU_ENVVARS: Tuple[str, ...] = (
    r"%APPDATA%\Microsoft\Windows\Start Menu\Programs",
    r"%PROGRAMDATA%\Microsoft\Windows\Start Menu\Programs",
)

SHORTCUT_EXTS: Tuple[str, ...] = (".lnk", ".url")
APP_EXTS: Tuple[str, ...] = (".exe", ".cmd", ".bat", ".com")
SCAN_TTL = 300.0
MAX_SCAN_ENTRIES = 5000

_VAR_RE = re.compile(r"%([^%]+)%")


@dataclass(frozen=True)
class Entry:
    """One launchable target: shortcut, PATH app, or path."""

    name: str
    path: str
    kind: str = "shortcut"
    source: str = ""

    @property
    def label(self) -> str:
        return self.name or os.path.basename(self.path) or self.path

    @property
    def kind_label(self) -> str:
        return {"shortcut": "Start Menu", "app": "PATH", "path": "Path"}.get(self.kind, self.kind)


def _expand(text: str, env) -> str:
    if not text:
        return ""
    lookup = env if env is not None else os.environ

    def replace(match):
        name = match.group(1)
        for candidate in (name, name.upper(), name.lower()):
            value = lookup.get(candidate)
            if value:
                return value
        return match.group(0)

    return _VAR_RE.sub(replace, str(text))


def start_menu_roots(env=None, isdir=None) -> List[str]:
    check = isdir or (lambda path: os.path.isdir(path))
    roots: List[str] = []
    for template in START_MENU_ENVVARS:
        expanded = _expand(template, env)
        if "%" in expanded:
            continue
        try:
            if check(expanded) and expanded not in roots:
                roots.append(expanded)
        except OSError:
            continue
    return roots


def _walk_entries(root: str, extensions: Sequence[str], kind: str, max_items: int) -> List[Entry]:
    found: List[Entry] = []
    suffixes = tuple(ext.lower() for ext in extensions)
    try:
        walker = os.walk(root, onerror=lambda _exc: None)
    except (OSError, TypeError):
        return found
    for folder, dirnames, filenames in walker:
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for filename in filenames:
            if not filename.lower().endswith(suffixes):
                continue
            path = os.path.join(folder, filename)
            name = os.path.splitext(filename)[0]
            found.append(Entry(name=name, path=path, kind=kind, source=root))
            if len(found) >= max_items:
                return found
    return found


def scan_start_menu(roots: Optional[Sequence[str]] = None, env=None,
                    max_items: int = MAX_SCAN_ENTRIES) -> List[Entry]:
    targets = list(roots) if roots is not None else start_menu_roots(env=env)
    entries: List[Entry] = []
    seen = set()
    for root in targets:
        for entry in _walk_entries(root, SHORTCUT_EXTS, "shortcut", max_items):
            key = (entry.name.lower(), entry.path.lower())
            if key in seen:
                continue
            seen.add(key)
            entries.append(entry)
    return entries


def scan_path(pathenv: Optional[str] = None, isfile=None,
              max_items: int = MAX_SCAN_ENTRIES) -> List[Entry]:
    raw = pathenv if pathenv is not None else os.environ.get("PATH", "")
    check = isfile or (lambda path: os.path.isfile(path))
    entries: List[Entry] = []
    seen_names = set()
    seen_dirs = set()
    for folder in str(raw or "").split(os.pathsep):
        folder = folder.strip().strip('"')
        if not folder:
            continue
        key = folder.lower()
        if key in seen_dirs:
            continue
        seen_dirs.add(key)
        try:
            names = os.listdir(folder)
        except (OSError, TypeError):
            continue
        for filename in names:
            if not filename.lower().endswith(APP_EXTS):
                continue
            stem = os.path.splitext(filename)[0].lower()
            if stem in seen_names:
                continue
            path = os.path.join(folder, filename)
            try:
                if not check(path):
                    continue
            except OSError:
                continue
            seen_names.add(stem)
            entries.append(Entry(name=os.path.splitext(filename)[0], path=path, kind="app", source=folder))
            if len(entries) >= max_items:
                return entries
    return entries


_SCAN_CACHE: Dict[str, Any] = {"key": None, "at": 0.0, "entries": []}
_SCAN_LOCK = threading.Lock()


def invalidate_cache() -> None:
    with _SCAN_LOCK:
        _SCAN_CACHE.update({"key": None, "at": 0.0, "entries": []})


def scan_targets(roots: Optional[Sequence[str]] = None,
                 pathenv: Optional[str] = None, ttl: float = SCAN_TTL,
                 now: Optional[float] = None, use_cache: bool = True,
                 max_items: int = MAX_SCAN_ENTRIES) -> List[Entry]:
    clock = time.monotonic() if now is None else float(now)
    resolved_roots = list(roots) if roots is not None else start_menu_roots()
    resolved_path = pathenv if pathenv is not None else os.environ.get("PATH", "")
    key = (tuple(resolved_roots), str(resolved_path))

    if use_cache:
        with _SCAN_LOCK:
            if _SCAN_CACHE["key"] == key and clock - float(_SCAN_CACHE["at"] or 0.0) < float(ttl):
                return list(_SCAN_CACHE["entries"])

    entries = (scan_start_menu(resolved_roots, max_items=max_items)
               + scan_path(resolved_path, max_items=max_items))
    entries.sort(key=lambda e: (0 if e.kind == "shortcut" else 1, e.name.lower()))

    if use_cache:
        with _SCAN_LOCK:
            _SCAN_CACHE.update({"key": key, "at": clock, "entries": list(entries)})
    return entries


def search_targets(term: Any, entries: Optional[Sequence[Entry]] = None,
                   limit: int = 30, use_cache: bool = True) -> List[Entry]:
    pool = list(entries) if entries is not None else scan_targets(use_cache=use_cache)
    query = str(term or "").strip().strip('"')
    if not query:
        return pool[:limit]

    direct: List[Entry] = []
    try:
        if os.path.exists(query):
            candidate = os.path.abspath(query)
            direct.append(Entry(name=os.path.basename(candidate) or candidate,
                                path=candidate, kind="path",
                                source=os.path.dirname(candidate)))
    except (OSError, ValueError):
        direct = []

    ranked = modes_matching.rank_items(query, pool, ("name", "path"), limit=limit)
    if direct:
        ranked = direct + [e for e in ranked if e.path != direct[0].path]
    return ranked[:limit]
