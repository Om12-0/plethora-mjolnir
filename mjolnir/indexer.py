"""Directory walking + incremental indexing.

The walker is deliberately conservative, because a semantic index is only as
good as the junk you keep out of it:

* VCS / build / cache directories are never descended into
  (:data:`ALWAYS_SKIP_DIRS` plus the configured ``excludes``).
* ``.gitignore`` files are honoured - the checkout root's one and any nested
  one, each applying to its own subtree. Supported syntax: ``#`` comments,
  blank lines, ``!`` negation, leading-slash anchoring, a trailing slash for
  "directory only", ``*`` / ``?`` / ``**`` globs and character classes
  (``[abc]``, ``[a-z]``). Later rules override earlier ones.
* ``*.tmp`` / ``*.log`` are always dropped, as is anything over ``max_file_mb``.
* Text files containing a single line longer than ``max_line_chars`` are treated
  as minified (bundled JS, one-line JSON) or binary-ish and skipped.

:func:`walk_files` keeps working with its original three positional arguments;
the new knobs are optional keyword arguments with safe defaults.
"""
from __future__ import annotations

import fnmatch
import os
import re
import time
from typing import Dict, Iterable, List, Optional, Tuple

from . import extract
from .chunking import chunk_pages
from .embed import tokenize
from .store import Store

HIDDEN_PREFIXES = (".", "~$")

#: Directories skipped in every walk, on top of ``Config.excludes``.
ALWAYS_SKIP_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build",
    "target", ".idea", ".vscode", "bin", "obj",
}

#: File name patterns skipped in every walk.
ALWAYS_SKIP_FILE_PATTERNS = ("*.tmp", "*.log")

_READ_CHUNK = 65536


def _looks_hidden(name: str) -> bool:
    return name.startswith(HIDDEN_PREFIXES)


def _log_msg(log, text: str) -> None:
    """Emit *text* through the caller's logger (defaults to ``print``)."""
    try:
        (log or print)(text)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# .gitignore engine
# ---------------------------------------------------------------------------
class _IgnoreRule:
    """One compiled ``.gitignore`` line."""

    __slots__ = ("regex", "negated", "dir_only")

    def __init__(self, regex: "re.Pattern[str]", negated: bool, dir_only: bool):
        self.regex = regex
        self.negated = negated
        self.dir_only = dir_only


def _translate(pattern: str, anchored: bool) -> str:
    """Translate a gitignore glob into a regex source (used with ``fullmatch``).

    ``anchored`` means "the pattern contains a slash, therefore it is relative
    to the directory holding the .gitignore"; otherwise the pattern matches a
    bare name at any depth. In a gitignore glob ``*`` and ``?`` never cross a
    path separator, while ``**/`` matches zero or more leading directories.
    """
    out: List[str] = []
    if not anchored:
        out.append("(?:.*/)?")
    i, n = 0, len(pattern)
    while i < n:
        char = pattern[i]
        if char == "*":
            j = i
            while j < n and pattern[j] == "*":
                j += 1
            if j - i >= 2:                      # '**'
                if j < n and pattern[j] == "/":
                    out.append("(?:.*/)?")
                    j += 1
                else:
                    out.append(".*")
            else:
                out.append("[^/]*")
            i = j
            continue
        if char == "?":
            out.append("[^/]")
            i += 1
            continue
        if char == "[":
            j = i + 1
            if j < n and pattern[j] in "!^":
                j += 1
            if j < n and pattern[j] == "]":     # []abc] -> first ] is literal
                j += 1
            while j < n and pattern[j] != "]":
                j += 1
            if j >= n:                          # unterminated class -> literal [
                out.append(r"\[")
                i += 1
                continue
            body = pattern[i + 1:j]
            if body.startswith("!"):
                body = "^" + body[1:]
            out.append("[" + body.replace("\\", "\\\\") + "]")
            i = j + 1
            continue
        out.append(re.escape(char))
        i += 1
    return "".join(out)


