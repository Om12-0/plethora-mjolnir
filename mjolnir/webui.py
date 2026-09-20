"""A tiny local web UI (stdlib http.server only) for natural-language retrieval.

Bind to 127.0.0.1 by default and never exposed to the network. Open the page,
type a plain-English query, and the exact file + page is one click away.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .search import Searcher

PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PLETHORA MJOLNIR</title>
<style>
  :root{
    --bg:#0b0f17; --panel:#131a26; --panel2:#1a2332; --line:#25324a;
    --fg:#e8eefc; --muted:#8ea0c0; --accent:#5ac8fa; --accent2:#a78bfa;
  }
  *{box-sizing:border-box}
  body{margin:0;background:radial-gradient(1200px 600px at 20% -10%,#16233a,#0b0f17 60%);
       color:var(--fg);font:15px/1.55 "Segoe UI",system-ui,sans-serif;min-height:100vh}
  header{padding:28px 22px 8px;max-width:1000px;margin:0 auto}
  h1{margin:0;font-size:24px;letter-spacing:.5px}
  h1 span{background:linear-gradient(90deg,var(--accent),var(--accent2));
    -webkit-background-clip:text;background-clip:text;color:transparent}
  .sub{color:var(--muted);font-size:13px;margin-top:4px}
  main{max-width:1000px;margin:0 auto;padding:18px 22px 60px}
  .bar{display:flex;gap:10px;margin:14px 0 6px}
  input[type=search]{flex:1;background:var(--panel);border:1px solid var(--line);
    color:var(--fg);padding:14px 16px;border-radius:12px;font-size:16px;outline:none}
  input[type=search]:focus{border-color:var(--accent);box-shadow:0 0 0 3px #5ac8fa22}
  button{background:var(--accent);color:#04121b;border:0;border-radius:12px;
    padding:0 20px;font-weight:700;cursor:pointer}
  button.ghost{background:var(--panel2);color:var(--fg);border:1px solid var(--line);font-weight:600}
  .chips{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0 18px}
  .chip{background:var(--panel2);border:1px solid var(--line);color:var(--muted);
    padding:6px 12px;border-radius:999px;font-size:12.5px;cursor:pointer}
  .chip:hover{color:var(--fg);border-color:var(--accent)}
  .meta{color:var(--muted);font-size:12.5px;margin:6px 2px 12px}
  .hit{background:var(--panel);border:1px solid var(--line);border-radius:14px;
    padding:14px 16px;margin-bottom:12px;transition:border-color .15s}
  .hit:hover{border-color:var(--accent)}
  .hit .top{display:flex;justify-content:space-between;gap:12px;align-items:baseline}
  .path{font-weight:600;word-break:break-all}
  .rank{color:var(--muted);font-size:12px;white-space:nowrap}
  .page{display:inline-block;background:#5ac8fa1f;color:var(--accent);
    border:1px solid #5ac8fa55;border-radius:8px;padding:1px 8px;font-size:12px;margin-left:8px}
  .snip{color:#c8d5ee;font-size:13.5px;margin:9px 0 12px;white-space:pre-wrap}
  .acts{display:flex;gap:8px}
  .acts button{padding:7px 14px;font-size:13px;border-radius:9px}
  mark{background:#a78bfa33;color:#e8eefc;border-radius:3px;padding:0 2px}
  .empty{color:var(--muted);text-align:center;padding:40px 10px}
  .badge{display:inline-block;background:var(--panel2);border:1px solid var(--line);
    color:var(--muted);border-radius:8px;padding:3px 9px;font-size:12px;margin-left:6px}
</style>
</head>
<body>
<header>
  <h1>PLETHORA <span>MJOLNIR</span></h1>
  <div class="sub">Local semantic search across your study &amp; work folders &mdash; ask in plain English.</div>
</header>
<main>
  <div class="bar">
    <input id="q" type="search" placeholder="e.g. circuit capacitor report from June" autofocus>
    <button id="go">Search</button>
    <button class="ghost" id="statsBtn">Stats</button>
  </div>
  <div class="chips" id="chips"></div>
  <div class="meta" id="meta"></div>
  <div id="results"></div>
</main>
<script>
const samples = [
  "circuit capacitor report from June",
  "restaurant database schema",
  "assignment normalization",
  "how does RC discharge work"
];
const chips = document.getElementById("chips");
samples.forEach(s => {
  const c = document.createElement("div");
  c.className = "chip"; c.textContent = s;
  c.onclick = () => { document.getElementById("q").value = s; run(); };
  chips.appendChild(c);
});
const qEl = document.getElementById("q");
const metaEl = document.getElementById("meta");
const resEl = document.getElementById("results");
const esc = s => (s||"").replace(/[&<>"]/g, m => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[m]));

async function run(){
  const q = qEl.value.trim();
  if(!q){ resEl.innerHTML = ""; metaEl.textContent = ""; return; }
  metaEl.textContent = "Searching…";
  const t0 = performance.now();
  const r = await fetch("/api/search?q=" + encodeURIComponent(q) + "&limit=12");
  const data = await r.json();
  const ms = (performance.now() - t0).toFixed(0);
  const hits = data.results || [];
  metaEl.innerHTML = hits.length
    ? `${hits.length} result(s) in ${ms} ms <span class="badge">${esc(data.mode)}</span>` +
      `<span class="badge">${esc(data.embedder)}</span>`
    : `No matches in ${ms} ms — try indexing first or different words.`;
  if(!hits.length){ resEl.innerHTML = '<div class="empty">Nothing found.</div>'; return; }
  resEl.innerHTML = hits.map((h,i) => `
    <div class="hit">
      <div class="top">
        <div class="path">${esc(h.name)}${h.page ? `<span class="page">page ${h.page}</span>` : ""}</div>
        <div class="rank">#${i+1} · score ${h.score.toFixed(4)}</div>
      </div>
      <div class="snip">${highlight(h.snippet, q)}</div>
      <div class="acts">
        <button onclick="openFile('${encodeURIComponent(h.path)}')">Open file</button>
        <button class="ghost" onclick="reveal('${encodeURIComponent(h.path)}')">Show in folder</button>
      </div>
    </div>`).join("");
}
function highlight(text, q){
  let out = esc(text);
  const terms = [...new Set((q.toLowerCase().match(/[a-z0-9_]+/g)||[]).filter(t=>t.length>1))];
  terms.forEach(t => { out = out.replace(new RegExp("("+t.replace(/[.*+?^${}()|[\]\\]/g,"\\$&")+")","gi"), "<mark>$1</mark>"); });
  return out;
}
async function openFile(p){ await fetch("/api/open?path=" + p); }
async function reveal(p){ await fetch("/api/reveal?path=" + p); }
async function stats(){
  const r = await fetch("/api/stats"); const s = await r.json();
  metaEl.innerHTML = `Indexed <b>${s.files}</b> files · <b>${s.chunks}</b> chunks · ` +
    `<b>${(s.vec_bytes/1048576).toFixed(1)} MB</b> vectors · FTS5 ${s.fts ? "on" : "off"}` +
    ` · vec ${esc(s.vec_backend || "-")}`;
}
document.getElementById("go").onclick = run;
document.getElementById("statsBtn").onclick = stats;
qEl.addEventListener("keydown", e => { if(e.key === "Enter") run(); });
stats();
</script>
</body>
</html>
"""


