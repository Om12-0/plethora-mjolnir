"""Aggregate checker: imports every mjolnir module + runs every check script.

Prints a PASS/FAIL/SKIP table and exits non-zero on any FAIL::

    python tests\\run_checks.py
"""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULES = [
    "mjolnir.config", "mjolnir.extract", "mjolnir.chunking", "mjolnir.embed",
    "mjolnir.store", "mjolnir.indexer", "mjolnir.search", "mjolnir.watcher",
    "mjolnir.webui", "mjolnir.cli", "mjolnir.styles", "mjolnir.openers",
    "mjolnir.actions", "mjolnir.action_handlers", "mjolnir.modes",
    "mjolnir.modes_matching", "mjolnir.open_scanner", "mjolnir.calc",
    "mjolnir.clipboard", "mjolnir.ui_components", "mjolnir.gui", "mjolnir.gui_tk",
    "mjolnir_ui", "mjolnir_ui.action_panel", "mjolnir_ui.hotkey_manager",
    "mjolnir_ui.inspector_pane", "mjolnir_ui.mode_router", "mjolnir_ui.mode_views",
    "mjolnir_ui.result_list", "mjolnir_ui.search_controller", "mjolnir_ui.tray_icon",
    "mjolnir_ui.window",
]
# Modules that legitimately need a GUI toolkit; a missing PySide6 is a SKIP.
QT_MODULES = {
    "mjolnir.ui_components", "mjolnir.gui",
    "mjolnir_ui", "mjolnir_ui.action_panel", "mjolnir_ui.hotkey_manager",
    "mjolnir_ui.inspector_pane", "mjolnir_ui.mode_router", "mjolnir_ui.mode_views",
    "mjolnir_ui.result_list", "mjolnir_ui.search_controller", "mjolnir_ui.tray_icon",
    "mjolnir_ui.window",
}


def _check_imports() -> tuple[str, str]:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    failed: list[str] = []
    skipped: list[str] = []
    for mod in MODULES:
        try:
            __import__(mod)
        except SystemExit as exc:
            if mod in QT_MODULES:
                skipped.append(f"{mod} (PySide6 missing: {exc})")
            else:
                failed.append(f"{mod}: SystemExit {exc}")
        except Exception as exc:
            if mod in QT_MODULES and "PySide6" in f"{type(exc).__name__} {exc}":
                skipped.append(f"{mod} ({exc})")
            else:
                failed.append(f"{mod}: {type(exc).__name__}: {exc}")
    if failed:
        return "FAIL", "; ".join(failed)
    if skipped:
        return "PASS", "imports ok (SKIP: " + "; ".join(skipped) + ")"
    return "PASS", "imports ok"


def _run_script(name: str) -> tuple[str, str]:
    path = os.path.join(ROOT, "tests", name)
    try:
        proc = subprocess.run(
            [sys.executable, path], cwd=ROOT, capture_output=True,
            text=True, timeout=180,
            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        )
    except subprocess.TimeoutExpired:
        return "FAIL", "timed out"
    out = (proc.stdout or "") + (proc.stderr or "")
    last = " | ".join([ln for ln in out.strip().splitlines() if ln.strip()][-3:])
    if proc.returncode != 0:
        return "FAIL", last or f"exit {proc.returncode}"
    if "[SKIP]" in out or "SKIP" in last:
        return "SKIP", last
    return "PASS", last


def main() -> int:
    sys.path.insert(0, ROOT)
    rows: list[tuple[str, str, str]] = []
    status, detail = _check_imports()
    rows.append(("imports", status, detail))
    for script, label in (("stress_wal.py", "wal_stress"),
                          ("check_highdpi.py", "highdpi"),
                          ("check_phase_a.py", "phase_a"),
                          ("check_phase_b.py", "phase_b"),
                          ("check_terminal_safety.py", "terminal_safety"),
                          ("check_tray_theme.py", "tray_theme"),
                          ("check_line_counts.py", "line_counts")):
        status, detail = _run_script(script)
        rows.append((label, status, detail))

    print(f"{'check':<16} {'result':<6} detail")
    print("-" * 76)
    failed = False
    for label, status, detail in rows:
        print(f"{label:<16} {status:<6} {detail[:110]}")
        if status == "FAIL":
            failed = True
    print("-" * 76)
    print("FAIL" if failed else "ALL PASS (skips allowed with reasons above)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
