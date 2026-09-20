"""SQLite storage: file metadata, chunks, float vectors, and an FTS5 index."""
from __future__ import annotations

import array
import sqlite3
import time
from contextlib import contextmanager
from typing import Dict, Iterable, List, Optional, Tuple

SCHEMA = """
CREATE TABLE IF NOT EXISTS files(
    path       TEXT PRIMARY KEY,
    mtime      REAL,
    size       INTEGER,
    ext        TEXT,
    indexed_at REAL
);
CREATE TABLE IF NOT EXISTS chunks(
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    path        TEXT,
    page        INTEGER,
    chunk_index INTEGER,
    content     TEXT,
    ntok        INTEGER,
    dim         INTEGER,
    vec         BLOB
);
CREATE INDEX IF NOT EXISTS idx_chunks_path ON chunks(path);
CREATE INDEX IF NOT EXISTS idx_chunks_page ON chunks(path, page);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
"""

# Concurrency: the watcher writes while the launcher reads.  WAL lets readers
# (searches) run without blocking the writer, NORMAL is the recommended
# durability level for WAL, and busy_timeout absorbs the remaining overlap
# instead of raising "database is locked".
PRAGMAS = (
    "PRAGMA journal_mode = WAL",
    "PRAGMA synchronous = NORMAL",
    "PRAGMA busy_timeout = 5000",
)


def apply_pragmas(conn: sqlite3.Connection) -> None:
    """Best-effort pragmas.

    ``journal_mode`` returns a row (sqlite echoes the mode actually chosen) and
    can legitimately fail - read-only databases, network/removable filesystems -
    so every pragma is swallowed: a degraded mode is fine, a crash is not.
    """
    for statement in PRAGMAS:
        try:
            conn.execute(statement)
        except sqlite3.Error:
            pass


def pack_vector(vec: List[float]) -> bytes:
    return array.array("f", vec).tobytes()


def unpack_vector(blob: bytes) -> array.array:
    arr = array.array("f")
    arr.frombytes(blob)
    return arr


