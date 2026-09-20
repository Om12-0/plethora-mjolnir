# PLETHORA MJOLNIR

A **local, background file indexer** with **natural-language retrieval** and an
**Alfred-style floating launcher**. Ask *"circuit capacitor report from June"* or
*"restaurant database schema"* and jump straight to the exact **file and page** —
no cloud, no upload, no exact-filename guessing.

Built in three phases:

| Phase | What | Status |
| --- | --- | --- |
| **1** | Headless search core (Python CLI) | ✅ `mj.py index` / `mj.py search` |
| **2** | Background file watcher (`watchdog`, incremental) | ✅ `mj.py watch` |
| **3** | Floating launcher GUI (PySide6, global hotkey, tray) | ✅ `mj.py ui` |

> Everything runs offline. The only network call ever made is the one-time model
> download if you enable neural embeddings.

---

## Why it exists

Windows Search and Spotlight match **filenames and metadata**, not meaning. Ask for
"the capacitor lab report" and they return nothing because the file is called
`PHY2049_Lab3_final_v2.pdf`. MJOLNIR reads the *contents*, chunks them, embeds them,
and ranks by meaning.

---

## Install

```powershell
cd C:\plethora-mjolnir

# 1. (recommended) isolated environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. dependencies (PDF/DOCX extractors, watcher, dense embeddings, GUI)
pip install -r requirements.txt

# 3. create config
python mj.py init
```

`requirements.txt` includes: `pypdf`, `python-docx`, `watchdog`, `fastembed` +
`onnxruntime` (dense ONNX embeddings), `sqlite-vec` (fast KNN), and `PySide6` (GUI).
Everything degrades gracefully if a piece is missing — the core needs only the
Python standard library.

Or run the one-shot setup:

```powershell
.\scripts\install.ps1     # venv + deps + config
```

---

## Use it

| Goal | Command |
| --- | --- |
| Build / refresh the index | `python mj.py index` |
| Search from the terminal | `python mj.py search "restaurant database schema"` |
| **Floating launcher** | `python mj.py ui` → press **Alt+Space** |
| Launcher without PySide6 | `python mj.py ui --tk` |
| Local web UI | `python mj.py serve` → <http://127.0.0.1:8765> |
| Watch folders forever | `python mj.py watch` |
| Add a folder to the roots | `python mj.py add "D:\Uni\Semester 5"` |
| Index health | `python mj.py stats` |

Search modes: `--mode hybrid` (default), `--mode keyword` (BM25 only),
`--mode semantic` (vectors only). Add `--json` for scriptable output.

Put `C:\plethora-mjolnir` on your `PATH` and the bundled `mj.cmd` lets you run
`mj index`, `mj search "..."`, `mj ui`, `mj watch`.

### The floating launcher (Phase 3 — Raycast-style dual pane)

- **Alt+Space** (or **Ctrl+Alt+Space**) toggles a centred, frameless, always-on-top
  overlay (760×480 default, floating ~18% down from the screen top).
- Left pane: results list with filename, elided path, category chip (PDF, PY, SQL…),
  page/line pill and a **1–9 quick-jump badge** on the top nine hits. Right pane:
  live inspector with file size, modified date, highlighted snippet preview and two
  **capsules** (e.g. `96% match` · `Chunk 2/5 · p. 1`).
- Live results as you type (debounced ~120 ms, `debounce_ms`); embedding + DB search
  runs in a dedicated worker thread so typing never freezes.
- **↑ / ↓** move (preview updates live) · **Enter** open file (VS Code `code -g
  file:line` for code, SumatraPDF/Acrobat at the matched page for PDFs) ·
  **Shift+Enter** reveal in Explorer · **Ctrl+C** copy snippet ("Snippet copied!"
  toast) · **Esc** hide · **Ctrl+R** re-index now.