def _make_handler(searcher: Searcher, store, embedder_name: str, cfg):
    class Handler(BaseHTTPRequestHandler):
        server_version = "PlethoraMjolnir/1.0"

        def log_message(self, *args):  # silence default logging
            pass

        def _json(self, obj, code=200):
            body = json.dumps(obj).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            if parsed.path in ("/", "/index.html"):
                body = PAGE.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if parsed.path == "/api/search":
                query = (qs.get("q") or [""])[0]
                limit = int((qs.get("limit") or ["10"])[0])
                mode = (qs.get("mode") or ["hybrid"])[0]
                hits = searcher.search(query, limit=limit, mode=mode)
                self._json({
                    "query": query, "mode": mode, "embedder": embedder_name,
                    "results": [{
                        "path": h.path,
                        "name": os.path.basename(h.path),
                        "dir": os.path.dirname(h.path),
                        "page": h.page, "score": h.score, "snippet": h.snippet,
                        "matched": h.matched,
                    } for h in hits],
                })
                return
            if parsed.path == "/api/stats":
                self._json(store.stats())
                return
            if parsed.path == "/api/open":
                self._open((qs.get("path") or [""])[0])
                return
            if parsed.path == "/api/reveal":
                self._reveal((qs.get("path") or [""])[0])
                return
            self._json({"error": "not found"}, 404)

        def _open(self, path):
            path = os.path.abspath(path)
            if not os.path.isfile(path):
                return self._json({"ok": False, "error": "missing"}, 404)
            try:
                if sys.platform.startswith("win"):
                    os.startfile(path)  # noqa: type: ignore[attr-defined]
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", path])
                else:
                    subprocess.Popen(["xdg-open", path])
                self._json({"ok": True})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, 500)

        def _reveal(self, path):
            path = os.path.abspath(path)
            if not os.path.exists(path):
                return self._json({"ok": False, "error": "missing"}, 404)
            try:
                if sys.platform.startswith("win"):
                    subprocess.Popen(["explorer", "/select,", path])
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", "-R", path])
                else:
                    subprocess.Popen(["xdg-open", os.path.dirname(path)])
                self._json({"ok": True})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, 500)

    return Handler


def serve(cfg, store, embedder, open_browser: bool = True, log=print):
    searcher = Searcher(store, embedder)
    handler = _make_handler(searcher, store, getattr(embedder, "name", "?"), cfg)
    httpd = ThreadingHTTPServer((cfg.web_host, cfg.web_port), handler)
    url = f"http://{cfg.web_host}:{cfg.web_port}/"
    log(f"[mjolnir] web UI at {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log("\n[mjolnir] shutting down.")
    finally:
        httpd.server_close()
    return 0
