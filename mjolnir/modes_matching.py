"""Fuzzy scoring and text ranking utilities shared across launcher modes. Qt-free."""
from __future__ import annotations

import re
from typing import Any, Iterable, List, Optional, Sequence, Tuple

__all__ = ["fuzzy_score", "rank_items", "one_line"]


def fuzzy_score(needle: str, haystack: Any) -> Optional[int]:
    """Rank needle inside haystack; None when it does not match."""
    text = str(haystack if haystack is not None else "")
    term = str(needle or "")
    if not term:
        return 0
    if not text:
        return None
    low = text.lower()
    index = low.find(term.lower())
    if index != -1:
        score = 1000 + min(len(term), 64)
        if index == 0:
            score += 220
        else:
            score += max(0, 100 - index)
            if not low[index - 1].isalnum():
                score += 60
        return score

    low_term = term.lower()
    position = -1
    first = -1
    gaps = 0
    for char in low_term:
        found = low.find(char, position + 1)
        if found == -1:
            return None
        if first < 0:
            first = found
        else:
            gaps += found - position - 1
        position = found
    return max(1, 400 + 4 * len(low_term) - min(gaps, 200) - min(first, 100))


def _field(item: Any, key: Any) -> str:
    if key is None:
        return str(item if item is not None else "")
    if callable(key):
        try:
            return str(key(item) or "")
        except Exception:
            return ""
    return str(getattr(item, str(key), "") or "")


def rank_items(term: str, items: Iterable, keys: Sequence = (None,),
               limit: Optional[int] = None) -> List:
    """Filter and rank items by fuzzy_score, best match first."""
    needle = str(term or "").strip()
    scored: List[Tuple[int, int, Any]] = []
    fields = tuple(keys) or (None,)
    for index, item in enumerate(items or []):
        best: Optional[int] = None
        for depth, key in enumerate(fields):
            score = fuzzy_score(needle, _field(item, key))
            if score is None:
                continue
            score -= depth * 60
            if best is None or score > best:
                best = score
        if best is not None:
            scored.append((-best, index, item))
    scored.sort(key=lambda row: (row[0], row[1]))
    ranked = [item for _, _, item in scored]
    return ranked[:limit] if limit else ranked


def one_line(text: Any, width: int = 160) -> str:
    """Collapse whitespace/newlines into a single elided line."""
    collapsed = re.sub(r"\s+", " ", str(text if text is not None else "")).strip()
    limit = max(8, int(width))
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[:limit - 1].rstrip() + "…"