- **Tab** or **→** opens the **Action Panel** (below); **Alt+1 … Alt+9** runs the
  default action on that row instantly, without arrowing down.
- The window is a three-page `QStackedWidget` (document search / action panel /
  clipboard history), so switching views never rebuilds a page.
- **Prefix modes** — one box, five behaviours: `?` or `find` (documents), `open`
  (Start Menu + PATH launcher), `calc` or `=` (calculator), `>` (terminal command)
  and `cb` (clipboard history). The footer keycaps follow the active mode.
- **Alt+Shift+C** (or the tray menu) opens the clipboard history from anywhere.
- On show it picks the screen under the mouse cursor and centres itself there, 18%
  from the top; High-DPI scaling uses `PassThrough` rounding.
- Footer shows `Indexed: X files · Y chunks | Vector: sqlite-vec (384d)` live from
  `Store.stats()` plus keycap hints.
- Hides itself when it loses focus; lives in the system tray with a right-click menu
  (the tray icon is painted from the theme tokens, so a themed config recolours it).

### Action Panel (Tab / →)

Nine keyboard-indexed actions for the highlighted result — press the digit, click the
row, or `↑`/`↓` then `Enter`. `Esc` or `←` goes back to the search list.

| Key | Action | What it does |
| --- | ------ | ------------ |
| 1 | Open Default | `os.startfile` (the shell decides) |
| 2 | Open With… | inline submenu of the handlers that exist on this machine (VS Code, Notepad, SumatraPDF, Edge/Chrome) plus “Choose another app…” → the real Windows dialog (`rundll32 shell32.dll,OpenAs_RunDLL`) |
| 3 | Reveal in File Explorer | `explorer.exe /select,"<abspath>"` |
| 4 | Copy Full File Path | clipboard + toast |
| 5 | Copy Matched Chunk | the matched snippet + toast |
| 6 | Open Containing Terminal | Windows Terminal `wt -d <dir>` when installed, else `powershell -NoExit -Command Set-Location -LiteralPath <dir>` |
| 7 | Deep-Link to Editor / Page | `code -g path:line` for code, `-page N` for PDFs |
| 8 | Re-index This File | forces a single-file re-chunk + re-embed through `Indexer` |
| 9 | Delete (Recycle Bin) | Win32 `SHFileOperationW` with `FOF_ALLOWUNDO` — always a recycle, never a hard delete; the index is pruned afterwards |

All of it lives in `mjolnir/actions.py` (Qt-free: pure functions + a registry behind an
injectable `ActionContext`), so the panel is exercised headlessly with
`ActionContext(dry_run=True)` — see `tests/check_phase_a.py`.

### Prefix modes (one box, five behaviours)

The parsing rules live in `mjolnir/modes.py` (Qt-free, so they are unit-tested
headlessly). Word prefixes are matched as whole words — `finder` is still a document
search — and anything without a prefix is the default hybrid search.

| You type | Mode | What happens |
| --- | ---- | ------------ |
| `report from june`, `? report`, `find report` | documents | Semantic + BM25 hybrid search over the index (the default) |
| `open chrome` | launcher | Ranks `*.lnk` / `*.url` shortcuts from **both** Start Menu folders (per-user `%APPDATA%` + all-users `%PROGRAMDATA%`) and executables on `PATH`; `Enter` opens, `Shift+Enter` reveals, `Tab` opens the action panel. The scan is cached (`ttl` 300 s) so typing never re-walks the disk |
| `calc 2 ** 10`, `= 45 * 1.18` | calculator | Result shown in the list **and** the inspector; `Enter` copies it (toast). Grammar: `+ - * / // % **`, unary ±, and `sqrt sin cos tan log log10 exp abs round min max pow` with `pi` / `e`. Anything else is a friendly error, never a traceback |
| `> ipconfig /flushdns` | terminal | Shows the exact command line and the shell it will use; **nothing runs until you press Enter**, and it then opens in Windows Terminal (`wt`) or PowerShell (`-NoExit`) |
| `cb invoice` | clipboard | Fuzzy search over the clipboard history (below) |

