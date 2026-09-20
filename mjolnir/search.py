"""Natural-language search: hybrid keyword (BM25/FTS5) + vector similarity,
fused with Reciprocal Rank Fusion.
"""
from __future__ import annotations

import heapq
import math
import operator
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from .embed import tokenize
from .store import Store, unpack_vector

RRF_K = 60
CANDIDATES = 250
_WORD_RE = re.compile(r"[A-Za-z0-9_]+")


@dataclass
class Hit:
    path: str
    page: Optional[int]
    score: float
    snippet: str
    chunk_index: int = 0
    matched: List[str] = field(default_factory=list)


def _fts_match(query: str) -> str:
    raw_tokens = _WORD_RE.findall(query)
    if not raw_tokens:
        return ""
    clauses: List[str] = []
    for raw in raw_tokens:
        low = raw.lower()
        clauses.append(f'"{low}"*')
        clauses.append(f'"{low}"')
        if len(raw) >= 4:
            parts = re.findall(r"[A-Z]+(?=[A-Z][a-z]|\b)|[A-Z]?[a-z]+|[0-9]+", raw)
            if len(parts) > 1:
                for p in parts:
                    if len(p) >= 2:
                        clauses.append(f'"{p.lower()}"*')
            elif raw.isupper() and len(raw) >= 6:
                for split_len in (3, 4):
                    for i in range(0, len(raw) - split_len + 1, split_len):
                        sub = raw[i:i + split_len].lower()
                        if len(sub) >= 3:
                            clauses.append(f'"{sub}"*')
    seen = set()
    unique = [c for c in clauses if not (c in seen or seen.add(c))]
    return " OR ".join(unique)


def _snippet(content: str, query: str, width: int = 260) -> str:
    """Best window around the first query token; falls back to the head."""
    terms = [t for t in _WORD_RE.findall(query.lower()) if len(t) > 1]
    low = content.lower()
    pos = -1
    for term in terms:
        pos = low.find(term)
        if pos != -1:
            break
    if pos == -1:
        return re.sub(r"\s+", " ", content[:width]).strip()
    start = max(0, pos - width // 3)
    end = min(len(content), start + width)
    text = re.sub(r"\s+", " ", content[start:end]).strip()
    return ("..." if start > 0 else "") + text + ("..." if end < len(content) else "")


def _cosine(query_vec: Sequence[float], doc_vec) -> float:
    # vectors are L2-normalised at index time; query vector is normalised here
    return sum(map(operator.mul, query_vec, doc_vec))


class Searcher:
    def __init__(self, store: Store, embedder):
        self.store = store
        self.embedder = embedder

    def search(self, query: str, limit: int = 10,
               mode: str = "hybrid") -> List[Hit]:
        query = (query or "").strip()
        if not query:
            return []

        rank_lists: List[List[int]] = []

        # 1. keyword ranking (FTS5 BM25)
        if mode in ("hybrid", "keyword") and self.store.fts_enabled:
            fts = self.store.fts_top(_fts_match(query), CANDIDATES)
            rank_lists.append([cid for cid, _ in fts])

        # 2. vector ranking (sqlite-vec KNN, else pure-python cosine)
        if mode in ("hybrid", "semantic"):
            qvec = self.embedder.encode([query])[0]
            knn = self.store.knn_ids(qvec, CANDIDATES)
            if knn:
                rank_lists.append(knn)
            else:
                top = heapq.nlargest(
                    CANDIDATES,
                    ((_cosine(qvec, unpack_vector(row["vec"])), row["id"])
                     for row in self.store.iter_vectors()),
                    key=lambda x: x[0],
                )
                rank_lists.append([cid for score, cid in top if score > 0.0])

        if not rank_lists:
            return []

        # 3. Reciprocal Rank Fusion
        fused: Dict[int, float] = {}
        for ranks in rank_lists:
            for rank, cid in enumerate(ranks):
                fused[cid] = fused.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)

        best = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[:limit]
        ids = [cid for cid, _ in best]
        rows = self.store.chunks_by_ids(ids)

        hits: List[Hit] = []
        for cid, score in best:
            row = rows.get(cid)
            if not row:
                continue
            hits.append(Hit(
                path=row["path"],
                page=row["page"],
                score=score,
                snippet=_snippet(row["content"], query),
                chunk_index=row["chunk_index"] or 0,
                matched=sorted(set(tokenize(query)) & set(tokenize(row["content"]))),
            ))
        return hits
