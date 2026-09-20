# CODING TASK — PLETHORA MJOLNIR v2: Raycast-Tier Launcher & Production Hardening

> Paste everything below this line into your coding-mode agent.
> Target machine: Windows 11 · Python 3.13 · repo already exists and works.

---

## 0. ROLE & MISSION

You are a senior Python + PySide6 engineer. Upgrade the existing project at
`C:\plethora-mjolnir` into a **production-grade, visually stunning Windows
productivity launcher** matching Raycast / macOS Spotlight standards, and harden
the backend against **concurrency locks** and **indexing bloat**.

Work directly in the repo. Preserve all existing functionality (CLI, watcher, web
UI, Tk fallback). Do not rewrite the world — extend and refactor the modules
listed below.

## 1. ENVIRONMENT & EXISTING STATE (already true — do not rebuild)

- Repo: `C:\plethora-mjolnir` (run `python mj.py <cmd>` from the repo root).
- Already implemented and verified: Phase 1 headless core (`index`, `search`),
  Phase 2 watcher (`watch`, watchdog + polling fallback), Phase 3 basic GUI (`ui`),
  plus `serve` (web UI), `stats`, `add`, `remove`.
- Storage: SQLite + **FTS5** (BM25) + **sqlite-vec** (`vec0`, 384-dim) + **RRF**
  fusion. Embeddings: **fastembed** `BAAI/bge-small-en-v1.5` (ONNX, CPU), with
  `sentence-transformers` and stdlib `hashing` fallbacks. Selection order is
  `auto`.
- Installed: `pypdf`, `python-docx`, `watchdog`, `fastembed`, `onnxruntime`,
  `sqlite-vec`, `PySide6`.
- Files that exist today:
  ```
  mj.py  mj.cmd  requirements.txt  pyproject.toml  config.example.json  README.md
  mjolnir/  config.py extract.py chunking.py embed.py store.py
            indexer.py search.py watcher.py webui.py gui.py gui_tk.py cli.py
  examples/ scripts/ tests/ (may not exist yet)
  ```
- Config lives at `%USERPROFILE%\.plethora-mjolnir\config.json` (override dir with
  env `PLETHORA_HOME`). `Config` is a dataclass; `Config.load()` already tolerates
  a UTF-8 BOM. It now also has these fields (keep them): `ignore_gitignore`,
  `max_line_chars`, `ui_width`, `ui_height`, `debounce_ms`, `theme` (dict),
  `bindings` (dict).

## 2. DELIVERABLE FILE MAP (create/modify only these)

| File | Action |
| --- | --- |
| `mjolnir/styles.py` | **NEW** — design tokens + full QSS |
| `mjolnir/ui_components.py` | **NEW** — badges, keycaps, list-item widget, preview HTML |
| `mjolnir/openers.py` | **NEW** — deep-linking / reveal / clipboard |
| `mjolnir/gui.py` | **REWRITE** — dual-pane Raycast-style overlay |
| `mjolnir/store.py` | modify — WAL pragmas |
| `mjolnir/indexer.py` | modify — gitignore engine + junk filter + size/line guards |
| `tests/stress_wal.py`, `tests/check_highdpi.py`, `tests/run_checks.py` | **NEW** |
| `config.example.json`, `README.md` | update |

Do **not** change public APIs of `extract.py`, `chunking.py`, `embed.py`,
`search.py`, `watcher.py`, `webui.py`, or `cli.py` (you may add optional kwargs).

### Frozen interfaces (other code depends on these exact names)

```python
# mjolnir/styles.py
BG="#161618"; BORDER="#2A2A2E"; INPUT_BG="#1C1C1F"; FG="#ECECEC"; FG_MUTED="#8A8A93"
ACCENT="rgba(99,102,241,0.18)"; ACCENT_BORDER="rgba(99,102,241,0.5)"; ACCENT_SOLID="#6366F1"
SHADOW=dict(blur=28, dx=0, dy=8, alpha=115)     # 0.45*255 ≈ 115
CATEGORY_COLORS: dict[str, tuple[str, str]]     # uppercase category -> (fg, bg)
PANEL_QSS: str                                  # full application stylesheet

# mjolnir/ui_components.py
category_of(path_or_ext) -> str
badge_colors(category) -> tuple[str, str]
make_shadow(widget) -> QGraphicsDropShadowEffect
format_size(num_bytes) -> str
format_mtime(ts) -> str
highlight_html(snippet, query) -> str
preview_html(hit: dict) -> str                  # keys: path,name,page,snippet,score,chunk_index
class ResultItemWidget(QWidget):  # ctor(name, path, category, page)
keycaps(items: list[tuple[str,str]]) -> QWidget # ("↵","Open") ...

# mjolnir/openers.py
open_target(path, page=None, line=None) -> str  # "vscode"|"sumatra"|"acrobat"|"default"
reveal(path) -> None
copy_to_clipboard(text) -> bool
```

