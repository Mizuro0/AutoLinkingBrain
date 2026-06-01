"""Brain Viewer HTTP server: API поверх Mem0/Chroma + статика SPA.

Эндпоинты:
  GET    /api/memories          — все факты + cross_links из memory_cross_links.json
  GET    /api/health            — путь к Chroma, имя коллекции
  DELETE /api/memory/{id}       — удалить факт по id
  GET    /*                     — статика из viewer_web/ (index.html и ассеты)

Запуск: python viewer_server.py   (или scripts/start_brain_viewer.ps1)
Порт: переменная окружения VIEWER_PORT (по умолчанию 8501).
"""
from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import chromadb
from chromadb.config import Settings
from mem0 import Memory

from autolinkingbrain.brain_link_store import load_cross_links
from autolinkingbrain.mem0_kb_log import count_get_all_rows, log_mem0
from autolinkingbrain.mem0_lifecycle import is_stale_memory, stale_days_default
from autolinkingbrain.mem0_settings import CHROMA_COLLECTION, chroma_path_resolved, mem0_vector_config

WEB_ROOT = ROOT / "viewer_web"

_MIMES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".map": "application/json",
}


_mem: Memory | None = None


def _memory() -> Memory:
    """Ленивая инициализация Mem0 — чтобы отдача статики не требовала Ollama."""
    global _mem
    if _mem is None:
        _mem = Memory.from_config(config_dict=mem0_vector_config())
    return _mem


def _classify_scope(user_id: str) -> str:
    if user_id == "global_skills":
        return "global"
    if user_id == "global_topology":
        return "topology"
    if user_id.startswith("project_"):
        return "project"
    return "other"


def _discover_user_ids() -> list[str]:
    """Все уникальные user_id из метаданных Chroma (global_*, project_*, прочее)."""
    client = chromadb.PersistentClient(
        path=str(chroma_path_resolved()),
        settings=Settings(anonymized_telemetry=False),
    )
    col = client.get_collection(CHROMA_COLLECTION)

    seen: set[str] = set()
    offset = 0
    batch_size = 2000
    while True:
        batch = col.get(include=["metadatas"], limit=batch_size, offset=offset)
        metas = batch.get("metadatas") or []
        if not metas:
            break
        for meta in metas:
            uid = (meta or {}).get("user_id")
            if isinstance(uid, str) and uid:
                seen.add(uid)
        if len(metas) < batch_size:
            break
        offset += batch_size

    def _sort_key(uid: str) -> tuple[int, str]:
        scope = _classify_scope(uid)
        order = {"global": 0, "topology": 1, "project": 2, "other": 3}
        return order.get(scope, 9), uid

    return sorted(seen, key=_sort_key)


def _fetch_all() -> dict:
    """Возвращает плоский список узлов + счётчики по каналам."""
    try:
        user_ids = _discover_user_ids()
    except Exception as exc:
        return {
            "error": f"chroma_unavailable: {exc}",
            "nodes": [],
            "groups": {},
        }

    nodes: list[dict] = []
    groups: dict[str, int] = {}

    try:
        mem = _memory()
    except Exception as exc:
        return {"error": f"mem0_unavailable: {exc}", "nodes": [], "groups": {}}

    for uid in user_ids:
        try:
            raw = mem.get_all(filters={"user_id": uid}, top_k=500)
            log_mem0(
                "read",
                "viewer.brain.get_all",
                user_id=uid,
                top_k=500,
                rows=count_get_all_rows(raw),
            )
            rows = raw.get("results", []) if isinstance(raw, dict) else (raw or [])
        except Exception:
            rows = []
        groups[uid] = len(rows)
        for row in rows:
            meta = row.get("metadata") or {}
            updated_at = row.get("updated_at") or meta.get("updated_at") or ""
            created_at = row.get("created_at") or meta.get("created_at") or ""
            node = {
                "id": str(row.get("id", "")),
                "text": row.get("memory") or "",
                "user_id": uid,
                "scope": _classify_scope(uid),
                "metadata": meta,
                "updated_at": updated_at,
                "created_at": created_at,
            }
            node["stale"] = is_stale_memory(
                {"updated_at": updated_at, "created_at": created_at},
            )
            nodes.append(node)
    cross = load_cross_links()
    out: dict = {
        "nodes": nodes,
        "groups": groups,
        "stale_days": stale_days_default(),
    }
    # Для совместимости с фронтом: edges с полем rationale для агента/человека
    if isinstance(cross, dict) and isinstance(cross.get("edges"), list):
        out["cross_links"] = cross
    else:
        out["cross_links"] = {"version": 1, "edges": []}
    return out


def _fetch_metrics(*, days: float = 7.0, recent: int = 80) -> dict:
    try:
        from autolinkingbrain.brain_metrics import aggregate_for_viewer

        return aggregate_for_viewer(days=days, recent_limit=recent)
    except Exception as exc:
        return {"error": str(exc)}


