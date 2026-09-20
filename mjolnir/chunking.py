"""Split extracted text into overlapping chunks, preserving page numbers."""
from __future__ import annotations

from typing import List, Tuple

Page = Tuple[int | None, str]


def chunk_text(text: str, chunk_chars: int = 1000, overlap: int = 150) -> List[str]:
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= chunk_chars:
        return [text]

    chunks: List[str] = []
    n = len(text)
    start = 0
    while start < n:
        end = min(n, start + chunk_chars)
        if end < n:
            window = text[start:end]
            # prefer to break on a paragraph, then a line, then a space
            br = window.rfind("\n\n")
            if br < chunk_chars * 0.5:
                br = window.rfind("\n")
            if br < chunk_chars * 0.5:
                br = window.rfind(" ")
            if br > chunk_chars * 0.5:
                end = start + br
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return chunks


def chunk_pages(
    pages: List[Page], chunk_chars: int = 1000, overlap: int = 150
) -> List[Tuple[int | None, int, str]]:
    """Return (page, chunk_index_within_file, text) tuples."""
    out: List[Tuple[int | None, int, str]] = []
    idx = 0
    for page, text in pages:
        for piece in chunk_text(text, chunk_chars, overlap):
            out.append((page, idx, piece))
            idx += 1
    return out