class Store:
    def __init__(self, path: str, default_dim: Optional[int] = None):
        self.path = path
        self.conn = sqlite3.connect(path, check_same_thread=False)
        apply_pragmas(self.conn)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.vec_enabled = self._load_sqlite_vec()
        self.vec_dim: Optional[int] = None
        self.fts_enabled = self._init_fts()
        if self.vec_enabled:
            self._init_vec_table()
            if self.vec_dim is None and default_dim:
                self.ensure_vec_dim(default_dim)
        self.conn.commit()

    # -- helpers -------------------------------------------------------------
    @contextmanager
    def _tx(self):
        yield
        self.conn.commit()

    def _load_sqlite_vec(self) -> bool:
        try:
            import sqlite_vec

            self.conn.enable_load_extension(True)
            sqlite_vec.load(self.conn)
            self.conn.enable_load_extension(False)
            return True
        except Exception as exc:
            import logging
            logging.getLogger("mjolnir.store").error("Failed to load sqlite-vec extension: %s", exc)
            return False

    def _init_vec_table(self):
        stored = self.get_meta("vec_dim")
        if stored:
            self.vec_dim = int(stored)
            self.conn.execute(
                f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks "
                f"USING vec0(embedding float[{self.vec_dim}])"
            )

    def ensure_vec_dim(self, dim: int) -> bool:
        """Make sure vec_chunks exists with the right dimension.

        Returns True when the sqlite-vec table is usable for this dim.
        """
        if not self.vec_enabled:
            return False
        if self.vec_dim == dim:
            return True
        if self.vec_dim is not None and self.vec_dim != dim:
            # embedding backend changed -> rebuild the vector table
            self.conn.execute("DROP TABLE IF EXISTS vec_chunks")
            self.conn.commit()
        self.conn.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks "
            f"USING vec0(embedding float[{dim}])"
        )
        self.vec_dim = dim
        self.set_meta("vec_dim", str(dim))
        # re-populate any rows we already have stored as blobs
        for row in self.conn.execute("SELECT id, vec, dim FROM chunks"):
            if row["dim"] == dim:
                self.conn.execute(
                    "INSERT OR REPLACE INTO vec_chunks(rowid, embedding) VALUES(?,?)",
                    (row["id"], row["vec"]),
                )
        self.conn.commit()
        return True

    def _init_fts(self) -> bool:
        try:
            self.conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS fts "
                "USING fts5(content, tok, tokenize='unicode61')"
            )
            self.conn.commit()
            return True
        except sqlite3.OperationalError as exc:
            print(f"[mjolnir] FTS5 unavailable ({exc}); keyword search degraded.")
            return False

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass

    # -- meta ----------------------------------------------------------------
    def get_meta(self, key: str, default: Optional[str] = None) -> Optional[str]:
        row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set_meta(self, key: str, value: str):
        self.conn.execute(
            "INSERT INTO meta(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self.conn.commit()

    # -- files ---------------------------------------------------------------
    def get_file(self, path: str):
        return self.conn.execute(
            "SELECT path, mtime, size, ext FROM files WHERE path=?", (path,)
        ).fetchone()

    def all_files(self) -> List[sqlite3.Row]:
        return list(self.conn.execute("SELECT path, mtime, size, ext FROM files"))

    def is_fresh(self, path: str, mtime: float, size: int) -> bool:
        row = self.get_file(path)
        return bool(row) and abs(row["mtime"] - mtime) < 1e-6 and row["size"] == size

    def chunk_count(self, path: str) -> int:
        """How many chunks the index holds for *path* (0 when unknown)."""
        row = self.conn.execute(
            "SELECT COUNT(*) c FROM chunks WHERE path=?", (path,)).fetchone()
        return int(row["c"]) if row else 0

    def delete_file(self, path: str):
        ids = [r["id"] for r in self.conn.execute(
            "SELECT id FROM chunks WHERE path=?", (path,))]
        if ids:
            if self.fts_enabled:
                self.conn.executemany("DELETE FROM fts WHERE rowid=?", [(i,) for i in ids])
            if self.vec_enabled and self.vec_dim:
                self.conn.executemany(
                    "DELETE FROM vec_chunks WHERE rowid=?", [(i,) for i in ids])
        self.conn.execute("DELETE FROM chunks WHERE path=?", (path,))
        self.conn.execute("DELETE FROM files WHERE path=?", (path,))
        self.conn.commit()

    def add_file(self, path: str, mtime: float, size: int, ext: str,
                 chunks: Iterable[Tuple[Optional[int], int, str, int, List[float]]]):
        chunks = list(chunks)
        self.delete_file(path)
        vec_ok = bool(chunks) and self.ensure_vec_dim(len(chunks[0][4]))
        for page, cidx, content, ntok, vec in chunks:
            cur = self.conn.execute(
                "INSERT INTO chunks(path,page,chunk_index,content,ntok,dim,vec) "
                "VALUES(?,?,?,?,?,?,?)",
                (path, page, cidx, content, ntok, len(vec), pack_vector(vec)),
            )
            rowid = cur.lastrowid
            if self.fts_enabled:
                self.conn.execute(
                    "INSERT INTO fts(rowid, content, tok) VALUES(?,?,?)",
                    (rowid, content, " ".join(_tok(content))),
                )
            if vec_ok:
                self.conn.execute(
                    "INSERT INTO vec_chunks(rowid, embedding) VALUES(?,?)",
                    (rowid, pack_vector(vec)),
                )
        self.conn.execute(
            "INSERT INTO files(path,mtime,size,ext,indexed_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(path) DO UPDATE SET mtime=excluded.mtime, "
            "size=excluded.size, ext=excluded.ext, indexed_at=excluded.indexed_at",
            (path, mtime, size, ext, time.time()),
        )
        self.conn.commit()

    # -- search primitives ---------------------------------------------------
    def iter_vectors(self):
        return self.conn.execute(
            "SELECT id, path, page, chunk_index, ntok, dim, vec FROM chunks"
        )

    def chunks_by_ids(self, ids: List[int]) -> Dict[int, sqlite3.Row]:
        if not ids:
            return {}
        marks = ",".join("?" for _ in ids)
        rows = self.conn.execute(
            f"SELECT id, path, page, chunk_index, content, ntok FROM chunks "
            f"WHERE id IN ({marks})", ids,
        )
        return {r["id"]: r for r in rows}

    def fts_top(self, match: str, limit: int = 200) -> List[Tuple[int, float]]:
        if not self.fts_enabled or not match:
            return []
        try:
            rows = self.conn.execute(
                "SELECT rowid, bm25(fts) AS score FROM fts WHERE tok MATCH ? "
                "ORDER BY score LIMIT ?", (match, limit),
            )
            # bm25() is negative; more negative = better. Flip sign.
            return [(r["rowid"], -float(r["score"])) for r in rows]
        except sqlite3.OperationalError:
            return []

    def knn_ids(self, qvec: List[float], k: int = 200) -> List[int]:
        """sqlite-vec KNN; returns rowids best-first (or [] if unavailable)."""
        if not self.vec_enabled or self.vec_dim != len(qvec):
            return []
        try:
            rows = self.conn.execute(
                "SELECT rowid FROM vec_chunks WHERE embedding MATCH ? "
                "ORDER BY distance LIMIT ?",
                (pack_vector(qvec), k),
            )
            return [r["rowid"] for r in rows]
        except sqlite3.OperationalError:
            return []

    def stats(self) -> Dict[str, object]:
        files = self.conn.execute("SELECT COUNT(*) c FROM files").fetchone()["c"]
        chunks = self.conn.execute("SELECT COUNT(*) c FROM chunks").fetchone()["c"]
        pages = self.conn.execute(
            "SELECT COUNT(DISTINCT path || '#' || IFNULL(page,-1)) c FROM chunks"
        ).fetchone()["c"]
        by_ext = list(self.conn.execute(
            "SELECT ext, COUNT(*) c FROM files GROUP BY ext ORDER BY c DESC"
        ))
        size = self.conn.execute("SELECT COALESCE(SUM(LENGTH(vec)),0) b FROM chunks").fetchone()["b"]
        return {"files": files, "chunks": chunks, "pages": pages, "vec_bytes": size,
                "by_ext": by_ext, "fts": self.fts_enabled, "db": self.path,
                "vec_backend": "sqlite-vec" if self.vec_enabled else "python-cosine",
                "vec_dim": self.vec_dim or 0}


def _tok(text: str) -> List[str]:
    import re
    return re.findall(r"[A-Za-z0-9_]+", text.lower())