class Handler(BaseHTTPRequestHandler):
    server_version = "BrainViewer/1.0"

    def log_message(self, fmt: str, *args) -> None:  # noqa: D401 (quiet log)
        return

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, obj) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path == "/api/memories":
            return self._send_json(200, _fetch_all())
        if path == "/api/metrics":
            qs = parse_qs(parsed.query)
            try:
                days = float((qs.get("days") or ["7"])[0])
            except (TypeError, ValueError):
                days = 7.0
            try:
                recent = int((qs.get("recent") or ["80"])[0])
            except (TypeError, ValueError):
                recent = 80
            recent = max(10, min(recent, 200))
            days = max(0.25, min(days, 90))
            return self._send_json(200, _fetch_metrics(days=days, recent=recent))
        if path == "/api/health":
            return self._send_json(
                200,
                {
                    "chroma": str(chroma_path_resolved()),
                    "collection": CHROMA_COLLECTION,
                    "stale_days": stale_days_default(),
                    "viewer_api": "1.1",
                    "metrics": True,
                },
            )
        return self._serve_static(path)

    def do_DELETE(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/memory/"):
            mid = unquote(path[len("/api/memory/"):])
            if not mid:
                return self._send_json(400, {"error": "empty id"})
            try:
                _memory().delete(mid)
                log_mem0("write", "viewer.brain.delete", memory_id=mid)
            except Exception as exc:
                return self._send_json(500, {"error": str(exc)})
            return self._send_json(200, {"ok": True, "id": mid})

        if path.startswith("/api/scope/"):
            uid = unquote(path[len("/api/scope/"):])
            return self._delete_batch(user_id=uid)

        if path == "/api/batch":
            return self._delete_batch_body()

        return self._send(404, b"not found", "text/plain; charset=utf-8")

    def _delete_batch(self, *, user_id: str) -> None:
        if not user_id:
            return self._send_json(400, {"error": "empty user_id"})
        try:
            mem = _memory()
            raw = mem.get_all(filters={"user_id": user_id}, top_k=1000)
            rows = raw.get("results", []) if isinstance(raw, dict) else (raw or [])
        except Exception as exc:
            return self._send_json(500, {"error": f"fetch failed: {exc}"})

        ids = [str(r.get("id")) for r in rows if r.get("id")]
        deleted, failed = 0, []
        for mid in ids:
            try:
                mem.delete(mid)
                deleted += 1
            except Exception as exc:
                failed.append({"id": mid, "error": str(exc)})
        log_mem0(
            "write",
            "viewer.brain.delete_scope",
            user_id=user_id,
            deleted=deleted,
            failed=len(failed),
        )
        return self._send_json(
            200,
            {"ok": True, "user_id": user_id, "deleted": deleted, "failed": failed},
        )

    def _delete_batch_body(self) -> None:
        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw_body = self.rfile.read(length) if length else b"{}"
            body = json.loads(raw_body or b"{}")
        except Exception as exc:
            return self._send_json(400, {"error": f"bad body: {exc}"})
        ids = body.get("ids") or []
        if not isinstance(ids, list) or not ids:
            return self._send_json(400, {"error": "ids list required"})
        mem = _memory()
        deleted, failed = 0, []
        for mid in ids:
            mid_str = str(mid)
            try:
                mem.delete(mid_str)
                deleted += 1
            except Exception as exc:
                failed.append({"id": mid_str, "error": str(exc)})
        log_mem0(
            "write",
            "viewer.brain.delete_batch",
            count=len(ids),
            deleted=deleted,
            failed=len(failed),
        )
        return self._send_json(
            200, {"ok": True, "deleted": deleted, "failed": failed}
        )

    def _serve_static(self, path: str) -> None:
        if path.startswith("/api/"):
            return self._send_json(
                404,
                {
                    "error": "unknown_api",
                    "path": path,
                    "hint": "Restart brain viewer: stop old process and run start.bat again.",
                },
            )
        if not WEB_ROOT.exists():
            return self._send(
                500,
                b"viewer_web/ not found. See README: brain viewer.",
                "text/plain; charset=utf-8",
            )
        rel = path.lstrip("/") or "index.html"
        candidate = (WEB_ROOT / rel).resolve()
        try:
            candidate.relative_to(WEB_ROOT.resolve())
        except ValueError:
            return self._send(403, b"forbidden", "text/plain; charset=utf-8")
        if not candidate.exists() or not candidate.is_file():
            candidate = WEB_ROOT / "index.html"
            if not candidate.exists():
                return self._send(404, b"not found", "text/plain; charset=utf-8")
        mime = _MIMES.get(candidate.suffix.lower(), "application/octet-stream")
        self._send(200, candidate.read_bytes(), mime)


def main() -> None:
    host = os.environ.get("VIEWER_HOST", "127.0.0.1")
    port = int(os.environ.get("VIEWER_PORT", "8501"))
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(
        f"Brain viewer: http://{host}:{port}/  "
        f"(chroma={chroma_path_resolved()}, collection={CHROMA_COLLECTION})"
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()


if __name__ == "__main__":
    main()
