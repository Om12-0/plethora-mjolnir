"""Zero-dependency floating launcher (Tkinter fallback).

Use this when PySide6 is not installed:  python mj.py ui --tk
Same behaviour (centred overlay, live results, Enter opens, Shift+Enter reveals,
global Alt+Space hotkey on Windows), just with the stdlib GUI toolkit.
"""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading

from .search import Searcher

MOD_ALT, MOD_CONTROL = 0x0001, 0x0002
WM_HOTKEY = 0x0312
VK_SPACE = 0x20


def _hotkey_thread(out: "queue.Queue"):
    if not sys.platform.startswith("win"):
        return
    import ctypes
    import ctypes.wintypes as wt

    user32 = ctypes.windll.user32
    ids = []
    for i, (mods, vk) in enumerate([(MOD_ALT, VK_SPACE), (MOD_CONTROL | MOD_ALT, VK_SPACE)]):
        if user32.RegisterHotKey(None, 9100 + i, mods, vk):
            ids.append(9100 + i)
    if not ids:
        return
    msg = wt.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
        if msg.message == WM_HOTKEY:
            out.put("toggle")


def _open_path(path):
    if sys.platform.startswith("win"):
        os.startfile(path)  # noqa
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def _reveal_path(path):
    if sys.platform.startswith("win"):
        subprocess.Popen(["explorer", "/select,", os.path.abspath(path)])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", path])
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(path)])


def run_gui(cfg, store, embedder, log=print) -> int:
    import tkinter as tk

    searcher = Searcher(store, embedder)
    events: "queue.Queue" = queue.Queue()
    threading.Thread(target=_hotkey_thread, args=(events,), daemon=True).start()

    BG, FG, MUT = "#0f1622", "#e8eefc", "#7f93b5"
    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.configure(bg=BG)
    W, H = 760, 78
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    x, y = (sw - W) // 2, int(sh * 0.22)
    root.geometry(f"{W}x{H}+{x}+{y}")

    frame = tk.Frame(root, bg=BG, highlightbackground="#2b3a55", highlightthickness=1)
    frame.pack(fill="both", expand=True)
    entry = tk.Entry(frame, font=("Segoe UI", 20), bg=BG, fg=FG, insertbackground=FG,
                     relief="flat", highlightthickness=0)
    entry.pack(fill="x", padx=16, pady=(12, 6))
    entry.insert(0, "")
    listbox = tk.Listbox(frame, font=("Consolas", 10), bg="#131a26", fg="#c8d5ee",
                         relief="flat", highlightthickness=0, selectbackground="#1d2b42",
                         selectforeground="#ffffff", activestyle="none")
    status = tk.Label(frame, text="", font=("Segoe UI", 9), bg=BG, fg=MUT, anchor="w")

    hits = []

    def hide(_=None):
        root.withdraw()

    def show():
        root.deiconify()
        root.lift()
        root.attributes("-topmost", True)
        entry.focus_set()
        entry.select_range(0, "end")

    def do_search(*_):
        nonlocal hits
        q = entry.get().strip()
        listbox.delete(0, "end")
        hits = []
        if not q:
            root.geometry(f"{W}x{H}+{x}+{y}")
            status.pack_forget()
            listbox.pack_forget()
            return
        hits = searcher.search(q, limit=8)
        for h in hits:
            page = f"  ·  p.{h.page}" if h.page else ""
            listbox.insert("end", f" {os.path.basename(h.path)}{page}   —   {h.snippet[:96]}")
        root.geometry(f"{W}x{H + min(max(len(hits),1),8)*26 + 22}+{x}+{y}")
        listbox.pack(fill="both", expand=True, padx=12, pady=(0, 4))
        status.pack(fill="x", padx=14, pady=(0, 8))
        if hits:
            listbox.selection_clear(0, "end")
            listbox.selection_set(0)
            status.config(text=f"{len(hits)} result(s)   ↑↓  Enter open  Shift+Enter folder  Esc hide")
        else:
            status.config(text="No matches — still indexing, or try other words.")

    def open_selected(event=None):
        sel = listbox.curselection()
        if sel and sel[0] < len(hits):
            _open_path(hits[sel[0]].path)
            hide()

    def reveal_selected(event=None):
        sel = listbox.curselection()
        if sel and sel[0] < len(hits):
            _reveal_path(hits[sel[0]].path)

    def move(delta):
        if not hits:
            return
        sel = listbox.curselection()
        row = (sel[0] if sel else 0) + delta
        row = max(0, min(row, len(hits) - 1))
        listbox.selection_clear(0, "end")
        listbox.selection_set(row)
        listbox.see(row)

    entry.bind("<KeyRelease>", do_search)
    entry.bind("<Return>", open_selected)
    entry.bind("<Shift-Return>", reveal_selected)
    entry.bind("<Escape>", hide)
    entry.bind("<Down>", lambda e: (move(1), "break"))
    entry.bind("<Up>", lambda e: (move(-1), "break"))
    listbox.bind("<Double-Button-1>", open_selected)
    root.bind("<FocusOut>", lambda e: root.after(150, hide))

    def pump():
        try:
            while True:
                events.get_nowait()
                if root.winfo_viewable():
                    hide()
                else:
                    show()
        except queue.Empty:
            pass
        root.after(80, pump)

    pump()
    log("[mjolnir] Tk launcher ready. Alt+Space toggles it; Esc hides.")

    selftest = os.environ.get("MJOLNIR_UI_SELFTEST")
    if selftest:
        show()
        entry.delete(0, "end")
        entry.insert(0, selftest)
        do_search()
        root.after(2500, root.destroy)
    else:
        show()
    try:
        root.mainloop()
    except Exception:
        pass
    if selftest:
        print(f"[selftest] results for {selftest!r}: {len(hits)}")
    return 0
