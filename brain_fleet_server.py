#!/usr/bin/env python3
"""Brain Fleet Hub — admin ingest + dashboard (zero-sensitive telemetry)."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from autolinkingbrain.brain_fleet_sanitize import sanitize_payload, validate_payload

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("BRAIN_FLEET_DB", str(ROOT / "fleet_metrics.db")))
INSTALL_TOKEN = os.environ.get("BRAIN_FLEET_INSTALL_TOKEN", "")
ADMIN_TOKEN = os.environ.get("BRAIN_FLEET_ADMIN_TOKEN", "")
PORT = int(os.environ.get("BRAIN_FLEET_PORT", "8600"))


def _init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            install_ref TEXT,
            device_ref TEXT,
            project_ref TEXT,
            ts TEXT,
            payload_json TEXT NOT NULL,
            received_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def _store(payload: dict) -> None:
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        "INSERT INTO snapshots(install_ref, device_ref, project_ref, ts, payload_json, received_at) VALUES(?,?,?,?,?,?)",
        (
            payload.get("install_ref"),
            payload.get("device_ref"),
            payload.get("project_ref"),
            payload.get("ts"),
            json.dumps(payload),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def _list_snapshots(limit: int = 200) -> list[dict]:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT install_ref, device_ref, project_ref, ts, payload_json FROM snapshots ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        try:
            out.append(json.loads(r["payload_json"]))
        except json.JSONDecodeError:
            continue
    return out


class FleetHandler(BaseHTTPRequestHandler):
    def _auth_install(self) -> bool:
        if not INSTALL_TOKEN:
            return False
        auth = self.headers.get("Authorization", "")
        return auth == f"Bearer {INSTALL_TOKEN}"

    def _auth_admin(self) -> bool:
        if not ADMIN_TOKEN:
            return False
        auth = self.headers.get("Authorization", "")
        return auth == f"Bearer {ADMIN_TOKEN}"

    def _json(self, code: int, data: dict) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path: Path) -> None:
        if not path.is_file():
            self.send_error(404)
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/fleet.html" or parsed.path == "/":
            if not self._auth_admin():
                self.send_error(403)
                return
            html = ROOT / "viewer_web" / "fleet.html"
            self._file(html)
            return
        if parsed.path == "/api/fleet/snapshots":
            if not self._auth_admin():
                self.send_error(403)
                return
            qs = parse_qs(parsed.query)
            limit = int((qs.get("limit") or ["200"])[0])
            self._json(200, {"snapshots": _list_snapshots(limit=limit)})
            return
        self.send_error(404)

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/fleet/ingest":
            self.send_error(404)
            return
        if not self._auth_install():
            self.send_error(403)
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = json.loads(self.rfile.read(length).decode("utf-8"))
        ok, msg = validate_payload(raw)
        if not ok:
            self._json(400, {"error": msg})
            return
        try:
            clean = sanitize_payload(raw)
        except ValueError as exc:
            self._json(400, {"error": str(exc)})
            return
        _store(clean)
        self._json(200, {"ok": True})

    def log_message(self, format: str, *args) -> None:
        return


def main() -> None:
    _init_db()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), FleetHandler)
    print(f"Brain Fleet Hub http://0.0.0.0:{PORT}/fleet.html")
    server.serve_forever()


if __name__ == "__main__":
    main()
