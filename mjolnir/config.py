"""Configuration for PLETHORA MJOLNIR.

The config is a small JSON file (default: %USERPROFILE%\\.plethora-mjolnir\\config.json).
Everything can be overridden from the CLI, but the file is what the background
watcher reads, so it is the single source of truth for "what should be indexed".
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List

__version__ = "1.0.3"

# --- sensible defaults -------------------------------------------------------

DEFAULT_EXTENSIONS = [
    # documents
    ".pdf", ".docx", ".txt", ".md", ".rtf",
    # code / data
    ".py", ".ipynb", ".sql", ".java", ".c", ".h", ".cpp", ".hpp", ".cs",
    ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".rb", ".php", ".r",
    ".html", ".css", ".scss", ".yaml", ".yml", ".toml", ".ini",
    ".json", ".csv", ".tex", ".sh", ".ps1", ".bat",
]

DEFAULT_EXCLUDES = [
    ".git", ".svn", ".hg", "node_modules", "__pycache__", ".venv", "venv",
    "env", ".idea", ".vscode", "dist", "build", ".next", ".cache",
    "AppData", ".mypy_cache", ".pytest_cache", "$RECYCLE.BIN",
    "System Volume Information",
]


def _default_theme() -> dict:
    """Theme tokens for the launcher UI (mirrors mjolnir.styles)."""
    return {
        "bg": "#161618",
        "border": "#2A2A2E",
        "input_bg": "#1C1C1F",
        "fg": "#ECECEC",
        "fg_muted": "#8A8A93",
        "accent_solid": "#6366F1",
        # tray / window icon: a 2-stop gradient plus the ink of the "M"
        "icon_gradient": ["#5AC8FA", "#A78BFA"],
        "icon_fg": "#0B0F17",
        "radius": 12,
        "shadow": {"blur": 28, "dx": 0, "dy": 8, "alpha": 115},
    }


def _default_bindings() -> dict:
    """Keyboard bindings shown in the launcher footer / handled by the UI."""
    return {
        "open": "Enter",
        "reveal": "Shift+Enter",
        "copy": "Ctrl+C",
        "actions": "Tab / \u2192",
        "actions_back": "Esc / \u2190",
        "quick_jump": "Alt+1..9",
        "close": "Esc",
        "reindex": "Ctrl+R",
        "clipboard": "Alt+Shift+C",
        "paste": "Enter",
        "hotkey_primary": "Alt+Space",
        "hotkey_fallback_1": "Ctrl+Shift+Space",
        "hotkey_fallback_2": "Alt+Shift+Space",
    }


def default_config_dir() -> Path:
    base = os.environ.get("PLETHORA_HOME")
    if base:
        return Path(base)
    return Path.home() / ".plethora-mjolnir"


def default_config_path() -> Path:
    return default_config_dir() / "config.json"


def default_index_path() -> Path:
    return default_config_dir() / "index.sqlite3"


def default_clipboard_path() -> Path:
    """Clipboard history database - next to the index, in the config dir."""
    return default_config_dir() / "clipboard.db"


def _guess_roots() -> List[str]:
    home = Path.home()
    candidates = [
        home / "Documents",
        home / "Desktop",
        home / "OneDrive" / "Documents",
        home / "OneDrive" / "Desktop",
    ]
    roots = [str(p) for p in candidates if p.exists()]
    return roots or [str(home / "Documents")]


@dataclass
class Config:
    roots: List[str] = field(default_factory=_guess_roots)
    extensions: List[str] = field(default_factory=lambda: list(DEFAULT_EXTENSIONS))
    excludes: List[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDES))
    index_path: str = field(default_factory=lambda: str(default_index_path()))
    max_file_mb: float = 25.0
    chunk_chars: int = 1000
    chunk_overlap: int = 150
    # "fastembed" = fastembed/ONNX (BAAI/bge-small-en-v1.5, 384d)
    # other options: "hashing" | "fastembed" | "sentence-transformers"
    embed_backend: str = "fastembed"
    embed_model: str = "all-MiniLM-L6-v2"                 # sentence-transformers name
    fastembed_model: str = "BAAI/bge-small-en-v1.5"       # 384-dim ONNX model
    watch_interval: float = 5.0          # polling interval when watchdog is absent
    watch_debounce: float = 1.5          # seconds to wait after a burst of changes
    web_host: str = "127.0.0.1"
    web_port: int = 8765

    # -- indexing guards -----------------------------------------------------
    ignore_gitignore: bool = True        # honour .gitignore files while walking
    max_line_chars: int = 1000           # one longer line => minified/binary-ish

    # -- launcher UI (phase A tokens; phase B renders them) -------------------
    ui_width: int = 760
    ui_height: int = 480
    debounce_ms: int = 120               # keystroke debounce for live search
    theme: dict = field(default_factory=_default_theme)
    bindings: dict = field(default_factory=_default_bindings)
    hotkey_chain: List[str] = field(default_factory=lambda: ["Alt+Space", "Ctrl+Shift+Space", "Alt+Shift+Space"])

    # -- clipboard history (phase B) ------------------------------------------
    clipboard_enabled: bool = True       # run the background clipboard watcher
    clipboard_db: str = field(default_factory=lambda: str(default_clipboard_path()))
    clipboard_max_items: int = 500       # history cap; oldest entries are trimmed
    clipboard_max_chars: int = 100000    # skip oversized copies (a whole file)
    clipboard_poll_ms: int = 500         # watcher tick; changes are detected by
                                         # the Win32 clipboard sequence number

    # -- io ------------------------------------------------------------------
    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})

    def save(self, path: str | os.PathLike | None = None):
        target = Path(path) if path else default_config_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return target

    @classmethod
    def load(cls, path: str | os.PathLike | None = None):
        target = Path(path) if path else default_config_path()
        if target.exists():
            # utf-8-sig tolerates a BOM (Notepad / PowerShell Set-Content)
            raw = target.read_text(encoding="utf-8-sig")
            return cls.from_dict(json.loads(raw))
        cfg = cls()
        cfg.save(target)
        return cfg
