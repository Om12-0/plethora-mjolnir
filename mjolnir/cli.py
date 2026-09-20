"""Command-line interface for PLETHORA MJOLNIR."""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List

from .config import Config, default_config_path
from .embed import get_embedder
from .indexer import Indexer
from .search import Searcher
from .store import Store


def _load(args) -> Config:
    path = getattr(args, "config", None)
    cfg = Config.load(path)
    if getattr(args, "root", None):
        cfg.roots = list(args.root)
    return cfg


def _open_store(cfg) -> Store:
    os.makedirs(os.path.dirname(os.path.abspath(cfg.index_path)) or ".", exist_ok=True)
    return Store(cfg.index_path)


# ---------------------------------------------------------------------------
def cmd_init(args):
    path = default_config_path()
    if path.exists() and not args.force:
        print(f"Config already exists: {path}\nUse --force to overwrite.")
        return 0
    cfg = Config()
    saved = cfg.save()
    print(f"Created config: {saved}")
    print("Indexed roots:")
    for r in cfg.roots:
        print(f"  - {r}")
    print("\nNext steps:")
    print("  python mj.py index          # build the index")
    print("  python mj.py search \"...\"   # search")
    print("  python mj.py watch          # run in the background")
    return 0


def cmd_index(args):
    cfg = _load(args)
    store = _open_store(cfg)
    embedder = get_embedder(cfg)
    model_name = getattr(cfg, "fastembed_model", "BAAI/bge-small-en-v1.5")
    dim = getattr(embedder, "dim", 384)
    print(f"[mjolnir] Model loaded: {model_name}")
    print(f"[mjolnir] Dimensions: {dim}")
    print(f"[mjolnir] embedder = {embedder.name}")
    print(f"[mjolnir] roots    = {cfg.roots}")
    if dim and store.vec_enabled:
        store.ensure_vec_dim(dim)
        print("[mjolnir] Vectors committed to sqlite-vec table.")
    indexer = Indexer(cfg, store, embedder)
    rebuild = getattr(args, "force", False) or getattr(args, "rebuild", False)
    counters = indexer.index_all(rebuild=rebuild)
    print(f"[mjolnir] done: {counters}")
    store.close()
    return 0


def cmd_search(args):
    cfg = _load(args)
    store = _open_store(cfg)
    embedder = get_embedder(cfg)
    searcher = Searcher(store, embedder)
    hits = searcher.search(args.query, limit=args.limit, mode=args.mode)
    if args.json:
        print(json.dumps([{
            "path": h.path, "page": h.page, "score": h.score,
            "snippet": h.snippet,
        } for h in hits], indent=2))
        return 0
    if not hits:
        print("No matches. Try `python mj.py index` first, or other words.")
        return 1
    print(f"{len(hits)} result(s) for: {args.query!r}\n")
    for i, h in enumerate(hits, 1):
        page = f"  (page {h.page})" if h.page else ""
        print(f"{i:>2}. {h.path}{page}")
        print(f"    score {h.score:.4f}")
        print(f"    {h.snippet}\n")
    store.close()
    return 0


def cmd_stats(args):
    cfg = _load(args)
    store = _open_store(cfg)
    s = store.stats()
    print(f"Index file : {s['db']}")
    print(f"Files      : {s['files']}")
    print(f"Chunks     : {s['chunks']}")
    print(f"Pages      : {s['pages']}")
    print(f"Vec size   : {s['vec_bytes'] / 1048576:.2f} MB")
    print(f"FTS5       : {'on' if s['fts'] else 'off'}")
    print(f"Vectors    : {s.get('vec_backend','?')} (dim {s.get('vec_dim',0)})")
    print(f"Last index : {store.get_meta('last_index') or 'never'}")
    print(f"Embedder   : {store.get_meta('embedder') or '-'}")
    if s["by_ext"]:
        print("By type    :")
        for row in s["by_ext"]:
            print(f"  {row['ext'] or '?':<8} {row['c']}")
    store.close()
    return 0


def cmd_add(args):
    cfg = _load(args)
    added = []
    for p in args.paths:
        ap = os.path.abspath(p)
        if not os.path.isdir(ap):
            print(f"skip (not a folder): {p}")
            continue
        if ap not in cfg.roots:
            cfg.roots.append(ap)
            added.append(ap)
    cfg.save(getattr(args, "config", None))
    print(f"Roots now ({len(cfg.roots)}):")
    for r in cfg.roots:
        print(f"  - {r}")
    if added:
        print("\nRun `python mj.py index` to include the new folder(s).")
    return 0


