"""Core non-GUI acceptance checks for Phase B (modes, calculator, open index, clipboard)."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from mjolnir import clipboard as cb, modes
from mjolnir.clipboard import ClipboardStore, ClipboardWatcher
from mjolnir.config import Config, default_clipboard_path, default_config_dir


def run_phase_b_core(check, _read, tmp) -> None:
    modes_src = _read("mjolnir/modes.py")
    clipboard_src = _read("mjolnir/clipboard.py")

    # ---------------------------------------------------------------- 2.3 routing
    print("2.3 prefix routing (Qt-free parser)")
    routing = [
        ("? capacitor", modes.MODE_SEARCH, "capacitor"),
        ("find capacitor", modes.MODE_SEARCH, "capacitor"),
        ("open chrome", modes.MODE_OPEN, "chrome"),
        ("calc 2 ** 10", modes.MODE_CALC, "2 ** 10"),
        ("= 45 * 1.18", modes.MODE_CALC, "45 * 1.18"),
        ("=45*1.18", modes.MODE_CALC, "45*1.18"),
        ("> ipconfig /flushdns", modes.MODE_SHELL, "ipconfig /flushdns"),
        (">ping 1.1.1.1", modes.MODE_SHELL, "ping 1.1.1.1"),
        ("cb", modes.MODE_CLIPBOARD, ""),
        ("cb invoice", modes.MODE_CLIPBOARD, "invoice"),
    ]
    for text, expected_mode, expected_term in routing:
        parsed = modes.parse(text)
        check(f"parse({text!r}) -> {expected_mode}",
              parsed.mode == expected_mode and parsed.term == expected_term,
              f"mode={parsed.mode} term={parsed.term!r}")
    default = modes.parse("capacitor report june")
    check("an unprefixed query keeps the default search mode",
          default.mode == modes.MODE_SEARCH
          and default.term == "capacitor report june" and default.prefix == "",
          f"mode={default.mode} term={default.term!r}")
    check("an empty box is a search, not a mode",
          modes.parse("").mode == modes.MODE_SEARCH and modes.parse("   ").empty)
    check("word prefixes are whole-word only ('finder' stays a search)",
          modes.parse("finder").mode == modes.MODE_SEARCH
          and modes.parse("finder").term == "finder"
          and modes.parse("cbx").mode == modes.MODE_SEARCH)
    check("the parsed query reports its own mode flags",
          modes.parse("cb").is_clipboard and modes.parse("> x").is_shell
          and modes.parse("= 1").is_calc and modes.parse("open x").is_open
          and modes.parse("?").is_search)
    check("the prefix that matched is reported",
          (modes.parse("= 1").prefix, modes.parse("calc 1").prefix,
           modes.parse("? x").prefix) == ("=", "calc", "?"))
    check("every mode has a label and a placeholder",
          all(modes.mode_label(m) and modes.placeholder(m) for m in modes.MODES))
    check("the self-test routing table covers every mode",
          {mode for _text, mode in modes.PREFIX_EXAMPLES} == set(modes.MODES),
          str(sorted({mode for _t, mode in modes.PREFIX_EXAMPLES})))
    check("modes.py is Qt-free (unit-testable headlessly)",
          "PySide6" not in modes_src and "QtWidgets" not in modes_src)

    # ------------------------------------------------------------- 2.3 calculator
    print("2.3 calculator (ast grammar, no dynamic execution)")
    cases = [
        ("= 45 * 1.18", 53.1),
        ("45 * 1.18", 53.1),
        ("sqrt(256)", 16.0),
        ("2 ** 10", 1024),
        ("log10(1000)", 3.0),
        ("round(3.14159, 2)", 3.14),
        ("(2 + 3) * 4", 20.0),
        ("-5 + 2", -3.0),
        ("sin(pi / 2)", 1.0),
        ("max(3, 7, 5)", 7.0),
        ("pow(2, 8)", 256.0),
        ("abs(-4.5)", 4.5),
        ("min(2, 3) + exp(0)", 3.0),
        ("10 % 3", 1.0),
        ("7 // 2", 3.0),
    ]
    for expression, expected in cases:
        result = modes.calculate(expression)
        check(f"calc {expression!r} == {expected}",
              result.ok and abs(float(result.value) - expected) < 1e-9,
              f"ok={result.ok} value={result.value!r} error={result.error!r}")
    check("calc '= 45 * 1.18' formats as 53.1",
          modes.calculate("= 45 * 1.18").text == "53.1",
          modes.calculate("= 45 * 1.18").text)
    check("calc 'sqrt(256)' shows a whole number",
          modes.calculate("sqrt(256)").text == "16")
    check("calc '2 ** 10' shows an integer, not 1024.0",
          modes.calculate("2 ** 10").text == "1024")

    bad_inputs = ["", "   ", "2 +", "= ", "1/0", "sqrt(-1)", "os.system('calc')",
                  "__import__('os')", "open('x')", "x = 1", "import os",
                  "2 ** 999999", "9 ** 9 ** 9", '"abc" + 1', "[1,2][0]",
                  "(lambda: 1)()", "2 if 1 else 3", "$(calc)", "1 +"]
    for expression in bad_inputs:
        try:
            result = modes.calculate(expression)
        except Exception as exc:      # the whole point: it must never raise
            check(f"calc {expression!r} never raises", False,
                  f"{type(exc).__name__}: {exc}")
            continue
        check(f"calc {expression!r} -> friendly error, no raise",
              result.ok is False and bool(result.error) and result.value is None
              and not result.text,
              f"ok={result.ok} error={result.error!r}")
    check("a division by zero is reported, not raised",
          "zero" in modes.calculate("1/0").error.lower())
    check("an unknown function is refused by the whitelist",
          "unknown" in modes.calculate("__import__('os')").error.lower())
    check("attribute access is refused (no os.system)",
          "call" in modes.calculate("os.system('calc')").error.lower()
          or "function" in modes.calculate("os.system('calc')").error.lower(),
          modes.calculate("os.system('calc')").error)
    check("a runaway exponent is bounded",
          "large" in modes.calculate("2 ** 999999").error.lower(),
          modes.calculate("2 ** 999999").error)
    check("format_number keeps integers and trims float noise",
          modes.format_number(1024) == "1024"
          and modes.format_number(53.099999999999994) == "53.1",
          modes.format_number(53.099999999999994))
    check("the function whitelist is exactly the documented set",
          set(modes.ALLOWED_FUNCTIONS) == {
              "sqrt", "sin", "cos", "tan", "log", "log10", "exp",
              "abs", "round", "min", "max", "pow"},
          str(sorted(modes.ALLOWED_FUNCTIONS)))
    check("the constant whitelist is pi and e",
          set(modes.ALLOWED_CONSTANTS) == {"pi", "e"})

    calculator_src = modes_src.split("def calculate", 1)[1]
    check("the calculator source contains no bare 'eval(' at all",
          "eval(" not in modes_src and "eval(" not in calculator_src)
    check("the calculator parses with ast instead of executing the string",
          "ast.parse" in calculator_src and "import ast" in modes_src
          and "_eval_node" in calculator_src)
    codegen = [line.strip() for line in modes_src.splitlines()
               if ("compile(" in line or "exec(" in line)
               and "re.compile(" not in line]
    check("no compile()/exec() of user input anywhere in the parser",
          not codegen, str(codegen[:2]))
    check("clipboard.py is Qt-free (usable from a plain thread)",
          "PySide6" not in clipboard_src and "QtWidgets" not in clipboard_src)

    # ------------------------------------------------- 2.3 open: fake Start Menu
    print("2.3 'open' index (fake Start Menu + fake PATH)")
    roaming = os.path.join(tmp, "AppData", "Roaming")
    programs = os.path.join(roaming, "Microsoft", "Windows", "Start Menu", "Programs")
    deep = os.path.join(programs, "Vendor Tools", "deep")
    fake_apps = os.path.join(tmp, "fakebin")
    for folder in (programs, os.path.join(programs, "Google"),
                   os.path.join(programs, "Vendor Tools"), deep, fake_apps):
        os.makedirs(folder, exist_ok=True)
    shortcuts = [
        os.path.join(programs, "Notepad.lnk"),
        os.path.join(programs, "Google", "Google Chrome.lnk"),
        os.path.join(programs, "Vendor Tools", "Chrome Remote Desktop.lnk"),
        os.path.join(deep, "Widget Runner.url"),
    ]
    for path in shortcuts:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("")
    with open(os.path.join(programs, "notes.txt"), "w", encoding="utf-8") as fh:
        fh.write("not a shortcut\n")
    for name in ("widget.exe", "notepad.exe", "widget-helper.cmd"):
        with open(os.path.join(fake_apps, name), "w", encoding="utf-8") as fh:
            fh.write("")

    found = modes.scan_start_menu(roots=[programs])
    names = sorted(entry.name for entry in found)
    check("the Start Menu scan finds .lnk and .url recursively",
          names == ["Chrome Remote Desktop", "Google Chrome", "Notepad",
                    "Widget Runner"],
          str(names))
    check("non-shortcut files next to them are ignored",
          all(entry.path.lower().endswith((".lnk", ".url")) for entry in found))
    check("every shortcut keeps its absolute path",
          all(os.path.isabs(entry.path) for entry in found))

    entries = modes.scan_targets(roots=[programs], pathenv=fake_apps,
                                 use_cache=False)
    check("scan_targets merges Start Menu shortcuts and PATH executables",
          {e.kind for e in entries} == {"shortcut", "app"} and len(entries) == 7,
          str([(e.name, e.kind) for e in entries]))
    check("PATH entries keep their executable",
          sorted(e.name for e in entries if e.kind == "app")
          == ["notepad", "widget", "widget-helper"])
    check("shortcuts are ranked before PATH apps",
          [e.kind for e in entries][:4] == ["shortcut"] * 4)

    first = modes.scan_targets(roots=[programs], pathenv=fake_apps)
    second = modes.scan_targets(roots=[programs], pathenv=fake_apps,
                                now=time.monotonic())
    check("a second scan is served from cache (no re-walk of the disk)",
          len(first) == len(second) == len(entries) == 7)
    modes.invalidate_cache()
    os.remove(os.path.join(programs, "Notepad.lnk"))
    third = modes.scan_targets(roots=[programs], pathenv=fake_apps, use_cache=False)
    check("use_cache=False (and invalidate_cache) picks up a changed tree",
          len(third) == len(entries) - 1, f"{len(third)} vs {len(entries)}")

    ranked = modes.search_targets("chrome", entries=entries)
    check("'open chrome' ranks the Chrome shortcuts first",
          [e.name for e in ranked[:2]] == ["Chrome Remote Desktop", "Google Chrome"],
          str([e.name for e in ranked]))
    check("'open chrome' drops the entries that cannot match at all",
          not any(e.name in ("notepad", "widget", "widget-helper") for e in ranked),
          str([e.name for e in ranked]))
    widget_matches = modes.search_targets("widget", entries=entries)
    check("'open widget' offers both the shortcut and the PATH apps",
          [e.name for e in widget_matches][:3]
          == ["Widget Runner", "widget", "widget-helper"],
          str([e.name for e in widget_matches]))
    check("an empty term lists targets instead of nothing",
          len(modes.search_targets("", entries=entries, limit=3)) == 3)
    direct = modes.search_targets(tmp, entries=entries)
    check("a term that is a real path is offered as a direct target",
          bool(direct) and direct[0].kind == "path"
          and direct[0].path == os.path.abspath(tmp),
          str(direct[0]) if direct else "none")
    check("rank_items prefers a name match over a folder match",
          modes.rank_items("nr", [modes.Entry("x", r"C:\nr\thing.txt"),
                                  modes.Entry("nr", r"C:\other\nr.txt")])[0].name
          == "nr")
    check("fuzzy_score is a subsequence matcher with a None miss",
          modes.fuzzy_score("gch", "Google Chrome") is not None
          and modes.fuzzy_score("zzz", "Google Chrome") is None
          and modes.fuzzy_score("", "anything") == 0)
    check("one_line collapses whitespace for row previews",
          modes.one_line("a\n\nb\tc") == "a b c"
          and modes.one_line("y" * 40, 10).endswith("\u2026"))
    check("start_menu_roots expands %APPDATA%/$PROGRAMDATA% and keeps the order",
          modes.start_menu_roots(env={"APPDATA": roaming, "PROGRAMDATA": ""},
                                 isdir=os.path.isdir) == [programs],
          str(modes.start_menu_roots(env={"APPDATA": roaming}, isdir=os.path.isdir)))
    check("a Start Menu root whose variable is unset is skipped",
          modes.start_menu_roots(env={}, isdir=os.path.isdir) == [])

    # --------------------------------------------------------- 2.3 > terminal
    print("2.3 '>' terminal command plan")
    wt_plan = modes.shell_plan("ipconfig /flushdns", which=lambda _n: r"C:\wt.exe")
    check("a command prefers Windows Terminal when present",
          wt_plan.shell == "wt" and wt_plan.argv[0] == r"C:\wt.exe"
          and wt_plan.argv[1] == "-d", str(wt_plan.argv))
    check("-NoExit keeps the output on screen",
          list(wt_plan.argv[-4:]) == ["powershell.exe", "-NoExit", "-Command",
                                      "ipconfig /flushdns"],
          str(wt_plan.argv))
    check("the plan shows the exact command line",
          "ipconfig /flushdns" in wt_plan.display
          and wt_plan.display.startswith("C:\\wt.exe"), wt_plan.display)
    ps_plan = modes.shell_plan("ping 1.1.1.1", which=lambda _n: None)
    check("PowerShell is the fallback",
          ps_plan.shell == "powershell"
          and list(ps_plan.argv) == ["powershell", "-NoExit", "-Command",
                                     "ping 1.1.1.1"],
          str(ps_plan.argv))
    check("an empty command is not runnable",
          not modes.shell_plan("").ok and bool(modes.shell_plan("").error))
    check("an absurdly long command is refused",
          not modes.shell_plan("x" * (modes.MAX_COMMAND_CHARS + 1)).ok)
    check("run_shell refuses a plan that is not ok",
          modes.run_shell(modes.shell_plan(""), spawner=lambda *a, **k: True) is False)
    spawned: list = []
    started = modes.run_shell(ps_plan, spawner=lambda argv, new_console=False:
                              spawned.append((list(argv), new_console)) or True)
    check("run_shell asks for a visible console on the PowerShell fallback",
          started and spawned and spawned[0][1] is True, str(spawned))
    spawned.clear()
    modes.run_shell(wt_plan, spawner=lambda argv, new_console=False:
                    spawned.append((list(argv), new_console)) or True)
    check("Windows Terminal manages its own window (no new console flag)",
          spawned and spawned[0][1] is False, str(spawned))

    # ------------------------------------------------------- 2.4 clipboard store
    print("2.4 clipboard store (temporary databases)")
    db_path = os.path.join(tmp, "clipboard.db")
    store = ClipboardStore(db_path, max_items=500, max_chars=100)
    check("the database is created where it was asked for",
          os.path.isfile(db_path) and store.path == db_path)
    row = store.add("invoice 2026-09 from Acme")
    check("insert returns the new row id",
          isinstance(row, int) and row > 0 and store.count() == 1, str(row))
    check("a consecutive duplicate is dropped",
          store.add("invoice 2026-09 from Acme") is None and store.count() == 1)
    store.add("capacitor report June")
    store.add("invoice 2026-09 from Acme")
    check("a non-consecutive duplicate is kept (history keeps its order)",
          store.count() == 3, str(store.count()))
    check("empty and whitespace-only copies are skipped",
          store.add("") is None and store.add("   \n ") is None
          and store.add(None) is None)
    check("oversized copies are skipped",
          store.add("x" * 101) is None and store.add("x" * 99) is not None)
    items = store.items()
    check("items() is newest-first with a timestamp and a character count",
          [i.text[:7] for i in items][:2] == ["xxxxxxx", "invoice"]
          and all(i.nchars == len(i.text) and i.created_at > 0 for i in items),
          str([(i.text[:8], i.nchars) for i in items]))
    check("a row carries preview + timestamp + character count",
          "chars" in items[0].meta and items[0].when
          and "\u00b7" in items[0].meta, items[0].meta)
    check("the row preview is a single collapsed line",
          (store.add("multi\nline\n\tcopy") is not None)
          and store.items()[0].preview == "multi line copy",
          store.items()[0].preview)
    substring = store.search("capac")
    check("substring search finds the entry",
          [h.text for h in substring] == ["capacitor report June"],
          str([h.text for h in substring]))
    fuzzy = store.search("rprt")
    check("fuzzy search finds it too (subsequence)",
          [h.text for h in fuzzy] == ["capacitor report June"],
          str([h.text for h in fuzzy]))
    check("an empty term lists the newest items",
          [h.text for h in store.search("", limit=2)]
          == [i.text for i in store.items()[:2]])
    check("a miss returns nothing", store.search("zzzzz") == [])
    check("a store can be reopened with the history intact",
          ClipboardStore(db_path).count() == store.count())

    capped = ClipboardStore(os.path.join(tmp, "capped.db"), max_items=5)
    for index in range(8):
        capped.add(f"entry {index}")
    check("the history is capped, the oldest entries trimmed",
          capped.count() == 5 and capped.items()[0].text == "entry 7"
          and capped.items()[-1].text == "entry 3",
          str([i.text for i in capped.items()]))
    check("de-duplication still applies at the cap",
          capped.add("entry 7") is None and capped.count() == 5)
    check("delete removes one row",
          capped.delete(capped.items()[-1].id) and capped.count() == 4)
    check("get() round-trips a row",
          capped.get(capped.items()[0].id).text == "entry 7")
    check("clear empties the history", capped.clear() == 4 and capped.count() == 0)
    check("stats report the database, the cap and the count",
          capped.stats()["db"].endswith("capped.db")
          and capped.stats()["max_items"] == 5 and capped.stats()["items"] == 0)
    check("format_when/format_age render a timestamp",
          bool(cb.format_when(time.time())) and cb.format_age(time.time()) == "just now"
          and cb.format_age(time.time() - 7200) == "2h ago",
          f"{cb.format_when(time.time())} / {cb.format_age(time.time() - 7200)}")
    check("format_when is safe on garbage",
          cb.format_when(None) == "" and cb.format_when("nope") == "")

    print("2.4 clipboard watcher (fake sequence number, fake reader)")
    seq = {"n": 1000}
    text = {"value": "first copy"}
    watch_store = ClipboardStore(os.path.join(tmp, "watch.db"), max_items=50)
    watcher = ClipboardWatcher(watch_store, interval=0.05,
                               sequence=lambda: seq["n"],
                               reader=lambda: text["value"])
    watcher.prime()
    check("an unchanged sequence number reads nothing",
          watcher._poll_once() is None and watch_store.count() == 0)
    seq["n"] += 1
    check("a moved sequence number records exactly one entry",
          watcher._poll_once() is not None and watch_store.count() == 1)
    check("the same sequence number again is a no-op",
          watcher._poll_once() is None and watch_store.count() == 1)
    seq["n"] += 1
    check("the same text under a new sequence number is de-duplicated",
          watcher._poll_once() is None and watch_store.count() == 1)
    seq["n"] += 1
    text["value"] = "second copy"
    check("a genuinely new copy is recorded",
          watcher._poll_once() is not None
          and watch_store.items()[0].text == "second copy")
    check("the watcher counts what it did",
          watcher.polls == 5 and watcher.recorded == 2, str(watcher.stats()))
    no_seq_store = ClipboardStore(os.path.join(tmp, "nosq.db"))
    fallback = ClipboardWatcher(no_seq_store, interval=0.05, sequence=lambda: 0,
                                reader=lambda: text["value"])
    check("without a sequence number it falls back to hashing the text",
          fallback._poll_once() is not None
          and fallback._poll_once() is None and no_seq_store.count() == 1,
          str(fallback.stats()))
    threaded = ClipboardStore(os.path.join(tmp, "threaded.db"))
    seen: list = []
    live = ClipboardWatcher(threaded, interval=0.05, sequence=lambda: seq["n"],
                            reader=lambda: text["value"], on_change=seen.append)
    live.start()
    time.sleep(0.2)
    seq["n"] += 1
    text["value"] = "copied while watching"
    deadline = time.monotonic() + 5.0
    while not seen and time.monotonic() < deadline:
        time.sleep(0.05)
    stopped = live.stop(2.0)
    check("the watcher thread records in the background and stops cleanly",
          bool(seen) and stopped and not live.is_alive(),
          f"seen={seen} stopped={stopped} alive={live.is_alive()}")
    check("a started watcher reports live stats",
          live.stats()["recorded"] >= 1 and live.stats()["interval"] == 0.05)
    check("a watcher that is stopped twice stays stopped",
          live.stop(0.5) and not live.is_alive())

    print("2.4 Win32 clipboard surface")
    sequence = cb.clipboard_sequence()
    check("clipboard_sequence() reports an integer (0 when unavailable)",
          isinstance(sequence, int) and sequence >= 0, str(sequence))
    check("the copy/paste entry points exist and are callable",
          all(callable(fn) for fn in (cb.get_clipboard_text, cb.set_clipboard_text,
                                      cb.paste_ctrl_v, cb.clear_clipboard)))
    check("the paste is SendInput-based with a keybd_event fallback",
          "_send_input_ctrl_v" in clipboard_src
          and "_keybd_event_ctrl_v" in clipboard_src
          and "VK_V" in clipboard_src and "KEYEVENTF_KEYUP" in clipboard_src)
    check("the watcher polls the sequence number, not the clipboard text",
          "GetClipboardSequenceNumber" in clipboard_src
          and "clipboard_sequence" in clipboard_src)
    check("reading the clipboard keeps the 64-bit HANDLE intact",
          "GetClipboardData.restype = ctypes.c_void_p" in clipboard_src
          and "GlobalLock.restype = ctypes.c_void_p" in clipboard_src)
    check("clipboard.db lives next to the index by default",
          default_clipboard_path().name == "clipboard.db"
          and default_clipboard_path().parent == default_config_dir(),
          str(default_clipboard_path()))

    # -------------------------------------------------------------- 2.4 config
    print("2.4 config additions")
    cfg = Config()
    check("clipboard_enabled defaults to True", cfg.clipboard_enabled is True)
    check("clipboard_max_items defaults to 500", cfg.clipboard_max_items == 500)
    check("clipboard_max_chars defaults to 100000", cfg.clipboard_max_chars == 100000)
    check("clipboard_poll_ms has a sane default", cfg.clipboard_poll_ms > 0)
    check("clipboard_db defaults to the config directory",
          Path(cfg.clipboard_db) == default_clipboard_path(), cfg.clipboard_db)
    legacy = ["roots", "extensions", "excludes", "index_path", "max_file_mb",
              "chunk_chars", "chunk_overlap", "embed_backend", "embed_model",
              "fastembed_model", "watch_interval", "watch_debounce", "web_host",
              "web_port", "ignore_gitignore", "max_line_chars", "ui_width",
              "ui_height", "debounce_ms", "theme", "bindings"]
    missing = [name for name in legacy if name not in Config.__dataclass_fields__]
    check("every pre-existing config field is still there", not missing, str(missing))
    check("the clipboard hotkey is recorded in the default bindings",
          cfg.bindings["clipboard"] == "Alt+Shift+C" and cfg.bindings["paste"] == "Enter",
          str(sorted(cfg.bindings)))
    check("the new fields are additive (from_dict tolerates them)",
          Config.from_dict({"clipboard_max_items": 42}).clipboard_max_items == 42
          and Config.from_dict({"clipboard_enabled": False}).clipboard_enabled is False)
    saved_path = Config(clipboard_db=os.path.join(tmp, "x.db"),
                        clipboard_max_items=7).save(os.path.join(tmp, "config.json"))
    reloaded = Config.load(saved_path)
    check("a saved config keeps the clipboard settings",
          reloaded.clipboard_max_items == 7
          and reloaded.clipboard_db == os.path.join(tmp, "x.db"),
          f"{reloaded.clipboard_max_items} {reloaded.clipboard_db}")

    example = json.loads(_read("config.example.json"))
    new_keys = ["clipboard_enabled", "clipboard_db", "clipboard_max_items",
                "clipboard_max_chars", "clipboard_poll_ms"]
    example_legacy = ["roots", "extensions", "excludes", "index_path",
                      "max_file_mb", "chunk_chars", "chunk_overlap",
                      "embed_backend", "embed_model", "watch_interval",
                      "watch_debounce", "web_host", "web_port",
                      "ignore_gitignore", "max_line_chars", "ui_width",
                      "ui_height", "debounce_ms", "theme", "bindings"]
    check("config.example.json documents every new key",
          not [key for key in new_keys if key not in example],
          str([key for key in new_keys if key not in example]))
    check("config.example.json documents each new key with a // comment",
          not [key for key in new_keys if f"//{key}" not in example])
    check("config.example.json preserves every existing key",
          not [name for name in example_legacy if name not in example],
          str([name for name in example_legacy if name not in example]))
    check("config.example.json is valid JSON naming clipboard.db",
          example["clipboard_db"].endswith("clipboard.db")
          and example["clipboard_max_items"] == 500)

    previous_home = os.environ.get("PLETHORA_HOME")
    env_home = os.path.join(tmp, "home")
    try:
        os.environ["PLETHORA_HOME"] = env_home
        check("PLETHORA_HOME is honoured for clipboard.db",
              default_clipboard_path() == Path(env_home) / "clipboard.db"
              and Path(Config().clipboard_db) == Path(env_home) / "clipboard.db",
              str(default_clipboard_path()))
        from_cfg = cb.from_config(Config(clipboard_db=os.path.join(tmp, "fromcfg.db"),
                                         clipboard_max_items=11))
        check("from_config() opens the store the config points at",
              from_cfg is not None and from_cfg.stats()["max_items"] == 11)
        from_cfg.close()
    finally:
        if previous_home is None:
            os.environ.pop("PLETHORA_HOME", None)
        else:
            os.environ["PLETHORA_HOME"] = previous_home

    return (programs, fake_apps, shortcuts, store, capped, watch_store, no_seq_store, threaded)