---

## SECTION 1 — VISUAL & UX OVERHAUL (`mjolnir/gui.py` + the two NEW modules)

Re-architect `python mj.py ui` into a sleek modern overlay.

**1.1 Window anatomy & geometry**
- Frameless + translucent + always-on-top; centered horizontally on the active
  monitor, floating ~18% down from the screen top.
- Default size **760 × 480** px (from `cfg.ui_width` / `cfg.ui_height`).
- Flags: `Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool` and
  `Qt.WA_TranslucentBackground`.
- Outer shadow via `QGraphicsDropShadowEffect`: **blur radius 28**, colour
  `rgba(0,0,0,0.45)` (alpha 115), **y-offset 8**.
- Surface: background `#161618`, 1px solid border `#2A2A2E`, **border-radius 12px**.
  Input area background `#1C1C1F`. Selection accent: translucent indigo
  `rgba(99,102,241,0.18)` fill with `rgba(99,102,241,0.5)` border.

**1.2 Dual-pane layout**
- **Header:** borderless search input (17px, "Segoe UI Variable"/"Segoe UI"/Inter),
  placeholder `"Search documents, code, notes by meaning..."`, with a subtle search
  icon and a small spinner shown while the search worker is busy.
- **Body split ~55% / 45%:**
  - **Left — Results list** (`QListWidget` with `ResultItemWidget` via
    `setItemWidget`): bold 14px `#ECECEC` filename; 11px `#8A8A93` path subtitle
    elided with ellipsis; a category chip (`PDF`,`PY`,`SQL`,`DOCX`,...) with muted
    accent colours; a page/line pill (`p. 2` / `L:45`).
  - **Right — Inspector / live preview**, updating instantly on ↑/↓: file icon,
    full name, size, modified date; a preview box (`preview_html`) with matched
    query tokens highlighted; a metadata bar with a `94% match` score pill and
    chunk index info.
- **Footer status bar:** left = `Indexed: X files · Y chunks | Vector: sqlite-vec (384d)`
  (read live from `Store.stats()`); right = tiny keycap chips
  `[↵] Open  [⇧↵] Reveal  [Ctrl+C] Copy Snippet  [Tab] Actions  [Esc] Close`.

**1.3 Interactivity — zero UI freezing**
- Run query embedding + DB search in a dedicated `QThread` worker; debounce text
  input by **120 ms** (`cfg.debounce_ms`). Typing must be perfectly fluid; drop no
  keystrokes (use a request-id guard so stale results are discarded).
- Keyboard: ↑/↓ navigate, Enter open, Shift+Enter reveal, Ctrl+C copy snippet
  (show a brief "Snippet copied!" toast), Tab quick-action menu, Esc hide,
  Ctrl+R reindex. Hide on focus-out. Keep the system-tray icon + global hotkey
  (Alt+Space, Ctrl+Alt+Space backup) from the existing implementation.

---

## SECTION 2 — BACKEND CONCURRENCY & ROBUSTNESS

**2.1 `store.py` — SQLite WAL + busy timeout.** Immediately after
`sqlite3.connect(...)` in `Store.__init__`, execute:
```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;
```
This guarantees the background watcher can write while the launcher reads, with no
`sqlite3.OperationalError: database is locked`. Keep every existing method intact
(FTS5 + sqlite-vec init must still work).

**2.2 `indexer.py` — recursive ignore engine + junk filter.** In `walk_files`:
- Respect `.gitignore` recursively when a folder is a Git repo (parse root and
  nested `.gitignore`; support `#` comments, `!` negation, leading-slash anchoring,
  trailing-slash = directory, `*` `?` `**`, simple char classes). Pure stdlib —
  no new dependency.
- Always skip these directories: `{".git",".venv","venv","node_modules",
  "__pycache__","dist","build","target",".idea",".vscode","bin","obj"}` and file
  patterns `{"*.tmp","*.log"}`.