def _parse_gitignore(path: str) -> Optional[List[_IgnoreRule]]:
    """Compile a ``.gitignore``; ``None`` when the file is absent or empty.

    Decoding uses ``utf-8-sig`` with ``errors="replace"``: a .gitignore is
    configuration (often hand-edited on Windows), not indexed source text, and
    one mojibake comment must never abort a walk.
    """
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
            raw = fh.read()
    except OSError:
        return None

    rules: List[_IgnoreRule] = []
    for line in raw.splitlines():
        line = line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        while line.endswith(" ") and not line.endswith("\\ "):   # unescaped
            line = line[:-1]
        line = line.replace("\\ ", " ")
        negated = line.startswith("!")
        if negated:
            line = line[1:]
        elif line.startswith("\\!") or line.startswith("\\#"):
            line = line[1:]
        if not line:
            continue
        dir_only = line.endswith("/")
        if dir_only:
            line = line[:-1]
        anchored = "/" in line
        if line.startswith("/"):
            line = line[1:]
        if not line:
            continue
        try:
            regex = re.compile(_translate(line, anchored))
        except re.error:
            continue
        rules.append(_IgnoreRule(regex, negated, dir_only))
    return rules or None


def _ignore_decision(frames: List[Tuple[str, List[_IgnoreRule]]],
                     abspath: str, is_dir: bool) -> Optional[bool]:
    """Evaluate the ignore stack for one candidate path.

    ``frames`` is an ordered list of ``(directory, rules)`` - outermost first,
    nested ``.gitignore`` files last, exactly git's precedence. Returns ``True``
    (ignored), ``False`` (explicitly re-included by ``!``) or ``None`` (no rule
    matched).
    """
    decision: Optional[bool] = None
    for base_abs, rules in frames:
        rel = os.path.relpath(abspath, base_abs)
        if rel == os.pardir or rel.startswith(os.pardir + os.sep):
            continue                             # outside this .gitignore's tree
        rel_posix = rel.replace(os.sep, "/")
        for rule in rules:
            if rule.dir_only and not is_dir:
                continue                         # files never match "foo/"
            if rule.regex.fullmatch(rel_posix):
                decision = not rule.negated
    return decision