def cmd_remove(args):
    cfg = _load(args)
    ap = os.path.abspath(args.path)
    before = len(cfg.roots)
    cfg.roots = [r for r in cfg.roots if os.path.abspath(r) != ap]
    cfg.save(getattr(args, "config", None))
    if len(cfg.roots) == before:
        print(f"Not a configured root: {ap}")
    else:
        store = _open_store(cfg)
        print(f"Removed root: {ap}\nRun `python mj.py index` to prune its files.")
        store.close()
    return 0


def cmd_watch(args):
    cfg = _load(args)
    store = _open_store(cfg)
    embedder = get_embedder(cfg)
    from .watcher import watch
    return watch(cfg, store, embedder)


def cmd_serve(args):
    cfg = _load(args)
    if args.port:
        cfg.web_port = args.port
    if args.root:
        cfg.roots = list(args.root)
    store = _open_store(cfg)
    embedder = get_embedder(cfg)
    from .webui import serve
    return serve(cfg, store, embedder, open_browser=not args.no_browser)


def cmd_ui(args):
    cfg = _load(args)
    if args.root:
        cfg.roots = list(args.root)
    store = _open_store(cfg)
    embedder = get_embedder(cfg)
    tray_only = bool(getattr(args, "tray", False))
    if args.tk:
        from .gui_tk import run_gui
        return run_gui(cfg, store, embedder)
    else:
        try:
            from mjolnir_ui import run_gui
            return run_gui(cfg, store, embedder, tray_only=tray_only)
        except Exception:
            try:
                from .gui import run_gui
                return run_gui(cfg, store, embedder)
            except SystemExit as exc:
                print(str(exc))
                print("[mjolnir] falling back to the Tk launcher.")
                from .gui_tk import run_gui
                return run_gui(cfg, store, embedder)


# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mjolnir",
        description="PLETHORA MJOLNIR - local semantic file indexer & search.",
    )
    p.add_argument("--config", help="path to config.json (default: ~/.plethora-mjolnir/config.json)")
    sub = p.add_subparsers(dest="command", required=False)

    sp = sub.add_parser("init", help="create a default config file")
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("index", help="index configured folders")
    sp.add_argument("--rebuild", action="store_true", help="re-index everything from scratch")
    sp.add_argument("--force", action="store_true", help="alias for --rebuild")
    sp.add_argument("--root", action="append", help="override roots (repeatable)")
    sp.set_defaults(func=cmd_index)

    sp = sub.add_parser("search", help="natural-language search")
    sp.add_argument("query")
    sp.add_argument("--limit", type=int, default=10)
    sp.add_argument("--mode", choices=["hybrid", "semantic", "keyword"], default="hybrid")
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--root", action="append")
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("stats", help="show index statistics")
    sp.set_defaults(func=cmd_stats)

    sp = sub.add_parser("add", help="add folder(s) to the watch roots")
    sp.add_argument("paths", nargs="+")
    sp.set_defaults(func=cmd_add)

    sp = sub.add_parser("remove", help="remove a folder from the watch roots")
    sp.add_argument("path")
    sp.set_defaults(func=cmd_remove)

    sp = sub.add_parser("watch", help="index once, then watch folders in the background")
    sp.add_argument("--root", action="append")
    sp.set_defaults(func=cmd_watch)

    sp = sub.add_parser("serve", help="start the local web UI")
    sp.add_argument("--port", type=int)
    sp.add_argument("--no-browser", action="store_true")
    sp.add_argument("--root", action="append")
    sp.set_defaults(func=cmd_serve)

    sp = sub.add_parser("ui", help="floating launcher (Alt+Space overlay)")
    sp.add_argument("--tray", action="store_true", help="start silently in system tray")
    sp.add_argument("--tk", action="store_true", help="use the stdlib Tkinter fallback")
    sp.add_argument("--root", action="append")
    sp.set_defaults(func=cmd_ui)

    return p


def main(argv: List[str] | None = None) -> int:
    if argv is None:
        argv = list(sys.argv[1:])
    if not argv:
        argv = ["ui"]
    elif argv == ["--tray"]:
        argv = ["ui", "--tray"]
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        args.func = cmd_ui
        args.tray = False
        args.tk = False
        args.root = None
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\ninterrupted.")
        return 130
    except Exception as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
