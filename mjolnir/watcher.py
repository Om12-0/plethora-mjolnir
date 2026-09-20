"""Background watching.

Uses `watchdog` when available (instant, event-driven). Falls back to a polling
loop otherwise. Both routes debounce bursts of filesystem events so that saving a
file in an editor triggers exactly one re-index.
"""
from __future__ import annotations

import os
import threading
import time
from typing import Iterable, Set

from .indexer import Indexer, walk_files


class _DebouncedWorker:
    def __init__(self, indexer: Indexer, debounce: float, log=print):
        self.indexer = indexer
        self.debounce = debounce
        self.log = log
        self._pending: Set[str] = set()
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None

    def submit(self, paths: Iterable[str]):
        with self._lock:
            self._pending.update(os.path.abspath(p) for p in paths)
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(self.debounce, self._flush)
            self._timer.daemon = True
            self._timer.start()

    def _flush(self):
        with self._lock:
            pending = list(self._pending)
            self._pending.clear()
        if not pending:
            return
        try:
            counters = self.indexer.index_paths(pending)
            changed = {k: v for k, v in counters.items() if v}
            if changed:
                self.log(f"[watch] {len(pending)} change(s) -> {changed}")
        except Exception as exc:  # never let a watcher thread die
            self.log(f"[watch] error while indexing: {exc}")


def _interesting(path: str, extensions: Iterable[str], excludes: Iterable[str]) -> bool:
    name = os.path.basename(path)
    if name.startswith((".", "~$")):
        return False
    if os.path.splitext(path)[1].lower() not in {e.lower() for e in extensions}:
        return False
    parts = {p.lower() for p in os.path.abspath(path).split(os.sep)}
    return not (parts & {e.lower() for e in excludes})


def watch(cfg, store, embedder, log=print):
    indexer = Indexer(cfg, store, embedder, log=log)
    worker = _DebouncedWorker(indexer, cfg.watch_debounce, log=log)

    log("[mjolnir] initial index pass ...")
    counters = indexer.index_all()
    log(f"[mjolnir] initial index done: {counters}")
    log(f"[mjolnir] watching {len(cfg.roots)} root(s). Ctrl+C to stop.")

    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        log("[mjolnir] watchdog not installed -> polling mode "
            f"(every {cfg.watch_interval}s). Install with:  pip install watchdog")
        return _poll_loop(cfg, indexer, worker, log)

    class Handler(FileSystemEventHandler):
        def on_any_event(self, event):
            if event.is_directory:
                return
            for raw in (getattr(event, "src_path", None), getattr(event, "dest_path", None)):
                if raw and _interesting(raw, cfg.extensions, cfg.excludes):
                    # covers create / modify / move / delete (delete -> prune)
                    worker.submit([raw])

    observer = Observer()
    handler = Handler()
    scheduled = 0
    for root in cfg.roots:
        root = os.path.abspath(root)
        if os.path.isdir(root):
            observer.schedule(handler, root, recursive=True)
            scheduled += 1
    observer.start()
    if scheduled == 0:
        log("[mjolnir] no valid roots to watch; check config.")
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
    return 0


def _poll_loop(cfg, indexer: Indexer, worker, log):
    snapshot = {}
    while True:
        try:
            current = {}
            for path in walk_files(cfg.roots, cfg.extensions, cfg.excludes):
                try:
                    st = os.stat(path)
                except OSError:
                    continue
                current[path] = (st.st_mtime, st.st_size)
            changed = [p for p, sig in current.items() if snapshot.get(p) != sig]
            removed = [p for p in snapshot if p not in current]
            if changed or removed:
                worker.submit(changed + removed)
            snapshot = current
        except Exception as exc:
            log(f"[watch] poll error: {exc}")
        time.sleep(cfg.watch_interval)
