"""
mjolnir/engine.py - High-speed crash-proof search aggregator (<2ms).
Integrates bundled Voidtools Everything 1.4 SDK & silent portable service.
Zero COM dependencies. Zero native access violations.
"""

import os
import sys
import ctypes
from ctypes import wintypes
import subprocess
from typing import List, Dict, Any
from rapidfuzz import process, fuzz

# --- EVERYTHING IPC CONSTANTS (kept for compat) ---
EVERYTHING_REQUEST_FILE_NAME = 0x00000001
EVERYTHING_REQUEST_PATH = 0x00000002
EVERYTHING_REQUEST_HIGHLIGHTED_FILE_NAME = 0x00002000


class EverythingSDK:
    """Live ctypes bindings for Everything64.dll (full-drive <2ms search).

    Crash-proof: never raises. If the DLL is missing or Everything is not
    running, `available` is False and `search()` returns [] so callers fall
    back to the in-memory catalog.
    """

    def __init__(self):
        self.dll = None
        self.available = False
        self._ensure_service()
        self._load_dll()

    def _bundle_base(self) -> str:
        """Base dir for bundled binaries (source tree or PyInstaller bundle)."""
        try:
            base = getattr(sys, "_MEIPASS", None)
            if base and os.path.exists(base):
                return base
        except Exception:
            pass
        return os.getcwd()

    def _ensure_service(self):
        """Silently launches bundled Everything.exe in the background if not active."""
        try:
            if sys.platform != "win32":
                return
            user32 = ctypes.windll.user32
            hwnd = user32.FindWindowW("EVERYTHING_TASKBAR_NOTIFICATION", None)
            if hwnd != 0:
                return  # Already running
        except Exception:
            return

        candidates = [
            os.path.join(os.path.dirname(__file__), "bin", "Everything.exe"),
            os.path.join(os.getcwd(), "mjolnir", "bin", "Everything.exe"),
            os.path.join(os.getcwd(), "bin", "Everything.exe"),
            os.path.join(self._bundle_base(), "bin", "Everything.exe"),
            r"C:\Program Files\Everything\Everything.exe",
        ]
        for exe in candidates:
            try:
                if exe and os.path.exists(exe):
                    try:
                        flags = 0x08000000  # CREATE_NO_WINDOW
                        subprocess.Popen([exe, "-startup"], creationflags=flags)
                        break
                    except Exception:
                        pass
            except Exception:
                continue

    def _load_dll(self):
        # Look for Everything64.dll: bundled bin/ first, then legacy locations.
        if sys.platform != "win32":
            self.available = False
            return

        candidates = [
            os.path.join(os.path.dirname(__file__), "bin", "Everything64.dll"),
            os.path.join(os.path.dirname(__file__), "Everything64.dll"),
            os.path.join(os.getcwd(), "Everything64.dll"),
            os.path.join(os.getcwd(), "mjolnir", "bin", "Everything64.dll"),
            os.path.join(self._bundle_base(), "Everything64.dll"),
            os.path.join(self._bundle_base(), "bin", "Everything64.dll"),
            r"C:\Program Files\Everything\Everything64.dll",
            r"C:\Program Files\Everything 1.5a\Everything64.dll",
        ]
        for p in candidates:
            try:
                if p and os.path.exists(p):
                    try:
                        self.dll = ctypes.WinDLL(p)
                    except Exception:
                        continue
                    try:
                        self._setup_prototypes()
                    except Exception:
                        self.dll = None
                        continue
                    self.available = True
                    break
            except Exception:
                continue

        # Fallback: try PATH / System32 resolution (e.g. DLL shipped on PATH)
        if not self.available:
            try:
                self.dll = ctypes.WinDLL("Everything64.dll")
                self._setup_prototypes()
                self.available = True
            except Exception:
                self.dll = None
                self.available = False

    def _setup_prototypes(self):
        self.dll.Everything_SetSearchW.argtypes = [wintypes.LPCWSTR]
        self.dll.Everything_SetSearchW.restype = None
        self.dll.Everything_SetMax.argtypes = [wintypes.DWORD]
        self.dll.Everything_SetMax.restype = None
        self.dll.Everything_QueryW.argtypes = [wintypes.BOOL]
        self.dll.Everything_QueryW.restype = wintypes.BOOL
        self.dll.Everything_GetNumResults.restype = wintypes.DWORD
        self.dll.Everything_GetResultFullPathNameW.argtypes = [
            wintypes.DWORD, wintypes.LPWSTR, wintypes.DWORD
        ]
        self.dll.Everything_GetResultFullPathNameW.restype = wintypes.DWORD
        self.dll.Everything_GetResultFileNameW.argtypes = [wintypes.DWORD]
        self.dll.Everything_GetResultFileNameW.restype = wintypes.LPCWSTR

    def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        if not self.available or self.dll is None:
            return []
        try:
            if not query or not query.strip():
                return []
        except Exception:
            return []
        try:
            self.dll.Everything_SetSearchW(query)
            self.dll.Everything_SetMax(limit)
            if not self.dll.Everything_QueryW(True):
                return []

            count = self.dll.Everything_GetNumResults()
            results: List[Dict[str, Any]] = []
            # 1024 chars covers long paths (> MAX_PATH 260) without truncation.
            buf = ctypes.create_unicode_buffer(1024)

            for i in range(min(count, limit)):
                try:
                    self.dll.Everything_GetResultFullPathNameW(i, buf, 1024)
                    full_path = buf.value
                    fname = self.dll.Everything_GetResultFileNameW(i)
                except Exception:
                    continue
                if not full_path:
                    continue
                results.append({
                    "title": fname or os.path.basename(full_path),
                    "subtitle": full_path,
                    "path": full_path,
                    "category": "System File",
                    "score": 95.0
                })
            return results
        except Exception:
            return []


