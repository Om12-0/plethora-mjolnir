"""Live search worker and document query controller mixin for the launcher."""
from __future__ import annotations

import os
from typing import List, Optional

from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import QTimer, Signal

from mjolnir import actions, modes, openers
from .inspector_pane import match_capsule, preview_html
from .result_list import ResultItemWidget, category_of, format_mtime, format_size


class _SearchSignal(QtCore.QObject):
    requested = Signal(int, str)


class SearchWorker(QtCore.QThread):
    finished = Signal(int, list, str)
    results_ready = Signal(int, list)

    def __init__(self, searcher, lock=None, query_id: int = 0, query: str = ""):
        super().__init__()
        self.searcher = searcher
        self.lock = lock
        self.query_id = query_id
        self.req_id = query_id
        self.query = query

    @QtCore.Slot(int, str)
    def do_search(self, req_id: int, query: str):
        self.query_id = req_id
        self.req_id = req_id
        self.query = query
        self.run()

    def run(self):
        req = getattr(self, "query_id", 0) or getattr(self, "req_id", 0)
        try:
            if self.lock is not None:
                with self.lock:
                    hits = self.searcher.search(self.query, limit=12)
            else:
                hits = self.searcher.search(self.query, limit=12)
            self.results_ready.emit(req, hits)
            self.finished.emit(req, hits, "")
        except Exception as exc:
            self.results_ready.emit(req, [])
            self.finished.emit(req, [], str(exc))


