"""Text extraction for PDF / DOCX / plain-text (code, sql, notes...) files.

Every extractor returns a list of (page, text) tuples. `page` is a 1-based page
number for paginated formats (PDF) and None for everything else.
"""
from __future__ import annotations

import os
from typing import List, Tuple

Page = Tuple[int | None, str]

# extensions that we read as raw text
TEXT_EXTS = {
    ".txt", ".md", ".markdown", ".rtf", ".log",
    ".py", ".pyw", ".ipynb", ".sql", ".java", ".c", ".h", ".cpp", ".hpp",
    ".cc", ".cs", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".rb", ".php",
    ".r", ".html", ".htm", ".css", ".scss", ".less", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".json", ".jsonl", ".csv", ".tsv", ".tex",
    ".sh", ".bash", ".zsh", ".ps1", ".bat", ".cmd", ".env", ".dockerfile",
    ".graphql", ".proto", ".vue", ".svelte",
}
BINARY_EXTS = {".pdf", ".docx"}


def _read_text(path: str) -> List[Page]:
    for enc in ("utf-8", "utf-8-sig", "utf-16", "cp1252", "latin-1"):
        try:
            with open(path, "r", encoding=enc) as fh:
                return [(None, fh.read())]
        except (UnicodeDecodeError, UnicodeError):
            continue
        except OSError:
            return []
    return []


def _read_pdf(path: str) -> List[Page]:
    try:
        from pypdf import PdfReader
    except ImportError:  # pragma: no cover
        try:
            from PyPDF2 import PdfReader  # type: ignore
        except ImportError:
            raise RuntimeError(
                "PDF support needs 'pypdf'. Install it with:  pip install pypdf"
            )
    reader = PdfReader(path)
    pages: List[Page] = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if text.strip():
            pages.append((i, text))
    return pages


def _read_docx(path: str) -> List[Page]:
    try:
        import docx  # python-docx
    except ImportError:
        raise RuntimeError(
            "DOCX support needs 'python-docx'. Install it with:  pip install python-docx"
        )
    doc = docx.Document(path)
    parts = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                parts.append(" | ".join(cells))
    return [(None, "\n".join(parts))]


def extract(path: str) -> List[Page]:
    """Extract (page, text) pairs from a file. Never raises on unknown types."""
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".pdf":
            return _read_pdf(path)
        if ext in (".docx", ".docm"):
            return _read_docx(path)
        if ext == ".doc":
            raise RuntimeError("Legacy .doc is not supported; save as .docx or .pdf.")
        return _read_text(path)
    except Exception as exc:  # keep the indexer running on one bad file
        return [(-1, f"[extraction failed: {type(exc).__name__}: {exc}]")]