def _git_root(start: str) -> Optional[str]:
    """Nearest ancestor of *start* (inclusive) that looks like a git checkout."""
    current = os.path.abspath(start)
    while True:
        if os.path.exists(os.path.join(current, ".git")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def has_long_line(path: str, max_chars: int) -> bool:
    """True when the file holds a line longer than *max_chars* characters.

    Reads in binary chunks and gives up as soon as the run without a newline
    exceeds the limit, so minified bundles are rejected within a few KB. Any
    I/O problem answers ``False`` (let extraction report the real error).
    """
    if max_chars <= 0:
        return False
    run = 0
    try:
        with open(path, "rb") as fh:
            while True:
                chunk = fh.read(_READ_CHUNK)
                if not chunk:
                    return False
                start = 0
                while True:
                    newline = chunk.find(b"\n", start)
                    if newline == -1:
                        run += len(chunk) - start
                        if run > max_chars:
                            return True
                        break
                    run += newline - start
                    if run > max_chars:
                        return True
                    run = 0
                    start = newline + 1
    except OSError:
        return False


def _file_ok(path: str, name: str, ext: str, max_bytes: int,
              max_line_chars: int, log, size: Optional[int] = None) -> bool:
    """Shared junk / size / minified-line filter (used by the walk and roots)."""
    if any(fnmatch.fnmatchcase(name.lower(), pat)
           for pat in ALWAYS_SKIP_FILE_PATTERNS):
        return False
    if size is None:
        try:
            size = os.stat(path).st_size
        except OSError:
            return False
    if max_bytes and size > max_bytes:
        return False
    if (max_line_chars and ext in extract.TEXT_EXTS
            and has_long_line(path, max_line_chars)):
        _log_msg(log, f"[mjolnir] skip (minified/long line): {path}")
        return False
    return True


def _walk_dir(root: str, exts: set, skip_dirs: set, max_bytes: int,
              max_line_chars: int, ignore_gitignore: bool,
              log) -> List[str]:
    """Depth-first walk of *root* honouring the ignore stack."""
    found: List[str] = []
    frames: List[Tuple[str, List[_IgnoreRule]]] = []
    if ignore_gitignore:
        repo = _git_root(root)
        if repo:
            repo_rules = _parse_gitignore(os.path.join(repo, ".gitignore"))
            if repo_rules:
                frames.append((repo, repo_rules))

    stack: List[Tuple[str, List[Tuple[str, List[_IgnoreRule]]]]] = [(root, frames)]
    while stack:
        dirpath, frames = stack.pop()

        if ignore_gitignore:
            # A .gitignore in a subdirectory only governs that subtree, so it is
            # pushed here rather than pre-scanned for the whole walk.
            local = _parse_gitignore(os.path.join(dirpath, ".gitignore"))
            if local:
                frames = frames + [(dirpath, local)]

        try:
            entries = list(os.scandir(dirpath))
        except OSError:
            continue

        child_dirs: List[str] = []
        for entry in entries:
            name = entry.name
            if _looks_hidden(name):
                continue
            try:
                is_link = entry.is_symlink()
                is_dir = entry.is_dir(follow_symlinks=False)
            except OSError:
                continue
            if is_dir:
                if name.lower() in skip_dirs:
                    continue
                if frames and _ignore_decision(frames, entry.path, True) is True:
                    continue        # pruned: nothing below an ignored dir is walked
                child_dirs.append(entry.path)
                continue
            if is_link and entry.is_dir():
                continue            # never follow directory links / junctions
            ext = os.path.splitext(name)[1].lower()
            if ext not in exts:
                continue
            if frames and _ignore_decision(frames, entry.path, False) is True:
                continue
            try:
                size = entry.stat().st_size
            except OSError:
                continue
            if _file_ok(entry.path, name, ext, max_bytes, max_line_chars,
                        log, size=size):
                found.append(entry.path)

        for child in reversed(child_dirs):        # LIFO stack -> natural order
            stack.append((child, frames))
    return found


def walk_files(roots: Iterable[str], extensions: Iterable[str],
               excludes: Iterable[str], max_file_mb: float = 25.0,
               max_line_chars: int = 1000, ignore_gitignore: bool = True,
               log=None) -> List[str]:
    """Return every indexable file under *roots*.

    ``roots`` may be files or directories. Existing three-argument calls behave
    exactly as before; the extra keyword arguments enable the size and
    minified-line guards and the ``.gitignore`` engine.

    Note: a ``.gitignore`` is honoured wherever it is found, even if the folder
    is not a git checkout (a checkout root's ``.gitignore`` is picked up as
    well), which is the behaviour people expect from an "index my documents"
    tool.
    """
    exts = {str(e).lower() for e in extensions}
    skip_dirs = {str(e).lower() for e in excludes} | ALWAYS_SKIP_DIRS
    max_bytes = int(max_file_mb * 1024 * 1024) if max_file_mb else 0

    found: List[str] = []
    for root in roots:
        root = os.path.abspath(str(root))
        if os.path.isfile(root):                 # a directly named file is taken
            name = os.path.basename(root)
            ext = os.path.splitext(name)[1].lower()
            if ext in exts and _file_ok(root, name, ext, max_bytes,
                                        max_line_chars, log):
                found.append(root)
            continue
        if not os.path.isdir(root):
            continue
        found.extend(_walk_dir(root, exts, skip_dirs, max_bytes,
                               max_line_chars, ignore_gitignore, log))
    return found


class Indexer:
    def __init__(self, cfg, store: Store, embedder, log=print):
        self.cfg = cfg
        self.store = store
        self.embedder = embedder
        self.log = log

    # -- config access (tolerant of configs written before phase A) -----------
    def _max_file_mb(self) -> float:
        return float(getattr(self.cfg, "max_file_mb", 25.0) or 0.0)

    def _max_line_chars(self) -> int:
        return int(getattr(self.cfg, "max_line_chars", 1000) or 0)

    def _ignore_gitignore(self) -> bool:
        return bool(getattr(self.cfg, "ignore_gitignore", True))

    def _walk(self, roots: Iterable[str]) -> List[str]:
        """walk_files with every configured guard switched on."""
        return walk_files(
            roots, self.cfg.extensions, self.cfg.excludes,
            max_file_mb=self._max_file_mb(),
            max_line_chars=self._max_line_chars(),
            ignore_gitignore=self._ignore_gitignore(),
            log=self.log,
        )

    # -- public --------------------------------------------------------------
    def index_all(self, rebuild: bool = False) -> Dict[str, int]:
        started = time.time()
        files = self._walk(self.cfg.roots)
        seen = set()
        counters = {"added": 0, "updated": 0, "skipped": 0, "removed": 0, "failed": 0}
        existing = {r["path"] for r in self.store.all_files()}

        for i, path in enumerate(files, 1):
            seen.add(path)
            outcome = self._index_file(path, rebuild=rebuild,
                                       known_unchanged=not rebuild)
            if outcome == "added" and path not in existing:
                counters["added"] += 1
            elif outcome == "updated":
                counters["updated"] += 1
            elif outcome == "skipped":
                counters["skipped"] += 1
            elif outcome == "failed":
                counters["failed"] += 1
            if i % 25 == 0 or i == len(files):
                self.log(f"  indexed {i}/{len(files)} files ...")

        # prune files that disappeared
        for path in existing - seen:
            self.store.delete_file(path)
            counters["removed"] += 1

        self.store.set_meta("last_index", str(time.time()))
        self.store.set_meta("embedder", getattr(self.embedder, "name", "?"))
        self.store.set_meta("roots", ",".join(self.cfg.roots))
        self.store.set_meta("last_duration", f"{time.time() - started:.1f}s")
        return counters

    def index_paths(self, paths: Iterable[str], rebuild: bool = False) -> Dict[str, int]:
        """Index exactly *paths* (files or folders).

        ``rebuild=True`` forces a re-chunk/re-embed even when the mtime and size
        still match - the launcher's "Re-index This File" action. A path that no
        longer exists is pruned from the store instead.
        """
        counters = {"added": 0, "updated": 0, "skipped": 0, "removed": 0, "failed": 0}
        for path in paths:
            path = os.path.abspath(path)
            if not os.path.exists(path):
                if self.store.get_file(path):
                    self.store.delete_file(path)
                    counters["removed"] += 1
                continue
            if os.path.isdir(path):
                for sub in self._walk([path]):
                    out = self._index_file(sub, rebuild=rebuild,
                                           known_unchanged=not rebuild)
                    counters[out if out in counters else "failed"] += 1
                continue
            out = self._index_file(path, rebuild=rebuild,
                                   known_unchanged=not rebuild)
            counters[out if out in counters else "failed"] += 1
        return counters

    # -- internals -----------------------------------------------------------
    def _index_file(self, path: str, rebuild: bool = False,
                    known_unchanged: bool = True) -> str:
        try:
            st = os.stat(path)
        except OSError:
            return "failed"
        size = st.st_size
        max_file_mb = self._max_file_mb()
        if max_file_mb and size > max_file_mb * 1024 * 1024:
            return "skipped"
        if not rebuild and known_unchanged and self.store.is_fresh(path, st.st_mtime, size):
            return "skipped"
        existed = self.store.get_file(path) is not None

        ext = os.path.splitext(path)[1].lower()
        max_line_chars = self._max_line_chars()
        if (max_line_chars and ext in extract.TEXT_EXTS
                and has_long_line(path, max_line_chars)):
            self.log(f"[mjolnir] skip (minified/long line): {path}")
            return "skipped"

        pages = extract.extract(path)
        chunks = chunk_pages(pages, self.cfg.chunk_chars, self.cfg.chunk_overlap)
        chunks = [c for c in chunks if c[2] and not c[2].startswith("[extraction failed")]
        if not chunks:
            self.store.delete_file(path)
            return "skipped"

        texts = [c[2] for c in chunks]
        vectors = self.embedder.encode(texts)

        payload = []
        for (page, cidx, text), vec in zip(chunks, vectors):
            payload.append((page, cidx, text, len(tokenize(text)), vec))

        self.store.add_file(path, st.st_mtime, size, ext, payload)
        return "updated" if existed else "added"
