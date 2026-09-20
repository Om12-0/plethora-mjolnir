"""Embedding backends.

Two backends ship with MJOLNIR:

* ``hashing`` (default) - pure standard library. A signed hashing vectorizer over
  word unigrams, word bigrams and character trigrams, L2-normalised. Requires
  no downloads and no heavy dependencies; gives strong lexical + fuzzy matching.

* ``sentence-transformers`` - real local neural embeddings (great semantic
  quality). Optional: ``pip install sentence-transformers``. The first use
  downloads the model once, then runs fully offline.
"""
from __future__ import annotations

import hashlib
import logging
import math
import os
import re
import sys
import tempfile
from typing import List, Sequence

DIM = 512
_WORD_RE = re.compile(r"[A-Za-z0-9_]+")


def tokenize(text: str) -> List[str]:
    return _WORD_RE.findall(text.lower())


def _hash(token: str, dim: int):
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    value = int.from_bytes(digest, "big")
    index = value % dim
    sign = 1.0 if (value >> 63) & 1 else -1.0
    return index, sign


class HashingEmbedder:
    backend = "hashing"

    def __init__(self, dim: int = DIM):
        self.dim = dim
        self.name = f"hashing-{dim}"

    def _one(self, text: str) -> List[float]:
        vec = [0.0] * self.dim
        low = text.lower()
        words = _WORD_RE.findall(low)
        features = list(words)
        features.extend(a + "_" + b for a, b in zip(words, words[1:]))
        # character trigrams over whitespace-collapsed text (fuzzy matching)
        norm = re.sub(r"\s+", " ", low)
        if len(norm) > 2:
            features.extend(norm[i:i + 3] for i in range(len(norm) - 2))
        for feat in features:
            idx, sign = _hash(feat, self.dim)
            vec[idx] += sign
        norm2 = math.sqrt(sum(x * x for x in vec))
        if norm2 > 0.0:
            vec = [x / norm2 for x in vec]
        return vec

    def encode(self, texts: Sequence[str]) -> List[List[float]]:
        return [self._one(t) for t in texts]


class SentenceTransformerEmbedder:
    backend = "sentence-transformers"

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer  # heavy import

        self.model = SentenceTransformer(model_name)
        self.dim = int(self.model.get_sentence_embedding_dimension())
        self.name = f"st:{model_name}"

    def encode(self, texts: Sequence[str]) -> List[List[float]]:
        arr = self.model.encode(list(texts), normalize_embeddings=True)
        return [list(map(float, row)) for row in arr]


def get_fastembed_cache_dir() -> str | None:
    candidates: List[str] = []
    if getattr(sys, "frozen", False):
        if hasattr(sys, "_MEIPASS"):
            candidates.append(os.path.join(sys._MEIPASS, "fastembed_cache"))
        candidates.append(os.path.join(os.path.dirname(sys.executable), "fastembed_cache"))
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates.append(os.path.join(repo_root, "fastembed_cache"))
    localapp = os.environ.get("LOCALAPPDATA", "")
    if localapp:
        candidates.append(os.path.join(localapp, "Programs", "Plethora Mjolnir", "fastembed_cache"))
    candidates.append(os.path.join(tempfile.gettempdir(), "fastembed_cache"))
    for c in candidates:
        if os.path.isdir(c):
            return c
    return None


class FastEmbedEmbedder:
    """Dense ONNX embeddings via fastembed (ONNX Runtime, CPU, no GPU needed).

    Default model ``BAAI/bge-small-en-v1.5`` is 384-dimensional, ~15-30 ms per
    chunk on CPU and <100 MB RAM. The model is downloaded once, then runs fully
    offline.
    """

    backend = "fastembed"

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5", cache_dir: str | None = None):
        from fastembed import TextEmbedding

        if cache_dir is None:
            cache_dir = get_fastembed_cache_dir()
        self.cache_dir = cache_dir
        kwargs = {"model_name": model_name}
        if cache_dir:
            kwargs["cache_dir"] = cache_dir
        self.model = TextEmbedding(**kwargs)
        probe = next(iter(self.model.embed(["dimension probe"])))
        self.dim = int(len(probe))
        if self.dim == 0:
            raise RuntimeError(f"FastEmbed model {model_name} returned 0-dimensional embedding!")
        self.name = f"fastembed:{model_name}"

    def encode(self, texts: Sequence[str]) -> List[List[float]]:
        return [list(map(float, vec)) for vec in self.model.embed(list(texts))]


def get_embedder(cfg) -> object:
    backend = getattr(cfg, "embed_backend", "fastembed")
    if backend == "auto":
        backend = "fastembed"

    def _try_fastembed():
        return FastEmbedEmbedder(getattr(cfg, "fastembed_model", "BAAI/bge-small-en-v1.5"))

    def _try_st():
        return SentenceTransformerEmbedder(cfg.embed_model)

    order = {
        "hashing": [],
        "fastembed": [_try_fastembed],
        "sentence-transformers": [_try_st],
    }.get(backend, [_try_fastembed, _try_st])

    for factory in order:
        try:
            embedder = factory()
            if hasattr(embedder, "dim") and embedder.dim > 0:
                return embedder
            logging.getLogger("mjolnir.embed").error("%s resolved to 0d embedding!", factory.__name__)
        except Exception as exc:  # noqa: BLE001
            logging.getLogger("mjolnir.embed").error("%s unavailable: %s", factory.__name__, exc)
            if backend == "fastembed":
                raise RuntimeError(f"FastEmbed 384d initialization failed: {exc}") from exc
            print(f"[mjolnir] {factory.__name__} unavailable ({type(exc).__name__}: "
                  f"{exc}); trying next backend.")
    if backend not in ("hashing",):
        print("[mjolnir] using built-in hashing embedder (no neural model).")
    return HashingEmbedder()