- Skip files > **25 MB**, and skip any text file containing a line longer than
  **`cfg.max_line_chars` (1000)** (minified/binary-ish) — log
  `[mjolnir] skip (minified/long line): <path>`.
- Keep incremental mtime+size skipping and pruning of removed files.

**2.3 `openers.py` — precise deep-linking on Enter.**
- Code files (`.py .sql .js .ts .jsx .tsx .java .c .cpp .h .cs .go .rs .rb .php
  .html .css .json .yaml .yml .toml .sh .ps1 .md .r .ipynb`): if VS Code is on
  `PATH` (`shutil.which("code")`), run `code -g "<path>:<line or 1>"`; else
  `os.startfile`.
- PDFs with a matched page: prefer SumatraPDF `["-page", str(page), path]` (check
  `PATH` and common install dirs); else Acrobat via
  `["cmd","/c","start","","/A",f"page={page}",path]` when Acrobat is detected;
  else `os.startfile`.
- Everything else: `os.startfile`.
- `Shift+Enter` → `explorer.exe /select,"<abspath>"`.
- `Ctrl+C` → copy the previewed snippet to the clipboard (tkinter with hidden root,
  fallback to `clip`), never raise; UI shows the toast.

---

## SECTION 3 — VERIFICATION & PACKAGING

1. Update `config.example.json` (and `README.md`) with the new **UI theme** and
   **keyboard binding** fields, plus `ignore_gitignore`, `max_line_chars`,
   `ui_width`, `ui_height`, `debounce_ms`.
2. Automated checks (write and run them):
   - `tests/stress_wal.py` — run the indexer writing to the DB in one thread while a
     searcher queries in another for ~6 s; assert **zero** lock errors; print
     `WAL: N searches, M writer passes, 0 lock errors`; exit non-zero on failure.
   - `tests/check_highdpi.py` — set
     `QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)`
     before creating the `QApplication`; build the launcher with
     `QT_QPA_PLATFORM=offscreen`; assert the window/panel default size is 760×480;
     grab a snapshot; print `HighDPI OK`.
   - `tests/run_checks.py` — import every `mjolnir` module, run both checks, print a
     PASS/FAIL table, exit non-zero on any FAIL.
3. Keep it modular: QSS in `styles.py`, delegate/widgets in `ui_components.py`.
4. Set the high-DPI rounding policy **once, before `QApplication` is constructed**
   (in `gui.py`'s `run_gui`, and in `tests/check_highdpi.py`).

---

## 4. ACCEPTANCE CRITERIA (must all pass)

```powershell
cd C:\plethora-mjolnir
python -c "import sys; sys.path.insert(0,r'C:\plethora-mjolnir'); from mjolnir import store, indexer, openers, styles, ui_components, gui; print('imports ok')"
python mj.py index                                   # rebuild index, no crashes
python mj.py search "restaurant database schema"     # still returns file + page
python tests\run_checks.py                           # PASS/PASS (or explicit SKIP reasons)
$env:QT_QPA_PLATFORM="offscreen"; $env:MJOLNIR_UI_SELFTEST="circuit capacitor report from June"; python mj.py ui
```

- `python mj.py ui` shows a 760×480 dual-pane overlay; Arrow keys update the right
  pane live; Enter opens to line/page where possible; Ctrl+C shows "Snippet copied!".
- No `database is locked` error while the watcher runs and you type rapidly.
- All existing commands (`index`, `search`, `stats`, `watch`, `serve`, `ui`, `add`,
  `remove`) still work.

## 5. CONSTRAINTS

- Python 3.13, Windows. No new third-party dependencies (stdlib + PySide6 + the
  already-installed list only).
- All files UTF-8. No `errors="ignore"`/`gbk`/`latin-1` fallbacks for source text.
- Public APIs of untouched modules stay stable.
- Keep the code modular, documented, and under ~400 lines per file where practical.
- If a piece genuinely cannot be done, implement the rest and list the gap.

## 6. DEFINITION OF DONE

The repo at `C:\plethora-mjolnir` builds, indexes, searches, and launches the new
dual-pane overlay; `tests\run_checks.py` passes; the WAL stress test reports zero
lock errors; `config.example.json` documents the theme and bindings. Report the
exact commands you ran and their output.
