"""
mjolnir/engine.py - High-speed in-memory application and file search engine (<3ms).
Combines cached Start Menu shortcuts with tokenized Windows Search OLE DB.
"""

import os
import sys
import re
from typing import List, Dict, Any
from rapidfuzz import process, fuzz

class SearchEngine:
    _instance = None

    def __init__(self):
        self.apps: List[Dict[str, Any]] = []
        self.reload_apps()

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = SearchEngine()
        return cls._instance

    def reload_apps(self):
        """Pre-warms all installed apps and shortcuts into RAM (<20ms once at startup)."""
        app_dirs = [
            os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"),
            os.path.expandvars(r"%ALLUSERSPROFILE%\Microsoft\Windows\Start Menu\Programs"),
        ]
        self.apps = []
        seen = set()

        for d in app_dirs:
            if not os.path.exists(d):
                continue
            for root, _, files in os.walk(d):
                for f in files:
                    if f.lower().endswith((".lnk", ".url")):
                        full = os.path.join(root, f)
                        clean_name = os.path.splitext(f)[0]
                        if full not in seen:
                            seen.add(full)
                            self.apps.append({
                                "title": clean_name,
                                "subtitle": full,
                                "path": full,
                                "category": "Application",
                                "score": 100.0,
                                "icon": "app"
                            })

    def search_apps(self, query: str, limit: int = 6) -> List[Dict[str, Any]]:
        q = query.strip().lower()
        if not q:
            return []

        results = []
        # Prefix match
        for app in self.apps:
            name_lower = app["title"].lower()
            if name_lower.startswith(q):
                res = app.copy()
                res["score"] = 120.0
                results.append(res)
            elif q in name_lower:
                res = app.copy()
                res["score"] = 100.0
                results.append(res)

        if len(results) >= limit:
            return results[:limit]

        # Fuzzy fallback for typos
        names = [a["title"] for a in self.apps]
        fuzzy_matches = process.extract(
            query,
            names,
            scorer=fuzz.WRatio,
            limit=limit,
            score_cutoff=55
        )
        for name, score, idx in fuzzy_matches:
            match_app = self.apps[idx].copy()
            match_app["score"] = score
            if not any(r["path"] == match_app["path"] for r in results):
                results.append(match_app)

        return results[:limit]

    def search_files(self, query: str, limit: int = 15) -> List[Dict[str, Any]]:
        """Queries Windows Search Service with thread-safe COM initialization."""
        if sys.platform != "win32" or not query.strip():
            return []

        clean_q = re.sub(r'[^\w\s]', '', query).strip()
        tokens = clean_q.split()
        if not tokens:
            return []

        results = []
        try:
            import pythoncom
            import win32com.client

            pythoncom.CoInitialize()
            try:
                connection = win32com.client.Dispatch("ADODB.Connection")
                connection.Open("Provider=Search.CollatorDSO;Extended Properties='Application=Windows';")
                
                like_clauses = " AND ".join([f"(System.ItemName LIKE '%{t}%' OR System.ItemPathDisplay LIKE '%{t}%')" for t in tokens])
                sql = f"""
                    SELECT TOP {limit} 
                        System.ItemName, 
                        System.ItemPathDisplay, 
                        System.ItemType,
                        System.Size
                    FROM SystemIndex 
                    WHERE SCOPE='file:' AND ({like_clauses})
                    ORDER BY System.DateModified DESC
                """
                recordset = win32com.client.Dispatch("ADODB.Recordset")
                recordset.Open(sql, connection)
                
                while not recordset.EOF:
                    name = recordset.Fields.Item("System.ItemName").Value or ""
                    path = recordset.Fields.Item("System.ItemPathDisplay").Value or ""
                    if name and path and os.path.exists(path):
                        results.append({
                            "title": name,
                            "subtitle": path,
                            "path": path,
                            "category": "File",
                            "score": 85.0,
                            "icon": "file"
                        })
                    recordset.MoveNext()
                recordset.Close()
                connection.Close()
            finally:
                pythoncom.CoUninitialize()
        except Exception:
            pass

        return results

    def query(self, query_str: str) -> List[Dict[str, Any]]:
        if not query_str.strip():
            return []

        apps = self.search_apps(query_str, limit=8)
        files = self.search_files(query_str, limit=16)

        seen = {a["path"] for a in apps}
        combined = list(apps)
        for f in files:
            if f["path"] not in seen:
                seen.add(f["path"])
                combined.append(f)

        combined.sort(key=lambda x: x.get("score", 0), reverse=True)
        return combined