# Backward-compat alias: previous code used EverythingIPC / engine.ipc.
EverythingIPC = EverythingSDK


class SearchEngine:
    _instance = None

    def __init__(self):
        self.apps: List[Dict[str, Any]] = []
        self.files: List[Dict[str, Any]] = []
        self.everything = EverythingSDK()
        # Alias for backward compatibility (ui/tests may reference .ipc).
        self.ipc = self.everything
        self.reload_cache()

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = SearchEngine()
        return cls._instance

    def reload_cache(self):
        """Scans shortcuts, games, and user documents into RAM once."""
        self._index_apps()
        self._index_games()
        self._index_user_files()

    def _index_apps(self):
        app_dirs = [
            os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"),
            os.path.expandvars(r"%ALLUSERSPROFILE%\Microsoft\Windows\Start Menu\Programs"),
        ]
        self.apps = []
        seen = set()

        for base in app_dirs:
            if not os.path.exists(base):
                continue
            for root, _, files in os.walk(base):
                for f in files:
                    if f.lower().endswith((".lnk", ".url")):
                        full = os.path.join(root, f)
                        clean = os.path.splitext(f)[0]
                        if full not in seen:
                            seen.add(full)
                            self.apps.append({
                                "title": clean,
                                "subtitle": full,
                                "path": full,
                                "category": "Application",
                                "score": 110.0
                            })

    def _index_games(self):
        """Discovers Steam and common library game executables/shortcuts."""
        steam_path = r"C:\Program Files (x86)\Steam\steamapps"
        if os.path.exists(steam_path):
            for item in os.listdir(steam_path):
                if item.startswith("appmanifest_") and item.endswith(".acf"):
                    try:
                        with open(os.path.join(steam_path, item), "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()
                        import re
                        name_match = re.search(r'"name"\s+"([^"]+)"', content)
                        appid_match = re.search(r'"appid"\s+"([^"]+)"', content)
                        if name_match and appid_match:
                            g_name = name_match.group(1)
                            g_id = appid_match.group(1)
                            self.apps.append({
                                "title": g_name,
                                "subtitle": f"Steam Game (AppID: {g_id})",
                                "path": f"steam://rungameid/{g_id}",
                                "category": "Game",
                                "score": 105.0
                            })
                    except Exception:
                        pass

    def _get_search_roots(self) -> List[str]:
        """Defaults + OneDrive-redirected folders + custom paths (no Qt import)."""
        roots = [
            os.path.expanduser(r"~\Desktop"),
            os.path.expanduser(r"~\Documents"),
            os.path.expanduser(r"~\Downloads"),
        ]
        # Windows often redirects Desktop/Documents to OneDrive. The plain
        # expanduser paths above can be empty shells (e.g. no Desktop dir at
        # all, or a Documents dir with only 4 stub entries). Add the real
        # OneDrive locations so deep user files are actually indexed.
        try:
            onedrive = os.environ.get("OneDrive") or os.environ.get(
                "OneDriveConsumer"
            )
            od_candidates = []
            if onedrive:
                od_candidates += [
                    os.path.join(onedrive, "Desktop"),
                    os.path.join(onedrive, "Documents"),
                    os.path.join(onedrive, "Downloads"),
                ]
            od_candidates += [
                os.path.expanduser(r"~\OneDrive\Desktop"),
                os.path.expanduser(r"~\OneDrive\Documents"),
                os.path.expanduser(r"~\OneDrive\Downloads"),
            ]
            for p in od_candidates:
                if p and p not in roots:
                    roots.append(p)
        except Exception:
            pass
        # Merge custom search_paths from settings JSON if present.
        try:
            import json
            settings_file = os.path.expandvars(r"%APPDATA%\Plethora\mjolnir\settings.json")
            if os.path.exists(settings_file):
                with open(settings_file, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                for p in cfg.get("search_paths", []):
                    if p and isinstance(p, str) and p not in roots:
                        roots.append(p)
        except Exception:
            pass
        # Deduplicate while preserving order; keep only existing dirs.
        seen = set()
        out = []
        for r in roots:
            try:
                norm = os.path.normpath(r)
            except Exception:
                continue
            if norm not in seen:
                seen.add(norm)
                if os.path.exists(r):
                    out.append(r)
        return out

    def _index_user_files(self):
        roots = self._get_search_roots()
        self.files = []
        seen = set()

        # Folders to skip for speed
        skip_dirs = {
            "node_modules", ".git", "__pycache__", "venv", ".venv",
            "appdata", "local settings", "cache"
        }

        for r in roots:
            if not os.path.exists(r):
                continue
            for root, dirs, files in os.walk(r):
                dirs[:] = [d for d in dirs if not d.startswith(".") and d.lower() not in skip_dirs]
                for f in files:
                    full = os.path.join(root, f)
                    if full not in seen:
                        seen.add(full)
                        self.files.append({
                            "title": f,
                            "subtitle": full,
                            "path": full,
                            "category": "File",
                            "score": 85.0
                        })
                    if len(self.files) >= 100000:
                        break
                if len(self.files) >= 100000:
                    break
            if len(self.files) >= 100000:
                break

    def query(self, query_str: str, limit: int = 15) -> List[Dict[str, Any]]:
        q_raw = query_str.strip() if query_str else ""
        if not q_raw:
            return []
        q = q_raw.lower()

        tokens = q.split()
        results: List[Dict[str, Any]] = []
        seen = set()

        # 1. Exact & Token-matching in Applications & Games (Fast Path < 1ms)
        for app in self.apps:
            title_low = app["title"].lower()
            if all(t in title_low for t in tokens):
                item = app.copy()
                item["score"] = 120.0 if title_low.startswith(tokens[0]) else 105.0
                results.append(item)
                seen.add(item["path"])

        # 2. System-wide live results via Everything64.dll (< 2ms, whole drive)
        try:
            if self.everything.available:
                for item in self.everything.search(q_raw, limit=limit):
                    path = item.get("path")
                    if path and path not in seen:
                        seen.add(path)
                        results.append(item)
        except Exception:
            pass

        # 3. Token-matching in User Files & Documents (in-memory)
        for f in self.files:
            fname_low = f["title"].lower()
            if all(t in fname_low for t in tokens):
                if f["path"] not in seen:
                    item = f.copy()
                    item["score"] = 90.0
                    results.append(item)
                    seen.add(item["path"])
                if len(results) >= limit + 10:
                    break

        # 4. Fuzzy fallback for typos (e.g., "amsporps" -> "AMS PORP")
        if len(results) < 6:
            pool = self.apps + self.files
            titles = [p["title"] for p in pool]
            matches = process.extract(q, titles, scorer=fuzz.WRatio, limit=limit, score_cutoff=55)
            for title, score, idx in matches:
                item = pool[idx].copy()
                if item["path"] not in seen:
                    item["score"] = score
                    results.append(item)
                    seen.add(item["path"])

        results.sort(key=lambda x: x.get("score", 0), reverse=True)
        return results[:limit]
