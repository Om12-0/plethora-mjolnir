"""WAL concurrency stress: writer (indexer) vs reader (searcher), ~6 seconds.

The background watcher must be able to write while the launcher reads without
``sqlite3.OperationalError: database is locked``. Both sides open their own
connection to the same DB file (exactly like watcher + launcher processes do);
the WAL + busy_timeout pragmas in :mod:`mjolnir.store` absorb the overlap.

Prints: ``WAL: <N> searches, <M> writer passes, 0 lock errors``.
Exit code is non-zero on any lock error or unexpected failure.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DURATION_S = 6.0


def _build_corpus(root: str, n: int = 12) -> None:
    os.makedirs(root, exist_ok=True)
    for i in range(n):
        with open(os.path.join(root, f"doc_{i:02d}.txt"), "w", encoding="utf-8") as fh:
            fh.write(
                f"Mjolnir stress document {i}.\n"
                f"The restaurant database schema stores menus and orders.\n"
                f"Capacitor circuit lab report number {i} with resistor values.\n"
                f"Unique token alpha{i}beta for retrieval.\n"
            )


def main() -> int:
    from mjolnir.config import Config
    from mjolnir.embed import HashingEmbedder
    from mjolnir.indexer import Indexer
    from mjolnir.search import Searcher
    from mjolnir.store import Store

    tmp = tempfile.mkdtemp(prefix="mjolnir-wal-")
    corpus = os.path.join(tmp, "docs")
    _build_corpus(corpus)
    db_path = os.path.join(tmp, "index.sqlite3")

    cfg = Config(
        roots=[corpus],
        extensions=[".txt"],
        excludes=[],
        index_path=db_path,
        embed_backend="hashing",
    )
    embedder = HashingEmbedder()

    # Prime the index once so readers have something to query.
    prime = Store(db_path)
    Indexer(cfg, prime, embedder, log=lambda *_: None).index_all(rebuild=True)
    prime.close()

    store_w = Store(db_path)
    store_r = Store(db_path)
    indexer = Indexer(cfg, store_w, embedder, log=lambda *_: None)
    searcher = Searcher(store_r, embedder)

    stop = time.time() + DURATION_S
    lock_errors = 0
    searches = 0
    passes = 0
    state_lock = threading.Lock()

    queries = [
        "restaurant database schema",
        "capacitor circuit report",
        "stress document retrieval",
        "resistor values",
        "menus and orders",
    ]

    def writer():
        nonlocal passes, lock_errors
        i = 0
        while time.time() < stop:
            try:
                # Touch a file each pass so there is real write work to do.
                p = os.path.join(corpus, f"doc_{i % 12:02d}.txt")
                with open(p, "a", encoding="utf-8") as fh:
                    fh.write(f"\nheartbeat pass {i}.\n")
                indexer.index_all()
                with state_lock:
                    passes += 1
            except sqlite3.OperationalError as exc:
                if "locked" in str(exc).lower():
                    with state_lock:
                        lock_errors += 1
                else:
                    raise
            i += 1

    def reader():
        nonlocal searches, lock_errors
        i = 0
        while time.time() < stop:
            try:
                searcher.search(queries[i % len(queries)], limit=5)
                with state_lock:
                    searches += 1
            except sqlite3.OperationalError as exc:
                if "locked" in str(exc).lower():
                    with state_lock:
                        lock_errors += 1
                else:
                    raise
            i += 1

    tw = threading.Thread(target=writer, daemon=True)
    tr = threading.Thread(target=reader, daemon=True)
    tw.start()
    tr.start()
    tw.join(timeout=DURATION_S + 15)
    tr.join(timeout=DURATION_S + 15)

    try:
        store_w.close()
    except Exception:
        pass
    try:
        store_r.close()
    except Exception:
        pass

    print(f"WAL: {searches} searches, {passes} writer passes, {lock_errors} lock errors")
    if lock_errors:
        print("[FAIL] database-is-locked errors observed under WAL concurrency.")
        return 1
    if not searches or not passes:
        print("[FAIL] no work completed (searches=%d passes=%d)." % (searches, passes))
        return 1
    print("[PASS] no lock errors during concurrent read/write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