`=` / `calc` never touches Python's dynamic execution: the string is parsed with
`ast` and walked node by node, so only numeric literals, the whitelisted operators
and the whitelisted functions survive.

### Clipboard history (Alt+Shift+C, or `cb`)

- A background daemon thread records every copied **text** into `clipboard.db`
  (SQLite, next to `index.sqlite3` in the `PLETHORA_HOME` config directory).
- Change detection is cheap: one `GetClipboardSequenceNumber()` call per tick
  (`clipboard_poll_ms`, 500 ms default) and the clipboard itself is only read when
  that number moved.
- Consecutive identical copies are de-duplicated, empty/oversized entries are
  skipped (`clipboard_max_chars`) and the history is capped at `clipboard_max_items`
  (500 by default, oldest trimmed first).
- Each row shows a one-line preview, its timestamp and its character count; typing
  filters fuzzily, `↑`/`↓` and `Alt+1…9` move, `Ctrl+C` copies again.
- **Enter copies the item back and auto-pastes it** into the window that had the
  focus: the launcher hides itself, waits for Windows to hand the focus back, then
  synthesises `Ctrl+V` through `SendInput` (with a `keybd_event` fallback). `Esc`
  returns to document search.

---

## Run it in the background

1. **Hidden watcher process**
   ```powershell
   .\scripts\watch-background.ps1      # stop with .\scripts\stop-background.ps1
   ```
2. **Auto-start at logon**
   ```powershell
   .\scripts\install-startup.ps1       # remove with .\scripts\uninstall-startup.ps1
   ```
3. **Manual** — leave `python mj.py watch` running in a terminal.

Launch the floating UI alongside it with `.\scripts\run-ui.ps1` (or add it to the
same startup entry).

---

## How it works

```
 folders you watch
        │
        ▼
 ┌────────────────┐   ┌──────────────────┐   ┌───────────────────┐
 │ 1. WALK        │ → │ 2. EXTRACT       │ → │ 3. CHUNK          │
 │ ext + excludes │   │ pdf/docx/text    │   │ ~1000 char, 150   │
 │ incremental    │   │ (page, text)     │   │ overlap, keeps pg │
 └────────────────┘   └──────────────────┘   └─────────┬─────────┘
                                                       ▼
 ┌────────────────────────────────────────────────────────────────────┐
 │ 4. EMBED   fastembed bge-small-en-v1.5 → 384-dim (ONNX, CPU)       │
 │            fallback: sentence-transformers, then stdlib hashing    │
 └───────────────────────────┬────────────────────────────────────────┘
                             ▼
 ┌────────────────────────────────────────────────────────────────────┐
 │ 5. STORE   SQLite: files + chunks + float32 vectors                │
 │            FTS5 keyword index   +   sqlite-vec KNN (vec0, 384-dim) │
 └────────────────────────────────────────────────────────────────────┘

 your query ──▶ FTS5 / BM25 ranking        ┐
                                           ├─▶ RRF fusion ─▶ top-N (path, page, snippet)
 your query ──▶ sqlite-vec cosine KNN      ┘
```

### Components (mapped to the plan)