class SearchControllerMixin:
    """Methods managing document querying, result rendering, and file preview."""

    def _schedule(self):
        if self.view == 1:  # VIEW_ACTIONS
            self.show_view(0)  # VIEW_SEARCH
        text = self.search.text() if hasattr(self, "search") else ""
        if not text.strip():
            self._abandon_pending_search()
            self._reset_list()
            self._refresh_stats()
            timer = getattr(self, "_search_timer", None) or getattr(self, "_timer", None)
            if timer is not None:
                timer.stop()
            return
        timer = getattr(self, "_search_timer", None) or getattr(self, "_timer", None)
        if timer is not None:
            timer.start()

    def _fire_query(self):
        timer = getattr(self, "_search_timer", None) or getattr(self, "_timer", None)
        if timer is not None:
            timer.stop()
        parsed = self.router.parse_query(self.search.text())
        self.parsed = parsed
        if parsed.mode != self.mode:
            self.mode = parsed.mode
            self.search.setPlaceholderText(modes.placeholder(parsed.mode))
        if not parsed.is_search:
            self._abandon_pending_search()
            if parsed.is_clipboard:
                self._show_clipboard(parsed.term)
            elif parsed.is_calc:
                self._show_calc(parsed.term)
            elif parsed.is_open:
                self._show_open(parsed.term)
            else:
                self._show_shell(parsed.term)
            return
        self._search_documents(parsed.term)

    def _abandon_pending_search(self):
        if self._busy or self._pending is not None:
            self._req_id += 1
            self._busy = False
            self._pending = None
        timer = getattr(self, "_search_timer", None) or getattr(self, "_timer", None)
        if timer is not None:
            timer.stop()
        self.spinner.hide()

    def _reset_list(self, title: str = "No selection", sub: str = "") -> None:
        self.hits = []
        self.rows = []
        self.results.clear()
        self.preview.clear()
        self.insp_title.setText(title)
        self.insp_sub.setText(sub)
        self._chunk_totals.clear()
        self._render_capsules(None, None, None, None)
        self._set_inspector_warning_border(False)

    def _set_inspector_warning_border(self, active: bool):
        if active:
            self.preview.setStyleSheet("border: 2px solid #F59E0B; border-radius: 6px;")
        else:
            self.preview.setStyleSheet("")

    def _search_documents(self, query: str):
        self.show_view(0)
        if self.rows:
            self._reset_list()
        if not query or not query.strip():
            self._reset_list()
            self._refresh_stats()
            return
        self._req_id += 1
        req = self._req_id
        self._query_by_req[req] = query
        if self._busy:
            self._pending = query
            return
        self._busy = True
        self.spinner.show()
        if hasattr(self, "_sig") and hasattr(self._sig, "requested"):
            self._sig.requested.emit(req, query)

    def _add_row(self, widget, height: int = 58, tooltip: str = "") -> None:
        item = QtWidgets.QListWidgetItem()
        item.setSizeHint(QtCore.QSize(0, int(height)))
        if tooltip:
            item.setToolTip(tooltip)
        self.results.addItem(item)
        self.results.setItemWidget(item, widget)

    @QtCore.Slot(int, list, str)
    def _on_results(self, req_id, hits, error):
        if req_id != self._req_id:
            return
        self._busy = False
        self.spinner.hide()
        if self.mode != modes.MODE_SEARCH or not self.parsed.is_search:
            self._pending = None
            return
        self.hits = hits
        self._chunk_totals.clear()
        self.results.clear()
        for position, h in enumerate(hits):
            item = QtWidgets.QListWidgetItem()
            widget = ResultItemWidget(
                os.path.basename(h.path), h.path,
                category_of(h.path), page=h.page, score=h.score,
                index=position + 1,
            )
            item.setSizeHint(QtCore.QSize(0, 58))
            item.setToolTip(h.path)
            self.results.addItem(item)
            self.results.setItemWidget(item, widget)
        if hits:
            self.results.setCurrentRow(0)
            self.status.setText(f"{len(hits)} result(s)")
        else:
            self.status.setText(error or "No matches — still indexing, or try other words.")
            self.preview.clear()
            self.insp_title.setText("No matches")
            self.insp_sub.setText("")
            self._render_capsules(None, None, None, None)
        self._query_by_req.pop(req_id, None)
        if hits:
            self._update_preview(0)

    def _chunk_total(self, path: str) -> int:
        if not path:
            return 0
        cached = self._chunk_totals.get(path)
        if cached is None:
            try:
                cached = int(self.store.chunk_count(path))
            except Exception:
                cached = 0
            self._chunk_totals[path] = cached
        return cached

    def _target_of(self, hit) -> "actions.Target":
        if hit is None:
            return actions.Target(path="")
        path = str(getattr(hit, "path", "") or "")
        return actions.Target(
            path=path,
            page=getattr(hit, "page", None),
            chunk_index=int(getattr(hit, "chunk_index", 0) or 0),
            chunk_total=self._chunk_total(path),
            snippet=str(getattr(hit, "snippet", "") or ""),
            score=float(getattr(hit, "score", 0.0) or 0.0),
        )

    def _update_preview(self, row):
        if not (0 <= row < len(self.hits)):
            return
        h = self.hits[row]
        query = self.parsed.term or self.search.text()
        try:
            st = os.stat(h.path)
            size_txt = format_size(st.st_size)
            mtime_txt = format_mtime(st.st_mtime)
        except OSError:
            size_txt, mtime_txt = "", ""
        self.insp_title.setText(os.path.basename(h.path))
        sub = h.path + (f"  ·  {size_txt}" if size_txt else "") + (f"  ·  {mtime_txt}" if mtime_txt else "")
        self.insp_sub.setText(sub)
        top = max((x.score for x in self.hits), default=h.score) or 1.0
        ratio = (h.score / top) if top > 0 else 0.0
        self._render_capsules(ratio, h.chunk_index, self._chunk_total(h.path), h.page)
        self.preview.setHtml(preview_html({
            "path": h.path, "name": os.path.basename(h.path),
            "page": h.page, "snippet": h.snippet, "score": h.score,
            "chunk_index": h.chunk_index, "query": query,
            "matched": getattr(h, "matched", []),
        }))

    def _render_capsules(self, score, chunk_index, chunk_total, page) -> None:
        widget = match_capsule(score, chunk_index, chunk_total, page)
        previous = self.insp_caps_widget
        if previous is not None:
            self.insp_caps.removeWidget(previous)
            previous.setParent(None)
            previous.deleteLater()
        self.insp_caps_widget = widget
        self.insp_caps.addWidget(widget)

    def _on_row_changed(self, row):
        if self.mode == modes.MODE_OPEN:
            self._update_open_preview(row)
            return
        if self.mode != modes.MODE_SEARCH:
            return
        self._update_preview(row)

    def _current_hit(self):
        row = self.results.currentRow()
        if 0 <= row < len(self.hits):
            return self.hits[row]
        return None

    def _open_selected(self):
        hit = self._current_hit()
        if hit:
            openers.open_target(hit.path, page=hit.page)
            self.hide()

    def _reveal_selected(self):
        hit = self._current_hit()
        if hit:
            openers.reveal(hit.path)

    def _copy_snippet(self):
        hit = self._current_hit()
        if not hit:
            return
        openers.copy_to_clipboard(hit.snippet or hit.path)
        self._toast("Snippet copied!")

    def _quick_jump(self, number: int) -> bool:
        row = int(number) - 1
        target = self.clipboard_list if self.view == 2 else self.results
        if not (0 <= row < target.count()):
            return False
        target.setCurrentRow(row)
        if self.view == 2:
            return True
        if self.mode == modes.MODE_OPEN:
            return self._activate_row()
        if self.mode != modes.MODE_SEARCH:
            return True
        return self.run_action("open_default")

    def _drop_current_row(self) -> None:
        row = self.results.currentRow()
        if row < 0 and self.results.count() > 0:
            row = 0
        if self.mode == modes.MODE_OPEN and 0 <= row < len(self.rows):
            self.rows.pop(row)
            item = self.results.takeItem(row)
            if item is not None:
                del item
            if self.rows:
                self.results.setCurrentRow(min(row, len(self.rows) - 1))
            else:
                self.results.clear()
                self.preview.clear()
                self.insp_title.setText("No selection")
                self.insp_sub.setText("")
            self.status.setText(f"{len(self.rows)} target(s)")
            return
        if 0 <= row < len(self.hits):
            self.hits.pop(row)
            item = self.results.takeItem(row)
            if item is not None:
                del item
        self._chunk_totals.clear()
        if self.hits:
            self.results.setCurrentRow(min(row, len(self.hits) - 1))
        else:
            self.results.clear()
            self.insp_title.setText("No selection")
            self.insp_sub.setText("")
            self.preview.clear()
            self._render_capsules(None, None, None, None)
        self.status.setText(f"{len(self.hits)} result(s)")

    def _refresh_stats(self):
        try:
            s = self.store.stats()
            dim = int(s.get("vec_dim", 0))
            if dim == 0 and hasattr(self.embedder, "dim") and self.embedder.dim:
                dim = int(self.embedder.dim)
                if self.store.vec_enabled:
                    self.store.ensure_vec_dim(dim)
                    s = self.store.stats()
            backend = s.get("vec_backend", "?")
            if dim == 0:
                import logging
                logging.getLogger("mjolnir.search").error(
                    "Vector dimension resolved to 0d! Embedder: %s, Store vec_enabled: %s",
                    getattr(self.embedder, "name", "None"), self.store.vec_enabled,
                )
            vec = f"{backend} ({dim}d)"
            self.status.setText(f"Indexed: {s['files']} files · {s['chunks']} chunks | Vector: {vec}")
        except Exception:
            self.status.setText("Ready.")

    def reindex(self):
        self.status.setText("Re-indexing…")
        import threading
        from mjolnir.indexer import Indexer

        def work():
            try:
                with self._lock:
                    idx = Indexer(self.cfg, self.store, self.embedder, log=lambda *_: None)
                    counters = idx.index_all()
                text = f"Indexed: {counters.get('added', 0) + counters.get('updated', 0)} updated · {counters.get('skipped', 0)} skipped"
            except Exception as exc:
                text = f"Reindex failed: {exc}"

            def done():
                self.status.setText(text)
                self._refresh_stats()
            QTimer.singleShot(0, done)

        threading.Thread(target=work, daemon=True).start()