| Plan component | Where | Notes |
| --- | --- | --- |
| Folder watcher (`watchdog`) | `mjolnir/watcher.py` | Event-driven, debounced incremental re-index; polling fallback |
| Text parsers | `mjolnir/extract.py` | `pypdf` (page numbers), `python-docx`, raw UTF-8 code/SQL |
| Local embedding model | `mjolnir/embed.py` | `fastembed` + ONNX Runtime, `all-MiniLM-L6-v2` / `bge-small-en-v1.5`, ~15–30 ms/chunk, no API keys |
| Hybrid search | `mjolnir/search.py` | FTS5 BM25 **+** dense vectors fused with **RRF**, top-N < 200 ms |
| Storage | `mjolnir/store.py` | SQLite + **FTS5** + **sqlite-vec** `vec0` table, WAL mode (`journal_mode=WAL`, `busy_timeout=5000`) so the watcher can write while the launcher reads |
| Floating UI | `mjolnir/gui.py`, `mjolnir/gui_tk.py` | PySide6 dual-pane overlay + tray (QSS in `mjolnir/styles.py`, rows/preview in `mjolnir/ui_components.py`, open/reveal/clipboard in `mjolnir/openers.py`); stdlib Tk fallback |
| Action engine | `mjolnir/actions.py` | Qt-free registry of the nine actions behind an injectable `ActionContext` |
| Prefix modes | `mjolnir/modes.py` | Qt-free parsing (`?` / `find` / `open` / `calc` / `=` / `>` / `cb`), the safe `ast` calculator, the cached Start Menu + PATH scan and the terminal argv builder |
| Clipboard history | `mjolnir/clipboard.py` | Qt-free `ClipboardStore` (`clipboard.db`) + `ClipboardWatcher` (Win32 sequence number) + `SendInput` paste |
| Web UI (bonus) | `mjolnir/webui.py` | Local browser search page, 127.0.0.1 only |
| CLI | `mjolnir/cli.py` | `init / index / search / stats / add / remove / watch / serve / ui` |

### Data model (SQLite)

- **files** – `path, mtime, size, ext, indexed_at` (incremental skip via mtime+size)
- **chunks** – `path, page, chunk_index, content, ntok, dim, vec` (float32 blob)
- **fts** – FTS5 mirror for BM25 keyword ranking
- **vec_chunks** – sqlite-vec `vec0(embedding float[384])` for fast KNN

---

## How to customize

| You want to change… | Edit |
| --- | --- |
| Watched folders | `config.json → roots`, or `python mj.py add <folder>` |
| File types | `config.json → extensions` |
| Folders to skip | `config.json → excludes` |
| Chunk size / overlap | `config.json → chunk_chars`, `chunk_overlap` |
| Embedding model | `config.json → embed_backend` (`auto` / `fastembed` / `sentence-transformers` / `hashing`), `fastembed_model` |
| Web port / host | `config.json → web_port`, `web_host` |
| Index location | `config.json → index_path` |
| `.gitignore` handling | `config.json → ignore_gitignore` (repo-root + nested, `!` negation, `* ? **` globs) |
| Minified/binary-ish guard | `config.json → max_line_chars` (default 1000; a longer line skips the file) |
| Launcher size | `config.json → ui_width`, `ui_height` (default 760×480) |
| Keystroke debounce | `config.json → debounce_ms` (default 120 ms) |
| UI look & feel | `config.json → theme` (design tokens mirroring `mjolnir/styles.py`); full QSS lives in `mjolnir/styles.py`, widgets in `mjolnir/ui_components.py` |
| Keyboard hints | `config.json → bindings` (`open`/`reveal`/`copy`/`actions`/`close`/`reindex`/`clipboard`/`paste`) |
| Global hotkey | `HotkeyThread([...])` in `mjolnir/gui.py` (VK + modifier codes) |
| Clipboard history | `config.json → clipboard_enabled` / `clipboard_max_items` / `clipboard_max_chars` / `clipboard_poll_ms` / `clipboard_db` |
| Calculator vocabulary | `ALLOWED_FUNCTIONS` / `ALLOWED_CONSTANTS` in `mjolnir/modes.py` |
| Start Menu / PATH scan | `START_MENU_ENVVARS`, `APP_EXTS`, `SCAN_TTL` in `mjolnir/modes.py` |

After changing `extensions`, `roots`, or the embedding backend, run
`python mj.py index --rebuild` once.

### Embedding backends

| Backend | Dim | Quality | Requirements |
| --- | --- | --- | --- |
| `fastembed` (default via `auto`) | 384 | Strong semantic | `pip install fastembed onnxruntime` |
| `sentence-transformers` | 384 | Strong semantic | `pip install sentence-transformers` (PyTorch) |
| `hashing` | 512 | Lexical + fuzzy | none (stdlib only) |

`auto` tries fastembed → sentence-transformers → hashing, so it never breaks.

---

## Quality & edge cases covered

- **Incremental indexing** — unchanged files skipped via mtime+size.
- **Deletions & renames** — vanished files pruned automatically.
- **Corrupt / unsupported files** — errors caught per file; a bad file never aborts a run.
- **BOM-tolerant config** — `config.json` saved by Notepad/PowerShell still loads.
- **Encoding robustness** — text tried as utf-8 / utf-16 / cp1252 / latin-1.
- **Oversized files** — skipped above `max_file_mb` (default 25 MB).
- **Minified files** — text files with a line longer than `max_line_chars` (default
  1000) are skipped as bundled/minified; junk dirs (`.git`, `node_modules`,
  `__pycache__`, `dist`, `build`, `bin`, `obj`, …) and `*.tmp`/`*.log` are always
  skipped; `.gitignore` files (root + nested) are honoured.
- **Concurrency** — SQLite WAL + `busy_timeout=5000`; verify with
  `python tests\stress_wal.py`, geometry with `python tests\check_highdpi.py`,
  launcher modes + clipboard with `python tests\check_phase_b.py`,
  everything with `python tests\run_checks.py`.
- **No dynamic execution** — the calculator parses with `ast` and walks the tree;
  a name or function that is not whitelisted is an error, not a lookup.
- **Clipboard privacy** — only text, only locally, in the PLETHORA_HOME directory;
  the watcher compares one integer per tick instead of polling clipboard contents.
- **FTS5 syntax safety** — natural-language queries tokenized + quoted, no crashes.
- **Graceful degradation** — missing FTS5 → vector search only; missing sqlite-vec →
  pure-Python cosine; missing neural model → hashing embedder; missing PySide6 → Tk UI.
- **Local only** — web server binds `127.0.0.1` and is never exposed.
- **Page-level results** — PDF findings report the exact page number.

---

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `PDF support needs 'pypdf'` | `pip install pypdf` |
| `DOCX support needs 'python-docx'` | `pip install python-docx` |
| Watching feels laggy | `pip install watchdog` (else it polls every 5 s) |
| `FTS5 unavailable` warning | Your SQLite lacks FTS5; keyword search degrades, vectors still work |
| UI: `PySide6 is required` | `pip install PySide6`, or run `python mj.py ui --tk` |
| Alt+Space does nothing | Another app owns it — use Ctrl+Alt+Space, or the tray icon |
| First index pauses ~10 s | One-time fastembed model download (~130 MB) |
| No results | `python mj.py index`, then `python mj.py stats` |

---

## Layout

```
plethora-mjolnir/
├── mj.py                 portable launcher
├── mj.cmd                PATH-friendly wrapper
├── requirements.txt
├── pyproject.toml
├── config.example.json
├── scripts/              install / watch-background / run-ui / install-startup
├── examples/
│   ├── make_samples.py   generates sample pdf + docx
│   └── sample_docs/      demo corpus
└── mjolnir/
    ├── config.py  extract.py  chunking.py  embed.py  store.py
    ├── indexer.py  search.py  watcher.py  webui.py
    ├── gui.py  gui_tk.py  cli.py
    ├── actions.py  modes.py  clipboard.py        # Qt-free launcher logic
    ├── styles.py  ui_components.py  openers.py   # launcher visuals + file opening
└── tests/
    ├── stress_wal.py  check_highdpi.py  run_checks.py
    ├── check_phase_a.py  check_phase_b.py
```

## License

Use it however you like. Self-contained and dependency-light by design.
